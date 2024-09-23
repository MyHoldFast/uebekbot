from chatgpt_md_converter import telegram_format 
from aiogram import Router, Bot
from aiogram import html
from aiogram.filters import CommandObject, Command
from aiogram.types import Message, CallbackQuery
from duckduckgo_search import AsyncDDGS
import pickle
import os
import time
import gzip
import google.generativeai as genai
from tinydb import Query, TinyDB
from dotenv import load_dotenv
from localization import get_localization, DEFAULT_LANGUAGE 
from keyboards.gpt import get_gpt_keyboard, models

load_dotenv()

router = Router()
db = TinyDB('db/models.json')
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

async def update_model_message(callback_query: CallbackQuery, model: str):
    keyboard = get_gpt_keyboard(model)
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)

def load_user_context(user_id):
    file_path = f'db/{user_id}.pcl.gz'
    if os.path.exists(file_path):
        last_modified_time = os.path.getmtime(file_path)
        current_time = time.time()
        # Проверяем, прошло ли меньше 3 часов (3 часа = 3 * 3600 секунд)
        if current_time - last_modified_time < 3 * 3600:
            with gzip.open(file_path, 'rb') as file:
                return pickle.load(file)
    return None, None

def save_user_context(user_id, context):
    file_path = f'db/{user_id}.pcl.gz'
    with gzip.open(file_path, 'wb') as file:
        pickle.dump(context, file)

def remove_user_context(user_id):
    file_path = f'db/{user_id}.pcl.gz'
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False

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
        myfile = genai.upload_file("tmp/"+photo.file_id+".jpg")
        os.remove(f"tmp/"+photo.file_id+".jpg")
        model = genai.GenerativeModel("gemini-1.5-flash")
        result = model.generate_content(
            [myfile, "\n\n", command.args]
        )
        if result.text:
            await message.reply(result.text, parse_mode="html")
        return   

    d = AsyncDDGS()
    chat_messages, chat_vqd = load_user_context(user_id)
    if chat_messages is not None and chat_vqd is not None:
        d._chat_messages = chat_messages
        d._chat_vqd = chat_vqd
    
    answer = ""
    default = "gpt-4o-mini"
    model = default
    try:
        user_model = db.get(Query().uid == user_id)
        if user_model and user_model["model"] in models:
            model = user_model["model"]
        if messagetext:            
            answer = await d.achat(messagetext, model=model)
            save_user_context(user_id, (d._chat_messages, d._chat_vqd))

            for x in range(0, len(answer), 4000):
                await message.reply(telegram_format(answer[x:x + 4000]), parse_mode="HTML")
        else:
            keyboard = get_gpt_keyboard(model)
            await message.reply(_("gpt_help"), reply_markup=keyboard, parse_mode="markdown")
    except Exception as e:
        #print(e)
        await message.bot.send_chat_action(chat_id=message.chat.id, action='cancel')
        if answer:
            for x in range(0, len(answer), 4000):
                await message.reply(html.quote(answer[x:x + 4000]), parse_mode="html")
        else:
            await message.reply(_("gpt_error"), parse_mode="html")

@router.message(Command("gptrm"))
async def cmd_remove_context(message: Message, command: CommandObject):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if remove_user_context(message.from_user.id):
        await message.reply(_("gpt_ctx_removed"), parse_mode="markdown")
    else:
        await message.reply(_("gpt_ctx_not_found"), parse_mode="markdown")