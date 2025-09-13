# app/crud/crud_homework.py
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from app.models.homework import Homework
from app.models.schedule import Lesson
from app.models.user import User
from app.schemas.homework import HomeworkCreate
from app import models
from datetime import date

async def get_homework_by_lesson_id(db: AsyncSession, *, lesson_id: int) -> Optional[Homework]:
    """Получает ДЗ для конкретного занятия, подгружая автора."""
    stmt = (
        select(Homework)
        .where(Homework.lesson_source_id == lesson_id)
        .options(selectinload(Homework.author))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def create_or_update_homework(
    db: AsyncSession, *, lesson: Lesson, author_id: int, homework_in: HomeworkCreate
) -> Homework:
    """
    Создает или обновляет ДЗ, принимая уже загруженный объект Lesson.
    """
    # Теперь нам не нужно искать занятие, оно уже передано
    # lesson = await db.get(Lesson, lesson_id) ...

    existing_homework = await get_homework_by_lesson_id(db, lesson_id=lesson.source_id)
    
    if existing_homework:
        # Обновляем
        existing_homework.content = homework_in.content
        existing_homework.author_telegram_id = author_id
        db_obj = existing_homework
    else:
        # Создаем новое
        db_obj = Homework(
            content=homework_in.content,
            lesson_source_id=lesson.source_id,
            author_telegram_id=author_id
        )
    
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

async def get_homework_for_user_group_paginated(
    db: AsyncSession, *, user: models.user.User, skip: int, limit: int
) -> tuple[list[Homework], int]:
    """
    Получает пагинированный список ДЗ для группы пользователя.
    Сортирует по дате занятия.
    """
    if not user.group_id:
        return [], 0

    # Запрос для получения ДЗ с присоединением занятий
    stmt = (
        select(Homework)
        .join(Homework.lesson)
        .where(Lesson.group_id == user.group_id)
        .options(selectinload(Homework.author), selectinload(Homework.lesson))
    )
    
    # Считаем общее количество
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Применяем сортировку и пагинацию
    result_stmt = stmt.order_by(Lesson.date.desc()).offset(skip).limit(limit)
    result = await db.execute(result_stmt)
    
    return result.scalars().all(), total



# --- НОВАЯ ФУНКЦИЯ ---
async def get_homework_for_user_group_paginated(
    db: AsyncSession,
    *,
    user: User,
    skip: int,
    limit: int,
    # --- НОВЫЕ ПАРАМЕТРЫ ФИЛЬТРАЦИИ ---
    status: Optional[str] = None, # "expired" или "actual"
    subject_search: Optional[str] = None,
    start_date: Optional[date] = None, # Для "на этой неделе", "на следующей"
    end_date: Optional[date] = None,
) -> tuple[List[Homework], int]:
    """
    Получает пагинированный и отфильтрованный список ДЗ для группы пользователя.
    """
    if not user.group_id:
        return [], 0

    stmt = (
        select(Homework)
        .join(Homework.lesson)
        .where(Lesson.group_id == user.group_id)
        .options(
            selectinload(Homework.author),
            selectinload(Homework.lesson)
        )
    )

    # --- ПРИМЕНЯЕМ НОВЫЕ ФИЛЬТРЫ ---
    today = date.today()
    if status == "expired":
        stmt = stmt.where(Lesson.date < today)
    elif status == "actual":
        stmt = stmt.where(Lesson.date >= today)
    
    if subject_search:
        stmt = stmt.where(Lesson.subject_name.ilike(f"%{subject_search}%"))

    # Фильтры по датам (для кастомного периода)
    if start_date:
        stmt = stmt.where(Lesson.date >= start_date)
    if end_date:
        stmt = stmt.where(Lesson.date <= end_date)
    # --- КОНЕЦ НОВЫХ ФИЛЬТРОВ ---
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Сортировка: сначала актуальные, потом истекшие
    order_logic = Lesson.date.desc() if status == "expired" else Lesson.date.asc()
    result_stmt = stmt.order_by(order_logic).offset(skip).limit(limit)
    
    result = await db.execute(result_stmt)
    return result.scalars().all(), total