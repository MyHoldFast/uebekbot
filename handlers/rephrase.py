import re, os
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
    "sid": "312bc51e.68790e7c.452ffae0.74722d656469746f72-00-0",
    "srv": "tr-editor",
}


@router.message(Command("rephrase", ignore_case=True))
@check_command_enabled("rephrase")
async def on_text(message: Message, command: CommandObject, bot: Bot):
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

    if reply_id:
        await message.answer(
            "Что сделать с текстом?",
            reply_markup=keyboard,
            reply_to_message_id=reply_id,
        )
    else:
        await message.reply("Что сделать с текстом?", reply_markup=keyboard)


@router.callback_query(F.data.in_(actions))
async def on_action_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    action = callback.data
    chat_id = callback.message.chat.id
    original_msg = callback.message.reply_to_message

    if not original_msg:
        await callback.message.answer("Оригинальный текст не найден.")
        return

    src_text = original_msg.text or original_msg.caption
    src_text = re.sub(r"^\/rephrase(@\w+)?(\s+)?", "", src_text, flags=re.IGNORECASE)

    async with TypingIndicator(bot=bot, chat_id=chat_id):
        try:
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
                    result = json_resp.get("result_text", "Ошибка")
        except:
            result = "Ошибка при обработке текста."

        await callback.message.answer(
            result, reply_to_message_id=original_msg.message_id
        )