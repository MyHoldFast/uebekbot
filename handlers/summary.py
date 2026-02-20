import aiohttp
import asyncio
import os
import re

from utils.typing_indicator import TypingIndicator
from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from utils.command_states import check_command_enabled
from localization import DEFAULT_LANGUAGE, get_localization

router = Router()

GEN_URL = "https://300.ya.ru/api/generation"

class Yandex300API:
    def __init__(self):
        self.session = None
        self.headers = {
            'accept': '*/*',
            'accept-language': 'ru-RU,ru;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://300.ya.ru',
            'referer': 'https://300.ya.ru/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'authorization': f'OAuth {os.getenv("YANDEX_OAUTH_TOKEN")}'
        }
        self.cookies = {
            'Session_id': os.getenv("YANDEX_SESSIONID_COOK"),
            'yp': os.getenv("YANDEX_YP_COOK"),
            'summary-mode': 'short'
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers, cookies=self.cookies)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def toggle_summary_mode(self):
        
        toggle_url = "https://300.ya.ru/summary?/toggle"
        form_data = {"summary-mode": "short"}
        async with self.session.post(toggle_url, data=form_data) as response:
            if response.status != 200:
                raise Exception(f"Failed to toggle summary mode: {response.status}")

    async def post(self, url, data):
        
        await self.toggle_summary_mode() 
        async with self.session.post(url, json=data, timeout=120) as response:
            return await response.json()

async def generate_summary(input_value: str, content_type: str = "text") -> str:
    async with Yandex300API() as api:
        payload = {"text": input_value, "type": content_type} if content_type == "text" else {"video_url": input_value, "type": "video"} if content_type == "video" else {"article_url": input_value, "ignore_cache": False, "type": "article"}
        
        gen_data = await api.post(GEN_URL, payload)
        
        if "message" in gen_data:
            return None

        if gen_data.get('status_code') == 2:
            return await process_summary_data(gen_data, content_type)

        session_id = gen_data['session_id']
        await asyncio.sleep(gen_data['poll_interval_ms'] / 1000)

        first_run = True
        while first_run or gen_data.get('status_code') == 1:
            first_run = False
            payload = {"session_id": session_id, "type": content_type}
            if content_type == "text":
                payload["text"] = input_value
            elif content_type == "video":
                payload["video_url"] = input_value
            else:
                payload["article_url"] = input_value
                payload["ignore_cache"] = False
            
            gen_data = await api.post(GEN_URL, payload)
            await asyncio.sleep(gen_data['poll_interval_ms'] / 1000)

        return await process_summary_data(gen_data, content_type)

async def process_summary_data(data: dict, content_type: str) -> str:
    summary = ""

    if content_type == "text":
        for thesis in data.get('thesis', []):
            summary += f"* {thesis['content']}\n"
    elif content_type == "video":
        for keypoint in data.get('keypoints', []):
            for thesis in keypoint.get('theses', []):
                summary += f"{keypoint['id']}.{thesis['id']}. {thesis['content']}\n"
    else:
        if data.get('have_chapters', False):
            for chapter in data.get('chapters', []):
                summary += f"\n{chapter['id'] + 1}. {chapter['content']}\n"
                for thesis in chapter.get('theses', []):
                    summary += f"   {chapter['id'] + 1}.{thesis['id'] + 1}. {thesis['content']}\n"
        else:
            for thesis in data.get('thesis', []):
                summary += f"{thesis['id'] + 1}. {thesis['content']}\n"

    return summary.strip()

async def process_url(text: str) -> str:
    if not text:    
        user_language = DEFAULT_LANGUAGE
        _ = get_localization(user_language)
        return _("send_link")

    url_patterns = {
        r'https?://(?:www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/\S+': 'video',
        r'https?://[^\s]+': 'article'
    }

    content_type = 'text'
    match_url = None

    for pattern in url_patterns:
        match = re.search(pattern, text)
        if match:
            match_url = match.group()
            content_type = url_patterns[pattern]
            break

    if match_url:
        summary = await generate_summary(match_url, content_type)
        if summary:
            title = ""
            if isinstance(summary, tuple):
                summary, title = summary
            if title:
                summary = f"{title}\n\n{summary}"
            return summary
    
    return await generate_summary(text, 'text')

@router.message(Command("summary", ignore_case=True))
@check_command_enabled("summary")
async def summary(message: Message, command: CommandObject, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    link_preview = None
    text = message.reply_to_message.text if message.reply_to_message else command.args

    if message.reply_to_message:
        link_preview = message.reply_to_message.link_preview_options
        text = message.reply_to_message.caption or message.reply_to_message.text

    if link_preview and link_preview.url:
        text = link_preview.url

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        result = await process_url(text)

        if result:
            is_long = len(result) >= 1000
            wrap_start, wrap_end = ("<blockquote expandable>", "</blockquote>") if is_long else ("", "")
            chunk_length = 4096 - len(wrap_start) - len(wrap_end)

            for i in range(0, len(result), chunk_length):
                chunk = f"{wrap_start}{result[i:i + chunk_length]}{wrap_end}"
                await message.reply(chunk, parse_mode="HTML")
        else:
            await message.reply(_("summary_failed"))
