from utils.typing_indicator import TypingIndicator
from utils.text_utils import split_html
from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
import aiohttp, asyncio, json, os, time, uuid
from chatgpt_md_converter import telegram_format
from utils.dbmanager import DB
from localization import get_localization, DEFAULT_LANGUAGE
from utils.command_states import check_command_enabled
from dotenv import load_dotenv

from pylatexenc.latex2text import LatexNodes2Text
import re

context_db, ContextQuery = DB("db/qwen_context.json").get_db()
router = Router()

MESSAGE_EXPIRY = 3 * 60 * 60

proxy = os.getenv("PROXY")

cookies = {
    'ssxmod_itna': '1-QqAxyiGQiQK7Txe94mwqQK0QDtHi=HtoDzxC5iOD_xQ5DODLxnb4Gdqndq6w=zWdzb70044dDDqXhlD050rDmqi12DYPGfKPk2ImdC7BA5GdC3l5NNqC0Cwq4tauUGxI565s0I9tlmvZKshHbtQ4DHxi8DB9DmlcYDeeDtx0rD0eDPxDYDG4DoEYDn14DjxDd84SAmROaDm_IHxDbDimIW4aeDD5DAhBPLngrDGyrKsextDgD0bd_i1RPhtD6djGID7y3Dlp5ksmISR6y5h36Wk6LQroDX2tDvrSoEfBPnnEfpSSYoDHVwmmejhrBvC0P3iGwjK4Q_ebhhQeNGGrQDqBh=im=QDZ0qD92mDDAB2rFDN3O4b_r3WMGvlAvZK2Dk0GKeP=i4CG7CDKEDN77N/ri9i4aqqZhPti44_5TDPeD',
    'ssxmod_itna2': '1-QqAxyiGQiQK7Txe94mwqQK0QDtHi=HtoDzxC5iOD_xQ5DODLxnb4Gdqndq6w=zWdzb70044dDDqXhwDDcAeq9mnAqDLQ0TaNk87DDs2QW=9_LoDTOQxuGyAUSKq5Zzl8a4uLk10geaHjyOp2DkcpGklrHaeI71EcBsyrG_uWpqYBc82eAHOPKkYZKFzpGvp=04m8a1oUSskQOQqjB1u6OajzKOc28j3GMazDF4UtmHhzfGubF0z=e6qihuFo9DuZ0_osjxO69409o0PBpkjtvsgbSkejx7pO7_Rfca6k7Sc1ihy2o/OxgDu3z/qrSfQPh=2OQoBH=0x5TTo0Ni3KzdYqMtjhO/MQco5OjQzd_WRG52hQLtKiH/rkm2qFE4hnx94oEh_NfGe3QLOCh2=2YYOmNfo1u0Te7wGOOLxNGrTu_Em23a3zDbWCCQp2_cEb78L/xTWWhbCbk1=_YEwOFzGj7ZtZx7Y2xtnNd1tOxEbl3tnweWaVE8Z2=QfNEo_jOhVONq0dFEkbM1yoreqtj2qq_TFzrMlQV42oSkVr_447iGbMoaiWn5LI7g0dLXcjXh=KUxft1r52F/hOR2Of=GvOdnw=LOp5ObMCrFT1K_DTfQ2BINh4q0xlAQegL_gjh38/EWHOx0l7v_4sNdHS7j_4Oo5mnDdFlHhZVxa0gdh8q5SNe7FZi7R5HGYIyansfHxSNOx2i1m54KQahxntgvNjYzFtDGp2Kihrn8mbw02pbDYqFbMpxY=5hKzQkiZmqkqOxekq5he4RNi5dGG7_nh57_4urWenhcYYkh=4xGq3tDw0D7DsYTFe3hNDe54zBxPDTIeY2cZh4D',
}

headers = {
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'DNT': '1',
    'Origin': 'https://chat.qwen.ai',
    'Pragma': 'no-cache',
    'Referer': 'https://chat.qwen.ai/c/2412f2a1-b964-4af7-a2a4-6cc2e213df13',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'bx-umidtoken': 'T2gA0vIYCH63-9f8G-HkJxZ-QTRRf-SNPjQfr8zLFWFBdnp2Ftt9ByU8Zhjx4lhqX6w=',
    'bx-v': '2.5.31',
    'content-type': 'application/json; charset=UTF-8',
    'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'source': 'web',
    'timezone': 'Mon Sep 29 2025 16:34:00 GMT+0300',
    'x-accel-buffering': 'no',
}


def load_context(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        messages = json.loads(context_item.get("messages", "[]"))
        chat_id = context_item.get("chat_id", "")
        parent_id = context_item.get("parent_id", "")
        message_id = context_item.get("message_id", "")
        timestamp = float(context_item.get("timestamp", 0))
        if time.time() - timestamp < MESSAGE_EXPIRY:
            return messages, chat_id, parent_id, message_id
    return [], "", "", ""


def save_context(user_id, messages, chat_id, parent_id, message_id):
    getcontext = ContextQuery().uid == user_id
    context_item = context_db.get(getcontext)

    new_data = {
        "uid": user_id,
        "messages": json.dumps(messages, ensure_ascii=False),
        "chat_id": chat_id,
        "parent_id": parent_id,
        "message_id": message_id,
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


async def update_memory_settings(session, proxy):
    memory_settings_payload = {
        "memory": {
            "enable_memory": False,
            "enable_history_memory": False,
            "memory_version_reminder": False
        }
    }
    
    try:
        async with session.post(
            'https://chat.qwen.ai/api/v2/users/user/settings/update',
            json=memory_settings_payload,
            proxy=proxy
        ) as resp:
            if resp.status == 200:
                #print("Memory settings updated successfully")
                pass
            else:
                #print(f"Memory settings update failed: {resp.status}")
                pass
    except Exception as e:
        #print(f"Error updating memory settings: {e}")
        pass


@router.message(Command("qwen", ignore_case=True))
@check_command_enabled("qwen")
async def cmd_qwen(message: Message, command: CommandObject, bot: Bot, id: int = None, lang: str = None):
    load_dotenv(override=True)
    qwen_accs = json.loads(os.getenv("QWEN_ACCS") or "[]")
    headers["authorization"] = "Bearer " + (qwen_accs[0]["bearer"] if qwen_accs else "")
    cookies.update({'token': qwen_accs[0]["bearer"]})
    
    if message.reply_to_message and id == None:
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
    messages, chat_id, parent_id, message_id = load_context(user_id)

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            try:
                
                await update_memory_settings(session, proxy)
                
                if not chat_id:
                    chat_payload = {
                        "title": "Qwen Chat",
                        "models": ["qwen3-max"],
                        "chat_mode": "normal",
                        "chat_type": "t2t",
                        "timestamp": int(time.time() * 1000)
                    }
                    
                    async with session.post(
                        "https://chat.qwen.ai/api/v2/chats/new",
                        json=chat_payload,
                        proxy=proxy
                    ) as chat_resp:
                        if chat_resp.status != 200:
                            raise Exception(f"Chat create failed: {chat_resp.status}")
                        chat_data = await chat_resp.json()
                        chat_id = chat_data["data"]["id"]
                
                #print(f"Current parent_id: {parent_id}")

                user_message = {
                    'role': 'user',
                    'content': user_input,
                    'user_action': 'chat',
                    'files': [],
                    'models': ['qwen3-max'],
                    'chat_type': 't2t',
                    **({'parentId': parent_id} if parent_id else {}),
                    **({'parent_id': parent_id} if parent_id else {}),
                    'feature_config': {
                        'thinking_enabled': False,
                        'output_schema': 'phase',
                    },
                    'extra': {
                        'meta': {
                            'subChatType': 't2t',
                        },
                    },
                    'sub_chat_type': 't2t'
                }

                json_data = {
                    'stream': True,
                    'incremental_output': True,
                    'chat_id': chat_id,
                    'chat_mode': 'normal',
                    'model': 'qwen3-max',
                    **({'parent_id': parent_id} if parent_id else {}),
                    'messages': [user_message],
                }

                params = {
                    'chat_id': chat_id,
                }

                full_response = ""
                new_parent_id = parent_id
                new_message_id = message_id

                async with session.post(
                    'https://chat.qwen.ai/api/v2/chat/completions',
                    params=params,
                    json=json_data,
                    timeout=180,
                    proxy=proxy
                ) as r:
                    if r.status == 200:
                        async for line in r.content:
                            if not line:
                                continue
                            line = line.decode("utf-8").strip()
                            
                            if not line or not line.startswith("data: "):
                                continue
                            
                            payload = line[len("data: "):]
                            
                            if not payload:
                                continue

                            try:
                                result = json.loads(payload)
                                
                                if 'response.created' in result:
                                    response_created_data = result['response.created']
                                    new_parent_id = response_created_data.get('response_id', new_parent_id)
                                    new_message_id = None
                                
                                elif 'choices' in result:
                                    choices = result.get('choices', [])
                                    if choices:
                                        delta = choices[0].get('delta', {})
                                        content = delta.get('content', '')
                                        
                                        if content is not None:
                                            full_response += content
                                            
                                elif 'status' in result and result.get('status') == 'finished':
                                    break
                                    
                                if 'parent_id' in result:
                                    new_parent_id = result.get('response_id', new_parent_id)
                                if 'message_id' in result:
                                    new_message_id = result.get('message_id', new_message_id)
                                        
                            except json.JSONDecodeError:
                                continue
                            except Exception:
                                continue

                if full_response.strip():
                    formatted_reply = process_latex(telegram_format(full_response))
                    chunks = split_html(formatted_reply)

                    for chunk in chunks:
                        await message.reply(chunk, parse_mode="HTML")

                    save_context(user_id, messages, chat_id, new_parent_id, new_message_id)
                else:
                    await message.reply(_("qwen_error"))

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
    load_dotenv(override=True)
    qwen_accs = json.loads(os.getenv("QWEN_ACCS") or "[]")
    
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

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        sent_message = await message.reply(_("qwenimg_gen"))

        acc_index = 0
        while acc_index < len(qwen_accs):
            headers["authorization"] = "Bearer " + qwen_accs[acc_index]["bearer"]
            cookies.update({'token': qwen_accs[0][acc_index]})

            try:
                async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
                    await update_memory_settings(session, proxy)                    
                    chat_payload = {
                        "title": "Qwen Image Chat",
                        "models": ["qwen3-max"],
                        "chat_mode": "normal",
                        "chat_type": "t2i",
                        "timestamp": int(time.time() * 1000)
                    }
                    async with session.post(
                        "https://chat.qwen.ai/api/v2/chats/new",
                        json=chat_payload,
                        proxy=proxy
                    ) as resp:
                        if resp.status == 429:
                            acc_index += 1
                            continue
                        if resp.status != 200:
                            raise Exception(f"Chat create failed: {resp.status}")
                        chat_data = await resp.json()
                        chat_id = chat_data["data"]["id"]

                    fid = str(uuid.uuid4())
                    json_data = {
                        "stream": True,
                        "incremental_output": True,
                        "chat_id": chat_id,
                        "chat_mode": "normal",
                        "model": "qwen3-max",
                        "parent_id": None,
                        "messages": [
                            {
                                "fid": fid,
                                "parentId": None,
                                "childrenIds": [],
                                "role": "user",
                                "content": user_input,
                                "user_action": "chat",
                                "files": [],
                                "timestamp": int(time.time()),
                                "models": ["qwen3-max"],
                                "chat_type": "t2i",
                                "feature_config": {
                                    "thinking_enabled": False,
                                    "output_schema": "phase",
                                },
                                "extra": {"meta": {"subChatType": "t2i"}},
                                "sub_chat_type": "t2i",
                                "parent_id": None,
                            }
                        ],
                        "timestamp": int(time.time()) + 1,
                        "size": "1:1",
                    }

                    async with session.post(
                        "https://chat.qwen.ai/api/v2/chat/completions",
                        params={"chat_id": chat_id},
                        json=json_data,
                        proxy=proxy
                    ) as resp:
                        if resp.status == 429:
                            acc_index += 1
                            continue
                        if resp.status != 200:
                            raise Exception(f"Completions failed: {resp.status}")

                        async for line in resp.content:
                            if not line:
                                continue
                            line = line.decode("utf-8").strip()
                            if not line.startswith("data: "):
                                continue
                            payload = line[len("data: "):]

                            if payload == "[DONE]":
                                break

                            try:
                                data = json.loads(payload)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    phase = delta.get("phase", "")
                                    if phase == "image_gen" and content.startswith("http"):
                                        await safe_delete(sent_message)
                                        await message.reply_photo(photo=content)
                                        return
                            except Exception:
                                continue

            except Exception as e:
                #print(f"Qwen error (acc {acc_index}): {e}")
                acc_index += 1
                continue

        await safe_delete(sent_message)
        await message.reply(_("qwenimg_err"))


async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass