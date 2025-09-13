# notifier.py

import asyncio
import json
import logging
from typing import Dict

import redis.asyncio as redis
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.crud.crud_user import get_users_by_group_id, get_all_active_users
from app.schemas.notifications import ScheduleChange

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Notifier")

# Константы для подключения к Redis
# В идеале, REDIS_URL тоже должен быть в settings
REDIS_URL = "redis://localhost:6379/0"
SCHEDULE_CHANGES_QUEUE = "schedule_changes_queue"
BROADCAST_QUEUE = "broadcast_queue"

# --- Функции-помощники ---

def format_change_message(change: ScheduleChange) -> str:
    """Форматирует красивое и информативное сообщение для пользователя."""
    if change.change_type == "NEW":
        l = change.lesson_after
        return f"✅ **Новое занятие**\n\n**Дата:** {l.date}\n**Пара:** {l.time_slot}\n**Предмет:** {l.subject_name}"
    
    if change.change_type == "CANCELLED":
        l = change.lesson_before
        return f"❌ **Отмена занятия**\n\n**Дата:** {l.date}\n**Пара:** {l.time_slot}\n**Предмет:** {l.subject_name}"
        
    if change.change_type == "UPDATED":
        b = change.lesson_before
        a = change.lesson_after
        # Собираем строку с изменениями, показывая только то, что изменилось
        details = []
        if b.subject_name != a.subject_name:
            details.append(f"Предмет: ~{b.subject_name}~ -> **{a.subject_name}**")
        if b.date != a.date:
            details.append(f"Дата: ~{b.date}~ -> **{a.date}**")
        if b.time_slot != a.time_slot:
            details.append(f"Пара: ~{b.time_slot}~ -> **{a.time_slot}**")
        
        details_str = "\n".join(details)
        if not details_str: # Если изменилось что-то неочевидное (аудитория, преподаватель), но в LessonInfo этого нет
            details_str = f"Обновлена информация о занятии '{a.subject_name}'"

        return f"✏️ **Изменение в расписании**\n\n{details_str}"
        
    return "В вашем расписании произошли изменения. Пожалуйста, проверьте."

# --- Обработчики задач из очереди ---

async def handle_schedule_change(bot: Bot, change: ScheduleChange):
    """Обрабатывает задачу на уведомление об изменении в расписании."""
    message = format_change_message(change)
    
    async with AsyncSessionLocal() as session:
        users_to_notify = await get_users_by_group_id(session, group_id=change.group_id)

    if not users_to_notify:
        logger.info(f"No users found for group {change.group_id} to notify.")
        return

    logger.info(f"Notifying {len(users_to_notify)} users in group {change.group_id} about a schedule change.")
    for user in users_to_notify:
        if user.settings and user.settings.get("notifications_enabled", False):
            try:
                await bot.send_message(user.telegram_id, message, parse_mode="Markdown")
                logger.info(f"Sent schedule update to user {user.telegram_id}")
                await asyncio.sleep(0.1) # Небольшая задержка
            except TelegramAPIError as e:
                logger.error(f"Failed to send message to {user.telegram_id}: {e}")
                # TODO: Здесь можно добавить логику для пометки "мертвых" пользователей,
                # например, если бот заблокирован.

async def handle_broadcast(bot: Bot, task: Dict):
    """Обрабатывает задачу на широковещательную рассылку."""
    message = task.get("message")
    if not message:
        logger.warning("Broadcast task received without a message. Skipping.")
        return

    logger.info(f"Starting broadcast with message: '{message[:50]}...'")
    async with AsyncSessionLocal() as session:
        all_users = await get_all_active_users(session)

    if not all_users:
        logger.info("No active users found for broadcast.")
        return

    success_count = 0
    fail_count = 0
    for user in all_users:
        try:
            await bot.send_message(user.telegram_id, message)
            success_count += 1
            await asyncio.sleep(0.1) # Задержка 100мс между сообщениями для избежания лимитов
        except TelegramAPIError as e:
            fail_count += 1
            logger.warning(f"Failed to send broadcast to {user.telegram_id}: {e}")
    
    logger.info(f"Broadcast finished. Successfully sent: {success_count}, Failed: {fail_count}")

# --- Основной цикл обработки очередей ---

async def process_queues(bot: Bot):
    """Бесконечный цикл обработки нескольких очередей Redis."""
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info(f"Notifier started. Listening to queues: [{SCHEDULE_CHANGES_QUEUE}, {BROADCAST_QUEUE}]")
    
    while True:
        try:
            # blpop ждет, пока в ЛЮБОЙ из очередей не появится элемент.
            # Возвращает кортеж (имя_очереди, элемент).
            # timeout=0 означает вечное ожидание.
            result = await redis_client.blpop([SCHEDULE_CHANGES_QUEUE, BROADCAST_QUEUE], timeout=0)
            if not result:
                continue

            queue_name, task_json = result
            task_data = json.loads(task_json)

            logger.info(f"New task received from queue '{queue_name}'")

            if queue_name == SCHEDULE_CHANGES_QUEUE:
                change = ScheduleChange.model_validate(task_data)
                await handle_schedule_change(bot, change)
            elif queue_name == BROADCAST_QUEUE:
                await handle_broadcast(bot, task_data)

        except (redis.RedisError, ConnectionRefusedError) as e:
            logger.error(f"Redis connection error: {e}. Reconnecting in 10 seconds...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Critical error in processing queues: {e}", exc_info=True)
            await asyncio.sleep(5) # Короткая пауза перед повторной попыткой

async def main():
    """Главная асинхронная функция для запуска бота и обработчика очереди."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is not set in .env file! Notifier cannot start.")
        return

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await process_queues(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Notifier stopped by user.")