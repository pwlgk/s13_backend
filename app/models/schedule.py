# app/models/schedule.py
from sqlalchemy import Column, Integer, String, BigInteger, Date, Text, ForeignKey, DateTime
from sqlalchemy.sql import func # Импортируем func
from sqlalchemy.orm import relationship
from app.db.base import Base


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    name = Column(String, unique=True, index=True, nullable=False)
    real_group_id = Column(Integer, nullable=True)

class Tutor(Base):
    __tablename__ = "tutors"
    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    name = Column(String, index=True, nullable=False)

class Auditory(Base):
    __tablename__ = "auditories"
    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    name = Column(String, nullable=False)
    building = Column(String, nullable=True)


class Lesson(Base):
    __tablename__ = "lessons"
    source_id = Column(BigInteger, primary_key=True, index=True, autoincrement=False)
    date = Column(Date, nullable=False, index=True) # Добавим индекс для дат
    time_slot = Column(Integer, nullable=False)
    subgroup_name = Column(String, nullable=True)
    subject_name = Column(String, nullable=False)
    lesson_type = Column(String(10), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    
    # Новое поле, чтобы отслеживать актуальность записи
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False, index=True) # Добавим индекс
    tutor_id = Column(Integer, ForeignKey("tutors.id"), nullable=False)
    auditory_id = Column(Integer, ForeignKey("auditories.id"), nullable=False)
    lesson_id = Column(Integer, index=True)
    group = relationship("Group")
    tutor = relationship("Tutor")
    auditory = relationship("Auditory")