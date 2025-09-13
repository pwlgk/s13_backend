# app/bot/commands.py
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllGroupChats

def get_private_chat_commands() -> list[BotCommand]:
    """Возвращает список команд для личных чатов."""
    return [
        BotCommand(command="start", description="🚀 Перезапустить бота"),
        BotCommand(command="myday", description="🗓️ Мое расписание на сегодня"),
        BotCommand(command="nextday", description="▶️ Мое расписание на завтра"),
        # BotCommand(command="myweek", description="📅 Мое расписание на неделю"),
        BotCommand(command="help", description="ℹ️ Помощь"),
    ]

def get_group_chat_commands() -> list[BotCommand]:
    """Возвращает список команд для групповых чатов."""
    return [
        BotCommand(command="today", description="🗓️ Расписание группы на сегодня"),
        BotCommand(command="tomorrow", description="▶️ Расписание группы на завтра"),
        BotCommand(command="week", description="📅 Расписание группы на неделю"),
        BotCommand(command="nextweek", description="⏩ Расписание группы на след. неделю"),
        BotCommand(command="groupinfo", description="ℹ️ Информация о привязанной группе"),
        BotCommand(command="setgroup", description="⚙️ (Админам) Привязать группу"),
    ]