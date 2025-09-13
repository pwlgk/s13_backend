# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Конфигурация модели Pydantic V2
    model_config = SettingsConfigDict(
        env_file='.env', 
        env_file_encoding='utf-8', 
        extra='ignore'  # Игнорируем лишние переменные в .env
    )

    # Описываем только те переменные, которые нужны приложению
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    TELEGRAM_BOT_TOKEN: str
    ADMIN_TELEGRAM_IDS: str

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

    MINI_APP_URL: str
    
    LESSON_START_TIMES: str
settings = Settings()

