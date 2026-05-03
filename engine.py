# engine.py

import csv
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import config_live as config
from core.models import Order, TickData, OrderStatus, Signal, Side, OrderType
from core.order_manager import OrderManager
from core.portfolio import Portfolio
from core.risk_manager import RiskManager
from data.news_provider import NewsProvider


class TradingEngine:
    def __init__(self, broker, strategy, logger, telegram=None, sqlite_store=None, initial_cash=5_000_000, test_name="default"):
        self.broker = broker
        self.strategy = strategy
        self.logger = logger
        self.telegram = telegram
        self.sqlite_store = sqlite_store
        self.test_name = str(test_name).strip() if test_name else "default"

        self.portfolio = Portfolio(initial_cash=initial_cash)
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager()

        self.is_running = False

        # 외부 점수 공급기
        self.news_provider = NewsProvider(logger=logger)

        # 주문 방어 설정
        self.last_order_time = {}
        self.last_order_time_by_strategy = {}
        self.order_cooldown_sec = 10
        self.daily_order_count = 0
        self.daily_order_count_by_strategy = {}
        self.max_daily_orders = 20
        self.current_trading_date = datetime.now().date()
        self.daily_realized_pnl_base = 0.0

        self.min_tick_volume = 1
        self.max_symbol_position = 1
        self.max_positions = 3
        self.order_amount_per_trade = 0

        self._load_runtime_config()

        self.broker.set_real_tick_callback(self.on_real_tick)
        self.broker.set_fill_callback(self.on_fill)
        self.broker.set_msg_callback(self.on_broker_msg)

        self.sell_in_progress = set()
        self.last_price_map = {}
        self.last_market_data_map = {}
        self.reentry_block_until = {}
        self.last_exit_reason = {}

        self.partial_exit_done = set()
        self.breakeven_active = set()
        self.trailing_high_price = {}
        self.trailing_armed = set()
        self.trend_hold_active = set()

        self.cancel_in_progress = set()
        self.pending_resell = {}
        self.resell_retry_count = {}
        self.resell_escalated_symbols = set()
        self.last_cancel_request_time = {}

        self.consecutive_loss_count = 0
        self.error_count = 0
        self.engine_protected = False
        self.protected_tick_log_last_ts = {}
        self.daily_loss_protection_active = False
        self.stale_force_exit_sent = set()
        self.stale_notify_sent = set()

        self.trade_log = []
        self.win_count = 0
        self.loss_count = 0
        self.trade_open_info = {}
        self.trade_cycle_realized_pnl = {}
        self.strategy_reject_reason_counts = defaultdict(Counter)
        self.strategy_signal_counts = Counter()
        self.strategy_order_block_counts = defaultdict(Counter)
        self.strategy_order_ready_counts = Counter()

        # -------------------------
        # 엔진 직접 약손절 / 초기 되밀림 관리
        # 전략 should_exit 의존 없이 엔진이 직접 처리
        # -------------------------
        self.tick_seq = {}
        self.last_entry_signal_context = {}
        self.position_entry_context = {}
        self.order_route_context = {}

        self.engine_early_stop_enabled = True
        self.engine_early_stop_max_hold_ticks = 4
        self.engine_early_stop_loss_pct = -0.2
        self.engine_early_stop_strength_keep_ratio = 0.85
        self.engine_early_stop_price_change_keep_ratio = 0.75

        self.engine_peak_retrace_enabled = True
        self.engine_peak_retrace_max_hold_ticks = 4
        self.engine_peak_retrace_pct = 1.0

    # -------------------------
    # 안전 변환 유틸
    # -------------------------
    def _safe_int(self, value, default=0):
        try:
            if value in ("", None):
                return default
            if isinstance(value, str):
                value = value.replace(",", "").strip()
            return int(float(value))
        except Exception:
            return default

    def _safe_float(self, value, default=0.0):
        try:
            if value in ("", None):
                return default
            if isinstance(value, str):
                value = value.replace(",", "").strip()
            return float(value)
        except Exception:
            return default

    def _side_value(self, side):
        return getattr(side, "value", str(side))

    def _cfg(self, name, default):
        return getattr(config, name, default)

    def _strategy_runtime_cfg(self, strategy_name: str) -> dict:
        all_cfg = getattr(config, "STRATEGY_RUNTIME_CONFIG", {}) or {}
        if not isinstance(all_cfg, dict):
            return {}
        strategy_cfg = all_cfg.get(str(strategy_name or "").strip(), {})
        return strategy_cfg if isinstance(strategy_cfg, dict) else {}

    def _strategy_name_for_symbol(self, symbol: str) -> str:
        ctx = self.position_entry_context.get(symbol, {})
        strategy_name = str(ctx.get("strategy_name", "") or "").strip()
        if strategy_name:
            return strategy_name
        trade_info = self.trade_open_info.get(symbol, {})
        return str(trade_info.get("strategy_name", "") or "").strip()

    def _strategy_name_for_signal(self, signal) -> str:
        route = self._get_signal_route_context(signal)
        return str(route.get("strategy_name", "") or "").strip()

    def _strategy_cfg_value(self, strategy_name: str, key: str, default):
        return self._strategy_runtime_cfg(strategy_name).get(key, default)

    def _strategy_cfg_float(self, strategy_name: str, key: str, default: float) -> float:
        return self._safe_float(self._strategy_cfg_value(strategy_name, key, default), default)

    def _strategy_cfg_bool(self, strategy_name: str, key: str, default: bool) -> bool:
        return bool(self._strategy_cfg_value(strategy_name, key, default))

    def _parse_dt(self, value):
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text[:19], fmt)
            except Exception:
                continue
        return None

    def _parse_hhmm(self, value: str, default: str):
        text = str(value or default).strip() or default
        try:
            return datetime.strptime(text, "%H:%M").time()
        except Exception:
            return datetime.strptime(default, "%H:%M").time()

    def _strategy_enabled(self, strategy_name: str) -> bool:
        return self._strategy_cfg_bool(strategy_name, "enabled", True)

    def _strategy_daily_order_limit(self, strategy_name: str) -> int:
        return max(
            1,
            self._safe_int(
                self._strategy_cfg_value(strategy_name, "max_daily_orders", self.max_daily_orders),
                self.max_daily_orders,
            ),
        )

    def _strategy_daily_order_count(self, strategy_name: str) -> int:
        return int(self.daily_order_count_by_strategy.get(str(strategy_name or "").strip(), 0))

    def _increment_strategy_daily_order_count(self, strategy_name: str):
        strategy_name = str(strategy_name or "").strip()
        if not strategy_name:
            return
        self.daily_order_count_by_strategy[strategy_name] = self._strategy_daily_order_count(strategy_name) + 1

    def _record_strategy_reject_details(self, reject_details: dict):
        if not isinstance(reject_details, dict):
            return
        for strategy_name, reason in reject_details.items():
            strategy_name = str(strategy_name or "").strip()
            reason = str(reason or "").strip()
            if strategy_name and reason:
                self.strategy_reject_reason_counts[strategy_name][reason] += 1

    def _record_strategy_signal(self, strategy_name: str):
        strategy_name = str(strategy_name or "").strip()
        if strategy_name:
            self.strategy_signal_counts[strategy_name] += 1

    def _record_strategy_order_block(self, strategy_name: str, reason: str):
        strategy_name = str(strategy_name or "").strip()
        reason = str(reason or "").strip()
        if strategy_name and reason:
            self.strategy_order_block_counts[strategy_name][reason] += 1

    def _record_strategy_order_ready(self, strategy_name: str):
        strategy_name = str(strategy_name or "").strip()
        if strategy_name:
            self.strategy_order_ready_counts[strategy_name] += 1

    def _format_strategy_diagnostics_lines(self) -> list[str]:
        strategy_names = sorted(
            set(self.strategy_reject_reason_counts.keys())
            | set(self.strategy_signal_counts.keys())
            | set(self.strategy_order_block_counts.keys())
            | set(self.strategy_order_ready_counts.keys())
        )
        lines = []
        for strategy_name in strategy_names:
            reject_counter = self.strategy_reject_reason_counts.get(strategy_name, Counter())
            block_counter = self.strategy_order_block_counts.get(strategy_name, Counter())
            top_rejects = ", ".join(
                f"{reason}({count})" for reason, count in reject_counter.most_common(3)
            ) or "-"
            top_blocks = ", ".join(
                f"{reason}({count})" for reason, count in block_counter.most_common(3)
            ) or "-"
            lines.append(
                f"{strategy_name} | signals={self.strategy_signal_counts.get(strategy_name, 0)} "
                f"ready={self.strategy_order_ready_counts.get(strategy_name, 0)} "
                f"top_rejects={top_rejects} top_blocks={top_blocks}"
            )
        return lines

    def _send_strategy_diagnostics_summary(self):
        if not self.telegram:
            return
        lines = self._format_strategy_diagnostics_lines()
        if not lines:
            return
        try:
            self.telegram.send("[전략별 실패 원인 요약]\n" + "\n".join(f"- {line}" for line in lines[:10]))
        except Exception as e:
            self.logger.warning(f"전략별 실패 원인 요약 전송 실패 | {e}")

    def _effective_order_amount_limit(self, signal=None, symbol: str = "") -> int:
        strategy_name = ""
        if signal is not None:
            strategy_name = self._strategy_name_for_signal(signal)
            self._record_strategy_signal(strategy_name)
        elif symbol:
            strategy_name = self._strategy_name_for_symbol(symbol)
        return max(
            0,
                self._safe_int(
                    self._strategy_cfg_value(strategy_name, "order_amount_per_trade", self.order_amount_per_trade),
                    self.order_amount_per_trade,
                ),
        )

    def _normalize_buy_signal_qty(self, signal, tick) -> None:
        if self._side_value(getattr(signal, "side", "")) != "BUY":
            return

        price = max(0, self._safe_float(getattr(tick, "price", 0), 0.0))
        if price <= 0:
            return

        order_amount_limit = self._effective_order_amount_limit(signal=signal)
        if order_amount_limit <= 0:
            return

        cash = max(0.0, float(getattr(self.portfolio, "cash", 0.0)))
        max_affordable_amount = min(float(order_amount_limit), cash)
        normalized_qty = int(max_affordable_amount // price)
        signal.qty = max(0, normalized_qty)

    def _restore_position_route_context(self, symbol: str, qty: int, avg_price: float):
        if qty <= 0:
            return

        route = {}
        if self.sqlite_store:
            try:
                route = self.sqlite_store.get_latest_buy_route(
                    test_name=self.test_name,
                    symbol=symbol,
                )
            except Exception as e:
                self.logger.warning(f"포지션 전략 복원 실패 | symbol={symbol} err={e}")

        entry_dt = self._parse_dt(route.get("created_at", ""))
        strategy_name = str(route.get("strategy_name", "") or "").strip()
        selector_name = str(route.get("selector_name", "") or "").strip()
        universe_name = str(route.get("universe_name", "") or "").strip()
        fill_price = float(route.get("fill_price", 0.0) or 0.0) or float(avg_price)

        self.trade_open_info[symbol] = {
            "entry_time": entry_dt or datetime.now(),
            "entry_price": float(avg_price),
            "entry_qty": int(qty),
            "strategy_name": strategy_name,
            "selector_name": selector_name,
            "universe_name": universe_name,
        }
        self.trade_cycle_realized_pnl.setdefault(symbol, 0.0)
        self.position_entry_context[symbol] = {
            "entry_tick_no": int(self.tick_seq.get(symbol, 0)),
            "entry_signal_price": float(fill_price),
            "entry_signal_strength": 0.0,
            "entry_signal_price_change_pct": 0.0,
            "entry_signal_volume_ratio": 0.0,
            "strategy_name": strategy_name,
            "selector_name": selector_name,
            "universe_name": universe_name,
            "peak_price_after_entry": float(avg_price),
            "entry_time": (entry_dt.strftime("%Y-%m-%d %H:%M:%S") if entry_dt else ""),
            "entry_trade_date": (entry_dt.strftime("%Y-%m-%d") if entry_dt else ""),
        }

    def _check_close_buy_next_day_exit(self, symbol: str, price: int, avg_price: float, qty: int, tick=None):
        strategy_name = self._strategy_name_for_symbol(symbol)
        if strategy_name != "close_buy":
            return None
        if not self._strategy_cfg_bool(strategy_name, "next_day_exit_enabled", True):
            return None

        ctx = self.position_entry_context.get(symbol, {})
        entry_trade_date = str(ctx.get("entry_trade_date", "") or "").strip()
        if not entry_trade_date:
            entry_time = self._parse_dt(ctx.get("entry_time", ""))
            if entry_time:
                entry_trade_date = entry_time.strftime("%Y-%m-%d")
        if not entry_trade_date:
            return None

        ts = getattr(tick, "ts", None)
        current_dt = ts if isinstance(ts, datetime) else datetime.now()
        current_trade_date = current_dt.strftime("%Y-%m-%d")
        if current_trade_date <= entry_trade_date:
            return None

        current_hhmm = current_dt.strftime("%H:%M")
        start_hhmm = str(self._strategy_cfg_value(strategy_name, "next_day_exit_start_hhmm", "09:05") or "09:05")
        force_hhmm = str(self._strategy_cfg_value(strategy_name, "next_day_exit_force_hhmm", "09:30") or "09:30")
        if current_hhmm < start_hhmm:
            return None

        pnl_pct = (price - avg_price) / avg_price
        take_profit_pct = self._strategy_cfg_float(strategy_name, "next_day_take_profit_pct", 0.012)
        stop_loss_pct = self._strategy_cfg_float(strategy_name, "next_day_stop_loss_pct", -0.015)

        if pnl_pct >= take_profit_pct:
            return f"close_buy_next_day_take {pnl_pct:.2%}"
        if pnl_pct <= stop_loss_pct:
            return f"close_buy_next_day_stop {pnl_pct:.2%}"
        if current_hhmm >= force_hhmm:
            return f"close_buy_next_day_force {current_hhmm}"
        return None

    def _trend_hold_enabled(self) -> bool:
        return bool(self._cfg("ENABLE_TREND_HOLD_AFTER_SCALP", False))

    def _should_activate_trend_hold(self, symbol: str, tick, pnl_pct: float) -> bool:
        if not self._trend_hold_enabled() or tick is None:
            return False

        ctx = self.position_entry_context.get(symbol, {})
        entry_strength = self._safe_float(ctx.get("entry_signal_strength", 0.0), 0.0)
        entry_chg = self._safe_float(ctx.get("entry_signal_price_change_pct", 0.0), 0.0)
        entry_vr = self._safe_float(ctx.get("entry_signal_volume_ratio", 0.0), 0.0)

        current_strength = self._safe_float(getattr(tick, "trade_strength", 0.0), 0.0)
        current_chg = self._safe_float(getattr(tick, "price_change_pct", 0.0), 0.0)
        current_vr = self._safe_float(getattr(tick, "volume_ratio", 0.0), 0.0)

        min_pnl_pct = self._safe_float(self._cfg("TREND_HOLD_MIN_PNL_PCT", 0.012), 0.012)
        if pnl_pct < min_pnl_pct:
            return False

        entry_ok = (
            entry_strength >= self._safe_float(self._cfg("TREND_HOLD_ENTRY_STRENGTH", 140.0), 140.0)
            and entry_chg >= self._safe_float(self._cfg("TREND_HOLD_ENTRY_PRICE_CHANGE_PCT", 0.8), 0.8)
            and entry_vr >= self._safe_float(self._cfg("TREND_HOLD_ENTRY_VOLUME_RATIO", 1.1), 1.1)
        )
        current_ok = (
            current_chg >= self._safe_float(self._cfg("TREND_HOLD_CURRENT_PRICE_CHANGE_PCT", 0.8), 0.8)
            and current_vr >= self._safe_float(self._cfg("TREND_HOLD_CURRENT_VOLUME_RATIO", 1.0), 1.0)
            and (current_strength <= 0.0 or current_strength >= self._safe_float(self._cfg("TREND_HOLD_CURRENT_STRENGTH", 110.0), 110.0))
        )

        return entry_ok or current_ok

    def _update_trend_hold_state(self, symbol: str, tick, pnl_pct: float) -> bool:
        active = self._should_activate_trend_hold(symbol, tick, pnl_pct)
        if active and symbol not in self.trend_hold_active:
            self.trend_hold_active.add(symbol)
            self.logger.info(
                f"[TREND_HOLD_ON] {symbol} pnl={pnl_pct:.2%} "
                f"chg={getattr(tick, 'price_change_pct', 0.0)} "
                f"strength={getattr(tick, 'trade_strength', 0.0)} "
                f"vr={getattr(tick, 'volume_ratio', 0.0)}"
            )
        return symbol in self.trend_hold_active

    def _effective_partial_take_profit_pct(self, symbol: str) -> float:
        strategy_name = self._strategy_name_for_symbol(symbol)
        if symbol in self.trend_hold_active:
            return self._safe_float(
                self._cfg("TREND_HOLD_PARTIAL_TAKE_PROFIT_PCT", self._cfg("PARTIAL_TAKE_PROFIT_PCT", 0.02)),
                self._cfg("PARTIAL_TAKE_PROFIT_PCT", 0.02),
            )
        return self._strategy_cfg_float(
            strategy_name,
            "partial_take_profit_pct",
            self._cfg("PARTIAL_TAKE_PROFIT_PCT", 0.02),
        )

    def _effective_partial_take_ratio(self, symbol: str) -> float:
        strategy_name = self._strategy_name_for_symbol(symbol)
        if symbol in self.trend_hold_active:
            return self._safe_float(
                self._cfg("TREND_HOLD_PARTIAL_TAKE_RATIO", self._cfg("PARTIAL_TAKE_RATIO", 0.5)),
                self._cfg("PARTIAL_TAKE_RATIO", 0.5),
            )
        return self._strategy_cfg_float(
            strategy_name,
            "partial_take_ratio",
            self._cfg("PARTIAL_TAKE_RATIO", 0.5),
        )

    def _effective_take_profit_pct(self, symbol: str) -> float:
        strategy_name = self._strategy_name_for_symbol(symbol)
        if symbol in self.trend_hold_active:
            return self._safe_float(
                self._cfg("TREND_HOLD_FULL_TAKE_PROFIT_PCT", 0.04),
                0.04,
            )
        return self._strategy_cfg_float(
            strategy_name,
            "take_profit_pct",
            self._cfg("TAKE_PROFIT_PCT", 0.03),
        )

    def _effective_trailing_start_pct(self, symbol: str) -> float:
        strategy_name = self._strategy_name_for_symbol(symbol)
        if symbol in self.trend_hold_active:
            return self._safe_float(
                self._cfg("TREND_HOLD_TRAILING_START_PCT", 0.03),
                0.03,
            )
        strategy_start = self._strategy_cfg_float(
            strategy_name,
            "trailing_start_pct",
            self._cfg("PARTIAL_TAKE_PROFIT_PCT", 0.02) + 0.003,
        )
        return max(
            strategy_start,
            self._effective_take_profit_pct(symbol) * 0.7,
        )

    def _effective_trailing_stop_pct(self, symbol: str) -> float:
        strategy_name = self._strategy_name_for_symbol(symbol)
        if symbol in self.trend_hold_active:
            return self._safe_float(
                self._cfg("TREND_HOLD_TRAILING_STOP_PCT", self._cfg("TRAILING_STOP_PCT", 0.01)),
                self._cfg("TRAILING_STOP_PCT", 0.01),
            )
        return self._strategy_cfg_float(
            strategy_name,
            "trailing_stop_pct",
            self._cfg("TRAILING_STOP_PCT", 0.01),
        )

    def _effective_breakeven_floor(self, symbol: str) -> float:
        if symbol in self.trend_hold_active:
            return self._safe_float(self._cfg("TREND_HOLD_BREAKEVEN_FLOOR_PCT", -0.001), -0.001)
        return 0.001

    def _load_runtime_config(self):
        self.order_cooldown_sec = max(
            1,
            self._safe_int(
                self._cfg("ORDER_COOLDOWN_SECONDS", self._cfg("REBUY_COOLDOWN_SECONDS", 10)),
                10,
            ),
        )
        self.max_daily_orders = max(1, self._safe_int(self._cfg("MAX_DAILY_ORDERS", 20), 20))
        self.min_tick_volume = max(1, self._safe_int(self._cfg("MIN_TICK_VOLUME", 1), 1))
        self.max_symbol_position = max(
            1,
            self._safe_int(self._cfg("MAX_SYMBOL_POSITION", self._cfg("MAX_POSITIONS", 1)), 1),
        )
        self.max_positions = max(1, self._safe_int(self._cfg("MAX_POSITIONS", 3), 3))
        self.order_amount_per_trade = max(
            0,
            self._safe_int(self._cfg("ORDER_AMOUNT_PER_TRADE", 0), 0),
        )

        self.logger.info(
            "리스크 설정 로드 | "
            f"cooldown={self.order_cooldown_sec}s "
            f"max_daily_orders={self.max_daily_orders} "
            f"min_tick_volume={self.min_tick_volume} "
            f"max_symbol_position={self.max_symbol_position} "
            f"max_positions={self.max_positions} "
            f"order_amount_per_trade={self.order_amount_per_trade}"
        )

    def _notify_enabled(self, key: str, default: bool):
        return bool(self._cfg(key, default))

    def _should_notify_order_event(self, event: str, status: str = "") -> bool:
        event = str(event or "")
        status = str(status or "")
        if event == "📈 주문 발생":
            return self._notify_enabled("TELEGRAM_NOTIFY_ORDER_SUBMITTED", False)
        if event == "🔻 자동매도 주문":
            return self._notify_enabled("TELEGRAM_NOTIFY_AUTO_SELL_ORDER", False)
        if event == "📉 청산신호":
            return self._notify_enabled("TELEGRAM_NOTIFY_EXIT_SIGNAL", False)
        if event == "❌ 주문 거부":
            return self._notify_enabled("TELEGRAM_NOTIFY_ORDER_REJECTED", True)
        if event == "✅ 체결":
            if "PARTIAL" in status.upper():
                return self._notify_enabled("TELEGRAM_NOTIFY_PARTIAL_FILL", True)
            return self._notify_enabled("TELEGRAM_NOTIFY_FILL", True)
        return True

    def _current_open_symbols(self) -> int:
        try:
            return sum(
                1
                for pos in getattr(self.portfolio, "positions", {}).values()
                if int(getattr(pos, "qty", 0)) > 0
            )
        except Exception:
            return 0

    def _current_open_symbols_for_strategy(self, strategy_name: str) -> int:
        strategy_name = str(strategy_name or "").strip()
        if not strategy_name:
            return self._current_open_symbols()
        try:
            return sum(
                1
                for symbol, pos in getattr(self.portfolio, "positions", {}).items()
                if int(getattr(pos, "qty", 0)) > 0
                and self._strategy_name_for_symbol(symbol) == strategy_name
            )
        except Exception:
            return 0

    def _estimate_order_amount(self, qty: int, price: float) -> int:
        try:
            return int(max(0, qty) * max(0, float(price)))
        except Exception:
            return 0

    def _send_daily_summary(self, reason: str = "manual") -> bool:
        try:
            if not self.telegram or not self._cfg("ENABLE_TELEGRAM_LOG", False):
                return False
            if not self._notify_enabled("TELEGRAM_NOTIFY_DAILY_SUMMARY", True):
                return False

            summary = self.get_trade_summary()
            open_symbols = self._current_open_symbols()

            if hasattr(self.telegram, "send_daily_summary"):
                return self.telegram.send_daily_summary(
                    test_name=self.test_name,
                    reason=reason,
                    total_trades=summary.get("total_trades"),
                    wins=summary.get("wins"),
                    losses=summary.get("losses"),
                    win_rate=summary.get("win_rate"),
                    avg_profit_pct=summary.get("avg_profit_pct"),
                    avg_loss_pct=summary.get("avg_loss_pct"),
                    net_pnl=summary.get("net_pnl"),
                    cash=getattr(self.portfolio, "cash", None),
                    realized_pnl=getattr(self.portfolio, "realized_pnl", None),
                    daily_order_count=self.daily_order_count,
                    max_daily_orders=self.max_daily_orders,
                    open_symbols=open_symbols,
                )

            return self.telegram.send(
                "📊 일일 요약\n"
                f"테스트: {self.test_name}\n"
                f"사유: {reason}\n"
                f"총거래: {summary.get('total_trades', 0)}\n"
                f"승/패: {summary.get('wins', 0)}/{summary.get('losses', 0)}\n"
                f"승률: {summary.get('win_rate', 0)}%\n"
                f"순손익: {summary.get('net_pnl', 0)}\n"
                f"예수금: {getattr(self.portfolio, 'cash', 0)}\n"
                f"실현손익: {getattr(self.portfolio, 'realized_pnl', 0)}"
            )
        except Exception as e:
            self.logger.warning(f"일일 요약 텔레그램 실패 | {e}")
            return False

    def _send_strategy_daily_summary(self, reason: str = "manual") -> bool:
        try:
            if not self.telegram or not self._cfg("ENABLE_TELEGRAM_LOG", False):
                return False
            if not self._notify_enabled("TELEGRAM_NOTIFY_DAILY_SUMMARY", True):
                return False
            if not self.sqlite_store:
                return False

            trade_date = datetime.now().strftime("%Y-%m-%d")
            rows = self.sqlite_store.fetch_strategy_day_rollup(
                trade_date=trade_date,
                test_name=self.test_name,
            )
            if not rows:
                return False

            lines = [
                "📈 전략별 일일 요약",
                f"테스트: {self.test_name}",
                f"사유: {reason}",
                f"날짜: {trade_date}",
            ]
            for row in rows:
                strategy_name = str(row["strategy_name"] or "").strip() or "(미지정)"
                lines.append(
                    f"{strategy_name} | "
                    f"U={int(row['universe_count'] or 0)} "
                    f"S={int(row['signal_count'] or 0)} "
                    f"A={int(row['allowed_signal_count'] or 0)} "
                    f"O={int(row['order_count'] or 0)} "
                    f"T={int(row['trade_count'] or 0)} "
                    f"W={int(row['wins'] or 0)} "
                    f"PnL={float(row['net_pnl'] or 0):,.0f} "
                    f"Avg={float(row['avg_pnl_pct'] or 0):.2f}%"
                )
            return self.telegram.send("\n".join(lines))
        except Exception as e:
            self.logger.warning(f"전략별 일일 요약 텔레그램 실패 | {e}")
            return False

    def _send_strategy_detail_summary(self, reason: str = "manual") -> bool:
        try:
            if not self.telegram or not self._cfg("ENABLE_TELEGRAM_LOG", False):
                return False
            if not self._notify_enabled("TELEGRAM_NOTIFY_DAILY_SUMMARY", True):
                return False
            if not self.sqlite_store:
                return False

            trade_date = datetime.now().strftime("%Y-%m-%d")
            rows = self.sqlite_store.fetch_strategy_day_detail(
                trade_date=trade_date,
                test_name=self.test_name,
            )
            if not rows:
                return False

            lines = [
                "📋 전략별 상세 리포트",
                f"테스트: {self.test_name}",
                f"사유: {reason}",
                f"날짜: {trade_date}",
            ]
            for row in rows:
                strategy_name = str(row["strategy_name"] or "").strip() or "(미지정)"
                reason_parts = []
                top_exit_reason = str(row["top_exit_reason"] or "").strip()
                second_exit_reason = str(row["second_exit_reason"] or "").strip()
                if top_exit_reason:
                    reason_parts.append(f"{top_exit_reason}({int(row['top_exit_count'] or 0)})")
                if second_exit_reason and second_exit_reason != top_exit_reason:
                    reason_parts.append(f"{second_exit_reason}({int(row['second_exit_count'] or 0)})")
                reason_text = ", ".join(reason_parts) if reason_parts else "(청산 없음)"
                lines.append(
                    f"{strategy_name} | "
                    f"U={int(row['universe_count'] or 0)} "
                    f"S={int(row['signal_count'] or 0)} "
                    f"O={int(row['order_count'] or 0)} "
                    f"T={int(row['trade_count'] or 0)} "
                    f"W={int(row['wins'] or 0)} "
                    f"PnL={float(row['net_pnl'] or 0):,.0f} "
                    f"Avg={float(row['avg_pnl_pct'] or 0):.2f}% "
                    f"Exit={reason_text}"
                )
            return self.telegram.send("\n".join(lines))
        except Exception as e:
            self.logger.warning(f"전략별 상세 리포트 텔레그램 실패 | {e}")
            return False

    def _send_strategy_diagnostics_summary(self, reason: str = "manual") -> bool:
        try:
            if not self.telegram or not self._cfg("ENABLE_TELEGRAM_LOG", False):
                return False
            lines = self._format_strategy_diagnostics_lines()
            if not lines:
                return False
            message = ["🧭 전략별 실패 원인 요약", f"테스트: {self.test_name}", f"사유: {reason}"]
            message.extend(f"- {line}" for line in lines[:10])
            return self.telegram.send("\n".join(message))
        except Exception as e:
            self.logger.warning(f"전략별 실패 원인 요약 전송 실패 | {e}")
            return False

    def _send_risk_status(self, reason: str = "startup") -> bool:
        try:
            if not self.telegram or not self._cfg("ENABLE_TELEGRAM_LOG", False):
                return False
            if not self._notify_enabled("TELEGRAM_NOTIFY_RISK_STATUS", True):
                return False

            if hasattr(self.telegram, "send_risk_status"):
                return self.telegram.send_risk_status(
                    reason=reason,
                    max_positions=self.max_positions,
                    max_symbol_position=self.max_symbol_position,
                    max_daily_orders=self.max_daily_orders,
                    order_amount_per_trade=self.order_amount_per_trade,
                    order_cooldown_sec=self.order_cooldown_sec,
                    min_tick_volume=self.min_tick_volume,
                    cash=getattr(self.portfolio, "cash", None),
                )

            return self.telegram.send(
                "🛡️ 리스크 설정\n"
                f"사유: {reason}\n"
                f"최대보유종목수: {self.max_positions}\n"
                f"종목당 최대보유수: {self.max_symbol_position}\n"
                f"일일주문한도: {self.max_daily_orders}\n"
                f"주문금액한도: {self.order_amount_per_trade}\n"
                f"주문쿨다운: {self.order_cooldown_sec}s\n"
                f"최소틱거래량: {self.min_tick_volume}"
            )
        except Exception as e:
            self.logger.warning(f"리스크 상태 텔레그램 실패 | {e}")
            return False

    def _register_tick(self, symbol: str):
        self.tick_seq[symbol] = int(self.tick_seq.get(symbol, 0)) + 1
        return self.tick_seq[symbol]


    def _symbol_label(self, symbol: str) -> str:
        try:
            if self.telegram and hasattr(self.telegram, "format_symbol"):
                return self.telegram.format_symbol(symbol)
        except Exception:
            pass
        return str(symbol)

    def _record_signal_snapshot(self, signal, tick, allowed: bool, block_reason: str = ""):
        if not self.sqlite_store:
            return
        try:
            route = self._get_signal_route_context(signal)
            self.sqlite_store.record_signal(
                test_name=self.test_name,
                strategy_name=route["strategy_name"],
                selector_name=route["selector_name"],
                universe_name=route["universe_name"],
                signal=signal,
                tick=tick,
                allowed=allowed,
                block_reason=block_reason,
            )
        except Exception as e:
            self.logger.warning(f"SQLite signal 저장 실패 | symbol={getattr(signal, 'symbol', '')} err={e}")

    def _record_order_snapshot(self, order, request_price=None):
        if not self.sqlite_store:
            return
        try:
            route = self._get_order_route_context(order)
            self.sqlite_store.record_order(
                test_name=self.test_name,
                order=order,
                request_price=request_price,
                strategy_name=route["strategy_name"],
                selector_name=route["selector_name"],
                universe_name=route["universe_name"],
            )
        except Exception as e:
            self.logger.warning(f"SQLite order 저장 실패 | order_id={getattr(order, 'order_id', '')} err={e}")

    def _record_fill_snapshot(self, fill, local_order_id, unfilled_qty, realized_delta):
        if not self.sqlite_store:
            return
        try:
            route = self._resolve_fill_route_context(fill, local_order_id)
            self.sqlite_store.record_fill(
                test_name=self.test_name,
                fill=fill,
                local_order_id=local_order_id,
                unfilled_qty=unfilled_qty,
                realized_delta=realized_delta,
                cash_after=float(getattr(self.portfolio, "cash", 0.0) or 0.0),
                realized_pnl_after=float(getattr(self.portfolio, "realized_pnl", 0.0) or 0.0),
                strategy_name=route["strategy_name"],
                selector_name=route["selector_name"],
                universe_name=route["universe_name"],
            )
        except Exception as e:
            self.logger.warning(f"SQLite fill 저장 실패 | order_id={getattr(fill, 'order_id', '')} err={e}")

    def _store_daily_summary_snapshot(self):
        if not self.sqlite_store:
            return
        try:
            summary = self.get_trade_summary()
            self.sqlite_store.upsert_daily_summary(
                test_name=self.test_name,
                summary=summary,
                cash=float(getattr(self.portfolio, "cash", 0.0) or 0.0),
                realized_pnl=float(getattr(self.portfolio, "realized_pnl", 0.0) or 0.0),
                daily_order_count=self.daily_order_count,
                max_daily_orders=self.max_daily_orders,
                engine_protected=bool(self.engine_protected),
            )
            self._store_strategy_daily_summary_snapshots()
        except Exception as e:
            self.logger.warning(f"SQLite 요약 저장 실패 | {e}")

    def _empty_route_context(self):
        return {
            "strategy_name": "",
            "selector_name": "",
            "universe_name": "",
        }

    def _normalize_route_context(self, route):
        base = self._empty_route_context()
        if isinstance(route, dict):
            for key in base:
                base[key] = str(route.get(key, "") or "").strip()
        if not base["strategy_name"]:
            base["strategy_name"] = self.strategy.__class__.__name__
        return base

    def _get_strategy_route_context(self):
        if hasattr(self.strategy, "get_active_route_context"):
            try:
                return self._normalize_route_context(self.strategy.get_active_route_context())
            except Exception:
                pass
        return self._normalize_route_context({})

    def _get_signal_route_context(self, signal):
        route = {
            "strategy_name": getattr(signal, "strategy_name", ""),
            "selector_name": getattr(signal, "selector_name", ""),
            "universe_name": getattr(signal, "universe_name", ""),
        }
        if not any(route.values()):
            route = self._get_strategy_route_context()
        return self._normalize_route_context(route)

    def _attach_order_route_context(self, order, route):
        route = self._normalize_route_context(route)
        setattr(order, "strategy_name", route["strategy_name"])
        setattr(order, "selector_name", route["selector_name"])
        setattr(order, "universe_name", route["universe_name"])
        order_id = getattr(order, "order_id", "")
        if order_id:
            self.order_route_context[order_id] = dict(route)

    def _get_order_route_context(self, order):
        route = {
            "strategy_name": getattr(order, "strategy_name", ""),
            "selector_name": getattr(order, "selector_name", ""),
            "universe_name": getattr(order, "universe_name", ""),
        }
        if not any(route.values()):
            route = self.order_route_context.get(getattr(order, "order_id", ""), {})
        return self._normalize_route_context(route)

    def _resolve_fill_route_context(self, fill, local_order_id):
        order = self.order_manager.get_order(local_order_id) if local_order_id else None
        if order is not None:
            return self._get_order_route_context(order)
        broker_order_id = getattr(fill, "order_id", "")
        return self._normalize_route_context(self.order_route_context.get(broker_order_id, {}))

    def _get_symbol_route_context(self, symbol: str):
        ctx = self.position_entry_context.get(symbol, {})
        route = {
            "strategy_name": ctx.get("strategy_name", ""),
            "selector_name": ctx.get("selector_name", ""),
            "universe_name": ctx.get("universe_name", ""),
        }
        return self._normalize_route_context(route)

    def _store_strategy_daily_summary_snapshots(self):
        if not self.sqlite_store:
            return
        summaries = {}
        for trade_item in self.trade_log:
            key = (
                str(trade_item.get("strategy_name", "") or "").strip(),
                str(trade_item.get("selector_name", "") or "").strip(),
                str(trade_item.get("universe_name", "") or "").strip(),
            )
            if not key[0]:
                continue
            bucket = summaries.setdefault(
                key,
                {
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "net_pnl": 0.0,
                    "pnl_pcts": [],
                },
            )
            bucket["total_trades"] += 1
            result = str(trade_item.get("result", "") or "")
            if result == "WIN":
                bucket["wins"] += 1
            elif result == "LOSS":
                bucket["losses"] += 1
            bucket["net_pnl"] += float(trade_item.get("pnl", 0.0) or 0.0)
            bucket["pnl_pcts"].append(float(trade_item.get("pnl_pct", 0.0) or 0.0))

        for (strategy_name, selector_name, universe_name), bucket in summaries.items():
            total = int(bucket["total_trades"] or 0)
            pnl_pcts = list(bucket["pnl_pcts"])
            summary = {
                "total_trades": total,
                "wins": int(bucket["wins"]),
                "losses": int(bucket["losses"]),
                "win_rate": round((bucket["wins"] / total * 100.0), 4) if total else 0.0,
                "net_pnl": round(float(bucket["net_pnl"]), 2),
                "avg_pnl_pct": round(sum(pnl_pcts) / len(pnl_pcts), 4) if pnl_pcts else 0.0,
            }
            self.sqlite_store.upsert_strategy_daily_summary(
                test_name=self.test_name,
                strategy_name=strategy_name,
                selector_name=selector_name,
                universe_name=universe_name,
                summary=summary,
            )
    def _notify_order_event(
        self,
        *,
        event: str,
        symbol: str,
        side,
        qty: int,
        price: float,
        status: str = "",
        score=None,
        reason: str = "",
        pnl_pct=None,
    ):
        try:
            if not self.telegram or not self._cfg("ENABLE_TELEGRAM_LOG", False):
                return
            if not self._should_notify_order_event(event=event, status=status):
                return

            side_text = self._side_value(side)
            cash = getattr(self.portfolio, "cash", None)
            realized_pnl = getattr(self.portfolio, "realized_pnl", None)

            if hasattr(self.telegram, "send_order_event"):
                self.telegram.send_order_event(
                    event=event,
                    symbol=symbol,
                    side=side_text,
                    qty=qty,
                    price=price,
                    status=status,
                    score=score,
                    reason=reason,
                    daily_order_count=self.daily_order_count,
                    max_daily_orders=self.max_daily_orders,
                    cash=cash,
                    realized_pnl=realized_pnl,
                    pnl_pct=(float(pnl_pct) * 100.0) if pnl_pct is not None and abs(float(pnl_pct)) <= 1.0 else pnl_pct,
                )
            else:
                self.telegram.send(
                    f"{event}\n"
                    f"종목: {self._symbol_label(symbol)}\n"
                    f"방향: {side_text}\n"
                    f"수량: {qty}\n"
                    f"가격: {price}\n"
                    f"상태: {status}\n"
                    f"사유: {reason}\n"
                    f"예수금: {cash}\n"
                    f"실현손익: {realized_pnl}"
                )
        except Exception as e:
            self.logger.warning(f"텔레그램 주문 알림 실패 | symbol={symbol} err={e}")

    def _notify_trade_close(self, trade_item: dict):
        try:
            if not self.telegram or not self._cfg("ENABLE_TELEGRAM_LOG", False):
                return
            if not self._notify_enabled("TELEGRAM_NOTIFY_TRADE_CLOSE", True):
                return

            summary = self.get_trade_summary()
            symbol = trade_item.get("symbol", "")
            result = str(trade_item.get("result", ""))
            pnl_pct = float(trade_item.get("pnl_pct", 0.0))
            pnl = float(trade_item.get("pnl", 0.0))
            qty = int(trade_item.get("qty", 0))
            exit_price = float(trade_item.get("exit_price", 0.0))
            reason = str(trade_item.get("exit_reason", ""))

            if hasattr(self.telegram, "send_trade_close"):
                self.telegram.send_trade_close(
                    symbol=symbol,
                    result=result,
                    qty=qty,
                    exit_price=exit_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    reason=reason,
                    cash=getattr(self.portfolio, "cash", None),
                    realized_pnl=getattr(self.portfolio, "realized_pnl", None),
                    total_trades=summary.get("total_trades"),
                    wins=summary.get("wins"),
                    losses=summary.get("losses"),
                    win_rate=summary.get("win_rate"),
                    net_pnl=summary.get("net_pnl"),
                )
            else:
                self.telegram.send(
                    f"거래 종료\n"
                    f"종목: {self._symbol_label(symbol)}\n"
                    f"결과: {result}\n"
                    f"손익: {pnl}\n"
                    f"손익률: {pnl_pct:.2f}%"
                )
        except Exception as e:
            self.logger.warning(f"텔레그램 거래종료 알림 실패 | {e}")

    # -------------------------
    # 거래 성과 집계 CSV 저장
    # -------------------------
    def _get_trade_log_csv_path(self):
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        safe_test_name = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in str(self.test_name)
        ).strip("_")
        if not safe_test_name:
            safe_test_name = "default"

        file_name = f"trades_{safe_test_name}_{datetime.now().strftime('%Y%m%d')}.csv"
        return log_dir / file_name

    def _append_trade_log_to_csv(self, trade_item: dict):
        try:
            csv_path = self._get_trade_log_csv_path()
            file_exists = csv_path.exists()
            fieldnames = [
                "date",
                "test_name",
                "symbol",
                "entry_time",
                "exit_time",
                "entry_price",
                "exit_price",
                "qty",
                "pnl",
                "pnl_pct",
                "result",
                "exit_reason",
            ]

            row = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "test_name": self.test_name,
                "symbol": trade_item.get("symbol", ""),
                "entry_time": trade_item.get("entry_time", ""),
                "exit_time": trade_item.get("exit_time", ""),
                "entry_price": trade_item.get("entry_price", 0.0),
                "exit_price": trade_item.get("exit_price", 0.0),
                "qty": trade_item.get("qty", 0),
                "pnl": trade_item.get("pnl", 0.0),
                "pnl_pct": trade_item.get("pnl_pct", 0.0),
                "result": trade_item.get("result", ""),
                "exit_reason": trade_item.get("exit_reason", ""),
            }

            with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)

            self.logger.info(
                f"거래로그 CSV 저장 | path={csv_path} test_name={self.test_name} "
                f"symbol={row['symbol']} result={row['result']}"
            )
        except Exception as e:
            self.logger.exception(f"거래로그 CSV 저장 실패 | {e}")

    # -------------------------
    # 거래 성과 집계 유틸
    # -------------------------
    def _start_trade_cycle_if_needed(self, symbol: str, qty_before: int, qty_after: int, avg_price_after: float):
        try:
            if qty_after <= 0:
                return

            signal_ctx = self.last_entry_signal_context.get(symbol, {})
            open_info = self.trade_open_info.get(symbol)

            if qty_before <= 0 and qty_after > 0:
                signal_ctx = self.last_entry_signal_context.get(symbol, {})
                self.trade_open_info[symbol] = {
                    "entry_time": datetime.now(),
                    "entry_price": float(avg_price_after),
                    "entry_qty": int(qty_after),
                    "strategy_name": str(signal_ctx.get("strategy_name", "") or ""),
                    "selector_name": str(signal_ctx.get("selector_name", "") or ""),
                    "universe_name": str(signal_ctx.get("universe_name", "") or ""),
                }
                self.trade_cycle_realized_pnl[symbol] = 0.0

                # 엔진 직접 약손절용 진입 컨텍스트 생성
                self.position_entry_context[symbol] = {
                    "entry_tick_no": int(self.tick_seq.get(symbol, 0)),
                    "entry_signal_price": float(signal_ctx.get("price", avg_price_after)),
                    "entry_signal_strength": float(signal_ctx.get("trade_strength", 0.0)),
                    "entry_signal_price_change_pct": float(signal_ctx.get("price_change_pct", 0.0)),
                    "entry_signal_volume_ratio": float(signal_ctx.get("volume_ratio", 0.0)),
                    "strategy_name": str(signal_ctx.get("strategy_name", "") or ""),
                    "selector_name": str(signal_ctx.get("selector_name", "") or ""),
                    "universe_name": str(signal_ctx.get("universe_name", "") or ""),
                    "peak_price_after_entry": float(avg_price_after),
                    "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_trade_date": datetime.now().strftime("%Y-%m-%d"),
                }
                self.trend_hold_active.discard(symbol)

                self.logger.info(
                    f"[TRADE_OPEN] symbol={symbol} entry_price={avg_price_after:.2f} qty={qty_after}"
                )
                return

            if open_info and qty_after >= qty_before:
                open_info["entry_price"] = float(avg_price_after)
                open_info["entry_qty"] = int(qty_after)
                if signal_ctx:
                    open_info["strategy_name"] = str(signal_ctx.get("strategy_name", open_info.get("strategy_name", "")) or "")
                    open_info["selector_name"] = str(signal_ctx.get("selector_name", open_info.get("selector_name", "")) or "")
                    open_info["universe_name"] = str(signal_ctx.get("universe_name", open_info.get("universe_name", "")) or "")

                ctx = self.position_entry_context.get(symbol)
                if ctx is not None:
                    ctx["peak_price_after_entry"] = max(
                        float(ctx.get("peak_price_after_entry", 0.0) or 0.0),
                        float(avg_price_after),
                    )

                self.logger.info(
                    f"[TRADE_OPEN_UPDATE] symbol={symbol} entry_price={avg_price_after:.2f} qty={qty_after}"
                )
        except Exception as e:
            self.logger.exception(f"거래 사이클 시작 기록 실패 | symbol={symbol} err={e}")

    def _accumulate_trade_realized_pnl(self, symbol: str, realized_delta: float):
        try:
            if symbol not in self.trade_cycle_realized_pnl:
                self.trade_cycle_realized_pnl[symbol] = 0.0
            self.trade_cycle_realized_pnl[symbol] += float(realized_delta)
        except Exception as e:
            self.logger.exception(f"실현손익 누적 실패 | symbol={symbol} err={e}")

    def _close_trade_cycle_if_needed(self, symbol: str, qty_before: int, qty_after: int, fill_price: float, exit_reason: str = ""):
        try:
            if not (qty_before > 0 and qty_after <= 0):
                return

            open_info = self.trade_open_info.pop(symbol, None)
            total_realized_pnl = float(self.trade_cycle_realized_pnl.pop(symbol, 0.0))
            self.position_entry_context.pop(symbol, None)
            self.trend_hold_active.discard(symbol)

            if not open_info:
                self.logger.warning(
                    f"거래 종료 감지됐지만 진입 정보 없음 | symbol={symbol} pnl={total_realized_pnl:.0f}"
                )
                return

            entry_price = float(open_info.get("entry_price", 0.0))
            entry_qty = int(open_info.get("entry_qty", 0))
            entry_time = open_info.get("entry_time")

            entry_amount = entry_price * entry_qty
            pnl_pct = 0.0
            if entry_amount > 0:
                pnl_pct = (total_realized_pnl / entry_amount) * 100.0

            result = "WIN" if total_realized_pnl > 0 else "LOSS" if total_realized_pnl < 0 else "FLAT"

            trade_item = {
                "symbol": symbol,
                "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S") if entry_time else "",
                "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "entry_price": round(entry_price, 2),
                "exit_price": round(float(fill_price), 2),
                "qty": entry_qty,
                "pnl": round(total_realized_pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "result": result,
                "exit_reason": exit_reason or self.last_exit_reason.get(symbol, ""),
                "strategy_name": str(open_info.get("strategy_name", "") or ""),
                "selector_name": str(open_info.get("selector_name", "") or ""),
                "universe_name": str(open_info.get("universe_name", "") or ""),
            }

            self.trade_log.append(trade_item)
            self._append_trade_log_to_csv(trade_item)
            if self.sqlite_store:
                self.sqlite_store.record_trade(test_name=self.test_name, trade_item=trade_item)

            if result == "WIN":
                self.win_count += 1
            elif result == "LOSS":
                self.loss_count += 1

            self.logger.info(
                f"[TRADE_CLOSE] symbol={symbol} result={result} "
                f"entry={entry_price:.2f} exit={float(fill_price):.2f} qty={entry_qty} "
                f"pnl={total_realized_pnl:.2f} pnl_pct={pnl_pct:.4f}% "
                f"reason={trade_item['exit_reason']}"
            )

            self._notify_trade_close(trade_item)

            summary = self.get_trade_summary()
            self.logger.info(
                f"[PERFORMANCE] trades={summary['total_trades']} "
                f"wins={summary['wins']} losses={summary['losses']} "
                f"win_rate={summary['win_rate']:.2f}% "
                f"avg_profit={summary['avg_profit_pct']:.4f}% "
                f"avg_loss={summary['avg_loss_pct']:.4f}% "
                f"net_pnl={summary['net_pnl']:.2f}"
            )
            self._store_daily_summary_snapshot()

        except Exception as e:
            self.logger.exception(f"거래 종료 기록 실패 | symbol={symbol} err={e}")

    def get_trade_summary(self):
        total_trades = len(self.trade_log)
        wins = self.win_count
        losses = self.loss_count

        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        profit_list = [x["pnl_pct"] for x in self.trade_log if x.get("pnl_pct", 0.0) > 0]
        loss_list = [x["pnl_pct"] for x in self.trade_log if x.get("pnl_pct", 0.0) < 0]

        avg_profit_pct = sum(profit_list) / len(profit_list) if profit_list else 0.0
        avg_loss_pct = sum(loss_list) / len(loss_list) if loss_list else 0.0
        net_pnl = sum(x.get("pnl", 0.0) for x in self.trade_log)

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "avg_profit_pct": round(avg_profit_pct, 4),
            "avg_loss_pct": round(avg_loss_pct, 4),
            "net_pnl": round(net_pnl, 2),
        }

    def log_trade_summary(self, prefix: str = "성과 요약"):
        try:
            s = self.get_trade_summary()
            self.logger.info(
                f"{prefix} | trades={s['total_trades']} wins={s['wins']} losses={s['losses']} "
                f"win_rate={s['win_rate']:.2f}% avg_profit={s['avg_profit_pct']:.4f}% "
                f"avg_loss={s['avg_loss_pct']:.4f}% net_pnl={s['net_pnl']:.2f}"
            )
        except Exception as e:
            self.logger.exception(f"성과 요약 로그 실패 | {e}")

    def _current_daily_realized_pnl(self) -> float:
        try:
            realized_total = float(getattr(self.portfolio, "realized_pnl", 0.0) or 0.0)
            return realized_total - float(getattr(self, "daily_realized_pnl_base", 0.0) or 0.0)
        except Exception:
            return 0.0

    def _daily_loss_limit_reached(self):
        limit = float(self._cfg("MAX_DAILY_LOSS", 0.0) or 0.0)
        realized = self._current_daily_realized_pnl()
        if limit >= 0:
            return False, realized, limit
        return realized <= limit, realized, limit

    def _extract_score_from_reason(self, reason: str):
        try:
            if not reason:
                return None
            text = str(reason)
            if "score=" in text:
                part = text.split("score=", 1)[1].split()[0]
                return float(part.strip())
            for token in text.split(":"):
                if token.startswith("score="):
                    return float(token.split("=", 1)[1])
        except Exception:
            return None
        return None

    def _build_external_scores(self, raw_tick: dict):
        symbol = str(raw_tick.get("symbol", ""))

        news_score = self._safe_float(raw_tick.get("news_score", 0.0), 0.0)
        theme_score = self._safe_float(raw_tick.get("theme_score", 0.0), 0.0)
        leader_score = self._safe_float(raw_tick.get("leader_score", 0.0), 0.0)

        if news_score != 0.0 or theme_score != 0.0 or leader_score != 0.0:
            return {
                "news_score": news_score,
                "theme_score": theme_score,
                "leader_score": leader_score,
                "total_external_score": round(news_score + theme_score + leader_score, 2),
            }

        return self.news_provider.get_scores(symbol)

    # -------------------------
    # 장 시간 체크 / 상태
    # -------------------------
    def is_market_open(self):
        now = datetime.now().time()
        market_open = datetime.strptime("09:00", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        return market_open <= now <= market_close

    def reset_daily_counters_if_needed(self):
        today = datetime.now().date()
        if today != self.current_trading_date:
            self.current_trading_date = today
            self.daily_order_count = 0
            self.daily_order_count_by_strategy = {}
            self.last_order_time = {}
            self.last_order_time_by_strategy = {}
            self.strategy_reject_reason_counts = defaultdict(Counter)
            self.strategy_signal_counts = Counter()
            self.strategy_order_block_counts = defaultdict(Counter)
            self.strategy_order_ready_counts = Counter()
            self.daily_realized_pnl_base = float(getattr(self.portfolio, "realized_pnl", 0.0) or 0.0)
            if self.daily_loss_protection_active:
                self.daily_loss_protection_active = False
                max_consecutive_loss = self._cfg("MAX_CONSECUTIVE_LOSS", 3)
                max_error_count = self._cfg("MAX_ERROR_COUNT", self._cfg("MAX_ENGINE_ERROR_COUNT", 5))
                if (
                    self.consecutive_loss_count < max_consecutive_loss
                    and self.error_count < max_error_count
                ):
                    self.engine_protected = False
            self.logger.info("일일 주문 카운터 초기화")

    def start(self):
        self.broker.connect()
        self.is_running = True
        self.logger.info("브로커 연결 완료")

    def stop(self):
        if not self.is_running:
            self.logger.info("이미 종료 상태")
            self.log_trade_summary(prefix="종료 전 성과 요약")
            self._send_daily_summary(reason="already_stopped")
            self._send_strategy_daily_summary(reason="already_stopped")
            self._send_strategy_detail_summary(reason="already_stopped")
            self._send_strategy_diagnostics_summary(reason="already_stopped")
            try:
                self.broker.shutdown()
            except Exception as e:
                self.logger.warning(f"브로커 종료 실패 | {e}")
            return

        self.logger.info("엔진 종료 시작")
        self.log_trade_summary(prefix="종료 전 성과 요약")
        self._send_daily_summary(reason="engine_stop")
        self._send_strategy_daily_summary(reason="engine_stop")
        self._send_strategy_detail_summary(reason="engine_stop")
        self._send_strategy_diagnostics_summary(reason="engine_stop")
        try:
            self.broker.shutdown()
        except Exception as e:
            self.logger.warning(f"브로커 종료 실패 | {e}")

        self.is_running = False
        self.logger.info("엔진 종료 완료")

    def health_check(self):
        try:
            positions = getattr(self.portfolio, "positions", {})
            pending_count = len(getattr(self.order_manager, "orders", {}))
            self.logger.info(
                f"health_check 완료 | positions={len(positions)} pending_orders={pending_count} "
                f"daily_order_count={self.daily_order_count} protected={self.engine_protected}"
            )
            self._store_daily_summary_snapshot()
        except Exception as e:
            self.logger.warning(f"health_check 점검 중 예외 | {e}")

    # -------------------------
    # 계좌 동기화
    # -------------------------
    def sync_account(self, password: str = ""):
        try:
            deposit = self.broker.get_deposit(password=password)
            time.sleep(1.0)
            positions = self.broker.get_positions(password=password)

            self.logger.info(f"예수금 동기화 완료 | deposit={deposit}")
            self.logger.info(f"보유종목 동기화 완료 | count={len(positions)}")

            self.portfolio.cash = deposit

            for item in positions:
                symbol = item["symbol"]
                qty = int(item["qty"])
                avg_price = float(item["avg_price"])

                pos = self.portfolio.get_position(symbol)
                pos.qty = qty
                pos.avg_price = avg_price
                pos.partial_taken = False
                pos.highest_return_pct = 0.0

                self.logger.info(
                    f"포지션 반영 | symbol={symbol} qty={qty} avg_price={avg_price}"
                )
                self._restore_position_route_context(symbol, qty, avg_price)

            self._send_risk_status(reason="sync_account")
            return {"deposit": deposit, "positions": positions}

        except Exception as e:
            self.logger.exception(f"계좌 동기화 실패 | {e}")
            return {"deposit": 0, "positions": []}

    def sync_pending_orders(self, password: str = ""):
        try:
            pending_orders = self.broker.get_pending_orders(password=password)
            self.logger.info(f"미체결 주문 동기화 시작 | count={len(pending_orders)}")

            restored = 0
            for item in pending_orders:
                symbol = item["symbol"]
                order_no = item["order_no"]
                side = item["side"]
                order_qty = int(item["order_qty"])
                unfilled_qty = int(item["unfilled_qty"])
                filled_qty = int(item["filled_qty"])
                order_price = float(item["order_price"])
                order_status = str(item["order_status"])

                if unfilled_qty <= 0:
                    continue

                local_id = f"RESTORE_{order_no}"
                if self.order_manager.get_order(local_id) is not None:
                    continue

                order_type = OrderType.LIMIT if order_price > 0 else OrderType.MARKET
                status = OrderStatus.PARTIAL if filled_qty > 0 else OrderStatus.SUBMITTED

                restored_order = Order(
                    order_id=local_id,
                    symbol=symbol,
                    side=side,
                    qty=order_qty,
                    price=order_price,
                    order_type=order_type,
                    status=status,
                    filled_qty=filled_qty,
                    avg_fill_price=order_price if filled_qty > 0 else 0.0,
                    reason=f"restored_pending:{order_status}",
                )

                self.order_manager.register(restored_order)
                self.order_manager.broker_to_local_id[order_no] = local_id
                restored += 1

                self.logger.info(
                    f"미체결 주문 복원 | symbol={symbol} "
                    f"broker_order_no={order_no} local_id={local_id} "
                    f"side={side} qty={order_qty} filled={filled_qty} "
                    f"remain={unfilled_qty} price={order_price} status={status}"
                )

            self.logger.info(f"미체결 주문 동기화 완료 | restored={restored}")
            return pending_orders

        except Exception as e:
            self.logger.exception(f"미체결 주문 동기화 실패 | {e}")
            return []

    # -------------------------
    # 주기적 미체결 관리
    # -------------------------
    def _stale_position_policy(self, strategy_name: str) -> dict:
        policies = self._cfg("STALE_POSITION_POLICY", {})
        if not isinstance(policies, dict):
            return {}
        strategy_key = str(strategy_name or "").strip() or "unknown"
        policy = policies.get(strategy_key)
        if not isinstance(policy, dict):
            policy = policies.get("unknown", {})
        return policy if isinstance(policy, dict) else {}

    def _check_stale_position_force_exit(self):
        if not self._cfg("FORCE_EXIT_STALE_POSITIONS", False):
            return

        now = datetime.now()
        now_time = now.time()
        allowlist = {str(x).strip() for x in self._cfg("STALE_POSITION_ALLOWLIST", []) if str(x).strip()}
        blocklist = {str(x).strip() for x in self._cfg("STALE_POSITION_BLOCKLIST", []) if str(x).strip()}

        positions = getattr(self.portfolio, "positions", {})
        for symbol, pos in list(positions.items()):
            symbol = str(symbol or "").strip()
            if not symbol:
                continue

            qty = int(getattr(pos, "qty", 0) or 0)
            avg_price = float(getattr(pos, "avg_price", 0.0) or 0.0)
            if qty <= 0 or avg_price <= 0:
                continue
            if allowlist and symbol not in allowlist:
                continue
            if symbol in blocklist:
                continue
            if symbol in self.sell_in_progress or symbol in self.cancel_in_progress:
                continue
            if symbol in self.pending_resell:
                continue
            if self.order_manager.exists_open_order(symbol):
                continue

            strategy_name = self._strategy_name_for_symbol(symbol) or "unknown"
            policy = self._stale_position_policy(strategy_name)
            notify_only = bool(policy.get("notify_only", False))
            if not bool(policy.get("enabled", False)):
                if notify_only and symbol not in self.stale_notify_sent:
                    self.stale_notify_sent.add(symbol)
                    self.logger.warning(
                        f"잔존 포지션 수동확인 필요 | symbol={symbol} qty={qty} "
                        f"avg_price={avg_price:.0f} strategy={strategy_name}"
                    )
                continue

            ctx = self.position_entry_context.get(symbol, {})
            entry_dt = self._parse_dt(ctx.get("entry_time", ""))
            if entry_dt is None and self.sqlite_store:
                route = self.sqlite_store.get_latest_buy_route(
                    test_name=self.test_name,
                    symbol=symbol,
                )
                entry_dt = self._parse_dt(route.get("created_at", ""))

            if entry_dt is None:
                if symbol not in self.stale_notify_sent:
                    self.stale_notify_sent.add(symbol)
                    self.logger.warning(
                        f"잔존 포지션 진입일 확인 실패 | symbol={symbol} qty={qty} "
                        f"avg_price={avg_price:.0f} strategy={strategy_name}"
                    )
                continue

            age_days = max((now.date() - entry_dt.date()).days, 0)
            stale_after_days = max(0, self._safe_int(policy.get("stale_after_days", 1), 1))
            if age_days < stale_after_days:
                continue

            start_time = self._parse_hhmm(policy.get("exit_start_hhmm", "09:03"), "09:03")
            end_time = self._parse_hhmm(policy.get("exit_end_hhmm", "10:00"), "10:00")
            if not (start_time <= now_time <= end_time):
                continue

            dedupe_key = (symbol, now.strftime("%Y-%m-%d"))
            if dedupe_key in self.stale_force_exit_sent:
                continue

            self.stale_force_exit_sent.add(dedupe_key)
            reason = (
                f"stale_force_exit strategy={strategy_name} "
                f"age_days={age_days} entry={entry_dt.strftime('%Y-%m-%d')}"
            )
            self.logger.warning(
                f"잔존 포지션 강제청산 | symbol={symbol} qty={qty} "
                f"avg_price={avg_price:.0f} reason={reason}"
            )
            if self.telegram:
                self.telegram.send(
                    f"🚨 잔존 포지션 강제청산\n"
                    f"종목: {symbol}\n"
                    f"전략: {strategy_name}\n"
                    f"수량: {qty}\n"
                    f"평단: {avg_price:.0f}\n"
                    f"보유일수: {age_days}\n"
                    f"사유: {reason}"
                )
            self._submit_auto_sell(symbol=symbol, qty=qty, reason=reason)

    def manage_pending_orders(self):
        try:
            if not self.is_running:
                return

            self._check_stale_position_force_exit()

            symbols = set()
            for order in self.order_manager.orders.values():
                if getattr(order, "status", None) in (OrderStatus.SUBMITTED, OrderStatus.PARTIAL):
                    if getattr(order, "symbol", None):
                        symbols.add(order.symbol)

            symbols.update(self.pending_resell.keys())

            for symbol in list(symbols):
                self._check_stale_sell_order(symbol)
                self._retry_sell_after_cancel(symbol)

        except Exception as e:
            self.logger.exception(f"미체결 주문 관리 실패 | {e}")

    # -------------------------
    # 실시간 틱 수신
    # -------------------------
    def on_real_tick(self, raw_tick: dict):
        try:
            symbol = str(raw_tick["symbol"])
            price = self._safe_int(raw_tick.get("price", 0), 0)
            volume = self._safe_int(raw_tick.get("trade_volume", raw_tick.get("volume", 0)), 0)

            price_change_pct = self._safe_float(
                raw_tick.get("price_change_pct", raw_tick.get("change_rate", 0.0)),
                0.0,
            )
            trade_strength = self._safe_float(raw_tick.get("trade_strength", 0.0), 0.0)
            volume_ratio = self._safe_float(raw_tick.get("volume_ratio", 0.0), 0.0)

            external_scores = self._build_external_scores(raw_tick)
            current_tick_no = self._register_tick(symbol)

            self.logger.info(
                f"[TICK] {symbol} tick_no={current_tick_no} price={price} vol={volume} "
                f"chg={price_change_pct} strength={trade_strength} vr={volume_ratio} "
                f"news={external_scores['news_score']} "
                f"theme={external_scores['theme_score']} "
                f"leader={external_scores['leader_score']}"
            )

            if price <= 0:
                return

            self.last_price_map[symbol] = price
            self.last_market_data_map[symbol] = {
                "price": price,
                "price_change_pct": price_change_pct,
                "trade_strength": trade_strength,
                "volume_ratio": volume_ratio,
                "news_score": external_scores["news_score"],
                "theme_score": external_scores["theme_score"],
                "leader_score": external_scores["leader_score"],
            }

            # 초기 보유 구간 최고가 추적
            ctx = self.position_entry_context.get(symbol)
            if ctx:
                peak_price = float(ctx.get("peak_price_after_entry", price))
                if price > peak_price:
                    ctx["peak_price_after_entry"] = price

            tick = TickData(
                symbol=symbol,
                price=price,
                volume=volume,
                ts=datetime.now(),
                price_change_pct=price_change_pct,
                trade_strength=trade_strength,
                volume_ratio=volume_ratio,
                news_score=external_scores["news_score"],
                theme_score=external_scores["theme_score"],
                leader_score=external_scores["leader_score"],
            )

            self._check_auto_exit(symbol, price, tick=tick)
            self._check_stale_sell_order(symbol)
            self._retry_sell_after_cancel(symbol)

            if self.engine_protected:
                now_ts = time.time()
                if now_ts - self.protected_tick_log_last_ts.get(symbol, 0.0) >= 60:
                    self.protected_tick_log_last_ts[symbol] = now_ts
                    self.logger.info(
                        f"보호모드 신규진입 차단 | symbol={symbol} price={price}"
                    )
                return

            self.on_tick(tick)

        except Exception as e:
            self.error_count += 1
            self.logger.exception(f"실시간 틱 처리 실패 | tick={raw_tick} err={e}")
            self._check_engine_protection()

    # -------------------------
    # 청산 로그 포맷
    # -------------------------
    def _log_exit_event(self, symbol: str, price: int, avg_price: float, qty: int, event: str):
        try:
            pnl_pct = 0.0
            if avg_price > 0:
                pnl_pct = (price - avg_price) / avg_price

            self.logger.info(
                f"[EXIT_CHECK] {symbol} "
                f"event={event} "
                f"price={price} avg={avg_price:.2f} qty={qty} pnl={pnl_pct:.2%}"
            )

            self._notify_order_event(
                event="📉 청산신호",
                symbol=symbol,
                side=Side.SELL,
                qty=qty,
                price=price,
                status=event,
                reason=event,
                pnl_pct=pnl_pct,
            )
        except Exception as e:
            self.logger.warning(f"청산 로그 기록 실패 | symbol={symbol} err={e}")

    # -------------------------
    # 엔진 직접 약손절 판단
    # -------------------------
    def _check_engine_early_stop(self, symbol: str, price: int, avg_price: float, qty: int, tick):
        ctx = self.position_entry_context.get(symbol)
        if not ctx:
            return None

        current_tick_no = int(self.tick_seq.get(symbol, 0))
        entry_tick_no = int(ctx.get("entry_tick_no", current_tick_no))
        ticks_from_entry = current_tick_no - entry_tick_no
        pnl_pct = ((price - avg_price) / avg_price) * 100.0

        entry_strength = float(ctx.get("entry_signal_strength", 0.0))
        entry_price_change_pct = float(ctx.get("entry_signal_price_change_pct", 0.0))
        current_strength = float(getattr(tick, "trade_strength", 0.0))
        current_price_change_pct = float(getattr(tick, "price_change_pct", 0.0))

        strength_fail = (
            entry_strength > 0
            and current_strength < (entry_strength * self.engine_early_stop_strength_keep_ratio)
        )
        momentum_fail = (
            entry_price_change_pct > 0
            and current_price_change_pct < (entry_price_change_pct * self.engine_early_stop_price_change_keep_ratio)
        )
        price_fail = pnl_pct <= self.engine_early_stop_loss_pct

        if (
            self.engine_early_stop_enabled
            and ticks_from_entry <= self.engine_early_stop_max_hold_ticks
            and price_fail
            and (strength_fail or momentum_fail)
        ):
            return {
                "reason": "engine_early_stop",
                "qty": qty,
                "event": "ENGINE_EARLY_STOP",
                "pnl_pct": pnl_pct,
            }

        peak_price = float(ctx.get("peak_price_after_entry", price))
        if (
            self.engine_peak_retrace_enabled
            and ticks_from_entry <= self.engine_peak_retrace_max_hold_ticks
            and peak_price > 0
        ):
            retrace_pct = ((peak_price - price) / peak_price) * 100.0
            if retrace_pct >= self.engine_peak_retrace_pct and (strength_fail or momentum_fail):
                return {
                    "reason": "engine_peak_retrace_stop",
                    "qty": qty,
                    "event": "ENGINE_PEAK_RETRACE_STOP",
                    "pnl_pct": pnl_pct,
                }

        return None

    def _in_stop_loss_grace_window(self, symbol: str, tick=None) -> bool:
        ctx = self.position_entry_context.get(symbol, {})
        if not ctx:
            return False

        strategy_name = self._strategy_name_for_symbol(symbol)
        grace_seconds = max(
            int(self._strategy_cfg_value(strategy_name, "stop_loss_grace_seconds", 0) or 0),
            0,
        )
        grace_ticks = max(
            int(self._strategy_cfg_value(strategy_name, "stop_loss_grace_ticks", 0) or 0),
            0,
        )
        if grace_seconds <= 0 and grace_ticks <= 0:
            return False

        tick_ok = False
        if grace_ticks > 0:
            current_tick_no = int(self.tick_seq.get(symbol, 0))
            entry_tick_no = int(ctx.get("entry_tick_no", current_tick_no))
            ticks_from_entry = max(current_tick_no - entry_tick_no, 0)
            tick_ok = ticks_from_entry < grace_ticks

        second_ok = False
        if grace_seconds > 0:
            entry_dt = self._parse_dt(ctx.get("entry_time", ""))
            current_dt = getattr(tick, "ts", None)
            if not isinstance(current_dt, datetime):
                current_dt = datetime.now()
            if entry_dt is not None:
                elapsed_sec = max((current_dt - entry_dt).total_seconds(), 0.0)
                second_ok = elapsed_sec < grace_seconds

        return tick_ok or second_ok

    # -------------------------
    # 자동 매도 검사
    # -------------------------
    def _check_auto_exit(self, symbol: str, price: int, tick=None):
        try:
            pos = self.portfolio.get_position(symbol)
            qty = int(getattr(pos, "qty", 0))
            avg_price = float(getattr(pos, "avg_price", 0))
            strategy_name = self._strategy_name_for_symbol(symbol)

            if qty <= 0 or avg_price <= 0:
                return
            if symbol in self.pending_resell:
                return
            if symbol in self.cancel_in_progress:
                return
            if symbol in self.sell_in_progress:
                return
            if self.order_manager.exists_open_order(symbol):
                return

            pnl_pct = (price - avg_price) / avg_price
            trend_hold_now = self._update_trend_hold_state(symbol, tick, pnl_pct) if tick is not None else (symbol in self.trend_hold_active)
            partial_take_profit_pct = self._effective_partial_take_profit_pct(symbol)
            partial_take_ratio = self._effective_partial_take_ratio(symbol)
            take_profit_pct = self._effective_take_profit_pct(symbol)
            trailing_start_pct = self._effective_trailing_start_pct(symbol)
            trailing_stop_pct = self._effective_trailing_stop_pct(symbol)
            breakeven_floor = self._effective_breakeven_floor(symbol)
            stop_loss_pct = self._strategy_cfg_float(
                strategy_name,
                "stop_loss_pct",
                self._cfg("STOP_LOSS_PCT", -0.02),
            )
            stop_loss_grace_active = self._in_stop_loss_grace_window(symbol, tick=tick)
            breakeven_enabled = self._strategy_cfg_bool(
                strategy_name,
                "breakeven_enabled",
                self._cfg("BREAKEVEN_ENABLED", False),
            )
            trailing_stop_enabled = self._strategy_cfg_bool(
                strategy_name,
                "trailing_stop_enabled",
                self._cfg("TRAILING_STOP_ENABLED", False),
            )

            if tick is not None:
                early_stop = None if stop_loss_grace_active else self._check_engine_early_stop(symbol, price, avg_price, qty, tick)
                if early_stop:
                    reason = early_stop["reason"]
                    self.last_exit_reason[symbol] = reason
                    self._log_exit_event(symbol, price, avg_price, qty, early_stop["event"])
                    self.logger.info(
                        f"익일 청산 실행 | symbol={symbol} price={price} avg_price={avg_price} "
                        f"qty={qty} pnl_pct={pnl_pct:.2%} reason={reason}"
                    )
                    self._submit_auto_sell(symbol=symbol, qty=qty, reason=reason)
                    return

            close_buy_next_day_reason = self._check_close_buy_next_day_exit(
                symbol=symbol,
                price=price,
                avg_price=avg_price,
                qty=qty,
                tick=tick,
            )
            if close_buy_next_day_reason:
                self.last_exit_reason[symbol] = close_buy_next_day_reason
                self._log_exit_event(symbol, price, avg_price, qty, "CLOSE_BUY_NEXT_DAY_EXIT")
                self.logger.info(
                    f"종가매수 익일 청산 | symbol={symbol} price={price} avg_price={avg_price} "
                    f"qty={qty} reason={close_buy_next_day_reason}"
                )
                self._submit_auto_sell(symbol=symbol, qty=qty, reason=close_buy_next_day_reason)
                return

            if pnl_pct <= stop_loss_pct and not stop_loss_grace_active:
                exit_reason = f"stop_loss {pnl_pct:.2%}"
                self.last_exit_reason[symbol] = exit_reason
                self._log_exit_event(symbol, price, avg_price, qty, "STOP_LOSS")
                self.logger.info(
                    f"손절 조건 충족 | symbol={symbol} price={price} avg_price={avg_price} "
                    f"qty={qty} pnl_pct={pnl_pct:.2%}"
                )
                self._submit_auto_sell(symbol=symbol, qty=qty, reason=exit_reason)
                return

            if symbol not in self.partial_exit_done and pnl_pct >= partial_take_profit_pct:
                sell_qty = max(int(qty * partial_take_ratio), 1)
                sell_qty = min(sell_qty, qty)

                self.last_exit_reason[symbol] = "partial_take"
                self._log_exit_event(symbol, price, avg_price, sell_qty, "PARTIAL_TAKE")
                self.logger.info(
                    f"부분익절 실행 | symbol={symbol} qty={sell_qty} pnl={pnl_pct:.2%} "
                    f"threshold={partial_take_profit_pct:.2%} trend_hold={trend_hold_now}"
                )

                self.partial_exit_done.add(symbol)
                if breakeven_enabled:
                    self.breakeven_active.add(symbol)
                if trailing_stop_enabled:
                    self.trailing_high_price[symbol] = price

                self._submit_auto_sell(symbol, sell_qty, "partial_take")
                return

            if symbol in self.partial_exit_done and trailing_stop_enabled:
                prev_high = self.trailing_high_price.get(symbol, 0)
                if price > prev_high:
                    self.trailing_high_price[symbol] = price
                    self.logger.info(
                        f"[TRAIL_HIGH] {symbol} high_price_update prev={prev_high} new={price}"
                    )

            if symbol in self.partial_exit_done and trailing_stop_enabled and pnl_pct >= trailing_start_pct:
                if symbol not in self.trailing_armed:
                    self.trailing_armed.add(symbol)
                    self.logger.info(
                        f"[TRAIL_ARM] {symbol} pnl={pnl_pct:.2%} start_pct={trailing_start_pct:.2%} trend_hold={trend_hold_now}"
                    )

            if symbol in self.breakeven_active:
                if pnl_pct <= breakeven_floor:
                    self.last_exit_reason[symbol] = "breakeven_exit"
                    self._log_exit_event(symbol, price, avg_price, qty, "BREAKEVEN_EXIT")
                    self.logger.info(
                        f"본절 청산 실행 | symbol={symbol} price={price} avg_price={avg_price} "
                        f"pnl={pnl_pct:.2%} floor={breakeven_floor:.2%}"
                    )
                    self._submit_auto_sell(symbol, qty, "breakeven_exit")
                    return

            if symbol in self.partial_exit_done and symbol in self.trailing_armed and trailing_stop_enabled:
                high_price = self.trailing_high_price.get(symbol, 0)
                if high_price > 0:
                    trailing_stop_price = high_price * (1 - trailing_stop_pct)
                    self.logger.info(
                        f"[TRAIL_CHECK] {symbol} price={price} high={high_price} stop={trailing_stop_price:.2f} trend_hold={trend_hold_now}"
                    )
                    if price <= trailing_stop_price:
                        reason = f"trailing_stop high={high_price}"
                        self.last_exit_reason[symbol] = reason
                        self._log_exit_event(symbol, price, avg_price, qty, "TRAILING_STOP")
                        self.logger.info(
                            f"트레일링 스탑 실행 | symbol={symbol} price={price} high={high_price} stop={trailing_stop_price:.2f}"
                        )
                        self._submit_auto_sell(symbol, qty, reason)
                        return

            if symbol not in self.partial_exit_done and pnl_pct >= take_profit_pct:
                exit_reason = f"take_profit {pnl_pct:.2%}"
                self.last_exit_reason[symbol] = exit_reason
                self._log_exit_event(symbol, price, avg_price, qty, "TAKE_PROFIT")
                self.logger.info(
                    f"목표가 청산 실행 | symbol={symbol} price={price} avg_price={avg_price} qty={qty} "
                    f"pnl_pct={pnl_pct:.2%} target={take_profit_pct:.2%} trend_hold={trend_hold_now}"
                )
                self._submit_auto_sell(symbol=symbol, qty=qty, reason=exit_reason)
                return

        except Exception as e:
            self.logger.exception(f"자동 청산 검사 실패 | symbol={symbol} price={price} err={e}")

    def _submit_auto_sell(self, symbol: str, qty: int, reason: str):
        try:
            if qty <= 0:
                return

            self.sell_in_progress.add(symbol)
            signal = Signal(
                symbol=symbol,
                side=Side.SELL,
                qty=qty,
                price=0,
                order_type=OrderType.MARKET,
                reason=reason,
            )

            order = self.broker.place_order(signal)
            self._attach_order_route_context(order, self._get_symbol_route_context(symbol))
            self.order_manager.register(order)
            self._record_order_snapshot(order, request_price=float(self.last_price_map.get(symbol, 0) or 0.0))

            if self._cfg("PAPER_TRADING", self._cfg("DRY_RUN", False)):
                class StubFill:
                    pass
                fill = StubFill()
                fill.order_id = order.order_id
                fill.symbol = order.symbol
                fill.side = order.side
                fill.fill_qty = order.qty
                fill.fill_price = self.last_price_map.get(symbol, 0)
                fill.unfilled_qty = 0
                self.on_fill(fill)

            if order.status == OrderStatus.SUBMITTED:
                self.last_order_time[symbol] = time.time()
                self.daily_order_count += 1
                self._increment_strategy_daily_order_count(self._strategy_name_for_symbol(symbol))

                if "손절" in reason or "stop" in reason:
                    self.consecutive_loss_count += 1
                else:
                    self.consecutive_loss_count = 0

                self._check_engine_protection()

            self.logger.info(
                f"자동매도 주문 등록 | symbol={symbol} qty={qty} "
                f"order_id={order.order_id} reason={reason} status={order.status}"
            )

            if order.status == OrderStatus.SUBMITTED:
                self._set_reentry_block(symbol, reason)

            self._notify_order_event(
                event="🔻 자동매도 주문",
                symbol=symbol,
                side=Side.SELL,
                qty=qty,
                price=self.last_price_map.get(symbol, 0),
                status=str(order.status),
                reason=reason,
            )

            if order.status == OrderStatus.REJECTED:
                self.sell_in_progress.discard(symbol)

        except Exception as e:
            self.sell_in_progress.discard(symbol)
            self.error_count += 1
            self.logger.exception(f"자동매도 주문 실패 | symbol={symbol} qty={qty} err={e}")
            self._check_engine_protection()

    # -------------------------
    # 오래된 매도 미체결 주문 취소
    # -------------------------
    def _check_stale_sell_order(self, symbol: str):
        try:
            if not self._cfg("ENABLE_SELL_CANCEL_TIMEOUT", False):
                return
            if symbol in self.cancel_in_progress:
                return

            order = self.order_manager.get_open_sell_order_by_symbol(symbol)
            if order is None:
                return

            broker_order_id = None
            for real_id, local_id in self.order_manager.broker_to_local_id.items():
                if local_id == order.order_id:
                    broker_order_id = real_id
                    break

            if not broker_order_id:
                broker_order_id = order.order_id

            order_ts = getattr(order, "ts", None)
            if order_ts is None:
                elapsed = 0.0
            elif isinstance(order_ts, datetime):
                elapsed = time.time() - order_ts.timestamp()
            else:
                elapsed = time.time() - float(order_ts)

            if elapsed < self._cfg("SELL_ORDER_TIMEOUT_SEC", 10):
                return

            remain_qty = max(int(order.qty) - int(order.filled_qty), 0)
            if remain_qty <= 0:
                return

            self.cancel_in_progress.add(symbol)
            self.logger.warning(
                f"매도 미체결 타임아웃 | symbol={symbol} local_id={order.order_id} "
                f"broker_id={broker_order_id} elapsed={elapsed:.1f}s remain_qty={remain_qty}"
            )

            ret = self.broker.cancel_order(
                symbol=symbol,
                order_no=broker_order_id,
                qty=remain_qty,
                side=Side.SELL,
            )

            if ret == 0:
                self.last_cancel_request_time[symbol] = time.time()
                order.status = OrderStatus.CANCELED

                try:
                    self.order_manager.orders.pop(order.order_id, None)
                except Exception:
                    pass

                try:
                    remove_keys = []
                    for broker_id, local_id in self.order_manager.broker_to_local_id.items():
                        if local_id == order.order_id:
                            remove_keys.append(broker_id)
                    for broker_id in remove_keys:
                        self.order_manager.broker_to_local_id.pop(broker_id, None)
                except Exception:
                    pass

                self.sell_in_progress.discard(symbol)

                if self._cfg("RETRY_SELL_AFTER_CANCEL", False):
                    self.pending_resell[symbol] = {
                        "qty": remain_qty,
                        "reason": "취소후재매도",
                        "requested_at": time.time(),
                    }

                if self.telegram:
                    self.telegram.send(
                        f"⏳ 매도 미체결 취소 요청\n"
                        f"종목: {symbol}\n"
                        f"내부주문번호: {order.order_id}\n"
                        f"실제주문번호: {broker_order_id}\n"
                        f"잔량: {remain_qty}\n"
                        f"경과: {elapsed:.1f}초"
                    )
            else:
                self.cancel_in_progress.discard(symbol)

        except Exception as e:
            self.cancel_in_progress.discard(symbol)
            self.error_count += 1
            self.logger.exception(f"매도 미체결 취소 검사 실패 | symbol={symbol} err={e}")
            self._check_engine_protection()

    # -------------------------
    # 취소 후 재매도 재시도
    # -------------------------
    def _retry_sell_after_cancel(self, symbol: str):
        try:
            if not self._cfg("RETRY_SELL_AFTER_CANCEL", False):
                return

            pending = self.pending_resell.get(symbol)
            if not pending:
                return
            if symbol in self.sell_in_progress:
                return

            requested_at = float(pending.get("requested_at", 0))
            if time.time() - requested_at < self._cfg("RETRY_SELL_DELAY_SEC", 2):
                return

            qty = int(pending.get("qty", 0))
            reason = str(pending.get("reason", "취소후재매도"))

            if qty <= 0:
                self.pending_resell.pop(symbol, None)
                self.cancel_in_progress.discard(symbol)
                return

            pos = self.portfolio.get_position(symbol)
            hold_qty = int(getattr(pos, "qty", 0))
            if hold_qty <= 0:
                self.pending_resell.pop(symbol, None)
                self.cancel_in_progress.discard(symbol)
                return

            sell_qty = min(qty, hold_qty)
            retry_count = self.resell_retry_count.get(symbol, 0)

            if retry_count >= self._cfg("RETRY_SELL_MAX_COUNT", 3):
                self.logger.warning(
                    f"재매도 최대 횟수 초과 | symbol={symbol} retry_count={retry_count} "
                    f"| 자동청산 감시는 유지"
                )
                self.pending_resell.pop(symbol, None)
                self.cancel_in_progress.discard(symbol)
                self.sell_in_progress.discard(symbol)
                self.resell_escalated_symbols.add(symbol)
                if self.telegram:
                    self.telegram.send(
                        f"🚨 재매도 실패 고위험\n"
                        f"종목: {symbol}\n"
                        f"재시도횟수: {retry_count}\n"
                        f"상태: 자동청산 감시는 계속 유지됩니다.\n"
                        f"계좌와 미체결 상태를 직접 확인해주세요."
                    )
                return

            if self.order_manager.exists_open_order(symbol):
                return

            self.sell_in_progress.add(symbol)
            signal = Signal(
                symbol=symbol,
                side=Side.SELL,
                qty=sell_qty,
                price=0,
                order_type=OrderType.MARKET,
                reason=f"{reason}_{retry_count + 1}",
            )

            order = self.broker.place_order(signal)
            self._attach_order_route_context(order, self._get_symbol_route_context(symbol))
            self.order_manager.register(order)
            self._record_order_snapshot(order, request_price=float(self.last_price_map.get(symbol, 0) or 0.0))

            if order.status == OrderStatus.SUBMITTED:
                self.resell_retry_count[symbol] = retry_count + 1
                self.last_order_time[symbol] = time.time()
                self.daily_order_count += 1
                self._increment_strategy_daily_order_count(self._strategy_name_for_symbol(symbol))

                self.logger.warning(
                    f"취소 후 재매도 주문 등록 | symbol={symbol} qty={sell_qty} "
                    f"order_id={order.order_id} retry={self.resell_retry_count[symbol]}"
                )

                self.pending_resell.pop(symbol, None)
                self.cancel_in_progress.discard(symbol)

                if self.telegram:
                    self.telegram.send(
                        f"🔁 취소 후 재매도\n"
                        f"종목: {symbol}\n"
                        f"수량: {sell_qty}\n"
                        f"재시도: {self.resell_retry_count[symbol]}/{self._cfg('RETRY_SELL_MAX_COUNT', 3)}\n"
                        f"내부주문번호: {order.order_id}"
                    )
            else:
                self.sell_in_progress.discard(symbol)

        except Exception as e:
            self.sell_in_progress.discard(symbol)
            self.error_count += 1
            self.logger.exception(f"취소 후 재매도 실패 | symbol={symbol} err={e}")
            self._check_engine_protection()

    # -------------------------
    # 재진입 제한 설정 / 확인
    # -------------------------
    def _set_reentry_block(self, symbol: str, reason: str):
        now_ts = time.time()

        if "손절" in reason or "stop" in reason:
            block_sec = self._cfg("REENTRY_BLOCK_SEC_AFTER_STOPLOSS", 60)
        else:
            block_sec = self._cfg("REENTRY_BLOCK_SEC_AFTER_SELL", 30)

        until_ts = now_ts + block_sec
        self.reentry_block_until[symbol] = until_ts
        self.last_exit_reason[symbol] = reason

        self.logger.info(
            f"재진입 제한 설정 | symbol={symbol} reason={reason} "
            f"block_sec={block_sec} until_ts={until_ts}"
        )

    def _can_reenter_buy(self, symbol: str):
        until_ts = self.reentry_block_until.get(symbol, 0)
        now_ts = time.time()

        if now_ts < until_ts:
            remain = int(until_ts - now_ts)
            reason = self.last_exit_reason.get(symbol, "최근 청산")
            return False, f"재진입 제한 중({remain}초 남음, 사유={reason})"

        return True, "OK"

    # -------------------------
    # 주문 가능 여부 방어 로직
    # -------------------------
    def can_send_order(self, signal, tick):
        self.reset_daily_counters_if_needed()

        if not self.is_running:
            return False, "엔진 비실행 상태"

        if not self.is_market_open():
            if not self._cfg("PAPER_TRADING", self._cfg("DRY_RUN", False)):
                return False, "장외 시간"

        if self.engine_protected:
            return False, "엔진 보호모드"

        daily_loss_hit, realized_pnl, daily_loss_limit = self._daily_loss_limit_reached()
        if daily_loss_hit:
            return False, f"daily loss limit reached ({realized_pnl:.0f}<={daily_loss_limit:.0f})"

        if self.daily_order_count >= self.max_daily_orders:
            return False, "일일 주문 한도 초과"

        symbol = signal.symbol
        strategy_name = self._strategy_name_for_signal(signal)
        side_value = self._side_value(signal.side)
        qty = max(0, self._safe_int(getattr(signal, "qty", 0), 0))
        price = max(0, self._safe_float(getattr(tick, "price", 0), 0.0))
        estimated_amount = self._estimate_order_amount(qty, price)
        order_amount_limit = self._effective_order_amount_limit(signal=signal)
        strategy_max_positions = max(
            1,
            self._safe_int(
                self._strategy_cfg_value(strategy_name, "max_positions", self.max_positions),
                self.max_positions,
            ),
        )
        strategy_max_symbol_position = max(
            1,
            self._safe_int(
                self._strategy_cfg_value(strategy_name, "max_symbol_position", self.max_symbol_position),
                self.max_symbol_position,
            ),
        )
        cash = float(getattr(self.portfolio, "cash", 0.0))

        if qty <= 0:
            return False, "주문수량 오류"

        if side_value == "BUY":
            if strategy_name and not self._strategy_enabled(strategy_name):
                return False, f"전략 비활성화({strategy_name})"
            if strategy_name and self._strategy_daily_order_count(strategy_name) >= self._strategy_daily_order_limit(strategy_name):
                return False, (
                    f"전략 일일 주문 한도 초과("
                    f"{self._strategy_daily_order_count(strategy_name)}>="
                    f"{self._strategy_daily_order_limit(strategy_name)})"
                )

            ok, reason = self._can_reenter_buy(symbol)
            if not ok:
                return False, reason

            last_ts = float(self.last_order_time.get(symbol, 0))
            now_ts = time.time()
            if last_ts > 0 and now_ts - last_ts < self.order_cooldown_sec:
                remain = max(1, int(self.order_cooldown_sec - (now_ts - last_ts)))
                return False, f"주문 쿨다운 중({remain}초 남음)"

            strategy_interval_sec = max(
                self._safe_int(
                    self._strategy_cfg_value(strategy_name, "order_interval_seconds", 0),
                    0,
                ),
                0,
            )
            strategy_last_ts = float(self.last_order_time_by_strategy.get(strategy_name, 0.0))
            if strategy_interval_sec > 0 and strategy_last_ts > 0 and now_ts - strategy_last_ts < strategy_interval_sec:
                remain = max(1, int(strategy_interval_sec - (now_ts - strategy_last_ts)))
                return False, f"전략 주문 간격 대기({strategy_name}, {remain}초 남음)"

            pos = self.portfolio.get_position(symbol)
            hold_qty = int(getattr(pos, "qty", 0))
            if hold_qty >= strategy_max_symbol_position:
                return False, f"전략 종목 최대 보유수 초과({hold_qty}>={strategy_max_symbol_position})"

            open_symbols = self._current_open_symbols()
            strategy_open_symbols = self._current_open_symbols_for_strategy(strategy_name)
            if hold_qty <= 0 and open_symbols >= self.max_positions:
                return False, "동시 보유 종목 수 초과"
            if hold_qty <= 0 and strategy_open_symbols >= strategy_max_positions:
                return False, f"전략 동시 보유 종목 수 초과({strategy_open_symbols}>={strategy_max_positions})"

            if getattr(tick, "volume", 0) < self.min_tick_volume:
                return False, "틱 거래량 부족"

            if order_amount_limit > 0 and estimated_amount > order_amount_limit:
                return False, f"주문금액 한도 초과({estimated_amount}>{order_amount_limit})"

            if estimated_amount > cash:
                return False, f"예수금 부족({estimated_amount}>{int(cash)})"

        return True, "OK"

    # -------------------------
    # 진입 처리
    # -------------------------
    def on_tick(self, tick):
        try:
            if self.engine_protected:
                return

            symbol = tick.symbol
            price = int(tick.price)

            self.logger.info(f"[CHECK] {symbol} price={price}")

            signal = self.strategy.generate_signal(tick, self.portfolio)
            if signal is None:
                self._record_strategy_reject_details(getattr(self.strategy, "last_reject_details", {}))
                reject_reason = getattr(self.strategy, "last_reject_reason", "")
                if reject_reason:
                    self.logger.info(f"[SIGNAL_SKIP] {symbol} | {reject_reason}")
                return

            self._normalize_buy_signal_qty(signal, tick)
            strategy_name = self._strategy_name_for_signal(signal)

            entry_score = self._extract_score_from_reason(getattr(signal, "reason", ""))
            ok, reason = self.can_send_order(signal, tick)
            if not ok:
                self._record_strategy_order_block(strategy_name, reason)
                self._record_signal_snapshot(signal, tick, allowed=False, block_reason=reason)
                self.logger.info(
                    f"[{signal.symbol}] 주문 차단 | {reason} | "
                    f"score={entry_score} chg={getattr(tick, 'price_change_pct', 0.0)} "
                    f"strength={getattr(tick, 'trade_strength', 0.0)} "
                    f"vr={getattr(tick, 'volume_ratio', 0.0)}"
                )
                return

            self._record_signal_snapshot(signal, tick, allowed=True)
            self._record_strategy_order_ready(strategy_name)
            self.logger.info(
                f"[ORDER_READY] {signal.symbol} side={signal.side} qty={signal.qty} "
                f"score={entry_score} reason={signal.reason}"
            )

            # BUY 신호 직전 컨텍스트 저장
            if self._side_value(signal.side) == "BUY":
                route = self._get_signal_route_context(signal)
                self.last_entry_signal_context[signal.symbol] = {
                    "price": float(tick.price),
                    "trade_strength": float(getattr(tick, "trade_strength", 0.0)),
                    "price_change_pct": float(getattr(tick, "price_change_pct", 0.0)),
                    "volume_ratio": float(getattr(tick, "volume_ratio", 0.0)),
                    "strategy_name": route["strategy_name"],
                    "selector_name": route["selector_name"],
                    "universe_name": route["universe_name"],
                }

            order = self.broker.place_order(signal)
            self._attach_order_route_context(order, self._get_signal_route_context(signal))
            self.order_manager.register(order)
            self._record_order_snapshot(order, request_price=float(getattr(tick, "price", 0.0) or 0.0))

            if order.status == OrderStatus.SUBMITTED:
                self.last_order_time[signal.symbol] = time.time()
                self.last_order_time_by_strategy[strategy_name] = time.time()
                self.daily_order_count += 1
                self._increment_strategy_daily_order_count(strategy_name)

                if self._side_value(signal.side) == "BUY" and hasattr(self.strategy, "mark_entry"):
                    self.strategy.mark_entry(signal.symbol, tick.ts)

            if self._cfg("PAPER_TRADING", self._cfg("DRY_RUN", False)) and self._side_value(signal.side) == "BUY":
                class StubFill:
                    pass

                fill = StubFill()
                fill.order_id = order.order_id
                fill.symbol = order.symbol
                fill.side = order.side
                fill.fill_qty = order.qty
                fill.fill_price = tick.price
                fill.unfilled_qty = 0
                self.on_fill(fill)

            self.logger.info(
                f"주문 등록 | id={order.order_id} symbol={order.symbol} "
                f"side={order.side} qty={order.qty} count={self.daily_order_count}/{self.max_daily_orders} "
                f"score={entry_score}"
            )

            self._notify_order_event(
                event="📈 주문 발생",
                symbol=order.symbol,
                side=order.side,
                qty=order.qty,
                price=tick.price,
                status=str(order.status),
                score=entry_score,
                reason=signal.reason,
            )

            if order.status == OrderStatus.REJECTED:
                self.logger.warning(f"주문 거부 | {order.symbol}")
                self._notify_order_event(
                    event="❌ 주문 거부",
                    symbol=order.symbol,
                    side=order.side,
                    qty=order.qty,
                    price=tick.price,
                    status=str(order.status),
                    score=entry_score,
                    reason=signal.reason,
                )

        except Exception as e:
            self.error_count += 1
            self.logger.exception(f"주문 처리 실패 | {e}")
            self._check_engine_protection()
            if self.telegram and self._cfg("ENABLE_TELEGRAM_LOG", False):
                self.telegram.send(
                    f"🚨 주문 처리 실패\n"
                    f"종목: {self._symbol_label(tick.symbol)}\n"
                    f"예수금: {getattr(self.portfolio, 'cash', 0):,.0f}\n"
                    f"실현손익: {getattr(self.portfolio, 'realized_pnl', 0):,.0f}\n"
                    f"에러: {e}"
                )

    # -------------------------
    # 체결 반영
    # -------------------------
    def _normalize_fill_qty(self, order, fill) -> int:
        try:
            reported_fill_qty = int(getattr(fill, "fill_qty", 0) or 0)
            if order is None:
                return max(reported_fill_qty, 0)

            prev_filled = int(getattr(order, "filled_qty", 0) or 0)
            total_qty = int(getattr(order, "qty", 0) or 0)
            raw_unfilled = getattr(fill, "unfilled_qty", None)

            if raw_unfilled is not None and total_qty > 0:
                unfilled_qty = max(int(raw_unfilled or 0), 0)
                cumulative_filled = max(total_qty - unfilled_qty, 0)
                normalized_fill_qty = cumulative_filled - prev_filled
                return max(normalized_fill_qty, 0)

            return max(reported_fill_qty, 0)
        except Exception:
            return max(int(getattr(fill, "fill_qty", 0) or 0), 0)

    def on_fill(self, fill):
        try:
            symbol = fill.symbol

            pos_before = self.portfolio.get_position(symbol)
            qty_before = int(getattr(pos_before, "qty", 0))
            realized_before = float(getattr(self.portfolio, "realized_pnl", 0.0))

            local_order_id = self.order_manager.bind_broker_order_id(
                symbol=fill.symbol,
                broker_order_id=fill.order_id
            )
            resolved_order_id = local_order_id or self.order_manager.resolve_order_id(fill.order_id)
            tracked_order = self.order_manager.get_order(resolved_order_id) if resolved_order_id else None
            normalized_fill_qty = self._normalize_fill_qty(tracked_order, fill)

            if normalized_fill_qty <= 0:
                self.logger.info(
                    f"중복/누적 체결 무시 | broker_id={fill.order_id} local_id={resolved_order_id} "
                    f"symbol={fill.symbol} raw_fill_qty={getattr(fill, 'fill_qty', 0)} "
                    f"unfilled={getattr(fill, 'unfilled_qty', None)}"
                )
                return

            original_fill_qty = int(getattr(fill, "fill_qty", 0) or 0)
            fill.fill_qty = normalized_fill_qty

            self.portfolio.update_fill(fill)

            order = self.order_manager.apply_fill(
                order_id=resolved_order_id,
                fill_qty=fill.fill_qty,
                fill_price=fill.fill_price,
                unfilled_qty=getattr(fill, "unfilled_qty", None)
            )

            pos_after = self.portfolio.get_position(symbol)
            qty_after = int(getattr(pos_after, "qty", 0))
            avg_after = float(getattr(pos_after, "avg_price", 0.0))
            realized_after = float(getattr(self.portfolio, "realized_pnl", 0.0))
            realized_delta = realized_after - realized_before
            self._record_fill_snapshot(
                fill,
                local_order_id=resolved_order_id,
                unfilled_qty=getattr(fill, "unfilled_qty", None),
                realized_delta=realized_delta,
            )

            if order is None:
                self.logger.warning(
                    f"체결은 들어왔지만 주문 매핑 실패 | broker_id={fill.order_id} "
                    f"symbol={fill.symbol} qty={fill.fill_qty} price={fill.fill_price}"
                )
            else:
                self.logger.info(
                    f"체결 반영 | broker_id={fill.order_id} local_id={resolved_order_id} "
                    f"symbol={fill.symbol} side={fill.side} qty={fill.fill_qty} "
                    f"raw_qty={original_fill_qty} price={fill.fill_price} "
                    f"unfilled={getattr(fill, 'unfilled_qty', 0)} "
                    f"status={order.status}"
                )

            side_value = self._side_value(getattr(fill, "side", ""))
            fill_status = "FILLED" if int(getattr(fill, "unfilled_qty", 0) or 0) == 0 else "PARTIAL"

            self._notify_order_event(
                event="✅ 체결",
                symbol=fill.symbol,
                side=side_value,
                qty=int(getattr(fill, "fill_qty", 0)),
                price=float(getattr(fill, "fill_price", 0.0)),
                status=fill_status,
                reason=f"order_id={getattr(fill, 'order_id', '')}",
            )

            if side_value == "BUY":
                self._start_trade_cycle_if_needed(symbol, qty_before, qty_after, avg_after)
            elif side_value == "SELL":
                self._accumulate_trade_realized_pnl(symbol, realized_delta)
                self._close_trade_cycle_if_needed(
                    symbol=symbol,
                    qty_before=qty_before,
                    qty_after=qty_after,
                    fill_price=float(fill.fill_price),
                    exit_reason=self.last_exit_reason.get(symbol, "")
                )

            if qty_after <= 0:
                self.sell_in_progress.discard(symbol)
                self.cancel_in_progress.discard(symbol)
                self.pending_resell.pop(symbol, None)
                self.resell_retry_count.pop(symbol, None)
                self.partial_exit_done.discard(symbol)
                self.breakeven_active.discard(symbol)
                self.trailing_armed.discard(symbol)
                self.trailing_high_price.pop(symbol, None)
            else:
                if side_value == "SELL":
                    self.sell_in_progress.discard(symbol)

        except Exception as e:
            self.error_count += 1
            self.logger.exception(f"체결 처리 실패 | {e}")
            self._check_engine_protection()

    # -------------------------
    # 브로커 메시지
    # -------------------------
    def on_broker_msg(self, msg):
        try:
            self.logger.info(f"[BROKER_MSG] {msg}")
        except Exception:
            pass

    # -------------------------
    # 엔진 보호모드
    # -------------------------
    def _check_engine_protection(self):
        try:
            max_consecutive_loss = self._cfg("MAX_CONSECUTIVE_LOSS", 3)
            max_error_count = self._cfg("MAX_ERROR_COUNT", self._cfg("MAX_ENGINE_ERROR_COUNT", 5))
            daily_loss_hit, realized_pnl, daily_loss_limit = self._daily_loss_limit_reached()

            if self.consecutive_loss_count >= max_consecutive_loss:
                self.engine_protected = True
                self.logger.warning(
                    f"엔진 보호모드 진입 | 연속손실={self.consecutive_loss_count} "
                    f"기준={max_consecutive_loss}"
                )

            if self.error_count >= max_error_count:
                self.engine_protected = True
                self.logger.warning(
                    f"엔진 보호모드 진입 | error_count={self.error_count} "
                    f"기준={max_error_count}"
                )

            if daily_loss_hit:
                self.engine_protected = True
                self.daily_loss_protection_active = True
                self.logger.warning(
                    f"일일 손실 한도 도달 | realized_pnl={realized_pnl:.0f} "
                    f"daily_loss_limit={daily_loss_limit:.0f}"
                )

        except Exception as e:
            self.logger.warning(f"엔진 보호모드 점검 실패 | {e}")
