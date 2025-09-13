# app/api/v1/endpoints/lessons.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List # Добавим List для будущего

from app import models, schemas
from app.api import deps
from app.crud import crud_homework, crud_schedule
from app.db.session import get_db

router = APIRouter()

@router.get(
    "/{lesson_source_id}/homework",
    response_model=Optional[schemas.homework.HomeworkBase],
    summary="Get homework for a lesson"
)
async def get_homework(
    lesson_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.user.User = Depends(deps.get_current_user),
):
    """
    Получить домашнее задание для конкретного занятия.
    Возвращает null, если ДЗ не добавлено.
    """
    homework = await crud_homework.get_homework_by_lesson_id(db, lesson_id=lesson_source_id)
    return homework


@router.post(
    "/{lesson_source_id}/homework",
    response_model=schemas.homework.HomeworkBase,
    summary="Add or update homework for a lesson"
)
async def add_or_update_homework(
    lesson_source_id: int,
    homework_in: schemas.homework.HomeworkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.user.User = Depends(deps.get_current_user),
):
    """
    Добавить или обновить домашнее задание для занятия.
    Проверяет, что пользователь редактирует ДЗ только для своей группы.
    """
    # 1. Проверяем, настроена ли у пользователя группа
    if not current_user.group_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must have a group set in your profile to add homework."
        )

    # 2. Находим занятие в БД
    lesson = await crud_schedule.get_lesson_by_source_id(db, source_id=lesson_source_id)
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    # 3. Сравниваем группу пользователя и группу занятия
    if lesson.group_id != current_user.group_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only add homework for lessons of your own group."
        )
    
    # 4. Если все проверки пройдены, создаем/обновляем ДЗ
    homework = await crud_homework.create_or_update_homework(
        db,
        lesson=lesson, # Передаем уже найденный объект для оптимизации
        author_id=current_user.telegram_id,
        homework_in=homework_in
    )
        
    return homework