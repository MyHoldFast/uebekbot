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

from pylatexenc.latex2text import LatexNodes2Text
import re

context_db, ContextQuery = DB("db/qwen_context.json").get_db()
router = Router()

qwen_accs_str = os.getenv("QWEN_ACCS")
qwen_accs = json.loads(qwen_accs_str)

acc_index = 0
last_update_time = None

MESSAGE_EXPIRY = 3 * 60 * 60

proxy = os.getenv("PROXY")


def load_messages(user_id):
    context_item = context_db.get(ContextQuery().uid == user_id)
    if context_item:
        messages = json.loads(context_item.get("messages", "[]"))
        timestamp = float(context_item.get("timestamp", 0))
        if time.time() - timestamp < MESSAGE_EXPIRY:
            return messages
    return []


def save_messages(user_id, messages):
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

cookies = {
    'ssxmod_itna': 'Gu0Q0I4fx+xGxiqYQKYvq7QGODOf3GRDODl4BtiD2DIqGQGcD8hq0p8pFbKGkG9g3WGx5Yq7QGWx4SD05qPmDY5GS+xi3Dar39r5StjurqdtgjLbEvY7tBDev3Fu0=T5chLmZxAixCPGnD064BBdbDYYDC4GwDGoD34DiDDPDb3iDAqeD7qDF+lb=yCbLDYpY24DmDGAYHQ3oDDtDiMNQFhb5DDN5S=+qtjGTHZXADxqQd7aK7YbDjkPD/bhA1YR7pI85/CapOUWIFeGye5Gu9eeiqeq8AQWtdpe+7+Ybl+qmW0ohKA4YCDxiYoMGsQYY3A4Rk55A4AxstYhp75S0zmDDiEq5mIb0xXDx4r+2OtnEt9r4mQvM7vatitCD2CGxCKbDK1nwseesWD5lbbG0dBqtAG4gDxD',
    'ssxmod_itna2': 'Gu0Q0I4fx+xGxiqYQKYvq7QGODOf3GRDODl4BtiD2DIqGQGcD8hq0p8pFbKGkG9g3WGx5Yq7QGWx4mDDPot5YEAbPDL0hwwfPGFOyxDlPuHcOQ9RrQhRd9UTQmu27W7de2F3NCLq2Dcu2FQGytSEPHBEiOqGI7FPw+PnHQ4E5e=4O1uWv5/27QFPe78rOa2=8OHUukszImGxaa5IK15YMFqDMxQzBGCQGau49rP9d7sCLiGxr15FD7sKA4hpaRE10OKsi244L+45B7=b8G5WxzpP7Pqtu6IdI+HF0kw2oICjyhgtqra2GlE2Q5fiY8tMBQiYiuTQIM3rStwgbV8dhhbH+xNmhHnF3qbFhxU+1TQbMM+kgCWSw74493KeQGCEQh+zBu8BoC3Cb34bkgO+ktQbW6kKxZ=m3NPji2AA0uIp8t/uDBrTCj+MjtND+CMad6Qr3GhwGNTTx=QREtPBtmbr186Zea+LDvMAUxa8E5ygNtqFtid2EU723TLrDgUA6Nq2F57X3g3RuHsL3sh1OwNIZr5hrnhL83iDuN=CK94mmKQ6lDCCbCBfA=GP2bywHyM3I8s94d1qfl7d3Da9bxZKfrbcI3fhrd8O2qdO3YHH4fYfO/uxXEiDCgvrg8oAHkdlxFSrRgbTHvCarxGahx+qMibS7zqr5YeBI44H+OqTdkIr=irN0xe0gDb/Ti0s7WamDgvG0FbbaQDriPmdqAi0GkvOpCa4FW57qeBDnb9phV2UAGqG+BP92LQGp7aC+5m4tP9RHBNP2DlhvyPYzY7WBD7W4OWj5+p7qqS=3422EeZKYxGPEqmm=yAmPYId/Ni0C6qW2AehqqK=Q3qNtpN0uBhv4qjdmiPiemGqAIm09AqZ0Nee/Gmj7SDoWwqiWi5SDeAq4D'
}

headers = {
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'DNT': '1',
    'Origin': 'https://chat.qwen.ai',
    'Pragma': 'no-cache',
    'Referer': 'https://chat.qwen.ai/c/a8c98a2d-9910-477e-9499-c0ab26e0bcc2',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    "authorization": "Bearer " + qwen_accs[0]["bearer"],
}


@router.message(Command("qwen", ignore_case=True))
@check_command_enabled("qwen")
async def cmd_qwen(message: Message, command: CommandObject, bot: Bot):
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
        await message.reply(_("qwen_help"))
        return

    user_id = message.from_user.id
    messages = load_messages(user_id)

    messages.append(
        {
            "role": "user",
            "content": user_input,
            "chat_type": "t2t",
            "extra": {},
            "feature_config": {"thinking_enabled": False},
        }
    )
    
    url = "https://chat.qwen.ai/api/chat/completions"
    data = {
        "stream": False,
        "incremental_output": False,
        "chat_type": "t2t",
        "model": "qwen3-235b-a22b",
        "messages": messages,
        "session_id": str(uuid.uuid4()),
        "chat_id": str(uuid.uuid4()),
        "id": str(uuid.uuid4()),
    }

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        async with aiohttp.ClientSession(cookies=cookies) as session:
            try:
                async with session.post(url, headers=headers, json=data, timeout=120, proxy=proxy) as r:
                    if r.status == 200:
                        result = await r.json()
                        assistant_reply = (
                            result.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "Ошибка")
                        )

                        formatted_reply = process_latex(telegram_format(assistant_reply))
                        chunks = split_html(formatted_reply)

                        for chunk in chunks:
                            #soup = BeautifulSoup(html.unescape(chunk), "html.parser")
                            #fixed = soup.encode(formatter="minimal").decode("utf-8")                        
                            #try:
                            await message.reply(chunk, parse_mode="HTML")
                            #except Exception:
                            #    await message.reply(soup.get_text())

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

    url = "https://chat.qwen.ai/api/chat/completions"
    data = {
        "stream": False,
        "chat_type": "t2i",
        "model": "qwen3-235b-a22b",
        "size": "1280*720",
        "messages": [{"role": "user", "content": user_input}],
        "id": str(uuid.uuid4()),
        "chat_id": str(uuid.uuid4()),
    }

    async def make_request(session, url, headers, data, message, sent_message):
        global acc_index, last_update_time

        headers["Authorization"] = "Bearer " + qwen_accs[acc_index]["bearer"]

        async with session.post(url, headers=headers, cookies=cookies, json=data, timeout=120, proxy=proxy) as r:
            try:
                if r.status == 200:
                    result = await r.json()
                    task_id = result["messages"][1]["extra"]["wanx"]["task_id"]
                    await check_task_status(session, task_id, message, sent_message)
                elif r.status == 429:
                    if last_update_time is not None:
                        time_diff = time.time() - last_update_time
                        if time_diff > 86400:
                            acc_index = 0

                    if acc_index + 1 < len(qwen_accs):
                        acc_index += 1
                        last_update_time = time.time()
                        await session.close()
                        async with aiohttp.ClientSession() as new_session:
                            try:
                                await make_request(
                                    new_session,
                                    url,
                                    headers,
                                    data,
                                    message,
                                    sent_message,
                                )
                            except Exception:
                                await safe_delete(sent_message)
                                await message.reply(_("qwenimg_err"))
                    else:
                        await safe_delete(sent_message)
                        await message.reply(_("qwenimg_err"))
                else:
                    await safe_delete(sent_message)
                    await message.reply(_("qwenimg_err"))
            except Exception:
                await safe_delete(sent_message)
                await message.reply(_("qwenimg_err"))

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        sent_message = await message.reply(_("qwenimg_gen"))

        async with aiohttp.ClientSession(cookies=cookies) as session:
            await make_request(session, url, headers, data, message, sent_message)


async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def check_task_status(session, task_id, message, sent_message):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)
    status_url = f"https://chat.qwen.ai/api/v1/tasks/status/{task_id}"
    while True:
        async with session.get(status_url, headers=headers, timeout=180, proxy=proxy) as r:
            try:
                if r.status == 200:
                    result = await r.json()
                    task_status = result.get("task_status", "")
                    if task_status == "success":
                        image_url = result.get("content", "")
                        await safe_delete(sent_message)
                        await message.reply_photo(photo=image_url)
                        break
                    elif task_status in ["failed", "error"]:
                        await safe_delete(sent_message)
                        await message.reply(_("qwenimg_err"))
                        break
                    else:
                        await asyncio.sleep(5)
                else:
                    await safe_delete(sent_message)
                    await message.reply(_("qwenimg_err"))
                    break
            except Exception:
                await safe_delete(sent_message)
                await message.reply(_("qwenimg_err"))
                break
