from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
import aiohttp, asyncio, json, os
from chatgpt_md_converter import telegram_format
from utils.dbmanager import DB
from localization import get_localization, DEFAULT_LANGUAGE

context_db, ContextQuery = DB('db/qwen_context.json').get_db()
router = Router()

def load_messages(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        return json.loads(context_item.get('messages', '[]'))
    return []

def save_messages(user_id, messages):
    getcontext = ContextQuery()
    context_item = context_db.get(getcontext.uid == user_id)
    
    if context_item:
        context_db.update({'messages': json.dumps(messages, ensure_ascii=False)}, getcontext.uid == user_id)
    else:
        context_db.insert({'uid': user_id, 'messages': json.dumps(messages, ensure_ascii=False)})

def remove_messages(user_id):
    getcontext = ContextQuery()
    context_db.remove(getcontext.uid == user_id)

@router.message(Command("qwen", ignore_case=True))
async def cmd_qwen(message: Message, bot: Bot):
    user_id = message.from_user.id
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    messages = load_messages(user_id)
    
    user_input = message.text[len("/qwen "):].strip()
    if not user_input:
        await message.reply(_("qwen_help"))
        return
    
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
                    assistant_reply = telegram_format(result.get("choices", [{}])[0].get("message", {}).get("content", "Ошибка"))
                    await message.reply(assistant_reply, parse_mode="HTML")
                    messages.append({"role": "assistant", "content": assistant_reply})
                    save_messages(user_id, messages)
                else:
                    await message.reply(_("qwen_server_error"))
        except aiohttp.ClientError:
            await message.reply(_("qwen_network"))
        except asyncio.TimeoutError:
            await message.reply(_("qwen_timeout"))
        except Exception as e:
            await message.reply(_("qwen_error")+f"({e})")

@router.message(Command("qwenrm", ignore_case=True))
async def cmd_qwenrm(message: Message, bot: Bot):
    user_id = message.from_user.id
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    remove_messages(user_id)
    await message.reply(_("qwen_history_rm"))