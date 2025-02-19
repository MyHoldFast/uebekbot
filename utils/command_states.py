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
            data = json.loads(context_item.get('data', '{}'))
            global_commands = data.get("global", {})
            chat_commands = data.get("chat", {})
            return global_commands, chat_commands
        except json.JSONDecodeError as e:
            return {}, {}
    return {}, {}

def save_disabled_commands():
    new_data = {
        'uid': "disabled_commands",
        'data': json.dumps({"global": global_disabled_commands, "chat": chat_disabled_commands}, ensure_ascii=False)
    }
    context_item = command_db.get(CommandQuery().uid == "disabled_commands")

    if context_item:
        command_db.update(new_data, CommandQuery().uid == "disabled_commands")
    else:
        command_db.insert(new_data)

global_disabled_commands, chat_disabled_commands = load_disabled_commands()

def update():
    global global_disabled_commands, chat_disabled_commands
    global_disabled_commands, chat_disabled_commands = load_disabled_commands()
    return global_disabled_commands, chat_disabled_commands

def is_command_enabled(command: str, chat_id: int) -> bool:
    if command in global_disabled_commands:
        return False 
    return command not in chat_disabled_commands.get(str(chat_id), {})

async def disable_command(command: str, chat_id: int = None):
    global global_disabled_commands, chat_disabled_commands

    if chat_id is None:
        global_disabled_commands[command] = True
    else:
        chat_id = str(chat_id) 
        chat_disabled_commands.setdefault(chat_id, {})[command] = True

    save_disabled_commands()

async def enable_command(command: str, chat_id: int = None):
    global global_disabled_commands, chat_disabled_commands

    if chat_id is None:
        global_disabled_commands.pop(command, None)
    else:
        chat_id = str(chat_id) 
        if chat_id in chat_disabled_commands and command in chat_disabled_commands[chat_id]:
            chat_disabled_commands[chat_id].pop(command, None)
            if not chat_disabled_commands[chat_id]:
                chat_disabled_commands.pop(chat_id, None)

    save_disabled_commands()

def check_command_enabled(command_name):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            chat_id = str(message.chat.id)
            user_language = message.from_user.language_code or DEFAULT_LANGUAGE
            _ = get_localization(user_language)

            if command_name in global_disabled_commands:
                await message.answer(_("disable_global").format(command_name=command_name))
                return
            
            if chat_id in chat_disabled_commands and command_name in chat_disabled_commands[chat_id]:
                await message.answer(_("disable_in_chat").format(command_name=command_name))
                return
            
            return await handler(message, *args, **kwargs)
        return wrapper
    return decorator
