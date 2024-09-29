from aiogram import Router, Bot
from aiogram.filters import CommandObject, Command
from aiogram.types import Message
import aiohttp
import asyncio
import re, os
from chatgpt_md_converter import telegram_format 
from dotenv import load_dotenv
from utils.translate import translate_text
from localization import get_localization, DEFAULT_LANGUAGE, LANGUAGES


load_dotenv()
router = Router() 

headers = {
     'cookie': f'Session_id={os.getenv("YANDEXKZ_SESSIONID_COOK")}'
}

async def fetch_fresh_message(session, response_message_id):
    url = 'https://yandex.kz/neuralsearch/api/get_fresh_message?lr='
    data = {"ResponseMessageId": response_message_id}

    while True:
        async with session.post(url, headers=headers, json=data) as res:
            result = await res.json()
            if result.get('IsCompleteResults'):
                return re.sub(r'\[\`\`\`\d+\`\`\`\]\(.*?\)', '', result.get('TargetMarkdownText'))
            await asyncio.sleep(result.get('RetryRecommendationMs', 1000) / 1000)

async def send_request(user_request):
    url = 'https://yandex.kz/neuralsearch/api/send_to_dialog?lr='
    data = {"UserRequest": user_request}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as res:
            try:
                response = await res.json()
                submissions_left, response_message_id = response['ResponseStatus']['LimitsInfo']['SubmissionsLeft'], response['ResponseMessageId']

                if submissions_left == 0:
                    return("Количество запросов в час ограничено.")
            
                return await fetch_fresh_message(session, response_message_id)
            except: return "Произошла ошибка, попробуйте позднее"

@router.message(Command("neuro"))
async def neuro(message: Message, command: CommandObject, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    messagetext = message.reply_to_message.text if message.reply_to_message else command.args 
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE    
    await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
    if messagetext:
        result = (await send_request(messagetext))
        if user_language and user_language != "ru" and user_language in LANGUAGES:
            result = await translate_text([result], "ru", user_language) or result
        await message.reply(telegram_format(result), parse_mode="HTML")
    else:
         await message.reply(_('neuro_help'))