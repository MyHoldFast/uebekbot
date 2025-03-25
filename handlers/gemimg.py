import aiohttp
import base64
import os
from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.types.input_file import BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from utils.translate import translate_text
from localization import get_localization, DEFAULT_LANGUAGE

URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent?key={os.environ["GEMINI_API_KEY"]}"

router = Router()

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

async def generate_image(session, user_input):
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": await translate_text(user_input, "auto", "en")}]}],
        "generationConfig": {"responseModalities": ["Text", "Image"]}
    }
    try:
        async with session.post(URL, headers=headers, json=data) as response:
            if response.status == 200:
                json_response = await response.json()
                for candidate in json_response.get("candidates", []):
                    for part in candidate.get("content", {}).get("parts", []):
                        if "inlineData" in part:
                            return base64.b64decode(part["inlineData"].get("data"))
            return None
    except Exception:
        return None

@router.message(Command("gemimg", ignore_case=True))
@check_command_enabled("gemimg")
async def cmd_gemimg(message: Message, command: CommandObject, bot: Bot):
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
            async with aiohttp.ClientSession() as session:
                image_bytes = await generate_image(session, user_input)
                if image_bytes:
                    photo = BufferedInputFile(image_bytes, filename="image.png")
                    await safe_delete(sent_message)
                    await message.answer_photo(photo=photo)
                else:
                    await safe_delete(sent_message)
                    await message.reply(_("qwenimg_err"))
        except Exception:
            await safe_delete(sent_message)
            await message.reply(_("qwenimg_err"))