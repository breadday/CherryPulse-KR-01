# strategy/momentum_intraday.py

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional

from core.models import Signal, Side


class MomentumIntradayStrategy:
    """
    CherryPulse-KR-01 전략 튜닝 버전

    엔진 호환 포인트:
    - engine.py 에서 strategy.generate_signal(tick, portfolio) 호출
    - 따라서 generate_signal() 메서드를 반드시 제공
    """

    def __init__(self, config=None):
        self.cfg = config or {}

        self.watchlist = set(self.cfg.get("watchlist", []))

        # 기본 진입 조건
        self.min_trade_strength = float(self.cfg.get("min_trade_strength", 0))
        self.min_price_change_pct = float(self.cfg.get("min_price_change_pct", 0.0))

        # 거래량 비율 관련
        self.min_volume_ratio = float(self.cfg.get("min_volume_ratio", 1.0))
        self.volume_ratio_hard_floor = float(self.cfg.get("volume_ratio_hard_floor", 0.5))
        self.strong_momentum_trade_strength = float(
            self.cfg.get("strong_momentum_trade_strength", 130)
        )
        self.strong_momentum_price_change_pct = float(
            self.cfg.get("strong_momentum_price_change_pct", 1.0)
        )
        self.strong_momentum_volume_ratio = float(
            self.cfg.get("strong_momentum_volume_ratio", 1.0)
        )

        # 포지션 / 재진입
        self.max_positions = int(self.cfg.get("max_positions", 1))
        self.entry_cooldown_sec = int(self.cfg.get("entry_cooldown_sec", 30))
        self.allow_reentry = bool(self.cfg.get("allow_reentry", False))

        # 점수 필터
        self.use_score_filter = bool(self.cfg.get("use_score_filter", True))
        self.min_entry_score = float(self.cfg.get("min_entry_score", 50))

        # 세부 가중치
        self.entry_volume_ratio_min = float(self.cfg.get("entry_volume_ratio_min", 1.0))
        self.news_weight = float(self.cfg.get("news_weight", 1.0))

        # 급등 추격 제어
        self.hot_move_price_change_pct = float(self.cfg.get("hot_move_price_change_pct", 2.0))
        self.hot_move_trade_strength = float(self.cfg.get("hot_move_trade_strength", 145))
        self.max_chase_price_change_pct = float(self.cfg.get("max_chase_price_change_pct", 5.0))
        self.max_chase_volume_ratio = float(self.cfg.get("max_chase_volume_ratio", 4.0))
        self.min_news_score_for_hot_move = float(
            self.cfg.get("min_news_score_for_hot_move", 0.0)
        )

        # 보조 점수
        self.min_theme_score_for_entry = float(
            self.cfg.get("min_theme_score_for_entry", 0.0)
        )
        self.min_leader_score_for_entry = float(
            self.cfg.get("min_leader_score_for_entry", 0.0)
        )

        # 최근 틱 저장
        self.tick_history: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=30))

        # 진입/청산 시간 기록
        self.last_entry_time: Dict[str, datetime] = {}
        self.last_exit_time: Dict[str, datetime] = {}

    # --------------------------------------------------
    # 엔진 호환용 메인 진입점
    # --------------------------------------------------
    def generate_signal(self, tick: Any, portfolio=None) -> Optional[Signal]:
        """
        engine.py 에서 호출하는 표준 인터페이스
        """
        has_position = self._has_position(tick, portfolio)
        return self.on_tick(tick, has_position=has_position)

    # --------------------------------------------------
    # 외부 연동용
    # --------------------------------------------------
    def mark_exit(self, symbol: str, when: Optional[datetime] = None):
        self.last_exit_time[symbol] = when or datetime.now()

    # --------------------------------------------------
    # 내부 메인 진입 판단
    # --------------------------------------------------
    def on_tick(self, tick: Any, has_position: bool = False) -> Optional[Signal]:
        symbol = self._get_symbol(tick)
        if not symbol:
            return None

        if self.watchlist and symbol not in self.watchlist:
            return None

        now = self._get_timestamp(tick)

        # 틱 기록 먼저 저장
        self._append_tick(symbol, tick)

        # 이미 포지션 있으면 신규 진입 안 함
        if has_position:
            return None

        # 쿨다운 체크
        if self._is_in_cooldown(symbol, now):
            return None

        # 최소 히스토리 부족 시 skip
        if len(self.tick_history[symbol]) < 3:
            return None

        return self._check_entry(symbol, tick)

    # --------------------------------------------------
    # 실제 진입 체크
    # --------------------------------------------------
    def _check_entry(self, symbol: str, tick: Any) -> Optional[Signal]:
        price = self._get_price(tick)
        if price <= 0:
            return None

        price_change_pct = self._get_price_change_pct(tick)
        trade_strength = self._get_trade_strength(tick)
        volume_ratio = self._get_volume_ratio(tick, symbol)
        news_score = self._get_news_score(tick)
        theme_score = self._get_theme_score(tick)
        leader_score = self._get_leader_score(tick)

        if price_change_pct < self.min_price_change_pct:
            return None

        if trade_strength < self.min_trade_strength:
            return None

        if volume_ratio < self.volume_ratio_hard_floor:
            return None

        if volume_ratio < self.entry_volume_ratio_min:
            return None

        if theme_score < self.min_theme_score_for_entry:
            return None

        if leader_score < self.min_leader_score_for_entry:
            return None

        # 급등 추격 방지
        if price_change_pct >= self.max_chase_price_change_pct:
            if volume_ratio >= self.max_chase_volume_ratio:
                return None

        # hot move 구간 추가 필터
        if price_change_pct >= self.hot_move_price_change_pct:
            if trade_strength < self.hot_move_trade_strength:
                return None
            if news_score < self.min_news_score_for_hot_move:
                return None

        # 모멘텀 조건
        base_ok = (
            price_change_pct >= self.min_price_change_pct
            and trade_strength >= self.min_trade_strength
            and volume_ratio >= self.min_volume_ratio
        )

        strong_ok = (
            price_change_pct >= self.strong_momentum_price_change_pct
            and trade_strength >= self.strong_momentum_trade_strength
            and volume_ratio >= self.strong_momentum_volume_ratio
        )

        if not (base_ok or strong_ok):
            return None

        # 최근 흐름 체크
        if not self._is_price_flow_positive(symbol):
            return None

        score = self._calculate_entry_score(
            price_change_pct=price_change_pct,
            trade_strength=trade_strength,
            volume_ratio=volume_ratio,
            news_score=news_score,
            theme_score=theme_score,
            leader_score=leader_score,
        )

        if self.use_score_filter and score < self.min_entry_score:
            return None

        reason = (
            f"ENTRY score={score:.1f} "
            f"chg={price_change_pct:.2f}% "
            f"str={trade_strength:.1f} "
            f"vol_ratio={volume_ratio:.2f} "
            f"news={news_score:.2f} "
            f"theme={theme_score:.2f} "
            f"leader={leader_score:.2f}"
        )

        signal = self._build_buy_signal(symbol, price, reason)
        self.last_entry_time[symbol] = self._get_timestamp(tick)
        return signal

    # --------------------------------------------------
    # portfolio 보유 여부 판단
    # --------------------------------------------------
    def _has_position(self, tick: Any, portfolio) -> bool:
        if portfolio is None:
            return False

        symbol = self._get_symbol(tick)
        if not symbol:
            return False

        # dict 형태 대응
        if isinstance(portfolio, dict):
            pos = portfolio.get(symbol)
            if pos is None:
                return False

            if isinstance(pos, dict):
                qty = pos.get("qty", pos.get("quantity", 0))
                return float(qty or 0) > 0

            qty = getattr(pos, "qty", None)
            if qty is None:
                qty = getattr(pos, "quantity", 0)
            return float(qty or 0) > 0

        # positions 속성 대응
        positions = getattr(portfolio, "positions", None)
        if isinstance(positions, dict):
            pos = positions.get(symbol)
            if pos is None:
                return False

            if isinstance(pos, dict):
                qty = pos.get("qty", pos.get("quantity", 0))
                return float(qty or 0) > 0

            qty = getattr(pos, "qty", None)
            if qty is None:
                qty = getattr(pos, "quantity", 0)
            return float(qty or 0) > 0

        return False

    # --------------------------------------------------
    # 점수 계산
    # --------------------------------------------------
    def _calculate_entry_score(
        self,
        price_change_pct: float,
        trade_strength: float,
        volume_ratio: float,
        news_score: float,
        theme_score: float,
        leader_score: float,
    ) -> float:
        score = 0.0

        if price_change_pct >= 0.3:
            score += 8
        if price_change_pct >= 0.5:
            score += 8
        if price_change_pct >= 0.8:
            score += 10
        if price_change_pct >= 1.2:
            score += 10
        if price_change_pct >= 2.0:
            score += 6
        if price_change_pct >= self.max_chase_price_change_pct:
            score -= 12

        if trade_strength >= 100:
            score += 8
        if trade_strength >= 120:
            score += 10
        if trade_strength >= 140:
            score += 10
        if trade_strength >= 160:
            score += 8
        if trade_strength >= 180:
            score += 4

        if volume_ratio >= 1.0:
            score += 10
        if volume_ratio >= 1.2:
            score += 10
        if volume_ratio >= 1.5:
            score += 8
        if volume_ratio >= 2.0:
            score += 6
        if volume_ratio >= 3.5:
            score -= 4

        score += news_score * 10 * self.news_weight
        score += theme_score * 6
        score += leader_score * 6

        return score

    # --------------------------------------------------
    # 최근 가격 흐름 체크
    # --------------------------------------------------
    def _is_price_flow_positive(self, symbol: str) -> bool:
        hist = self.tick_history[symbol]
        if len(hist) < 3:
            return True

        items = list(hist)[-3:]
        prices = [x["price"] for x in items if x["price"] > 0]

        if len(prices) < 3:
            return True

        if prices[-1] < prices[-2] < prices[-3]:
            return False

        return True

    # --------------------------------------------------
    # 틱 기록
    # --------------------------------------------------
    def _append_tick(self, symbol: str, tick: Any):
        item = {
            "price": self._get_price(tick),
            "trade_volume": self._get_trade_volume(tick),
            "trade_strength": self._get_trade_strength(tick),
            "price_change_pct": self._get_price_change_pct(tick),
            "volume_ratio": self._extract_number(
                tick,
                ["volume_ratio", "vol_ratio"],
                default=None,
            ),
            "news_score": self._get_news_score(tick),
            "ts": self._get_timestamp(tick),
        }
        self.tick_history[symbol].append(item)

    # --------------------------------------------------
    # 쿨다운
    # --------------------------------------------------
    def _is_in_cooldown(self, symbol: str, now: datetime) -> bool:
        if self.allow_reentry:
            return False

        last_entry = self.last_entry_time.get(symbol)
        if last_entry and (now - last_entry).total_seconds() < self.entry_cooldown_sec:
            return True

        last_exit = self.last_exit_time.get(symbol)
        if last_exit and (now - last_exit).total_seconds() < self.entry_cooldown_sec:
            return True

        return False

    # --------------------------------------------------
    # Signal 생성
    # --------------------------------------------------
    def _build_buy_signal(self, symbol: str, price: float, reason: str) -> Signal:
        try:
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                qty=1,
                price=price,
                reason=reason,
            )
        except TypeError:
            try:
                return Signal(
                    symbol=symbol,
                    side=Side.BUY,
                    price=price,
                    reason=reason,
                )
            except TypeError:
                try:
                    return Signal(
                        symbol=symbol,
                        side=Side.BUY,
                        reason=reason,
                    )
                except TypeError:
                    return Signal(symbol=symbol, side=Side.BUY)

    # --------------------------------------------------
    # Tick 파싱
    # --------------------------------------------------
    def _get_symbol(self, tick: Any) -> str:
        value = self._extract_value(tick, ["symbol", "code", "stock_code"])
        return str(value) if value is not None else ""

    def _get_price(self, tick: Any) -> float:
        return self._extract_number(
            tick,
            ["price", "current_price", "close"],
            default=0.0,
        )

    def _get_trade_volume(self, tick: Any) -> float:
        return self._extract_number(
            tick,
            ["trade_volume", "volume", "acc_volume"],
            default=0.0,
        )

    def _get_trade_strength(self, tick: Any) -> float:
        return self._extract_number(
            tick,
            ["trade_strength", "strength", "execution_strength"],
            default=0.0,
        )

    def _get_news_score(self, tick: Any) -> float:
        return self._extract_number(tick, ["news_score"], default=0.0)

    def _get_theme_score(self, tick: Any) -> float:
        return self._extract_number(tick, ["theme_score"], default=0.0)

    def _get_leader_score(self, tick: Any) -> float:
        return self._extract_number(tick, ["leader_score"], default=0.0)

    def _get_price_change_pct(self, tick: Any) -> float:
        return self._extract_number(
            tick,
            ["price_change_pct", "change_pct", "rate"],
            default=0.0,
        )

    def _get_volume_ratio(self, tick: Any, symbol: str) -> float:
        direct = self._extract_number(
            tick,
            ["volume_ratio", "vol_ratio"],
            default=None,
        )
        if direct is not None:
            return direct

        hist = self.tick_history[symbol]
        if len(hist) < 4:
            return 0.0

        current_vol = self._get_trade_volume(tick)
        prev = [x["trade_volume"] for x in list(hist)[-4:-1] if x["trade_volume"] > 0]

        if not prev or current_vol <= 0:
            return 0.0

        avg_vol = sum(prev) / len(prev)
        if avg_vol <= 0:
            return 0.0

        return current_vol / avg_vol

    def _get_timestamp(self, tick: Any) -> datetime:
        value = self._extract_value(tick, ["ts", "timestamp", "dt"])
        if isinstance(value, datetime):
            return value
        return datetime.now()

    # --------------------------------------------------
    # 공통 유틸
    # --------------------------------------------------
    def _extract_value(self, obj: Any, names, default=None):
        if isinstance(obj, dict):
            for name in names:
                if name in obj and obj[name] is not None:
                    return obj[name]
            return default

        for name in names:
            if hasattr(obj, name):
                value = getattr(obj, name)
                if value is not None:
                    return value
        return default

    def _extract_number(self, obj: Any, names, default=0.0):
        value = self._extract_value(obj, names, default=None)
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default