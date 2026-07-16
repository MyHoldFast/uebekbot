import os
import re
import tempfile
import asyncio
import json

import httpx
from PIL import Image as PILImage

from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InputMediaPhoto
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from localization import get_localization, DEFAULT_LANGUAGE

from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model

router = Router()

client = None
client_lock = asyncio.Lock()
albums_buffer = {}

SIZE_HINT = "Generate the image at standard resolution (around 1024x1024, or 1024x1536 / 1536x1024 depending on orientation), high detail, not a thumbnail."


async def get_client():
    global client

    Secure_1PSID = os.environ.get("GEMINI_SECURE_1PSID")
    Secure_1PSIDTS = os.environ.get("GEMINI_SECURE_1PSIDTS")

    if not Secure_1PSID:
        return None

    async with client_lock:
        if client is None:
            client = GeminiClient(Secure_1PSID, Secure_1PSIDTS, proxy=None)
            await client.init(timeout=300, auto_close=False, auto_refresh=False)

        return client


def _full_res_url(url: str) -> str:
    if not url:
        return url

    if url.endswith("=s0"):
        return url

    m = re.match(r"^(.*)=([swh][\w\-]*)$", url)
    if m:
        return f"{m.group(1)}=s0"

    return f"{url}=s0"


def _is_valid_image(path: str) -> bool:
    try:
        with PILImage.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


async def extract_prompt_from_response(text):
    try:
        if not text or not isinstance(text, str):
            return None

        text = text.strip()

        if '"action": "image_generation"' in text:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and data.get("action") == "image_generation":
                    action_input = data.get("action_input", "")

                    if isinstance(action_input, str):
                        try:
                            inner_data = json.loads(action_input.replace("'", '"'))
                        except Exception:
                            try:
                                inner_data = json.loads(action_input)
                            except Exception:
                                return None

                        prompt = inner_data.get("prompt")
                        if prompt:
                            return prompt
                    elif isinstance(action_input, dict):
                        prompt = action_input.get("prompt")
                        if prompt:
                            return prompt
            except json.JSONDecodeError:
                return None

        return None
    except Exception:
        return None


async def _save_image(image, tmp_dir: str, gclient: "GeminiClient") -> str | None:
    tmp_path = os.path.join(tmp_dir, f"{next(tempfile._get_candidate_names())}.png")

    original_url = image.url
    full_res_url = _full_res_url(original_url)
    if full_res_url != original_url:
        image.url = full_res_url

    try:
        await image.save(
            path=os.path.dirname(tmp_path),
            filename=os.path.basename(tmp_path),
            skip_invalid_filename=True,
        )
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            if _is_valid_image(tmp_path):
                return tmp_path
    except Exception:
        pass

    try:
        cookies = {
            "__Secure-1PSID": os.environ.get("GEMINI_SECURE_1PSID", ""),
            "__Secure-1PSIDTS": os.environ.get("GEMINI_SECURE_1PSIDTS", ""),
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, cookies=cookies, headers=headers) as http_client:
            resp = await http_client.get(image.url)
            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                f.write(resp.content)

        if os.path.getsize(tmp_path) > 0 and _is_valid_image(tmp_path):
            return tmp_path
    except Exception:
        pass

    return None


async def generate_image_gemini_web(user_input, image_paths=None):
    enhanced_prompt = f"Generate image: {user_input}. {SIZE_HINT}"

    gclient = await get_client()
    if not gclient:
        return [], None

    files = image_paths if image_paths else []
    tmp_dir = tempfile.mkdtemp()

    try:
        if files:
            response = await gclient.generate_content(enhanced_prompt, files=files, model=Model.BASIC_FLASH)
        else:
            response = await gclient.generate_content(enhanced_prompt, model=Model.BASIC_FLASH)

        image_paths_result = []
        response_text = None

        if response.images:
            for image in response.images:
                saved = await _save_image(image, tmp_dir, gclient)
                if saved:
                    image_paths_result.append(saved)

            if image_paths_result:
                if response.text:
                    response_text = response.text
                return image_paths_result, response_text

        if response.text:
            extracted_prompt = await extract_prompt_from_response(response.text)

            if extracted_prompt:
                second_response = await gclient.generate_content(
                    f"{extracted_prompt}. {SIZE_HINT}", model=Model.BASIC_FLASH
                )

                if second_response.images:
                    for image in second_response.images:
                        saved = await _save_image(image, tmp_dir, gclient)
                        if saved:
                            image_paths_result.append(saved)

                    if image_paths_result:
                        if second_response.text:
                            response_text = second_response.text
                        return image_paths_result, response_text

                if second_response.text:
                    response_text = second_response.text
            else:
                response_text = response.text

        return image_paths_result, response_text

    except Exception:
        return [], None


@check_command_enabled("gemimg")
async def process_gemimg(message: Message, bot: Bot, user_input: str, photos):
    input_image_paths = []
    for photo in photos:
        try:
            file = await bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                await bot.download_file(file.file_path, destination=tmp_file)
                input_image_paths.append(tmp_file.name)
        except Exception:
            pass

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input:
        await message.reply(_("gemimghelp"))
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        sent_message = await message.reply(_("qwenimg_gen"))

        generated_image_paths = []
        response_text = None

        try:
            generated_image_paths, response_text = await generate_image_gemini_web(
                user_input, input_image_paths
            )

            if generated_image_paths:
                await safe_delete(sent_message)

                if len(generated_image_paths) == 1:
                    caption = response_text[:1000] if response_text else None
                    await message.reply_photo(
                        photo=FSInputFile(generated_image_paths[0]),
                        caption=caption,
                        parse_mode="Markdown"
                    )
                else:
                    media_group = []
                    for i, image_path in enumerate(generated_image_paths):
                        if i == 0 and response_text:
                            caption = response_text[:1000]
                            media_group.append(
                                InputMediaPhoto(
                                    media=FSInputFile(image_path),
                                    caption=caption,
                                    parse_mode="Markdown"
                                )
                            )
                        else:
                            media_group.append(InputMediaPhoto(media=FSInputFile(image_path)))

                    await message.reply_media_group(media=media_group)

            elif response_text:
                await safe_delete(sent_message)
                await message.reply(response_text[:4000], parse_mode="Markdown")

            else:
                await safe_delete(sent_message)
                await message.reply(_("gemimg_err"))

        except Exception:
            await safe_delete(sent_message)
            await message.reply(_("gemimg_err"))

        finally:
            for path in (input_image_paths + generated_image_paths):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass


@router.message(F.media_group_id)
async def handle_album_command(message: Message, bot: Bot):
    mgid = message.media_group_id

    if mgid not in albums_buffer:
        albums_buffer[mgid] = []

        async def finalize():
            await asyncio.sleep(0.7)
            messages = albums_buffer.pop(mgid, [])

            if not messages:
                return

            caption = messages[0].caption or ""

            if not caption.startswith("/gemimg"):
                return

            user_input = caption.replace("/gemimg", "").strip()

            reply_photos = []
            if messages[0].reply_to_message and messages[0].reply_to_message.photo:
                reply_photos.append(messages[0].reply_to_message.photo[-1])

            photos = reply_photos + [m.photo[-1] for m in messages if m.photo]

            await process_gemimg(messages[0], bot, user_input, photos)

        asyncio.create_task(finalize())

    albums_buffer[mgid].append(message)


@router.message(F.photo, F.caption.startswith("/gemimg"))
async def handle_single_photo_with_caption(message: Message, bot: Bot):
    user_input = message.caption.replace("/gemimg", "").strip()
    photos = [message.photo[-1]]

    if message.reply_to_message and message.reply_to_message.photo:
        photos.insert(0, message.reply_to_message.photo[-1])

    await process_gemimg(message, bot, user_input, photos)


@router.message(Command("gemimg", ignore_case=True))
@check_command_enabled("gemimg")
async def cmd_gemimg(message: Message, command: CommandObject, bot: Bot):
    user_input = ""
    photos = []

    if message.reply_to_message and message.reply_to_message.photo:
        photos.append(message.reply_to_message.photo[-1])

    if message.reply_to_message:
        if message.reply_to_message.text:
            user_input = message.reply_to_message.text

    if message.photo:
        photos.append(message.photo[-1])

    if command.args and command.args.strip():
        user_input += ("\n" if user_input else "") + command.args.strip()

    if photos:
        await process_gemimg(message, bot, user_input, photos)
        return

    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    if not user_input.strip():
        await message.reply(_("gemimghelp"))
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        sent_message = await message.reply(_("qwenimg_gen"))

        generated_image_paths = []
        response_text = None

        try:
            generated_image_paths, response_text = await generate_image_gemini_web(user_input)

            if generated_image_paths:
                await safe_delete(sent_message)

                if len(generated_image_paths) == 1:
                    caption = response_text[:1000] if response_text else None
                    await message.reply_photo(
                        photo=FSInputFile(generated_image_paths[0]),
                        caption=caption,
                        parse_mode="Markdown"
                    )
                else:
                    media_group = []
                    for i, image_path in enumerate(generated_image_paths):
                        if i == 0 and response_text:
                            caption = response_text[:1000]
                            media_group.append(
                                InputMediaPhoto(
                                    media=FSInputFile(image_path),
                                    caption=caption,
                                    parse_mode="Markdown"
                                )
                            )
                        else:
                            media_group.append(InputMediaPhoto(media=FSInputFile(image_path)))

                    await message.reply_media_group(media=media_group)

            elif response_text:
                await safe_delete(sent_message)
                await message.reply(response_text[:4000], parse_mode="Markdown")

            else:
                await safe_delete(sent_message)
                await message.reply(_("gemimg_err"))

        except Exception:
            await safe_delete(sent_message)
            await message.reply(_("gemimg_err"))

        finally:
            for path in generated_image_paths:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass


async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass