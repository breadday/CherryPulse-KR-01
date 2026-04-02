# broker/kiwoom_broker.py

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

        ret = self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            "deposit_req",
            "opw00001",
            0,
            self.deposit_screen_no,
        )
        self.logger.info(f"CommRqData(opw00001) 완료 | ret={ret}")

        self.tr_loop.exec_()
        return self._deposit_result

    def get_positions(self, password: str = "") -> list[dict]:
        """
        보유 종목 조회 (opw00018)
        """
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
        ret = self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            "opw00018_req",
            "opw00018",
            int(prev_next),
            self.balance_screen_no,
        )
        self.logger.info(f"CommRqData(opw00018) 완료 | ret={ret}")

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
            
    def get_pending_orders(self, password: str = "") -> list[dict]:
        """
        미체결 주문 조회 (opt10075)
        반환 예:
        [
            {
                "order_no": "1234567",
                "symbol": "005930",
                "name": "삼성전자",
                "side": Side.BUY,
                "order_price": 70000,
                "order_qty": 2,
                "unfilled_qty": 1,
                "filled_qty": 1,
                "order_status": "접수",
            }
        ]
        """
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
        """
        opt10075 미체결 주문 조회
        입력값:
        - 계좌번호
        - 전체종목구분: 0 전체 / 1 종목
        - 매매구분: 0 전체 / 1 매도 / 2 매수
        - 종목코드: 전체면 공백
        - 체결구분: 1 미체결 / 2 체결 / 0 전체
        """
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self.account_no)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "전체종목구분", "0")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "매매구분", "0")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", "")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "체결구분", "1")

        self.logger.info(f"미체결주문요청 호출 | prev_next={prev_next}")
        ret = self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            "opt10075_req",
            "opt10075",
            int(prev_next),
            self.pending_screen_no,
        )
        self.logger.info(f"CommRqData(opt10075) 완료 | ret={ret}")

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

    def _parse_order_side(self, order_gubun: str):
        text = str(order_gubun).strip().replace("+", "").replace("-", "")
        if "매도" in text:
            return Side.SELL
        return Side.BUY

    def _request_positions(self, prev_next: str = "0", password: str = ""):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self.account_no)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", password)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "1")

        self.logger.info(f"계좌평가잔고내역요청 호출 | prev_next={prev_next}")
        ret = self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            "opw00018_req",
            "opw00018",
            int(prev_next),
            self.balance_screen_no,
        )
        self.logger.info(f"CommRqData(opw00018) 완료 | ret={ret}")

    def get_balance(self):
        """
        기존 호환용.
        내부적으로 get_positions() 결과를 dict 형태로 변환.
        """
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

        ret = self.ocx.dynamicCall(
            "SetRealReg(QString, QString, QString, QString)",
            self.real_screen_no,
            code_str,
            "10;15;13",
            "0"
        )

        self.logger.info(f"실시간 등록 | codes={code_str} ret={ret}")

    def remove_real(self, code="ALL"):
        self.ocx.dynamicCall(
            "SetRealRemove(QString, QString)",
            self.real_screen_no,
            code
        )

    def _on_receive_real_data(self, code, real_type, real_data):
        if self.on_real_tick_callback is None:
            return

        try:
            raw_price = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 10)
            raw_volume = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, 15)

            price = abs(self._to_int(raw_price))
            volume = abs(self._to_int(raw_volume))

            if price <= 0:
                return

            tick = {
                "symbol": code,
                "price": price,
                "trade_volume": volume
            }

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

        ret = self.ocx.dynamicCall(
            "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
            "주문요청",
            self.order_screen_no,
            self.account_no,
            order_type_map[signal.side],
            signal.symbol,
            int(signal.qty),
            price,
            hoga_gb,
            ""
        )

        if ret == 0:
            status = OrderStatus.SUBMITTED
            self.logger.info(f"주문 성공 | {signal.symbol} {signal.side} {signal.qty}")
        else:
            status = OrderStatus.REJECTED
            self.logger.error(f"주문 실패 | ret={ret}")

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
    def cancel_order(self, symbol: str, order_no: str, qty: int) -> int:
        try:
            import config

            if config.DRY_RUN or not config.LIVE_MODE:
                self.logger.warning(
                    f"[DRY_RUN] 취소 모의 처리 | symbol={symbol} order_no={order_no} qty={qty}"
                )
                return 0

            if not order_no:
                self.logger.warning(f"취소 실패 | 주문번호 없음 | symbol={symbol}")
                return -1

            ret = self.ocx.dynamicCall(
                "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                "주문취소",
                self.order_screen_no,
                self.account_no,
                4,
                symbol,
                int(qty),
                0,
                "00",
                order_no
            )

            if ret == 0:
                self.logger.info(
                    f"취소 주문 요청 성공 | symbol={symbol} order_no={order_no} qty={qty}"
                )
            else:
                self.logger.error(
                    f"취소 주문 요청 실패 | symbol={symbol} order_no={order_no} qty={qty} ret={ret}"
                )

            return ret

        except Exception as e:
            self.logger.exception(
                f"취소 주문 예외 | symbol={symbol} order_no={order_no} qty={qty} err={e}"
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