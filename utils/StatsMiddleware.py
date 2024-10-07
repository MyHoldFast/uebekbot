import re 
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Awaitable, Optional, Tuple
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import pytz, asyncio
from utils.dbmanager import DB

db, Query = DB('db/stats.json').get_db()
moscow_tz = pytz.timezone('Europe/Moscow')
cmds = ['/summary', '/ocr', '/gpt', '/stt', '/neuro']

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
        if cmd.lower() in cmds:
            save_stats(cmd.lower())
        return await handler(event, data)

def save_stats(cmd: str):
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

def get_stats(date: Optional[str] = None) -> Tuple[Optional[str], Dict[str, Any], Dict[str, int]]:
    total_stats = {cmd: 0 for cmd in cmds}
    
    if date is None:
        date = str(datetime.now(moscow_tz).date())
    elif date == "yesterday":
        date = str((datetime.now(moscow_tz) - timedelta(days=1)).date())
    
    result = db.search(Query().date == date)

    if result:
        stats_data = result[0]
    else:
        stats_data = {cmd: 0 for cmd in cmds}

    for stats_record in db.all():
        for cmd in cmds:
            total_stats[cmd] += int(stats_record.get(cmd, 0) or 0)
    
    return date, stats_data, total_stats
