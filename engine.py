# engine.py

import csv
import time
from datetime import datetime
from pathlib import Path

import config
from core.models import Order, TickData, OrderStatus, Signal, Side, OrderType
from core.order_manager import OrderManager
from core.portfolio import Portfolio
from core.risk_manager import RiskManager
from data.news_provider import NewsProvider


class TradingEngine:
    def __init__(self, broker, strategy, logger, telegram=None, initial_cash=5_000_000, test_name="default"):
        self.broker = broker
        self.strategy = strategy
        self.logger = logger
        self.telegram = telegram
        self.test_name = str(test_name).strip() if test_name else "default"

        self.portfolio = Portfolio(initial_cash=initial_cash)
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager()

        self.is_running = False

        # 외부 점수 공급기
        self.news_provider = NewsProvider(logger=logger)

        # 주문 방어 설정
        self.last_order_time = {}
        self.order_cooldown_sec = 10
        self.daily_order_count = 0
        self.max_daily_orders = 20
        self.current_trading_date = datetime.now().date()

        self.min_tick_volume = 1
        self.max_symbol_position = 1

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

        self.cancel_in_progress = set()
        self.pending_resell = {}
        self.resell_retry_count = {}
        self.abandon_resell_symbols = set()
        self.last_cancel_request_time = {}

        self.consecutive_loss_count = 0
        self.error_count = 0
        self.engine_protected = False

        self.trade_log = []
        self.win_count = 0
        self.loss_count = 0
        self.trade_open_info = {}
        self.trade_cycle_realized_pnl = {}

        # -------------------------
        # 엔진 직접 약손절 / 초기 되밀림 관리
        # 전략 should_exit 의존 없이 엔진이 직접 처리
        # -------------------------
        self.tick_seq = {}
        self.last_entry_signal_context = {}
        self.position_entry_context = {}

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

    def _register_tick(self, symbol: str):
        self.tick_seq[symbol] = int(self.tick_seq.get(symbol, 0)) + 1
        return self.tick_seq[symbol]

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
            if qty_before <= 0 and qty_after > 0:
                self.trade_open_info[symbol] = {
                    "entry_time": datetime.now(),
                    "entry_price": float(avg_price_after),
                    "entry_qty": int(qty_after),
                }
                self.trade_cycle_realized_pnl[symbol] = 0.0

                # 엔진 직접 약손절용 진입 컨텍스트 생성
                signal_ctx = self.last_entry_signal_context.get(symbol, {})
                self.position_entry_context[symbol] = {
                    "entry_tick_no": int(self.tick_seq.get(symbol, 0)),
                    "entry_signal_price": float(signal_ctx.get("price", avg_price_after)),
                    "entry_signal_strength": float(signal_ctx.get("trade_strength", 0.0)),
                    "entry_signal_price_change_pct": float(signal_ctx.get("price_change_pct", 0.0)),
                    "entry_signal_volume_ratio": float(signal_ctx.get("volume_ratio", 0.0)),
                    "peak_price_after_entry": float(avg_price_after),
                }

                self.logger.info(
                    f"[TRADE_OPEN] symbol={symbol} entry_price={avg_price_after:.2f} qty={qty_after}"
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
            }

            self.trade_log.append(trade_item)
            self._append_trade_log_to_csv(trade_item)

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

            summary = self.get_trade_summary()
            self.logger.info(
                f"[PERFORMANCE] trades={summary['total_trades']} "
                f"wins={summary['wins']} losses={summary['losses']} "
                f"win_rate={summary['win_rate']:.2f}% "
                f"avg_profit={summary['avg_profit_pct']:.4f}% "
                f"avg_loss={summary['avg_loss_pct']:.4f}% "
                f"net_pnl={summary['net_pnl']:.2f}"
            )

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
            self.last_order_time = {}
            self.logger.info("일일 주문 카운터 초기화")

    def start(self):
        self.broker.connect()
        self.is_running = True
        self.logger.info("브로커 연결 완료")

    def stop(self):
        if not self.is_running:
            self.logger.info("이미 종료 상태")
            self.log_trade_summary(prefix="종료 전 성과 요약")
            try:
                self.broker.shutdown()
            except Exception as e:
                self.logger.warning(f"브로커 종료 실패 | {e}")
            return

        self.logger.info("엔진 종료 시작")
        self.log_trade_summary(prefix="종료 전 성과 요약")
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
    def manage_pending_orders(self):
        try:
            if not self.is_running:
                return

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
        if self.engine_protected:
            return

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

            if self.telegram and self._cfg("ENABLE_TELEGRAM_LOG", False):
                self.telegram.send(
                    f"📉 청산신호\n"
                    f"종목: {symbol}\n"
                    f"유형: {event}\n"
                    f"현재가: {price}\n"
                    f"평단: {avg_price:.2f}\n"
                    f"수량: {qty}\n"
                    f"손익률: {pnl_pct:.2%}"
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

    # -------------------------
    # 자동 매도 검사
    # -------------------------
    def _check_auto_exit(self, symbol: str, price: int, tick=None):
        try:
            pos = self.portfolio.get_position(symbol)
            qty = int(getattr(pos, "qty", 0))
            avg_price = float(getattr(pos, "avg_price", 0))

            if qty <= 0 or avg_price <= 0:
                return
            if symbol in self.abandon_resell_symbols:
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

            # 0) 엔진 직접 약손절 / 초기 되밀림
            if tick is not None:
                early_stop = self._check_engine_early_stop(symbol, price, avg_price, qty, tick)
                if early_stop:
                    reason = early_stop["reason"]
                    self.last_exit_reason[symbol] = reason
                    self._log_exit_event(symbol, price, avg_price, qty, early_stop["event"])
                    self.logger.info(
                        f"엔진 직접 약손절 발동 | symbol={symbol} price={price} avg_price={avg_price} "
                        f"qty={qty} pnl_pct={pnl_pct:.2%} reason={reason}"
                    )
                    self._submit_auto_sell(symbol=symbol, qty=qty, reason=reason)
                    return

            # 1) 손절 먼저
            if pnl_pct <= self._cfg("STOP_LOSS_PCT", -0.02):
                exit_reason = f"손절 {pnl_pct:.2%}"
                self.last_exit_reason[symbol] = exit_reason
                self._log_exit_event(symbol, price, avg_price, qty, "STOP_LOSS")
                self.logger.info(
                    f"자동매도 조건 충족 | symbol={symbol} price={price} "
                    f"avg_price={avg_price} qty={qty} pnl_pct={pnl_pct:.2%} reason={exit_reason}"
                )
                self._submit_auto_sell(symbol=symbol, qty=qty, reason=exit_reason)
                return

            # 2) 부분익절
            if symbol not in self.partial_exit_done and pnl_pct >= self._cfg("PARTIAL_TAKE_PROFIT_PCT", 0.02):
                sell_qty = max(int(qty * self._cfg("PARTIAL_TAKE_RATIO", 0.5)), 1)
                sell_qty = min(sell_qty, qty)

                self.last_exit_reason[symbol] = "부분익절"
                self._log_exit_event(symbol, price, avg_price, sell_qty, "PARTIAL_TAKE")
                self.logger.info(
                    f"부분익절 발생 | symbol={symbol} qty={sell_qty} pnl={pnl_pct:.2%}"
                )

                self.partial_exit_done.add(symbol)

                if self._cfg("BREAKEVEN_ENABLED", False):
                    self.breakeven_active.add(symbol)
                if self._cfg("TRAILING_STOP_ENABLED", False):
                    self.trailing_high_price[symbol] = price

                self._submit_auto_sell(symbol, sell_qty, "부분익절")
                return

            # 3) 부분익절 이후 최고가 갱신
            if symbol in self.partial_exit_done and self._cfg("TRAILING_STOP_ENABLED", False):
                prev_high = self.trailing_high_price.get(symbol, 0)
                if price > prev_high:
                    self.trailing_high_price[symbol] = price
                    self.logger.info(
                        f"[TRAIL_HIGH] {symbol} high_price_update prev={prev_high} new={price}"
                    )

            # 4) trailing arm 활성화
            trailing_start_pct = max(
                self._cfg("PARTIAL_TAKE_PROFIT_PCT", 0.02) + 0.003,
                self._cfg("TAKE_PROFIT_PCT", 0.03) * 0.7
            )
            if symbol in self.partial_exit_done and self._cfg("TRAILING_STOP_ENABLED", False) and pnl_pct >= trailing_start_pct:
                if symbol not in self.trailing_armed:
                    self.trailing_armed.add(symbol)
                    self.logger.info(
                        f"[TRAIL_ARM] {symbol} pnl={pnl_pct:.2%} start_pct={trailing_start_pct:.2%}"
                    )

            # 5) 본절 보호
            if symbol in self.breakeven_active:
                if pnl_pct <= 0.001:
                    self.last_exit_reason[symbol] = "본절청산"
                    self._log_exit_event(symbol, price, avg_price, qty, "BREAKEVEN_EXIT")
                    self.logger.info(
                        f"본절 청산 | symbol={symbol} price={price} avg_price={avg_price} pnl={pnl_pct:.2%}"
                    )
                    self._submit_auto_sell(symbol, qty, "본절청산")
                    return

            # 6) 트레일링 스탑
            if symbol in self.partial_exit_done and symbol in self.trailing_armed and self._cfg("TRAILING_STOP_ENABLED", False):
                high_price = self.trailing_high_price.get(symbol, 0)
                if high_price > 0:
                    trailing_stop_price = high_price * (1 - self._cfg("TRAILING_STOP_PCT", 0.01))
                    self.logger.info(
                        f"[TRAIL_CHECK] {symbol} price={price} high={high_price} stop={trailing_stop_price:.2f}"
                    )
                    if price <= trailing_stop_price:
                        reason = f"트레일링청산 high={high_price}"
                        self.last_exit_reason[symbol] = reason
                        self._log_exit_event(symbol, price, avg_price, qty, "TRAILING_STOP")
                        self.logger.info(
                            f"트레일링 스탑 청산 | symbol={symbol} price={price} "
                            f"high={high_price} stop={trailing_stop_price:.2f}"
                        )
                        self._submit_auto_sell(symbol, qty, reason)
                        return

            # 7) 부분익절 안 한 상태에서 최종 익절
            if symbol not in self.partial_exit_done and pnl_pct >= self._cfg("TAKE_PROFIT_PCT", 0.03):
                exit_reason = f"익절 {pnl_pct:.2%}"
                self.last_exit_reason[symbol] = exit_reason
                self._log_exit_event(symbol, price, avg_price, qty, "TAKE_PROFIT")
                self.logger.info(
                    f"자동익절 조건 충족 | symbol={symbol} price={price} "
                    f"avg_price={avg_price} qty={qty} pnl_pct={pnl_pct:.2%}"
                )
                self._submit_auto_sell(symbol=symbol, qty=qty, reason=exit_reason)
                return

        except Exception as e:
            self.logger.exception(f"자동매도 검사 실패 | symbol={symbol} price={price} err={e}")

    # -------------------------
    # 자동 매도 주문
    # -------------------------
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
            self.order_manager.register(order)

            if self._cfg("DRY_RUN", False):
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

            if self.telegram:
                self.telegram.send(
                    f"🔻 자동매도 주문\n"
                    f"종목: {symbol}\n"
                    f"수량: {qty}\n"
                    f"사유: {reason}\n"
                    f"내부주문번호: {order.order_id}\n"
                    f"일일주문: {self.daily_order_count}/{self.max_daily_orders}"
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
                    f"재매도 최대 횟수 초과 | symbol={symbol} retry_count={retry_count}"
                )
                self.pending_resell.pop(symbol, None)
                self.cancel_in_progress.discard(symbol)
                self.sell_in_progress.discard(symbol)
                self.abandon_resell_symbols.add(symbol)
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
            self.order_manager.register(order)

            if order.status == OrderStatus.SUBMITTED:
                self.resell_retry_count[symbol] = retry_count + 1
                self.last_order_time[symbol] = time.time()
                self.daily_order_count += 1

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
            if not self._cfg("DRY_RUN", False):
                return False, "장외 시간"

        if self.engine_protected:
            return False, "엔진 보호모드"

        if self.daily_order_count >= self.max_daily_orders:
            return False, "일일 주문 한도 초과"

        symbol = signal.symbol
        side_value = self._side_value(signal.side)

        if side_value == "BUY":
            ok, reason = self._can_reenter_buy(symbol)
            if not ok:
                return False, reason

            pos = self.portfolio.get_position(symbol)
            hold_qty = int(getattr(pos, "qty", 0))
            if hold_qty >= self.max_symbol_position:
                return False, "종목 최대 보유수 초과"

            if getattr(tick, "volume", 0) < self.min_tick_volume:
                return False, "틱 거래량 부족"

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
                return

            entry_score = self._extract_score_from_reason(getattr(signal, "reason", ""))
            ok, reason = self.can_send_order(signal, tick)
            if not ok:
                self.logger.info(
                    f"[{signal.symbol}] 주문 차단 | {reason} | "
                    f"score={entry_score} chg={getattr(tick, 'price_change_pct', 0.0)} "
                    f"strength={getattr(tick, 'trade_strength', 0.0)} "
                    f"vr={getattr(tick, 'volume_ratio', 0.0)}"
                )
                return

            self.logger.info(
                f"[ORDER_READY] {signal.symbol} side={signal.side} qty={signal.qty} "
                f"score={entry_score} reason={signal.reason}"
            )

            # BUY 신호 직전 컨텍스트 저장
            if self._side_value(signal.side) == "BUY":
                self.last_entry_signal_context[signal.symbol] = {
                    "price": float(tick.price),
                    "trade_strength": float(getattr(tick, "trade_strength", 0.0)),
                    "price_change_pct": float(getattr(tick, "price_change_pct", 0.0)),
                    "volume_ratio": float(getattr(tick, "volume_ratio", 0.0)),
                }

            order = self.broker.place_order(signal)
            self.order_manager.register(order)

            if order.status == OrderStatus.SUBMITTED:
                self.last_order_time[signal.symbol] = time.time()
                self.daily_order_count += 1

                if self._side_value(signal.side) == "BUY" and hasattr(self.strategy, "mark_entry"):
                    self.strategy.mark_entry(signal.symbol, tick.ts)

            if self._cfg("DRY_RUN", False) and self._side_value(signal.side) == "BUY":
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

            if self.telegram:
                self.telegram.send(
                    f"📈 주문 발생\n"
                    f"종목: {order.symbol}\n"
                    f"방향: {order.side}\n"
                    f"수량: {order.qty}\n"
                    f"상태: {order.status}\n"
                    f"점수: {entry_score}\n"
                    f"사유: {signal.reason}\n"
                    f"일일주문: {self.daily_order_count}/{self.max_daily_orders}"
                )

            if order.status == OrderStatus.REJECTED:
                self.logger.warning(f"주문 거부 | {order.symbol}")
                if self.telegram:
                    self.telegram.send(
                        f"❌ 주문 거부\n"
                        f"종목: {order.symbol}\n"
                        f"방향: {order.side}\n"
                        f"수량: {order.qty}\n"
                        f"점수: {entry_score}\n"
                        f"사유: {signal.reason}"
                    )

        except Exception as e:
            self.error_count += 1
            self.logger.exception(f"주문 처리 실패 | {e}")
            self._check_engine_protection()
            if self.telegram:
                self.telegram.send(f"🚨 주문 처리 실패\n{tick.symbol}\n{e}")

    # -------------------------
    # 체결 반영
    # -------------------------
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

            if order is None:
                self.logger.warning(
                    f"체결은 들어왔지만 주문 매핑 실패 | broker_id={fill.order_id} "
                    f"symbol={fill.symbol} qty={fill.fill_qty} price={fill.fill_price}"
                )
            else:
                self.logger.info(
                    f"체결 반영 | broker_id={fill.order_id} local_id={resolved_order_id} "
                    f"symbol={fill.symbol} side={fill.side} qty={fill.fill_qty} "
                    f"price={fill.fill_price} unfilled={getattr(fill, 'unfilled_qty', 0)} "
                    f"status={order.status}"
                )

            side_value = self._side_value(getattr(fill, "side", ""))
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
            max_error_count = self._cfg("MAX_ENGINE_ERROR_COUNT", 5)

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

        except Exception as e:
            self.logger.warning(f"엔진 보호모드 점검 실패 | {e}")
