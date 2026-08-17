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

albums_buffer = {}

SIZE_HINT = "Generate the one image at high resolution (around 2048x2048, or 2048x3072 / 3072x2048 depending on orientation), maximum detail, not a thumbnail."

QUALITY_HINT = "Ultra high quality, sharp focus, finely detailed, no compression artifacts, no blur, no pixelation, professional-grade rendering."

PSIDTS_PLACEHOLDER = "sidts-cookie"

LANGUAGE_HINT = (
    "If, for any reason (including hitting a usage limit or quota), you cannot "
    "generate the image right now, write that explanation in English."
)

_TRAILING_MARKER_RE = re.compile(r"[\s]*_\d+_?\s*$")

_cookie_pairs: list[tuple[str, str]] = []
_clients: list[GeminiClient | None] = []
_active_index = 0
_locked_at_zero = False
_client_lock = asyncio.Lock()


def _strip_trailing_marker(text: str | None) -> str:
    if not text:
        return ""
    return _TRAILING_MARKER_RE.sub("", text).strip()


def _is_junk_text(text: str | None) -> bool:
    return not _strip_trailing_marker(text)


def _ensure_cookie_state():
    global _cookie_pairs, _clients

    if not _cookie_pairs:
        _cookie_pairs = _parse_cookie_pairs()
        _clients = [None] * len(_cookie_pairs)


async def _get_or_create_client(idx: int) -> "GeminiClient":
    if _clients[idx] is None:
        psid, psidts = _cookie_pairs[idx]
        gclient = GeminiClient(psid, psidts, proxy=None)
        await gclient.init(timeout=300, auto_close=False, auto_refresh=False)
        gclient._bot_psid = psid
        gclient._bot_psidts = psidts
        _clients[idx] = gclient

    return _clients[idx]


async def get_active_client():
    async with _client_lock:
        _ensure_cookie_state()

        if not _cookie_pairs:
            return None, None

        idx = _active_index
        gclient = await _get_or_create_client(idx)
        return idx, gclient


async def handle_quota_exceeded(failed_idx: int):
    global _active_index, _locked_at_zero

    async with _client_lock:
        n = len(_cookie_pairs)
        if n <= 1:
            return

        if failed_idx == 0 and _locked_at_zero:
            return

        next_idx = (failed_idx + 1) % n
        _active_index = next_idx

        if next_idx == 0:
            _locked_at_zero = True


async def handle_success(succeeded_idx: int):
    global _locked_at_zero

    if succeeded_idx == 0 and _locked_at_zero:
        async with _client_lock:
            _locked_at_zero = False


def _is_quota_exceeded_text(text: str) -> bool:
    if not text:
        return False

    t = text.lower()

    if "limit" in t and ("reset" in t or "settings" in t or "usage" in t):
        return True

    ru_markers = ("лимит", "настройках", "сброшен")
    matched = [m for m in ru_markers if m in t]
    if len(matched) >= 2:
        return True

    return False


def _parse_cookie_pairs() -> list[tuple[str, str]]:
    psid_env = os.environ.get("GEMINI_SECURE_1PSID", "") or ""
    psidts_env = os.environ.get("GEMINI_SECURE_1PSIDTS", "") or ""

    psids = [p.strip() for p in psid_env.split(";")]
    psids = [p for p in psids if p]

    if not psids:
        return []

    if ";" in psidts_env:
        psidts_list = [p.strip() for p in psidts_env.split(";")]

        if len(psidts_list) < len(psids):
            psidts_list += [""] * (len(psids) - len(psidts_list))
        elif len(psidts_list) > len(psids):
            psidts_list = psidts_list[: len(psids)]

        psidts_list = [p if p else PSIDTS_PLACEHOLDER for p in psidts_list]
    else:
        single = psidts_env.strip()
        value = single if single else PSIDTS_PLACEHOLDER
        psidts_list = [value] * len(psids)

    return list(zip(psids, psidts_list))


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

    download_url = full_res_url

    try:
        try:
            await image.save(
                path=os.path.dirname(tmp_path),
                filename=os.path.basename(tmp_path),
                skip_invalid_filename=True,
            )
        except TypeError as te:
            if "skip_invalid_filename" in str(te):
                await image.save(
                    path=os.path.dirname(tmp_path),
                    filename=os.path.basename(tmp_path),
                )
            else:
                raise

        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            if _is_valid_image(tmp_path):
                return tmp_path
    except Exception:
        pass

    try:
        cookies = {
            "__Secure-1PSID": getattr(gclient, "_bot_psid", ""),
            "__Secure-1PSIDTS": getattr(gclient, "_bot_psidts", ""),
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, cookies=cookies, headers=headers) as http_client:
            resp = await http_client.get(download_url)

            if resp.status_code == 400 and download_url != original_url:
                resp = await http_client.get(original_url)

            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                f.write(resp.content)

        if os.path.getsize(tmp_path) > 0 and _is_valid_image(tmp_path):
            return tmp_path
    except Exception:
        pass

    return None


async def generate_image_gemini_web(user_input, image_paths=None):
    enhanced_prompt = f"Generate image: {user_input}. {SIZE_HINT} {QUALITY_HINT} {LANGUAGE_HINT}"

    _ensure_cookie_state()
    max_attempts = max(len(_cookie_pairs), 1)

    files = image_paths if image_paths else []
    tmp_dir = tempfile.mkdtemp()

    last_text = None
    tried_indexes = set()

    for attempt in range(max_attempts):
        idx, gclient = await get_active_client()

        if gclient is None:
            break

        if idx in tried_indexes:
            break

        tried_indexes.add(idx)

        try:
            if files:
                response = await gclient.generate_content(enhanced_prompt, files=files, model="gemini-flash-lite")
            else:
                response = await gclient.generate_content(enhanced_prompt, model="gemini-flash-lite")
        except Exception:
            return [], None

        image_paths_result = []
        response_text = None

        if response.images:
            for image in response.images:
                saved = await _save_image(image, tmp_dir, gclient)
                if saved:
                    image_paths_result.append(saved)

            if image_paths_result:
                await handle_success(idx)
                if response.text:
                    response_text = response.text
                return image_paths_result, response_text

        if response.text and _is_quota_exceeded_text(response.text):
            await handle_quota_exceeded(idx)
            last_text = response.text
            continue

        await handle_success(idx)

        if response.text:
            extracted_prompt = await extract_prompt_from_response(response.text)

            if extracted_prompt:
                try:
                    second_response = await gclient.generate_content(
                        f"{extracted_prompt}. {SIZE_HINT} {LANGUAGE_HINT}", model="gemini-flash-lite"
                    )
                except Exception:
                    second_response = None

                if second_response is not None:
                    if second_response.images:
                        for image in second_response.images:
                            saved = await _save_image(image, tmp_dir, gclient)
                            if saved:
                                image_paths_result.append(saved)

                        if image_paths_result:
                            if second_response.text:
                                response_text = second_response.text
                            return image_paths_result, response_text

                    if second_response.text and _is_quota_exceeded_text(second_response.text):
                        await handle_quota_exceeded(idx)
                        last_text = second_response.text
                        continue

                    if second_response.text:
                        response_text = second_response.text
            else:
                response_text = response.text

        return image_paths_result, response_text

    return [], last_text


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
                caption_text = _strip_trailing_marker(response_text) or None

                if len(generated_image_paths) == 1:
                    caption = caption_text[:1000] if caption_text else None
                    await _safe_reply_photo(message, FSInputFile(generated_image_paths[0]), caption)
                else:
                    await _safe_reply_media_group(message, generated_image_paths, caption_text)

            elif response_text:
                await safe_delete(sent_message)
                cleaned = _strip_trailing_marker(response_text)
                if not cleaned:
                    await message.reply(_("gemimg_err"))
                else:
                    await _safe_reply_text(message, cleaned)

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
                caption_text = _strip_trailing_marker(response_text) or None

                if len(generated_image_paths) == 1:
                    caption = caption_text[:1000] if caption_text else None
                    await _safe_reply_photo(message, FSInputFile(generated_image_paths[0]), caption)
                else:
                    await _safe_reply_media_group(message, generated_image_paths, caption_text)

            elif response_text:
                await safe_delete(sent_message)
                cleaned = _strip_trailing_marker(response_text)
                if not cleaned:
                    await message.reply(_("gemimg_err"))
                else:
                    await _safe_reply_text(message, cleaned)

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


async def _safe_reply_photo(message: Message, photo: FSInputFile, caption: str | None):
    try:
        await message.reply_photo(photo=photo, caption=caption, parse_mode="Markdown")
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            await message.reply_photo(photo=photo, caption=caption, parse_mode=None)
        else:
            raise


async def _safe_reply_media_group(message: Message, image_paths: list[str], response_text: str | None):
    def build(parse_mode):
        group = []
        for i, image_path in enumerate(image_paths):
            if i == 0 and response_text:
                group.append(
                    InputMediaPhoto(
                        media=FSInputFile(image_path),
                        caption=response_text[:1000],
                        parse_mode=parse_mode,
                    )
                )
            else:
                group.append(InputMediaPhoto(media=FSInputFile(image_path)))
        return group

    try:
        await message.reply_media_group(media=build("Markdown"))
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            await message.reply_media_group(media=build(None))
        else:
            raise


async def _safe_reply_text(message: Message, text: str):
    try:
        await message.reply(text[:4000], parse_mode="Markdown")
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            await message.reply(text[:4000], parse_mode=None)
        else:
            raise


async def safe_delete(message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass