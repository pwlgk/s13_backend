# app/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator # <--- 1. ИМПОРТИРУЕМ AsyncGenerator

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

AsyncSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine, 
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]: # <--- 2. ИСПРАВЛЯЕМ АННОТАЦИЮ
    """
    Dependency function that yields a new SQLAlchemy AsyncSession.
    """
    async with AsyncSessionLocal() as session:
        yield session