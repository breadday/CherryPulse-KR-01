"""Outgoing Telegram Bot API adapter; credentials are never persisted here."""

import json
import os
from dataclasses import dataclass
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_MESSAGE_LENGTH = 4096


class TelegramDeliveryError(RuntimeError):
    """A sanitized delivery failure that never includes token or response text."""

    def __init__(self, code: str, *, http_status: int | None = None) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(code)


class _RejectRedirects(HTTPRedirectHandler):
    """Do not forward a token-bearing Bot API path to a redirect destination."""

    def redirect_request(
        self,
        request: Request,
        response: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> Request | None:
        """Turn redirects into a sanitized HTTP error handled by the caller."""
        return None


@dataclass(frozen=True, slots=True)
class TelegramReceipt:
    """Telegram's non-secret message identity after an accepted send."""

    message_id: int


class TelegramNotifier:
    """Send one outgoing message; caller owns retry and local failure recording."""

    def __init__(self, token: str, chat_id: str, *, timeout_seconds: float) -> None:
        if not token.strip() or not chat_id.strip():
            raise TelegramDeliveryError("TELEGRAM_CONFIGURATION_MISSING")
        if timeout_seconds <= 0:
            raise ValueError("TELEGRAM_TIMEOUT_MUST_BE_POSITIVE")
        self._token = token
        self._chat_id = chat_id
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls, *, timeout_seconds: float) -> "TelegramNotifier":
        """Read runtime secrets without printing or storing them."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        return cls(token, chat_id, timeout_seconds=timeout_seconds)

    def send(self, text: str) -> TelegramReceipt:
        """POST a plain text message and sanitize all transport failures."""
        if not text.strip() or len(text) > MAX_MESSAGE_LENGTH:
            raise TelegramDeliveryError("TELEGRAM_MESSAGE_INVALID")
        endpoint = f"https://api.telegram.org/bot{self._token}/sendMessage"
        body = json.dumps(
            {"chat_id": self._chat_id, "text": text}, ensure_ascii=False
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            opener = build_opener(_RejectRedirects)
            with opener.open(request, timeout=self._timeout_seconds) as response:
                status = response.status
                payload = json.loads(response.read())
        except HTTPError as exc:
            status = exc.code
            if 400 <= status < 500:
                raise TelegramDeliveryError(
                    "TELEGRAM_HTTP_4XX", http_status=status
                ) from None
            if status >= 500:
                raise TelegramDeliveryError(
                    "TELEGRAM_HTTP_5XX", http_status=status
                ) from None
            raise TelegramDeliveryError(
                "TELEGRAM_HTTP_UNEXPECTED", http_status=status
            ) from None
        except (TimeoutError, URLError, OSError, HTTPException):
            raise TelegramDeliveryError("TELEGRAM_NETWORK_ERROR") from None
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            raise TelegramDeliveryError("TELEGRAM_RESPONSE_INVALID") from None

        if not 200 <= status < 300 or not isinstance(payload, dict):
            raise TelegramDeliveryError("TELEGRAM_RESPONSE_INVALID", http_status=status)
        if payload.get("ok") is not True:
            raise TelegramDeliveryError("TELEGRAM_API_REJECTED", http_status=status)
        result = payload.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if type(message_id) is not int:
            raise TelegramDeliveryError("TELEGRAM_RESPONSE_INVALID", http_status=status)
        return TelegramReceipt(message_id=message_id)
