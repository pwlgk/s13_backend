# app/bot/handlers/personal_commands.py

import asyncio
from datetime import date, timedelta
from collections import defaultdict
from app.crud import crud_homework 
from aiogram import Router, F, types
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
# Импортируем утилиты из общего файла
from app.bot.utils import (
    get_week_dates, 
    format_date_with_russian_weekday, 
    split_long_message, 
    get_mini_app_keyboard
)

from app.db.session import AsyncSessionLocal
from app.crud import crud_user, crud_schedule, crud_chat
from app.models.schedule import Lesson
from app.models.user import User

router = Router()
# Ограничиваем все хендлеры в этом роутере только личными сообщениями
router.message.filter(F.chat.type == "private")


# --- Вспомогательные функции ---

def filter_lessons_by_user_preferences(lessons: list[Lesson], user: User) -> list[Lesson]:
    """
    ФИНАЛЬНАЯ ВЕРСИЯ №2. Более простой и надежный алгоритм.
    Сначала обрабатывает элективы, затем подгруппы.
    """
    
    # --- ЭТАП 1: ФИЛЬТРАЦИЯ ПО ЭЛЕКТИВАМ ---
    preferred_tutors = user.settings.get("preferred_tutors", {})
    
    # Группируем все занятия по номеру пары
    lessons_by_slot = defaultdict(list)
    for lesson in lessons:
        lessons_by_slot[lesson.time_slot].append(lesson)

    lessons_after_electives_filter = []
    for time_slot, slot_lessons in lessons_by_slot.items():
        # Если в слоте одно занятие, оно не электив, берем его.
        if len(slot_lessons) <= 1:
            lessons_after_electives_filter.extend(slot_lessons)
            continue

        # Если в слоте несколько занятий, ищем предпочтение
        subject_name_key = slot_lessons[0].subject_name
        preferred_tutor_id = preferred_tutors.get(subject_name_key)

        if preferred_tutor_id:
            # Ищем занятие с выбранным преподавателем
            found = False
            for lesson in slot_lessons:
                if lesson.tutor_id == preferred_tutor_id:
                    lessons_after_electives_filter.append(lesson)
                    found = True
                    break
            # Если преподавателя сегодня нет, добавляем все варианты
            if not found:
                lessons_after_electives_filter.extend(slot_lessons)
        else:
            # Если выбор не сделан, добавляем все варианты
            lessons_after_electives_filter.extend(slot_lessons)

    # --- ЭТАП 2: ФИЛЬТРАЦИЯ ПО ПОДГРУППЕ ---
    # Работаем со списком, уже отфильтрованным по элективам.
    if not user.subgroup_number:
        # Если подгруппа не указана, показываем только общие занятия
        final_lessons = [l for l in lessons_after_electives_filter if not l.subgroup_name]
    else:
        # Если подгруппа указана, показываем общие + занятия для нашей подгруппы
        user_subgroup_str_part = f"/{user.subgroup_number}"
        final_lessons = [
            l for l in lessons_after_electives_filter 
            if not l.subgroup_name or user_subgroup_str_part in l.subgroup_name
        ]
        
    return sorted(final_lessons, key=lambda l: l.time_slot)


async def format_schedule_for_user(session: AsyncSession, lessons: list[Lesson]) -> str:
    """
    Форматирует отфильтрованный список занятий в красивое сообщение для личных сообщений.
    Включает информацию о домашнем задании.
    """
    if not lessons:
        return "На этот день занятий нет. Время отдыхать! 🎉\n"
    
    response_parts = []
    # Сортируем по номеру пары, чтобы расписание всегда было в правильном порядке
    sorted_lessons = sorted(lessons, key=lambda l: l.time_slot)

    for lesson in sorted_lessons:
        # Получаем домашнее задание для каждого занятия
        homework = await crud_homework.get_homework_by_lesson_id(session, lesson_id=lesson.source_id)
        homework_str = ""
        if homework:
            # Ограничиваем длину ДЗ для краткости в общем списке
            content_preview = homework.content[:100] + "..." if len(homework.content) > 100 else homework.content
            homework_str = f"\n*ДЗ:* {content_preview}"

        # Форматируем информацию о подгруппе
        subgroup_info = ""
        if lesson.subgroup_name:
            # Извлекаем только номер подгруппы для краткости
            subgroup_num = lesson.subgroup_name.split('/')[-1]
            subgroup_info = f" ({subgroup_num} подгруппа)"
        
        # Собираем блок для одного занятия
        part = (
            f"*{lesson.time_slot} пара* ({lesson.lesson_type}){subgroup_info}\n"
            f"_{lesson.subject_name}_\n"
            f"👤 {lesson.tutor.name}\n"
            f"📍 ауд. {lesson.auditory.name} ({lesson.auditory.building}к)"
            f"{homework_str}"
        )
        response_parts.append(part)
        
    return "\n\n".join(response_parts)


async def get_schedule_and_reply_for_day(message: types.Message, target_date: date):
    """Общая функция для получения, фильтрации и отправки расписания на ОДИН день."""
    async with AsyncSessionLocal() as session:
        user = await crud_user.get_user_by_telegram_id(session, telegram_id=message.from_user.id)
        if not user or not user.group_id:
            return await message.answer("Ваш профиль не настроен. Пожалуйста, укажите вашу группу в Mini App.", reply_markup=get_mini_app_keyboard())

        lessons = await crud_schedule.get_schedule_for_group_by_date(session, group_id=user.group_id, target_date=target_date)
        filtered_lessons = filter_lessons_by_user_preferences(lessons, user)
        response_text = await format_schedule_for_user(filtered_lessons)
        
        await message.answer(
            f"Расписание на *{format_date_with_russian_weekday(target_date)}*:\n\n{response_text}",
            parse_mode="Markdown",
            reply_markup=get_mini_app_keyboard()
        )


# --- Основные хендлеры ---

@router.message(CommandStart())
async def command_start_handler(message: types.Message):
    """Хендлер на команду /start."""
    keyboard = get_mini_app_keyboard("Открыть расписание 🚀")
    
    await message.answer(
        f"Привет, {message.from_user.full_name}! 👋\n\nЯ помогу тебе следить за расписанием ОмГУ.",
        reply_markup=keyboard
    )
    await command_help_handler(message, show_greeting=False)
    await asyncio.sleep(1)
    await suggest_group_setup(message)


@router.message(Command("help"))
async def command_help_handler(message: types.Message, show_greeting: bool = True):
    """Отправляет справочное сообщение."""
    greeting = "Я помогу тебе следить за расписанием ОмГУ. Вот что я умею:\n\n" if show_greeting else ""
    help_text = (
        f"ℹ️ **Справка по боту**\n\n{greeting}"
        "**Личные команды:**\n"
        "*/start* - Перезапустить бота и показать главное меню.\n"
        "*/myday* - Показать твое расписание на сегодня.\n"
        "*/nextday* - Показать твое расписание на завтра.\n"
        "*/myweek* - Показать твое расписание на текущую неделю.\n\n"
        "Для полноценной работы настрой свой профиль (укажи группу) через Mini App (кнопка в меню /start)."
    )
    await message.answer(help_text, parse_mode="Markdown")


@router.message(Command("myday"))
async def get_my_schedule_today(message: types.Message):
    await get_schedule_and_reply_for_day(message, target_date=date.today())

@router.message(Command("nextday"))
async def get_my_schedule_tomorrow(message: types.Message):
    await get_schedule_and_reply_for_day(message, target_date=date.today() + timedelta(days=1))


@router.message(Command("myweek"))
async def get_my_schedule_week(message: types.Message):
    """Отправляет личное расписание на текущую неделю."""
    async with AsyncSessionLocal() as session:
        user = await crud_user.get_user_by_telegram_id(session, telegram_id=message.from_user.id)
        if not user or not user.group_id:
            return await message.answer("Сначала укажите вашу группу в Mini App.", reply_markup=get_mini_app_keyboard())

        today = date.today()
        start_of_week, end_of_week = get_week_dates(today)
        lessons_db = await crud_schedule.get_schedule_for_group_for_period(
            session, group_id=user.group_id, start_date=start_of_week, end_date=end_of_week
        )
        
        # --- НАЧАЛО ИЗМЕНЕНИЙ ---
        # Применяем ВСЕ персональные фильтры (подгруппа + элективы)
        filtered_lessons = filter_lessons_by_user_preferences(lessons_db, user)
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---
        
        if not filtered_lessons:
            return await message.answer("На этой неделе занятий нет (с учетом ваших фильтров).", reply_markup=get_mini_app_keyboard())

        # Группируем УЖЕ отфильтрованные занятия
        schedule_by_day = defaultdict(list)
        for lesson in filtered_lessons:
            schedule_by_day[lesson.date].append(lesson)
        
        full_response = ""
        for day in sorted(schedule_by_day.keys()):
            day_str = format_date_with_russian_weekday(day)
            day_header = f"🗓️ *{day_str}*\n\n"
            # Передаем в форматирование уже отфильтрованные занятия для этого дня
            day_content = await format_schedule_for_user(session, schedule_by_day[day])
            full_response += day_header + day_content + "\n" + ("-"*20) + "\n\n"
        
        keyboard = get_mini_app_keyboard()
        message_parts = split_long_message(full_response)
        for i, part in enumerate(message_parts):
            if i == len(message_parts) - 1:
                await message.answer(part, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=keyboard)
            else:
                await message.answer(part, parse_mode="Markdown", disable_web_page_preview=True)


# --- "Умные" рекомендации и Callbacks ---

async def suggest_group_setup(message: types.Message):
    """Проверяет, нужно ли предложить пользователю настроить группу."""
    async with AsyncSessionLocal() as session:
        user = await crud_user.get_user_by_telegram_id(session, telegram_id=message.from_user.id)
        if not user or user.group_id:
            return

        # TODO: Реализовать более сложную логику поиска чатов, если потребуется
        # user_chats = await crud_chat.get_user_chats_with_linked_group(session, user_id=user.telegram_id)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="Настроить профиль", web_app=types.WebAppInfo(url=settings.MINI_APP_URL))
        await message.answer(
            "Похоже, у тебя еще не настроена учебная группа. "
            "Нажми кнопку ниже, чтобы выбрать ее и получать персональное расписание!",
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data.startswith("set_group_"))
async def set_user_group_callback(callback: types.CallbackQuery):
    """Обрабатывает нажатие на кнопку быстрой установки группы."""
    group_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        user = await crud_user.set_user_group(session, user_id=callback.from_user.id, group_id=group_id)
    
    if user:
        await callback.message.edit_text(f"Отлично! Твоя основная группа установлена. ✅\n"
                                         f"Теперь ты можешь использовать команды /myday, /nextday и получать уведомления.")
    else:
        await callback.message.edit_text("Что-то пошло не так. Попробуй настроить группу через Mini App.")
    await callback.answer()

@router.callback_query(F.data == "cancel_suggestion")
async def cancel_suggestion_callback(callback: types.CallbackQuery):
    """Обрабатывает отмену предложения."""
    await callback.message.delete()
    await callback.answer()

@router.message()
async def handle_unknown_messages(message: types.Message):
    """Ловит все остальные сообщения, на которые нет хендлеров."""
    await message.answer("Я не знаю такой команды. 😕\nИспользуй /start или /help, чтобы увидеть список доступных команд.")