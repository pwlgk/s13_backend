# worker_main.py

import asyncio
import json
import logging
import signal
from typing import Coroutine

import redis.asyncio as redis

# Импортируем компоненты нашей системы
from app.worker import scheduler, run_hot_schedule_sync, run_dict_sync
from app.bot.bot import bot
from app.bot.notifier import process_queues
from app.core.queue import CONTROL_QUEUE

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WorkerProcess")

# --- Глобальные переменные для управления graceful shutdown ---
shutdown_event = asyncio.Event()

def _handle_shutdown_signal(*args):
    """Обработчик сигналов SIGINT/SIGTERM для корректного завершения."""
    logger.info("Shutdown signal received. Stopping tasks...")
    shutdown_event.set()

async def listen_control_queue():
    """Слушает очередь управляющих команд из Redis и запускает соответствующие задачи."""
    redis_client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    logger.info(f"Listening for control commands on '{CONTROL_QUEUE}'...")
    
    while not shutdown_event.is_set():
        try:
            # Ждем команду с таймаутом, чтобы цикл мог проверить shutdown_event
            result = await redis_client.blpop([CONTROL_QUEUE], timeout=1)
            if not result:
                continue

            _, command_json = result
            command_data = json.loads(command_json)
            command = command_data.get("command")
            logger.info(f"Received control command: '{command}'")

            if command == "run_hot_schedule_sync":
                scheduler.add_job(run_hot_schedule_sync, id='manual_hot_sync', replace_existing=True)
            elif command == "run_dict_sync":
                scheduler.add_job(run_dict_sync, id='manual_dict_sync', replace_existing=True)
            else:
                logger.warning(f"Unknown control command received: {command}")

        except asyncio.CancelledError:
            logger.info("Control queue listener task cancelled.")
            break
        except (redis.RedisError, ConnectionRefusedError) as e:
            logger.error(f"Redis connection error in control listener: {e}. Reconnecting in 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error in control queue listener: {e}", exc_info=True)
            await asyncio.sleep(1)
    
    logger.info("Control queue listener stopped.")


async def main():
    """Главная асинхронная функция для запуска всех фоновых задач воркера."""
    logger.info("Worker process starting...")
    
    # Запускаем планировщик apscheduler
    scheduler.start()
    logger.info("APScheduler has been started.")
    
    # Создаем задачи для notifier и слушателя команд
    notifier_task = asyncio.create_task(process_queues(bot), name="NotifierTask")
    control_task = asyncio.create_task(listen_control_queue(), name="ControlTask")
    
    # Ожидаем сигнала на завершение
    await shutdown_event.wait()
    
    # Корректно завершаем все задачи
    logger.info("Shutting down worker process...")
    
    # Останавливаем планировщик, не дожидаясь завершения текущих задач
    scheduler.shutdown(wait=False)
    
    # Отменяем асинхронные задачи
    notifier_task.cancel()
    control_task.cancel()
    
    # Ожидаем их завершения
    await asyncio.gather(notifier_task, control_task, return_exceptions=True)
    
    # Закрываем сессию бота
    await bot.session.close()
    
    logger.info("Worker process shut down gracefully.")


if __name__ == "__main__":
    # Устанавливаем обработчики сигналов для корректного завершения
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, _handle_shutdown_signal)
    loop.add_signal_handler(signal.SIGTERM, _handle_shutdown_signal)

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Worker process stopped by user (KeyboardInterrupt).")
    finally:
        loop.close()