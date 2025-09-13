# app/db/base.py
from sqlalchemy.orm import declarative_base

# Создаем базовый класс для всех наших моделей SQLAlchemy
# Все модели будут наследоваться от этого класса
Base = declarative_base()