# app/schemas/notifications.py
from pydantic import BaseModel
from typing import Optional

class LessonInfo(BaseModel):
    source_id: int # <-- Добавьте это поле
    date: str
    time_slot: int
    subject_name: str

class ScheduleChange(BaseModel):
    """Модель одного изменения в расписании."""
    change_type: str  # "NEW", "UPDATED", "CANCELLED"
    group_id: int
    lesson_before: Optional[LessonInfo] = None # Старое состояние (для UPDATED и CANCELLED)
    lesson_after: Optional[LessonInfo] = None  # Новое состояние (для NEW и UPDATED)pip