from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
ADMIN_ID = os.getenv("ADMIN_ID")

router = Router()

start_time = datetime.now()
@router.message(Command("uptime"))
async def cmd_uptime(message: Message):
    user_id = message.from_user.id
    if str(user_id) != ADMIN_ID: return
    now = datetime.now()
    uptime = now - start_time
    days = uptime.days
    hours = (uptime.total_seconds() // 3600) % 24
    minutes = (uptime.total_seconds() // 60) % 60
    await message.answer(f"Uptime: {days} days, {int(hours)} hours, {int(minutes)} minutes")