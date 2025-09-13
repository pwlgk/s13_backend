# app/schemas/homework.py
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime, date
from .schedule import Lesson
# Импортируем схему пользователя для вложенного отображения автора
from .user import UserBase

# Схема для создания/обновления ДЗ (то, что приходит от фронтенда)
class HomeworkCreate(BaseModel):
    content: str

# Базовая схема для отображения ДЗ
class HomeworkBase(BaseModel):
    id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    lesson_source_id: int
    
    # Включаем полную информацию об авторе
    author: UserBase

    model_config = ConfigDict(from_attributes=True)

class LessonForHomework(BaseModel):
    """Урезанная информация о занятии для страницы ДЗ."""
    source_id: int
    subject_name: str
    date: date
    model_config = ConfigDict(from_attributes=True)
    
class HomeworkWithLesson(HomeworkBase):
    """Схема ДЗ, включающая информацию о занятии."""
    lesson: LessonForHomework