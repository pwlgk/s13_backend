# app/bot/handlers/chat_management.py
from aiogram import Router, F, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.crud import crud_chat

router = Router()

@router.my_chat_member(F.chat.type.in_({"group", "supergroup"}))
async def on_bot_join_or_leave_group(event: types.ChatMemberUpdated):
    """Отслеживает добавление/удаление бота из чата."""
    new_status = event.new_chat_member.status
    
    async with AsyncSessionLocal() as session:
        if new_status in ("member", "administrator"):
            await crud_chat.upsert_chat(session, chat_id=event.chat.id, title=event.chat.title)
        elif new_status in ("left", "kicked"):
            await crud_chat.upsert_chat(session, chat_id=event.chat.id, title=event.chat.title, is_active=False)

@router.message(Command("setgroup"), F.text.startswith("/setgroup"))
async def set_group_for_chat(message: types.Message, command: Command):
    # Проверяем, что команду пишет админ чата
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.reply("Эту команду может использовать только администратор чата.")

    group_name = command.args
    if not group_name:
        return await message.reply("Укажите название группы после команды, например:\n`/setgroup МБС-501-О-01`")
    
    async with AsyncSessionLocal() as session:
        chat = await crud_chat.link_chat_to_group(session, chat_id=message.chat.id, group_name=group_name.strip())

    if chat and chat.linked_group_id:
        await message.reply(f"Отлично! Этот чат теперь привязан к учебной группе **{group_name.strip()}**.", parse_mode="Markdown")
    else:
        await message.reply(f"Не удалось найти группу с названием `{group_name.strip()}`. Проверьте название и попробуйте снова.")