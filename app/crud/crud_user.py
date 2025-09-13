# app/crud/crud_user.py
from typing import Optional
from sqlalchemy import String, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import UserCreate
from sqlalchemy import func
from sqlalchemy.sql.expression import cast

async def get_user_by_telegram_id(db: AsyncSession, *, telegram_id: int) -> User | None:
    """
    Получение пользователя по его Telegram ID.
    """
    result = await db.execute(select(User).filter(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, *, user_in: UserCreate) -> User:
    """
    Создание нового пользователя.
    """
    db_obj = User(
        telegram_id=user_in.telegram_id,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        username=user_in.username,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_users_by_group_id(db: AsyncSession, *, group_id: int) -> list[User]:
    stmt = select(User).where(User.group_id == group_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_users_paginated(
    db: AsyncSession, *, skip: int, limit: int, search: Optional[str] = None
) -> tuple[list[User], int]:
    """
    Получает пагинированный список пользователей с возможностью поиска.
    Поиск выполняется по telegram_id, username, first_name, last_name.
    """
    stmt = select(User)

    # --- НАЧАЛО ИЗМЕНЕНИЙ: ЛОГИКА ПОИСКА ---
    if search:
        # Преобразуем telegram_id в строку для универсального поиска
        telegram_id_str = cast(User.telegram_id, String)
        
        # Используем or_ для поиска по любому из полей
        search_filter = or_(
            telegram_id_str.ilike(f"%{search}%"),
            User.username.ilike(f"%{search}%"),
            User.first_name.ilike(f"%{search}%"),
            User.last_name.ilike(f"%{search}%")
        )
        stmt = stmt.where(search_filter)
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    # Сначала считаем общее количество без лимитов
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Затем применяем пагинацию и сортировку
    result_stmt = stmt.offset(skip).limit(limit).order_by(User.telegram_id)
    result = await db.execute(result_stmt)
    
    return result.scalars().all(), total

async def update_user_block_status(db: AsyncSession, user_id: int, is_blocked: bool) -> Optional[User]:
    user = await get_user_by_telegram_id(db, telegram_id=user_id)
    if user:
        user.is_blocked = is_blocked
        await db.commit()
        await db.refresh(user)
    return user

async def get_all_active_users(db: AsyncSession) -> list[User]:
    """Получает всех незаблокированных пользователей."""
    stmt = select(User).where(User.is_blocked == False)
    result = await db.execute(stmt)
    return result.scalars().all()

async def set_user_group(db: AsyncSession, user_id: int, group_id: int) -> Optional[User]:
    """Устанавливает основную группу для пользователя."""
    user = await get_user_by_telegram_id(db, telegram_id=user_id)
    if user:
        user.group_id = group_id
        await db.commit()
        await db.refresh(user)
    return user