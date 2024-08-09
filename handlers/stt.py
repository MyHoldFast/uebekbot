import io
import asyncio
from aiogram import Bot, types
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp
import time, random
from io import BytesIO
from localization import get_localization, DEFAULT_LANGUAGE

API_URLS = ["https://api-inference.huggingface.co/models/openai/whisper-medium", "https://api-inference.huggingface.co/models/openai/whisper-base", "https://api-inference.huggingface.co/models/openai/whisper-tiny"]
headers = {"Authorization": "Bearer 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"}



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

@router.message(Command(commands=["stt"]))
async def tts_command(message: types.Message, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    if not message.reply_to_message or not message.reply_to_message.voice:
        await message.reply(_("voice_help"))
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
    voice = message.reply_to_message.voice
    file_id = voice.file_id
    
    file = await bot.get_file(file_id)
    file_path = file.file_path
    audio_file = await bot.download_file(file_path)
    
    audio_bytes = io.BytesIO()
    audio_bytes.write(audio_file.getvalue())
    audio_bytes.seek(0)
    api = 0
    if voice.duration > 180:
        api = 2
    elif voice.duration > 120:
        api = 1
    #print(API_URLS[api])
    transcription = await process_audio(audio_bytes, message, api)
    
    # Create an inline button for translation
    translate_button = InlineKeyboardButton(
        text=_("translate_button"), 
        callback_data='translate'
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[translate_button]])
    
    await message.reply(transcription, reply_markup=keyboard)

