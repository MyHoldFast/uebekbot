import os
import tempfile
import asyncio
import json
from pathlib import Path

from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InputMediaPhoto
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from utils.typing_indicator import TypingIndicator
from utils.command_states import check_command_enabled
from localization import get_localization, DEFAULT_LANGUAGE

from gemini_webapi import GeminiClient
from gemini_webapi import set_log_level

set_log_level("CRITICAL")

router = Router()

client = None
client_lock = asyncio.Lock()
albums_buffer = {}


async def get_client():
    global client

    Secure_1PSID = os.environ.get("GEMINI_SECURE_1PSID")
    Secure_1PSIDTS = os.environ.get("GEMINI_SECURE_1PSIDTS")

    if not Secure_1PSID:
        return None

    async with client_lock:
        if client is None:
            client = GeminiClient(Secure_1PSID, Secure_1PSIDTS, proxy=None)
            await client.init(timeout=30)

        return client


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
                        except:
                            try:
                                inner_data = json.loads(action_input)
                            except:
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


async def generate_image_gemini_web(user_input, image_paths=None):
    try:
        enhanced_prompt = f"{user_input}. Generate a large, detailed, high-quality image."

        client = await get_client()
        if not client:
            return [], None

        files = image_paths if image_paths else []

        if files:
            response = await client.generate_content(enhanced_prompt, files=files)
        else:
            response = await client.generate_content(enhanced_prompt)

        image_paths_result = []
        response_text = None

        if response.images:
            for image in response.images:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    tmp_path = tmp_file.name

                await image.save(
                    path=os.path.dirname(tmp_path),
                    filename=os.path.basename(tmp_path),
                    skip_invalid_filename=True
                )
                image_paths_result.append(tmp_path)

            if response.text:
                response_text = response.text

        elif response.text:
            extracted_prompt = await extract_prompt_from_response(response.text)

            if extracted_prompt:
                second_response = await client.generate_content(extracted_prompt)

                if second_response.images:
                    for image in second_response.images:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                            tmp_path = tmp_file.name

                        await image.save(
                            path=os.path.dirname(tmp_path),
                            filename=os.path.basename(tmp_path),
                            skip_invalid_filename=True
                        )
                        image_paths_result.append(tmp_path)

                    if second_response.text:
                        response_text = second_response.text
                elif second_response.text:
                    response_text = second_response.text
            else:
                response_text = response.text

        return image_paths_result, response_text

    except Exception:
        return [], None


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
@check_command_enabled("gemimg")
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
@check_command_enabled("gemimg")
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

        if message.reply_to_message.caption:
            user_input = message.reply_to_message.caption
        elif message.reply_to_message.text:
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
                
