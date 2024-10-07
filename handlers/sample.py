from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router() 

@router.message(Command("start", ignore_case=True))
async def cmd_start(message: Message):
    await message.answer(
        "шалом"
    )