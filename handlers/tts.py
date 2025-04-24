import os
import tempfile
import asyncio
import fasttext
from utils.typing_indicator import TypingIndicator
from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile
from utils.command_states import check_command_enabled
from localization import get_localization, DEFAULT_LANGUAGE
import edge_tts

router = Router()

FASTTEXT_MODEL_PATH = "trained_models/lid.176.bin"
model = fasttext.load_model(FASTTEXT_MODEL_PATH)

VOICES = {
    "ru": ["ru-RU-SvetlanaNeural"],
    "en": ["en-US-JennyNeural"],
    "fr": ["fr-FR-EloiseNeural"],
    "es": ["es-ES-ElviraNeural"],
    "de": ["de-DE-KatjaNeural"],
    "it": ["it-IT-IsabellaNeural"],
    "zh": ["zh-CN-XiaoxiaoNeural"],
    "uk": ["uk-UA-PolinaNeural"]
}

DEFAULT_VOICE_LANG = "en"

async def async_run_ffmpeg(input_path: str, output_path: str):
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-loglevel", "quiet",
        "-acodec", "libopus",
        "-ar", "24000",
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()

@router.message(Command("tts", ignore_case=True))
@check_command_enabled("tts")
async def cmd_tts(message: Message, command: CommandObject, bot: Bot):
    if message.reply_to_message:
        user_input = (
            message.reply_to_message.text or message.reply_to_message.caption or ""
        )
        if command.args:
            user_input += "\n" + command.args
    else:
        user_input = command.args if command.args else ""

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input:
        await message.reply(_("tts_help"), parse_mode='Markdown')
        return

    try:
        predictions = model.predict(user_input.replace("\n", " ").lower(), k=1)
        detected_lang = predictions[0][0].replace("__label__", "")
    except Exception as e:
        print(e)
        detected_lang = DEFAULT_VOICE_LANG

    if detected_lang not in VOICES:
        detected_lang = DEFAULT_VOICE_LANG

    available_voices = VOICES.get(detected_lang, VOICES[DEFAULT_VOICE_LANG])
    voice = available_voices[0]

    try:
        async with TypingIndicator(bot=message.bot, chat_id=message.chat.id):
            communicate = edge_tts.Communicate(user_input, voice)

            tmp_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            mp3_path = tmp_mp3.name
            tmp_mp3.close()
            ogg_path = mp3_path.replace(".mp3", ".ogg")

            await communicate.save(mp3_path)
            await async_run_ffmpeg(mp3_path, ogg_path)

            voice_file = FSInputFile(ogg_path)
            await message.reply_voice(voice=voice_file)

    except Exception as e:
        await message.reply(_("tts_error"))

    finally:
        for f in (mp3_path, ogg_path):
            if os.path.exists(f):
                os.remove(f)