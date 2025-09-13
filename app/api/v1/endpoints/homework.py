# app/api/v1/endpoints/homework.py

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date, timedelta
from pydantic import constr
from typing import Optional, Annotated 

from app import models, schemas
from app.api import deps
from app.crud import crud_homework
from app.db.session import get_db
from app.bot.utils import get_week_dates # Импортируем нашу утилиту для расчета недель

# Импортируем Pydantic-схемы
from app.schemas.utils import PaginatedResponse
from app.schemas.homework import HomeworkWithLesson

router = APIRouter()

@router.get(
    "/my",
    response_model=PaginatedResponse[HomeworkWithLesson],
    summary="Get my paginated and filtered homework list"
)
async def get_my_homework_list(
    db: AsyncSession = Depends(get_db),
    current_user: models.user.User = Depends(deps.get_current_user),
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(10, ge=1, le=50, description="Количество элементов на странице"),
    status: Annotated[
        Optional[str], 
        Query(description="Фильтр по статусу: 'expired' или 'actual'", pattern=r"^(expired|actual)$")
    ] = None,
    week: Annotated[
        Optional[str], 
        Query(description="Быстрый фильтр по неделе: 'current' или 'next'", pattern=r"^(current|next)$")
    ] = None,
    subject_search: Annotated[
        Optional[str], 
        Query(min_length=3, description="Поиск по названию предмета")
    ] = None,
):
    """
    Получить пагинированный список всех домашних заданий для группы пользователя.
    
    Поддерживает комбинированную фильтрацию и поиск.
    """
    if not current_user.group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User profile is not configured with a group."
        )

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    today = date.today()
    
    # Обрабатываем быстрые фильтры по неделям
    if week == "current":
        start_date, end_date = get_week_dates(today)
    elif week == "next":
        # Находим следующий понедельник
        next_monday = today + timedelta(days=(7 - today.weekday()))
        start_date, end_date = get_week_dates(next_monday)
    
    skip = (page - 1) * size
    
    homework_list, total = await crud_homework.get_homework_for_user_group_paginated(
        db,
        user=current_user,
        skip=skip,
        limit=size,
        status=status,
        subject_search=subject_search,
        start_date=start_date,
        end_date=end_date
    )
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": homework_list
    }