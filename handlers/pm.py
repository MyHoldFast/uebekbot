from aiogram import Router, Bot, F
from aiogram.enums import ChatType, ContentType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from handlers.gpt import process_gpt, process_gemini
from handlers.stt import stt_command
from handlers.qwen import cmd_qwen
from localization import get_localization, DEFAULT_LANGUAGE
from utils.ThrottlingMiddleware import ThrottlingMiddleware

router = Router()

router.message.middleware(ThrottlingMiddleware(default_rate_limit=2.0))

is_not_forwarded = (
    F.forward_from == None,
    F.forward_from_chat == None,
)

@router.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    start_text = _("start_message")

    await message.answer(start_text, parse_mode="Markdown")

@router.message(
    F.chat.type == ChatType.PRIVATE,
    lambda message: message.text and not message.text.startswith("/"),
    F.content_type == ContentType.TEXT,
    *is_not_forwarded
)
async def pm(message: Message, bot: Bot):
    command = CommandObject(command=None, args=message.text)
    await cmd_qwen(message, command, bot)
    #await process_gpt(message, command, message.from_user.id)

@router.message(
    F.chat.type == ChatType.PRIVATE,
    F.content_type == ContentType.PHOTO,
    *is_not_forwarded 
)
async def handle_photo(message: Message, bot: Bot):
    command = CommandObject(command=None, args=message.caption) 
    photo = message.reply_to_message.photo[-1] if message.reply_to_message and message.reply_to_message.photo else None
    photo = photo or (message.photo[-1] if message.photo else None)
    await process_gemini(message, command, bot, photo)

@router.message(
    F.chat.type == ChatType.PRIVATE,
    F.content_type == ContentType.VOICE,
    *is_not_forwarded
)
async def handle_voice(message: Message, bot: Bot):
    await stt_command(message, bot)

@router.message(
    F.chat.type == ChatType.PRIVATE,
    F.content_type.not_in({ContentType.TEXT, ContentType.PHOTO, ContentType.VOICE}),
    *is_not_forwarded
)
async def handle_other_content(message: Message, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    await message.answer(_("pm_default"))