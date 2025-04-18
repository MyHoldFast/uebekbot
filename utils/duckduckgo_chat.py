import requests
import json
import re
from duckai.libs.utils_chat import HashBuilder

class DuckDuckGoChat:
    chat_url = "https://duckduckgo.com/duckchat/v1/chat"
    init_url = "https://duckduckgo.com/?q=DuckDuckGo&ia=chat"
    status_url = "https://duckduckgo.com/duckchat/v1/status"

    common_headers = {
        "accept": "text/event-stream",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "dnt": "1",
        "origin": "https://duckduckgo.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://duckduckgo.com/",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    }

    def __init__(self, model="gpt-4o-mini", proxy=None):
        self.model = model
        self.proxy = proxy
        self.messages = []
        self.vqd = None
        self.vqd_hash = None
        self.fe_version = None
        self.cookies = {"dcs": "1", "dcm": "3"}
        self._hashbuilder = HashBuilder()


    def chat(self, user_input, timeout=30):
        if not self.fe_version and not self.vqd and not self.vqd_hash:
            self.fe_version = self._fetch_fe_version()

        if not self.vqd or not self.vqd_hash:
            self.vqd, self.vqd_hash = self._fetch_vqd()

        self.messages.append({"role": "user", "content": user_input})
        payload = {
            "model": self.model,
            "messages": self.messages,
        }

        headers = self.common_headers.copy()
        headers["x-fe-version"] = self.fe_version
        headers["x-vqd-4"] = self.vqd
        headers["x-vqd-hash-1"] = self._hashbuilder.build_hash(self.vqd_hash, headers)

        #print("HEADERS:", headers)
        #print("VQD HASH BEFORE:", self.vqd_hash)
        #print("BUILT HASH:", self._hashbuilder.build_hash(self.vqd_hash, headers))


        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        response = requests.post(
            self.chat_url,
            headers=headers,
            cookies=self.cookies,
            json=payload,
            stream=True,
            proxies=proxies,
            timeout=timeout
        )

        if response.status_code != 200:
            raise Exception(f"Failed to send message: {response.status_code}")

        self.vqd = response.headers.get("x-vqd-4", self.vqd)
        self.vqd_hash = response.headers.get("x-vqd-hash-1", self.vqd_hash)

        results = []
        for line in response.iter_lines():
            if line.startswith(b"data: ") and b"[DONE]" not in line:
                try:
                    decoded = line.decode("utf-8")[6:]
                    data = json.loads(decoded)
                    if message := data.get("message"):
                        results.append(message)
                except Exception:
                    continue

        result = "".join(results)
        self.messages.append({"role": "assistant", "content": result})
        return result, self.messages, self.vqd, self.vqd_hash

    def _fetch_fe_version(self):
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        resp = requests.get(self.init_url, proxies=proxies, timeout=10)
        if resp.status_code != 200:
            raise Exception("Failed to fetch x-fe-version")

        match1 = re.search(r'__DDG_BE_VERSION__="([^"]+)"', resp.text)
        match2 = re.search(r'__DDG_FE_CHAT_HASH__="([^"]+)"', resp.text)

        if not match1 or not match2:
            raise Exception("x-fe-version not found")

        return f"{match1.group(1)}-{match2.group(1)}"

    def _fetch_vqd(self):
        headers = self.common_headers.copy()
        headers["x-vqd-accept"] = "1"
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        resp = requests.get(self.status_url, headers=headers, proxies=proxies, timeout=10)
        if resp.status_code != 200:
            raise Exception("Failed to fetch vqd")

        return (
            resp.headers.get("x-vqd-4", ""),
            resp.headers.get("x-vqd-hash-1", ""),
        )