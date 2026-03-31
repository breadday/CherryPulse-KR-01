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

        self.on_real_tick_callback = None
        self.on_fill_callback = None
        self.on_msg_callback = None

        self._set_signal_slots()

    # -------------------------
    # 이벤트 연결
    # -------------------------
    def _set_signal_slots(self):
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.OnReceiveRealData.connect(self._on_receive_real_data)
        self.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        self.ocx.OnReceiveMsg.connect(self._on_receive_msg)

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
        account_list = [x for x in accounts.split(";") if x.strip()]

        if self.account_no is None:
            self.account_no = account_list[0]

        self.logger.info(f"키움 연결 완료 | 계좌={self.account_no}")

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

            # 값이 이상하면 스킵
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

        # -------------------------
        # DRY RUN / LIVE MODE 체크
        # -------------------------
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

        # -------------------------
        # 실주문
        # -------------------------
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
                4,              # 4: 매도취소, 3: 매수취소
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
        
    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        try:
            # 주문/체결 구분만 우선 처리
            if str(gubun).strip() != "0":
                return

            code = self._chejan(9001).replace("A", "").strip()
            order_no = self._chejan(9203).strip()

            order_status = self._chejan(913).strip()     # 접수 / 확인 / 체결
            unfilled_qty = self._to_int(self._chejan(902))
            fill_qty = self._to_int(self._chejan(911))   # 이번 체결량
            fill_price = self._to_int(self._chejan(910))
            side_raw = self._chejan(907).strip()         # 1:매도, 2:매수

            side = Side.BUY if side_raw == "2" else Side.SELL if side_raw == "1" else Side.BUY

            self.logger.info(
                f"체결 수신 | gubun={gubun} code={code} order_no={order_no} "
                f"status={order_status} side={side} fill_qty={fill_qty} "
                f"fill_price={fill_price} unfilled_qty={unfilled_qty}"
            )

            # 실제 체결분만 엔진으로 넘김
            if order_status == "체결" and fill_qty > 0 and fill_price > 0:
                fill = Fill(
                    order_id=order_no,
                    symbol=code,
                    side=side,
                    fill_qty=fill_qty,
                    fill_price=fill_price
                )

                # engine.py에서 getattr(fill, "unfilled_qty", None)로 읽도록 추가 부착
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

    # -------------------------
    # 종료
    # -------------------------
    def shutdown(self):
        self.logger.info("브로커 종료 시작")
        self.is_shutting_down = True

        try:
            self.remove_real("ALL")
        except:
            pass

        try:
            if self.login_loop:
                self.login_loop.exit()
        except:
            pass

        self.connected = False
        self.logger.info("브로커 종료 완료")

    # -------------------------
    # 계좌 잔고 조회
    # -------------------------
    def get_balance(self):
        result = {}

        self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", self.account_no)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", "0000")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "2")

        self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            "잔고조회",
            "opw00018",
            0,
            "2000"
        )

        # 👉 여기선 간단 버전 (동기 대기 없이 sleep)
        time.sleep(1)

        cnt = int(self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", "opw00018", "잔고조회"))

        for i in range(cnt):
            code = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)",
                                        "opw00018", "잔고조회", i, "종목번호").strip()[1:]
            qty = int(self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)",
                                           "opw00018", "잔고조회", i, "보유수량").strip())
            avg_price = float(self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)",
                                                   "opw00018", "잔고조회", i, "평균단가").strip())

            result[code] = {
                "qty": qty,
                "avg_price": avg_price
            }

        return result
    
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
            return int(s)
        except:
            return 0

    # -------------------------
    # 콜백 등록
    # -------------------------
    def set_real_tick_callback(self, cb):
        self.on_real_tick_callback = cb

    def set_fill_callback(self, cb):
        self.on_fill_callback = cb

    def set_msg_callback(self, cb):
        self.on_msg_callback = cb