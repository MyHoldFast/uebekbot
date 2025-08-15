import aiohttp
import asyncio
import re

from utils.typing_indicator import TypingIndicator
from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from utils.command_states import check_command_enabled

from chatgpt_md_converter import telegram_format
from localization import DEFAULT_LANGUAGE, get_localization
#from utils.translate import translate_text

router = Router() 

async def fetch_fresh_message(session, response_message_id):
    url = 'https://yandex.kz/neuralsearch/api/get_fresh_message?lr='
    data = {"ResponseMessageId": response_message_id}

    while True:
        async with session.post(url,  json=data) as res:
            result = await res.json()
            if result.get('IsCompleteResults'):
                return re.sub(r'\[\`\`\`\d+\`\`\`\]\(.*?\)', '', result.get('TargetMarkdownText'))
            await asyncio.sleep(result.get('RetryRecommendationMs', 1000) / 1000)

async def send_request(user_request):
    url = 'https://yandex.kz/neuralsearch/api/send_to_dialog?lr='
    data = {"UserRequest": user_request}

    async with aiohttp.ClientSession() as session:
        async with session.post(url,  json=data) as res:
            try:
                response = await res.json()
                submissions_left, response_message_id = response['ResponseStatus']['LimitsInfo']['SubmissionsLeft'], response['ResponseMessageId']

                if submissions_left == 0:
                    return("Количество запросов в час ограничено.")
            
                return await fetch_fresh_message(session, response_message_id)
            except: return "Произошла ошибка, попробуйте позднее"

@router.message(Command("neuro", ignore_case=True))
@check_command_enabled("neuro")
async def neuro(message: Message, command: CommandObject, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if message.reply_to_message:
        user_input = message.reply_to_message.text or message.reply_to_message.caption or ""
        if command.args:
            user_input += '\n' + command.args
    else:
        user_input = command.args if command.args else ""

    if user_input:
        async with TypingIndicator(bot=bot, chat_id=message.chat.id):
            result = await send_request(user_input)
            #if user_language and user_language != "ru" and user_language in LANGUAGES:
                #result = await translate_text([result], "ru", user_language) or result
            await message.reply(telegram_format(result), parse_mode="HTML")
    else:
        await message.reply(_('neuro_help'))