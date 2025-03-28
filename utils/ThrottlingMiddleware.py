from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import Message, CallbackQuery
import asyncio

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, default_rate_limit: float = 1.0):
        self.default_rate_limit = default_rate_limit
        self.user_times = {}
        self.notified_users = set()

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        current_time = asyncio.get_event_loop().time()

        rate_limit = get_flag(data, "throttling") or self.default_rate_limit

        if user_id in self.user_times:
            last_time = self.user_times[user_id]
            if current_time - last_time < rate_limit:
                if user_id not in self.notified_users:
                    self.notified_users.add(user_id)
                    message = None
                    if isinstance(event, Message):
                        message = event
                    elif isinstance(event, CallbackQuery) and event.message:
                        message = event.message
                    
                    if message:
                        await message.answer("Не так быстро, обработаю что-то одно 😊")
                return
            else:
                if user_id in self.notified_users:
                    self.notified_users.remove(user_id)

        self.user_times[user_id] = current_time
        return await handler(event, data)