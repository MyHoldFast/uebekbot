from aiogram import Router, Bot
from aiogram.types import CallbackQuery
from aiogram.filters import CommandObject
from aiogram.exceptions import TelegramBadRequest
from localization import get_localization, DEFAULT_LANGUAGE
from utils.translate import translate_text
from handlers.stt import stt_command
from handlers.shazam import shazam_command
from utils.StatsMiddleware import save_stats
#from handlers.gpt import process_gpt
from handlers.qwen import cmd_qwen
from datetime import datetime, timedelta
from functools import wraps

router = Router() 

user_cooldowns = {}

def throttle(seconds: int = 5):
    def decorator(func):
        @wraps(func)
        async def wrapper(callback_query: CallbackQuery, *args, **kwargs):
            user_id = callback_query.from_user.id
            user_language = callback_query.from_user.language_code or DEFAULT_LANGUAGE
            _ = get_localization(user_language)
            current_time = datetime.now()            
            last_request_time = user_cooldowns.get(user_id)
            if last_request_time and (current_time - last_request_time) < timedelta(seconds=seconds):
                await callback_query.answer(_("throttle_wait").format(seconds=seconds), show_alert=True)
                return
            
            user_cooldowns[user_id] = current_time
            return await func(callback_query, *args, **kwargs)
        return wrapper
    return decorator

@router.callback_query(lambda c: c.data == 'translate')
@throttle(seconds=5) 
async def translate_callback(callback_query: CallbackQuery, bot: Bot):
    user_language = callback_query.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    
    original_text = callback_query.message.text
    translated_text = await translate_text(original_text, target_lang=user_language)
    
    await callback_query.message.reply(translated_text)
    await callback_query.answer()

@router.callback_query(lambda c: c.data == 'stt_button')
@throttle(seconds=5)
async def stt_callback(callback_query: CallbackQuery, bot: Bot):
    await callback_query.answer()
    message = await callback_query.message.reply("⏳")  
    await stt_command(callback_query.message, bot, lang=callback_query.from_user.language_code)
    await safe_delete(message)
    save_stats('/stt')


@router.callback_query(lambda c: c.data == 'shazam_button')
@throttle(seconds=5)
async def shazam_callback(callback_query: CallbackQuery, bot: Bot): 
    await callback_query.answer()   
    message = await callback_query.message.reply("⏳")  
    await shazam_command(callback_query.message, bot, lang=callback_query.from_user.language_code)
    await safe_delete(message)
    save_stats('/shazam')

# @router.callback_query(lambda c: c.data == 'query_button')
# @throttle(seconds=5)
# async def query_callback(callback_query: CallbackQuery, bot: Bot):
#     await callback_query.message.reply('query')
#     await callback_query.answer()

@router.callback_query(lambda c: c.data == 'query')
@throttle(seconds=5)
async def query_callback(callback_query: CallbackQuery, bot: Bot):
    await callback_query.answer()
    user_language = callback_query.from_user.language_code or DEFAULT_LANGUAGE
    message = await callback_query.message.reply("⏳")
    original_text = callback_query.message.text
    command = CommandObject(command=None, args=original_text) 
    await cmd_qwen(callback_query.message, command, bot, id=callback_query.from_user.id, lang=user_language)  
    #await process_gpt(callback_query.message, command, callback_query.from_user.id)
    await safe_delete(message)
    save_stats('/qwen')

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass



