import asyncio
from aiogram import Bot

class TypingIndicator:
    def __init__(self, bot: Bot, chat_id: int, duration: int = 120):
        self.bot = bot
        self.chat_id = chat_id
        self.typing_task = None
        self.duration = duration

    async def start(self):
        async def send_typing_periodically():
            try:
                end_time = asyncio.get_event_loop().time() + self.duration
                while asyncio.get_event_loop().time() < end_time:
                    await self.bot.send_chat_action(chat_id=self.chat_id, action='typing')
                    await asyncio.sleep(3)
            except asyncio.CancelledError:
                pass

        self.typing_task = asyncio.create_task(send_typing_periodically())

    async def stop(self):
        if self.typing_task:
            self.typing_task.cancel()
            try:
                await self.typing_task
            except asyncio.CancelledError:
                pass

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
