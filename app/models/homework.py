# app/models/homework.py

from sqlalchemy import Column, Integer, Text, BigInteger, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from app.db.base import Base

class Homework(Base):
    __tablename__ = "homework"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # Связь с занятием. source_id - это PK в таблице lessons
    lesson_source_id = Column(BigInteger, ForeignKey("lessons.source_id"), nullable=False, index=True)
    
    # Связь с пользователем, который добавил/изменил ДЗ
    author_telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)

    # Определяем relationships для удобного доступа через ORM
    lesson = relationship("Lesson", back_populates="homework")
    author = relationship("User")


# Дополняем модель Lesson, чтобы она знала о домашних заданиях
from .schedule import Lesson
Lesson.homework = relationship("Homework", back_populates="lesson", cascade="all, delete-orphan", uselist=False)