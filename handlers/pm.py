from aiogram import Router, Bot, F
from aiogram.enums import ChatType, ContentType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from localization import get_localization, DEFAULT_LANGUAGE
from handlers.gpt import process_gpt

router = Router() 

@router.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    start_text = _("start_message")

    await message.answer(start_text, parse_mode="Markdown")

@router.message(F.chat.type == ChatType.PRIVATE, lambda message: message.text and not message.text.startswith("/"), F.content_type == ContentType.TEXT)
async def pm(message: Message, bot: Bot):
    command = CommandObject(command=None, args=message.text)
    await process_gpt(message, command, message.from_user.id)

@router.message(
    F.chat.type == ChatType.PRIVATE,
    F.content_type.not_in({ContentType.TEXT})
)
async def handle_other_content(message: Message, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    await message.answer(_("pm_default"))