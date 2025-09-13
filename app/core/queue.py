# app/core/queue.py
import redis.asyncio as redis
import json
from typing import List
from app.models.schedule import Lesson
from app.schemas.notifications import ScheduleChange
from app.core.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True) # <-- Используем

SCHEDULE_CHANGES_QUEUE = "schedule_changes_queue"
BROADCAST_QUEUE = "broadcast_queue" # <-- Новая очередь
CHAT_MESSAGES_QUEUE = "chat_messages_queue"
REMINDERS_QUEUE = "reminders_queue"
CONTROL_QUEUE = "control_queue"

async def push_changes_to_queue(changes: List[ScheduleChange]):
    """Сериализует и добавляет изменения расписания в очередь Redis."""
    async with redis_client.pipeline() as pipe:
        for change in changes:
            pipe.rpush(SCHEDULE_CHANGES_QUEUE, change.model_dump_json())
        await pipe.execute()


async def push_broadcast_to_queue(message: str, admin_id: int):
    """Добавляет задачу на широковещательную рассылку в очередь Redis."""
    task = {
        "type": "broadcast",
        "message": message,
        "admin_id": admin_id # <-- Добавляем ID админа
    }
    await redis_client.rpush(BROADCAST_QUEUE, json.dumps(task))


async def push_message_to_chat_queue(chat_id: int, message: str):
    """Добавляет задачу на отправку сообщения в конкретный чат."""
    task = {
        "type": "chat_message",
        "chat_id": chat_id,
        "message": message
    }
    await redis_client.rpush(CHAT_MESSAGES_QUEUE, json.dumps(task))

async def push_reminders_to_queue(lessons: List[Lesson]):
    """Добавляет задачи на отправку напоминаний."""
    tasks = []
    for lesson in lessons:
        task = {
            "type": "lesson_reminder",
            "lesson_id": lesson.source_id, # Отправляем ID, чтобы notifier мог получить свежие данные
            "group_id": lesson.group_id,
            "subject_name": lesson.subject_name,
            "time_slot": lesson.time_slot,
            "auditory_name": lesson.auditory.name
        }
        tasks.append(json.dumps(task))
    
    if tasks:
        await redis_client.rpush(REMINDERS_QUEUE, *tasks)



async def push_control_command(command: str):
    """Добавляет управляющую команду в очередь."""
    task = {"type": "control", "command": command}
    await redis_client.rpush(CONTROL_QUEUE, json.dumps(task))