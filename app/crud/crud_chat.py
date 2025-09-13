# app/crud/crud_chat.py
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from sqlalchemy.orm import selectinload
from app.models.group_chat import GroupChat
from app.models.schedule import Group
from sqlalchemy import func

async def get_chat_by_id(db: AsyncSession, chat_id: int) -> Optional[GroupChat]:
    """
    Получает чат по ID и сразу же подгружает связанную с ним группу.
    """
    # --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
    stmt = (
        select(GroupChat)
        .where(GroupChat.chat_id == chat_id)
        .options(selectinload(GroupChat.linked_group)) # <-- Жадная загрузка
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_chat(db: AsyncSession, chat_id: int, title: str, is_active: bool = True) -> GroupChat:
    chat = await get_chat_by_id(db, chat_id)
    if chat:
        chat.title = title
        chat.is_active = is_active
    else:
        chat = GroupChat(chat_id=chat_id, title=title, is_active=is_active)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat

async def link_chat_to_group(db: AsyncSession, chat_id: int, group_name: str) -> Optional[GroupChat]:
    # Сначала ищем группу по имени
    group_stmt = select(Group).where(Group.name.ilike(group_name))
    group_result = await db.execute(group_stmt)
    group = group_result.scalar_one_or_none()

    if not group:
        return None # Группа не найдена

    chat = await get_chat_by_id(db, chat_id)
    if chat:
        chat.linked_group_id = group.id
        await db.commit()
        await db.refresh(chat)
    
    return chat


async def get_user_chats_with_linked_group(db: AsyncSession, user_id: int) -> list[GroupChat]:
    """
    Находит все активные чаты с привязанной группой, в которых (предположительно) состоит пользователь.
    ВНИМАНИЕ: Мы не можем реально проверить, состоит ли пользователь в чате,
    мы можем только предполагать это.
    """
    # Этот запрос просто вернет все чаты. В реальном приложении нужна была бы
    # таблица M2M `chat_members`, которая наполняется при вступлении/выходе.
    # Для нашей цели рекомендации этого будет достаточно.
    stmt = (
        select(GroupChat)
        .where(GroupChat.is_active == True, GroupChat.linked_group_id != None)
        .options(selectinload(GroupChat.linked_group)) # Подгружаем группу
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_chats_paginated(db: AsyncSession, skip: int, limit: int) -> tuple[list[GroupChat], int]:
    """Получает пагинированный список чатов, в которых состоит бот."""
    stmt = (
        select(GroupChat)
        .where(GroupChat.is_active == True)
        .options(selectinload(GroupChat.linked_group))
    )
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()
    
    result_stmt = stmt.offset(skip).limit(limit).order_by(GroupChat.title)
    result = await db.execute(result_stmt)
    
    return result.scalars().all(), total