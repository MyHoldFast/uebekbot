import os
import json
import requests
from dotenv import load_dotenv

dotenv_utils_path = os.path.join(os.path.dirname(__file__), ".pass")
load_dotenv(dotenv_utils_path)
email_base = os.getenv("QWEN_EMAIL")
password = os.getenv("QWEN_PASSWORD")

url = "https://chat.qwen.ai/api/v1/auths/signin"
headers = {
    "Content-Type": "application/json",
    "Origin": "https://chat.qwen.ai",
    "Referer": "https://chat.qwen.ai/",
    "User-Agent": "Mozilla/5.0",
}

tokens = []
for i in range(10):
    email = email_base if i == 0 else email_base.replace("@", f"+{i}@")
    payload = {"email": email, "password": password}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if token:
            tokens.append({"bearer": token})
    except Exception:
        pass

tokens_json = json.dumps(tokens, ensure_ascii=False)
main_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
env_key = "QWEN_ACCS"
new_line = f'{env_key}={tokens_json}\n'

if os.path.exists(main_env_path):
    with open(main_env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{env_key}="):
            lines[i] = new_line
            updated = True
            break

    if not updated:
        lines.append(new_line)
else:
    lines = [new_line]

with open(main_env_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("✅ QWEN_ACCS успешно обновлён.")