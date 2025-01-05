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
        headers = {"x-vqd-accept": "1"}
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
        headers = {
            "x-vqd-4": self.vqd,
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        response = requests.post(self.chat_url, headers=headers, json=payload, stream=True, proxies=proxies)
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
