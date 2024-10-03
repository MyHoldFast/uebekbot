import aiohttp
import asyncio
import json
import os
from datetime import datetime
from functools import wraps
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
from utils.StatsMiddleware import get_stats, cmds

router = Router()
start_time = datetime.now()

async def login_yandex(login, password, url):
    cookie_jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        data = {'login': login, 'passwd': password}
        async with session.post(url, data=data, allow_redirects=True) as response:
            if response.status == 200:
                return {cookie.key: cookie.value for cookie in cookie_jar if cookie.key in {'Session_id', 'yp'}}
    return None

async def fetch_with_cookies(url, cookies):
    cookie_jar = aiohttp.CookieJar()
    for key, value in cookies.items():
        cookie_jar.update_cookies({key: value})

    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        async with session.get(url) as response:
            if response.status == 200:
                return {cookie.key: cookie.value for cookie in cookie_jar}
    return None

async def get_cookies():
    urls = [
        ("https://passport.ya.ru/auth?retpath=https://300.ya.ru/?nr=1", "RU"),
        ("https://passport.yandex.kz/auth", "KZ")
    ]
    results = await asyncio.gather(*[login_yandex(os.getenv('YA_LOGIN'), os.getenv('YA_PASSWORD'), url) for url, _ in urls])
    cookies = {region: result or {} for result, (_, region) in zip(results, urls)}
    
    return cookies['RU'], cookies['KZ']

def update_environment_cookies(cookies):
    if "KZ" in cookies and "RU" in cookies:
        kz_cookies = cookies["KZ"]
        ru_cookies = cookies["RU"]
        
        if "Session_id" in kz_cookies:
            os.environ["YANDEXKZ_SESSIONID_COOK"] = kz_cookies["Session_id"]
        
        #if "yp" in kz_cookies:
        #    os.environ["YANDEX_YP_COOK"] = kz_cookies["yp"]
        
        if "Session_id" in ru_cookies:
            os.environ["YANDEX_SESSIONID_COOK"] = ru_cookies["Session_id"]
        
        if "yp" in ru_cookies:
            os.environ["YANDEX_YP_COOK"] = ru_cookies["yp"]

def admin_only(func):
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if str(message.from_user.id) != os.getenv("ADMIN_ID"):
            return
        return await func(message, *args, **kwargs)
    return wrapper

@router.message(Command("uptime"))
@admin_only
async def cmd_uptime(message: Message):
    now = datetime.now()
    uptime = now - start_time
    days = uptime.days
    hours = (uptime.total_seconds() // 3600) % 24
    minutes = (uptime.total_seconds() // 60) % 60
    await message.answer(f"Uptime: {days} days, {int(hours)} hours, {int(minutes)} minutes")

@router.message(Command("stop"))
@admin_only
async def cmd_stop(message: Message):
    os._exit(0)

@router.message(Command("stats"))
@admin_only
async def stats(message: Message):
    date, stats, total_stats = get_stats()
    #if date:
    message_text = f"Дата: {date}\n" + "\n".join(f"{cmd}: {stats.get(cmd, 0)}" for cmd in cmds)
    #else:
    #    message_text = "Статистика за сегодня пуста."
    
    message_text += "\n\nОбщая статистика:\n" + "\n".join(f"{cmd}: {total_stats[cmd]}" for cmd in cmds)
    
    await message.answer(message_text)

@router.message(Command("update_cookie"))
@admin_only
async def update_cookie(message: Message, bot: Bot):
    ru_cookies, kz_cookies = await get_cookies()    
    update_environment_cookies({"RU": ru_cookies, "KZ": kz_cookies})

    output = {
        "KZ": kz_cookies,
        "RU": ru_cookies
    }

    await bot.send_message(chat_id=os.getenv("ADMIN_ID"), text=f"Куки обновлены: {json.dumps(output, indent=4)}")
    await message.answer(f"Куки обновлены.")
