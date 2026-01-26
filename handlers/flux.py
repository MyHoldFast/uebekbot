from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile
from aiogram.exceptions import TelegramBadRequest
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
            "User-Agent": "Mozilla/5.0",
        }

        payload = {
            "model": "black-forest-labs/FLUX-2-max",
            "prompt": prompt,
            "response_format": "b64_json",
           # "height": 480,
           # "width": 832,
        }

        async with TypingIndicator(bot=bot, chat_id=message.chat.id):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepinfra.com/v1/openai/images/generations",
                    headers=headers,
                    json=payload,
                    timeout=180,
                ) as response:

                    if response.status != 200:
                        raise Exception(f"{response.status}: {await response.text()}")

                    result = await response.json()

                    b64_image = result["data"][0]["b64_json"]
                    image_bytes = base64.b64decode(b64_image)

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        tmp.write(image_bytes)
                        image_path = tmp.name

        await sent_message.delete()
        await message.reply_photo(photo=FSInputFile(image_path))

    except Exception as e:
        try:
            await sent_message.delete()
        except TelegramBadRequest:
            pass
        await message.reply(_("qwenimg_err") + f" ({str(e)})")

    finally:
        try:
            os.remove(image_path)
        except Exception:
            pass