import aiohttp, httpx
import asyncio
import os
import re

from utils.typing_indicator import TypingIndicator
from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import CallbackQuery
from bs4 import BeautifulSoup
from utils.command_states import check_command_enabled

from localization import DEFAULT_LANGUAGE, LANGUAGES, get_localization
#from utils.translate import translate_text

router = Router()

gen_url = "https://300.ya.ru/api/generation"

async def fetch_data(session, url, data):
    async with session.post(url, json=data, timeout=120, headers={
        'Authorization': f'OAuth {os.getenv("YANDEX_OAUTH_TOKEN")}'}, 
        cookies={'Session_id': os.getenv("YANDEX_SESSIONID_COOK"),
        'yp': os.getenv("YANDEX_YP_COOK")}) as response:
        return await response.json()

async def generate_summary(input_value: str, is_text=False) -> str:
    summary = ''
    try:
        async with aiohttp.ClientSession() as session:
            params = {"text": input_value, "type": "text"} if is_text else {"video_url": input_value, "type": "video"}
            gen_start_json = await fetch_data(session, gen_url, params)

        if "message" in gen_start_json:
            return None

        session_id = gen_start_json['session_id']
        await asyncio.sleep(gen_start_json['poll_interval_ms'] / 1000)

        gen_data = {}
        first_run = True

        while first_run or gen_data.get('status_code') == 1:
            first_run = False
            async with aiohttp.ClientSession() as session:
                params = {"session_id": session_id, "text": input_value, "type": "text"} if is_text else {"session_id": session_id, "video_url": input_value, "type": "video"}
                gen_data = await fetch_data(session, gen_url, params)

            interval = gen_data['poll_interval_ms']
            await asyncio.sleep(interval / 1000)

        keypoints = gen_data.get('thesis', []) if is_text else gen_data.get('keypoints', [])

        for keypoint in keypoints:
            if is_text:
                summary += f"* {keypoint['content']}\n"
            else:
                for thesis in keypoint['theses']:
                    summary += f"{keypoint['id']}.{thesis['id']}. {thesis['content']}\n"
        return summary
    except Exception as e:
        print(f"Error: {e}")
        return None

async def fetch_sharing_url(link):
    endpoint = "https://300.ya.ru/api/sharing-url"
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, timeout=120, json={"article_url": f"{link}"}, headers={"Authorization": f'OAuth {os.getenv("YANDEX_OAUTH_TOKEN")}'}) as response:
            data = await response.json()
            return data.get("sharing_url")

async def extract_url_info(target):
    final_url = await fetch_sharing_url(target)
    title, description, identifier = '', '', None

    headers = {
        'DNT': '1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

    if final_url:
        identifier_match = re.search(r'https://300\.ya\.ru/([a-zA-Z0-9]+)', final_url)
        if identifier_match:
            identifier = identifier_match.group(1)

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
                content = (title + "\n\n" + description).replace(" - Пересказ YandexGPT", "")
                return content, identifier

    return None, None

async def process_url(text):
    if not text:    
        return _("send_link"), None # type: ignore

    result = ""
    button_callback = None

    regexes = [
        (r'https?://(?:www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/\S+', generate_summary),
        (r'https?://(?:www\.)?(?:[a-zA-Zа-яА-Я]{2,}\.)?(?:m\.)?wikipedia\.\w{2,}/wiki/[^\s]+', extract_url_info),
        (r'https?://(?:www\.)?habr\.\w{2,}/\S+', extract_url_info)
    ]

    for regex, func in regexes:
        match = re.search(regex, text)
        if match:
            link = match.group()
            if func == extract_url_info:
                func_result, button_callback = await func(link)
            else:
                func_result = await func(link)
            if func_result:
                result += "\n\n" + func_result
            break

    if not result:
        #if text.startswith('/summary'):
        #   return _("send_link"), None # type: ignore
        match = re.search(r'(https?://[^\s]+)', text)
        if match:
            result, button_callback = await extract_url_info(match.group(0))
        else:
            result = await generate_summary(text, True)

    return result, button_callback

@router.callback_query(lambda c: c.data.startswith("link:"))
async def handle_details_callback(callback: CallbackQuery):
    identifier = callback.data[5:]
    target_url = f"https://300.ya.ru/{identifier}/"
    detailed_summary = await fetch_detailed_summary(target_url)
    user_language = callback.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if detailed_summary:
        #if user_language and user_language != "ru" and user_language in LANGUAGES:
        #   detailed_summary = await translate_text([detailed_summary], "ru", user_language) or detailed_summary 
        for x in range(0, len(detailed_summary), 4096):
            await callback.message.reply(detailed_summary[x:x + 4096])
    else:
        await callback.message.reply(_("summary_detail_failed"))
    await callback.answer()

async def fetch_detailed_summary(final_url: str):
    #print(final_url)
    headers = {
        "accept": "application/json",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "content-type": "application/x-www-form-urlencoded",
        "sec-ch-ua": "\"Google Chrome\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "referrer": final_url,
    }

    data = {
        "summary-mode": "detailed"
    }

    cookies = {
        "summary-mode": "detailed"
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        toggle_response = await client.post(final_url + "?/toggle", headers=headers, data=data, cookies=cookies, timeout=120)

        if toggle_response.status_code != 200:
            return None

        response = await client.get(final_url, headers=headers, cookies=cookies, timeout=120)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, "html.parser")
            summary_div = soup.find("div", class_="summary-text")
            if not summary_div:
                return None

            results = []
            seen_headings = set()
            seen_texts = set()

            for h2 in summary_div.find_all("h2"):
                h2_text = h2.get_text(strip=True)
                if h2_text not in seen_headings:
                    results.append(f"\n- {h2_text}")
                    seen_headings.add(h2_text)

                span_texts = []
                for span in h2.find_all_next("span", class_="text-wrapper"):
                    span_text = span.get_text(strip=True)
                    if span.find_previous("h2") != h2:
                        break
                    if span_text not in seen_texts:
                        span_texts.append(span_text)
                        seen_texts.add(span_text)
                
                for text in span_texts:
                    results.append(f"  {text}")

            return "\n".join(results)

    return None

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
        result, button_callback = await process_url(text)

        if result:
            #if user_language and user_language != "ru" and user_language in LANGUAGES:
            #    result = await translate_text([result], "ru", user_language) or result 

            keyboard = None
            if button_callback:
                details_button = InlineKeyboardButton(text=_("summary_detail"), callback_data='link:'+button_callback)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[details_button]])

            for x in range(0, len(result), 4096):
                await message.reply(result[x:x + 4096], reply_markup=keyboard if x == 0 else None)
        else:
            await message.reply(_("summary_failed"))
