from aiogram import Router, Bot
from aiogram.types import CallbackQuery
from localization import get_localization, DEFAULT_LANGUAGE
from utils.translate import translate_text

router = Router() 

@router.callback_query(lambda c: c.data and c.data == 'translate')
async def translate_callback(callback_query: CallbackQuery, bot: Bot):
    user_language = callback_query.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    
    original_text = callback_query.message.text
    translated_text = await translate_text(original_text, target_lang=user_language)
    
    await callback_query.message.reply(translated_text)
    await callback_query.answer()

