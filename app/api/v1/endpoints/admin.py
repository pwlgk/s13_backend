# app/api/v1/endpoints/admin.py
import logging
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.queue import push_broadcast_to_queue
from app.core.queue import push_message_to_chat_queue # Новая функция для Redis
from app import schemas, models
from app.api import deps
from app.crud import crud_user
from app.db.session import get_db
from app.schemas import group_chat
from app.crud import crud_chat
from app.core.queue import push_control_command

from app.worker import scheduler, run_hot_schedule_sync, run_dict_sync

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Модели для запросов ---
class ChatMessage(BaseModel):
    message: str

class BroadcastMessage(BaseModel):
    message: str

# --- Эндпоинты для управления пользователями ---

@router.get(
    "/users", 
    response_model=schemas.user.PaginatedResponse[schemas.user.UserBase],
    summary="[Admin] Get all users with search"
)
async def admin_read_users(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(20, ge=1, le=100, description="Количество элементов на странице"),
    # --- НАЧАЛО ИЗМЕНЕНИЙ: ДОБАВЛЯЕМ ПАРАМЕТР SEARCH ---
    search: Optional[str] = Query(None, min_length=2, description="Поисковый запрос"),
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
    admin: models.user.User = Depends(deps.get_current_admin_user)
):
    """
    [Admin] Получить пагинированный список всех пользователей системы.
    Поддерживает поиск по ID, username, имени и фамилии.
    """
    skip = (page - 1) * size
    # --- Передаем search в CRUD-функцию ---
    users, total = await crud_user.get_users_paginated(
        db, skip=skip, limit=size, search=search
    )
    return {"total": total, "page": page, "size": size, "items": users}

@router.post(
    "/users/{user_id}/block", 
    response_model=schemas.user.UserBase,
    summary="[Admin] Block a user"
)
async def admin_block_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: models.user.User = Depends(deps.get_current_admin_user)
):
    """
    [Admin] Заблокировать пользователя по его Telegram ID.
    Заблокированный пользователь не сможет использовать API.
    """
    user = await crud_user.update_user_block_status(db, user_id=user_id, is_blocked=True)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post(
    "/users/{user_id}/unblock", 
    response_model=schemas.user.UserBase,
    summary="[Admin] Unblock a user"
)
async def admin_unblock_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: models.user.User = Depends(deps.get_current_admin_user)
):
    """
    [Admin] Разблокировать пользователя по его Telegram ID.
    """
    user = await crud_user.update_user_block_status(db, user_id=user_id, is_blocked=False)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# --- Эндпоинты для управления системой ---

@router.post(
    "/system/trigger-schedule-sync", 
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Admin] Trigger HOT schedule sync"
)
async def trigger_schedule_sync(admin: models.user.User = Depends(deps.get_current_admin_user)):
    """
    [Admin] Принудительно запустить синхронизацию расписания для 'горячих' групп
    (групп с активными пользователями).
    """
    try:
        # --- ИСПОЛЬЗУЕМ НОВУЮ ЗАДАЧУ ---
        await push_control_command("run_hot_schedule_sync")
        return {"message": "Task 'run_hot_schedule_sync' has been queued for the worker."}
    except Exception as e:
        # Логирование ошибки на сервере
        # logger.error(f"Error triggering schedule sync: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/system/trigger-dict-sync", 
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Admin] Trigger dictionaries sync"
)
async def trigger_dict_sync(admin: models.user.User = Depends(deps.get_current_admin_user)):
    """
    [Admin] Принудительно запустить фоновую задачу синхронизации справочников.
    """
    try:
        await push_control_command("run_dict_sync")
        return {"message": "Task 'run_dict_sync' has been queued for the worker."}
    except Exception as e:
        # logger.error(f"Error triggering dict sync: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
@router.post(
    "/system/broadcast", 
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Admin] Send broadcast message"
)
async def broadcast_message(
    broadcast_in: BroadcastMessage,
    admin: models.user.User = Depends(deps.get_current_admin_user) # <- Мы уже получаем админа
):
    """
    [Admin] Отправить широковещательное сообщение всем пользователям.
    """
    if not broadcast_in.message or len(broadcast_in.message) < 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is too short.")
        
    # Передаем и сообщение, и ID админа
    await push_broadcast_to_queue(
        message=broadcast_in.message, 
        admin_id=admin.telegram_id
    )
    return {"message": f"Broadcast task has been queued. A report will be sent to you ({admin.telegram_id}) upon completion."}

@router.get(
    "/chats",
    response_model=schemas.user.PaginatedResponse[group_chat.GroupChatBase],
    summary="[Admin] Get list of group chats"
)
async def admin_get_chats(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: models.user.User = Depends(deps.get_current_admin_user),
):
    """[Admin] Получить список чатов, в которые добавлен бот."""
    skip = (page - 1) * size
    chats, total = await crud_chat.get_chats_paginated(db, skip=skip, limit=size)
    return {"total": total, "page": page, "size": size, "items": chats}

@router.post(
    "/chats/{chat_id}/send-message",
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Admin] Send message to a chat"
)
async def admin_send_message_to_chat(
    chat_id: int,
    message_in: ChatMessage,
    admin: models.user.User = Depends(deps.get_current_admin_user),
):
    """[Admin] Отправить сообщение в конкретный чат через бота."""
    await push_message_to_chat_queue(chat_id=chat_id, message=message_in.message)
    return {"message": f"Task to send message to chat {chat_id} has been queued."}