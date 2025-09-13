# app/schemas/user.py

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List

# Импортируем общую схему для пагинированных ответов
# Предполагается, что она находится в app/schemas/utils.py
from .utils import PaginatedResponse


# --- Схемы для API-эндпоинтов ---

class UserCreate(BaseModel):
    """Схема для создания нового пользователя (используется внутри CRUD)."""
    telegram_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None


class UserUpdate(BaseModel):
    """Схема для обновления профиля пользователя (то, что приходит от Mini App)."""
    group_id: Optional[int] = None
    subgroup_number: Optional[int] = None
    settings: Optional[Dict[str, Any]] = None
    preferred_tutors: Optional[Dict[str, int]] = Field(
        default=None, 
        description="Словарь {subject_name: tutor_id} для выбора преподавателей"
    )


class UserBase(BaseModel):
    """
    Основная схема для отображения данных пользователя.
    Именно эта модель возвращается эндпоинтами /profile/me и /admin/users.
    """
    telegram_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    group_id: Optional[int] = None
    subgroup_number: Optional[int] = None
    settings: Dict[str, Any]
    is_blocked: bool
    
    # Это поле не хранится в БД, а вычисляется на лету в эндпоинте
    is_admin: bool = False
    
    # model_config позволяет Pydantic работать с моделями SQLAlchemy
    # и корректно преобразовывать их в JSON
    model_config = ConfigDict(from_attributes=True)


# --- Экспортируем PaginatedResponse с конкретным типом ---
# Это позволяет использовать schemas.user.PaginatedResponse[UserBase]
# в аннотациях типов в эндпоинтах, что делает код чище.
# Этот блок опционален, но является хорошей практикой.
class PaginatedUserResponse(PaginatedResponse[UserBase]):
    pass