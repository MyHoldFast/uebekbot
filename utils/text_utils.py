from bs4 import BeautifulSoup, Tag

SUPPORTED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre"}

def remove_unsupported_tags(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        if tag.name not in SUPPORTED_TAGS:
            tag.unwrap()

def close_open_tags(stack: list[tuple[str, dict]]) -> str:
    return ''.join(f'</{tag}>' for tag, _ in reversed(stack))

def reopen_tags(stack: list[tuple[str, dict]]) -> str:
    return ''.join(
        f'<{tag} ' + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + '>' if attrs else f'<{tag}>'
        for tag, attrs in stack
    )

def split_html(text: str, max_length: int = 4096) -> list[str]:
    soup = BeautifulSoup(text, 'html.parser')
    remove_unsupported_tags(soup)
    
    parts: list[str] = []
    current_part: str = ''
    stack: list[tuple[str, dict]] = []

    def recursive_split(element: Tag | str) -> None:
        nonlocal current_part, stack
        if isinstance(element, Tag):
            attrs = ' '.join(f'{k}="{v}"' for k, v in element.attrs.items())
            tag_start = f"<{element.name}{' ' + attrs if attrs else ''}>"
            tag_end = f"</{element.name}>"
            stack.append((element.name, element.attrs))
            
            if len(current_part) + len(tag_start) > max_length:
                if current_part:
                    parts.append(current_part + close_open_tags(stack))
                current_part = reopen_tags(stack) + tag_start
            else:
                current_part += tag_start

            for child in element.contents:
                recursive_split(child)

            if len(current_part) + len(tag_end) > max_length:
                if current_part:
                    parts.append(current_part + close_open_tags(stack))
                current_part = reopen_tags(stack) + tag_end
            else:
                current_part += tag_end

            stack.pop()
        elif isinstance(element, str):
            while element:
                available_space = max_length - len(current_part)
                if available_space <= 0:
                    if current_part:
                        parts.append(current_part + close_open_tags(stack))
                    current_part = reopen_tags(stack)
                    available_space = max_length - len(current_part)
                chunk, element = element[:available_space], element[available_space:]
                current_part += chunk

    for el in soup.contents:
        recursive_split(el)

    if current_part:
        parts.append(current_part + close_open_tags(stack))
    
    return parts
