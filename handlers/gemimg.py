import os
import tempfile
import asyncio
import json
from pathlib import Path

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
from gemini_webapi.utils import rotate_1psidts

set_log_level("CRITICAL")

router = Router()

client = None
client_lock = asyncio.Lock()

async def update_env_cookies():
    try:
        env_path = Path(".env")
        secure_1psid = os.environ.get("GEMINI_SECURE_1PSID", "")
        secure_1psidts = os.environ.get("GEMINI_SECURE_1PSIDTS", "")
        
        if not env_path.exists():
            with open(env_path, "w", encoding="utf-8") as f:
                if secure_1psid:
                    f.write(f"GEMINI_SECURE_1PSID={secure_1psid}\n")
                if secure_1psidts:
                    f.write(f"GEMINI_SECURE_1PSIDTS={secure_1psidts}\n")
            return
        
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        updated_lines = []
        
        for line in lines:
            line = line.strip()
            if line.startswith("GEMINI_SECURE_1PSID="):
                if secure_1psid:
                    updated_lines.append(f"GEMINI_SECURE_1PSID={secure_1psid}\n")
                else:
                    updated_lines.append(line + "\n")
            elif line.startswith("GEMINI_SECURE_1PSIDTS="):
                if secure_1psidts:
                    updated_lines.append(f"GEMINI_SECURE_1PSIDTS={secure_1psidts}\n")
                else:
                    updated_lines.append(line + "\n")
            else:
                updated_lines.append(line + "\n")
        
        if not any(line.startswith("GEMINI_SECURE_1PSID=") for line in updated_lines) and secure_1psid:
            updated_lines.append(f"GEMINI_SECURE_1PSID={secure_1psid}\n")
        
        if not any(line.startswith("GEMINI_SECURE_1PSIDTS=") for line in updated_lines) and secure_1psidts:
            updated_lines.append(f"GEMINI_SECURE_1PSIDTS={secure_1psidts}\n")
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        
    except Exception:
        pass

async def get_client():
    global client
    
    Secure_1PSID = os.environ.get("GEMINI_SECURE_1PSID")
    Secure_1PSIDTS = os.environ.get("GEMINI_SECURE_1PSIDTS")
    
    if not Secure_1PSID:
        return None
    
    async with client_lock:
        if client is None:
            client = GeminiClient(Secure_1PSID, Secure_1PSIDTS, proxy=None)
            
            async def custom_auto_refresh():
                while client._running:
                    await asyncio.sleep(300)
                    
                    if not client._running:
                        break
                    
                    try:
                        async with client._lock:
                            new_1psidts, rotated_cookies = await rotate_1psidts(
                                client.cookies, client.proxy
                            )
                            
                            if rotated_cookies:
                                client.cookies.update(rotated_cookies)
                                if client.client:
                                    client.client.cookies.update(rotated_cookies)
                                
                                secure_1psid = rotated_cookies.get("__Secure-1PSID")
                                secure_1psidts = rotated_cookies.get("__Secure-1PSIDTS")
                                
                                if secure_1psid:
                                    os.environ["GEMINI_SECURE_1PSID"] = secure_1psid
                                if secure_1psidts:
                                    os.environ["GEMINI_SECURE_1PSIDTS"] = secure_1psidts
                                
                                await update_env_cookies()
                    
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        pass
            
            await client.init(
                timeout=30,
                auto_refresh=True,
                refresh_interval=300,
                verbose=False
            )
            
            refresh_task = asyncio.create_task(custom_auto_refresh())
            client.refresh_task = refresh_task
        
        return client

async def extract_prompt_from_response(text):
    try:
        if not text or not isinstance(text, str):
            return None
        
        text = text.strip()
        
        if '"action": "image_generation"' in text:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and data.get("action") == "image_generation":
                    action_input = data.get("action_input", "")
                    
                    if isinstance(action_input, str):
                        try:
                            inner_data = json.loads(action_input.replace("'", '"'))
                        except:
                            try:
                                inner_data = json.loads(action_input)
                            except:
                                return None
                        
                        prompt = inner_data.get("prompt")
                        if prompt:
                            return prompt
                    elif isinstance(action_input, dict):
                        prompt = action_input.get("prompt")
                        if prompt:
                            return prompt
            except json.JSONDecodeError:
                return None
        
        return None
    except Exception:
        return None

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
            extracted_prompt = await extract_prompt_from_response(response.text)
            
            if extracted_prompt:
                second_response = await client.generate_content(extracted_prompt)
                
                if second_response.images:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                        tmp_path = tmp_file.name
                    
                    await second_response.images[0].save(
                        path=os.path.dirname(tmp_path),
                        filename=os.path.basename(tmp_path),
                        skip_invalid_filename=True
                    )
                    
                    return tmp_path
                elif second_response.text:
                    return second_response.text
                else:
                    return None
            else:
                return response.text
        
        return None
            
    except Exception:
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

        except Exception:
            await safe_delete(sent_message)
            await message.reply(_("gemimg_err"))

        finally:
            for path in (image_path, generated_image_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass