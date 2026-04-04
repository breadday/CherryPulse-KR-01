import os
from dotenv import load_dotenv

load_dotenv()

# =========================
# 기본 실행 설정
# =========================
LIVE_MODE = True
DRY_RUN = True
ACCOUNT_PASSWORD = os.getenv("ACCOUNT_PASSWORD", "0000")

# =========================
# 텔레그램 설정
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# 주문 / 자금 관리
# =========================
MAX_POSITIONS = 3
ORDER_AMOUNT_PER_TRADE = 500000
REBUY_COOLDOWN_SECONDS = 300


# =========================
# 익절 / 손절 설정 (최종 튜닝)
# =========================
PARTIAL_TAKE_PROFIT_PCT = 0.025   # +2.5%에서 일부만
PARTIAL_TAKE_RATIO = 0.3          # 30%만 매도
TAKE_PROFIT_PCT = 0.060           # +6%까지 열어둠
TRAILING_STOP_PCT = 0.012         # 1.2% 트레일링 (조금 여유)
STOP_LOSS_PCT = -0.018            # 그대로 유지
BREAKEVEN_ENABLED = True
TRAILING_STOP_ENABLED = True

# =========================
# 매도 미체결 / 재매도
# =========================
ENABLE_SELL_CANCEL_TIMEOUT = True
SELL_ORDER_TIMEOUT_SEC = 10
RETRY_SELL_AFTER_CANCEL = True
RETRY_SELL_DELAY_SEC = 2
RETRY_SELL_MAX_COUNT = 2

# =========================
# 재진입 제한
# =========================
REENTRY_BLOCK_SEC_AFTER_STOPLOSS = 300
REENTRY_BLOCK_SEC_AFTER_SELL = 120

# =========================
# 엔진 보호
# =========================
MAX_CONSECUTIVE_LOSS = 3
MAX_DAILY_LOSS = -150000
MAX_ERROR_COUNT = 5

# =========================
# 로그 / 디버그
# =========================
ENABLE_DEBUG_LOG = True
ENABLE_TELEGRAM_LOG = True

# =========================
# 전략 설정
# =========================
STRATEGY_CONFIG = {
    "watchlist": [],

    # 기본 진입 조건
    "min_trade_strength": 120,
    "min_price_change_pct": 0.3,

    # 거래량 조건
    "min_volume_ratio": 1.10,
    "entry_volume_ratio_min": 1.00,
    "volume_ratio_hard_floor": 0.80,

    # 점수 필터
    "use_score_filter": True,
    "min_entry_score": 62,

    # 강한 모멘텀 조건
    "strong_momentum_trade_strength": 140,
    "strong_momentum_price_change_pct": 1.0,
    "strong_momentum_volume_ratio": 1.25,

    # 급등 추격 방지
    "max_chase_price_change_pct": 3.8,
    "max_chase_volume_ratio": 3.5,
    "hot_move_price_change_pct": 2.0,
    "hot_move_trade_strength": 145,
    "min_news_score_for_hot_move": 0.0,

    # 외부 점수
    "news_weight": 1.0,
    "min_theme_score_for_entry": 0.0,
    "min_leader_score_for_entry": 0.0,

    # 구조 필터
    "history_size": 30,
    "min_history_for_entry": 5,
    "pullback_tolerance_pct": 0.010,
    "near_high_tolerance_pct": 0.005,
    "max_short_term_spike_pct": 1.8,
    "require_price_above_recent_avg": True,

    # 포지션 / 재진입
    "max_positions": 1,
    "entry_cooldown_sec": 30,
    "allow_reentry": False,
}