import asyncio
import base64
import json
import os
import aiohttp
import re
import time
import itertools
from utils.markdownify import markdownify as md
from io import BytesIO
from utils.text_utils import split_html
from utils.typing_indicator import TypingIndicator
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

_raw_gemini_keys = os.environ.get("GEMINI_API_KEY")

if not _raw_gemini_keys:
    raise RuntimeError("GEMINI_API_KEY is not set")


def parse_gemini_keys(value: str) -> list[str]:
    value = value.strip().strip("[]")
    return [k.strip() for k in value.split(",") if k.strip()]


GEMINI_KEYS = parse_gemini_keys(_raw_gemini_keys)
_gemini_key_cycle = itertools.cycle(GEMINI_KEYS)
_gemini_key_lock = asyncio.Lock()


async def get_next_gemini_key() -> str:
    async with _gemini_key_lock:
        return next(_gemini_key_cycle)


GEMINI_MODEL_NAME = "gemini-2.5-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
URL_PROXY = os.environ.get("URL_PROXY")
if URL_PROXY:
    GEMINI_BASE_URL = URL_PROXY + GEMINI_BASE_URL

GPT_API_URL = "https://duckai.mbteam.ru/v1/chat/completions"

router = Router()

db, Query = DB("db/gpt_models.json").get_db()
context_db, ContextQuery = DB("db/gpt_context.json").get_db()


models = {
    "gpt-5-mini": "gpt-5-mini",
    "gpt-4o-mini": "gpt-4o-mini",
    "llama-4": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
    "claude-3.5-haiku": "claude-3-5-haiku-latest",
    "mistral-small-3": "mistralai/Mistral-Small-24B-Instruct-2501",
    "openai/gpt-oss-120b": "openai/gpt-oss-120b",
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
    

def load_user_context(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        last_modified_time = float(context_item.get("last_modified_time", 0))
        if time.time() - last_modified_time < 3 * 3600:
            return (
                json.loads(
                    base64.b64decode(context_item.get("chat_messages")).decode("utf-8")
                ),
                context_item.get("chat_vqd"),
                context_item.get("chat_vqd_hash"),
            )
    return None, None, None


def save_user_context(user_id, chat_messages, chat_vqd, chat_vqd_hash):
    encoded_chat_messages = base64.b64encode(
        json.dumps(chat_messages, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    context_data = {
        "uid": user_id,
        "chat_messages": encoded_chat_messages,
        "chat_vqd": chat_vqd,
        "chat_vqd_hash": chat_vqd_hash,
        "last_modified_time": time.time(),
    }

    if context_db.get(ContextQuery().uid == user_id):
        context_db.update(context_data, ContextQuery().uid == user_id)
    else:
        context_db.insert(context_data)


def remove_user_context(user_id):
    context_db.remove(ContextQuery().uid == user_id)


def process_latex(text):
    return re.sub(
        r"(?m)^\s*(\$\$|\\\[)\s*\n(.*?)\n\s*(\$\$|\\\])\s*$",
        lambda m: LatexNodes2Text().latex_to_text(m.group(2)),
        text,
        flags=re.DOTALL,
    )


def split_message(text: str, max_length: int = 4000):
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]



async def process_gemini(message: Message, command: CommandObject, bot: Bot, photo):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    text = command.args or "опиши изображение на русском языке"
    try:
        file = await bot.get_file(photo.file_id)
        photo_stream = BytesIO()
        await bot.download_file(file.file_path, destination=photo_stream)
        image_bytes = photo_stream.getvalue()

        api_key = await get_next_gemini_key()

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": text},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64.b64encode(image_bytes).decode(),
                            }
                        },
                    ]
                }
            ]
        }

        url = (
            f"{GEMINI_BASE_URL}/"
            f"{GEMINI_MODEL_NAME}:generateContent"
            f"?key={api_key}"
        )

        async with TypingIndicator(bot=bot, chat_id=message.chat.id):
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        await message.reply(_("gpt_gemini_error"))
                        return

                    data = await resp.json()

        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    for chunk in split_html(telegram_format(part["text"])):
                        await message.reply(chunk, parse_mode="HTML")
                    return

        await message.reply(_("gpt_gemini_error"))

    except Exception as e:
        print("Gemini error:", e)
        await message.reply(_("gpt_gemini_error"))


async def process_gpt(message: Message, command: CommandObject, user_id):
    messagetext = message.reply_to_message.text if message.reply_to_message else ""
    if command.args:
        messagetext += "\n" + command.args
    messagetext = messagetext.strip()

    model = "gpt-5-mini"
    user_model = db.get(Query().uid == user_id)
    if user_model and user_model["model"] in models:
        model = user_model["model"]

    if not messagetext:
        await message.reply(
            get_localization(message.from_user.language_code or DEFAULT_LANGUAGE)(
                "gpt_help"
            ),
            reply_markup=get_gpt_keyboard(model),
            parse_mode="markdown",
        )
        return

    try:
        chat_messages, _, _ = load_user_context(user_id)
        messages_for_api = (
            chat_messages + [{"role": "user", "content": messagetext}]
            if chat_messages
            else [{"role": "user", "content": messagetext}]
        )

        async with TypingIndicator(bot=message.bot, chat_id=message.chat.id):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GPT_API_URL,
                    json={"model": models[model], "messages": messages_for_api},
                    timeout=60,
                ) as resp:
                    data = await resp.json()

        answer = data["choices"][0]["message"]["content"]

        chat_messages = messages_for_api + [
            {"role": "assistant", "content": answer}
        ]
        save_user_context(user_id, chat_messages, None, None)

        answer = process_latex(telegram_format(answer))
        for chunk in split_html(answer):
            await message.reply(chunk, parse_mode="HTML")

    except Exception as e:
        print("GPT error:", e)
        await message.reply(
            get_localization(message.from_user.language_code or DEFAULT_LANGUAGE)(
                "gpt_error"
            ),
            parse_mode="html",
        )


@router.message(Command("gpt", ignore_case=True))
@check_command_enabled("gpt")
async def cmd_gpt(message: Message, command: CommandObject, bot: Bot):
    photo = (
        message.reply_to_message.photo[-1]
        if message.reply_to_message and message.reply_to_message.photo
        else None
    ) or (message.photo[-1] if message.photo else None)

    if photo:
        await process_gemini(message, command, bot, photo)
    else:
        await process_gpt(message, command, message.from_user.id)


@router.message(Command("gptrm", ignore_case=True))
async def cmd_remove_context(message: Message):
    remove_user_context(message.from_user.id)
    await message.reply(
        get_localization(message.from_user.language_code or DEFAULT_LANGUAGE)(
            "gpt_ctx_removed"
        ),
        parse_mode="markdown",
    )
