import re, os, json, time
from aiogram import Router, Bot, F
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.filters import Command, CommandObject
from utils.typing_indicator import TypingIndicator
from localization import get_localization, DEFAULT_LANGUAGE
from utils.command_states import check_command_enabled
from aiohttp import ClientSession
from handlers.callbacks import throttle

router = Router()

actions_name = {
    "make_text_more_complex": "Сделать сложнее",
    "make_text_more_simple": "Сделать проще",
    "make_text_more_formal": "Формальный стиль",
    "make_more_casual": "Разговорный стиль",
    "rephrase": "Переформулировать",
    "improve_text": "Улучшить текст",
    "correct_mistakes": "Исправить ошибки",
}

actions = list(actions_name.keys())

cookies = {
    "yp": os.getenv("YANDEX_YP_COOK"),
    "Session_id": os.getenv("YANDEX_SESSIONID_COOK"),
}

headers = {"origin": "https://translate.yandex.ru"}

params = {
    "sid": "initial-placeholder",
    "srv": "tr-editor",
}

SID_CACHE_FILE = "db/sid_cache.json"

def decode_sid(sid: str, hostname = "translate.yandex.ru") -> str:
    if not sid:
        return ""
    parts = sid.split(".")
    if "yandex." in hostname:
        parts = [part[::-1] for part in parts]
    else:
        parts = [part[::-1][::-1] for part in parts]

    return ".".join(parts)

async def get_sid():
    now = time.time()
    sid = None

    if os.path.exists(SID_CACHE_FILE):
        with open(SID_CACHE_FILE, "r", encoding="utf-8") as f:
            try:
                cache = json.load(f)
                if now - cache.get("timestamp", 0) < 2 * 24 * 3600:
                    sid = cache.get("sid")
            except Exception:
                pass

    if not sid:
        async with ClientSession() as session:
            async with session.get("https://translate.yandex.ru/editor",
                    params=params,
                    headers=headers,
                    cookies=cookies) as resp:
                html = await resp.text()
                match = re.search(r'"SID":"([a-z0-9.]+)"', html)
                if not match:
                    raise RuntimeError("SID not found in page.")
                sid = match.group(1)
                sid = decode_sid(sid) + "-00-0"

                with open(SID_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"sid": sid, "timestamp": now}, f)

    return sid

@router.message(Command("rephrase", ignore_case=True))
@check_command_enabled("rephrase")
async def cmd_rephrase(message: Message, command: CommandObject, bot: Bot):
    reply_id = message.reply_to_message.message_id if message.reply_to_message else None
    user_input = (
        (message.reply_to_message.text or message.reply_to_message.caption or "")
        if message.reply_to_message
        else ""
    )
    if command.args:
        user_input += "\n" + command.args if user_input else command.args

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input.strip():
        await message.reply(_("text_or_reply"))
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=action)]
            for action, label in actions_name.items()
        ]
    )
    
    text = "Что сделать с текстом?"
    if reply_id:
        await message.answer(
            text,
            reply_markup=keyboard,
            reply_to_message_id=reply_id,
        )
    else:
        await message.reply(text, reply_markup=keyboard)


@router.callback_query(F.data.in_(actions))
@throttle(seconds=5)
async def on_action_callback(callback: CallbackQuery, bot: Bot):
    action = callback.data
    chat_id = callback.message.chat.id
    original_msg = callback.message.reply_to_message

    if not original_msg:
        await callback.answer()
        await callback.message.reply("Оригинальный текст не найден.")
        return

    src_text = original_msg.text or original_msg.caption
    src_text = re.sub(r"^\/rephrase(@\w+)?(\s+)?", "", src_text, flags=re.IGNORECASE)

    async with TypingIndicator(bot=bot, chat_id=chat_id):
        try:
            params["sid"] = await get_sid()

            async with ClientSession() as session:
                async with session.post(
                    "https://translate.yandex.ru/editor/api/v1/transform-text",
                    params=params,
                    headers=headers,
                    cookies=cookies,
                    
                    data={
                        "action_type": action,
                        "targ_lang": "ru",
                        "src_text": src_text,
                    },
                ) as resp:
                    json_resp = await resp.json()
                    result = json_resp.get("result_text", "Ошибка при обработке текста.")
        except Exception as e:
            result = f"Ошибка при обработке текста.\n{str(e)}"
        
        await callback.answer()
        await callback.message.answer(
            result, reply_to_message_id=original_msg.message_id
        )
