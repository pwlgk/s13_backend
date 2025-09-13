# seed_database.py

import asyncio
import logging

# Настраиваем пути, чтобы можно было импортировать модули из `app`
import sys
import os
sys.path.append(os.getcwd())

from app.db.session import AsyncSessionLocal
from app.services.sync_service import sync_service
from app.crud.crud_schedule import get_all_groups_ids

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DatabaseSeeder")

async def seed_data():
    """
    Основная функция для выполнения первоначального наполнения базы данных.
    """
    logger.info("--- Starting Database Seeding Process ---")
    
    # Создаем асинхронную сессию для всех операций
    async with AsyncSessionLocal() as session:
        
        # --- Шаг 1: Синхронизация справочников ---
        logger.info("Step 1: Syncing dictionaries (groups, tutors, auditories)...")
        try:
            await sync_service.sync_dictionaries(session)
            logger.info("Step 1: Dictionaries synced successfully.")
        except Exception as e:
            logger.error(f"Step 1 FAILED: Could not sync dictionaries. Error: {e}", exc_info=True)
            # Прерываем выполнение, так как без справочников нет смысла продолжать
            return

        # --- Шаг 2: Получение списка всех групп для синхронизации ---
        logger.info("Step 2: Fetching all group IDs from the database...")
        try:
            all_group_ids = await get_all_groups_ids(session)
            if not all_group_ids:
                logger.error("Step 2 FAILED: No groups found in the database after sync. Aborting.")
                return
            logger.info(f"Step 2: Found {len(all_group_ids)} groups to process.")
        except Exception as e:
            logger.error(f"Step 2 FAILED: Could not fetch group IDs. Error: {e}", exc_info=True)
            return

        # --- Шаг 3: Синхронизация расписания для ВСЕХ групп ---
        # logger.info("Step 3: Syncing schedule for all groups. This may take a while...")
        # try:
        #     # Вызываем наш основной метод синхронизации, передавая ему список всех групп
        #     await sync_service.sync_schedules_for_groups(session, group_ids=all_group_ids)
        #     logger.info("Step 3: Full schedule sync completed successfully.")
        # except Exception as e:
        #     logger.error(f"Step 3 FAILED: An error occurred during schedule sync. Error: {e}", exc_info=True)
        #     return

    logger.info("--- Database Seeding Process Finished Successfully! ---")


if __name__ == "__main__":
    # Проверяем, что .env файл существует и загружен
    # (Pydantic Settings делает это автоматически при импорте `config`)
    try:
        from app.core.config import settings
        logger.info("Configuration loaded successfully.")
    except Exception as e:
        logger.critical(f"Could not load settings from .env file. Error: {e}")
        sys.exit(1)

    # Запускаем асинхронную функцию
    asyncio.run(seed_data())