import time, os, asyncio
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update, Message
from typing import Callable, Dict, Awaitable, Any
from utils.dbmanager import DB
from utils.cmd_list import cmds
from localization import get_localization, DEFAULT_LANGUAGE

ban_user_db, BanUserQuery = DB('db/banned_users.json').get_db()
ban_chat_db, BanChatQuery = DB('db/banned_chats.json').get_db()

def is_banned(user_id: int) -> bool:
    if str(user_id) == os.getenv("ADMIN_ID"):
        return False
    return ban_user_db.get(BanUserQuery().uid == user_id) is not None

def ban_user(user_id: int, username: str = None) -> None:
    if not ban_user_db.contains(BanUserQuery().uid == user_id):
        data = {
            'uid': user_id,
            'timestamp': time.time(),
            **({'username': username} if username is not None else {})
        }
        ban_user_db.insert(data)

def unban_user(user_id: int) -> None:
    ban_user_db.remove(BanUserQuery().uid == user_id)

def get_banned_users() -> list:
    return [
        {'uid': entry["uid"], 'username': entry.get("username", "Без никнейма")} 
        for entry in ban_user_db.all()
    ]

def is_chat_banned(chat_id: int) -> bool:
    return ban_chat_db.get(BanChatQuery().cid == chat_id) is not None

def ban_chat(chat_id: int, chat_title: str = None) -> None:
    if not ban_chat_db.contains(BanChatQuery().cid == chat_id):
        ban_chat_db.insert({
            'cid': chat_id,
            'title': chat_title,
            'timestamp': time.time()
        })

def unban_chat(chat_id: int) -> None:
    ban_chat_db.remove(BanChatQuery().cid == chat_id)

def get_banned_chats() -> list:
    return [
        {'cid': entry["cid"], 'title': entry.get("title", "Без названия")} 
        for entry in ban_chat_db.all()
    ]

class BanMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.botname = None
        asyncio.create_task(self.init())

    async def init(self):
        bot_info = await self.bot.get_me()
        self.botname = bot_info.username

    async def __call__(
        self, 
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], 
        event: TelegramObject, 
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        chat_id = None
        chat_title = None

        bot_username = self.botname
        if isinstance(event, Update):
            user_id = self._extract_user_id(event, bot_username)
            chat_id, chat_title = self._extract_chat_info(event)

        if user_id and is_banned(user_id):
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

        if chat_id and is_chat_banned(chat_id):
            user_language = self._get_user_language_code(event) or DEFAULT_LANGUAGE
            _ = get_localization(user_language)

            try:
                if event.message:
                    await event.message.reply(_("ban_chat_message"))
                elif event.callback_query:
                    await event.callback_query.answer(_("ban_chat_message"), show_alert=True)
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

    def _extract_chat_info(self, event: Update) -> tuple[int | None, str | None]:
        if event.message and event.message.chat:
            return event.message.chat.id, event.message.chat.title
        elif event.callback_query and event.callback_query.message and event.callback_query.message.chat:
            return event.callback_query.message.chat.id, event.callback_query.message.chat.title
        return None, None

    def _get_user_language_code(self, event: Update) -> str | None:
        if event.message and event.message.from_user:
            return event.message.from_user.language_code
        elif event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user.language_code
        return None