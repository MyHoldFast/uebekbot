import requests
import json

class DuckDuckGoChat:
    chat_url = "https://duckduckgo.com/duckchat/v1/chat"
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
        self.cookies = {"dcs": "1", "dcm": "3"}

    def chat(self, user_input, timeout=30):
        if not self.vqd or not self.vqd_hash:
            self.vqd, self.vqd_hash = self.fetch_vqd(self.proxy)
        
        self.messages.append({"role": "user", "content": user_input})
        payload = {
            "model": self.model,
            "messages": self.messages,
        }
        headers = self.common_headers.copy()
        headers["x-vqd-4"] = self.vqd
        headers["x-vqd-hash-1"] = "" #self.vqd_hash
        
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        response = requests.post(
            self.chat_url, headers=headers, cookies=self.cookies, json=payload, stream=True, proxies=proxies, timeout=timeout
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to send message: {response.status_code}")
        
        self.vqd = response.headers.get("x-vqd-4", self.vqd)
        self.vqd_hash = response.headers.get("x-vqd-hash-1", self.vqd_hash)
        
        results = []
        for line in response.iter_lines(decode_unicode=False):
            if line.startswith(b"data: ") and b"data: [DONE]" not in line:
                try:
                    decoded_line = line.decode("utf-8")
                    message_data = json.loads(decoded_line[6:].strip())
                    if message := message_data.get("message"):
                        results.append(message)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
        
        result = "".join(results)
        self.messages.append({"role": "assistant", "content": result})
        return result

    @staticmethod
    def fetch_vqd(proxy=None):
        headers = DuckDuckGoChat.common_headers.copy()
        headers["x-vqd-accept"] = "1"
        proxies = {"http": proxy, "https": proxy} if proxy else None
        response = requests.get("https://duckduckgo.com/duckchat/v1/status", headers=headers, proxies=proxies)
        
        if response.status_code == 200:
            return response.headers.get("x-vqd-4"), response.headers.get("x-vqd-hash-1")
        
        raise Exception(f"Failed to initialize chat: {response.status_code}")
