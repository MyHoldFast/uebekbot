import aiohttp
import httpx
import json
import os
from datetime import datetime
from functools import wraps
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.filters.command import CommandObject 
from aiogram.types import Message
from utils.StatsMiddleware import get_stats, cmds

router = Router()
start_time = datetime.now()

async def login_yandex_ru(login, password, url):
    cookie_jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        data = {'login': login, 'passwd': password}
        async with session.post(url, data=data, allow_redirects=True) as response:
            if response.status == 200:
                return {cookie.key: cookie.value for cookie in cookie_jar if cookie.key in {'Session_id', 'yp'}}
    return None

async def login_yandex_kz(login, password, url):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        data = {'login': login, 'passwd': password}
        response = await client.post(url, data=data)
        if response.status_code == 200:
            cookie_jar = client.cookies.jar
            return {cookie.name: cookie.value for cookie in cookie_jar if cookie.name in {'Session_id', 'yp'}}
    return None

async def get_cookies():
    urls = [
        ("https://passport.ya.ru/auth?retpath=https://300.ya.ru/?nr=1", "RU"),
        ("https://passport.yandex.kz/auth", "KZ")
    ]

    ru_cookies = await login_yandex_ru(os.getenv('YA_LOGIN'), os.getenv('YA_PASSWORD'), urls[0][0])
    kz_cookies = await login_yandex_kz(os.getenv('YA_LOGIN'), os.getenv('YA_PASSWORD'), urls[1][0])
    
    return ru_cookies, kz_cookies

def update_environment_cookies(cookies):
    if "KZ" in cookies:
        kz_cookies = cookies["KZ"]
        if "Session_id" in kz_cookies:
            os.environ["YANDEXKZ_SESSIONID_COOK"] = kz_cookies["Session_id"]
    
    if "RU" in cookies:
        ru_cookies = cookies["RU"]
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

@router.message(Command("uptime", ignore_case=True))
@admin_only
async def cmd_uptime(message: Message):
    now = datetime.now()
    uptime = now - start_time
    days = uptime.days
    hours = (uptime.total_seconds() // 3600) % 24
    minutes = (uptime.total_seconds() // 60) % 60
    await message.answer(f"Uptime: {days} days, {int(hours)} hours, {int(minutes)} minutes")

@router.message(Command("stop", ignore_case=True))
@admin_only
async def cmd_stop(message: Message):
    os._exit(0)

@router.message(Command("stats", ignore_case=True))
@admin_only
async def stats(message: Message, command: CommandObject):
    args = command.args.split() if command.args else []
    if len(args) == 2:
        start_date, end_date = args
    else:
        start_date, end_date = None, None 

    date, today_stats, total_stats, earliest_date = get_stats(start_date, end_date)

    message_text = f"Статистика за дату: {date}\n"
    message_text += "\n".join(f"{cmd}: {today_stats.get(cmd, 0)}" for cmd in cmds)
    message_text += f"\n\nОбщая статистика с {earliest_date or 'неизвестной даты'}:\n"
    message_text += "\n".join(f"{cmd}: {total_stats[cmd]}" for cmd in cmds)

    await message.answer(message_text)


@router.message(Command("update_cookie", ignore_case=True))
@admin_only
async def update_cookie(message: Message, bot: Bot):
    command_args = message.text.split()

    if len(command_args) == 1: 
        ru_cookies, kz_cookies = await get_cookies()
        update_environment_cookies({"RU": ru_cookies, "KZ": kz_cookies})
        output = {"KZ": kz_cookies, "RU": ru_cookies}
        await bot.send_message(chat_id=os.getenv("ADMIN_ID"), text=f"Куки обновлены: {json.dumps(output, indent=4)}")
        await message.answer(f"Куки обновлены.")
    
    elif len(command_args) == 2:
        arg = command_args[1].lower()

        if arg == "ru":
            ru_cookies = await login_yandex_ru(os.getenv('YA_LOGIN'), os.getenv('YA_PASSWORD'), "https://passport.ya.ru/auth?retpath=https://300.ya.ru/?nr=1")
            update_environment_cookies({"RU": ru_cookies})
            await bot.send_message(chat_id=os.getenv("ADMIN_ID"), text=f"Куки RU обновлены: {json.dumps({'RU': ru_cookies}, indent=4)}")
            await message.answer(f"Куки RU обновлены.")

        elif arg == "kz":
            kz_cookies = await login_yandex_kz(os.getenv('YA_LOGIN'), os.getenv('YA_PASSWORD'), "https://passport.yandex.kz/auth")
            update_environment_cookies({"KZ": kz_cookies})
            await bot.send_message(chat_id=os.getenv("ADMIN_ID"), text=f"Куки KZ обновлены: {json.dumps({'KZ': kz_cookies}, indent=4)}")
            await message.answer(f"Куки KZ обновлены.")

        else:
            await message.answer("Неверный аргумент. Используйте 'ru' или 'kz'.")
    else:
        await message.answer("Слишком много аргументов. Используйте '/update_cookie' или '/update_cookie ru/kz'.")
