# app/api/v1/endpoints/dictionaries.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app import schemas
from app.api import deps
from app.crud import crud_schedule
from app.db.session import get_db
from app import models
router = APIRouter()

@router.get("/groups", response_model=schemas.schedule.PaginatedResponse[schemas.schedule.GroupBase])
async def read_groups(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=2)
):
    """
    Получить пагинированный список групп с возможностью поиска.
    """
    skip = (page - 1) * size
    groups, total = await crud_schedule.get_groups_paginated(
        db, skip=skip, limit=size, search=search
    )
    return {"total": total, "page": page, "size": size, "items": groups}


@router.get("/tutors", response_model=schemas.schedule.PaginatedResponse[schemas.schedule.TutorBase])
async def read_tutors(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=2)
):
    """
    Получить пагинированный список преподавателей с возможностью поиска.
    """
    skip = (page - 1) * size
    tutors, total = await crud_schedule.get_tutors_paginated(
        db, skip=skip, limit=size, search=search
    )
    return {"total": total, "page": page, "size": size, "items": tutors}

@router.get(
    "/groups/{group_id}",
    response_model=schemas.schedule.GroupBase,
    summary="Get a single group by ID"
)
async def read_group_by_id(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    # Добавляем зависимость, чтобы только авторизованные пользователи могли делать запрос
    current_user: models.user.User = Depends(deps.get_current_user)
):
    """
    Получить информацию о конкретной учебной группе по ее ID.
    """
    group = await crud_schedule.get_group_by_id(db, group_id=group_id)
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with ID {group_id} not found"
        )
        
    return group