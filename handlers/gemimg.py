import os
import logging
import tempfile
import asyncio
import aiohttp
import aiofiles

from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InputMediaPhoto
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from localization import get_localization, DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)

router = Router()
albums_buffer = {}

NANO_BANANA_BASE_URL = "https://nanobanana.aikit.club"


async def download_image(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.error(f"Failed to download generated image: {resp.status}")
                return None
            suffix = ".png"
            content_type = resp.headers.get("Content-Type", "")
            if "jpeg" in content_type or "jpg" in content_type:
                suffix = ".jpg"
            elif "webp" in content_type:
                suffix = ".webp"

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp_path = tmp.name

            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(await resp.read())

            return tmp_path
    except Exception:
        logger.exception("Failed to download generated image")
        return None


async def download_telegram_photo(bot: Bot, photo) -> str | None:
    try:
        file = await bot.get_file(photo.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            tmp_path = tmp_file.name
        await bot.download_file(file.file_path, destination=tmp_path)
        return tmp_path
    except Exception:
        logger.exception(f"Failed to download telegram photo {photo.file_id}")
        return None


async def generate_image_nano_banana(
    user_input: str, image_paths: list[str] | None = None
) -> tuple[list[str], str | None]:
    result_paths: list[str] = []
    response_text: str | None = None

    try:
        async with aiohttp.ClientSession() as session:
            if image_paths:
                url = f"{NANO_BANANA_BASE_URL}/v1/images/edits"
                data = aiohttp.FormData()
                data.add_field("prompt", user_input)
                data.add_field("model", "nano-banana")
                data.add_field("response_format", "url")

                async with aiofiles.open(image_paths[0], "rb") as f:
                    image_bytes = await f.read()

                data.add_field(
                    "image",
                    image_bytes,
                    filename=os.path.basename(image_paths[0]),
                    content_type="image/jpeg",
                )

                async with session.post(url, data=data) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(f"Nano Banana edit request failed: {resp.status} {body}")
                        return [], None
                    payload = await resp.json()
            else:
                url = f"{NANO_BANANA_BASE_URL}/v1/images/generations"
                body = {
                    "prompt": user_input,
                    "model": "nano-banana",
                    "n": 1,
                    "aspect_ratio": "1:1",
                    "response_format": "url",
                }

                async with session.post(url, json=body) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error(f"Nano Banana generate request failed: {resp.status} {error_body}")
                        return [], None
                    payload = await resp.json()

            images = payload.get("data", [])
            for item in images:
                image_url = item.get("url")
                if not image_url:
                    continue
                local_path = await download_image(session, image_url)
                if local_path:
                    result_paths.append(local_path)

            response_text = payload.get("text") or payload.get("message") or None

    except Exception:
        logger.exception("Nano Banana request failed")
        return [], None

    return result_paths, response_text


async def send_result(message: Message, sent_message: Message, generated_image_paths: list[str], response_text: str | None, err_text: str):
    if generated_image_paths:
        await safe_delete(sent_message)

        if len(generated_image_paths) == 1:
            caption = response_text[:1000] if response_text else None
            await message.reply_photo(
                photo=FSInputFile(generated_image_paths[0]),
                caption=caption,
                parse_mode="Markdown",
            )
        else:
            media_group = []
            for i, image_path in enumerate(generated_image_paths):
                if i == 0 and response_text:
                    media_group.append(
                        InputMediaPhoto(
                            media=FSInputFile(image_path),
                            caption=response_text[:1000],
                            parse_mode="Markdown",
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
        await message.reply(err_text)


@check_command_enabled("gemimg")
async def process_gemimg(message: Message, bot: Bot, user_input: str, photos):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    input_image_paths = []
    for photo in photos:
        path = await download_telegram_photo(bot, photo)
        if path:
            input_image_paths.append(path)

    if photos and not input_image_paths:
        await message.reply(_("gemimg_err"))
        return

    if not user_input:
        await message.reply(_("gemimghelp"))
        for path in input_image_paths:
            if os.path.exists(path):
                os.remove(path)
        return

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        sent_message = await message.reply(_("qwenimg_gen"))

        generated_image_paths = []
        response_text = None

        try:
            generated_image_paths, response_text = await generate_image_nano_banana(
                user_input, input_image_paths
            )
            await send_result(message, sent_message, generated_image_paths, response_text, _("gemimg_err"))
        except Exception:
            logger.exception("process_gemimg failed")
            await safe_delete(sent_message)
            await message.reply(_("gemimg_err"))
        finally:
            for path in input_image_paths + generated_image_paths:
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
        elif message.reply_to_message.caption:
            user_input = message.reply_to_message.caption

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
            generated_image_paths, response_text = await generate_image_nano_banana(user_input)
            await send_result(message, sent_message, generated_image_paths, response_text, _("gemimg_err"))
        except Exception:
            logger.exception("cmd_gemimg failed")
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