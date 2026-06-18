# config_live.py

import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

load_dotenv()

# =========================
# 기본 실행 설정
# =========================
RUN_MODE = str(os.getenv("RUN_MODE", "paper")).strip().lower()
if RUN_MODE not in {"live", "paper"}:
    RUN_MODE = "paper"

PAPER_TRADING = RUN_MODE == "paper"
ALLOW_LIVE_ORDERS = RUN_MODE == "live"

LIVE_MODE = ALLOW_LIVE_ORDERS
DRY_RUN = PAPER_TRADING          # True : 모의 / False : 실주문
ACCOUNT_NO = os.getenv("ACCOUNT_NO", "").strip()
ACCOUNT_PASSWORD = os.getenv("ACCOUNT_PASSWORD", "0000")
SQLITE_DB_PATH = os.getenv(
    "SQLITE_DB_PATH",
    os.path.join(
        os.getenv("LOCALAPPDATA", os.getcwd()),
        "CherryPulse-KR-01",
        "cherry_pulse.sqlite3",
    ),
)

# =========================
# 텔레그램 설정
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_SEND_TIMEOUT_SEC = float(os.getenv("TELEGRAM_SEND_TIMEOUT_SEC", "3"))
SEND_TELEGRAM_ON_SHUTDOWN = False

# =========================
# 주문 / 자금 관리
# =========================
MAX_POSITIONS = 3
ORDER_AMOUNT_PER_TRADE = 1000000     #  주문 금액  1,000,000
REBUY_COOLDOWN_SECONDS = 300
# 기존 보유 잔고가 많아도 전략별 신규매수 검증은 막지 않습니다.
# 대신 각 전략의 max_positions / max_daily_orders로 위험을 제한합니다.
ENFORCE_GLOBAL_MAX_POSITIONS_FOR_BUY = False
ALLOW_MIN_ONE_SHARE_OVER_ORDER_AMOUNT = True


# =========================
# 익절 / 손절 설정 (최종 튜닝)
# =========================
PARTIAL_TAKE_PROFIT_PCT = 0.025   # +2.5%에서 일부만
PARTIAL_TAKE_RATIO = 0.3          # 30%만 매도
TRAILING_STOP_PCT = 0.012         # 1.2% 트레일링 (조금 여유)
BREAKEVEN_ENABLED = True
TRAILING_STOP_ENABLED = True
TAKE_PROFIT_PCT = 0.02            # +6%까지 열어둠   :: 0.060
STOP_LOSS_PCT = -0.015            # 그대로 유지      :: -0.018 
# TAKE_PROFIT_PCT = 0.015           # +6%까지 열어둠   :: 0.060
# STOP_LOSS_PCT = -0.02             # 그대로 유지      :: -0.018 

# 실전형  ==========================
# TAKE_PROFIT_PCT = 0.02    # +2.0%
# STOP_LOSS_PCT = -0.02     # -2.0%
# 밸렌스형 =========================
# TAKE_PROFIT_PCT = 0.02    # +2.0%
# STOP_LOSS_PCT = -0.02     # -2.0%
# 공격형 ===========================
# TAKE_PROFIT_PCT = 0.03    # +3.0%
# STOP_LOSS_PCT = -0.015    # -1.5%

# =========================
# 매도 미체결 / 재매도
# =========================
ENABLE_SELL_CANCEL_TIMEOUT = True
SELL_ORDER_TIMEOUT_SEC = 10
RETRY_SELL_AFTER_CANCEL = True
RETRY_SELL_DELAY_SEC = 2
RETRY_SELL_MAX_COUNT = 2
# 자동매도는 정규장 체결이 안정적으로 가능한 시간에만 허용합니다.
# 장 시작 직후 호가/체결 지연을 피하려고 09:03부터 열어둡니다.
AUTO_SELL_START_HHMM = "09:03"
AUTO_SELL_END_HHMM = "15:20"

# =========================
# 자동 종료 / 오버나이트 보유
# =========================
AUTO_SHUTDOWN_ENABLED = True
# 토/일은 자동으로 휴장일로 판단합니다.
# 평일 휴장일은 아래 목록에 "YYYY-MM-DD" 형식으로 추가하세요.
# 2026-05-25: 부처님오신날 대체공휴일
MARKET_HOLIDAYS = [
    "2026-05-25",  # 부처님오신날 대체공휴일
    "2026-06-03",  # 제9회 전국동시지방선거일
    "2026-07-17",  # 제헌절
]

# =========================
# 재진입 제한
# =========================
REENTRY_BLOCK_SEC_AFTER_STOPLOSS = 300
REENTRY_BLOCK_SEC_AFTER_SELL = 120
# 손절로 청산된 종목은 같은 날 재매수하지 않습니다.
BLOCK_STOPLOSS_SYMBOL_FOR_DAY = True

# =========================
# 신규매수 공통 안전장치
# =========================
# 모든 전략 공통으로 전일 대비 이 이상 오른 급등 종목은 신규매수하지 않습니다.
MAX_NEW_BUY_PRICE_CHANGE_PCT = 10.0

# =========================
# 운영 로그 설정
# =========================
# 0이면 틱/진입체크 원문 로그를 남기지 않습니다.
# 장중에는 틱이 초당 수십 건 들어와 로그 파일이 빠르게 커질 수 있으므로 기본값은 끕니다.
LOG_REAL_TICK_EVERY_N = 0
LOG_ENTRY_CHECK_EVERY_N = 0
SIGNAL_DB_BLOCKED_RETENTION_DAYS = 7
SIGNAL_DB_CLEANUP_ON_START = True

# =========================
# 엔진 보호
# =========================
MAX_CONSECUTIVE_LOSS = 3
MAX_DAILY_LOSS = -150000
MAX_ERROR_COUNT = 5
# 연속손실 보호는 전체 엔진이 아니라 전략별로 적용합니다.
STRATEGY_PROTECTION_ENABLED = True

# =========================
# 키움 응답 대기 제한
# =========================
# Kiwoom 이벤트가 누락되면 QEventLoop가 하루 종일 멈출 수 있어 timeout 후 재시도/복구 흐름으로 빠져나오게 합니다.
KIWOOM_TR_TIMEOUT_SEC = 20
KIWOOM_CONDITION_TIMEOUT_SEC = 20
# 실시간 틱마다 일봉 TR을 반복 호출하면 Kiwoom 응답 지연 시 매매 판단이 무너집니다.
# 일봉 후보는 사전 snapshot을 기본으로 쓰고, 장중 TR 재조회는 긴 간격으로만 재시도합니다.
SKIP_DAILY_CANDLE_FETCH_BEFORE_MARKET = True
DAILY_CANDLE_FETCH_RETRY_SEC = 600
DISABLE_INTRADAY_DAILY_CANDLE_TR = True
DAILY_CANDLE_CSV_DIR = os.path.join(os.path.dirname(__file__), "data", "daily")

# snapshot 후보가 오래된 일봉으로 만들어졌으면 당일 신규매수 후보로 쓰지 않습니다.
SNAPSHOT_MAX_STALE_DAYS = 1
# 오늘 기준 전일 거래일까지의 일봉만 허용합니다.
# 예: 수요일 실행인데 후보 last_date가 월요일이면 화요일 데이터가 빠진 것이므로 차단합니다.
SNAPSHOT_MAX_MISSING_TRADING_DAYS = 0

# 실시간 틱 무수신 복구가 반복되면 계좌/TR 요청까지 같이 지연될 수 있어 횟수를 제한합니다.
STALE_REALDATA_MAX_RECOVERIES = 3

# =========================
# 잔존 포지션 강제청산
# =========================
FORCE_EXIT_STALE_POSITIONS = True
STALE_POSITION_POLICY = {
    "vcp_box": {
        "enabled": True,
        "stale_after_days": 1,
        "exit_start_hhmm": "09:20",
        "exit_end_hhmm": "10:00",
    },
    "bottom_reversal": {
        "enabled": True,
        "stale_after_days": 20,
        "exit_start_hhmm": "14:30",
        "exit_end_hhmm": "15:10",
    },
    "momentum": {
        "enabled": True,
        "stale_after_days": 1,
        "exit_start_hhmm": "09:03",
        "exit_end_hhmm": "09:20",
    },
    "leader_pullback": {
        "enabled": True,
        "stale_after_days": 1,
        "exit_start_hhmm": "09:20",
        "exit_end_hhmm": "10:00",
    },
    "close_buy": {
        "enabled": True,
        "stale_after_days": 1,
        "exit_start_hhmm": "09:30",
        "exit_end_hhmm": "10:00",
    },
    "unknown": {
        "enabled": False,
        "notify_only": True,
    },
}
STALE_POSITION_ALLOWLIST = []
STALE_POSITION_BLOCKLIST = []

# =========================
# 로그 / 디버그
# =========================
ENABLE_DEBUG_LOG = True
ENABLE_TELEGRAM_LOG = True
# 같은 종목/전략/사유의 주문 차단 로그는 아래 초 동안 한 번만 남깁니다.
ORDER_BLOCK_LOG_COOLDOWN_SEC = 30
# 같은 종목/사유의 신호 탈락 로그도 과도하게 쌓이지 않도록 제한합니다.
SIGNAL_SKIP_LOG_COOLDOWN_SEC = 30
ENABLE_TREND_HOLD_AFTER_SCALP = True
TREND_HOLD_MIN_PNL_PCT = 0.012
TREND_HOLD_ENTRY_STRENGTH = 140.0
TREND_HOLD_ENTRY_PRICE_CHANGE_PCT = 0.8
TREND_HOLD_ENTRY_VOLUME_RATIO = 1.1
TREND_HOLD_CURRENT_STRENGTH = 110.0
TREND_HOLD_CURRENT_PRICE_CHANGE_PCT = 0.8
TREND_HOLD_CURRENT_VOLUME_RATIO = 1.0
TREND_HOLD_PARTIAL_TAKE_PROFIT_PCT = 0.02
TREND_HOLD_PARTIAL_TAKE_RATIO = 0.5
TREND_HOLD_FULL_TAKE_PROFIT_PCT = 0.04
TREND_HOLD_TRAILING_START_PCT = 0.03
TREND_HOLD_TRAILING_STOP_PCT = 0.015
TREND_HOLD_BREAKEVEN_FLOOR_PCT = -0.001

# =========================
# 전략별 주문금액 / 청산 설정
# =========================
STRATEGY_RUNTIME_CONFIG = {
    "vcp_box": {
        "enabled": False,
        "start_hhmm": "09:45",
        "end_hhmm": "14:20",
        # 신규 검증 전략이라 소액/저빈도로만 먼저 돌립니다.
        "max_daily_orders": 1,
        "max_positions": 1,
        "max_symbol_position": 1,
        "order_interval_seconds": 600,
        "order_amount_per_trade": 300_000,
        "stop_loss_pct": -0.012,
        "partial_take_profit_pct": 0.020,
        "partial_take_ratio": 0.50,
        "take_profit_pct": 0.040,
        "breakeven_enabled": True,
        "trailing_stop_enabled": True,
        "trailing_start_pct": 0.022,
        "trailing_stop_pct": 0.012,
        "stop_loss_grace_seconds": 90,
        "stop_loss_grace_ticks": 0,
    },
    "bottom_reversal": {
        "enabled": True,
        "start_hhmm": "09:35",
        "end_hhmm": "14:20",
        # 바닥권 회복 전략은 급등 추격이 아니라 좋은 자리 검증용이라 소액/저빈도로 시작합니다.
        "max_daily_orders": 2,
        "max_positions": 1,
        "max_symbol_position": 1,
        "order_interval_seconds": 600,
        "order_amount_per_trade": 300_000,
        "stop_loss_pct": -0.050,
        "partial_take_profit_pct": 0.100,
        "partial_take_ratio": 0.35,
        "take_profit_pct": 0.200,
        "breakeven_enabled": True,
        "trailing_stop_enabled": True,
        "trailing_start_pct": 0.120,
        "trailing_stop_pct": 0.040,
        # 바닥패턴 매수 후 충분히 오른 상태에서 일봉 긴 양봉이 2번 나오면 분출/과열로 보고 잔여 물량을 청산합니다.
        "long_bull_exit_enabled": True,
        "long_bull_exit_timeframe": "daily",
        "long_bull_exit_min_pnl_pct": 0.080,
        "long_bull_body_pct": 0.050,
        "long_bull_close_position": 0.65,
        "long_bull_required_count": 2,
        "long_bull_lookback_candles": 5,
        "stop_loss_grace_seconds": 300,
        "stop_loss_grace_ticks": 0,
        "max_consecutive_loss": 2,
    },
    "momentum": {
        "enabled": False,
        "start_hhmm": "09:35",
        "end_hhmm": "14:50",
        "max_daily_orders": 4,
        "max_positions": 2,
        "max_symbol_position": 1,
        "order_interval_seconds": 120,
        "order_amount_per_trade": 1_000_000,
        "stop_loss_pct": -0.012,
        "partial_take_profit_pct": 0.018,
        "partial_take_ratio": 0.40,
        "take_profit_pct": 0.028,
        "breakeven_enabled": True,
        "trailing_stop_enabled": True,
        "trailing_start_pct": 0.018,
        "trailing_stop_pct": 0.010,
        "stop_loss_grace_seconds": 90,
        "stop_loss_grace_ticks": 0,
        # 모멘텀은 급등 추격 손실이 빠르게 누적될 수 있어 2연속 손실이면 당일 중지합니다.
        "max_consecutive_loss": 2,
    },
    "leader_pullback": {
        "enabled": True,
        "start_hhmm": "09:40",
        "end_hhmm": "14:30",
        # 아직 승률 검증이 부족한 전략이라 소액/저빈도로만 비교합니다.
        "max_daily_orders": 3,
        "max_positions": 1,
        "max_symbol_position": 1,
        "order_interval_seconds": 120,
        "order_amount_per_trade": 300_000,
        "stop_loss_pct": -0.017,
        "partial_take_profit_pct": 0.022,
        "partial_take_ratio": 0.35,
        "take_profit_pct": 0.036,
        "breakeven_enabled": True,
        "trailing_stop_enabled": True,
        "trailing_start_pct": 0.022,
        "trailing_stop_pct": 0.012,
        "stop_loss_grace_seconds": 120,
        "stop_loss_grace_ticks": 0,
    },
    "close_buy": {
        "enabled": True,
        "start_hhmm": "15:15",
        "end_hhmm": "15:25",
        "max_daily_orders": 1,
        "max_positions": 1,
        "max_symbol_position": 1,
        "order_interval_seconds": 0,
        "order_amount_per_trade": 300_000,
        "stop_loss_pct": -0.020,
        "partial_take_profit_pct": 0.025,
        "partial_take_ratio": 0.50,
        "take_profit_pct": 0.045,
        "breakeven_enabled": True,
        "trailing_stop_enabled": True,
        "trailing_start_pct": 0.028,
        "trailing_stop_pct": 0.015,
        "stop_loss_grace_seconds": 0,
        "stop_loss_grace_ticks": 0,
        "next_day_exit_enabled": True,
        "next_day_exit_start_hhmm": "09:05",
        "next_day_exit_force_hhmm": "09:30",
        "next_day_take_profit_pct": 0.012,
        "next_day_stop_loss_pct": -0.015,
    },
}

STRATEGY_UNIVERSE_CONFIG = {
    "vcp_box": {
        "use_snapshot": False,
        "use_condition": False,
    },
    "bottom_reversal": {
        "use_snapshot": True,
        "use_condition": False,
    },
    "momentum": {
        "use_snapshot": False,
        "use_condition": False,
    },
    "leader_pullback": {
        "use_snapshot": True,
        "use_condition": False,
    },
    "close_buy": {
        "use_snapshot": True,
        "use_condition": False,
    },
}

# =========================
# 전략 설정
# =========================
ENABLE_CONDITION_SEARCH = False

STRATEGY_CONFIG = {
    "watchlist": [],
    "daily_candidate_mode": True,
    "enable_vcp_box_entry": False,
    "enable_bottom_reversal_entry": True,
    "enable_momentum_entry": False,
    "enable_leader_pullback_entry": True,
    "enable_close_buy_entry": True,

    # 기본 진입 조건
    "min_trade_strength": 80,
    "min_price_change_pct": 0.1,

    # 거래량 조건
    "min_volume_ratio": 0.70,
    "entry_volume_ratio_min": 0.70,
    "volume_ratio_hard_floor": 0.50,

    # 점수 필터
    "use_score_filter": False,
    "min_entry_score": 40,

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
    "entry_cooldown_sec": 30,
    "allow_reentry": False,

    # VCP + 다바스 박스 돌파 전략
    # 장중 고점 추격보다, 좁은 박스 안에서 변동성이 줄었다가 다시 돌파하는 종목만 소액 검증합니다.
    "vcp_box_selector_start_hhmm": "09:45",
    "vcp_box_selector_end_hhmm": "14:20",
    "vcp_box_min_price": 1000,
    "vcp_box_min_price_change_pct": 0.2,
    "vcp_box_max_price_change_pct": 10.0,
    "vcp_box_min_volume_ratio": 0.7,
    "vcp_box_history_size": 80,
    "vcp_box_min_history": 35,
    "vcp_box_lookback": 24,
    "vcp_box_early_lookback": 24,
    "vcp_box_max_box_width_pct": 2.8,
    "vcp_box_min_prior_width_pct": 1.2,
    "vcp_box_max_contraction_ratio": 0.75,
    "vcp_box_breakout_buffer_pct": 0.05,
    "vcp_box_min_trade_strength": 80.0,
    "vcp_box_signal_min_volume_ratio": 1.1,
    "vcp_box_signal_min_price_change_pct": 0.5,
    "vcp_box_signal_max_price_change_pct": 10.0,
    "vcp_box_entry_cooldown_sec": 600,

    # 바닥권 회복 전략
    # 하락이 멈춘 뒤 저점 대비 회복, 단기 평균선 회복, 거래량/체결강도 개선이 같이 나올 때만 매수합니다.
    "bottom_reversal_selector_start_hhmm": "09:35",
    "bottom_reversal_selector_end_hhmm": "14:20",
    "bottom_reversal_min_price": 1000,
    "bottom_reversal_min_price_change_pct": -3.5,
    "bottom_reversal_max_price_change_pct": 4.0,
    "bottom_reversal_min_volume_ratio": 0.4,
    "bottom_reversal_daily_candle_count": 100,
    "bottom_reversal_daily_cache_ttl_sec": 21600,
    "bottom_reversal_require_daily_pattern": True,
    "bottom_reversal_daily_min_candles": 60,
    "bottom_reversal_daily_lookback": 60,
    "bottom_reversal_daily_min_decline_pct": 25.0,
    "bottom_reversal_daily_near_low_pct": 16.0,
    "bottom_reversal_daily_recovery_from_low_pct": 5.0,
    "bottom_reversal_daily_min_volume_ratio": 1.2,
    "bottom_reversal_daily_ma_short": 5,
    "bottom_reversal_daily_ma_mid": 20,
    "bottom_reversal_daily_w_low_tolerance_pct": 5.0,
    "bottom_reversal_daily_w_min_separation": 5,
    "bottom_reversal_daily_v_recovery_pct": 5.0,
    "bottom_reversal_daily_rounded_rising_days": 2,
    "bottom_reversal_history_size": 80,
    "bottom_reversal_min_history": 25,
    "bottom_reversal_short_window": 5,
    "bottom_reversal_long_window": 20,
    "bottom_reversal_pattern_lookback": 50,
    "bottom_reversal_min_ticks_after_low": 3,
    "bottom_reversal_require_pattern": True,
    "bottom_reversal_enable_w_bottom": True,
    "bottom_reversal_enable_v_reversal": True,
    "bottom_reversal_enable_rounded_bottom": True,
    "bottom_reversal_w_min_separation": 6,
    "bottom_reversal_w_low_tolerance_pct": 1.2,
    "bottom_reversal_w_undercut_tolerance_pct": 0.6,
    "bottom_reversal_w_neckline_break_pct": 0.05,
    "bottom_reversal_v_drop_pct": 1.0,
    "bottom_reversal_v_recovery_pct": 0.8,
    "bottom_reversal_rounded_rising_ticks": 3,
    "bottom_reversal_min_recovery_from_low_pct": 0.4,
    "bottom_reversal_max_recovery_from_low_pct": 3.0,
    "bottom_reversal_max_pullback_from_high_pct": 5.0,
    "bottom_reversal_min_last_momentum_pct": 0.12,
    "bottom_reversal_signal_min_price_change_pct": -3.0,
    "bottom_reversal_signal_max_price_change_pct": 4.0,
    "bottom_reversal_signal_min_volume_ratio": 0.7,
    "bottom_reversal_signal_min_trade_strength": 80.0,
    "bottom_reversal_entry_cooldown_sec": 900,

    "leader_entry_start_hhmm": "09:00",
    "leader_pullback_exclude_symbols": ["005930", "000660"],
    "daily_candidate_max_gap_pct": 7.0,
    "leader_initial_rally_pct": 0.2,
    "leader_pullback_min_pct": 0.2,
    "leader_pullback_max_pct": 2.5,
    "leader_price_change_floor": 0.0,
    "leader_volume_ratio_floor": 0.4,
    "leader_strength_floor": 0.0,
    "leader_support_open_tolerance_pct": 0.5,
    "leader_rally_by_change_pct": 0.2,
    "leader_rally_by_volume_ratio": 0.7,

    # 종가매수 selector
    "close_buy_start_hhmm": "15:15",
    "close_buy_end_hhmm": "15:25",
    "close_buy_min_price": 1000,
    "close_buy_min_price_change_pct": 0.3,
    "close_buy_min_volume_ratio": 0.8,
    "close_buy_min_trade_strength": 0.0,
    "close_buy_max_price_change_pct": 7.0,

    # 종가매수 signal: 상승추세 종목의 장후반 눌림/회복을 소액 검증합니다.
    "close_buy_signal_min_price_change_pct": 0.3,
    "close_buy_signal_min_volume_ratio": 0.8,
    "close_buy_signal_min_trade_strength": 0.0,
    "close_buy_signal_max_price_change_pct": 7.0,
    "close_buy_signal_min_total_score": 0.0,
    "close_buy_use_rsi2": True,
    "close_buy_signal_max_rsi2": 30.0,
    "close_buy_rsi_sample_seconds": 60,
    "close_buy_rsi_max_samples": 30,
    "close_buy_min_recovery_from_low_pct": 0.3,
    "close_buy_max_pullback_from_high_pct": 4.5,
}

# =========================
# 오전 7시 종목 선정 연동
# =========================
SELECTED_STOCKS_FILE = "selected_stocks.json"
SELECTION_CANDIDATES_FILE = "selection_candidates.json"
SELECTION_UNIVERSE_FILE = "selection_universe.json"
SELECTION_NEWS_OVERRIDES_FILE = "selection_news_overrides.json"
DEFAULT_FALLBACK_SYMBOLS = ["005930", "000660"]
SELECTION_TOP_N = 3
