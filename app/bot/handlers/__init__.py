# app/bot/handlers/__init__.py
from aiogram import Dispatcher
from . import personal_commands, group_commands, chat_management

def setup_handlers(dp: Dispatcher):
    """Подключает все хендлеры к диспетчеру."""
    # Сначала регистрируем более специфичные роутеры
    dp.include_router(chat_management.router)
    dp.include_router(group_commands.router)
    
    # Роутер с "catch-all" хендлером (@router.message()) должен идти последним
    dp.include_router(personal_commands.router)