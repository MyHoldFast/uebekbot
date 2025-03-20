from bs4 import BeautifulSoup, Tag
import html

SUPPORTED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote"}

def remove_unsupported_tags(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        if tag.name not in SUPPORTED_TAGS:
            tag.unwrap()

def sanitize_attributes(attrs: dict) -> dict:
    sanitized = {}
    for key, value in attrs.items():
        sanitized[key] = html.escape(str(value))
    return sanitized

def split_html(text: str, max_length: int = 4096) -> list[str]:
    soup = BeautifulSoup(text, 'html.parser')
    remove_unsupported_tags(soup)

    parts = []
    current_part = ""
    tag_stack = []

    def add_tag_to_stack(tag_name: str, attrs: dict) -> str:
        tag_stack.append((tag_name, attrs))
        attrs_str = ' '.join(f'{k}="{v}"' for k, v in attrs.items())
        return f"<{tag_name}{' ' + attrs_str if attrs_str else ''}>"

    def close_tags_from_stack() -> str:
        return ''.join(f"</{tag}>" for tag, _ in reversed(tag_stack))

    def reopen_tags_from_stack() -> str:
        return ''.join(f"<{tag}{' ' + ' '.join(f'{k}="{v}"' for k, v in attrs.items())}>" for tag, attrs in tag_stack)

    def process_element(element) -> None:
        nonlocal current_part

        if isinstance(element, Tag):
            tag_name = element.name
            attrs = sanitize_attributes(element.attrs)
            tag_start = add_tag_to_stack(tag_name, attrs)

            if len(current_part) + len(tag_start) > max_length:
                parts.append(current_part + close_tags_from_stack())
                current_part = reopen_tags_from_stack() + tag_start
            else:
                current_part += tag_start

            for child in element.contents:
                process_element(child)

            tag_end = f"</{tag_name}>"
            if len(current_part) + len(tag_end) > max_length:
                parts.append(current_part + close_tags_from_stack())
                current_part = reopen_tags_from_stack() + tag_end
            else:
                current_part += tag_end

            tag_stack.pop()

        elif isinstance(element, str):
            text = element
            while text:
                available_space = max_length - len(current_part)
                if available_space <= 0:
                    parts.append(current_part + close_tags_from_stack())
                    current_part = reopen_tags_from_stack()
                    available_space = max_length - len(current_part)

                chunk = text[:available_space]
                current_part += html.escape(chunk)
                text = text[available_space:]

    for element in soup.contents:
        process_element(element)

    if current_part:
        parts.append(current_part + close_tags_from_stack())

    for i in range(len(parts) - 1):
        open_tags = [tag for tag, _ in tag_stack]
        for tag in reversed(open_tags):
            if f'<{tag}' in parts[i] and f'</{tag}>' not in parts[i]:
                parts[i] += f'</{tag}>'
                parts[i + 1] = f'<{tag}>' + parts[i + 1]

    return parts