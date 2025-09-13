# app/models/user.py
from sqlalchemy import Boolean, Column, BigInteger, String, Integer, JSON
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True, autoincrement=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True, unique=True, index=True)
    
    group_id = Column(Integer, nullable=True)
    subgroup_number = Column(Integer, nullable=True)
    
    settings = Column(JSON, nullable=False, server_default=
            '{"notifications_enabled": true, "reminders_enabled": true, "reminder_time": 15, "preferred_tutors": {}}'
        )
    is_blocked = Column(Boolean, server_default="false", nullable=False)
