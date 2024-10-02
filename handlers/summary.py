import aiohttp, httpx
import asyncio
import os
import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bs4 import BeautifulSoup

from localization import DEFAULT_LANGUAGE, LANGUAGES, get_localization
from utils.translate import translate_text

router = Router()

gen_url = "https://300.ya.ru/api/generation"

async def fetch(session, url, data):
    async with session.post(url, json=data, headers=
        {'Authorization': f'OAuth {os.getenv("YANDEX_OAUTH_TOKEN")}'}, 
        cookies={'Session_id': os.getenv("YANDEX_SESSIONID_COOK"),
        'yp': os.getenv("YANDEX_YP_COOK")}) as response:
        return await response.json() 

async def summarize(input_value: str, is_text=False) -> str:
    sum = ''
    async with aiohttp.ClientSession() as session:
        params = {"text": input_value, "type": "text"} if is_text else {"video_url": input_value, "type": "video"}
        gen_start_json = await fetch(session, gen_url, params)

    if "message" in gen_start_json:
        return

    ya300_session_id = gen_start_json['session_id']
    await asyncio.sleep(gen_start_json['poll_interval_ms'] / 1000)

    gen_data = {}
    first_run = True

    while first_run or gen_data.get('status_code') == 1:
        first_run = False
        async with aiohttp.ClientSession() as session:
            params = {"session_id": ya300_session_id, "text": input_value, "type": "text"} if is_text else {"session_id": ya300_session_id, "video_url": input_value, "type": "video"}
            gen_data = await fetch(session, gen_url, params)

        interval = gen_data['poll_interval_ms']
        await asyncio.sleep(interval / 1000)

    if is_text:
        keypoints = gen_data.get('thesis', [])
    else:
        keypoints = gen_data.get('keypoints', [])

    for keypoint in keypoints:
        if is_text:
            sum += f"* {keypoint['content']}\n"
        else:
            for thesis in keypoint['theses']:
                sum += f"{keypoint['id']}.{thesis['id']}. {thesis['content']}\n"
    return sum

async def send_yandex_api(link):
    endpoint = "https://300.ya.ru/api/sharing-url"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint,
            json={"article_url": f"{link}"},
            headers={"Authorization": f'OAuth {os.getenv("YANDEX_OAUTH_TOKEN")}'},
        ) as response:
            data = await response.json()
            return data.get("sharing_url")

async def read_url(target):
    final_url = await send_yandex_api(target)
    title = ''
    description = ''
    headers = {
        'DNT': '1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

    if final_url:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(final_url, headers=headers)
            
            if response.status_code == 200:
                response.encoding = 'utf-8'
                soup = BeautifulSoup(response.text, "html.parser")
                og_title_tag = soup.find("meta", attrs={"property": "og:title"})
                if og_title_tag:
                    title = og_title_tag["content"]
                og_description_tag = soup.find("meta", attrs={"name": "description"})
                if og_description_tag:
                    description = og_description_tag.get("content")
                return (title + "\n\n" + description).replace(" - Пересказ YandexGPT", "")
    
    return None


async def parse_url(text):    
    if text==None:
        return _("send_link") # type: ignore
    result = ""
    matched = False

    regexes = [
        (r'https?://(?:www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/\S+', summarize),
        (r'https?://(?:www\.)?(?:[a-zA-Zа-яА-Я]{2,}\.)?(?:m\.)?wikipedia\.\w{2,}/wiki/[^\s]+', read_url),
        (r'https?://(?:www\.)?habr\.\w{2,}/\S+', read_url)
    ]


    for regex, func in regexes:
        match = re.search(regex, text)
        if match:
            matched = True
            link = match.group()
            func_result = await func(link)
            if func_result is not None: 
                result += "\n\n" + func_result

    if not matched:
        
        if(text=='/summary'): result = _("send_link") # type: ignore
        else: result = await summarize(text, True)

    return result

@router.message(Command("summary"))
async def summary(message: Message):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    link_preview = None
    text = message.text
    
    if message.reply_to_message:
        link_preview = message.reply_to_message.link_preview_options
        text = message.reply_to_message.caption or message.reply_to_message.text
     
    await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
    if link_preview and link_preview.url: text = link_preview.url
    result = await parse_url(text)
    
    if result:
        if user_language and user_language != "ru" and user_language in LANGUAGES:
            result = await translate_text([result], "ru", user_language) or result 
        for x in range(0, len(result), 4096):
            await message.reply(result[x:x + 4096])
    else:
        await message.reply(_("summary_failed"))
