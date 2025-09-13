# app/api/v1/api.py
from fastapi import APIRouter
from .endpoints import auth, profile, schedule, dictionaries, admin, lessons, homework # <-- Добавляем dictionaries

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(profile.router, prefix="/profile", tags=["Profile"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["Schedule"])
api_router.include_router(dictionaries.router, prefix="/dicts", tags=["Dictionaries"]) # <-- Добавляем эту строку
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(lessons.router, prefix="/lessons", tags=["Lessons"]) # <-- Добавляем эту строку
api_router.include_router(homework.router, prefix="/homework", tags=["Homework"])

