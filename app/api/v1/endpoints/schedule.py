# app/api/v1/endpoints/schedule.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from typing import List, Optional
from collections import defaultdict
from app.schemas import schedule
from app import schemas, models
from app.api import deps
from app.crud import crud_schedule
from app.db.session import get_db

router = APIRouter()

def filter_lessons_by_preferences(
    lessons: list[models.schedule.Lesson],
    user: models.user.User
) -> list[models.schedule.Lesson]:
    """
    Главная функция фильтрации. Сначала по подгруппе, затем по преподавателям.
    """
    # 1. Фильтрация по подгруппе
    if user.subgroup_number:
        user_subgroup_str_part = f"/{user.subgroup_number}"
        lessons = [
            lesson for lesson in lessons
            if not lesson.subgroup_name or user_subgroup_str_part in lesson.subgroup_name
        ]
    
    # 2. Фильтрация по выбранным преподавателям для элективов
    # Получаем предпочтения, ключ - НАЗВАНИЕ ПРЕДМЕТА, значение - ID преподавателя
    preferred_tutors = user.settings.get("preferred_tutors", {})
    if not preferred_tutors:
        return lessons

    # Группируем занятия по номеру пары (time_slot), чтобы найти элективы
    lessons_by_slot = defaultdict(list)
    for lesson in lessons:
        lessons_by_slot[lesson.time_slot].append(lesson)

    final_lessons = []
    for time_slot, slot_lessons in lessons_by_slot.items():
        # Если в слоте только одно занятие, оно не электив, просто добавляем его
        if len(slot_lessons) == 1:
            final_lessons.append(slot_lessons[0])
            continue
        
        # Если в слоте несколько занятий (электив), ищем предпочтение
        # Используем НАЗВАНИЕ ПРЕДМЕТА как ключ. У всех вариантов оно будет одинаковое.
        subject_name_key = slot_lessons[0].subject_name
        
        preferred_tutor_id = preferred_tutors.get(subject_name_key)
        
        if preferred_tutor_id:
            # Ищем занятие с выбранным преподавателем
            found_preferred = False
            for lesson in slot_lessons:
                if lesson.tutor_id == preferred_tutor_id:
                    final_lessons.append(lesson)
                    found_preferred = True
                    break
            # Если по какой-то причине выбранного преподавателя сегодня нет,
            # показываем все доступные варианты, чтобы студент не пропустил пару.
            if not found_preferred:
                final_lessons.extend(slot_lessons)
        else:
            # Если для этого электива выбор не сделан, показываем все варианты
            final_lessons.extend(slot_lessons)
            
    return sorted(final_lessons, key=lambda l: l.time_slot)


@router.get("/my/day", response_model=schedule.DaySchedule)
async def get_my_schedule_for_day(
    target_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: models.user.User = Depends(deps.get_current_user),
):
    """
    Получение личного расписания на указанный день.
    Учитывает группу, подгруппу и выбранных преподавателей.
    """
    if not current_user.group_id:
        raise HTTPException(status_code=404, detail="User has no group assigned")

    all_lessons_for_group = await crud_schedule.get_schedule_for_group_by_date(
        db, group_id=current_user.group_id, target_date=target_date
    )
    
    filtered_lessons = filter_lessons_by_preferences(all_lessons_for_group, current_user)

    return {"date": target_date, "lessons": filtered_lessons}


@router.get(
    "/my/electives", 
    response_model=schemas.schedule.PaginatedResponse[schemas.schedule.ElectiveChoice] # <--- ИЗМЕНЯЕМ МОДЕЛЬ ОТВЕТА
)
async def get_my_electives(
    db: AsyncSession = Depends(get_db),
    current_user: models.user.User = Depends(deps.get_current_user),
    # --- ДОБАВЛЯЕМ ПАРАМЕТРЫ ПАГИНАЦИИ ---
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50)
):
    """
    Проанализировать расписание пользователя и вернуть пагинированный список дисциплин,
    требующих выбора преподавателя.
    """
    if not current_user.group_id:
        raise HTTPException(status_code=404, detail="User has no group assigned")
    
    
    # Получаем всё будущее расписание для группы (можно ограничить семестром)
    all_future_lessons = await crud_schedule.get_schedule_for_group_for_week(
        db, group_id=current_user.group_id, target_date=date.today()
    ) # Для примера берем текущую неделю, в проде можно брать дальше

    # Группируем занятия по названию предмета
    lessons_by_subject = defaultdict(list)
    for lesson in all_future_lessons:
        lessons_by_subject[lesson.subject_name].append(lesson)
        
    electives = []
    for subject_name, lessons in lessons_by_subject.items():
        unique_tutors = {lesson.tutor for lesson in lessons}
        if len(unique_tutors) > 1:
            electives.append({
                "subject_name": subject_name,
                "tutors": sorted(list(unique_tutors), key=lambda t: t.name)
            })
    
    # Сортируем для консистентного вывода
    electives.sort(key=lambda x: x['subject_name'])

    # --- НАЧАЛО ИЗМЕНЕНИЙ: ЛОГИКА ПАГИНАЦИИ "В ПАМЯТИ" ---
    total_electives = len(electives)
    start = (page - 1) * size
    end = start + size
    
    paginated_items = electives[start:end]
    
    return {
        "total": total_electives,
        "page": page,
        "size": size,
        "items": paginated_items
    }


@router.get(
    "/search",
    response_model=List[schemas.schedule.DaySchedule],
    summary="Search schedule by group, tutor, or auditory"
)
async def search_schedule(
    target_date: date,
    group_id: Optional[int] = Query(None, description="ID группы для поиска"),
    tutor_id: Optional[int] = Query(None, description="ID преподавателя для поиска"),
    auditory_id: Optional[int] = Query(None, description="ID аудитории для поиска"),
    db: AsyncSession = Depends(get_db),
    current_user: models.user.User = Depends(deps.get_current_user),
):
    """
    Получить расписание на неделю для группы, преподавателя или аудитории.
    
    Необходимо указать **только один** из параметров: `group_id`, `tutor_id` или `auditory_id`.
    `target_date` - любая дата в пределах нужной недели.
    """
    # Проверяем, что передан ровно один поисковый параметр
    search_params = [group_id, tutor_id, auditory_id]
    if sum(p is not None for p in search_params) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must provide exactly one of: group_id, tutor_id, or auditory_id"
        )
        
    # Определяем начало и конец недели
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    lessons_db = []
    if group_id:
        lessons_db = await crud_schedule.get_schedule_for_group_for_period(
            db, group_id=group_id, start_date=start_of_week, end_date=end_of_week
        )
    elif tutor_id:
        lessons_db = await crud_schedule.get_schedule_for_tutor_for_period(
            db, tutor_id=tutor_id, start_date=start_of_week, end_date=end_of_week
        )
    elif auditory_id:
        lessons_db = await crud_schedule.get_schedule_for_auditory_for_period(
            db, auditory_id=auditory_id, start_date=start_of_week, end_date=end_of_week
        )
        
    # Группируем занятия по дням (эта логика остается прежней)
    schedule_by_day = defaultdict(list)
    for lesson in lessons_db:
        schedule_by_day[lesson.date].append(lesson)
        
    response_data = [
        {"date": day, "lessons": lessons}
        for day, lessons in sorted(schedule_by_day.items())
    ]
    
    return response_data