from collections import defaultdict, deque
from PyQt5.QtCore import QObject, QEventLoop
from PyQt5.QAxContainer import QAxWidget
import time

from core.models import Order, OrderStatus, Signal, Side, OrderType, Fill


class KiwoomBroker(QObject):
    def __init__(self, logger, account_no=None):
        super().__init__()

        self.logger = logger
        self.account_no = account_no

        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")

        self.login_loop = None
        self.tr_loop = None

        self.connected = False
        self.is_shutting_down = False

        self.real_screen_no = "5000"
        self.order_screen_no = "6000"
        self.deposit_screen_no = "7000"
        self.balance_screen_no = "7100"
        self.pending_screen_no = "7200"

        self.on_real_tick_callback = None
        self.on_fill_callback = None
        self.on_msg_callback = None

        self._deposit_result = 0
        self._positions_result = []
        self._positions_password = ""

        self._pending_orders_result = []
        self._pending_orders_password = ""

        # -------------------------
        # TR 요청 속도 제한
        # -------------------------
        self.tr_interval_sec = 0.7
        self.tr_retry_wait_sec = 1.2
        self.max_tr_retry = 3
        self.last_tr_request_ts = 0.0

        # -------------------------
        # 주문 요청 속도 제한
        # -------------------------
        self.order_interval_sec = 0.5
        self.order_retry_wait_sec = 1.0
        self.max_order_retry = 3
        self.last_order_request_ts = 0.0

        # -------------------------
        # 실시간 보조 캐시
        # -------------------------
        self.last_tick_volume_map = {}
        self.last_total_volume_map = {}

        # volume_ratio 정교화용
        self.tick_volume_history = defaultdict(lambda: deque(maxlen=120))
        self.real_tick_time_history = defaultdict(lambda: deque(maxlen=120))
        self.symbol_first_seen_at = {}
        self.symbol_last_seen_at = {}

        self._set_signal_slots()

    # -------------------------
    # 이벤트 연결
    # -------------------------
    def _set_signal_slots(self):
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.OnReceiveRealData.connect(self._on_receive_real_data)
        self.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        self.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)

    # -------------------------
    # TR 속도 제한 대기
    # -------------------------
    def _wait_tr_slot(self, rqname: str, trcode: str):
        now = time.time()
        elapsed = now - self.last_tr_request_ts

        if elapsed < self.tr_interval_sec:
            wait_sec = self.tr_interval_sec - elapsed
            self.logger.info(f"TR 대기 | rq={rqname} tr={trcode} wait={wait_sec:.2f}s")
            time.sleep(wait_sec)

        self.last_tr_request_ts = time.time()

    # -------------------------
    # 주문 속도 제한 대기
    # -------------------------
    def _wait_order_slot(self, tag: str = "SendOrder"):
        now = time.time()
        elapsed = now - self.last_order_request_ts

        if elapsed < self.order_interval_sec:
            wait_sec = self.order_interval_sec - elapsed
            self.logger.info(f"주문 대기 | tag={tag} wait={wait_sec:.2f}s")
            time.sleep(wait_sec)

        self.last_order_request_ts = time.time()

    # -------------------------
    # CommRqData 공통 래퍼
    # -------------------------
    def _comm_rq_data_with_retry(
        self,
        rqname: str,
        trcode: str,
        prev_next: int,
        screen_no: str,
    ) -> int:
        last_ret = None

        for attempt in range(1, self.max_tr_retry + 1):
            self._wait_tr_slot(rqname, trcode)

            ret = self.ocx.dynamicCall(
                "CommRqData(QString, QString, int, QString)",
                rqname,
                trcode,
                int(prev_next),
                screen_no,
            )

            self.logger.info(
                f"CommRqData 호출 | rq={rqname} tr={trcode} prev_next={prev_next} "
                f"screen={screen_no} ret={ret} attempt={attempt}/{self.max_tr_retry}"
            )

            if ret == 0:
                return 0

            last_ret = ret

            if ret == -202:
                wait_sec = self.tr_retry_wait_sec * attempt
                self.logger.warning(
                    f"조회 제한 발생(-202) | rq={rqname} tr={trcode} "
                    f"attempt={attempt} wait={wait_sec:.1f}s 후 재시도"
                )
                time.sleep(wait_sec)
                continue

            raise RuntimeError(
                f"CommRqData 실패 | rqname={rqname} trcode={trcode} ret={ret}"
            )

        raise RuntimeError(
            f"CommRqData 재시도 실패 | rqname={rqname} trcode={trcode} ret={last_ret}"
        )

    # -------------------------
    # SendOrder 공통 래퍼
    # -------------------------
    def _send_order_with_retry(
        self,
        rqname: str,
        screen_no: str,
        account_no: str,
        order_type: int,
        code: str,
        qty: int,
        price: int,
        hoga_gb: str,
        org_order_no: str = "",
    ) -> int:
        last_ret = None

        for attempt in range(1, self.max_order_retry + 1):
            self._wait_order_slot(tag=f"{rqname}:{code}")

            ret = self.ocx.dynamicCall(
                "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                [
                    rqname,
                    screen_no,
                    account_no,
                    int(order_type),
                    code,
                    int(qty),
                    int(price),
                    hoga_gb,
                    org_order_no,
                ]
            )

            self.logger.info(
                f"SendOrder 호출 | rq={rqname} code={code} type={order_type} "
                f"qty={qty} price={price} hoga={hoga_gb} org={org_order_no} "
                f"ret={ret} attempt={attempt}/{self.max_order_retry}"
            )

            if ret == 0:
                return 0

            last_ret = ret

            if ret in (-308, -202):
                wait_sec = self.order_retry_wait_sec * attempt
                self.logger.warning(
                    f"주문 재시도 대상 오류 | rq={rqname} code={code} ret={ret} "
                    f"attempt={attempt} wait={wait_sec:.1f}s"
                )
                time.sleep(wait_sec)
                continue

            raise RuntimeError(
                f"SendOrder 실패 | rqname={rqname} code={code} order_type={order_type} ret={ret}"
            )

        raise RuntimeError(
            f"SendOrder 재시도 실패 | rqname={rqname} code={code} order_type={order_type} ret={last_ret}"
        )

    # -------------------------
    # 로그인
    # -------------------------
    def connect(self):
        self.logger.info("키움 로그인 시도")

        self.login_loop = QEventLoop()

        ret = self.ocx.dynamicCall("CommConnect()")
        self.logger.info(f"CommConnect 호출 완료 | ret={ret}")

        self.logger.info("로그인 이벤트 대기 시작")
        self.login_loop.exec_()
        self.logger.info("로그인 이벤트 대기 종료")

        if self.is_shutting_down:
            self.logger.info("종료 중 → connect 종료")
            return

        if not self.connected:
            raise RuntimeError("로그인 실패")

        accounts = self.ocx.dynamicCall("GetLoginInfo(QString)", "ACCNO")
        account_list = [x for x in str(accounts).split(";") if x.strip()]

        if self.account_no is None:
            if not account_list:
                raise RuntimeError("로그인 계좌정보 조회 실패")
            self.account_no = account_list[0]

        self.logger.info(f"키움 연결 완료 | 계좌={self.account_no}")

    def show_account_window(self):
        self.logger.info("계좌비밀번호 입력창 호출")
        self.ocx.dynamicCall('KOA_Functions(QString, QString)', "ShowAccountWindow", "")

    def _on_event_connect(self, err_code):
        self.logger.info(f"OnEventConnect 호출 | err_code={err_code}")

        if self.is_shutting_down:
            if self.login_loop:
                self.login_loop.exit()
                self.login_loop = None
            return

        if err_code == 0:
            self.connected = True
            self.logger.info("로그인 성공")
        else:
            self.connected = False
            self.logger.error("로그인 실패")

        if self.login_loop:
            self.login_loop.exit()
            self.login_loop = None

    # -------------------------
    # TR 데이터 수신
    # -------------------------
    def _on_receive_tr_data(
        self,
        sScrNo,
        sRQName,
        sTrCode,
        sRecordName,
        sPrevNext,
        nDataLength,
        sErrorCode,
        sMessage,
        sSplmMsg,
    ):
        self.logger.info(
            f"OnReceiveTrData | rq={sRQName} tr={sTrCode} prev_next={sPrevNext}"
        )

        try:
            if sRQName == "deposit_req":
                self._handle_deposit(sTrCode, sRQName)
                return

            if sRQName == "opw00018_req":
                self._handle_opw00018(sTrCode, sRQName, sPrevNext)
                return

            if sRQName == "opt10075_req":
                self._handle_opt10075(sTrCode, sRQName, sPrevNext)
                return

        except Exception as e:
            self.logger.exception(f"TR 처리 오류 | rq={sRQName} tr={sTrCode} err={e}")
            if self.tr_loop and self.tr_loop.isRunning():
                self.tr_loop.quit()

    def _handle_deposit(self, sTrCode: str, sRQName: str):
        raw_deposit = self.ocx.dynamicCall(
            "GetCommData(QString, QString, int, QString)",
            sTrCode, sRQName, 0, "예수금"
        )
        deposit = self._to_int(raw_deposit)
        self._deposit_result = deposit

        self.logger.info(f"예수금 조회 완료 | deposit={deposit}")

        if self.tr_loop and self.tr_loop.isRunning():
            self.tr_loop.quit()

    def _handle_opw00018(self, sTrCode: str, sRQName: str, sPrevNext: str):
        count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", sTrCode, sRQName)
        self.logger.info(f"opw00018 수신 | rows={count} | sPrevNext={sPrevNext}")

        for i in range(count):
            code = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "종목번호"
            ).strip()
            name = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "종목명"
            ).strip()
            qty = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "보유수량"
            ).strip()
            available_qty = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "매매가능수량"
            ).strip()
            avg_price = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "매입가"
            ).strip()
            current_price = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "현재가"
            ).strip()
            eval_pnl = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "평가손익"
            ).strip()
            return_pct = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "수익률(%)"
            ).strip()

            item = {
                "symbol": self._clean_code(code),
                "name": name,
                "qty": self._to_int(qty),
                "available_qty": self._to_int(available_qty),
                "avg_price": float(abs(self._to_int(avg_price))),
                "current_price": float(abs(self._to_int(current_price))),
                "eval_pnl": self._to_int(eval_pnl),
                "return_pct": self._to_float(return_pct),
            }

            if item["symbol"] and item["qty"] > 0:
                self._positions_result.append(item)

        if str(sPrevNext).strip() == "2":
            self._request_positions(prev_next="2", password=self._positions_password)
            return

        self.logger.info(f"보유종목 조회 완료 | count={len(self._positions_result)}")

        if self.tr_loop and self.tr_loop.isRunning():
            self.tr_loop.quit()

    def _handle_opt10075(self, sTrCode: str, sRQName: str, sPrevNext: str):
        count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", sTrCode, sRQName)
        self.logger.info(f"opt10075 수신 | rows={count} | sPrevNext={sPrevNext}")

        for i in range(count):
            order_no = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "주문번호"
            ).strip()

            code = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "종목코드"
            ).strip()

            name = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "종목명"
            ).strip()

            order_gubun = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "주문구분"
            ).strip()

            order_price = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "주문가격"
            ).strip()

            order_qty = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "주문수량"
            ).strip()

            unfilled_qty = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "미체결수량"
            ).strip()

            filled_qty = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "체결량"
            ).strip()

            order_status = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "주문상태"
            ).strip()

            item = {
                "order_no": order_no,
                "symbol": self._clean_code(code),
                "name": name,
                "side": self._parse_order_side(order_gubun),
                "order_gubun": order_gubun,
                "order_price": abs(self._to_int(order_price)),
                "order_qty": self._to_int(order_qty),
                "unfilled_qty": self._to_int(unfilled_qty),
                "filled_qty": self._to_int(filled_qty),
                "order_status": order_status,
            }

            if item["order_no"] and item["symbol"] and item["unfilled_qty"] > 0:
                self._pending_orders_result.append(item)

        if str(sPrevNext).strip() == "2":
            self._request_pending_orders(prev_next="2", password=self._pending_orders_password)
            return

        self.logger.info(f"미체결 주문 조회 완료 | count={len(self._pending_orders_result)}")

        if self.tr_loop and self.tr_loop.isRunning():
            self.tr_loop.quit()

    # -------------------------
    # 계좌 조회
    # -------------------------
    def get_deposit(self, password: str = "") -> int:
        self.logger.info("get_deposit 호출")

        if not self.account_no:
            raise RuntimeError("계좌번호(account_no)가 설정되지 않았습니다.")

        self._deposit_result = 0
        self.tr_loop = QEventLoop()

        self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self.account_no)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", password)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "2")

        self._comm_rq_data_with_retry(
            rqname="deposit_req",
            trcode="opw00001",
            prev_next=0,
            screen_no=self.deposit_screen_no,
        )

        self.tr_loop.exec_()
        return self._deposit_result

    def get_positions(self, password: str = "") -> list[dict]:
        self.logger.info("get_positions 호출")

        if not self.account_no:
            raise RuntimeError("계좌번호(account_no)가 설정되지 않았습니다.")

        self._positions_result = []
        self._positions_password = password
        self.tr_loop = QEventLoop()

        self._request_positions(prev_next="0", password=password)
        self.tr_loop.exec_()

        self.logger.info(f"get_positions 완료 | count={len(self._positions_result)}")
        return self._positions_result

    def _request_positions(self, prev_next: str = "0", password: str = ""):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self.account_no)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", password)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "1")

        self.logger.info(f"계좌평가잔고내역요청 호출 | prev_next={prev_next}")
        self._comm_rq_data_with_retry(
            rqname="opw00018_req",
            trcode="opw00018",
            prev_next=int(prev_next),
            screen_no=self.balance_screen_no,
        )

    def get_pending_orders(self, password: str = "") -> list[dict]:
        self.logger.info("get_pending_orders 호출")

        if not self.account_no:
            raise RuntimeError("계좌번호(account_no)가 설정되지 않았습니다.")

        self._pending_orders_result = []
        self._pending_orders_password = password
        self.tr_loop = QEventLoop()

        self._request_pending_orders(prev_next="0", password=password)
        self.tr_loop.exec_()

        self.logger.info(f"get_pending_orders 완료 | count={len(self._pending_orders_result)}")
        return self._pending_orders_result

    def _request_pending_orders(self, prev_next: str = "0", password: str = ""):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self.account_no)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "전체종목구분", "0")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "매매구분", "0")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", "")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "체결구분", "1")

        self.logger.info(f"미체결주문요청 호출 | prev_next={prev_next}")
        self._comm_rq_data_with_retry(
            rqname="opt10075_req",
            trcode="opt10075",
            prev_next=int(prev_next),
            screen_no=self.pending_screen_no,
        )

    def _parse_order_side(self, order_gubun: str):
        text = str(order_gubun).strip().replace("+", "").replace("-", "")
        if "매도" in text:
            return Side.SELL
        return Side.BUY

    def get_balance(self):
        result = {}
        positions = self.get_positions(password="")

        for item in positions:
            result[item["symbol"]] = {
                "qty": item["qty"],
                "avg_price": item["avg_price"],
            }

        return result

    # -------------------------
    # 실시간
    # -------------------------
    def register_real(self, codes):
        code_str = ";".join(codes)

        # 10: 현재가
        # 12: 등락율
        # 13: 누적거래량
        # 15: 거래량(체결량 계열)
        # 16: 시가
        # 17: 고가
        # 18: 저가
        # 228: 체결강도
        fid_list = "10;12;13;15;16;17;18;228"

        ret = self.ocx.dynamicCall(
            "SetRealReg(QString, QString, QString, QString)",
            self.real_screen_no,
            code_str,
            fid_list,
            "0"
        )

        self.logger.info(f"실시간 등록 | codes={code_str} fids={fid_list} ret={ret}")

    def remove_real(self, code="ALL"):
        self.ocx.dynamicCall(
            "SetRealRemove(QString, QString)",
            self.real_screen_no,
            code
        )

    def _avg(self, values):
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _estimate_volume_ratio(self, symbol: str, total_volume: int, tick_volume: int) -> float:
        """
        정교화 버전:
        - 최근 5틱 평균 / 직전 30틱 평균
        - 데이터가 부족하면 최근 3틱 / 전체 평균 fallback
        - 너무 초반에는 직전 tick 기반 fallback
        """
        if total_volume <= 0 and tick_volume <= 0:
            return 0.0

        hist = self.tick_volume_history[symbol]
        non_zero_hist = [v for v in hist if v > 0]

        if len(non_zero_hist) < 2:
            last_tick_volume = self.last_tick_volume_map.get(symbol, 0)
            base = max(last_tick_volume, 1)
            ratio = tick_volume / base if tick_volume > 0 else 0.0
            return round(min(max(ratio, 0.0), 10.0), 2)

        recent_window = [v for v in list(hist)[-5:] if v > 0]
        baseline_source = list(hist)[-35:-5]
        baseline_window = [v for v in baseline_source if v > 0]

        if len(recent_window) >= 3 and len(baseline_window) >= 10:
            recent_avg = self._avg(recent_window)
            baseline_avg = max(self._avg(baseline_window), 1.0)
            ratio = recent_avg / baseline_avg
            return round(min(max(ratio, 0.0), 10.0), 2)

        recent_small = [v for v in list(hist)[-3:] if v > 0]
        full_avg = max(self._avg(non_zero_hist), 1.0)

        if recent_small:
            ratio = self._avg(recent_small) / full_avg
            return round(min(max(ratio, 0.0), 10.0), 2)

        return 0.0

    def _on_receive_real_data(self, code, real_type, real_data):
        if self.on_real_tick_callback is None:
            return

        try:
            raw_price = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 10)
            raw_change_rate = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 12)
            raw_total_volume = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 13)
            raw_tick_volume = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 15)
            raw_open = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 16)
            raw_high = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 17)
            raw_low = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 18)
            raw_trade_strength = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 228)

            price = abs(self._to_int(raw_price))
            price_change_pct = self._to_float(raw_change_rate)
            total_volume = abs(self._to_int(raw_total_volume))
            tick_volume = abs(self._to_int(raw_tick_volume))
            trade_strength = self._to_float(raw_trade_strength)

            open_price = abs(self._to_int(raw_open))
            high_price = abs(self._to_int(raw_high))
            low_price = abs(self._to_int(raw_low))

            if price <= 0:
                return

            now_ts = time.time()

            if code not in self.symbol_first_seen_at:
                self.symbol_first_seen_at[code] = now_ts
            self.symbol_last_seen_at[code] = now_ts

            self.tick_volume_history[code].append(tick_volume)
            self.real_tick_time_history[code].append(now_ts)

            volume_ratio = self._estimate_volume_ratio(
                symbol=code,
                total_volume=total_volume,
                tick_volume=tick_volume,
            )

            tick = {
                "symbol": code,
                "price": price,
                "trade_volume": tick_volume,
                "total_volume": total_volume,
                "price_change_pct": price_change_pct,
                "trade_strength": trade_strength,
                "volume_ratio": volume_ratio,
                "open": open_price,
                "high": high_price,
                "low": low_price,
            }

            self.last_tick_volume_map[code] = tick_volume
            self.last_total_volume_map[code] = total_volume

            self.on_real_tick_callback(tick)

        except Exception as e:
            self.logger.exception(
                f"실시간 데이터 처리 오류 | code={code} real_type={real_type} err={e}"
            )

    # -------------------------
    # 주문 (실제 주문 / 드라이런)
    # -------------------------
    def place_order(self, signal: Signal) -> Order:
        import config

        order_type_map = {
            Side.BUY: 1,
            Side.SELL: 2,
        }

        hoga_gb = "03" if signal.order_type == OrderType.MARKET else "00"
        price = 0 if signal.order_type == OrderType.MARKET else int(signal.price or 0)

        local_id = f"ORD_{int(time.time() * 1000)}"

        if config.DRY_RUN or not config.LIVE_MODE:
            self.logger.warning(
                f"[DRY_RUN] 주문 모의 처리 | symbol={signal.symbol} side={signal.side} "
                f"qty={signal.qty} price={price} order_type={signal.order_type} reason={signal.reason}"
            )

            if signal.side == Side.BUY:
                return Order(
                    order_id=local_id,
                    symbol=signal.symbol,
                    side=signal.side,
                    qty=signal.qty,
                    price=price,
                    order_type=signal.order_type,
                    status=OrderStatus.SUBMITTED,
                    reason=signal.reason,
                )

            return Order(
                order_id=local_id,
                symbol=signal.symbol,
                side=signal.side,
                qty=signal.qty,
                price=price,
                order_type=signal.order_type,
                status=OrderStatus.SUBMITTED,
                reason="DRY_RUN_미체결",
            )

        try:
            ret = self._send_order_with_retry(
                rqname="주문요청",
                screen_no=self.order_screen_no,
                account_no=self.account_no,
                order_type=order_type_map[signal.side],
                code=signal.symbol,
                qty=int(signal.qty),
                price=price,
                hoga_gb=hoga_gb,
                org_order_no="",
            )

            if ret == 0:
                status = OrderStatus.SUBMITTED
                self.logger.info(f"주문 성공 | {signal.symbol} {signal.side} {signal.qty}")
            else:
                status = OrderStatus.REJECTED
                self.logger.error(f"주문 실패 | ret={ret}")

        except Exception as e:
            self.logger.exception(
                f"주문 예외 | symbol={signal.symbol} side={signal.side} qty={signal.qty} err={e}"
            )
            status = OrderStatus.REJECTED

        return Order(
            order_id=local_id,
            symbol=signal.symbol,
            side=signal.side,
            qty=signal.qty,
            price=price,
            order_type=signal.order_type,
            status=status,
            reason=signal.reason,
        )

    # -------------------------
    # 주문 취소
    # -------------------------
    def cancel_order(self, symbol: str, order_no: str, qty: int, side: Side = Side.SELL) -> int:
        try:
            import config

            if config.DRY_RUN or not config.LIVE_MODE:
                self.logger.warning(
                    f"[DRY_RUN] 취소 모의 처리 | symbol={symbol} order_no={order_no} qty={qty} side={side}"
                )
                return 0

            if not order_no:
                self.logger.warning(f"취소 실패 | 주문번호 없음 | symbol={symbol}")
                return -1

            cancel_type = 4 if side == Side.SELL else 3

            ret = self._send_order_with_retry(
                rqname="주문취소",
                screen_no=self.order_screen_no,
                account_no=self.account_no,
                order_type=cancel_type,
                code=symbol,
                qty=int(qty),
                price=0,
                hoga_gb="00",
                org_order_no=order_no,
            )

            if ret == 0:
                self.logger.info(
                    f"취소 주문 요청 성공 | symbol={symbol} order_no={order_no} qty={qty} side={side}"
                )
            else:
                self.logger.error(
                    f"취소 주문 요청 실패 | symbol={symbol} order_no={order_no} qty={qty} side={side} ret={ret}"
                )

            return ret

        except Exception as e:
            self.logger.exception(
                f"취소 주문 예외 | symbol={symbol} order_no={order_no} qty={qty} side={side} err={e}"
            )
            return -1

    # -------------------------
    # 체잔
    # -------------------------
    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        try:
            if str(gubun).strip() != "0":
                return

            code = self._chejan(9001).replace("A", "").strip()
            order_no = self._chejan(9203).strip()

            order_status = self._chejan(913).strip()
            unfilled_qty = self._to_int(self._chejan(902))
            fill_qty = self._to_int(self._chejan(911))
            fill_price = self._to_int(self._chejan(910))
            side_raw = self._chejan(907).strip()

            side = Side.BUY if side_raw == "2" else Side.SELL if side_raw == "1" else Side.BUY

            self.logger.info(
                f"체결 수신 | gubun={gubun} code={code} order_no={order_no} "
                f"status={order_status} side={side} fill_qty={fill_qty} "
                f"fill_price={fill_price} unfilled_qty={unfilled_qty}"
            )

            if order_status == "체결" and fill_qty > 0 and fill_price > 0:
                fill = Fill(
                    order_id=order_no,
                    symbol=code,
                    side=side,
                    fill_qty=fill_qty,
                    fill_price=fill_price
                )
                fill.unfilled_qty = unfilled_qty

                if self.on_fill_callback:
                    self.on_fill_callback(fill)

        except Exception as e:
            self.logger.exception(f"체잔 오류 | {e}")

    # -------------------------
    # 서버 메시지
    # -------------------------
    def _on_receive_msg(self, screen_no, rqname, trcode, msg):
        self.logger.info(f"서버메시지 | {msg}")

        if self.on_msg_callback:
            self.on_msg_callback(msg)

    # -------------------------
    # 콜백 등록
    # -------------------------
    def set_real_tick_callback(self, cb):
        self.on_real_tick_callback = cb

    def set_fill_callback(self, cb):
        self.on_fill_callback = cb

    def set_msg_callback(self, cb):
        self.on_msg_callback = cb

    # -------------------------
    # 종료
    # -------------------------
    def shutdown(self):
        self.logger.info("브로커 종료 시작")
        self.is_shutting_down = True

        try:
            self.remove_real("ALL")
        except Exception:
            pass

        try:
            if self.login_loop:
                self.login_loop.exit()
        except Exception:
            pass

        try:
            if self.tr_loop and self.tr_loop.isRunning():
                self.tr_loop.quit()
        except Exception:
            pass

        self.connected = False
        self.logger.info("브로커 종료 완료")

    # -------------------------
    # 유틸
    # -------------------------
    def _chejan(self, fid):
        return str(self.ocx.dynamicCall("GetChejanData(int)", fid)).strip()

    def _to_int(self, val):
        try:
            s = str(val).replace(",", "").strip()
            if s == "":
                return 0
            return int(float(s))
        except Exception:
            return 0

    def _to_float(self, value: str) -> float:
        try:
            s = str(value).replace(",", "").strip()
            if s == "":
                return 0.0
            return float(s)
        except Exception:
            return 0.0

    def _clean_code(self, code: str) -> str:
        code = str(code).strip()
        if code.startswith("A"):
            return code[1:]
        return code