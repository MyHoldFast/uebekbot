from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile
from utils.typing_indicator import TypingIndicator
from localization import get_localization, DEFAULT_LANGUAGE
from utils.command_states import check_command_enabled
import aiohttp
import base64
import tempfile
import os

router = Router()

@router.message(Command("flux", ignore_case=True))
@check_command_enabled("flux")
async def cmd_flux(message: Message, command: CommandObject, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    
    if message.reply_to_message:
        prompt = message.reply_to_message.text or message.reply_to_message.caption or ""
        if command.args:
            prompt += "\n" + command.args
    else:
        prompt = command.args if command.args else ""
    
    if not prompt:
        await message.reply(_("qwenimghelp"))
        return

    sent_message = await message.reply(_("qwenimg_gen"))

    try:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "DNT": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Origin": "http://localhost:8080",
            "Referer": "http://localhost:8080/",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Pragma": "no-cache"
        }

        payload = {
            "model": "black-forest-labs/FLUX-2-pro",
            "prompt": prompt,
            "response_format": "b64_json",
            "height": 480,
            "width": 832,
        }

        async with TypingIndicator(bot=bot, chat_id=message.chat.id):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.options(
                        "https://api.deepinfra.com/v1/openai/images/generations",
                        headers={
                            "Accept": "*/*",
                            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3",
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "Origin": "http://localhost:8080",
                            "Pragma": "no-cache",
                            "Referer": "http://localhost:8080/",
                            "Sec-Fetch-Dest": "empty",
                            "Sec-Fetch-Mode": "cors",
                            "Sec-Fetch-Site": "cross-site",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                            "Access-Control-Request-Headers": "content-type",
                            "Access-Control-Request-Method": "POST"
                        },
                        timeout=30
                    ) as options_response:
                        if options_response.status not in (200, 204):
                            print(f"Preflight failed: {options_response.status}")
            except Exception as e:
                print(f"Preflight error (non-critical): {e}")

            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://api.deepinfra.com/v1/openai/images/generations",
                    headers=headers,
                    json=payload,
                    timeout=timeout
                ) as response:

                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API Error {response.status}: {error_text}")

                    result = await response.json()
                    
                    if "data" not in result or not result["data"]:
                        raise Exception("No image data in response")
                    
                    b64_image = result["data"][0]["b64_json"]
                    image_bytes = base64.b64decode(b64_image)

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        tmp.write(image_bytes)
                        image_path = tmp.name

        await sent_message.delete()
        await message.reply_photo(photo=FSInputFile(image_path))

    except aiohttp.ClientError as e:
        await sent_message.delete()
        await message.reply(_("qwenimg_err") + f" (Network error: {str(e)})")
    except Exception as e:
        await sent_message.delete()
        await message.reply(_("qwenimg_err") + f" ({str(e)})")

    finally:
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass