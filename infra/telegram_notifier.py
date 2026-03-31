import requests


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def send(self, message: str):
        if not self.token or not self.chat_id:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        try:
            requests.post(url, data={
                "chat_id": self.chat_id,
                "text": message
            }, timeout=5)
        except Exception:
            pass