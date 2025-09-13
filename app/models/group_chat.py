# app/models/group_chat.py
from sqlalchemy import Column, BigInteger, String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.base import Base

class GroupChat(Base):
    __tablename__ = "group_chats"

    chat_id = Column(BigInteger, primary_key=True, index=True, autoincrement=False)
    title = Column(String)
    is_active = Column(Boolean, default=True)

    # Связь с учебной группой из справочника
    linked_group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    
    linked_group = relationship("Group")