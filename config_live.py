import os
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# 기본 설정
# -------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ACCOUNT_PASSWORD = "0000"

# -------------------------
# 실행 모드 (실전)
# -------------------------
DRY_RUN = False
LIVE_MODE = True

# -------------------------
# 매도 전략
# -------------------------
PARTIAL_TAKE_PROFIT_PCT = 0.02
TAKE_PROFIT_PCT = 0.04
STOP_LOSS_PCT = -0.02
TRAILING_STOP_PCT = 0.01

PARTIAL_TAKE_RATIO = 0.5
BREAKEVEN_ENABLED = True
TRAILING_STOP_ENABLED = True

# -------------------------
# 재진입 제한 (더 보수적)
# -------------------------
REENTRY_BLOCK_SEC_AFTER_STOPLOSS = 600
REENTRY_BLOCK_SEC_AFTER_SELL = 300

# -------------------------
# 미체결 대응 (실전 중요)
# -------------------------
ENABLE_SELL_CANCEL_TIMEOUT = True
SELL_ORDER_TIMEOUT_SEC = 10       # 🔥 실전은 여유 줘야 함
RETRY_SELL_AFTER_CANCEL = True
RETRY_SELL_MAX_COUNT = 1          # 🔥 실전은 재시도 줄임
RETRY_SELL_DELAY_SEC = 2

# -------------------------
# 보호모드 (강하게)
# -------------------------
MAX_CONSECUTIVE_LOSS = 3
MAX_DAILY_LOSS = -50000
MAX_ERROR_COUNT = 5

# -------------------------
# 주문 제한
# -------------------------
MAX_DAILY_ORDERS = 10
ORDER_COOLDOWN_SEC = 20
MIN_TICK_VOLUME = 1
MAX_SYMBOL_POSITION = 1

# -------------------------
# 전략 설정
# -------------------------
STRATEGY_CONFIG = {
    "watchlist": ["005930", "000660"],

    "min_trade_strength": 120,
    "min_price_change_pct": 0.5,
    "min_volume_ratio": 1.5,
    "max_positions": 3,

    "stop_loss_pct": -2.0,
    "take_profit_pct": 3.0,
    "partial_take_profit_pct": 2.0,
    "partial_take_profit_ratio": 0.5,
    "trailing_start_pct": 1.5,
    "trailing_gap_pct": 1.0,

    "re_sell_attempts": 1,
    "protect_mode_drawdown_pct": -3.0,

    "entry_cooldown_sec": 60,
    "allow_reentry": False,
    "min_entry_score": 2,
}