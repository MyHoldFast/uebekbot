import os
import tempfile
import asyncio

from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from google import genai
from google.genai import types
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from utils.translate import translate_text
from localization import get_localization, DEFAULT_LANGUAGE

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
router = Router()

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

async def generate_image(user_input, image_path: str = None):
    try:
        def sync_generate():
            contents = [user_input]

            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                    contents.append(image_part)

            response = client.models.generate_content(
                model="gemini-2.0-flash-preview-image-generation",
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

            for part in response.candidates[0].content.parts:
                if getattr(part, "inline_data", None):
                    return part.inline_data.data
            return None

        return await asyncio.to_thread(sync_generate)

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
                    output_file.flush()
                    output_path = output_file.name

                await safe_delete(sent_message)
                await message.reply_photo(photo=FSInputFile(output_path))
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
                        print(f"Ошибка удаления файла {path}:", e)
