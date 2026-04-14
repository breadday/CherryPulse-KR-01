# broker/kiwoom_broker.py

from collections import defaultdict, deque
from PyQt5.QtCore import QObject, QEventLoop
from PyQt5.QAxContainer import QAxWidget
import time

import config_live as config
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
        self.daily_screen_no = "7300"
        self.investor_screen_no = "7400"

        self.on_real_tick_callback = None
        self.on_fill_callback = None
        self.on_msg_callback = None

        self._deposit_result = 0
        self._positions_result = []
        self._positions_password = ""

        self._pending_orders_result = []
        self._pending_orders_password = ""

        self._daily_candles_result = []
        self._daily_candles_symbol = ""
        self._daily_candles_target_count = 0
        self._daily_candles_prev_next = "0"

        self._investor_flow_result = {}
        self._investor_flow_symbol = ""

        # -------------------------
        # 조건검색
        # -------------------------
        self.condition_screen_no = "7500"
        self.condition_loop = None
        self._condition_loaded = False
        self._condition_list = []
        self._condition_name_to_index = {}
        self._condition_result_codes = []
        self._condition_target_name = ""
        self._condition_active_name = ""
        self._condition_active_index = -1
        self.registered_real_codes = set()

        self.on_condition_initial_callback = None
        self.on_condition_realtime_callback = None

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
        self.ocx.OnReceiveConditionVer.connect(self._on_receive_condition_ver)
        self.ocx.OnReceiveTrCondition.connect(self._on_receive_tr_condition)
        self.ocx.OnReceiveRealCondition.connect(self._on_receive_real_condition)

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


    def get_code_name(self, code: str) -> str:
        try:
            name = self.ocx.dynamicCall("GetMasterCodeName(QString)", str(code).strip())
            return str(name).strip()
        except Exception:
            return ""

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

            if sRQName == "opt10081_req":
                self._handle_opt10081(sTrCode, sRQName, sPrevNext)
                return

            if sRQName == "opt10060_req":
                self._handle_opt10060(sTrCode, sRQName, sPrevNext)
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

    def _handle_opt10081(self, sTrCode: str, sRQName: str, sPrevNext: str):
        count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", sTrCode, sRQName)
        target_count = max(1, int(self._daily_candles_target_count or 20))

        self.logger.info(
            f"opt10081 수신 | symbol={self._daily_candles_symbol} rows={count} | "
            f"target_count={target_count} | sPrevNext={sPrevNext}"
        )

        existing_count = len(self._daily_candles_result)
        remaining = max(0, target_count - existing_count)
        rows_to_read = min(int(count), remaining)

        for i in range(rows_to_read):
            date = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "일자"
            ).strip()
            open_price = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "시가"
            ).strip()
            high_price = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "고가"
            ).strip()
            low_price = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "저가"
            ).strip()
            close_price = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "현재가"
            ).strip()
            volume = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "거래량"
            ).strip()
            trade_value = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, i, "거래대금"
            ).strip()

            self._daily_candles_result.append(
                {
                    "date": date,
                    "open": self._to_int(open_price),
                    "high": self._to_int(high_price),
                    "low": self._to_int(low_price),
                    "close": self._to_int(close_price),
                    "volume": self._to_int(volume),
                    "trade_value": self._to_int(trade_value),
                }
            )

        self._daily_candles_prev_next = str(sPrevNext).strip() or "0"

        if len(self._daily_candles_result) >= target_count:
            self.logger.info(
                f"opt10081 목표 개수 충족 | symbol={self._daily_candles_symbol} "
                f"collected={len(self._daily_candles_result)}"
            )
            if self.tr_loop and self.tr_loop.isRunning():
                self.tr_loop.quit()
            return

        need_more = self._daily_candles_prev_next == "2"

        if need_more:
            self._request_daily_candles(
                symbol=self._daily_candles_symbol,
                count=self._daily_candles_target_count,
                prev_next=2,
            )
            return

        if self.tr_loop and self.tr_loop.isRunning():
            self.tr_loop.quit()

    def _handle_opt10060(self, sTrCode: str, sRQName: str, sPrevNext: str):
        self.logger.info(f"opt10060 수신 | symbol={self._investor_flow_symbol} | sPrevNext={sPrevNext}")

        def _get(item_name: str):
            return self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                sTrCode, sRQName, 0, item_name
            ).strip()

        self._investor_flow_result = {
            "symbol": self._investor_flow_symbol,
            "date": _get("일자"),
            "current_price": self._to_int(_get("현재가")),
            "trade_value": self._to_int(_get("누적거래대금")),
            "individual": self._to_int(_get("개인투자자")),
            "foreign": self._to_int(_get("외국인투자자")),
            "institution": self._to_int(_get("기관계")),
            "financial_investment": self._to_int(_get("금융투자")),
            "insurance": self._to_int(_get("보험")),
            "investment_trust": self._to_int(_get("투신")),
            "pension": self._to_int(_get("연기금등")),
            "private_fund": self._to_int(_get("사모펀드")),
            "state": self._to_int(_get("국가")),
            "corporate": self._to_int(_get("기타법인")),
        }

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

    def get_daily_candles(self, symbol: str, count: int = 20, base_date: str = ""):
        self.logger.info(f"get_daily_candles 호출 | symbol={symbol} count={count} base_date={base_date}")

        self._daily_candles_result = []
        self._daily_candles_symbol = str(symbol).strip()
        self._daily_candles_target_count = int(count)
        self._daily_candles_prev_next = "0"

        self._request_daily_candles(
            symbol=self._daily_candles_symbol,
            count=count,
            prev_next=0,
            base_date=base_date,
        )

        self.logger.info(
            f"get_daily_candles 완료 | symbol={symbol} count={len(self._daily_candles_result)}"
        )
        return self._daily_candles_result[:count]

    def _request_daily_candles(self, symbol: str, count: int, prev_next: int = 0, base_date: str = ""):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", str(symbol))
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "기준일자", str(base_date or ""))
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "수정주가구분", "1")

        self.tr_loop = QEventLoop()
        self._comm_rq_data_with_retry(
            rqname="opt10081_req",
            trcode="opt10081",
            prev_next=int(prev_next),
            screen_no=self.daily_screen_no,
        )
        self.tr_loop.exec_()

    def get_investor_flow(self, symbol: str, date_yyyymmdd: str):
        self.logger.info(f"get_investor_flow 호출 | symbol={symbol} date={date_yyyymmdd}")

        self._investor_flow_symbol = str(symbol).strip()
        self._investor_flow_result = {}

        self.tr_loop = QEventLoop()
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "일자", str(date_yyyymmdd))
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", str(symbol))
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "금액수량구분", "1")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "매매구분", "0")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "단위구분", "1")

        self._comm_rq_data_with_retry(
            rqname="opt10060_req",
            trcode="opt10060",
            prev_next=0,
            screen_no=self.investor_screen_no,
        )
        self.tr_loop.exec_()

        self.logger.info(
            f"get_investor_flow 완료 | symbol={symbol} "
            f"foreign={self._investor_flow_result.get('foreign', 0)} "
            f"institution={self._investor_flow_result.get('institution', 0)}"
        )
        return self._investor_flow_result.copy()

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

        if str(real_type).strip() != "주식체결":
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

            if trade_strength <= 0.0 and total_volume > 0:
                self.logger.info(
                    f"[REAL_WARN] code={code} real_type={real_type} "
                    f"raw_strength='{str(raw_trade_strength).strip()}' price={price} "
                    f"chg={price_change_pct} tick_vol={tick_volume} total_vol={total_volume}"
                )

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
    # 조건검색
    # -------------------------
    def load_condition_list(self):
        self.logger.info("조건검색 목록 로드 시작")
        self._condition_loaded = False
        self._condition_list = []
        self._condition_name_to_index = {}
        self.condition_loop = QEventLoop()

        ret = self.ocx.dynamicCall("GetConditionLoad()")
        self.logger.info(f"GetConditionLoad 호출 | ret={ret}")

        if ret != 1:
            self.condition_loop = None
            raise RuntimeError(f"GetConditionLoad 실패 | ret={ret}")

        self.condition_loop.exec_()

        if not self._condition_loaded:
            raise RuntimeError("조건검색 목록 로드 실패")

        self.logger.info(f"조건검색 목록 로드 완료 | count={len(self._condition_list)}")
        return list(self._condition_list)

    def get_condition_list(self):
        return list(self._condition_list)

    def send_condition_by_name(self, condition_name: str, search: int = 1):
        target_name = str(condition_name).strip()
        if not target_name:
            raise ValueError("condition_name 이 비어 있습니다.")

        if not self._condition_loaded:
            self.load_condition_list()

        if target_name not in self._condition_name_to_index:
            names = ", ".join(name for _, name in self._condition_list)
            raise RuntimeError(
                f"조건식 미존재 | target={target_name} available=[{names}]"
            )

        index = int(self._condition_name_to_index[target_name])
        self._condition_target_name = target_name
        self._condition_result_codes = []
        self.condition_loop = QEventLoop()

        ret = self.ocx.dynamicCall(
            "SendCondition(QString, QString, int, int)",
            self.condition_screen_no,
            target_name,
            index,
            int(search),
        )
        self.logger.info(
            f"SendCondition 호출 | screen={self.condition_screen_no} name={target_name} "
            f"index={index} search={search} ret={ret}"
        )

        if ret != 1:
            self.condition_loop = None
            raise RuntimeError(
                f"SendCondition 실패 | condition_name={target_name} index={index} ret={ret}"
            )

        self.condition_loop.exec_()

        self._condition_active_name = target_name
        self._condition_active_index = index

        codes = list(self._condition_result_codes)
        self.logger.info(
            f"조건검색 초기 결과 수신 완료 | name={target_name} count={len(codes)}"
        )
        return codes

    def stop_condition(self, condition_name: str = ""):
        target_name = str(condition_name or self._condition_active_name).strip()
        if not target_name:
            return

        index = self._condition_name_to_index.get(target_name, self._condition_active_index)
        if index is None or int(index) < 0:
            return

        self.ocx.dynamicCall(
            "SendConditionStop(QString, QString, int)",
            self.condition_screen_no,
            target_name,
            int(index),
        )
        self.logger.info(
            f"SendConditionStop 호출 | screen={self.condition_screen_no} "
            f"name={target_name} index={index}"
        )

    def register_real(self, codes):
        clean_codes = []
        for code in codes or []:
            c = self._clean_code(code)
            if c:
                clean_codes.append(c)

        self.registered_real_codes = set(clean_codes)
        self._apply_real_registration()

    def register_real_add(self, code: str):
        clean_code = self._clean_code(code)
        if not clean_code:
            return

        if clean_code in self.registered_real_codes:
            return

        self.registered_real_codes.add(clean_code)
        self._apply_real_registration()

    def register_real_remove(self, code: str):
        clean_code = self._clean_code(code)
        if not clean_code:
            return

        if clean_code not in self.registered_real_codes:
            return

        self.registered_real_codes.remove(clean_code)
        self._apply_real_registration()

    def remove_real(self, code="ALL"):
        if code == "ALL":
            self.registered_real_codes = set()

        self.ocx.dynamicCall(
            "SetRealRemove(QString, QString)",
            self.real_screen_no,
            code
        )

    def _apply_real_registration(self):
        self.ocx.dynamicCall(
            "SetRealRemove(QString, QString)",
            self.real_screen_no,
            "ALL"
        )

        if not self.registered_real_codes:
            self.logger.info("실시간 등록 해제 | codes=(empty)")
            return

        code_str = ";".join(sorted(self.registered_real_codes))

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

        self.logger.info(
            f"실시간 등록 | codes={code_str} fids={fid_list} ret={ret}"
        )

    def _on_receive_condition_ver(self, ret, msg):
        self.logger.info(f"OnReceiveConditionVer | ret={ret} msg={msg}")

        try:
            if int(ret) != 1:
                self._condition_loaded = False
                return

            raw = self.ocx.dynamicCall("GetConditionNameList()")
            items = []
            name_to_index = {}

            for part in str(raw).split(";"):
                part = part.strip()
                if not part:
                    continue
                if "^" not in part:
                    continue

                idx_str, name = part.split("^", 1)
                idx = int(str(idx_str).strip())
                cond_name = str(name).strip()

                items.append((idx, cond_name))
                name_to_index[cond_name] = idx

            self._condition_list = items
            self._condition_name_to_index = name_to_index
            self._condition_loaded = True
        except Exception as e:
            self._condition_loaded = False
            self.logger.exception(f"조건검색 목록 처리 오류 | err={e}")
        finally:
            if self.condition_loop and self.condition_loop.isRunning():
                self.condition_loop.exit()
                self.condition_loop = None

    def _on_receive_tr_condition(self, screen_no, code_list, condition_name, index, next_):
        codes = []
        for code in str(code_list).split(";"):
            clean_code = self._clean_code(code)
            if clean_code:
                codes.append(clean_code)

        self._condition_result_codes = codes
        self.logger.info(
            f"OnReceiveTrCondition | screen={screen_no} name={condition_name} "
            f"index={index} count={len(codes)} next={next_}"
        )

        if callable(self.on_condition_initial_callback):
            try:
                self.on_condition_initial_callback(condition_name, list(codes))
            except Exception as e:
                self.logger.exception(f"조건검색 초기 콜백 오류 | err={e}")

        if self.condition_loop and self.condition_loop.isRunning():
            self.condition_loop.exit()
            self.condition_loop = None

    def _on_receive_real_condition(self, code, event_type, condition_name, condition_index):
        clean_code = self._clean_code(code)
        ev = str(event_type).strip()
        self.logger.info(
            f"OnReceiveRealCondition | code={clean_code} event={ev} "
            f"name={condition_name} index={condition_index}"
        )

        if callable(self.on_condition_realtime_callback):
            try:
                self.on_condition_realtime_callback(
                    clean_code,
                    ev,
                    str(condition_name).strip(),
                    int(condition_index),
                )
            except Exception as e:
                self.logger.exception(f"조건검색 실시간 콜백 오류 | err={e}")
    # -------------------------
    # 콜백 등록
    # -------------------------
    def set_real_tick_callback(self, cb):
        self.on_real_tick_callback = cb

    def set_fill_callback(self, cb):
        self.on_fill_callback = cb

    def set_msg_callback(self, cb):
        self.on_msg_callback = cb

    def set_condition_initial_callback(self, cb):
        self.on_condition_initial_callback = cb

    def set_condition_realtime_callback(self, cb):
        self.on_condition_realtime_callback = cb

    # -------------------------
    # 종료
    # -------------------------
    def shutdown(self):
        self.logger.info("브로커 종료 시작")
        self.is_shutting_down = True

        try:
            self.stop_condition()
        except Exception:
            pass

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

        try:
            if self.condition_loop and self.condition_loop.isRunning():
                self.condition_loop.quit()
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
