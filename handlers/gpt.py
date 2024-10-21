import asyncio
import base64
import json
import os
import re
import time
from aiogram import Bot, Router, html
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from duckduckgo_search import AsyncDDGS
import google.generativeai as genai
from pylatexenc.latex2text import LatexNodes2Text
from keyboards.gpt import get_gpt_keyboard, models
from localization import get_localization, DEFAULT_LANGUAGE
from utils.dbmanager import DB
from chatgpt_md_converter import telegram_format

router = Router()
db, Query = DB('db/models.json').get_db()
context_db, ContextQuery = DB('db/user_context.json').get_db()

async def update_model_message(callback_query: CallbackQuery, model: str):
    await callback_query.message.edit_reply_markup(reply_markup=get_gpt_keyboard(model))

def get_user_context(user_id):
    context = context_db.get(ContextQuery().uid == user_id)
    if context and time.time() - float(context.get('last_modified_time', 0)) < 3 * 3600:
        return json.loads(base64.b64decode(context['chat_messages']).decode('utf-8')), context['chat_vqd']
    return None, None

def set_user_context(user_id, chat_messages, chat_vqd):
    context_item = {
        'uid': user_id,
        'chat_messages': base64.b64encode(json.dumps(chat_messages).encode()).decode(),
        'chat_vqd': chat_vqd,
        'last_modified_time': time.time()
    }
    context_db.upsert(context_item, ContextQuery().uid == user_id)

def process_latex(text):
    return re.sub(
        r'(?m)^\s*\\\[\s*\n(.*?)\n\s*\\\]\s*$', 
        lambda m: LatexNodes2Text().latex_to_text(f"$${m.group(1).replace('\\\\', '\\')}$$"), 
        text, 
        flags=re.DOTALL
    )

@router.callback_query(lambda c: c.data in models)
async def handle_model_selection(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    db.upsert({'uid': user_id, 'model': callback_query.data}, Query().uid == user_id)
    set_user_context(user_id, [], None)
    await callback_query.answer()
    await update_model_message(callback_query, callback_query.data)
    user_language = callback_query.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    await callback_query.message.answer(f"{callback_query.from_user.first_name}, {_('you_choose_model')} {callback_query.data}")

@router.message(Command("gpt"))
async def handle_gpt(message: Message, command: Command, bot: Bot):
    user_id = message.from_user.id
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    
    messagetext = message.reply_to_message.text if message.reply_to_message else command.args
    await bot.send_chat_action(message.chat.id, 'typing')

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    photo = message.photo[-1] if message.photo else None
    if photo:
        text = command.args or "опиши изображение на русском языке"
        file = await bot.get_file(photo.file_id)
        image_data = await bot.download_file(file.file_path)
        image_path = f"tmp/{photo.file_id}.jpg"
        with open(image_path, "wb") as temp_file:
            temp_file.write(image_data.read())
        try:
            file_url = await asyncio.to_thread(genai.upload_file, image_path)
            model = genai.GenerativeModel("gemini-1.5-flash")
            result = await asyncio.to_thread(model.generate_content, [file_url, "\n\n", text])
            await message.reply(telegram_format(result.text), parse_mode="HTML")
        finally:
            os.remove(image_path)
        return

    model = db.get(Query().uid == user_id)
    model = model["model"] if model else "gpt-4o-mini"

    chat_messages, chat_vqd = get_user_context(user_id)
    if messagetext:
        try:
            d = AsyncDDGS()
            if chat_messages is not None and chat_vqd is not None:
                d._chat_messages = chat_messages
                d._chat_vqd = chat_vqd
            answer = await d.achat(messagetext, model=model)
            set_user_context(user_id, d._chat_messages, d._chat_vqd)
            answer_processed = process_latex(telegram_format(answer))
            for chunk in (answer_processed[i:i + 4000] for i in range(0, len(answer_processed), 4000)):
                await message.reply(chunk, parse_mode="HTML")
        except Exception as e:
            print(e)
            await message.reply(_("gpt_error"), parse_mode="HTML")
    else:
        await message.reply(_("gpt_help"), reply_markup=get_gpt_keyboard(model), parse_mode="markdown")

@router.message(Command("gptrm"))
async def remove_context(message: Message):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    set_user_context(message.from_user.id, [], None)
    await message.reply(_("gpt_ctx_removed"), parse_mode="markdown")
