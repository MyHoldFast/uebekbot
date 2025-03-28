from bs4 import BeautifulSoup, Tag, NavigableString
import html, re
import asyncio

SUPPORTED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote"}

async def remove_unsupported_tags(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        if tag.name not in SUPPORTED_TAGS:
            tag.unwrap()
    await asyncio.sleep(0)  # Уступка контроля событийному циклу

async def remove_think_tag(text):
    pattern = r'^<think>.*?</think>\s*'
    return re.sub(pattern, '', text, flags=re.DOTALL).strip()

async def sanitize_attributes(attrs: dict) -> dict:
    sanitized = {}
    for key, value in attrs.items():
        if key == 'href':
            sanitized[key] = html.escape(str(value), quote=True)
        else:
            sanitized[key] = html.escape(str(value))
    await asyncio.sleep(0)  # Уступка контроля событийному циклу
    return sanitized

async def build_open_tags(tag_stack: list[tuple[str, dict]]) -> str:
    result = ""
    for tag, attrs in tag_stack:
        if attrs:
            attr_str = " " + " ".join(f'{k}="{v}"' for k, v in attrs.items())
        else:
            attr_str = ""
        result += f"<{tag}{attr_str}>"
    await asyncio.sleep(0)  # Уступка контроля событийному циклу
    return result

async def build_close_tags(tag_stack: list[tuple[str, dict]]) -> str:
    result = ""
    for tag, _ in reversed(tag_stack):
        result += f"</{tag}>"
    await asyncio.sleep(0)  # Уступка контроля событийному циклу
    return result

async def split_html(text: str, max_length: int = 4096) -> list[str]:
    text = await remove_think_tag(text)
    soup = BeautifulSoup(text, 'html.parser')
    
    # Если тегов не найдено, считаем что это обычный текст
    if not soup.find(True):
        parts = []
        esc_text = html.escape(text)
        while esc_text:
            parts.append(esc_text[:max_length])
            esc_text = esc_text[max_length:]
        return parts

    await remove_unsupported_tags(soup)
    parts = []
    current_part = ""
    tag_stack: list[tuple[str, dict]] = []

    async def add_text(text_fragment: str):
        nonlocal current_part, parts
        esc_text = html.escape(text_fragment)
        while esc_text:
            available = max_length - len(current_part)
            if available <= 0:
                # Если длина текущей части достигла max_length, закрываем открытые теги и добавляем часть в parts
                current_part += await build_close_tags(tag_stack)
                parts.append(current_part)
                current_part = await build_open_tags(tag_stack)
                available = max_length - len(current_part)
            chunk = esc_text[:available]
            current_part += chunk
            esc_text = esc_text[available:]
            await asyncio.sleep(0)  # Уступка контроля событийному циклу

    async def process_node(node):
        nonlocal current_part, parts, tag_stack
        if isinstance(node, NavigableString):
            await add_text(str(node))
        elif isinstance(node, Tag):
            tag_name = node.name
            # Для тега <a> обязательно наличие href (иначе отбрасываем тег и обрабатываем только текст)
            if tag_name == 'a':
                attrs = await sanitize_attributes(node.attrs)
                if "href" not in attrs:
                    for child in node.contents:
                        await process_node(child)
                    return
            else:
                attrs = await sanitize_attributes(node.attrs)
            # Собираем открывающий тег
            if attrs:
                attr_str = " " + " ".join(f'{k}="{v}"' for k, v in attrs.items())
            else:
                attr_str = ""
            open_tag = f"<{tag_name}{attr_str}>"
            if len(current_part) + len(open_tag) > max_length:
                current_part += await build_close_tags(tag_stack)
                parts.append(current_part)
                current_part = await build_open_tags(tag_stack)
            current_part += open_tag
            tag_stack.append((tag_name, attrs))
            for child in node.contents:
                await process_node(child)
            close_tag = f"</{tag_name}>"
            if len(current_part) + len(close_tag) > max_length:
                current_part += await build_close_tags(tag_stack)
                parts.append(current_part)
                tag_stack.pop()
                current_part = await build_open_tags(tag_stack)
                current_part += close_tag
                tag_stack.append((tag_name, attrs))
            else:
                current_part += close_tag
            tag_stack.pop()
            await asyncio.sleep(0)  # Уступка контроля событийному циклу

    for node in soup.contents:
        await process_node(node)
    
    if current_part:
        # Закрываем оставшиеся теги, если они ещё остались открытыми (теоретически tag_stack должен быть пустым)
        current_part += await build_close_tags(tag_stack)
        parts.append(current_part)
    
    return parts