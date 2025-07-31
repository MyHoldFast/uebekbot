import aiohttp
import asyncio
import os
import subprocess
from io import BytesIO

from utils.typing_indicator import TypingIndicator
from aiogram import Bot, Router, types
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from utils.command_states import check_command_enabled
from localization import DEFAULT_LANGUAGE, get_localization

API_URLS = [
    "https://api-inference.huggingface.co/models/openai/whisper-large-v3-turbo",
    "https://api-inference.huggingface.co/models/openai/whisper-base",
    "https://api-inference.huggingface.co/models/openai/whisper-tiny"
]
headers = {
    "Authorization": "Bearer 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",
    'Content-Type': 'audio/ogg'
}

async def download_as_audio(file_path, output_file):
    token = os.getenv("TG_BOT_TOKEN")
    command = [
        'ffmpeg',
        '-i', f"https://api.telegram.org/file/bot{token}/{file_path}",
        '-vn', '-y',
        '-c:a', 'libvorbis',
        '-b:a', '64k',
        '-fs', '10M',
        output_file
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    await process.communicate()
    if os.path.exists(output_file):
        with open(output_file, 'rb') as f:
            return f.read()
    return b''

async def process_audio(wav_buffer: BytesIO, message, api=0):
    try:
        user_language = message.from_user.language_code or DEFAULT_LANGUAGE
        _ = get_localization(user_language)
        wav_buffer.seek(0)
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URLS[api], headers=headers, data=wav_buffer.getvalue()) as response:
                response_json = await response.json()
                return response_json.get('text', _("voice_error")) 
    except Exception:
        return _("voice_error")

router = Router()

@router.message(Command("stt", ignore_case=True))
@check_command_enabled("stt")
async def stt_command(message: types.Message, bot: Bot, lang: str = None):
    user_language = lang if lang is not None else message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    
    media_message = message.reply_to_message if message.reply_to_message else message
    media = None
    
    if media_message.voice:
        media = media_message.voice
    elif media_message.video:
        media = media_message.video
    elif media_message.video_note:
        media = media_message.video_note
    
    if not media:
        await message.reply(_("voice_help"))
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        file = await bot.get_file(media.file_id)
        content = await download_as_audio(file.file_path, f"tmp/{media.file_id}.ogg")
        audio_bytes = BytesIO(content)

        try:
            transcription = await process_audio(audio_bytes, message)
            
            translate_button = InlineKeyboardButton(
                text=_("translate_button"), 
                callback_data='translate'
            )

            if message.chat.type == ChatType.PRIVATE:        
                query_button = InlineKeyboardButton(
                    text=_("query_button"),
                    callback_data='query'
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[translate_button], [query_button]])
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[translate_button]])
            await message.reply(transcription, reply_markup=keyboard)
        except Exception as e:
            print(f"Error processing audio: {e}")
        
        if os.path.exists(f"tmp/{media.file_id}.ogg"):
            os.remove(f"tmp/{media.file_id}.ogg")
