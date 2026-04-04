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

    def _close_trade_cycle_if_needed(
        self,
        symbol: str,
        qty_before: int,
        qty_after: int,
        fill_price: float,
        exit_reason: str = "",
    ):
        try:
            if not (qty_before > 0 and qty_after <= 0):
                return

            open_info = self.trade_open_info.pop(symbol, None)
            total_realized_pnl = float(self.trade_cycle_realized_pnl.pop(symbol, 0.0))

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
    # 장 시간 체크
    # -------------------------
    def is_market_open(self):
        now = datetime.now().time()
        market_open = datetime.strptime("09:00", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        return market_open <= now <= market_close

    # -------------------------
    # 일자 변경 시 카운터 리셋
    # -------------------------
    def reset_daily_counters_if_needed(self):
        today = datetime.now().date()
        if today != self.current_trading_date:
            self.current_trading_date = today
            self.daily_order_count = 0
            self.last_order_time = {}
            self.logger.info("일일 주문 카운터 초기화")

    # -------------------------
    # 시작 / 종료
    # -------------------------
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

            return {
                "deposit": deposit,
                "positions": positions,
            }

        except Exception as e:
            self.logger.exception(f"계좌 동기화 실패 | {e}")
            return {
                "deposit": 0,
                "positions": [],
            }

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

            self.logger.info(
                f"[TICK] {symbol} price={price} vol={volume} "
                f"chg={price_change_pct} strength={trade_strength} vr={volume_ratio} "
                f"news={external_scores['news_score']} "
                f"theme={external_scores['theme_score']} "
                f"leader={external_scores['leader_score']}"
            )

            if price <= 0:
                return

            self.last_price_map[symbol] = price

            self._check_auto_exit(symbol, price)
            self._check_stale_sell_order(symbol)
            self._retry_sell_after_cancel(symbol)

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

            if self.telegram and getattr(config, "ENABLE_TELEGRAM_LOG", False):
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
    # 자동 매도 검사
    # -------------------------
    def _check_auto_exit(self, symbol: str, price: int):
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

            # 1) 손절 먼저
            if pnl_pct <= config.STOP_LOSS_PCT:
                exit_reason = f"손절 {pnl_pct:.2%}"
                self._log_exit_event(symbol, price, avg_price, qty, "STOP_LOSS")
                self.logger.info(
                    f"자동매도 조건 충족 | symbol={symbol} price={price} "
                    f"avg_price={avg_price} qty={qty} pnl_pct={pnl_pct:.2%} reason={exit_reason}"
                )
                self._submit_auto_sell(symbol=symbol, qty=qty, reason=exit_reason)
                return

            # 2) 부분익절
            if (
                symbol not in self.partial_exit_done
                and pnl_pct >= config.PARTIAL_TAKE_PROFIT_PCT
            ):
                sell_qty = max(int(qty * config.PARTIAL_TAKE_RATIO), 1)
                sell_qty = min(sell_qty, qty)

                self._log_exit_event(symbol, price, avg_price, sell_qty, "PARTIAL_TAKE")
                self.logger.info(
                    f"부분익절 발생 | symbol={symbol} qty={sell_qty} pnl={pnl_pct:.2%}"
                )

                self.partial_exit_done.add(symbol)

                if config.BREAKEVEN_ENABLED:
                    self.breakeven_active.add(symbol)

                if config.TRAILING_STOP_ENABLED:
                    self.trailing_high_price[symbol] = price

                self._submit_auto_sell(symbol, sell_qty, "부분익절")
                return

            # 3) 부분익절 이후 최고가 갱신
            if symbol in self.partial_exit_done and config.TRAILING_STOP_ENABLED:
                prev_high = self.trailing_high_price.get(symbol, 0)
                if price > prev_high:
                    self.trailing_high_price[symbol] = price
                    self.logger.info(
                        f"[TRAIL_HIGH] {symbol} high_price_update prev={prev_high} new={price}"
                    )

            # 4) trailing arm 활성화
            trailing_start_pct = max(
                config.PARTIAL_TAKE_PROFIT_PCT + 0.003,
                config.TAKE_PROFIT_PCT * 0.7
            )
            if (
                symbol in self.partial_exit_done
                and config.TRAILING_STOP_ENABLED
                and pnl_pct >= trailing_start_pct
            ):
                if symbol not in self.trailing_armed:
                    self.trailing_armed.add(symbol)
                    self.logger.info(
                        f"[TRAIL_ARM] {symbol} pnl={pnl_pct:.2%} start_pct={trailing_start_pct:.2%}"
                    )

            # 5) 본절 보호
            if symbol in self.breakeven_active:
                if pnl_pct <= 0.001:
                    self._log_exit_event(symbol, price, avg_price, qty, "BREAKEVEN_EXIT")
                    self.logger.info(
                        f"본절 청산 | symbol={symbol} price={price} "
                        f"avg_price={avg_price} pnl={pnl_pct:.2%}"
                    )
                    self._submit_auto_sell(symbol, qty, "본절청산")
                    return

            # 6) 트레일링 스탑
            if (
                symbol in self.partial_exit_done
                and symbol in self.trailing_armed
                and config.TRAILING_STOP_ENABLED
            ):
                high_price = self.trailing_high_price.get(symbol, 0)
                if high_price > 0:
                    trailing_stop_price = high_price * (1 - config.TRAILING_STOP_PCT)

                    self.logger.info(
                        f"[TRAIL_CHECK] {symbol} price={price} high={high_price} "
                        f"stop={trailing_stop_price:.2f}"
                    )

                    if price <= trailing_stop_price:
                        self._log_exit_event(symbol, price, avg_price, qty, "TRAILING_STOP")
                        self.logger.info(
                            f"트레일링 스탑 청산 | symbol={symbol} price={price} "
                            f"high={high_price} stop={trailing_stop_price:.2f}"
                        )
                        self._submit_auto_sell(
                            symbol,
                            qty,
                            f"트레일링청산 high={high_price}"
                        )
                        return

            # 7) 부분익절 안 한 상태에서 최종 익절
            if symbol not in self.partial_exit_done and pnl_pct >= config.TAKE_PROFIT_PCT:
                exit_reason = f"익절 {pnl_pct:.2%}"
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

            if config.DRY_RUN:
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

                if "손절" in reason:
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
            if not config.ENABLE_SELL_CANCEL_TIMEOUT:
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

            if elapsed < config.SELL_ORDER_TIMEOUT_SEC:
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

                if config.RETRY_SELL_AFTER_CANCEL:
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
            if not config.RETRY_SELL_AFTER_CANCEL:
                return

            pending = self.pending_resell.get(symbol)
            if not pending:
                return

            if symbol in self.sell_in_progress:
                return

            requested_at = float(pending.get("requested_at", 0))
            if time.time() - requested_at < config.RETRY_SELL_DELAY_SEC:
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
            if retry_count >= config.RETRY_SELL_MAX_COUNT:
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
                        f"재시도: {self.resell_retry_count[symbol]}/{config.RETRY_SELL_MAX_COUNT}\n"
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
    # 재진입 제한 설정
    # -------------------------
    def _set_reentry_block(self, symbol: str, reason: str):
        now_ts = time.time()

        if "손절" in reason:
            block_sec = config.REENTRY_BLOCK_SEC_AFTER_STOPLOSS
        else:
            block_sec = config.REENTRY_BLOCK_SEC_AFTER_SELL

        until_ts = now_ts + block_sec
        self.reentry_block_until[symbol] = until_ts
        self.last_exit_reason[symbol] = reason

        self.logger.info(
            f"재진입 제한 설정 | symbol={symbol} reason={reason} "
            f"block_sec={block_sec} until_ts={until_ts}"
        )

    # -------------------------
    # 재진입 가능 여부
    # -------------------------
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
            if not config.DRY_RUN:
                return False, "장외 시간"

        if self.daily_order_count >= self.max_daily_orders:
            return False, "일일 최대 주문 횟수 초과"

        if tick.volume < self.min_tick_volume:
            return False, "틱 거래량 기준 미달"

        if self.order_manager.exists_open_order(signal.symbol):
            return False, "미체결/진행중 주문 존재"

        now_ts = time.time()
        last_ts = self.last_order_time.get(signal.symbol, 0.0)
        if now_ts - last_ts < self.order_cooldown_sec:
            return False, f"주문 쿨타임 {self.order_cooldown_sec}초 이내"

        if signal.side.value == "BUY":
            ok_reenter, reason_reenter = self._can_reenter_buy(signal.symbol)
            if not ok_reenter:
                return False, reason_reenter

        pos = self.portfolio.get_position(signal.symbol)
        if signal.side.value == "BUY":
            if pos.qty >= self.max_symbol_position:
                return False, "종목당 최대 보유 제한"

        ok, reason = self.risk_manager.can_trade(signal, self.portfolio)
        if not ok:
            return False, reason

        return True, "OK"

    # -------------------------
    # 틱 처리
    # -------------------------
    def on_tick(self, tick: TickData):
        self.logger.info(
            f"[CHECK] {tick.symbol} "
            f"price={tick.price} vol={tick.volume} "
            f"chg={getattr(tick, 'price_change_pct', 0.0)} "
            f"strength={getattr(tick, 'trade_strength', 0.0)} "
            f"vr={getattr(tick, 'volume_ratio', 0.0)} "
            f"news={getattr(tick, 'news_score', 0.0)} "
            f"theme={getattr(tick, 'theme_score', 0.0)} "
            f"leader={getattr(tick, 'leader_score', 0.0)}"
        )

        if not self.is_running:
            return

        self.logger.info(
            f"[TRY_ENTRY] {tick.symbol} "
            f"chg={getattr(tick, 'price_change_pct', 0.0)} "
            f"strength={getattr(tick, 'trade_strength', 0.0)} "
            f"vr={getattr(tick, 'volume_ratio', 0.0)} "
            f"news={getattr(tick, 'news_score', 0.0)}"
        )

        signal = self.strategy.generate_signal(tick, self.portfolio)

        if signal is None:
            block_reason = ""
            if hasattr(self.strategy, "get_last_block_reason"):
                block_reason = self.strategy.get_last_block_reason(tick.symbol)

            self.logger.info(
                f"[ENTRY_FAIL] {tick.symbol} "
                f"chg={getattr(tick, 'price_change_pct', 0.0)} "
                f"strength={getattr(tick, 'trade_strength', 0.0)} "
                f"vr={getattr(tick, 'volume_ratio', 0.0)} "
                f"reason={block_reason or '전략 필터 통과 실패'}"
            )
            return

        entry_score = self._extract_score_from_reason(getattr(signal, "reason", ""))

        self.logger.info(
            f"[SIGNAL] {signal.symbol} side={signal.side} qty={signal.qty} "
            f"score={entry_score} reason={signal.reason}"
        )

        ok, reason = self.can_send_order(signal, tick)
        if not ok:
            self.logger.info(
                f"[{signal.symbol}] 주문 차단 | {reason} | "
                f"score={entry_score} chg={getattr(tick, 'price_change_pct', 0.0)} "
                f"strength={getattr(tick, 'trade_strength', 0.0)} "
                f"vr={getattr(tick, 'volume_ratio', 0.0)}"
            )
            return

        try:
            self.logger.info(
                f"[ORDER_READY] {signal.symbol} side={signal.side} qty={signal.qty} "
                f"score={entry_score} reason={signal.reason}"
            )

            order = self.broker.place_order(signal)
            self.order_manager.register(order)

            if order.status == OrderStatus.SUBMITTED:
                self.last_order_time[signal.symbol] = time.time()
                self.daily_order_count += 1

                if signal.side.value == "BUY" and hasattr(self.strategy, "mark_entry"):
                    self.strategy.mark_entry(signal.symbol, tick.ts)

            if config.DRY_RUN and signal.side.value == "BUY":
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
    # -------------------------
    # 체결 반영
    # -------------------------
    def on_fill(self, fill):
        try:
            symbol = fill.symbol

            pos_before = self.portfolio.get_position(symbol)
            qty_before = int(getattr(pos_before, "qty", 0))
            avg_before = float(getattr(pos_before, "avg_price", 0.0))
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
                    f"symbol={fill.symbol} side={fill.side} "
                    f"fill_qty={fill.fill_qty} fill_price={fill.fill_price} "
                    f"cum_filled={order.filled_qty}/{order.qty} status={order.status}"
                )

            self.logger.info(
                f"잔고 상태 | cash={self.portfolio.cash:.0f} realized_pnl={self.portfolio.realized_pnl:.0f}"
            )

            if self.telegram:
                status_text = order.status if order else "UNKNOWN"
                cum_text = f"{order.filled_qty}/{order.qty}" if order else f"{fill.fill_qty}/?"
                self.telegram.send(
                    f"✅ 체결\n"
                    f"종목: {fill.symbol}\n"
                    f"방향: {fill.side}\n"
                    f"주문번호(실제): {fill.order_id}\n"
                    f"주문번호(내부): {resolved_order_id}\n"
                    f"이번체결: {fill.fill_qty}\n"
                    f"체결가: {fill.fill_price}\n"
                    f"누적체결: {cum_text}\n"
                    f"상태: {status_text}"
                )

            side_name = getattr(fill.side, "name", "")

            if side_name == "BUY":
                self._start_trade_cycle_if_needed(
                    symbol=symbol,
                    qty_before=qty_before,
                    qty_after=qty_after,
                    avg_price_after=avg_after,
                )

            elif side_name == "SELL":
                self.sell_in_progress.discard(fill.symbol)
                self.logger.info(
                    f"매도 체결 완료 | symbol={fill.symbol} "
                    f"reentry_reason={self.last_exit_reason.get(fill.symbol, '')}"
                )

                self._accumulate_trade_realized_pnl(
                    symbol=symbol,
                    realized_delta=realized_delta,
                )

                self._close_trade_cycle_if_needed(
                    symbol=symbol,
                    qty_before=qty_before,
                    qty_after=qty_after,
                    fill_price=fill.fill_price,
                    exit_reason=self.last_exit_reason.get(symbol, "SELL_EXIT"),
                )

            try:
                pos = self.portfolio.get_position(fill.symbol)
                if int(getattr(pos, "qty", 0)) == 0:
                    self.partial_exit_done.discard(fill.symbol)
                    self.breakeven_active.discard(fill.symbol)
                    self.trailing_armed.discard(fill.symbol)
                    self.trailing_high_price.pop(fill.symbol, None)
                    self.logger.info(f"청산 상태 초기화 | symbol={fill.symbol}")
            except Exception:
                pass

            try:
                pos = self.portfolio.get_position(fill.symbol)
                if int(getattr(pos, "qty", 0)) == 0:
                    self.pending_resell.pop(fill.symbol, None)
                    self.resell_retry_count.pop(fill.symbol, None)
                    self.last_cancel_request_time.pop(fill.symbol, None)
                    self.abandon_resell_symbols.discard(fill.symbol)
            except Exception:
                pass

            try:
                self.cancel_in_progress.discard(fill.symbol)
            except Exception:
                pass

        except Exception as e:
            self.error_count += 1
            self.logger.exception(f"체결 반영 실패 | {e}")
            self._check_engine_protection()
            if self.telegram:
                self.telegram.send(f"🚨 체결 반영 실패\n{fill.symbol}\n{e}")
               
    # -------------------------
    # 브로커 메시지 처리
    # -------------------------
    def on_broker_msg(self, msg: str):
        try:
            self.logger.info(f"브로커 메시지 | {msg}")
            if self.telegram and config.ENABLE_TELEGRAM_LOG:
                self.telegram.send(f"ℹ️ 브로커 메시지\n{msg}")
        except Exception as e:
            self.logger.warning(f"브로커 메시지 처리 실패 | {e}")

    # -------------------------
    # 엔진 보호모드 체크
    # -------------------------
    def _check_engine_protection(self):
        try:
            max_consecutive_loss = getattr(config, "MAX_CONSECUTIVE_LOSS", 3)
            max_error_count = getattr(config, "MAX_ERROR_COUNT", 5)
            max_daily_loss = getattr(config, "MAX_DAILY_LOSS", -150000)

            if self.consecutive_loss_count >= max_consecutive_loss:
                self.engine_protected = True
                self.logger.error(
                    f"엔진 보호모드 진입 | 연속손실 {self.consecutive_loss_count}회"
                )

            if self.error_count >= max_error_count:
                self.engine_protected = True
                self.logger.error(
                    f"엔진 보호모드 진입 | 오류누적 {self.error_count}회"
                )

            if self.portfolio.realized_pnl <= max_daily_loss:
                self.engine_protected = True
                self.logger.error(
                    f"엔진 보호모드 진입 | 일손실 {self.portfolio.realized_pnl:.0f}"
                )

            if self.engine_protected and self.telegram:
                self.telegram.send(
                    f"🛑 엔진 보호모드 진입\n"
                    f"연속손실: {self.consecutive_loss_count}\n"
                    f"오류수: {self.error_count}\n"
                    f"실현손익: {self.portfolio.realized_pnl:.0f}"
                )
        except Exception as e:
            self.logger.warning(f"엔진 보호모드 체크 실패 | {e}")

    def health_check(self):
        """
        엔진 기본 상태 점검용.
        main_live.py 에서 호출해도 죽지 않도록 최소 점검만 수행한다.
        """
        if hasattr(self, "logger") and self.logger:
            try:
                position_count = len(getattr(self.portfolio, "positions", {})) if hasattr(self, "portfolio") else 0
                pending_count = len(getattr(self, "pending_orders", {})) if hasattr(self, "pending_orders") else 0

                self.logger.info(
                    f"health_check 완료 | positions={position_count} pending_orders={pending_count}"
                )
            except Exception as e:
                self.logger.warning(f"health_check 점검 중 예외 | {e}") 
                