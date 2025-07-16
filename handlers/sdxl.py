from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from utils.typing_indicator import TypingIndicator
from aiogram.exceptions import TelegramBadRequest
from utils.command_states import check_command_enabled
from handlers.admin import admin_only
from localization import get_localization, DEFAULT_LANGUAGE
from utils.command_states import check_command_enabled
from g4f.client import AsyncClient
from g4f.Provider import ImageLabs

router = Router() 


@router.message(Command("sdxl", ignore_case=True))
@admin_only
@check_command_enabled("sdxl")
async def cmd_sdxl(message: Message, command: CommandObject, bot: Bot):
    if message.reply_to_message:
        user_input = (
            message.reply_to_message.text or message.reply_to_message.caption or ""
        )
        if command.args:
            user_input += "\n" + command.args
    else:
        user_input = command.args if command.args else ""

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input:
        await message.reply(_("qwenimghelp"))
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):

        sent_message = await message.reply(_("qwenimg_gen"))        

        try:
            client = AsyncClient(image_provider=ImageLabs)
            response = await client.images.generate(
            model="sdxl-turbo",
            prompt=user_input,
            response_format="url"
            )
            await safe_delete(sent_message)
            await message.reply_photo(photo=response.data[0].url, has_spoiler=True)
        except Exception:
            await safe_delete(sent_message)
            await message.reply(_("qwenimg_err"))

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass