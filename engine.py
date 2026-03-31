import time
from datetime import datetime

import config
from core.models import TickData, OrderStatus, Signal, Side, OrderType
from core.order_manager import OrderManager
from core.portfolio import Portfolio
from core.risk_manager import RiskManager


class TradingEngine:
    def __init__(self, broker, strategy, logger, telegram=None, initial_cash=5_000_000):
        self.broker = broker
        self.strategy = strategy
        self.logger = logger
        self.telegram = telegram

        self.portfolio = Portfolio(initial_cash=initial_cash)
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager()

        self.is_running = False

        # -------------------------
        # 주문 방어 설정
        # -------------------------
        self.last_order_time = {}          # 종목별 마지막 주문 시각
        self.order_cooldown_sec = 10       # 같은 종목 재주문 최소 간격
        self.daily_order_count = 0         # 일일 주문 횟수
        self.max_daily_orders = 20         # 일일 최대 주문 수
        self.current_trading_date = datetime.now().date()

        # 선택 방어
        self.min_tick_volume = 1           # 너무 빈약한 틱 무시용
        self.max_symbol_position = 1       # 종목당 1포지션만 허용

        self.broker.set_real_tick_callback(self.on_real_tick)
        self.broker.set_fill_callback(self.on_fill)
        self.broker.set_msg_callback(self.on_broker_msg)
        self.sell_in_progress = set()      # 중복 매도 방지용
        self.last_price_map = {}           # 종목별 최근가 저장
        self.reentry_block_until = {}      # 종목별 재진입 금지 만료시각(timestamp)
        self.last_exit_reason = {}         # 종목별 마지막 청산 사유
        self.partial_exit_done = set()     # 1차 익절 완료 종목
        self.breakeven_active = set()      # 본절 적용 종목
        self.trailing_high_price = {}      # 종목별 트레일링 기준 최고가
        self.cancel_in_progress = set()    # 종목별 취소 중복 방지
        self.pending_resell = {}           # symbol -> {"qty": int, "reason": str, "requested_at": ts}
        self.resell_retry_count = {}       # symbol -> 재시도 횟수
        self.last_cancel_request_time = {} # symbol -> 마지막 취소 요청 시각
        self.consecutive_loss_count = 0
        self.error_count = 0
        self.engine_protected = False

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
            try:
                self.broker.shutdown()
            except Exception as e:
                self.logger.warning(f"브로커 종료 실패 | {e}")
            return

        self.logger.info("엔진 종료 시작")

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
            positions = self.broker.get_positions(password=password)

            if deposit.get("available_cash", 0) > 0:
                self.portfolio.cash = float(deposit["available_cash"])

            for row in positions.get("positions", []):
                pos = self.portfolio.get_position(row["symbol"])
                pos.qty = row["qty"]
                pos.avg_price = row["avg_price"]
                self.portfolio.positions[row["symbol"]] = pos

            self.logger.info(
                f"계좌 동기화 완료 | cash={self.portfolio.cash:.0f} "
                f"positions={len([p for p in self.portfolio.positions.values() if p.qty > 0])}"
            )
        except Exception as e:
            self.logger.exception(f"계좌 동기화 실패 | {e}")

    # -------------------------
    # 실시간 틱 수신
    # -------------------------
    def on_real_tick(self, raw_tick: dict):

        self.logger.info(f"[TICK] {symbol} price={price} vol={volume}")

        if self.engine_protected:
            return
        
        try:
            symbol = raw_tick["symbol"]
            price = int(raw_tick["price"])
            volume = int(raw_tick.get("trade_volume", 0))

            if price <= 0:
                return

            # 최근가 저장
            self.last_price_map[symbol] = price

            # 1) 자동 매도 먼저 검사
            self._check_auto_exit(symbol, price)

            # 1-1) 오래된 매도 미체결 주문 정리
            self._check_stale_sell_order(symbol)

            # 1-2) 취소 후 재매도 재시도
            self._retry_sell_after_cancel(symbol)

            # 2) 기존 전략 엔진으로 틱 전달
            tick = TickData(
                symbol=symbol,
                price=price,
                volume=volume,
                ts=datetime.now()
            )
            self.on_tick(tick)

        except Exception as e:
            self.error_count += 1
            self.logger.exception(f"실시간 틱 처리 실패 | tick={raw_tick} err={e}")
            self._check_engine_protection()

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

            # 이미 매도 진행 중이면 중복 방지
            if symbol in self.sell_in_progress:
                return

            # 미체결/진행중 주문 있으면 중복 방지
            if self.order_manager.exists_open_order(symbol):
                return

            pnl_pct = (price - avg_price) / avg_price

            # -------------------------
            # 1차 부분 익절
            # -------------------------
            if (
                symbol not in self.partial_exit_done
                and pnl_pct >= config.PARTIAL_TAKE_PROFIT_PCT
            ):
                sell_qty = max(int(qty * config.PARTIAL_TAKE_RATIO), 1)

                self.logger.info(
                    f"부분익절 발생 | symbol={symbol} qty={sell_qty} pnl={pnl_pct:.2%}"
                )

                self.partial_exit_done.add(symbol)

                if config.BREAKEVEN_ENABLED:
                    self.breakeven_active.add(symbol)

                # 부분익절 이후 남은 물량의 트레일링 최고가 시작
                if config.TRAILING_STOP_ENABLED:
                    self.trailing_high_price[symbol] = price

                self._submit_auto_sell(symbol, sell_qty, "부분익절")
                return

            # -------------------------
            # 부분익절 이후 최고가 갱신
            # -------------------------
            if symbol in self.partial_exit_done and config.TRAILING_STOP_ENABLED:
                prev_high = self.trailing_high_price.get(symbol, 0)
                if price > prev_high:
                    self.trailing_high_price[symbol] = price

            # -------------------------
            # 본절 손절
            # -------------------------
            if symbol in self.breakeven_active:
                if price <= avg_price:
                    self.logger.info(
                        f"본절 청산 | symbol={symbol} price={price} avg_price={avg_price}"
                    )
                    self._submit_auto_sell(symbol, qty, "본절청산")
                    return

            # -------------------------
            # 트레일링 스탑
            # -------------------------
            if symbol in self.partial_exit_done and config.TRAILING_STOP_ENABLED:
                high_price = self.trailing_high_price.get(symbol, 0)
                if high_price > 0:
                    trailing_stop_price = high_price * (1 - config.TRAILING_STOP_PCT)

                    if price <= trailing_stop_price:
                        self.logger.info(
                            f"트레일링 스탑 청산 | symbol={symbol} price={price} "
                            f"high={high_price} stop={trailing_stop_price:.2f}"
                        )
                        self._submit_auto_sell(symbol, qty, f"트레일링청산 high={high_price}")
                        return

            # -------------------------
            # 최종 익절 / 손절
            # -------------------------
            exit_reason = None

            if pnl_pct >= config.TAKE_PROFIT_PCT:
                exit_reason = f"익절 {pnl_pct:.2%}"
            elif pnl_pct <= config.STOP_LOSS_PCT:
                exit_reason = f"손절 {pnl_pct:.2%}"

            if exit_reason is not None:
                self.logger.info(
                    f"자동매도 조건 충족 | symbol={symbol} price={price} "
                    f"avg_price={avg_price} qty={qty} pnl_pct={pnl_pct:.2%} reason={exit_reason}"
                )
                self._submit_auto_sell(symbol=symbol, qty=qty, reason=exit_reason)

        except Exception as e:
            self.logger.exception(f"자동매도 검사 실패 | symbol={symbol} price={price} err={e}")

    # -------------------------
    # 자동 매도 주문
    # -------------------------
    def _submit_auto_sell(self, symbol: str, qty: int, reason: str):
        try:
            if qty <= 0:
                return

            # 중복 매도 방지 플래그
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

            if order.status == OrderStatus.SUBMITTED:
                self.last_order_time[symbol] = time.time()
                self.daily_order_count += 1

                # 손절/비손절 카운트 관리
                if "손절" in reason:
                    self.consecutive_loss_count += 1
                else:
                    self.consecutive_loss_count = 0

                # 보호모드 체크
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

            # 실제 주문번호가 아직 매핑 안 됐으면 취소 불가
            broker_order_id = None
            for real_id, local_id in self.order_manager.broker_to_local_id.items():
                if local_id == order.order_id:
                    broker_order_id = real_id
                    break

            if not broker_order_id:
                return

            elapsed = time.time() - float(order.ts)
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
                qty=remain_qty
            )

            if ret == 0:
                self.last_cancel_request_time[symbol] = time.time()

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

            # 아직 취소 직후 너무 이르면 대기
            requested_at = float(pending.get("requested_at", 0))
            if time.time() - requested_at < config.RETRY_SELL_DELAY_SEC:
                return

            qty = int(pending.get("qty", 0))
            reason = str(pending.get("reason", "취소후재매도"))

            if qty <= 0:
                self.pending_resell.pop(symbol, None)
                self.cancel_in_progress.discard(symbol)
                return

            # 보유 수량 다시 확인
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
                return

            # 아직 진행중인 주문 있으면 대기
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

        # 매수 재진입 제한
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
        self.logger.info(f"[CHECK] {tick.symbol} price={tick.price}")

        if not self.is_running:
            return

        if signal:
            self.logger.info(f"[SIGNAL] {signal.symbol} side={signal.side} qty={signal.qty}")
            
        signal = self.strategy.generate_signal(tick, self.portfolio)
        if signal is None:
            return

        ok, reason = self.can_send_order(signal, tick)
        if not ok:
            self.logger.info(f"[{signal.symbol}] 주문 차단 | {reason}")
            return

        try:
            order = self.broker.place_order(signal)
            self.order_manager.register(order)

            # ret=0 성공 기준으로 SUBMITTED 들어온 경우만 카운트
            if order.status == OrderStatus.SUBMITTED:
                self.last_order_time[signal.symbol] = time.time()
                self.daily_order_count += 1

                if signal.side.value == "BUY" and hasattr(self.strategy, "mark_entry"):
                    self.strategy.mark_entry(signal.symbol, tick.ts)

            self.logger.info(
                f"주문 등록 | id={order.order_id} symbol={order.symbol} "
                f"side={order.side} qty={order.qty} count={self.daily_order_count}/{self.max_daily_orders}"
            )

            if self.telegram:
                self.telegram.send(
                    f"📈 주문 발생\n"
                    f"종목: {order.symbol}\n"
                    f"방향: {order.side}\n"
                    f"수량: {order.qty}\n"
                    f"상태: {order.status}\n"
                    f"일일주문: {self.daily_order_count}/{self.max_daily_orders}"
                )

            if order.status == OrderStatus.REJECTED:
                self.logger.warning(f"주문 거부 | {order.symbol}")
                if self.telegram:
                    self.telegram.send(
                        f"❌ 주문 거부\n"
                        f"종목: {order.symbol}\n"
                        f"방향: {order.side}\n"
                        f"수량: {order.qty}"
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
            # 1) 실제 주문번호와 내부 주문번호 연결
            local_order_id = self.order_manager.bind_broker_order_id(
                symbol=fill.symbol,
                broker_order_id=fill.order_id
            )
            resolved_order_id = local_order_id or self.order_manager.resolve_order_id(fill.order_id)

            # 2) 포트폴리오에는 "이번 체결분"만 반영
            self.portfolio.update_fill(fill)

            # 3) 주문 누적 체결 반영
            order = self.order_manager.apply_fill(
                order_id=resolved_order_id,
                fill_qty=fill.fill_qty,
                fill_price=fill.fill_price,
                unfilled_qty=getattr(fill, "unfilled_qty", None)
            )

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

            # 매도 체결 시 중복 매도 방지 플래그 해제
            try:
                if getattr(fill.side, "name", "") == "SELL":
                    self.sell_in_progress.discard(fill.symbol)
                    self.logger.info(
                        f"매도 체결 완료 | symbol={fill.symbol} "
                        f"reentry_reason={self.last_exit_reason.get(fill.symbol, '')}"
                    )
            except Exception:
                pass

            # 포지션 완전 청산 시 상태 초기화
            try:
                pos = self.portfolio.get_position(fill.symbol)
                if int(getattr(pos, "qty", 0)) == 0:
                    self.partial_exit_done.discard(fill.symbol)
                    self.breakeven_active.discard(fill.symbol)
                    self.trailing_high_price.pop(fill.symbol, None)
                    self.logger.info(f"청산 상태 초기화 | symbol={fill.symbol}")
            except Exception:
                pass

            # 완전 청산 시 재매도 관련 상태도 초기화
            try:
                pos = self.portfolio.get_position(fill.symbol)
                if int(getattr(pos, "qty", 0)) == 0:
                    self.pending_resell.pop(fill.symbol, None)
                    self.resell_retry_count.pop(fill.symbol, None)
                    self.last_cancel_request_time.pop(fill.symbol, None)
            except Exception:
                pass

            # 완전 체결 또는 포지션 정리 시 취소 플래그 해제
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
    # 엔진 보호모드 체크
    # -------------------------
    def _check_engine_protection(self):
        try:
            # 1. 연속 손절
            if self.consecutive_loss_count >= config.MAX_CONSECUTIVE_LOSS:
                self._trigger_protection(f"연속 손절 {self.consecutive_loss_count}회")

            # 2. 일일 손실
            if self.portfolio.realized_pnl <= config.MAX_DAILY_LOSS:
                self._trigger_protection(f"일일 손실 초과 {self.portfolio.realized_pnl}")

            # 3. 오류 누적
            if self.error_count >= config.MAX_ERROR_COUNT:
                self._trigger_protection(f"오류 누적 {self.error_count}회")

        except Exception as e:
            self.logger.exception(f"보호모드 체크 실패 | {e}")

    def _trigger_protection(self, reason: str):
        if self.engine_protected:
            return

        self.engine_protected = True

        self.logger.error(f"🚨 엔진 보호모드 발동 | reason={reason}")

        if self.telegram:
            self.telegram.send(
                f"🚨 자동매매 중지\n"
                f"사유: {reason}\n"
                f"PnL: {self.portfolio.realized_pnl:.0f}"
            )

        # 엔진 중지
        self.stop()

    # -------------------------
    # 초기 포지션 동기화
    # -------------------------
    def sync_portfolio(self):
        try:
            balance = self.broker.get_balance()

            self.logger.info("초기 잔고 동기화 시작")

            for symbol, data in balance.items():
                qty = int(data["qty"])
                avg_price = float(data["avg_price"])

                if qty <= 0:
                    continue

                self.portfolio.positions[symbol].qty = qty
                self.portfolio.positions[symbol].avg_price = avg_price

                self.logger.info(
                    f"보유 종목 | symbol={symbol} qty={qty} avg_price={avg_price}"
                )

            self.logger.info("초기 잔고 동기화 완료")

        except Exception as e:
            self.logger.exception(f"포트폴리오 동기화 실패 | {e}")

    def health_check(self):
        try:
            total_qty = sum(p.qty for p in self.portfolio.positions.values())

            self.logger.info(f"헬스체크 | 총 보유수량={total_qty}")

            if total_qty > 50:
                self.logger.warning("보유 수량 과다 - 확인 필요")

        except Exception as e:
            self.logger.exception(f"헬스체크 실패 | {e}")
            
    # -------------------------
    # 서버 메시지
    # -------------------------
    def on_broker_msg(self, text: str):
        self.logger.info(text)

        # 취소/정정/거부 관련 메시지 들어오면 취소 플래그 해제
        cancel_keywords = ["취소", "정정", "거부", "실패", "오류"]
        if any(k in text for k in cancel_keywords):
            try:
                for symbol in list(self.cancel_in_progress):
                    self.cancel_in_progress.discard(symbol)
            except Exception:
                pass

        # 매도 취소/정정 관련 메시지 이후 재매도는 on_real_tick에서 처리
        error_keywords = ["실패", "오류", "거부", "에러", "제한"]
        if self.telegram and any(k in text for k in error_keywords):
            self.telegram.send(f"⚠️ 서버 메시지\n{text}")

