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
TAKE_PROFIT_PCT = 0.04
TRAILING_STOP_PCT = 0.01
PARTIAL_TAKE_RATIO = 0.5
BREAKEVEN_ENABLED = True
TRAILING_STOP_ENABLED = True
STOP_LOSS_PCT = -0.018
PARTIAL_TAKE_PROFIT_PCT = 0.025

# -------------------------
# 재진입 제한
# -------------------------
REENTRY_BLOCK_SEC_AFTER_STOPLOSS = 300
REENTRY_BLOCK_SEC_AFTER_SELL = 300

# -------------------------
# 미체결 대응
# -------------------------
ENABLE_SELL_CANCEL_TIMEOUT = True
SELL_ORDER_TIMEOUT_SEC = 3
RETRY_SELL_AFTER_CANCEL = True
RETRY_SELL_MAX_COUNT = 2
RETRY_SELL_DELAY_SEC = 1

# -------------------------
# 보호모드
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
    "min_trade_strength": 110,
    "min_price_change_pct": 0.3,

    # 거래량 비율
    "min_volume_ratio": 1.0,
    "volume_ratio_hard_floor": 0.75,
    "strong_momentum_trade_strength": 140,
    "strong_momentum_price_change_pct": 0.9,
    "strong_momentum_volume_ratio": 1.1,
    "max_positions": 3,

    # 청산
    "stop_loss_pct": -2.0,
    "take_profit_pct": 4.0,
    "partial_take_profit_pct": 2.0,
    "partial_take_profit_ratio": 0.5,
    "trailing_start_pct": 1.8,
    "trailing_gap_pct": 1.0,

    # 보조
    "re_sell_attempts": 2,
    "protect_mode_drawdown_pct": -3.0,
    "entry_cooldown_sec": 30,
    "allow_reentry": False,

    # 점수 필터
    "use_score_filter": True,
    "min_entry_score": 55,

    # 세부 점수/필터
    "entry_volume_ratio_min": 1.0,
    "news_weight": 1.0,
    "hot_move_price_change_pct": 2.0,
    "hot_move_trade_strength": 145,
    "max_chase_price_change_pct": 4.8,
    "max_chase_volume_ratio": 3.5,
    "min_news_score_for_hot_move": 0.5,
    "min_theme_score_for_entry": 0.0,
    "min_leader_score_for_entry": 0.0,

    # 추가 튜닝 파라미터
    "history_size": 30,
    "min_history_for_entry": 4,
    "pullback_tolerance_pct": 0.015,
    "near_high_tolerance_pct": 0.008,
    "max_short_term_spike_pct": 2.2,
    "require_price_above_recent_avg": True,
}