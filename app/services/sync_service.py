# app/services/sync_service.py

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, delete

from app.core.omsu_api import api_client
from app.models.schedule import Group, Tutor, Auditory, Lesson
from app.crud.crud_schedule import get_lessons_for_group
from app.schemas.notifications import ScheduleChange, LessonInfo
from app.core.queue import push_changes_to_queue

# Настраиваем логгер
logger = logging.getLogger(__name__)


def generate_lesson_hash(lesson_data: dict) -> str:
    """Генерирует стабильный хэш для объекта занятия."""
    stable_data = lesson_data.copy()
    stable_data.pop("id", None)
    stable_data.pop("publishDate", None)
    encoded_data = json.dumps(stable_data, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded_data).hexdigest()


class SyncService:
    async def sync_dictionaries(self, db: AsyncSession):
        """Синхронизирует справочники: группы, преподаватели, аудитории."""
        logger.info("Starting dictionaries sync...")
        try:
            # Синхронизация групп
            groups_data = await api_client.get_groups()
            if groups_data:
                normalized_groups = [
                    {"id": g.get("id"), "name": g.get("name"), "real_group_id": g.get("real_group_id")}
                    for g in groups_data if g.get("id") is not None
                ]
                if normalized_groups:
                    stmt = insert(Group).values(normalized_groups)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['id'],
                        set_={'name': stmt.excluded.name, 'real_group_id': stmt.excluded.real_group_id}
                    )
                    await db.execute(stmt)
                    logger.info(f"Synced {len(normalized_groups)} groups.")

            # Синхронизация преподавателей
            tutors_data = await api_client.get_tutors()
            if tutors_data:
                normalized_tutors = [t for t in tutors_data if t.get("id") is not None and t.get("name") not in ('-', '--', '_')]
                if normalized_tutors:
                    stmt = insert(Tutor).values(normalized_tutors)
                    stmt = stmt.on_conflict_do_update(index_elements=['id'], set_={'name': stmt.excluded.name})
                    await db.execute(stmt)
                    logger.info(f"Synced {len(normalized_tutors)} tutors.")

            # Синхронизация аудиторий
            auditories_data = await api_client.get_auditories()
            if auditories_data:
                normalized_auditories = [a for a in auditories_data if a.get("id") is not None]
                if normalized_auditories:
                    stmt = insert(Auditory).values(normalized_auditories)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['id'],
                        set_={'name': stmt.excluded.name, 'building': stmt.excluded.building}
                    )
                    await db.execute(stmt)
                    logger.info(f"Synced {len(normalized_auditories)} auditories.")
            
            await db.commit()
            logger.info("Dictionaries sync finished successfully.")
        except Exception as e:
            logger.error(f"FATAL error during dictionaries sync: {e}", exc_info=True)
            await db.rollback()

    async def find_schedule_changes(
        self, db: AsyncSession, group_id: int, lessons_from_api: List[Dict[str, Any]]
    ) -> List[ScheduleChange]:
        """
        Сравнивает данные из API с данными в БД и возвращает список изменений,
        произошедших СЕГОДНЯ или В БУДУЩЕМ.
        """
        changes: List[ScheduleChange] = []
        today = date.today()
        
        db_lessons_raw = await get_lessons_for_group(db, group_id=group_id)
        db_lessons = {l.source_id: l for l in db_lessons_raw}
        
        api_lessons_map: Dict[int, Dict[str, Any]] = {}

        # 1. Проходим по данным из API (ищем НОВЫЕ и ОБНОВЛЕННЫЕ занятия)
        for day_data in lessons_from_api:
            for lesson_api in day_data.get("lessons", []):
                source_id = lesson_api.get('id')
                if not source_id: continue
                
                try:
                    lesson_date = datetime.strptime(lesson_api.get('day', ''), "%d.%m.%Y").date()
                except (ValueError, TypeError):
                    continue

                if lesson_date < today:
                    continue # Игнорируем изменения, дата которых уже прошла

                api_lessons_map[source_id] = lesson_api
                lesson_hash = generate_lesson_hash(lesson_api)

                lesson_after_info = LessonInfo(
                    source_id=source_id, date=lesson_api.get('day', ''),
                    time_slot=lesson_api.get('time', 0), subject_name=lesson_api.get('lesson', 'N/A')
                )
                
                if source_id not in db_lessons:
                    changes.append(ScheduleChange(change_type="NEW", group_id=group_id, lesson_after=lesson_after_info))
                elif db_lessons[source_id].content_hash != lesson_hash:
                    db_lesson = db_lessons[source_id]
                    lesson_before_info = LessonInfo(
                        source_id=db_lesson.source_id, date=db_lesson.date.strftime("%d.%m.%Y"),
                        time_slot=db_lesson.time_slot, subject_name=db_lesson.subject_name
                    )
                    changes.append(ScheduleChange(
                        change_type="UPDATED", group_id=group_id,
                        lesson_before=lesson_before_info, lesson_after=lesson_after_info
                    ))

        # 2. Проходим по данным из БД (ищем ОТМЕНЕННЫЕ занятия)
        for source_id, db_lesson in db_lessons.items():
            if source_id not in api_lessons_map:
                if db_lesson.date < today:
                    continue # Игнорируем отмену занятий, которые уже прошли

                changes.append(ScheduleChange(
                    change_type="CANCELLED", group_id=group_id,
                    lesson_before=LessonInfo(
                        source_id=db_lesson.source_id, date=db_lesson.date.strftime("%d.%m.%Y"),
                        time_slot=db_lesson.time_slot, subject_name=db_lesson.subject_name
                    )
                ))
        return changes

    async def sync_schedules_for_groups(self, db: AsyncSession, group_ids: list[int]):
        """
        Синхронизирует расписание для ЗАДАННОГО списка групп, находит изменения,
        отправляет уведомления, обновляет БД и удаляет отмененные занятия.
        """
        if not group_ids:
            logger.info("Received empty list of group_ids to sync. Skipping.")
            return

        logger.info(f"Starting schedule sync for {len(group_ids)} groups...")
        current_sync_time = datetime.now(timezone.utc)
        
        tutors_res = await db.execute(select(Tutor.id))
        existing_tutor_ids = {id for id, in tutors_res}
        auditories_res = await db.execute(select(Auditory.id))
        existing_auditory_ids = {id for id, in auditories_res}
        
        for i, group_id in enumerate(group_ids):
            try:
                lessons_from_api = await api_client.get_schedule_for_group(group_id)
                if lessons_from_api is None:
                    logger.warning(f"API returned an error for group {group_id}. Skipping.")
                    continue

                changes = await self.find_schedule_changes(db, group_id, lessons_from_api)
                
                lessons_to_delete_ids = []
                if changes:
                    await push_changes_to_queue(changes)
                    lessons_to_delete_ids = [c.lesson_before.source_id for c in changes if c.change_type == "CANCELLED" and c.lesson_before]
                    logger.info(f"Found {len(changes)} changes for group {group_id} ({len(lessons_to_delete_ids)} to delete). Pushing to queue.")

                lessons_to_upsert = []
                if lessons_from_api:
                    for day_data in lessons_from_api:
                        for lesson_api in day_data.get("lessons", []):
                            source_id, teacher_id, auditory_id, day_str, lesson_id = (
                                lesson_api.get('id'), lesson_api.get('teacher_id'),
                                lesson_api.get('auditory_id'), lesson_api.get('day'),
                                lesson_api.get('lesson_id')
                            )
                            if not all([source_id, teacher_id, auditory_id, day_str, lesson_id]): continue
                            if teacher_id not in existing_tutor_ids: continue
                            if auditory_id not in existing_auditory_ids: continue
                            
                            lessons_to_upsert.append({
                                "source_id": source_id, "lesson_id": lesson_id,
                                "date": datetime.strptime(day_str, "%d.%m.%Y").date(),
                                "time_slot": lesson_api.get('time', 0), "subgroup_name": lesson_api.get('subgroupName'),
                                "subject_name": lesson_api.get('lesson', 'N/A'), "lesson_type": lesson_api.get('type_work', 'N/A'),
                                "content_hash": generate_lesson_hash(lesson_api), "last_seen_at": current_sync_time,
                                "group_id": group_id, "tutor_id": teacher_id, "auditory_id": auditory_id
                            })
                
                if lessons_to_upsert:
                    stmt = insert(Lesson).values(lessons_to_upsert)
                    update_dict = {c.name: getattr(stmt.excluded, c.name) for c in Lesson.__table__.columns if not c.primary_key}
                    stmt = stmt.on_conflict_do_update(index_elements=['source_id'], set_=update_dict)
                    await db.execute(stmt)
                
                if lessons_to_delete_ids:
                    delete_stmt = delete(Lesson).where(Lesson.source_id.in_(lessons_to_delete_ids))
                    await db.execute(delete_stmt)
                
                if lessons_to_upsert or lessons_to_delete_ids:
                    await db.commit()
                
                logger.info(f"Processed group {group_id} ({i+1}/{len(group_ids)}): Upserted {len(lessons_to_upsert)}, Deleted {len(lessons_to_delete_ids)}.")

            except Exception as e:
                logger.error(f"Failed to process group_id={group_id}: {e}", exc_info=True)
                await db.rollback()

    async def cleanup_old_lessons(self, db: AsyncSession):
        """Удаляет занятия, которые не были видны в течение последних 3 дней."""
        logger.info("Starting old lessons cleanup task...")
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        stmt = delete(Lesson).where(Lesson.last_seen_at < three_days_ago)
        result = await db.execute(stmt)
        await db.commit()
        logger.info(f"Cleaned up {result.rowcount} old lesson entries.")

sync_service = SyncService()