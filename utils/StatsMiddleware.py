import json
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Awaitable, Optional, Tuple
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import pytz

moscow_tz = pytz.timezone('Europe/Moscow')
cmds = ['/summary', '/ocr', '/gpt', '/stt', '/neuro']

class StatsMiddleware(BaseMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        cmd = (event.message.text.split(' ', 1)[0] if event.message.text else None)
        if cmd in cmds:
            save_stats(cmd)

        return await handler(event, data)

def save_stats(cmd: str):
    current_date = datetime.now(moscow_tz).date()
    stats_data = {}

    try:
        with open('db/stats.json', 'r') as f:
            for line in f:
                entry = json.loads(line)
                stats_data.update(entry)
    except FileNotFoundError:
        pass

    if str(current_date) not in stats_data:
        stats_data[str(current_date)] = {cmd: 1}
        for other_cmd in cmds:
            if other_cmd != cmd:
                stats_data[str(current_date)][other_cmd] = 0
    else:
        if cmd in stats_data[str(current_date)]:
            stats_data[str(current_date)][cmd] += 1
        else:
            stats_data[str(current_date)][cmd] = 1

        for other_cmd in cmds:
            if other_cmd not in stats_data[str(current_date)]:
                stats_data[str(current_date)][other_cmd] = 0

    with open('db/stats.json', 'w') as f:
        for date, stats in stats_data.items():
            json.dump({date: stats}, f)
            f.write('\n')

def get_stats(date: Optional[str] = None) -> Tuple[Optional[str], Dict[str, Any], Dict[str, int]]:
    stats_data = {}
    total_stats = {cmd: 0 for cmd in cmds}

    if date is None:
        date = str(datetime.now(moscow_tz).date())
    elif date == "yesterday":
        date = str((datetime.now(moscow_tz) - timedelta(days=1)).date())

    try:
        with open('db/stats.json', 'r') as f:
            for line in f:
                entry = json.loads(line)
                stats_data.update(entry)
    except FileNotFoundError:
        return None, {}, total_stats

    if date in stats_data:
        for stats in stats_data.values():
            for cmd in cmds:
                total_stats[cmd] += stats.get(cmd, 0)
        return date, stats_data[date], total_stats
    else:
        for stats in stats_data.values():
            for cmd in cmds:
                total_stats[cmd] += stats.get(cmd, 0)
        return None, {}, total_stats