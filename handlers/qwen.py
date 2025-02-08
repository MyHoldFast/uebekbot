from aiogram import Router, Bot, html
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
import aiohttp, asyncio, json, os, time, uuid
from chatgpt_md_converter import telegram_format
from utils.dbmanager import DB
from localization import get_localization, DEFAULT_LANGUAGE
from utils.command_states import check_command_enabled

context_db, ContextQuery = DB('db/qwen_context.json').get_db()
router = Router()

qwen_accs_str = os.getenv('QWEN_ACCS')
qwen_accs = json.loads(qwen_accs_str)
acc_index = 0

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

headers = {
    'authorization': 'Bearer '+qwen_accs[0]['bearer'],      
    'content-type': 'application/json',    
    'bx-v': '2.5.0',
    'cache-control': 'no-cache',
    'content-type': 'application/json',
    #'cookie': 'YOUR_COOKIES_HERE',
    'dnt': '1',
    'origin': 'https://chat.qwenlm.ai',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://chat.qwenlm.ai/c/6577ef55-cf1c-4136-bb96-0fc0b8603c51',
    'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'x-request-id': qwen_accs[0]['x']
}

@router.message(Command("qwen", ignore_case=True))
@check_command_enabled("qwen")
async def cmd_qwen(message: Message, command: CommandObject, bot: Bot):
    if message.reply_to_message:
        user_input = message.reply_to_message.text or message.reply_to_message.caption or ""
        if command.args:
            user_input += '\n' + command.args
    else:
        user_input = command.args if command.args else ""
    

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
    data = {"stream": False, "chat_type": "t2t", "model": "qwen-max-latest", "messages": messages}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data, timeout=120) as r:
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


@router.message(Command("qwenimg", ignore_case=True))
@check_command_enabled("qwenimg")
async def cmd_qwenimg(message: Message, command: CommandObject, bot: Bot):
    if message.reply_to_message:
        user_input = message.reply_to_message.text or message.reply_to_message.caption or ""
        if command.args:
            user_input += '\n' + command.args
    else:
        user_input = command.args if command.args else ""

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    
    if not user_input:
        await message.reply(_("qwenimghelp"))
        return
    
    url = 'https://chat.qwenlm.ai/api/chat/completions'
    data = {
        "stream": False, "chat_type": "t2i", "model": "qwen-plus-latest", 
        "size": "1280*720", "messages": [{"role": "user", "content": user_input}],
        "id": str(uuid.uuid4()), "chat_id": str(uuid.uuid4())
    }    
    
    async def make_request(session, url, headers, data, message, sent_message):
        global acc_index

        bearer = qwen_accs[acc_index]['bearer']
        x = qwen_accs[acc_index]['x']        
        
        headers['Authorization'] = 'Bearer ' + bearer
        headers['x-request-id'] = x        
        
        async with session.post(url, headers=headers, json=data, timeout=120) as r:
            if r.status == 200:
                result = await r.json()
                task_id = result['messages'][1]['extra']['wanx']['task_id']
                await check_task_status(session, task_id, message, sent_message)
            elif r.status == 429:
                if acc_index + 1 < len(qwen_accs):                    
                    acc_index += 1
                    await session.close()
                    async with aiohttp.ClientSession() as new_session:
                        try:
                            await make_request(new_session, url, headers, data, message, sent_message)
                        except Exception:
                            await sent_message.delete()
                            await message.reply(_("qwenimg_err"))
                else:
                    await sent_message.delete()
                    await message.reply(_("qwenimg_err"))
            else:
                await sent_message.delete()
                await message.reply(_("qwenimg_err"))
    
    sent_message = await message.reply(_("qwenimg_gen"))    
    
    async with aiohttp.ClientSession() as session:
        await make_request(session, url, headers, data, message, sent_message)

async def check_task_status(session, task_id, message, sent_message):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    status_url = f'https://chat.qwenlm.ai/api/v1/tasks/status/{task_id}'
    while True:
        async with session.get(status_url, headers=headers, timeout=180) as r:
            if r.status == 200:
                result = await r.json()
                task_status = result.get("task_status", "")
                if task_status == "success":
                    image_url = result.get("content", "")
                    await sent_message.delete()
                    await message.reply_photo(photo=image_url)
                    break
                elif task_status in ["failed", "error"]:
                    await sent_message.delete()
                    await message.reply(_("qwenimg_err"))
                    break
                else:
                    await asyncio.sleep(5)
            else:
                await sent_message.delete()
                await message.reply(_("qwenimg_err"))
                break
