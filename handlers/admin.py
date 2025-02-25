import os
from datetime import datetime
from functools import wraps
from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from utils.dbmanager import DB
from utils.cmd_list import cmds
from utils.StatsMiddleware import get_stats, get_all_chats
from utils.command_states import get_disabled_commands, disable_command, enable_command
from utils.BanMiddleware import (
    ban_user,
    unban_user,
    get_banned_users,
    is_banned,
)

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
    return (
        f"Uptime: {int(days)} days, {int(hours)} hours, {int(minutes)} minutes"
    )


@router.message(Command("uptime", ignore_case=True))
@admin_only
async def cmd_uptime(message: Message):
    await message.reply(format_uptime())


@router.message(Command("ban"))
@admin_only
async def cmd_ban(message: Message):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            return await message.reply(
                "⚠ Укажите ID пользователя или ответьте на его сообщение."
            )
        user_id = int(args[1])

    if str(user_id) == ADMIN_ID:
        return await message.reply("⛔ Вы не можете забанить самого себя!")

    if is_banned(user_id):
        return await message.reply("⚠ Этот пользователь уже в бане.")

    ban_user(user_id, message.reply_to_message.from_user.full_name)
    await message.reply(f"🚫 Пользователь {user_id} забанен!")


@router.message(Command("unban"))
@admin_only
async def cmd_unban(message: Message):
    args = message.text.split()
    if len(args) < 2:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
        else:
            return await message.reply(
                "⚠ Укажите ID пользователя для разблокировки."
            )
    else:
        if not args[1].isdigit():
            return await message.reply(
                "⚠ Укажите валидный ID пользователя для разблокировки."
            )
        user_id = int(args[1])

    if not is_banned(user_id):
        return await message.reply("⚠ Этот пользователь не в бане.")

    unban_user(user_id)
    await message.reply(f"✅ Пользователь {user_id} разбанен!")


@router.message(Command("ban_list"))
@admin_only
async def cmd_ban_list(message: Message):
    banned_users = get_banned_users()

    if not banned_users:
        return await message.reply("✅ В бане нет пользователей.")

    banned_text = "\n".join(
        f"🔴 {user['username']} ({user['uid']})" for user in banned_users
    )

    await message.reply(f"🚫 Забаненные пользователи:\n{banned_text}")


@router.message(Command("disable", ignore_case=True))
@admin_only
async def cmd_disable(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠ Укажите команду для отключения. Пример: /disable start или /disable start global")
        return

    command = args[1].lstrip("/")
    if f"/{command}" not in cmds:
        await message.reply(f"⚠ Команда /{command} не существует.")
        return

    is_global = len(args) > 2 and args[2] == "global"

    if is_global:
        await disable_command(command)
        scope = "глобально"
    else:
        await disable_command(command, message.chat.id)
        scope = "в этом чате"

    await message.reply(f"🚫 Команда /{command} отключена {scope}.")

@router.message(Command("enable", ignore_case=True))
@admin_only
async def cmd_enable(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠ Укажите команду для включения. Пример: /enable start или /enable start global")
        return

    command = args[1].lstrip("/")
    if f"/{command}" not in cmds:
        await message.reply(f"⚠ Команда /{command} не существует.")
        return

    is_global = len(args) > 2 and args[2] == "global"

    if is_global:
        await enable_command(command)
        scope = "глобально"
    else:
        await enable_command(command, message.chat.id)
        scope = "в этом чате"

    await message.reply(f"✅ Команда /{command} включена {scope}.")

@router.message(Command("commands"))
@admin_only
async def cmd_list_disabled(message: Message):
    disabled_commands = get_disabled_commands()
    chat_id = str(message.chat.id)

    global_disabled = "\n".join([f"🌍 /{cmd}" for cmd in disabled_commands["global"]]) or "Нет"
    chat_disabled_dict = disabled_commands["chat"].get(chat_id, {})
    chat_disabled = "\n".join([f"💬 /{cmd}" for cmd in chat_disabled_dict]) or "Нет"

    await message.reply(
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
    db_list = [
        "gpt_models",
        "gpt_context",
        "qwen_context",
        "stats",
        "command_states",
        "banned_users",
        "chats"
    ]

    if not command.args:
        await message.reply(", ".join(db_list))
        return

    if command.args in db_list:
        database = DB(f"db/{command.args}.json").get_db()[0]
        database.truncate()
        await message.reply(f"База {command.args} очищена")
    else:
        await message.reply("Неверное название базы данных.")


@router.message(Command("chats", ignore_case=True))
@admin_only
async def cmd_chats(message: Message, command: CommandObject):
    message_text = ""
    all_chats = get_all_chats()
    for chat in all_chats:
        message_text+="\n"+(f"Chat ID: {chat['chat_id']}, Title: {chat['chat_title']}")
    if message_text: await message.reply(message_text)


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

    date, today_stats, total_stats, earliest_date = get_stats(
        start_date, end_date
    )

    period_text = (
        f"Статистика за дату: {date}\n"
        if start_date == end_date
        else f"Статистика за период с {start_date} по {end_date}\n"
    )

    today_stats_text = "\n".join(
        f"{cmd}: {today_stats.get(cmd, 0)}" for cmd in cmds
    )
    total_stats_text = "\n".join(
        f"{cmd}: {total_stats.get(cmd, 0)}" for cmd in cmds
    )

    message_text = (
        f"{period_text}\n{today_stats_text}\n\n"
        f"Общая статистика с {earliest_date or 'неизвестной даты'}:\n"
        f"{total_stats_text}"
    )

    await message.reply(message_text)


@router.message(Command("proxy", ignore_case=True))
@admin_only
async def cmd_proxy(message: Message):
    command_args = message.text.split(maxsplit=1)

    if len(command_args) == 1:
        proxy_value = os.getenv("PROXY")
        await message.reply(
            f"Текущее значение PROXY: {proxy_value}"
            if proxy_value
            else "Переменная PROXY не установлена."
        )
    else:
        new_proxy = command_args[1]
        os.environ["PROXY"] = new_proxy
        await message.reply(f"Новое значение PROXY установлено: {new_proxy}")
