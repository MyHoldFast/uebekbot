import aiohttp
import asyncio
import base64
import json
import os
import re
import time

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from utils.command_states import check_command_enabled

from localization import DEFAULT_LANGUAGE, get_localization

router = Router()

lock = asyncio.Lock()
token_lock = asyncio.Lock()

url = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"

iam_token = None
token_expiry_time = 0

async def fetch_token():
    global iam_token, token_expiry_time
    async with token_lock:
        if time.time() > token_expiry_time:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://iam.api.cloud.yandex.net/iam/v1/tokens", data=json.dumps({"yandexPassportOauthToken": os.getenv("YANDEX_OAUTH_TOKEN")})) as response:
                    response.raise_for_status()
                    token_data = await response.json()
                    iam_token = token_data['iamToken']
                    token_expiry_time = time.time() + 7200  # Токен действителен в течение 2 часов
        return iam_token

async def do_ocr_request(file_id, bot):
    async with lock:
        file = await bot.get_file(file_id)
        file_path = file.file_path
        bytesIO = await bot.download_file(file_path)
        curData = {
            "content": base64.b64encode(bytesIO.read()).decode('utf-8'),
            "mimeType": "JPEG",
            "languageCodes": ["*"],
            "model": "page"
        }
        try:
            token = await fetch_token()
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=json.dumps(curData), headers={"Authorization": "Bearer {}".format(token), "Content-Type": "application/json", "x-folder-id": os.getenv("FOLDER_ID")}) as response:
                    response.raise_for_status()
                    ocr_result = await response.json()
        except aiohttp.ClientError as ex:
            print("Exception during request! {}".format(str(ex)))
            return None
        else:
            return re.sub(r'\n(?!\n)', ' ', ocr_result['result']['textAnnotation']['fullText'])

@router.message(Command("ocr", ignore_case=True))
@check_command_enabled("ocr")
async def ocr_handle(message: Message, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    translate_button = InlineKeyboardButton(
        text=_("translate_button"), 
        callback_data='translate'
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[translate_button]])  

    photo = None

    if message.reply_to_message:
        if message.reply_to_message.photo:
            photo = message.reply_to_message.photo[-1]
        elif message.reply_to_message.document:
            if message.reply_to_message.document.mime_type.startswith('image/'):
                photo = message.reply_to_message.document

    if not photo and message.photo:
        photo = message.photo[-1]

    if photo:
        await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
        result = await do_ocr_request(photo.file_id, bot)
        if result:
            for x in range(0, len(result), 4096):
                await message.reply((result[x:x + 4096]), reply_markup=keyboard)
        else:
            await message.reply(_("recognition_failed"))
    else:
        await message.reply(_("use_reply_or_attach_image"))
