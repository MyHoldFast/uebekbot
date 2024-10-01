from chatgpt_md_converter import telegram_format   
from aiogram import Router, Bot, html
from aiogram.filters import CommandObject, Command
from aiogram.types import Message, CallbackQuery
from duckduckgo_search import AsyncDDGS
import os
import re
import time
import base64
import json
import asyncio
from pylatexenc.latex2text import LatexNodes2Text
import google.generativeai as genai
from utils.dbmanager import DB
from localization import get_localization, DEFAULT_LANGUAGE 
from keyboards.gpt import get_gpt_keyboard, models

router = Router()
db, Query = DB('db/models.json').get_db()
context_db, ContextQuery = DB('db/user_context.json').get_db()

async def update_model_message(callback_query: CallbackQuery, model: str):
    keyboard = get_gpt_keyboard(model)
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)

def load_user_context(user_id):
    context_item = context_db.get(Query().uid == user_id)
    if context_item:
        last_modified_time = float(context_item.get('last_modified_time', 0))
        current_time = time.time()
        if current_time - last_modified_time < 3 * 3600:
            return json.loads(base64.b64decode(context_item.get('chat_messages')).decode('utf-8')), context_item.get('chat_vqd')
    return None, None

def save_user_context(user_id, chat_messages, chat_vqd):
    getcontext = ContextQuery()
    context_item = context_db.get(getcontext.uid == user_id)
    current_time = time.time()
    encoded_chat_messages = base64.b64encode(json.dumps(chat_messages, ensure_ascii=False).encode('utf-8')).decode('utf-8')

    if context_item:
        context_db.update({
            'uid': user_id,
            'chat_messages': encoded_chat_messages,
            'chat_vqd': chat_vqd,
            'last_modified_time': current_time
        }, getcontext.uid == user_id)        
    else:
        context_db.insert({
            'uid': user_id,
            'chat_messages': encoded_chat_messages,
            'chat_vqd': chat_vqd,
            'last_modified_time': current_time
        })

def remove_user_context(user_id):
    getcontext = ContextQuery()
    context_db.remove(getcontext.uid == user_id)
    
def process_latex(text):
    html_tags = re.findall(r"<.*?>", text)
    placeholders = {f"__HTML_{i}__": tag for i, tag in enumerate(html_tags)}
    
    for placeholder, tag in placeholders.items():
        text = text.replace(tag, placeholder)

    text = LatexNodes2Text().latex_to_text(text)
    
    for placeholder, tag in placeholders.items():
        text = text.replace(placeholder, tag)

    return text

@router.callback_query(lambda c: c.data and c.data in models)
async def callback_query_handler(callback_query: CallbackQuery):
    if callback_query.data in models:
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

@router.message(Command("gpt"))
async def cmd_start(message: Message, command: CommandObject, bot: Bot):
    messagetext = message.reply_to_message.text if message.reply_to_message else command.args
    await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
    user_id = message.from_user.id      
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    photo = None
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    if message.reply_to_message:
        if message.reply_to_message.photo:
            photo = message.reply_to_message.photo[-1]
        elif message.reply_to_message.document:
            if message.reply_to_message.document.mime_type.startswith('image/'):
                photo = message.reply_to_message.document

    if not photo and message.photo:
        photo = message.photo[-1]

    if photo and command.args:
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path
        bytesIO = await bot.download_file(file_path)
        image_data = bytesIO.read()
        with open("tmp/"+photo.file_id+".jpg", "wb") as temp_file:
            temp_file.write(image_data)
        try:
            myfile = await asyncio.to_thread(genai.upload_file, "tmp/" + photo.file_id + ".jpg")
            model = genai.GenerativeModel("gemini-1.5-flash")
            result = await asyncio.to_thread(model.generate_content, [myfile, "\n\n", command.args])
            
            if result.text:
                results.text = telegram_format(result.text)
                for x in range(0, len(result.text), 4000):
                    await message.reply((result.text[x:x + 4000]), parse_mode="HTML")
        except Exception as e:
            await message.reply(_("gpt_gemini_error"))  
        os.remove(f"tmp/"+photo.file_id+".jpg")         
        return   
    
    d = AsyncDDGS()
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    chat_messages, chat_vqd = load_user_context(user_id)
    if chat_messages is not None and chat_vqd is not None:
        d._chat_messages = chat_messages
        d._chat_vqd = chat_vqd

    messagetext = message.reply_to_message.text if message.reply_to_message else command.args
    answer = ""
    model = "gpt-4o-mini"
    try:
        user_model = db.get(Query().uid == user_id)
        if user_model and user_model["model"] in models:
            model = user_model["model"]
        if messagetext:            
            answer = await d.achat(messagetext, model=model)
            save_user_context(user_id, d._chat_messages, d._chat_vqd)
            answer = process_latex(telegram_format(answer))
            #answer = "\n".join(line.strip() for line in answer.splitlines() if line.strip())

            for x in range(0, len(answer), 4000):
                await message.reply((answer[x:x + 4000]), parse_mode="HTML")
        else:
            keyboard = get_gpt_keyboard(model)
            await message.reply(_("gpt_help"), reply_markup=keyboard, parse_mode="markdown")
    except Exception:
        await message.bot.send_chat_action(chat_id=message.chat.id, action='cancel')
        if answer:
            answer = process_latex(answer)
            #answer = "\n".join(line.strip() for line in answer.splitlines() if line.strip())

            for x in range(0, len(answer), 4000):
                await message.reply(html.quote((answer[x:x + 4000])), parse_mode="html")
        else:
            await message.reply(_("gpt_error"), parse_mode="html")

@router.message(Command("gptrm"))
async def cmd_remove_context(message: Message, command: CommandObject):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    remove_user_context(message.from_user.id)
    await message.reply(_("gpt_ctx_removed"), parse_mode="markdown")
