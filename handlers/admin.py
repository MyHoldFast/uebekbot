from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
import os
from datetime import datetime
from functools import wraps
from utils.StatsMiddleware import get_stats, cmds

router = Router()

start_time = datetime.now()

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
    if date:
        message_text = f"Дата: {date}\n" + "\n".join(f"{cmd}: {stats.get(cmd, 0)}" for cmd in cmds)
    else:
        message_text = "Статистика за сегодня пуста."
    message_text += "\n\nОбщая статистика:\n" + "\n".join(f"{cmd}: {total_stats[cmd]}" for cmd in cmds)
    await message.answer(message_text)
