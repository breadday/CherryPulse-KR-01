# config_test.py

import os
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# 기본 설정
# -------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ACCOUNT_PASSWORD = os.getenv("ACCOUNT_PASSWORD", "0000")

# -------------------------
# 실행 모드 (테스트)
# -------------------------
DRY_RUN = True
LIVE_MODE = False

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
# 재진입 제한
# -------------------------
REENTRY_BLOCK_SEC_AFTER_STOPLOSS = 300
REENTRY_BLOCK_SEC_AFTER_SELL = 300

# -------------------------
# 미체결 대응 (테스트 핵심)
# -------------------------
ENABLE_SELL_CANCEL_TIMEOUT = True
SELL_ORDER_TIMEOUT_SEC = 3
RETRY_SELL_AFTER_CANCEL = True
RETRY_SELL_MAX_COUNT = 2
RETRY_SELL_DELAY_SEC = 1

# -------------------------
# 보호모드 (느슨하게)
# -------------------------
MAX_CONSECUTIVE_LOSS = 5
MAX_DAILY_LOSS = -100000
MAX_ERROR_COUNT = 20

# -------------------------
# 주문 제한
# -------------------------
MAX_DAILY_ORDERS = 20
ORDER_COOLDOWN_SEC = 10
MIN_TICK_VOLUME = 1
MAX_SYMBOL_POSITION = 1

# -------------------------
# 전략 설정
# -------------------------
STRATEGY_CONFIG = {
    "watchlist": ["005930", "000660"],

    # 기본 진입 조건
    "min_trade_strength": 0,
    "min_price_change_pct": 0.0,

    # 새 volume_ratio 기준 반영
    "min_volume_ratio": 0.9,
    "volume_ratio_hard_floor": 0.5,
    "strong_momentum_trade_strength": 130,
    "strong_momentum_price_change_pct": 0.8,
    "strong_momentum_volume_ratio": 0.75,

    "max_positions": 3,

    # 청산
    "stop_loss_pct": -2.0,
    "take_profit_pct": 3.0,
    "partial_take_profit_pct": 2.0,
    "partial_take_profit_ratio": 0.5,
    "trailing_start_pct": 1.5,
    "trailing_gap_pct": 1.0,

    # 보조
    "re_sell_attempts": 2,
    "protect_mode_drawdown_pct": -3.0,
    "entry_cooldown_sec": 30,
    "allow_reentry": False,

    # 점수 필터
    "use_score_filter": True,
    "min_entry_score": 50,

    "entry_volume_ratio_min": 1.0,
    "news_weight": 1.3,
    "hot_move_price_change_pct": 2.0,
    "hot_move_trade_strength": 145,
    "max_chase_price_change_pct": 5.0,
    "max_chase_volume_ratio": 4.0,
    "min_news_score_for_hot_move": 1.0,
    "min_theme_score_for_entry": 0.0,
    "min_leader_score_for_entry": 0.0,    
}