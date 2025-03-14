from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled

router = Router() 

@router.message(Command("start", ignore_case=True))
@check_command_enabled("start")
async def cmd_start(message: Message, bot: Bot):
    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        await message.answer(
        "шалом"
    )