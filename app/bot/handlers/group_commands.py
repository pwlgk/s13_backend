# app/bot/handlers/group_commands.py

from datetime import date, timedelta
from collections import defaultdict

from aiogram import Router, F, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем утилиты из общего файла
from app.bot.utils import (
    get_week_dates, 
    format_date_with_russian_weekday, 
    split_long_message
)

from app.db.session import AsyncSessionLocal
from app.crud import crud_chat, crud_schedule
from app.models.schedule import Lesson

router = Router()

# --- Вспомогательные функции ---

def format_day_schedule_for_chat(lessons: list[Lesson]) -> str:
    """
    Форматирует список занятий за один день в красивое сообщение для групповых чатов.
    Не включает ДЗ для краткости и приватности.
    """
    if not lessons:
        return "На этот день занятий нет.\n"
    
    response_parts = []
    # Сортируем на случай, если из БД пришло не по порядку
    sorted_lessons = sorted(lessons, key=lambda l: l.time_slot)

    for lesson in sorted_lessons:
        # Форматируем информацию о подгруппе
        subgroup_info = ""
        if lesson.subgroup_name:
            subgroup_num = lesson.subgroup_name.split('/')[-1]
            subgroup_info = f" ({subgroup_num} подгруппа)"
        
        # Собираем блок для одного занятия
        part = (
            f"*{lesson.time_slot} пара* ({lesson.lesson_type}){subgroup_info}\n"
            f"_{lesson.subject_name}_\n"
            f"👤 {lesson.tutor.name}\n"
            f"📍 ауд. {lesson.auditory.name} ({lesson.auditory.building}к)"
        )
        response_parts.append(part)
        
    return "\n\n".join(response_parts)


async def get_schedule_and_reply(message: types.Message, start_date: date, end_date: date):
    """Общая функция для получения расписания за период и отправки ответа в группу."""
    async with AsyncSessionLocal() as session:
        chat = await crud_chat.get_chat_by_id(session, message.chat.id)
        
        if not chat or not chat.linked_group_id:
            return await message.reply(
                "Этот чат не привязан к учебной группе. Администратор может сделать это командой `/setgroup [название]`."
            )

        lessons_db = await crud_schedule.get_schedule_for_group_for_period(
            session, group_id=chat.linked_group_id, start_date=start_date, end_date=end_date
        )
        
        if not lessons_db:
            if start_date == end_date:
                await message.reply(f"На {start_date.strftime('%d.%m.%Y')} занятий нет.")
            else:
                await message.reply(f"На период с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')} занятий нет.")
            return

        schedule_by_day = defaultdict(list)
        for lesson in lessons_db:
            schedule_by_day[lesson.date].append(lesson)
            
        full_response = ""
        for day in sorted(schedule_by_day.keys()):
            day_str = format_date_with_russian_weekday(day)
            day_header = f"🗓️ *Расписание на {day_str}*\n\n"
            day_content = format_day_schedule_for_chat(schedule_by_day[day])
            full_response += day_header + day_content + "\n" + ("-"*20) + "\n\n"
        
        # Разбиваем сообщение, если нужно, и отправляем БЕЗ КЛАВИАТУРЫ
        message_parts = split_long_message(full_response)
        for part in message_parts:
            await message.reply(part, parse_mode="Markdown", disable_web_page_preview=True)

# --- Основные хендлеры с ЯВНЫМ фильтром чата ---

@router.message(F.text.startswith("/groupinfo"), F.chat.type.in_({"group", "supergroup"}))
async def get_group_info(message: types.Message):
    """Показывает, к какой группе привязан чат."""
    async with AsyncSessionLocal() as session:
        chat = await crud_chat.get_chat_by_id(session, message.chat.id)
        if chat and chat.linked_group and chat.linked_group.name:
            await message.reply(f"Этот чат привязан к учебной группе: **{chat.linked_group.name}**", parse_mode="Markdown")
        else:
            await message.reply("Этот чат еще не привязан к учебной группе. Администратор может сделать это командой `/setgroup [название]`.")


@router.message(F.text.startswith("/today"), F.chat.type.in_({"group", "supergroup"}))
async def get_group_schedule_today(message: types.Message):
    """Отдает расписание привязанной группы на сегодня."""
    today = date.today()
    await get_schedule_and_reply(message, start_date=today, end_date=today)


@router.message(F.text.startswith("/tomorrow"), F.chat.type.in_({"group", "supergroup"}))
async def get_group_schedule_tomorrow(message: types.Message):
    """Отдает расписание привязанной группы на завтра."""
    tomorrow = date.today() + timedelta(days=1)
    await get_schedule_and_reply(message, start_date=tomorrow, end_date=tomorrow)


@router.message(F.text.startswith("/week"), F.chat.type.in_({"group", "supergroup"}))
async def get_group_schedule_week(message: types.Message):
    """Отдает расписание привязанной группы на текущую неделю."""
    today = date.today()
    start_of_week, end_of_week = get_week_dates(today)
    await get_schedule_and_reply(message, start_date=start_of_week, end_date=end_of_week)


@router.message(F.text.startswith("/nextweek"), F.chat.type.in_({"group", "supergroup"}))
async def get_group_schedule_next_week(message: types.Message):
    """Отдает расписание привязанной группы на следующую неделю."""
    next_monday = date.today() + timedelta(days=(7 - date.today().weekday()))
    start_of_week, end_of_week = get_week_dates(next_monday)
    await get_schedule_and_reply(message, start_date=start_of_week, end_date=end_of_week)