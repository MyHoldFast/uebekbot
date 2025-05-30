import os
import tempfile
import asyncio
import base64
import aiohttp

from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from utils.translate import translate_text
from localization import get_localization, DEFAULT_LANGUAGE


API_KEY = os.environ["GEMINI_API_KEY"]
MODEL_NAME = "gemini-2.0-flash-exp-image-generation"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models" 

router = Router()

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

async def generate_image(user_input, image_path: str = None, timeout: int = 30):
    try:
        contents = [{"parts": [{"text": user_input}]}]

        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                img_base64 = base64.b64encode(image_bytes).decode('utf-8')
                contents[0]["parts"].append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_base64
                    }
                })

        url = f"{BASE_URL}/{MODEL_NAME}:generateContent?key={API_KEY}"
        payload = {
            "contents": contents,
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
        }

        headers = {
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    for candidate in data.get("candidates", []):
                        content = candidate.get("content", {})
                        for part in content.get("parts", []):
                            inline_data = part.get("inlineData", {})
                            if inline_data and inline_data.get("data"):
                                return base64.b64decode(inline_data["data"])
                else:
                    print(f"HTTP error: {response.status}, {await response.text()}")
                    return None

    except asyncio.TimeoutError:
        print(f"generate_image timed out after {timeout} seconds")
        return None

    except Exception as e:
        print("generate_image error:", e)
        return None

@router.message(Command("gemimg", ignore_case=True))
@check_command_enabled("gemimg")
async def cmd_gemimg(message: Message, command: CommandObject, bot: Bot):
    user_input = (
        message.reply_to_message.text or message.reply_to_message.caption or ""
        if message.reply_to_message else ""
    )
    if command.args:
        user_input += ("\n" if user_input else "") + command.args

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input:
        await message.reply(_("gemimghelp"))
        return

    photo = (
        message.reply_to_message.photo[-1]
        if message.reply_to_message and message.reply_to_message.photo
        else message.photo[-1] if message.photo
        else None
    )

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        sent_message = await message.reply(_("qwenimg_gen"))

        image_path = None
        output_path = None

        try:
            if photo:
                file = await bot.get_file(photo.file_id)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                    await bot.download_file(file.file_path, destination=tmp_file)
                    image_path = tmp_file.name

            result = await generate_image(user_input, image_path=image_path)

            if result:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as output_file:
                    output_file.write(result)
                    output_path = output_file.name
                
                await asyncio.sleep(0.1)

                await safe_delete(sent_message)

                try:                   
                    await asyncio.shield(
                        message.reply_photo(photo=FSInputFile(output_path))
                    )
                except asyncio.CancelledError:
                    print("Upload task was cancelled during file transmission.")
                    raise
                except Exception as e:
                    print("Failed to send image:", e)
                    await message.reply(_("gemimg_err"))
            else:
                await safe_delete(sent_message)
                await message.reply(_("gemimg_err"))

        except Exception as e:
            print("cmd_gemimg error:", e)
            await safe_delete(sent_message)
            await message.reply(_("gemimg_err"))

        finally:
            for path in (image_path, output_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        print(f"Error deleting file {path}:", e)