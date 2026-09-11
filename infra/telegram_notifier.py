# infra/telegram_notifier.py

from __future__ import annotations

from typing import Dict, Optional
import time
import requests
import config_live as config


class TelegramNotifier:
    DEFAULT_STOCK_NAME_MAP: Dict[str, str] = {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035720": "카카오",
        "051910": "LG화학",
        "207940": "삼성바이오로직스",
        "068270": "셀트리온",
        "105560": "KB금융",
        "096770": "SK이노베이션",
        "005380": "현대차",
        "012330": "현대모비스",
    }

    def __init__(self, token: str, chat_id: str, logger=None, stock_name_map: Optional[Dict[str, str]] = None):
        self.token = str(token).strip() if token else ""
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.logger = logger
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session = requests.Session()
        self.session.trust_env = False
        self.timeout_sec = max(1.0, float(getattr(config, "TELEGRAM_SEND_TIMEOUT_SEC", 3.0) or 3.0))
        self._last_error_log_ts = 0.0
        self._error_log_cooldown_sec = 300
        self.stock_name_map = dict(self.DEFAULT_STOCK_NAME_MAP)
        if stock_name_map:
            self.stock_name_map.update(stock_name_map)

    def is_enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _masked_token(self) -> str:
        if not self.token:
            return "(empty)"
        if len(self.token) <= 10:
            return self.token[:3] + "***"
        return self.token[:8] + "***"

    def _masked_chat_id(self) -> str:
        if not self.chat_id:
            return "(empty)"
        return "***"

    def debug_identity(self):
        if self.logger:
            self.logger.info(
                f"텔레그램 설정 | enabled={self.is_enabled()} "
                f"token={self._masked_token()} chat_id={self._masked_chat_id()}"
            )

    def get_name(self, symbol: str) -> str:
        return self.stock_name_map.get(str(symbol).strip(), "")

    def format_symbol(self, symbol: str) -> str:
        symbol = str(symbol).strip()
        name = self.get_name(symbol)
        return f"{symbol} {name}".strip()

    def _safe_num(self, value, digits: int = 2) -> str:
        try:
            return f"{float(value):,.{digits}f}"
        except Exception:
            return str(value)

    def send(self, message: str) -> bool:
        if not self.is_enabled():
            if self.logger:
                self.logger.warning("텔레그램 비활성 상태 | token/chat_id 확인 필요")
            return False

        try:
            resp = self.session.post(
                f"{self.base_url}/sendMessage",
                data={"chat_id": self.chat_id, "text": str(message)},
                timeout=(self.timeout_sec, self.timeout_sec),
            )
            ok = resp.status_code == 200
            if not ok and self.logger:
                self.logger.warning(
                    f"텔레그램 전송 실패 | status={resp.status_code} body={resp.text}"
                )
            return ok
        except Exception as e:
            if self.logger:
                now_ts = time.time()
                if now_ts - self._last_error_log_ts >= self._error_log_cooldown_sec:
                    self._last_error_log_ts = now_ts
                    self.logger.warning(f"텔레그램 전송 예외 | {type(e).__name__}: {e}")
            return False

    def send_startup_test(self) -> bool:
        return self.send("✅ 텔레그램 연결 테스트 성공")

    def send_order_event(
        self,
        *,
        event: str,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        status: str = "",
        score=None,
        reason: str = "",
        daily_order_count: Optional[int] = None,
        max_daily_orders: Optional[int] = None,
        cash: Optional[float] = None,
        realized_pnl: Optional[float] = None,
        pnl_pct: Optional[float] = None,
    ) -> bool:
        label = self.format_symbol(symbol)
        lines = [
            event,
            f"종목: {label}",
            f"방향: {side}",
            f"수량: {qty}",
            f"가격: {self._safe_num(price, 0)}",
        ]
        if status:
            lines.append(f"상태: {status}")
        if score is not None:
            lines.append(f"점수: {score}")
        if pnl_pct is not None:
            lines.append(f"손익률: {self._safe_num(pnl_pct, 2)}%")
        if reason:
            lines.append(f"사유: {reason}")
        if daily_order_count is not None and max_daily_orders is not None:
            lines.append(f"일일주문: {daily_order_count}/{max_daily_orders}")
        if cash is not None:
            lines.append(f"예수금: {self._safe_num(cash, 0)}")
        if realized_pnl is not None:
            lines.append(f"실현손익: {self._safe_num(realized_pnl, 0)}")
        return self.send("\n".join(lines))

    def send_daily_summary(
        self,
        *,
        test_name: str,
        reason: str,
        total_trades: Optional[int] = None,
        wins: Optional[int] = None,
        losses: Optional[int] = None,
        win_rate: Optional[float] = None,
        avg_profit_pct: Optional[float] = None,
        avg_loss_pct: Optional[float] = None,
        net_pnl: Optional[float] = None,
        cash: Optional[float] = None,
        realized_pnl: Optional[float] = None,
        daily_order_count: Optional[int] = None,
        max_daily_orders: Optional[int] = None,
        open_symbols: Optional[int] = None,
    ) -> bool:
        lines = [
            "📊 일일 요약",
            f"테스트: {test_name}",
            f"사유: {reason}",
        ]
        if total_trades is not None:
            lines.append(f"총거래: {total_trades}")
        if wins is not None and losses is not None:
            lines.append(f"승/패: {wins}/{losses}")
        if win_rate is not None:
            lines.append(f"승률: {self._safe_num(win_rate, 2)}%")
        if avg_profit_pct is not None:
            lines.append(f"평균수익률: {self._safe_num(avg_profit_pct, 2)}%")
        if avg_loss_pct is not None:
            lines.append(f"평균손실률: {self._safe_num(avg_loss_pct, 2)}%")
        if net_pnl is not None:
            lines.append(f"순손익: {self._safe_num(net_pnl, 0)}")
        if cash is not None:
            lines.append(f"예수금: {self._safe_num(cash, 0)}")
        if realized_pnl is not None:
            lines.append(f"실현손익: {self._safe_num(realized_pnl, 0)}")
        if daily_order_count is not None and max_daily_orders is not None:
            lines.append(f"일일주문: {daily_order_count}/{max_daily_orders}")
        if open_symbols is not None:
            lines.append(f"보유종목수: {open_symbols}")
        return self.send("\n".join(lines))

    def send_risk_status(
        self,
        *,
        reason: str,
        max_positions: int,
        max_symbol_position: int,
        max_daily_orders: int,
        order_amount_per_trade: int,
        order_cooldown_sec: int,
        min_tick_volume: int,
        cash: Optional[float] = None,
    ) -> bool:
        lines = [
            "🛡️ 리스크 설정",
            f"사유: {reason}",
            f"최대보유종목수: {max_positions}",
            f"종목당 최대보유수: {max_symbol_position}",
            f"일일주문한도: {max_daily_orders}",
            f"주문금액한도: {self._safe_num(order_amount_per_trade, 0)}",
            f"주문쿨다운: {order_cooldown_sec}초",
            f"최소틱거래량: {min_tick_volume}",
        ]
        if cash is not None:
            lines.append(f"예수금: {self._safe_num(cash, 0)}")
        return self.send("\n".join(lines))

    def send_trade_close(
        self,
        *,
        symbol: str,
        result: str,
        qty: int,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        reason: str,
        cash: Optional[float] = None,
        realized_pnl: Optional[float] = None,
        total_trades: Optional[int] = None,
        wins: Optional[int] = None,
        losses: Optional[int] = None,
        win_rate: Optional[float] = None,
        net_pnl: Optional[float] = None,
    ) -> bool:
        icon = "💰" if result == "WIN" else "⚠️" if result == "LOSS" else "➖"
        lines = [
            f"{icon} 거래 종료",
            f"종목: {self.format_symbol(symbol)}",
            f"결과: {result}",
            f"수량: {qty}",
            f"청산가: {self._safe_num(exit_price, 0)}",
            f"손익: {self._safe_num(pnl, 0)}",
            f"손익률: {self._safe_num(pnl_pct, 2)}%",
            f"사유: {reason}",
        ]
        if cash is not None:
            lines.append(f"예수금: {self._safe_num(cash, 0)}")
        if realized_pnl is not None:
            lines.append(f"실현손익: {self._safe_num(realized_pnl, 0)}")
        if total_trades is not None:
            lines.append(f"총거래: {total_trades}")
        if wins is not None and losses is not None:
            lines.append(f"승/패: {wins}/{losses}")
        if win_rate is not None:
            lines.append(f"승률: {self._safe_num(win_rate, 2)}%")
        if net_pnl is not None:
            lines.append(f"순손익: {self._safe_num(net_pnl, 0)}")
        return self.send("\n".join(lines))
