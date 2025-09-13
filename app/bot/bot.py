# app/bot/bot.py

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import BotCommandScopeDefault, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from aiogram.exceptions import TelegramAPIError
import logging
from app.core.config import settings
from .commands import get_private_chat_commands, get_group_chat_commands
from .handlers import setup_handlers

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Notifier")

# --- Создание основных объектов ---

# Создаем объект с настройками по умолчанию (способ для aiogram 3.7+)
defaults = DefaultBotProperties(parse_mode=ParseMode.HTML)

# Передаем объект с настройками по умолчанию в конструктор Bot
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=defaults)
dp = Dispatcher()

# Подключаем все наши хендлеры (из app/bot/handlers)
setup_handlers(dp)


# --- Логика, выполняемая при старте/остановке FastAPI ---

async def setup_bot_commands(bot: Bot):
    """Устанавливает меню команд для бота."""
    try:
        await bot.set_my_commands(
            commands=get_private_chat_commands(),
            scope=BotCommandScopeAllPrivateChats()
        )
        await bot.set_my_commands(
            commands=get_group_chat_commands(),
            scope=BotCommandScopeAllGroupChats()
        )
        logger.info("Bot commands have been set successfully.")
    except TelegramAPIError as e:
        logger.error(f"Error setting bot commands: {e}")


async def on_shutdown(bot: Bot):
    """Вызывается при остановке приложения."""
    # Этот метод остается для симметрии, в режиме polling делать нечего.
    # Если вернетесь к вебхукам, здесь будет bot.delete_webhook().
    logger.info("Bot shutdown actions completed.")