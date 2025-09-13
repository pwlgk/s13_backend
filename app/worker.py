# app/worker.py

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import AsyncSessionLocal
from app.services.sync_service import sync_service
from app.crud.crud_schedule import get_all_groups_ids, get_active_user_group_ids
from app.crud.crud_schedule import get_lessons_starting_soon
from app.core.queue import push_reminders_to_queue
# Настраиваем логгер
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Создаем асинхронный планировщик с временной зоной Омска
scheduler = AsyncIOScheduler(timezone="Asia/Omsk")


# --- Определения задач (Jobs) ---

async def run_dict_sync():
    """Асинхронная задача для синхронизации справочников."""
    logger.info("--- [JOB START] Dictionaries Sync ---")
    try:
        async with AsyncSessionLocal() as session:
            await sync_service.sync_dictionaries(session)
        logger.info("--- [JOB SUCCESS] Dictionaries Sync ---")
    except Exception as e:
        logger.error(f"--- [JOB FAILED] Dictionaries Sync: {e} ---", exc_info=True)


async def run_hot_schedule_sync():
    """Синхронизирует расписание для 'горячих' групп (с активными пользователями)."""
    logger.info("--- [JOB START] HOT Schedule Sync (for active user groups) ---")
    try:
        async with AsyncSessionLocal() as session:
            hot_group_ids = await get_active_user_group_ids(session)
            if not hot_group_ids:
                logger.info("No active user groups to sync. Skipping HOT sync.")
                return
            
            # Передаем список ID "горячих" групп в сервис синхронизации
            await sync_service.sync_schedules_for_groups(session, group_ids=hot_group_ids)
        logger.info("--- [JOB SUCCESS] HOT Schedule Sync ---")
    except Exception as e:
        logger.error(f"--- [JOB FAILED] HOT Schedule Sync: {e} ---", exc_info=True)


async def run_cold_schedule_sync():
    """Синхронизирует расписание для всех остальных ('холодных') групп."""
    logger.info("--- [JOB START] COLD Schedule Sync (for all other groups) ---")
    try:
        async with AsyncSessionLocal() as session:
            all_ids = set(await get_all_groups_ids(session))
            hot_ids = set(await get_active_user_group_ids(session))
            
            # Вычисляем разницу множеств, чтобы получить "холодные" группы
            cold_group_ids = list(all_ids - hot_ids)
            
            if not cold_group_ids:
                logger.info("No cold groups to sync. Skipping COLD sync.")
                return

            await sync_service.sync_schedules_for_groups(session, group_ids=cold_group_ids)
        logger.info("--- [JOB SUCCESS] COLD Schedule Sync ---")
    except Exception as e:
        logger.error(f"--- [JOB FAILED] COLD Schedule Sync: {e} ---", exc_info=True)


async def run_cleanup():
    """Асинхронная задача для очистки устаревших данных."""
    logger.info("--- [JOB START] Cleanup Old Lessons ---")
    try:
        async with AsyncSessionLocal() as session:
            await sync_service.cleanup_old_lessons(session)
        logger.info("--- [JOB SUCCESS] Cleanup Old Lessons ---")
    except Exception as e:
        logger.error(f"--- [JOB FAILED] Cleanup Old Lessons: {e} ---", exc_info=True)


async def run_lesson_reminders_check():
    """Проверяет, не пора ли отправлять напоминания."""
    # Мы будем проверять каждые 5 минут, но напоминать за 30, 15, 10, 5 минут
    # Это значит, что нам нужно проверить несколько временных интервалов
    reminder_intervals = [30, 15, 10, 5]
    
    async with AsyncSessionLocal() as session:
        for interval in reminder_intervals:
            lessons_to_remind = await get_lessons_starting_soon(session, interval_minutes=interval)
            if lessons_to_remind:
                # Отправляем найденные занятия в очередь Redis
                logger.info(f"Found {len(lessons_to_remind)} lessons starting in {interval} minutes. Pushing to queue.")
                await push_reminders_to_queue(lessons_to_remind)

# --- Добавление задач в планировщик ---

# 1. Синхронизация справочников (ежедневно в 3:00)
scheduler.add_job(
    run_dict_sync, 'cron', hour=3, minute=0, id='dict_sync_cron',
    name='Синхронизация справочников'
)

# 2. Оптимизированная синхронизация расписания
# Часто проверяем "горячие" группы (каждые 20 минут)
scheduler.add_job(
    run_hot_schedule_sync, 'interval', minutes=20, id='hot_schedule_sync',
    name='Синхронизация расписания (горячие группы)'
)
# Редко проверяем все остальные "холодные" группы (ежедневно в 4:30)
scheduler.add_job(
    run_cold_schedule_sync, 'cron', hour=4, minute=30, id='cold_schedule_sync',
    name='Синхронизация расписания (холодные группы)'
)

# 3. Очистка старых записей (ежедневно в 4:00)
scheduler.add_job(
    run_cleanup, 'cron', hour=4, minute=0, id='cleanup_cron',
    name='Очистка старых занятий'
)

scheduler.add_job(
    run_lesson_reminders_check, 'interval', minutes=1, id='lesson_reminders_check',
    name='Проверка напоминаний о занятиях'
)

# --- Отладочный немедленный запуск ---
# Чтобы протестировать, раскомментируйте нужную строку
# scheduler.add_job(run_hot_schedule_sync, id='initial_hot_sync')
# scheduler.add_job(run_cold_schedule_sync, id='initial_cold_sync')

logger.info("Scheduler configured for optimized production mode (hot/cold sync).")