# app/crud/crud_schedule.py
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import date, timedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.schedule import Group, Lesson, Tutor
from sqlalchemy import distinct
from app.models.user import User
from datetime import datetime, timedelta
from app.core.config import settings

async def get_all_groups_ids(db: AsyncSession) -> list[int]:
    """Возвравращает список ID всех групп из БД."""
    result = await db.execute(select(Group.id))
    return result.scalars().all()


async def get_schedule_for_group_by_date(
    db: AsyncSession, *, group_id: int, target_date: date
) -> list[Lesson]:
    """
    Получает расписание для группы на конкретную дату.
    Использует жадную загрузку для связанных данных.
    """
    stmt = (
        select(Lesson)
        .where(Lesson.group_id == group_id, Lesson.date == target_date)
        .options(
            # Добавляем жадную загрузку ВСЕХ необходимых полей
            selectinload(Lesson.group),
            selectinload(Lesson.tutor), 
            selectinload(Lesson.auditory)
        )
        .order_by(Lesson.time_slot)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# --- Убедимся, что и другие функции исправлены ---
async def get_schedule_for_group_for_period(
    db: AsyncSession, *, group_id: int, start_date: date, end_date: date
) -> list[Lesson]:
    """Получает расписание для группы за период с жадной загрузкой."""
    stmt = (
        select(Lesson)
        .where(
            Lesson.group_id == group_id,
            Lesson.date >= start_date,
            Lesson.date <= end_date
        )
        .options(
            selectinload(Lesson.group), # <-- Проверяем наличие
            selectinload(Lesson.tutor),
            selectinload(Lesson.auditory)
        )
        .order_by(Lesson.date, Lesson.time_slot)
    )
    result = await db.execute(stmt)
    return result.scalars().all()



async def get_schedule_for_group_for_week(
    db: AsyncSession, *, group_id: int, target_date: date
) -> list[Lesson]:
    """
    Получает расписание для группы на неделю (с понедельника по воскресенье),
    в которую входит target_date.
    """
    # Определяем начало (понедельник) и конец (воскресенье) недели
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    stmt = (
        select(Lesson)
        .where(
            Lesson.group_id == group_id,
            Lesson.date >= start_of_week,
            Lesson.date <= end_of_week
        )
        .options(
            selectinload(Lesson.tutor),
            selectinload(Lesson.auditory)
        )
        .order_by(Lesson.date, Lesson.time_slot)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_groups_paginated(
    db: AsyncSession, *, skip: int = 0, limit: int = 100, search: Optional[str] = None
) -> tuple[list[Group], int]:
    """Получает список групп с пагинацией и поиском, исключая технические группы."""
    stmt = select(Group)
    
    stmt = stmt.where(
        ~Group.name.contains('#'),      # Исключаем технические
        ~Group.name.contains('/'),      # <-- ИСКЛЮЧАЕМ ПОДГРУППЫ
        ~Group.name.startswith('Д-'),
        ~Group.name.startswith('И-1-О-Ин.яз')
    )

    if search:
        stmt = stmt.where(Group.name.ilike(f"%{search}%"))

    # Сначала считаем общее количество без лимитов
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Затем применяем пагинацию и сортировку
    result_stmt = stmt.offset(skip).limit(limit).order_by(Group.name)
    result = await db.execute(result_stmt)
    
    return result.scalars().all(), total

# Аналогичную функцию можно создать для преподавателей (Tutor)
async def get_tutors_paginated(
    db: AsyncSession, *, skip: int = 0, limit: int = 100, search: Optional[str] = None
) -> tuple[list[Tutor], int]:
    """Получает список преподавателей с пагинацией и поиском, исключая пустые записи."""
    stmt = select(Tutor)
    
    stmt = stmt.where(
        Tutor.name.notin_(['-', '--', '_'])
    )

    if search:
        stmt = stmt.where(Tutor.name.ilike(f"%{search}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result_stmt = stmt.offset(skip).limit(limit).order_by(Tutor.name)
    result = await db.execute(result_stmt)
    
    return result.scalars().all(), total

async def get_lessons_for_group(db: AsyncSession, *, group_id: int) -> List[Lesson]:
    """
    Получает ВСЕ записи о занятиях для одной группы.
    Нужно для сервиса синхронизации для сравнения.
    """
    stmt = select(Lesson).where(Lesson.group_id == group_id)
    result = await db.execute(stmt)
    return result.scalars().all()




async def get_lesson_by_source_id(db: AsyncSession, *, source_id: int) -> Optional[Lesson]:
    """
    Находит одно занятие по его первичному ключу (source_id).
    """
    stmt = select(Lesson).where(Lesson.source_id == source_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_group_by_id(db: AsyncSession, group_id: int) -> Optional[Group]:
    """
    Получает одну учебную группу по ее уникальному идентификатору.
    """
    # db.get() - это самый эффективный способ получить объект по первичному ключу.
    # Он не требует написания явного SELECT-запроса.
    return await db.get(Group, group_id)



# --- ИСПРАВЛЯЕМ НОВЫЕ ФУНКЦИИ ---

async def get_schedule_for_tutor_for_period(
    db: AsyncSession, *, tutor_id: int, start_date: date, end_date: date
) -> list[Lesson]:
    """Получает расписание для преподавателя за период с жадной загрузкой."""
    stmt = (
        select(Lesson)
        .where(
            Lesson.tutor_id == tutor_id,
            Lesson.date >= start_date,
            Lesson.date <= end_date
        )
        .options(
            # Здесь это уже было, но проверяем еще раз
            selectinload(Lesson.group),
            selectinload(Lesson.tutor),
            selectinload(Lesson.auditory)
        )
        .order_by(Lesson.date, Lesson.time_slot)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_schedule_for_auditory_for_period(
    db: AsyncSession, *, auditory_id: int, start_date: date, end_date: date
) -> list[Lesson]:
    """Получает расписание для аудитории за период с жадной загрузкой."""
    stmt = (
        select(Lesson)
        .where(
            Lesson.auditory_id == auditory_id,
            Lesson.date >= start_date,
            Lesson.date <= end_date
        )
        .options(
            # И здесь тоже
            selectinload(Lesson.group),
            selectinload(Lesson.tutor),
            selectinload(Lesson.auditory)
        )
        .order_by(Lesson.date, Lesson.time_slot)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_active_user_group_ids(db: AsyncSession) -> list[int]:
    """
    Возвращает уникальный список ID групп, в которых состоит
    хотя бы один активный (не заблокированный) пользователь.
    """
    stmt = (
        select(distinct(User.group_id))
        .where(User.group_id != None, User.is_blocked == False)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_lessons_starting_soon(db: AsyncSession, interval_minutes: int) -> list[Lesson]:
    """
    Находит все занятия, которые начнутся в заданном временном интервале от текущего момента.
    Например, interval_minutes=30 найдет занятия, начинающиеся через 29-30 минут.
    """
    lesson_start_times = settings.lesson_times_map


    now = datetime.now()
    # Ищем занятия, которые начнутся через `interval_minutes`
    target_time = now + timedelta(minutes=interval_minutes)
    
    # Находим, какой номер пары соответствует этому времени
    target_slot = 0
    for slot, time_str in lesson_start_times.items():
        h, m = map(int, time_str.split(':'))
        if target_time.hour == h and target_time.minute == m:
            target_slot = slot
            break
    
    if not target_slot:
        return [] # Сейчас не время для напоминаний

    # Ищем все занятия на сегодня в найденном временном слоте
    stmt = (
        select(Lesson)
        .where(Lesson.date == now.date(), Lesson.time_slot == target_slot)
        .options(selectinload(Lesson.tutor), selectinload(Lesson.auditory))
    )
    result = await db.execute(stmt)
    return result.scalars().all()