import time
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update
from typing import Callable, Dict, Awaitable, Any
from utils.dbmanager import DB
from utils.cmd_list import cmds
from localization import get_localization, DEFAULT_LANGUAGE

ban_db, BanQuery = DB('db/banned_users.json').get_db()

def is_banned(user_id: int) -> bool:
    return ban_db.get(BanQuery().uid == user_id) is not None

def ban_user(user_id: int, username: str = None) -> None:
    if not ban_db.contains(BanQuery().uid == user_id):
        ban_db.insert({
            'uid': user_id,
            'username': username,
            'timestamp': time.time()
        })

def unban_user(user_id: int) -> None:
    ban_db.remove(BanQuery().uid == user_id)

def get_banned_users() -> list:
    return [
        {'uid': entry["uid"], 'username': entry.get("username", "Без никнейма")} 
        for entry in ban_db.all()
    ]

class BanMiddleware(BaseMiddleware):
    async def __call__(
        self, 
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], 
        event: TelegramObject, 
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        bot: Bot = data.get('bot')
        if bot is None:
            return await handler(event, data)
        
        bot_username = (await bot.me()).username
        if isinstance(event, Update):
            user_id = self._extract_user_id(event, bot_username)
        
        if user_id and is_banned(user_id):            
            #print(language_code)
            user_language = self._get_user_language_code(event) or DEFAULT_LANGUAGE
            _ = get_localization(user_language) 
      
            try:
                if event.message:
                    await event.message.reply(_("ban_message"))
                elif event.callback_query:
                    await event.callback_query.answer(_("ban_message"), show_alert=True)
            except Exception as e:
                print(f"Ошибка при отправке сообщения: {e}")
            return None
        
        return await handler(event, data)
    
    def _extract_user_id(self, event: Update, bot_username: str) -> int | None:
        if event.message and event.message.from_user:
            message_text = event.message.text
            if (
                event.message.chat.type == 'private' or
                (message_text and any(
                    message_text.startswith(cmd) and
                    ('@' not in message_text or message_text.endswith(f"@{bot_username}"))
                for cmd in cmds))
            ):
                return event.message.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user.id
        return None
    
    def _get_user_language_code(self, event: Update) -> str | None:
        if event.message and event.message.from_user:
            return event.message.from_user.language_code
        elif event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user.language_code
        return None