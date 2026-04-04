from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict, Optional, Tuple

from core.models import Signal, Side, OrderType


class MomentumIntradayStrategy:
    """
    모멘텀 + 급상승 구간 필터 전략

    엔진에서 사용하는 인터페이스:
    - generate_signal(tick, portfolio)
    - get_last_block_reason(symbol)
    - mark_entry(symbol, ts)
    """

    def __init__(self, logger=None, config=None):
        self.logger = logger
        self.config = config or {}  

        # 최근 틱 히스토리
        self.price_history: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=30))
        self.volume_history: Dict[str, Deque[int]] = defaultdict(lambda: deque(maxlen=30))

        # 마지막 차단 사유 / 마지막 진입 시각
        self._last_block_reason: Dict[str, str] = {}
        self.last_entry_ts: Dict[str, datetime] = {}

        # -------------------------
        # 기본 파라미터
        # -------------------------
        self.min_history = 5
        self.entry_score_threshold = 78.0

        # 급상승 구간 필터
        # self.fast_rise_ret_3 = 0.008   # 3틱 +0.8%
        # self.fast_rise_ret_5 = 0.012   # 5틱 +1.2%
        # self.near_high_ratio = 0.998   # 최근 5틱 최고가의 99.8% 이상
        
        self.fast_rise_ret_3 = 0.004   # 0.4%
        self.fast_rise_ret_5 = 0.007   # 0.7%
        self.near_high_ratio = 0.995
        
        self.max_vertical_ret_5 = 0.060  # 5틱 +6% 초과면 과열로 제외

        # 보조 조건
        self.min_price_change_pct = 1.0
        self.min_trade_strength = 150.0
        self.min_volume_ratio = 1.10
        self.min_news_score = 0.0

    # -------------------------
    # 외부 조회용
    # -------------------------
    def get_last_block_reason(self, symbol: str) -> str:
        return self._last_block_reason.get(symbol, "")

    def mark_entry(self, symbol: str, ts):
        self.last_entry_ts[symbol] = ts

    # -------------------------
    # 내부 유틸
    # -------------------------
    def _set_block(self, symbol: str, reason: str):
        self._last_block_reason[symbol] = reason

    def _safe_float(self, value, default=0.0) -> float:
        try:
            if value in ("", None):
                return default
            return float(value)
        except Exception:
            return default

    def _calc_returns(self, prices: Deque[float]) -> Tuple[float, float]:
        p1 = float(prices[-1])
        p3 = float(prices[-3])
        p5 = float(prices[-5])

        ret_3 = (p1 - p3) / p3 if p3 > 0 else 0.0
        ret_5 = (p1 - p5) / p5 if p5 > 0 else 0.0
        return ret_3, ret_5

    def _is_fast_rising_zone(self, symbol: str, prices: Deque[float]) -> Tuple[bool, str]:
        if len(prices) < 5:
            return False, f"히스토리 부족 {len(prices)}/5"

        ret_3, ret_5 = self._calc_returns(prices)
        current_price = float(prices[-1])
        recent_prices = list(prices)[-5:]
        recent_high = max(recent_prices)
        near_high = current_price >= recent_high * self.near_high_ratio

        if ret_3 < self.fast_rise_ret_3:
            return False, f"3틱 급등 부족 {ret_3:.2%}"

        if ret_5 < self.fast_rise_ret_5:
            return False, f"5틱 급등 부족 {ret_5:.2%}"

        if ret_5 > self.max_vertical_ret_5:
            return False, f"과열 급등 {ret_5:.2%}"

        if not near_high:
            return False, "최근 고점 근처 아님"

        return True, f"급상승 구간 통과 ret3={ret_3:.2%} ret5={ret_5:.2%}"

    def _compute_entry_score(self, tick, prices: Deque[float]) -> Tuple[float, str]:
        chg = self._safe_float(getattr(tick, "price_change_pct", 0.0))
        strength = self._safe_float(getattr(tick, "trade_strength", 0.0))
        volume_ratio = self._safe_float(getattr(tick, "volume_ratio", 0.0))
        news = self._safe_float(getattr(tick, "news_score", 0.0))
        theme = self._safe_float(getattr(tick, "theme_score", 0.0))
        leader = self._safe_float(getattr(tick, "leader_score", 0.0))

        ret_3, ret_5 = self._calc_returns(prices)
        recent_prices = list(prices)[-5:]
        recent_high = max(recent_prices)
        near_high_bonus = 2.0 if tick.price >= recent_high * self.near_high_ratio else 0.0

        chg_score = min(max(chg, 0.0) * 12.0, 24.0)
        str_score = min(max(strength - 130.0, 0.0) * (22.0 / 55.0), 22.0)
        vol_score = min(max(volume_ratio - 1.0, 0.0) * (26.0 / 0.65), 26.0)
        news_score = min(max(news, 0.0) * 10.0, 20.0)

        vertical_penalty = 0.0
        if ret_5 > 0.030:
            vertical_penalty = min((ret_5 - 0.030) * 1000.0, 8.0)

        score = chg_score + str_score + vol_score + news_score + near_high_bonus - vertical_penalty

        detail = (
            f"chg:+{chg_score:.1f},"
            f"str:+{str_score:.1f},"
            f"vol:+{vol_score:.1f},"
            f"news:+{news_score:.1f},"
            f"near_high:+{near_high_bonus:.1f},"
            f"vertical:-{vertical_penalty:.1f}"
        )

        reason = (
            f"ENTRY score={score:.1f} "
            f"chg={chg:.2f}% "
            f"str={strength:.1f} "
            f"vol_ratio={volume_ratio:.2f} "
            f"news={news:.2f} "
            f"theme={theme:.2f} "
            f"leader={leader:.2f} "
            f"detail={detail}"
        )
        return round(score, 1), reason
    
    # -------------------------
    # 메인
    # -------------------------
    def generate_signal(self, tick, portfolio) -> Optional[Signal]:
        symbol = tick.symbol

        # 최근 틱 히스토리 누적
        self.price_history[symbol].append(float(tick.price))
        self.volume_history[symbol].append(int(getattr(tick, "volume", 0)))

        prices = self.price_history[symbol]

        if len(prices) < self.min_history:
            self._set_block(symbol, f"히스토리 부족 {len(prices)}/{self.min_history}")
            return None

        # 이미 보유 중이면 신규 진입 금지
        pos = portfolio.get_position(symbol)
        if int(getattr(pos, "qty", 0)) > 0:
            self._set_block(symbol, "이미 보유중")
            return None

        chg = self._safe_float(getattr(tick, "price_change_pct", 0.0))
        strength = self._safe_float(getattr(tick, "trade_strength", 0.0))
        volume_ratio = self._safe_float(getattr(tick, "volume_ratio", 0.0))
        news = self._safe_float(getattr(tick, "news_score", 0.0))

        if chg < self.min_price_change_pct:
            self._set_block(symbol, f"상승률 부족 {chg:.2f}%")
            return None

        if strength < self.min_trade_strength:
            self._set_block(symbol, f"체결강도 부족 {strength:.1f}")
            return None

        if volume_ratio < self.min_volume_ratio:
            self._set_block(symbol, f"거래량비 부족 {volume_ratio:.2f}")
            return None

        if news < self.min_news_score:
            self._set_block(symbol, f"뉴스점수 부족 {news:.2f}")
            return None

        # 급상승 구간 필터
        ok_fast, fast_reason = self._is_fast_rising_zone(symbol, prices)
        if not ok_fast:
            self._set_block(symbol, fast_reason)
            return None

        score, reason = self._compute_entry_score(tick, prices)
        if score < self.entry_score_threshold:
            self._set_block(symbol, f"점수 부족 {score:.1f}/{self.entry_score_threshold:.1f}")
            return None

        self._last_block_reason[symbol] = ""

        if self.logger:
            self.logger.info(
                f"[FAST_RISE_PASS] {symbol} "
                f"price={tick.price} chg={chg} strength={strength} vr={volume_ratio} "
                f"reason={fast_reason} score={score}"
            )

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=1,
            price=0,
            order_type=OrderType.MARKET,
            reason=reason,
        )
