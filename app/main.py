# app/main.py

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Импортируем роутер, который собирает все API-эндпоинты
from app.api.v1.api import api_router

# Импортируем компоненты системы, необходимые для API
from app.core.omsu_api import api_client
from app.core.config import settings

# Импортируем компоненты бота, необходимые для API
from app.bot.bot import bot, dp, setup_bot_commands
from aiogram import types

# Настраиваем логирование для API процесса
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("APIProcess")

# --- Глобальная переменная для управления задачей поллинга ---
polling_task: asyncio.Task | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управляет жизненным циклом только API и бота.
    """
    global polling_task
    
    # --- ДЕЙСТВИЯ ПРИ СТАРТЕ ---
    logger.info("API process starting up...")

    # Удаляем старый вебхук (на случай, если он был) и устанавливаем команды
    await bot.delete_webhook(drop_pending_updates=True)
    await setup_bot_commands(bot)
    
    # Запускаем Long Polling для бота в фоновой задаче
    polling_task = asyncio.create_task(dp.start_polling(bot), name="PollingTask")
    logger.info("Bot polling has been started as a background task.")

    yield # Приложение готово к работе и принимает запросы

    # --- ДЕЙСТВИЯ ПРИ ОСТАНОВКЕ ---
    logger.info("API process shutting down...")
    
    if polling_task:
        logger.info("Stopping polling...")
        # Сначала вежливо просим aiogram остановиться
        await dp.stop_polling()
        # Затем отменяем asyncio задачу
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            logger.info("Polling task has been successfully cancelled.")
    
    # Закрываем сессии, используемые в API
    await bot.session.close()
    await api_client.close()
    logger.info("Bot and API client sessions have been closed.")


# --- Создание FastAPI приложения ---
app = FastAPI(
    title="OmGU Schedule Service API",
    version="1.0.0",
    description="A reliable backend service for OmGU schedule with Telegram Bot integration.",
    lifespan=lifespan
)

# --- Настройка CORS ---
origins = [
    "http://localhost",
    "http://localhost:3000", # для React/Vue
    "http://localhost:8080",
    "http://localhost:5173", # для Vite
    "https://web.telegram.org",
    settings.MINI_APP_URL
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Подключение API-роутеров ---
app.include_router(api_router, prefix="/api/v1")

# --- Корневой эндпоинт для проверки работы ---
@app.get("/", include_in_schema=False)
def read_root():
    return {"status": "ok", "message": "API server is running. Bot is in polling mode."}