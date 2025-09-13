# app/schemas/schedule.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date

# Вспомогательные схемы для вложенных объектов
class TutorBase(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

class AuditoryBase(BaseModel):
    id: int
    name: str
    building: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
    
class GroupBase(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

# Основная схема для одного занятия (Lesson)
class Lesson(BaseModel):
    source_id: int = Field(alias="id")
    time_slot: int
    subgroup_name: Optional[str] = None
    subject_name: str
    lesson_type: str
    
    # --- ДОБАВЛЯЕМ ИНФОРМАЦИЮ О ГРУППЕ ---
    group: GroupBase # <-- Добавляем эту строку
    
    tutor: TutorBase
    auditory: AuditoryBase
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# Схема для расписания на один день
class DaySchedule(BaseModel):
    date: date
    lessons: List[Lesson]

# Схема для элемента в списке элективов
class ElectiveChoice(BaseModel):
    subject_name: str
    tutors: List[TutorBase]

# Схема для пагинированного ответа
class PaginatedResponse[T](BaseModel):
    total: int
    page: int
    size: int
    items: List[T]