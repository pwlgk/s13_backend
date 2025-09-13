# app/api/v1/endpoints/profile.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.crud import crud_user
from app.db.session import get_db
from app.models.user import User
from app.core.config import settings
router = APIRouter()

@router.get("/me", response_model=schemas.user.UserBase)
def read_user_me(
    # --- ИСПОЛЬЗУЕМ НОВУЮ ЗАВИСИМОСТЬ ---
current_user: User = Depends(deps.get_current_user_allow_blocked),):
    """
    Get current user's profile.
    Returns user data even if the user is blocked.
    """
    # ... (логика с добавлением флага is_admin остается без изменений)
    user_data = current_user.__dict__
    try:
        admin_ids_str = settings.ADMIN_TELEGRAM_IDS.split(',')
        admin_ids = [int(admin_id.strip()) for admin_id in admin_ids_str]
        user_data["is_admin"] = current_user.telegram_id in admin_ids
    except (ValueError, AttributeError):
        user_data["is_admin"] = False
    
    return user_data


@router.put("/me", response_model=schemas.user.UserBase)
async def update_user_me(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: schemas.user.UserUpdate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update current user's profile.
    """
    update_data = user_in.model_dump(exclude_unset=True)
    
    # Обновляем базовые поля
    if "group_id" in update_data:
        current_user.group_id = update_data["group_id"]
    if "subgroup_number" in update_data:
        current_user.subgroup_number = update_data["subgroup_number"]

    # --- НАЧАЛО ИСПРАВЛЕНИЙ ---
    
    # Создаем копию текущих настроек, чтобы не изменять объект "на месте"
    new_settings = dict(current_user.settings or {})

    # Обновляем общие настройки, если они переданы
    if "settings" in update_data and update_data["settings"] is not None:
        new_settings.update(update_data["settings"])

    # Обновляем/добавляем предпочтения по преподавателям
    if "preferred_tutors" in update_data and update_data["preferred_tutors"] is not None:
        if "preferred_tutors" not in new_settings:
            new_settings["preferred_tutors"] = {}
        # Используем .update() для слияния, а не полной замены
        new_settings["preferred_tutors"].update(update_data["preferred_tutors"])

    # Переприсваиваем новый объект полю модели.
    # Теперь SQLAlchemy точно знает, что поле изменилось.
    current_user.settings = new_settings
    
    # Альтернативный, более явный способ (если переприсваивание не сработает):
    # flag_modified(current_user, "settings")

    # --- КОНЕЦ ИСПРАВЛЕНИЙ ---
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return current_user