import asyncio
import base64
import json
import os
import re
import time
import html

from utils.text_utils import split_html
from utils.typing_indicator import TypingIndicator
from utils.duckduckgo_chat import DuckDuckGoChat
from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
import google.generativeai as genai
from pylatexenc.latex2text import LatexNodes2Text
from aiogram.exceptions import TelegramBadRequest

from localization import get_localization, DEFAULT_LANGUAGE
from utils.dbmanager import DB
from chatgpt_md_converter import telegram_format
from utils.command_states import check_command_enabled

router = Router()
db, Query = DB('db/gpt_models.json').get_db()
context_db, ContextQuery = DB('db/gpt_context.json').get_db()

models = {
    "gpt-4o-mini": "gpt-4o-mini",
    "o3-mini": "o3-mini",
    "Mistral Small 3": "mistralai/Mistral-Small-24B-Instruct-2501",
    "claude-3-haiku": "claude-3-haiku-20240307",        
    "llama 3.3 70B": "meta-llama/Llama-3.3-70B-Instruct-Turbo"
}

def get_gpt_keyboard(selected_model: str):
    keyboard = [
        [InlineKeyboardButton(text="✓ " + key if selected_model == key else key, callback_data=key)]
        for key in models.keys()
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def update_model_message(callback_query: CallbackQuery, model: str):
    keyboard = get_gpt_keyboard(model)
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)

def load_user_context(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        last_modified_time = float(context_item.get('last_modified_time', 0))
        current_time = time.time()
        if current_time - last_modified_time < 3 * 3600:
            return json.loads(base64.b64decode(context_item.get('chat_messages')).decode('utf-8')), context_item.get('chat_vqd'), context_item.get('chat_vqd_hash')
    return None, None, None

def save_user_context(user_id, chat_messages, chat_vqd, chat_vqd_hash):
    getcontext = ContextQuery()
    encoded_chat_messages = base64.b64encode(json.dumps(chat_messages, ensure_ascii=False).encode('utf-8')).decode('utf-8')
    current_time = time.time()

    context_item = context_db.get(getcontext.uid == user_id)
    context_data = {
        'uid': user_id,
        'chat_messages': encoded_chat_messages,
        'chat_vqd': chat_vqd,
        'chat_vqd_hash': chat_vqd_hash,
        'last_modified_time': current_time
    }

    if context_item:
        context_db.update(context_data, getcontext.uid == user_id)
    else:
        context_db.insert(context_data)

def remove_user_context(user_id):
    context_db.remove(ContextQuery().uid == user_id)

def process_latex(text):
    return re.sub(
        r'(?m)^\s*(\$\$|\\\[)\s*\n(.*?)\n\s*(\$\$|\\\])\s*$',
        lambda match: LatexNodes2Text().latex_to_text(match.group(2)),
        text,
        flags=re.DOTALL
    )

@router.callback_query(lambda c: c.data and c.data in models)
async def callback_query_handler(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    getmodel = Query()
    db_item = db.get(getmodel.uid == user_id)

    if not db_item:
        db.insert({'uid': user_id, 'model': callback_query.data})
    else:
        db.update({'model': callback_query.data}, getmodel.uid == user_id)

    remove_user_context(user_id)
    await callback_query.answer()
    await update_model_message(callback_query, callback_query.data)

    user_language = callback_query.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    await callback_query.message.answer(
        f"{callback_query.from_user.first_name}, {_('you_choose_model')} {callback_query.data}"
    )

def split_message(text: str, max_length: int = 4000):
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]

async def process_gemini(message: Message, command: CommandObject, bot: Bot, photo):
    text = command.args or "опиши изображение на русском языке"
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    bytesIO = await bot.download_file(file_path)
    image_data = bytesIO.read()
    tmp_file = f"tmp/{photo.file_id}.jpg"
    
    with open(tmp_file, "wb") as temp_file:
        temp_file.write(image_data)

    try:
        async with TypingIndicator(bot=bot, chat_id=message.chat.id):
            myfile = await asyncio.to_thread(genai.upload_file, tmp_file)
            model = genai.GenerativeModel("gemini-2.0-flash")
            result = await asyncio.to_thread(model.generate_content, [myfile, "\n\n", text])

            if result.text:
                chunks = split_html(telegram_format(result.text))
                for chunk in chunks:
                    await message.reply(chunk, parse_mode="HTML")
                
    except Exception:
        user_language = message.from_user.language_code or DEFAULT_LANGUAGE
        _ = get_localization(user_language)
        await message.reply(_("gpt_gemini_error"))
    finally:
        os.remove(tmp_file)

async def process_gpt(message: Message, command: CommandObject, user_id):
    messagetext = message.reply_to_message.text if message.reply_to_message else ''
    if command.args:
        messagetext += '\n' + command.args

    if not messagetext:
        model = "gpt-4o-mini"
        user_model = db.get(Query().uid == user_id)
        if user_model and user_model["model"] in models:
            model = user_model["model"]

        keyboard = get_gpt_keyboard(model)
        user_language = message.from_user.language_code or DEFAULT_LANGUAGE
        _ = get_localization(user_language)
        await message.reply(_("gpt_help"), reply_markup=keyboard, parse_mode="markdown")
        return

    try:
        proxy = os.getenv("PROXY")
        user_model = db.get(Query().uid == user_id)
        model = user_model["model"] if user_model and user_model["model"] in models else "gpt-4o-mini"

        d = DuckDuckGoChat(model=models[model], proxy=proxy)

        chat_messages, chat_vqd, chat_vqd_hash = load_user_context(user_id)
        if chat_messages is not None and chat_vqd is not None and chat_vqd_hash is not None:
            d.messages = chat_messages
            d.vqd = chat_vqd
            d.vqd_hash = chat_vqd_hash

        async with TypingIndicator(bot=message.bot, chat_id=message.chat.id):
            answer = await asyncio.to_thread(d.chat, messagetext)

        save_user_context(user_id, d.messages, d.vqd, d.vqd_hash)
        answer = process_latex(telegram_format(answer))
        chunks = split_html(answer) 
        
        for chunk in chunks:
            #soup = BeautifulSoup(html.unescape(chunk), "html.parser")
            #fixed = soup.encode(formatter="minimal").decode("utf-8")   
            #try:
            await message.reply(chunk, parse_mode="HTML")
            #except TelegramBadRequest:
                #await message.reply(soup.get_text())
    except Exception as e:
        user_language = message.from_user.language_code or DEFAULT_LANGUAGE
        _ = get_localization(user_language)
        await message.reply(_("gpt_error"), parse_mode="html")


@router.message(Command("gpt", ignore_case=True))
@check_command_enabled("gpt")
async def cmd_gpt(message: Message, command: CommandObject, bot: Bot):
    user_id = message.from_user.id

    photo = message.reply_to_message.photo[-1] if message.reply_to_message and message.reply_to_message.photo else None
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
