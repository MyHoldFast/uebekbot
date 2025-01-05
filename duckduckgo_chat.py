import requests
import json
from threading import Thread
from queue import Queue


class DuckDuckGoChat:
    def __init__(self, vqd=None, messages=None, model="gpt-4o-mini", proxy=None):
        self.chat_url = "https://duckduckgo.com/duckchat/v1/chat"
        self.vqd = vqd or self.fetch_vqd(proxy)
        self.model = model
        self.messages = messages or []
        self.proxy = proxy

    @staticmethod
    def fetch_vqd(proxy=None):
        url = "https://duckduckgo.com/duckchat/v1/status"
        headers = {"x-vqd-accept": "1", 'accept': 'text/event-stream',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3',
            'cache-control': 'no-cache',
            'dnt': '1',
            'origin': 'https://duckduckgo.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://duckduckgo.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
          }
        proxies = {"http": proxy, "https": proxy} if proxy else None
        response = requests.get(url, headers=headers, proxies=proxies)
        if response.status_code == 200:
            return response.headers.get("x-vqd-4")
        else:
            raise Exception(f"Failed to initialize chat: {response.status_code} {response.text}")

    def fetch_response(self, messages=None):
        payload = {
            "model": self.model,
            "messages": messages or self.messages
        }
        cookies = {
            'dcm': '3',
            'dcs': '1',
        }
        headers = {
            'accept': 'text/event-stream',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3',
            'cache-control': 'no-cache',
            'dnt': '1',
            'origin': 'https://duckduckgo.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://duckduckgo.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'x-vqd-4': self.vqd
        }
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        response = requests.post(self.chat_url, headers=headers, cookies=cookies, json=payload, stream=True, proxies=proxies)
        if response.status_code != 200:
            raise Exception(f"Failed to send message: {response.status_code} {response.text}")
        return response

    @staticmethod
    def process_stream(response):
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line == "data: [DONE]":
                    break
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        message = data.get("message", "")
                        if message:
                            yield message
                    except json.JSONDecodeError:
                        continue

    def add_message(self, content, role="user"):
        self.messages.append({"content": content, "role": role})

    def chat(self, user_input):
        self.add_message(user_input, role="user")
        response = self.fetch_response()
        output_queue = Queue()
        thread = Thread(target=self._stream_responses, args=(response, output_queue))
        thread.start()
        result = []
        while thread.is_alive() or not output_queue.empty():
            while not output_queue.empty():
                result.append(output_queue.get())
        thread.join()
        return "".join(result)

    @staticmethod
    def _stream_responses(response, output_queue):
        for message in DuckDuckGoChat.process_stream(response):
            output_queue.put(message)
