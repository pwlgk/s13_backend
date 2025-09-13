# app/schemas/group_chat.py
from pydantic import BaseModel, ConfigDict
from typing import Optional
from .schedule import GroupBase

class GroupChatBase(BaseModel):
    chat_id: int
    title: str
    is_active: bool
    linked_group: Optional[GroupBase] = None
    
    model_config = ConfigDict(from_attributes=True)