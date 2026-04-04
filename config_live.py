# config_live.py

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
# 실행 모드 (실전/모의실전)
# -------------------------
DRY_RUN = False
LIVE_MODE = True

# -------------------------
# 매도 전략
# -------------------------
PARTIAL_TAKE_PROFIT_PCT = 0.02     # +2.0%
TAKE_PROFIT_PCT = 0.04             # +4.0%
STOP_LOSS_PCT = -0.018             # -1.8%
TRAILING_STOP_PCT = 0.009          # 고점 대비 -0.9%

PARTIAL_TAKE_RATIO = 0.5
BREAKEVEN_ENABLED = True
TRAILING_STOP_ENABLED = True

# -------------------------
# 재진입 제한 (실전은 더 보수적)
# -------------------------
REENTRY_BLOCK_SEC_AFTER_STOPLOSS = 600
REENTRY_BLOCK_SEC_AFTER_SELL = 300

# -------------------------
# 미체결 대응
# -------------------------
ENABLE_SELL_CANCEL_TIMEOUT = True
SELL_ORDER_TIMEOUT_SEC = 10
RETRY_SELL_AFTER_CANCEL = True
RETRY_SELL_MAX_COUNT = 1
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

    # 기본 진입 조건
    "min_trade_strength": 120,
    "min_price_change_pct": 0.5,

    # 거래량 비율
    "min_volume_ratio": 1.1,
    "volume_ratio_hard_floor": 0.85,
    "strong_momentum_trade_strength": 150,
    "strong_momentum_price_change_pct": 1.1,
    "strong_momentum_volume_ratio": 1.25,

    "max_positions": 3,

    # 청산
    "stop_loss_pct": -1.8,
    "take_profit_pct": 4.0,
    "partial_take_profit_pct": 2.0,
    "partial_take_profit_ratio": 0.5,
    "trailing_start_pct": 1.8,
    "trailing_gap_pct": 0.9,

    # 보조
    "re_sell_attempts": 1,
    "protect_mode_drawdown_pct": -3.0,
    "entry_cooldown_sec": 60,
    "allow_reentry": False,

    # 점수 필터
    "use_score_filter": True,
    "min_entry_score": 63,

    # 세부 점수/필터
    "entry_volume_ratio_min": 1.1,
    "news_weight": 1.2,
    "hot_move_price_change_pct": 2.0,
    "hot_move_trade_strength": 155,
    "max_chase_price_change_pct": 4.2,
    "max_chase_volume_ratio": 3.0,
    "min_news_score_for_hot_move": 1.0,
    "min_theme_score_for_entry": 0.0,
    "min_leader_score_for_entry": 0.0,

    # 추가 튜닝 파라미터
    "history_size": 30,
    "min_history_for_entry": 4,
    "pullback_tolerance_pct": 0.010,
    "near_high_tolerance_pct": 0.005,
    "max_short_term_spike_pct": 1.6,
    "require_price_above_recent_avg": True,
}