import asyncio
import os
import subprocess

from aiogram import Bot, Router, types
from aiogram.filters import Command
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from localization import DEFAULT_LANGUAGE, get_localization
from shazamio import Shazam
from bs4 import BeautifulSoup
import httpx

router = Router()

async def download_audio(file_path: str, file_id: str) -> str:
    token = os.getenv("TG_BOT_TOKEN")
    TMP_DIR = "tmp"
    os.makedirs(TMP_DIR, exist_ok=True)
    output_file = f"{TMP_DIR}/{file_id}.ogg"
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
        return output_file
    raise Exception("Ошибка при конвертации аудио")

async def recognize_song(file_path: str) -> dict:
    shazam = Shazam()
    try:
        result = await shazam.recognize(file_path)
        return result.get('track')
    except Exception as e:
        #print(f"❌ Ошибка при распознавании трека: {e}")
        return {}

async def get_localized_artist_name(url: str) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",\
        "Range": "bytes=0-10000"
    }
    localized_url = url.replace("www.shazam.com/track", "www.shazam.com/ru-ru/track")

    async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
        try:
            response = await client.get(localized_url, headers=headers)
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError):
            return None

    soup = BeautifulSoup(response.text, 'html.parser')

    if meta_tag := soup.find("meta", {"itemprop": "name"}):
        if artist := meta_tag.get("content"):
            return artist

    if artist_tag := soup.find("a", {"data-test-id": "track_userevent_top-tracks_artistName"}):
        if artist := artist_tag.get("aria-label"):
            return artist

    return None

@router.message(Command("shazam", ignore_case=True))
@check_command_enabled("shazam")
async def shazam_command(message: types.Message, bot: Bot, lang: str = None):
    user_language = lang if lang is not None else message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    media_message = message.reply_to_message if message.reply_to_message else message
    media = None

    if media_message.voice:
        media = media_message.voice
    elif media_message.audio:
        media = media_message.audio
    elif media_message.video:
        media = media_message.video
    elif media_message.video_note:
        media = media_message.video_note
    elif media_message.document and media_message.document.mime_type in ["audio/ogg", "audio/mpeg"]:
        media = media_message.document

    if not media:
        await message.reply(_("shazam_help"))  # Добавьте в локализацию фразу подсказки
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        file = await bot.get_file(media.file_id)
        audio_path = await download_audio(file.file_path, media.file_id)

        track = await recognize_song(audio_path)

        if not track:
            await message.reply(_("shazam_not_found"))
            os.remove(audio_path)
            return

        title = track.get('title', 'Неизвестная песня')
        subtitle = track.get('subtitle', 'Неизвестный исполнитель')
        shazam_url = track.get('url')

        if shazam_url:
            localized_artist = await get_localized_artist_name(shazam_url)
            if localized_artist:
                subtitle = localized_artist

        result_text = f"🎵 `{subtitle} - {title}`"

        await message.reply(result_text, parse_mode="Markdown")
        if os.path.exists(audio_path):
            os.remove(audio_path)