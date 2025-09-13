# app/bot/notifier.py

import asyncio
import json
import logging
from typing import Dict, List
from collections import defaultdict
from datetime import date, timedelta, datetime

import redis.asyncio as redis
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from app.bot.handlers.personal_commands import filter_lessons_by_user_preferences

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.crud.crud_user import get_users_by_group_id, get_all_active_users
from app.schemas.notifications import ScheduleChange
from app.core.queue import SCHEDULE_CHANGES_QUEUE, BROADCAST_QUEUE, CHAT_MESSAGES_QUEUE, REMINDERS_QUEUE

# Настраиваем логгер
logger = logging.getLogger("Notifier")

# --- Функции-помощники для форматирования сообщений ---

def format_grouped_changes(changes: List[ScheduleChange]) -> str:
    """Форматирует сгруппированный список изменений в одно красивое сообщение."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    parts = {"today": [], "tomorrow": [], "future": []}
    
    for change in sorted(changes, key=lambda c: datetime.strptime((c.lesson_after or c.lesson_before).date, "%d.%m.%Y")):
        lesson_info = change.lesson_after or change.lesson_before
        try:
            lesson_date = datetime.strptime(lesson_info.date, "%d.%m.%Y").date()
        except (ValueError, TypeError):
            continue

        change_line = ""
        l_info = lesson_info
        if change.change_type == "NEW":
            change_line = f"✅ Новая пара в {l_info.time_slot}: {l_info.subject_name}"
        elif change.change_type == "CANCELLED":
            change_line = f"❌ Отмена пары в {l_info.time_slot}: {l_info.subject_name}"
        elif change.change_type == "UPDATED":
            b, a = change.lesson_before, change.lesson_after
            change_line = f"✏️ Изменена пара в {b.time_slot}: {b.subject_name} -> {a.subject_name}"

        if lesson_date == today:
            parts["today"].append(change_line)
        elif lesson_date == tomorrow:
            parts["tomorrow"].append(change_line)
        else:
            parts["future"].append(f"*{l_info.date}*: {change_line}")

    message_text = "🔔 **Обновление в расписании!**\n\n"
    if parts["today"]:
        message_text += "🚨 **На сегодня:**\n" + "\n".join(parts["today"]) + "\n\n"
    if parts["tomorrow"]:
        message_text += "❗️ **На завтра:**\n" + "\n".join(parts["tomorrow"]) + "\n\n"
    if parts["future"]:
        # Убираем дубликаты, если несколько изменений в один день
        unique_future = sorted(list(set(parts["future"])))
        message_text += "🗓️ **На будущее:**\n" + "\n".join(unique_future) + "\n\n"
        
    return message_text

# --- Обработчики задач из очереди ---

async def handle_schedule_changes(bot: Bot, all_changes: List[ScheduleChange]):
    """Обрабатывает пачку изменений, группирует их по группам и рассылает."""
    changes_by_group = defaultdict(list)
    for change in all_changes:
        changes_by_group[change.group_id].append(change)
        
    for group_id, group_changes in changes_by_group.items():
        message = format_grouped_changes(group_changes)
        
        async with AsyncSessionLocal() as session:
            users_to_notify = await get_users_by_group_id(session, group_id=group_id)
        if not users_to_notify: continue

        logger.info(f"Notifying {len(users_to_notify)} users in group {group_id} about {len(group_changes)} changes.")
        for user in users_to_notify:
            if user.settings and user.settings.get("notifications_enabled", False):
                try:
                    await bot.send_message(user.telegram_id, message, parse_mode=ParseMode.MARKDOWN)
                    await asyncio.sleep(0.1)
                except TelegramAPIError as e:
                    logger.error(f"Failed to send schedule update to user {user.telegram_id}: {e}")

async def handle_broadcast(bot: Bot, task: Dict):
    """Обрабатывает задачу на широковещательную рассылку и отправляет отчет."""
    message, admin_id = task.get("message"), task.get("admin_id")
    if not message:
        if admin_id: await bot.send_message(admin_id, "❌ Ошибка рассылки: не найден текст сообщения.")
        return

    logger.info(f"Starting broadcast from admin {admin_id}...")
    async with AsyncSessionLocal() as session:
        all_users = await get_all_active_users(session)
    if not all_users:
        if admin_id: await bot.send_message(admin_id, "⚠️ Рассылка не выполнена: нет активных пользователей.")
        return

    success, fail = 0, 0
    for user in all_users:
        try:
            await bot.send_message(user.telegram_id, message)
            success += 1; await asyncio.sleep(0.1)
        except TelegramAPIError as e:
            fail += 1; logger.warning(f"Failed to send broadcast to {user.telegram_id}: {e}")
    
    logger.info(f"Broadcast finished. Sent: {success}, Failed: {fail}")
    if admin_id:
        report = (f"📊 **Отчет о рассылке**\n\n"
                  f"Текст: *«{message[:1000].replace('*', '').replace('_', '')}»*\n\n"
                  f"✅ Успешно: {success}\n❌ Ошибок: {fail}")
        await bot.send_message(admin_id, report, parse_mode=ParseMode.MARKDOWN)

async def handle_chat_message(bot: Bot, task: Dict):
    """Обрабатывает задачу на отправку сообщения в групповой чат и отправляет отчет."""
    message, chat_id, admin_id = task.get("message"), task.get("chat_id"), task.get("admin_id")
    if not message or not chat_id:
        if admin_id: await bot.send_message(admin_id, f"❌ Ошибка отправки в чат {chat_id}: не найден текст или ID чата.")
        return

    logger.info(f"Sending message from admin {admin_id} to chat {chat_id}")
    try:
        await bot.send_message(chat_id=chat_id, text=message)
        if admin_id: await bot.send_message(admin_id, f"✅ Сообщение в чат `{chat_id}` успешно отправлено.", parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send message to chat {chat_id}: {e}")
        if admin_id: await bot.send_message(admin_id, f"❌ Не удалось отправить сообщение в чат `{chat_id}`.\nПричина: `{e}`", parse_mode="Markdown")

# --- Основной цикл обработки очередей ---
async def handle_lesson_reminder(bot: Bot, task: Dict):
    """Обрабатывает задачу на напоминание о занятии."""
    group_id = task.get("group_id")
    lesson_info = task.get("lesson")
    interval = task.get("interval")
    if not all([group_id, lesson_info, interval]):
        logger.warning(f"Reminder task received with missing data: {task}")
        return

    async with AsyncSessionLocal() as session:
        users = await get_users_by_group_id(session, group_id=group_id)
        
    for user in users:
        settings = user.settings or {}
        if settings.get("reminders_enabled") and settings.get("reminder_time") == interval:
            # Применяем персональные фильтры, чтобы не напоминать о ненужных занятиях
            lesson_obj = type('Lesson', (), lesson_info)() # Создаем "утиный" объект Lesson для фильтра
            filtered = filter_lessons_by_user_preferences([lesson_obj], user)
            
            if not filtered:
                logger.info(f"Skipping reminder for user {user.telegram_id} due to personal filters.")
                continue

            message = (f"🔔 **Напоминание**\n\n"
                       f"Через *{interval} минут* ({lesson_info['start_time']}) начинается занятие:\n\n"
                       f"_{lesson_info['subject_name']}_\n"
                       f"*{lesson_info['time_slot']} пара* в ауд. *{lesson_info['auditory_name']}*")
            try:
                await bot.send_message(user.telegram_id, message, parse_mode="Markdown")
            except TelegramAPIError as e:
                logger.warning(f"Failed to send reminder to user {user.telegram_id}: {e}")

# --- Основной цикл обработки очередей ---

async def process_queues(bot: Bot):
    """Бесконечный цикл, который слушает все очереди Redis и распределяет задачи."""
    redis_client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    queues_to_listen = [SCHEDULE_CHANGES_QUEUE, BROADCAST_QUEUE, CHAT_MESSAGES_QUEUE, REMINDERS_QUEUE]
    logger.info(f"Notifier task started. Listening to queues: {queues_to_listen}")
    
    while True:
        try:
            # Сначала пытаемся выгрести пачку изменений расписания
            tasks_json = await redis_client.lpop(SCHEDULE_CHANGES_QUEUE, 100)
            if tasks_json:
                all_changes = [ScheduleChange.model_validate_json(task) for task in tasks_json]
                if all_changes:
                    asyncio.create_task(handle_schedule_changes(bot, all_changes))

            # Затем с таймаутом слушаем остальные очереди "по-одному"
            result = await redis_client.blpop([BROADCAST_QUEUE, CHAT_MESSAGES_QUEUE, REMINDERS_QUEUE], timeout=1)
            if not result: continue

            queue_name, task_json = result
            task_data = json.loads(task_json)

            logger.info(f"New task received from queue '{queue_name}'")
            if queue_name == BROADCAST_QUEUE:
                asyncio.create_task(handle_broadcast(bot, task_data))
            elif queue_name == CHAT_MESSAGES_QUEUE:
                asyncio.create_task(handle_chat_message(bot, task_data))
            elif queue_name == REMINDERS_QUEUE:
                asyncio.create_task(handle_lesson_reminder(bot, task_data))

        except asyncio.CancelledError:
            logger.info("Notifier task is shutting down.")
            break
        except (redis.RedisError, ConnectionRefusedError) as e:
            logger.error(f"Redis connection error: {e}. Reconnecting in 10 seconds...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Critical error in processing queues: {e}", exc_info=True)
            await asyncio.sleep(5)