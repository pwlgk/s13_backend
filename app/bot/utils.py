# app/bot/utils.py

from typing import List
from aiogram import types
from datetime import date, timedelta
from app.core.config import settings
MAX_MESSAGE_LENGTH = 4096

def split_long_message(text: str) -> List[str]:
    """
    Разбивает длинный текст на части, не превышающие лимит Telegram.
    Пытается разбивать по двойному переносу строки, чтобы не рвать абзацы.
    """
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    parts = []
    current_part = ""
    blocks = text.split("-" * 20)

    for block in blocks:
        block_to_add = block.strip()
        if not block_to_add:
            continue
            
        if parts:
            block_to_add = ("-"*20) + "\n\n" + block_to_add
        
        if len(current_part) + len(block_to_add) <= MAX_MESSAGE_LENGTH:
            current_part += block_to_add
        else:
            parts.append(current_part.strip())
            current_part = block_to_add

    if current_part.strip():
        parts.append(current_part.strip())
        
    return parts


def get_mini_app_keyboard(button_text: str = "Открыть в Mini App 📲") -> types.InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой для открытия Mini App."""


    web_app_info = types.WebAppInfo(url=settings.MINI_APP_URL)
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text=button_text, web_app=web_app_info)]
        ]
    )
    return keyboard


def format_date_with_russian_weekday(target_date: date) -> str:
    """Форматирует дату и переводит день недели на русский."""
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    day_name = weekdays[target_date.weekday()]
    return target_date.strftime(f'%d.%m.%Y, {day_name}')

def get_week_dates(target_date: date) -> tuple[date, date]:
    """Возвращает понедельник и воскресенье для недели, в которую входит target_date."""
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week