# config_live.py

import os
from dotenv import load_dotenv

load_dotenv()

# =========================
# 기본 실행 설정
# =========================
LIVE_MODE = True
DRY_RUN = True   # 실주문 전 검증 단계에서는 True 유지
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
ORDER_AMOUNT_PER_TRADE = 500000   # 종목당 진입 금액
REBUY_COOLDOWN_SECONDS = 300      # 동일 종목 재진입 쿨다운

# =========================
# 수익률 튜닝 2차
# =========================
# 1차 부분익절: +2.5%
PARTIAL_TAKE_PROFIT_PCT = 0.025

# 최종 익절: 필요 시 기존 값 유지 또는 약간 상단 유지
TAKE_PROFIT_PCT = 0.045

# 손절: -1.8%
STOP_LOSS_PCT = -0.018

# =========================
# 진입 필터 튜닝
# =========================
# 최소 진입 점수 상향
MIN_ENTRY_SCORE = 65

# 추격매수 제한
MAX_CHASE_PRICE_CHANGE_PCT = 3.8

# 최소 체결강도 상향
MIN_TRADE_STRENGTH = 125

# =========================
# 거래량 / 가격 필터
# =========================
MIN_VOLUME = 50000
MIN_PRICE = 3000
MAX_PRICE = 300000

# =========================
# 장 운영 시간
# =========================
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 0
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 20

# =========================
# 로그 / 디버그
# =========================
ENABLE_DEBUG_LOG = True
ENABLE_TELEGRAM_LOG = True

# -------------------------
# 전략 설정 (🔥 추가)
# -------------------------
STRATEGY_CONFIG = {
    # 진입 필터
    "min_trade_strength": 125,
    "min_price_change_pct": 0.3,

    # 거래량
    "min_volume_ratio": 1.2,
    "entry_volume_ratio_min": 1.1,
    "volume_ratio_hard_floor": 0.8,

    # 점수 필터
    "use_score_filter": True,
    "min_entry_score": 65,

    # 강한 모멘텀
    "strong_momentum_trade_strength": 140,
    "strong_momentum_price_change_pct": 1.0,
    "strong_momentum_volume_ratio": 1.3,

    # 급등 추격 방지
    "max_chase_price_change_pct": 3.8,
    "hot_move_price_change_pct": 2.0,
    "hot_move_trade_strength": 145,

    # 뉴스 / 테마 / 대장
    "news_weight": 1.0,
    "min_theme_score_for_entry": 0.0,
    "min_leader_score_for_entry": 0.0,

    # 구조 필터
    "history_size": 30,
    "min_history_for_entry": 5,
    "pullback_tolerance_pct": 0.010,
    "near_high_tolerance_pct": 0.005,
    "max_short_term_spike_pct": 1.6,
    "require_price_above_recent_avg": True,

    # 포지션
    "max_positions": 1,
    "entry_cooldown_sec": 30,
    "allow_reentry": False,
}
