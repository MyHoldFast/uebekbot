from bs4 import BeautifulSoup, Tag, NavigableString
import html

SUPPORTED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote"}

def remove_unsupported_tags(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        if tag.name not in SUPPORTED_TAGS:
            tag.unwrap()

def sanitize_attributes(attrs: dict) -> dict:
    sanitized = {}
    for key, value in attrs.items():
        if key == 'href':
            sanitized[key] = html.escape(str(value), quote=True)
        else:
            sanitized[key] = html.escape(str(value))
    return sanitized

def build_open_tags(tag_stack: list[tuple[str, dict]]) -> str:
    result = ""
    for tag, attrs in tag_stack:
        if attrs:
            attr_str = " " + " ".join(f'{k}="{v}"' for k, v in attrs.items())
        else:
            attr_str = ""
        result += f"<{tag}{attr_str}>"
    return result

def build_close_tags(tag_stack: list[tuple[str, dict]]) -> str:
    result = ""
    for tag, _ in reversed(tag_stack):
        result += f"</{tag}>"
    return result

def split_html(text: str, max_length: int = 4096) -> list[str]:
    soup = BeautifulSoup(text, 'html.parser')
    remove_unsupported_tags(soup)
    parts = []
    current_part = ""
    tag_stack: list[tuple[str, dict]] = []

    def add_text(text_fragment: str):
        nonlocal current_part, parts
        esc_text = html.escape(text_fragment)
        while esc_text:
            available = max_length - len(current_part)
            if available <= 0:
                current_part += build_close_tags(tag_stack)
                parts.append(current_part)
                current_part = build_open_tags(tag_stack)
                available = max_length - len(current_part)
            chunk = esc_text[:available]
            current_part += chunk
            esc_text = esc_text[available:]
    
    def process_node(node):
        nonlocal current_part, parts, tag_stack
        if isinstance(node, NavigableString):
            add_text(str(node))
        elif isinstance(node, Tag):
            tag_name = node.name
            if tag_name == 'a':
                attrs = sanitize_attributes(node.attrs)
                if "href" not in attrs:
                    for child in node.contents:
                        process_node(child)
                    return
            else:
                attrs = sanitize_attributes(node.attrs)
            if attrs:
                attr_str = " " + " ".join(f'{k}="{v}"' for k, v in attrs.items())
            else:
                attr_str = ""
            open_tag = f"<{tag_name}{attr_str}>"
            if len(current_part) + len(open_tag) > max_length:
                current_part += build_close_tags(tag_stack)
                parts.append(current_part)
                current_part = build_open_tags(tag_stack)
            current_part += open_tag
            tag_stack.append((tag_name, attrs))
            for child in node.contents:
                process_node(child)
            close_tag = f"</{tag_name}>"
            if len(current_part) + len(close_tag) > max_length:
                current_part += build_close_tags(tag_stack)
                parts.append(current_part)
                tag_stack.pop()
                current_part = build_open_tags(tag_stack)
                current_part += close_tag
                tag_stack.append((tag_name, attrs))
            else:
                current_part += close_tag
            tag_stack.pop()
    
    for node in soup.contents:
        process_node(node)
    
    if current_part:
        current_part += build_close_tags(tag_stack)
        parts.append(current_part)
    
    return parts