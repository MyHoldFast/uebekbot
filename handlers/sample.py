from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from utils.command_states import check_command_enabled

router = Router() 

@router.message(Command("start", ignore_case=True))
@check_command_enabled("start")
async def cmd_start(message: Message):
    await message.answer(
        "шалом"
    )