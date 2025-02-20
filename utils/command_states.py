import json
from functools import wraps
from aiogram.types import Message
from utils.dbmanager import DB
from localization import DEFAULT_LANGUAGE, get_localization

command_db, CommandQuery = DB('db/command_states.json').get_db()

def load_disabled_commands():
    context_item = command_db.get(CommandQuery().uid == "disabled_commands")
    if context_item:
        try:
            return json.loads(context_item.get('data', '{}'))
        except json.JSONDecodeError:
            return {"global": {}, "chat": {}}
    return {"global": {}, "chat": {}}

def save_disabled_commands(disabled_commands):
    new_data = {
        'uid': "disabled_commands",
        'data': json.dumps(disabled_commands, ensure_ascii=False)
    }
    context_item = command_db.get(CommandQuery().uid == "disabled_commands")
    if context_item:
        command_db.update(new_data, CommandQuery().uid == "disabled_commands")
    else:
        command_db.insert(new_data)

def get_disabled_commands():
    return load_disabled_commands()

def is_command_enabled(command: str, chat_id: int) -> bool:
    disabled_commands = load_disabled_commands()
    if command in disabled_commands["global"]:
        return False
    return command not in disabled_commands["chat"].get(str(chat_id), {})

async def disable_command(command: str, chat_id: int = None):
    disabled_commands = load_disabled_commands()
    if chat_id is None:
        disabled_commands["global"][command] = True
    else:
        chat_id = str(chat_id)
        disabled_commands["chat"].setdefault(chat_id, {})[command] = True
    save_disabled_commands(disabled_commands)

async def enable_command(command: str, chat_id: int = None):
    disabled_commands = load_disabled_commands()
    if chat_id is None:
        disabled_commands["global"].pop(command, None)
    else:
        chat_id = str(chat_id)
        if chat_id in disabled_commands["chat"] and command in disabled_commands["chat"][chat_id]:
            disabled_commands["chat"][chat_id].pop(command, None)
            if not disabled_commands["chat"][chat_id]:
                disabled_commands["chat"].pop(chat_id, None)
    save_disabled_commands(disabled_commands)

def check_command_enabled(command_name):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            disabled_commands = load_disabled_commands()
            chat_id = str(message.chat.id)
            user_language = message.from_user.language_code or DEFAULT_LANGUAGE
            _ = get_localization(user_language)

            if command_name in disabled_commands["global"]:
                await message.answer(_("disable_global").format(command_name=command_name))
                return

            if chat_id in disabled_commands["chat"] and command_name in disabled_commands["chat"][chat_id]:
                await message.answer(_("disable_in_chat").format(command_name=command_name))
                return

            return await handler(message, *args, **kwargs)
        return wrapper
    return decorator
