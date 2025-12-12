from utils.typing_indicator import TypingIndicator
from utils.text_utils import split_html
from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
import aiohttp, asyncio, json, os, time
from chatgpt_md_converter import telegram_format
from utils.dbmanager import DB
from localization import get_localization, DEFAULT_LANGUAGE
from utils.command_states import check_command_enabled
from dotenv import load_dotenv
from pylatexenc.latex2text import LatexNodes2Text
import re
from typing import List, Dict
import threading

context_db, ContextQuery = DB("db/qwen_context.json").get_db()
router = Router()

MESSAGE_EXPIRY = 3 * 60 * 60

qwen_keys = []
current_key_index = 0
key_lock = threading.Lock()
chat_in_progress_locks = {}
chat_lock_timeout = 30

def init_keys():
    global qwen_keys
    load_dotenv(override=True)
    qwen_keys = json.loads(os.getenv("QWEN_ACCS") or "[]")
    if not qwen_keys:
        raise ValueError("No Qwen accounts configured")

def get_next_key():
    global current_key_index
    if not qwen_keys:
        init_keys()
    
    with key_lock:
        key = qwen_keys[current_key_index]
        current_key_index = (current_key_index + 1) % len(qwen_keys)
        return key

async def get_headers_with_retry(max_retries=3):
    for attempt in range(max_retries):
        key = get_next_key()
        headers = {
            "Authorization": f"Bearer {key['bearer']}",
            "Content-Type": "application/json",
        }
        return headers, key
    raise ValueError("Failed to get valid API key after retries")

async def wait_for_chat_lock(user_id):
    lock_key = f"chat_lock_{user_id}"
    
    if lock_key not in chat_in_progress_locks:
        chat_in_progress_locks[lock_key] = asyncio.Lock()
    
    lock = chat_in_progress_locks[lock_key]
    
    try:
        await asyncio.wait_for(lock.acquire(), timeout=chat_lock_timeout)
        return True
    except asyncio.TimeoutError:
        return False
    except Exception:
        return False

def release_chat_lock(user_id):
    lock_key = f"chat_lock_{user_id}"
    if lock_key in chat_in_progress_locks:
        lock = chat_in_progress_locks[lock_key]
        try:
            if lock.locked():
                lock.release()
        except RuntimeError:
            pass

def load_context(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        messages = json.loads(context_item.get("messages", "[]"))
        timestamp = float(context_item.get("timestamp", 0))
        if time.time() - timestamp < MESSAGE_EXPIRY:
            return messages
    return []

def save_context(user_id, messages):
    getcontext = ContextQuery().uid == user_id
    context_item = context_db.get(getcontext)

    new_data = {
        "uid": user_id,
        "messages": json.dumps(messages, ensure_ascii=False),
        "timestamp": time.time(),
    }

    if context_item:
        context_db.update(new_data, getcontext)
    else:
        context_db.insert(new_data)

def remove_messages(user_id):
    getcontext = ContextQuery()
    context_db.remove(getcontext.uid == user_id)

def process_latex(text):
    code_blocks = {}
    
    def extract_code(match):
        key = f"__CODE_BLOCK_{len(code_blocks)}__"
        code_blocks[key] = match.group(0)
        return key

    text = re.sub(r'<code class=".*?">.*?</code>', extract_code, text, flags=re.DOTALL)
    
    text = re.sub(
        r"(?s)\$\$\s*(.*?)\s*\$\$",
        lambda m: LatexNodes2Text().latex_to_text(m.group(1)),
        text
    )
    text = re.sub(
        r"(?s)\\\[\s*(.*?)\s*\\\]",
        lambda m: LatexNodes2Text().latex_to_text(m.group(1)),
        text
    )
    text = re.sub(
        r'\$\s*\\boxed\{(.*?)\}\s*\$',
        lambda m: f"<b>{LatexNodes2Text().latex_to_text(m.group(1))}</b>",
        text
    )
    text = re.sub(
        r'\$(.*?)\$',
        lambda m: LatexNodes2Text().latex_to_text(m.group(1)),
        text
    )
    
    for key, block in code_blocks.items():
        text = text.replace(key, block)

    return text

def remove_details_tags(text):
    return re.sub(r'<details>.*?</details>', '', text, flags=re.DOTALL)

@router.message(Command("qwen", ignore_case=True))
@check_command_enabled("qwen")
async def cmd_qwen(message: Message, command: CommandObject, bot: Bot, id=None, lang=None):
    if message.reply_to_message and id is None:
        user_input = (
            message.reply_to_message.text or message.reply_to_message.caption or ""
        )
        if command.args:
            user_input += "\n" + command.args
    else:
        user_input = command.args if command.args else ""

    user_language = lang if lang is not None else message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input:
        await message.reply(_("qwen_help"))
        return

    user_id = id if id is not None else message.from_user.id
    
    lock_acquired = await wait_for_chat_lock(user_id)
    if not lock_acquired:
        await message.reply(_("qwen_busy"))
        return
    
    try:
        messages = load_context(user_id)
        messages.append({"role": "user", "content": user_input})

        async with TypingIndicator(bot=bot, chat_id=message.chat.id):
            max_retries = len(qwen_keys) * 2 if qwen_keys else 3
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    headers, current_key = await get_headers_with_retry()
                    
                    json_data = {
                        "model": "qwen3-max",
                        "messages": messages,
                        "stream": False,
                    }

                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            "https://qwen.aikit.club/v1/chat/completions",
                            headers=headers,
                            json=json_data,
                            timeout=180
                        ) as response:
                            
                            if response.status == 400:
                                error_data = await response.json()
                                if error_data.get("error", {}).get("message") == "The chat is in progress!":
                                    await asyncio.sleep(2)
                                    continue
                            
                            if response.status != 200:
                                error_text = await response.text()
                                raise Exception(f"API error {response.status}: {error_text}")
                            
                            result = await response.json()
                            
                            if "choices" in result and len(result["choices"]) > 0:
                                assistant_message = result["choices"][0]["message"]
                                response_text = assistant_message.get("content", "")
                                
                                messages.append(assistant_message)
                                save_context(user_id, messages)
                                
                                if response_text.strip():
                                    response_text = remove_details_tags(response_text)
                                    formatted_reply = process_latex(telegram_format(response_text))
                                    chunks = split_html(formatted_reply)
                                    
                                    for chunk in chunks:
                                        await message.reply(chunk, parse_mode="HTML")
                                else:
                                    await message.reply(_("qwen_error"))
                                return
                            else:
                                raise Exception("No choices in response")
                                
                except aiohttp.ClientError as e:
                    last_error = e
                    await asyncio.sleep(1)
                    continue
                except Exception as e:
                    last_error = e
                    await asyncio.sleep(2)
                    continue
            
            error_msg = _("qwen_error")
            if last_error:
                error_msg += f" ({str(last_error)})"
            await message.reply(error_msg)
            
    except Exception as e:
        error_msg = _("qwen_error")
        if str(e):
            error_msg += f" ({str(e)})"
        await message.reply(error_msg)
        
    finally:
        release_chat_lock(user_id)

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
        user_input = (
            message.reply_to_message.text or message.reply_to_message.caption or ""
        )
        if command.args:
            user_input += "\n" + command.args
    else:
        user_input = command.args if command.args else ""

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input:
        await message.reply(_("qwenimghelp"))
        return

    sent_message = await message.reply(_("qwenimg_gen"))

    try:
        max_retries = len(qwen_keys) * 2 if qwen_keys else 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                headers, current_key = await get_headers_with_retry()
                
                json_data = {
                    "prompt": user_input,
                    "size": "1024x1024",
                    "n": 1,
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://qwen.aikit.club/v1/images/generations",
                        headers=headers,
                        json=json_data,
                        timeout=120
                    ) as response:
                        
                        if response.status == 400:
                            error_data = await response.json()
                            if error_data.get("error", {}).get("message") == "The chat is in progress!":
                                await asyncio.sleep(2)
                                continue
                        
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f"Image generation failed: {response.status} - {error_text}")
                        
                        result = await response.json()
                        
                        if "data" in result and len(result["data"]) > 0:
                            image_url = result["data"][0].get("url")
                            
                            if image_url:
                                await safe_delete(sent_message)
                                await message.reply_photo(photo=image_url)
                            else:
                                raise Exception("No image URL in response")
                            return
                        else:
                            raise Exception("No data in response")
                            
            except aiohttp.ClientError as e:
                last_error = e
                await asyncio.sleep(1)
                continue
            except Exception as e:
                last_error = e
                await asyncio.sleep(2)
                continue
        
        await safe_delete(sent_message)
        error_msg = _("qwenimg_err")
        if last_error:
            error_msg += f" ({str(last_error)})"
        await message.reply(error_msg)

    except Exception as e:
        await safe_delete(sent_message)
        await message.reply(_("qwenimg_err") + f" ({str(e)})")

async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

init_keys()