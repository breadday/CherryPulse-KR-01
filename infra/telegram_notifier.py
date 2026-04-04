# infra/telegram_notifier.py

import requests


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, logger=None):
        self.token = str(token).strip() if token else ""
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.logger = logger
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def is_enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _masked_token(self) -> str:
        if not self.token:
            return "(empty)"
        if len(self.token) <= 10:
            return self.token[:3] + "***"
        return self.token[:8] + "***"

    def debug_identity(self):
        if self.logger:
            self.logger.info(
                f"텔레그램 설정 | enabled={self.is_enabled()} "
                f"token={self._masked_token()} chat_id={self.chat_id!r}"
            )

    def send(self, message: str) -> bool:
        if not self.is_enabled():
            if self.logger:
                self.logger.warning("텔레그램 비활성 상태 | token/chat_id 확인 필요")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": str(message),
        }

        try:
            resp = requests.post(url, data=payload, timeout=10)
            ok = resp.status_code == 200

            if not ok and self.logger:
                self.logger.warning(
                    f"텔레그램 전송 실패 | chat_id={self.chat_id!r} "
                    f"status={resp.status_code} body={resp.text}"
                )

            return ok

        except Exception as e:
            if self.logger:
                self.logger.exception(f"텔레그램 전송 예외 | {e}")
            return False

    def send_startup_test(self) -> bool:
        return self.send("✅ 텔레그램 연결 테스트 성공")