# config.py

import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ACCOUNT_PASSWORD = "0000"   # 모의계좌용

# 자동 매도 기준
TAKE_PROFIT_PCT = 0.03   # +3.0%
STOP_LOSS_PCT = -0.02    # -2.0%

# 자동 매도 주문 방식
AUTO_SELL_ORDER_TYPE = "MARKET"   # 지금은 시장가 고정처럼 사용

# 재진입 금지 시간(초)
REENTRY_BLOCK_SEC_AFTER_SELL = 300   # 5분
REENTRY_BLOCK_SEC_AFTER_STOPLOSS = 900  # 손절 후 15분

PARTIAL_TAKE_PROFIT_PCT = 0.02   # +2%에서 1차 익절
PARTIAL_TAKE_RATIO = 0.5         # 50% 매도

BREAKEVEN_ENABLED = True         # 본절 이동 활성화

TRAILING_STOP_ENABLED = True
TRAILING_STOP_PCT = 0.015        # 최고가 대비 1.5% 하락 시 청산

SELL_ORDER_TIMEOUT_SEC = 15     # 매도 주문 15초 이상 미체결이면 취소 시도
ENABLE_SELL_CANCEL_TIMEOUT = True

RETRY_SELL_AFTER_CANCEL = True
RETRY_SELL_MAX_COUNT = 2
RETRY_SELL_DELAY_SEC = 2

# 보호모드 설정
MAX_CONSECUTIVE_LOSS = 3        # 연속 손절 3번이면 정지
MAX_DAILY_LOSS = -50000         # 일일 손실 -5만원
MAX_ERROR_COUNT = 5             # 연속 오류 5번

# 실행 모드
DRY_RUN = True                  # True면 실제 주문 전송 안 함 :  DRY_RUN=True 면 주문은 기록만 하고 실제 전송 안 함
LIVE_MODE = True                # 실주문 허용 스위치  :  LIVE_MODE=True 일 때만 실주문 허용

VOLUME_MULTIPLIER = 1.5
VOLATILITY_THRESHOLD = 0.01

# config.py

# -------------------------
# 공통 실행 옵션
# -------------------------
DRY_RUN = True

# -------------------------
# 전략 파라미터
# -------------------------
STRATEGY_CONFIG = {
    # 진입
    "min_trade_strength": 120,          # 최소 체결강도
    "min_price_change_pct": 0.5,        # 최소 상승률(%)
    "min_volume_ratio": 1.5,            # 거래량 배수(기준 대비)
    "max_positions": 3,                 # 최대 동시 보유 종목 수

    # 손절 / 익절 / 트레일링
    "stop_loss_pct": -2.0,              # 손절(%)
    "take_profit_pct": 3.0,             # 1차 익절(%)
    "partial_take_profit_pct": 2.0,     # 부분익절 시작(%)
    "partial_take_profit_ratio": 0.5,   # 부분익절 비중
    "trailing_start_pct": 1.5,          # 트레일링 시작(%)
    "trailing_gap_pct": 1.0,            # 고점대비 하락 허용폭(%)

    # 재매도 / 보호모드
    "re_sell_attempts": 2,              # 취소 후 재매도 최대 횟수
    "protect_mode_drawdown_pct": -3.0,  # 일 손실 보호모드 진입 기준(%)

    # 백테스트용 부가 옵션
    "entry_cooldown_sec": 30,           # 동일 종목 재진입 제한(초)
    "allow_reentry": False,             # 청산 후 재진입 허용 여부

    # 1주 매수 테스트용
    "min_trade_strength": 0,
    "min_price_change_pct": 0.0,
    "min_volume_ratio": 0.0,
}

