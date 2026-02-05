import os
import tempfile
import asyncio

from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from localization import get_localization, DEFAULT_LANGUAGE

from gemini_webapi import GeminiClient
from gemini_webapi import set_log_level

set_log_level("CRITICAL")

router = Router()

client = None
client_cookies = None
client_lock = asyncio.Lock()

async def get_client():
    global client, client_cookies
    
    Secure_1PSID = os.environ.get("GEMINI_SECURE_1PSID")
    Secure_1PSIDTS = os.environ.get("GEMINI_SECURE_1PSIDTS")
    
    if not Secure_1PSID:
        return None
    
    current_cookies = (Secure_1PSID, Secure_1PSIDTS)
    
    async with client_lock:
        if client is None or client_cookies != current_cookies:
            client = GeminiClient(Secure_1PSID, Secure_1PSIDTS, proxy=None)
            await client.init(timeout=30)
            client_cookies = current_cookies
        
        return client

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

async def generate_image_gemini_web(user_input, image_path=None):
    try:
        enhanced_prompt = f"{user_input}. Generate a large, detailed, high-quality image."
        
        client = await get_client()
        if not client:
            return None

        if image_path and os.path.exists(image_path):
            response = await client.generate_content(enhanced_prompt, files=[image_path])
        else:
            response = await client.generate_content(enhanced_prompt)

        if response.images:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                tmp_path = tmp_file.name
            
            await response.images[0].save(
                path=os.path.dirname(tmp_path),
                filename=os.path.basename(tmp_path),
                skip_invalid_filename=True
            )
            
            return tmp_path
        
        if response.text:
            return response.text
        
        return None
            
    except Exception as e:
        print(f"generate_image_gemini_web error: {e}")
        return None

@router.message(Command("gemimg", ignore_case=True))
@check_command_enabled("gemimg")
async def cmd_gemimg(message: Message, command: CommandObject, bot: Bot):    
    photo = (
        message.reply_to_message.photo[-1]
        if message.reply_to_message and message.reply_to_message.photo
        else message.photo[-1] if message.photo
        else None
    )
    
    user_input = (
        message.reply_to_message.text or message.reply_to_message.caption or ""
        if message.reply_to_message and not photo else ""
    )
    
    if command.args:
        user_input += ("\n" if user_input else "") + command.args

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input:
        await message.reply(_("gemimghelp"))
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        sent_message = await message.reply(_("qwenimg_gen"))

        image_path = None
        generated_image_path = None

        try:
            if photo:
                file = await bot.get_file(photo.file_id)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                    await bot.download_file(file.file_path, destination=tmp_file)
                    image_path = tmp_file.name

            result = await generate_image_gemini_web(user_input, image_path)

            if isinstance(result, str) and result.endswith('.png') and os.path.exists(result):
                generated_image_path = result
                await asyncio.sleep(0.1)
                await safe_delete(sent_message)
                await message.reply_photo(photo=FSInputFile(generated_image_path))
            
            elif isinstance(result, str):
                await safe_delete(sent_message)
                await message.reply(result[:4000], parse_mode="Markdown")
            
            else:
                await safe_delete(sent_message)
                await message.reply(_("gemimg_err"))

        except Exception as e:
            print(f"cmd_gemimg error: {e}")
            await safe_delete(sent_message)
            await message.reply(_("gemimg_err"))

        finally:
            for path in (image_path, generated_image_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        print(f"Error deleting file {path}: {e}")