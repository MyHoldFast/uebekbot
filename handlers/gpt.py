import asyncio
import base64
import json
import os
import aiohttp
import re
import time
from io import BytesIO
#from concurrent.futures import ProcessPoolExecutor
from utils.text_utils import split_html
from utils.typing_indicator import TypingIndicator
#from duckai import DuckAI
from g4f.client import AsyncClient
from g4f.Provider import Yqcloud
from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pylatexenc.latex2text import LatexNodes2Text

from localization import get_localization, DEFAULT_LANGUAGE
from utils.dbmanager import DB
from chatgpt_md_converter import telegram_format
from utils.command_states import check_command_enabled

API_KEY = os.environ["GEMINI_API_KEY"]
MODEL_NAME = "gemini-2.0-flash"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models" 
URL_PROXY = os.environ["URL_PROXY"]
if URL_PROXY:
    BASE_URL = URL_PROXY + BASE_URL
    
router = Router()

db, Query = DB("db/gpt_models.json").get_db()
context_db, ContextQuery = DB("db/gpt_context.json").get_db()

models = {
    "gpt-4": "gpt-4"
#        "gpt-4o-mini": "gpt-4o-mini",
#        "llama-3.3-70b": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
#        "claude-3-haiku": "claude-3-haiku-20240307",
#       "o3-mini": "o3-mini",
#       "mistral-small-3": "mistralai/Mistral-Small-24B-Instruct-2501",
    }


def get_gpt_keyboard(selected_model: str):
    keyboard = [
        [
            InlineKeyboardButton(
                text="✓ " + key if selected_model == key else key,
                callback_data=key,
            )
        ]
        for key in models.keys()
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def update_model_message(callback_query: CallbackQuery, model: str):
    keyboard = get_gpt_keyboard(model)
    try:
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass


def load_user_context(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        last_modified_time = float(context_item.get("last_modified_time", 0))
        current_time = time.time()
        if current_time - last_modified_time < 3 * 3600:
            return (
                json.loads(
                    base64.b64decode(context_item.get("chat_messages")).decode("utf-8")
                ),
                context_item.get("chat_vqd"),
                context_item.get("chat_vqd_hash"),
            )
    return None, None, None


def save_user_context(user_id, chat_messages, chat_vqd, chat_vqd_hash):
    getcontext = ContextQuery()
    encoded_chat_messages = base64.b64encode(
        json.dumps(chat_messages, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
    current_time = time.time()

    context_item = context_db.get(getcontext.uid == user_id)
    context_data = {
        "uid": user_id,
        "chat_messages": encoded_chat_messages,
        "chat_vqd": chat_vqd,
        "chat_vqd_hash": chat_vqd_hash,
        "last_modified_time": current_time,
    }

    if context_item:
        context_db.update(context_data, getcontext.uid == user_id)
    else:
        context_db.insert(context_data)


def remove_user_context(user_id):
    context_db.remove(ContextQuery().uid == user_id)


def process_latex(text):
    return re.sub(
        r"(?m)^\s*(\$\$|\\\[)\s*\n(.*?)\n\s*(\$\$|\\\])\s*$",
        lambda match: LatexNodes2Text().latex_to_text(match.group(2)),
        text,
        flags=re.DOTALL,
    )


@router.callback_query(lambda c: c.data and c.data in models)
async def callback_query_handler(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    getmodel = Query()
    db_item = db.get(getmodel.uid == user_id)

    if not db_item:
        db.insert({"uid": user_id, "model": callback_query.data})
    else:
        db.update({"model": callback_query.data}, getmodel.uid == user_id)

    remove_user_context(user_id)
    await callback_query.answer()
    await update_model_message(callback_query, callback_query.data)

    user_language = callback_query.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    await callback_query.message.answer(
        f"{callback_query.from_user.first_name}, {_('you_choose_model')} {callback_query.data}"
    )


def split_message(text: str, max_length: int = 4000):
    return [text[i : i + max_length] for i in range(0, len(text), max_length)]

async def process_gemini(message: Message, command: CommandObject, bot, photo):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    text = command.args or "опиши изображение на русском языке"
    try:
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path
        photo_stream = BytesIO()
        await bot.download_file(file_path, destination=photo_stream)
        photo_stream.seek(0)

        image_bytes = photo_stream.getvalue()
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')

        url = f"{BASE_URL}/{MODEL_NAME}:generateContent?key={API_KEY}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": text
                        },
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": img_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {"responseModalities": ["TEXT"]}
        }

        headers = {
            "Content-Type": "application/json"
        }

        async with TypingIndicator(bot=bot, chat_id=message.chat.id):
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    response_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                        except ValueError as e:
                            print(f"Error parsing JSON: {e}")
                            await message.reply(_("gpt_gemini_error"))
                            return

                        candidates = data.get("candidates", [])
                        if not candidates:
                            print("No candidates in response")
                            await message.reply(_("gpt_gemini_error"))
                            return

                        for candidate in candidates:
                            content = candidate.get("content", {})
                            parts = content.get("parts", [])
                            for part in parts:
                                if part.get("text"):
                                    text_response = part.get("text")
                                    chunks = split_html(telegram_format(text_response))
                                    for chunk in chunks:
                                        await message.reply(chunk, parse_mode="HTML")
                                    break
                    else:
                        print(f"HTTP error: {response.status}, {response_text}")
                        await message.reply(_("gpt_gemini_error"))

    except asyncio.TimeoutError:
        print(f"process_gemini timed out after 30 seconds")
        await message.reply(_("gpt_gemini_error"))

    except Exception as e:
        print(f"Gemini error: {e}")
        await message.reply(_("gpt_gemini_error"))


#def chat_with_duckai(model, message, chat_messages, chat_vqd, chat_vqd_hash):
#    duck_ai = DuckAI(proxy=os.getenv("PROXY"))
#    if chat_messages is not None and chat_vqd is not None and chat_vqd_hash is not None:
#        duck_ai._chat_messages = chat_messages
#        duck_ai._chat_vqd = chat_vqd
#        duck_ai._chat_vqd_hash = chat_vqd_hash
#    answer = duck_ai.chat(message, model=model)
#    return answer, duck_ai._chat_messages, duck_ai._chat_vqd, duck_ai._chat_vqd_hash


# async def process_gpt(message: Message, command: CommandObject, user_id):
#     if message.reply_to_message:
#         user_input = (
#             message.reply_to_message.text or message.reply_to_message.caption or ""
#         )
#         if command.args:
#             user_input += "\n" + command.args
#     else:
#         user_input = command.args if command.args else ""

#     model = "gpt-4o-mini"
#     user_model = db.get(Query().uid == user_id)
#     if user_model and user_model["model"] in models:
#         model = user_model["model"]

#     if not user_input:        
#         keyboard = get_gpt_keyboard(model)
#         user_language = message.from_user.language_code or DEFAULT_LANGUAGE
#         _ = get_localization(user_language)
#         await message.reply(_("gpt_help"), reply_markup=keyboard, parse_mode="markdown")
#         return

#     try:
#         chat_messages, chat_vqd, chat_vqd_hash = load_user_context(user_id)

#         async with TypingIndicator(bot=message.bot, chat_id=message.chat.id):
#             loop = asyncio.get_event_loop()
#             with ProcessPoolExecutor() as executor:
#                 answer, messages, vqd, vqdhash = await loop.run_in_executor(
#                     executor,
#                     chat_with_duckai,
#                     model,
#                     user_input,
#                     chat_messages,
#                     chat_vqd,
#                     chat_vqd_hash,
#                 )

#                 if answer:
#                     save_user_context(user_id, messages, vqd, vqdhash)
#                     answer = process_latex(telegram_format(answer))
#                     chunks = split_html(answer)
#                     for chunk in chunks:
#                         await message.reply(chunk, parse_mode="HTML")

#                 else:
#                     raise Exception("Exception")
#     except Exception as e:
#         user_language = message.from_user.language_code or DEFAULT_LANGUAGE
#         _ = get_localization(user_language)
#         print(e)
#         await message.reply(_("gpt_error"), parse_mode="html")

async def process_gpt(message: Message, command: CommandObject, user_id):
    messagetext = (
        message.reply_to_message.text if message.reply_to_message else ""
    )
    if command.args:
        messagetext += "\n" + command.args
    messagetext = messagetext.strip()

    if not messagetext:
        model = "gpt-4"
        user_model = db.get(Query().uid == user_id)
        if user_model and user_model["model"] in models:
            model = user_model["model"]

        keyboard = get_gpt_keyboard(model)
        user_language = message.from_user.language_code or DEFAULT_LANGUAGE
        _ = get_localization(user_language)
        await message.reply(
            _("gpt_help"), reply_markup=keyboard, parse_mode="markdown"
        )
        return

    try:
        proxy = os.getenv("PROXY")
        user_model = db.get(Query().uid == user_id)
        model = (
            user_model["model"]
            if user_model and user_model["model"] in models
            else "gpt-4"
        )

        #chat_messages = load_user_context(user_id)
        chat_messages, _, _ = load_user_context(user_id)
        if chat_messages is not None:
            chat_messages.append({"role": "user", "content": messagetext})
        else:
            chat_messages = [{"role": "user", "content": messagetext}]

        client = AsyncClient(proxies=proxy, provider=Yqcloud)

        async with TypingIndicator(bot=message.bot, chat_id=message.chat.id):
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=chat_messages,
                    web_search=False,
                    ignore_working=True,
                ),
                timeout=60
            )
        answer = response.choices[0].message.content

        if answer:
            chat_messages.append({"role": "assistant", "content": answer})
            #save_user_context(user_id, chat_messages)
            save_user_context(user_id, chat_messages, None, None)
            answer = process_latex(telegram_format(answer))
            chunks = split_html(answer)
            for chunk in chunks:
                await message.reply(chunk, parse_mode="HTML")

        else: raise Exception("Exception")
    except Exception as e:
        user_language = message.from_user.language_code or DEFAULT_LANGUAGE
        _ = get_localization(user_language)
        print(e)
        await message.reply(_("gpt_error"), parse_mode="html")


@router.message(Command("gpt", ignore_case=True))
@check_command_enabled("gpt")
async def cmd_gpt(message: Message, command: CommandObject, bot: Bot):
    user_id = message.from_user.id

    photo = (
        message.reply_to_message.photo[-1]
        if message.reply_to_message and message.reply_to_message.photo
        else None
    )
    photo = photo or (message.photo[-1] if message.photo else None)

    if photo:
        await process_gemini(message, command, bot, photo)
    else:
        await process_gpt(message, command, user_id)


@router.message(Command("gptrm", ignore_case=True))
async def cmd_remove_context(message: Message):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    remove_user_context(message.from_user.id)
    await message.reply(_("gpt_ctx_removed"), parse_mode="markdown")
