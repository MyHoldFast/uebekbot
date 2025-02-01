from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
import aiohttp, asyncio, json, os, html, time
from chatgpt_md_converter import telegram_format
from utils.dbmanager import DB
from localization import get_localization, DEFAULT_LANGUAGE

context_db, ContextQuery = DB('db/qwen_context.json').get_db()
router = Router()

MESSAGE_EXPIRY = 3 * 60 * 60 

def load_messages(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        messages = json.loads(context_item.get('messages', '[]'))
        timestamp = float(context_item.get('timestamp', 0))
        if time.time() - timestamp < MESSAGE_EXPIRY:
            return messages
    return []


def save_messages(user_id, messages):
    getcontext = ContextQuery().uid == user_id
    context_item = context_db.get(getcontext)
    
    new_data = {
        'uid': user_id,
        'messages': json.dumps(messages, ensure_ascii=False),
        'timestamp': time.time()
    }

    if context_item:
        context_db.update(new_data, getcontext)
    else:
        context_db.insert(new_data) 



def remove_messages(user_id):
    getcontext = ContextQuery()
    context_db.remove(getcontext.uid == user_id)


def split_message(text, limit=4000):
    return [text[i:i+limit] for i in range(0, len(text), limit)]


@router.message(Command("qwen", ignore_case=True))
async def cmd_qwen(message: Message, command: CommandObject, bot: Bot):
    if message.reply_to_message:
        user_input = message.reply_to_message.text
        if command.args:
            user_input += '\n' + command.args
    else:
        user_input = command.args if command.args else ''
 
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    if not user_input:
        await message.reply(_("qwen_help"))
        return

    user_id = message.from_user.id    
    messages = load_messages(user_id)
    
    messages.append({"role": "user", "content": user_input})
    await bot.send_chat_action(chat_id=message.chat.id, action='typing')
    
    url = 'https://chat.qwenlm.ai/api/chat/completions'
    headers = {
        'authorization': 'Bearer '+os.getenv("QWEN_AUTH"),
        'content-type': 'application/json'
    }
    data = {"stream": False, "chat_type": "t2t", "model": "qwen-max-latest", "messages": messages}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data, timeout=60) as r:
                if r.status == 200:
                    result = await r.json()
                    assistant_reply = result.get("choices", [{}])[0].get("message", {}).get("content", "Ошибка")
                    
                    formatted_reply = telegram_format(assistant_reply)
                    chunks = split_message(formatted_reply)
                    
                    for chunk in chunks:
                        try:
                            await message.reply(chunk, parse_mode="HTML")
                        except Exception:
                            await message.reply(html.quote(chunk))
                    
                    messages.append({"role": "assistant", "content": assistant_reply})
                    save_messages(user_id, messages)
                else:
                    await message.reply(_("qwen_server_error"))
        except aiohttp.ClientError:
            await message.reply(_("qwen_network"))
        except asyncio.TimeoutError:
            await message.reply(_("qwen_timeout"))
        except Exception as e:
            await message.reply(_("qwen_error") + f" ({e})")


@router.message(Command("qwenrm", ignore_case=True))
async def cmd_qwenrm(message: Message, bot: Bot):
    user_id = message.from_user.id
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    remove_messages(user_id)
    await message.reply(_("qwen_history_rm"))