import os
from datetime import datetime
from functools import wraps
from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from utils.dbmanager import DB
from utils.StatsMiddleware import get_stats, cmds
from utils.command_states import disable_command, enable_command, global_disabled_commands, chat_disabled_commands


router = Router()
start_time = datetime.now()
ADMIN_ID = os.getenv("ADMIN_ID")


def admin_only(func):
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if str(message.from_user.id) != ADMIN_ID:
            return
        return await func(message, *args, **kwargs)
    return wrapper


def format_uptime():
    uptime = datetime.now() - start_time
    days, remainder = divmod(uptime.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"Uptime: {int(days)} days, {int(hours)} hours, {int(minutes)} minutes"


@router.message(Command("uptime", ignore_case=True))
@admin_only
async def cmd_uptime(message: Message):
    await message.answer(format_uptime())

@router.message(Command("disable", ignore_case=True))
@admin_only
async def cmd_disable(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠ Укажите команду для отключения. Пример: /disable start или /disable start global")
        return

    command = args[1].lstrip("/")
    if len(args) > 2 and args[2] == "global":
        await disable_command(command)
        await message.answer(f"🚫 Команда /{command} отключена глобально.")
    else:
        await disable_command(command, message.chat.id)
        await message.answer(f"🚫 Команда /{command} отключена в этом чате.")

@router.message(Command("enable", ignore_case=True))
@admin_only
async def cmd_enable(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠ Укажите команду для включения. Пример: /enable start или /enable start global")
        return

    command = args[1].lstrip("/")
    if len(args) > 2 and args[2] == "global":
        await enable_command(command)
        await message.answer(f"✅ Команда /{command} включена глобально.")
    else:
        await enable_command(command, message.chat.id)
        await message.answer(f"✅ Команда /{command} включена в этом чате.")

@router.message(Command("commands"))
@admin_only
async def cmd_list_disabled(message: Message):
    chat_id = str(message.chat.id)

    global_disabled = "\n".join([f"🌍 /{cmd}" for cmd in global_disabled_commands.keys()]) or "Нет"
    chat_disabled_dict = chat_disabled_commands.get(chat_id, {})
    chat_disabled = "\n".join([f"💬 /{cmd}" for cmd in chat_disabled_dict.keys()]) or "Нет"
    
    await message.answer(
        f"🚫 Отключенные команды:\n\n"
        f"Глобально:\n{global_disabled}\n\n"
        f"В этом чате:\n{chat_disabled}"
    )

@router.message(Command("stop", ignore_case=True))
@admin_only
async def cmd_stop(message: Message):
    os._exit(0)


@router.message(Command("trunc", ignore_case=True))
@admin_only
async def cmd_trunc(message: Message, command: CommandObject):
    db_list = ["gpt_models", "gpt_context", "qwen_context", "stats", "command_states"]

    if not command.args:
        await message.answer(", ".join(db_list))
        return

    if command.args in db_list:
        database = DB(f'db/{command.args}.json').get_db()[0]
        database.truncate()
        await message.answer(f"База {command.args} очищена")
    else:
        await message.answer("Неверное название базы данных.")


@router.message(Command("stats", ignore_case=True))
@admin_only
async def cmd_stats(message: Message, command: CommandObject):
    args = command.args.split() if command.args else []

    if len(args) == 1 and args[0].lower() == "yesterday":
        start_date, end_date = "yesterday", "yesterday"
    elif len(args) == 2:
        start_date, end_date = args
    else:
        start_date, end_date = None, None

    date, today_stats, total_stats, earliest_date = get_stats(start_date, end_date)

    period_text = (
        f"Статистика за дату: {date}\n"
        if start_date == end_date
        else f"Статистика за период с {start_date} по {end_date}\n"
    )

    today_stats_text = "\n".join(f"{cmd}: {today_stats.get(cmd, 0)}" for cmd in cmds)
    total_stats_text = "\n".join(f"{cmd}: {total_stats.get(cmd, 0)}" for cmd in cmds)

    message_text = (
        f"{period_text}\n{today_stats_text}\n\n"
        f"Общая статистика с {earliest_date or 'неизвестной даты'}:\n"
        f"{total_stats_text}"
    )

    await message.answer(message_text)


@router.message(Command("proxy", ignore_case=True))
@admin_only
async def cmd_proxy(message: Message):
    command_args = message.text.split(maxsplit=1)

    if len(command_args) == 1:
        proxy_value = os.getenv("PROXY")
        await message.answer(f"Текущее значение PROXY: {proxy_value}" if proxy_value else "Переменная PROXY не установлена.")
    else:
        new_proxy = command_args[1]
        os.environ["PROXY"] = new_proxy
        await message.answer(f"Новое значение PROXY установлено: {new_proxy}")
