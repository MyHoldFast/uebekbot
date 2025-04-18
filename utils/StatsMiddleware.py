import re 
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Awaitable, Optional, Tuple
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import pytz, asyncio
from utils.dbmanager import DB
from utils.cmd_list import cmds

db, Query = DB('db/stats.json').get_db()
chats_db, ChatsQuery = DB('db/chats.json').get_db()

moscow_tz = pytz.timezone('Europe/Moscow')

class StatsMiddleware(BaseMiddleware):
    def __init__(self, bot: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.text = None
        asyncio.create_task(self.init())    

    async def init(self):
        bot_info = await self.bot.get_me()
        self.text = bot_info.username

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]) -> Any:        
        pattern = r'[@\s]+' + re.escape(self.text) + r'\b'
        cmd = (lambda t: re.split(pattern, t, 1)[0].split(' ')[0] if t else None)(event.message.text if event.message else None) or \
              (lambda c: re.split(pattern, c, 1)[0].split(' ')[0] if c else None)(event.message.caption if event.message else None)
        if cmd:
            if cmd.lower() in cmds:
                save_stats(cmd.lower())
        if event.message:
            chat_id = str(event.message.chat.id)
            chat_title = event.message.chat.title or event.message.chat.username or f"Chat {chat_id}"
            save_chat(chat_id, chat_title)
        return await handler(event, data)

def save_chat(chat_id: str, chat_title: str):
    global chats_db, ChatsQuery
    chats_db, ChatsQuery = DB('db/chats.json').get_db()

    if not chats_db.search(ChatsQuery().chat_id == chat_id):
        chats_db.insert({'chat_id': chat_id, 'chat_title': chat_title})


def get_all_chats():
    return chats_db.all()

def save_stats(cmd: str):
    global db, Query
    db, Query = DB('db/stats.json').get_db()

    current_datetime = datetime.now(moscow_tz)
    stats_query = Query()
    result = db.search(stats_query.date == str(current_datetime.date()))

    if not result:
        stats_data = {cmd_name: 0 for cmd_name in cmds}
        stats_data[cmd] = 1
        db.insert({'date': str(current_datetime.date()), **stats_data})
    else:
        stats_data = result[0]
        stats_data[cmd] = int(stats_data.get(cmd, 0)) + 1
        db.update(stats_data, stats_query.date == str(current_datetime.date()))

        
def get_stats(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Tuple[Optional[str], Dict[str, int], Dict[str, int], Optional[str]]:
    total_stats = {cmd: 0 for cmd in cmds}  
    selected_stats = {cmd: 0 for cmd in cmds}  
    earliest_date = None

    if start_date == "yesterday":
        start_date = (datetime.now(moscow_tz) - timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = start_date

    if start_date is None:
        start_date = str(datetime.now(moscow_tz).date())
    if end_date is None:
        end_date = str(datetime.now(moscow_tz).date())

    all_records = db.all()
    
    all_dates = [datetime.strptime(record.get("date", ""), "%Y-%m-%d").date() for record in all_records if "date" in record]
    if all_dates:
        earliest_date = str(min(all_dates))  

    for stats_record in all_records:
        record_date = datetime.strptime(stats_record.get("date", ""), "%Y-%m-%d").date()
        
        if start_date <= str(record_date) <= end_date:
            for cmd in cmds:
                selected_stats[cmd] += int(stats_record.get(cmd, 0) or 0)

        for cmd in cmds:
            total_stats[cmd] += int(stats_record.get(cmd, 0) or 0)

    return start_date, selected_stats, total_stats, earliest_date

