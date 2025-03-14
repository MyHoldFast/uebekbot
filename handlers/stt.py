import aiohttp
import asyncio
import os
import random
import subprocess
import time
from io import BytesIO

from utils.typing_indicator import TypingIndicator
from aiogram import Bot, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from utils.command_states import check_command_enabled

from localization import DEFAULT_LANGUAGE, get_localization

API_URLS = ["https://api-inference.huggingface.co/models/openai/whisper-large-v3-turbo", "https://api-inference.huggingface.co/models/openai/whisper-base", "https://api-inference.huggingface.co/models/openai/whisper-tiny"]
headers = {"Authorization": "Bearer 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"}

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
    stdout, stderr = await process.communicate()
    chunk = []
    if process.returncode != 0:
        print(f"Error during conversion: {stderr.decode()}")
    else:
        with open(output_file, 'rb') as f:
            return f.read()
    return chunk



async def process_audio(wav_buffer: BytesIO, message, api=0):
    wav_buffer.seek(0)
    
    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        
        while True:
            # Generate a small random chunk of bytes to send as dummy data
            random_data = BytesIO(bytes([random.randint(0, 255) for _ in range(10)]))
            random_data.seek(0)
            
            async with session.post(API_URLS[api], headers=headers, data=random_data.getvalue()) as response:
                response_json = await response.json()
                #print(API_URLS[api])
                #elapsed_time = time.time() - start_time
                
                if 'error' in response_json:
                    if 'estimated_time' in response_json:
                        #print(f"Ошибка: {response_json['error']}. Ожидание {response_json['estimated_time']} секунд.")
                        await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
                        await asyncio.sleep(3)
                    elif response_json.get('error') == "Internal Server Error" and api!=2:
                        api = 2
                        await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
                        #await asyncio.sleep(1)
                    else: break
                else:
                    break
        
        # Send the actual wav_buffer after the server is ready
        async with session.post(API_URLS[api], headers=headers, data=wav_buffer.getvalue()) as response:
            response_json = await response.json()
            #print(response_json)
            text = response_json.get('text', _("voice_error")) # type: ignore
            return text

router = Router()

@router.message(Command("stt", ignore_case=True))
@check_command_enabled("stt")
async def stt_command(message: types.Message, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not message.reply_to_message or (not message.reply_to_message.voice and not message.reply_to_message.video and not message.reply_to_message.video_note):
        await message.reply(_("voice_help"))
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        if message.reply_to_message.voice:
            voice = message.reply_to_message.voice
            file_id = voice.file_id
            duration = voice.duration
        if message.reply_to_message.video:
            video = message.reply_to_message.video
            file_id = video.file_id
            duration = video.duration
        if message.reply_to_message.video_note:
            video = message.reply_to_message.video_note
            file_id = video.file_id
            duration = video.duration

        file = await bot.get_file(file_id)
        file_path = file.file_path

        content = await download_as_audio(file_path, f"tmp/{file_id}.ogg")
        audio_bytes = BytesIO(content)
        api = 0
        #if duration > 180:
        #    api = 2
        #elif duration > 120:
        #    api = 1
        #print(API_URLS[api])
        transcription = await process_audio(audio_bytes, message, api)

        translate_button = InlineKeyboardButton(
            text=_("translate_button"), 
            callback_data='translate'
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[translate_button]])

        await message.reply(transcription, reply_markup=keyboard)
        os.remove(f"tmp/{file_id}.ogg")