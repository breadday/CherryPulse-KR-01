from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional, Tuple

from core.models import Signal, Side


class MomentumIntradayStrategy:
    """
    CherryPulse-KR-01 전략 튜닝 버전 (최종본)
    """

    def __init__(self, config=None):
        self.cfg = config or {}

        self.watchlist = set(self.cfg.get("watchlist", []))

        # 기본 진입 조건
        self.min_trade_strength = float(self.cfg.get("min_trade_strength", 120))
        self.min_price_change_pct = float(self.cfg.get("min_price_change_pct", 0.3))

        # 거래량 비율 관련
        self.min_volume_ratio = float(self.cfg.get("min_volume_ratio", 1.10))
        self.volume_ratio_hard_floor = float(self.cfg.get("volume_ratio_hard_floor", 0.8))
        self.strong_momentum_trade_strength = float(
            self.cfg.get("strong_momentum_trade_strength", 140)
        )
        self.strong_momentum_price_change_pct = float(
            self.cfg.get("strong_momentum_price_change_pct", 1.0)
        )
        self.strong_momentum_volume_ratio = float(
            self.cfg.get("strong_momentum_volume_ratio", 1.25)
        )

        # 포지션 / 재진입
        self.max_positions = int(self.cfg.get("max_positions", 1))
        self.entry_cooldown_sec = int(self.cfg.get("entry_cooldown_sec", 30))
        self.allow_reentry = bool(self.cfg.get("allow_reentry", False))

        # 점수 필터
        self.use_score_filter = bool(self.cfg.get("use_score_filter", True))
        self.min_entry_score = float(self.cfg.get("min_entry_score", 62))

        # 세부 가중치
        self.entry_volume_ratio_min = float(self.cfg.get("entry_volume_ratio_min", 1.00))
        self.news_weight = float(self.cfg.get("news_weight", 1.0))

        # 급등 추격 제어
        self.hot_move_price_change_pct = float(self.cfg.get("hot_move_price_change_pct", 2.0))
        self.hot_move_trade_strength = float(self.cfg.get("hot_move_trade_strength", 145))
        self.max_chase_price_change_pct = float(self.cfg.get("max_chase_price_change_pct", 3.8))
        self.max_chase_volume_ratio = float(self.cfg.get("max_chase_volume_ratio", 3.5))
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

        # 추가 튜닝 파라미터
        self.history_size = int(self.cfg.get("history_size", 30))
        self.min_history_for_entry = int(self.cfg.get("min_history_for_entry", 5))
        self.pullback_tolerance_pct = float(self.cfg.get("pullback_tolerance_pct", 0.010))
        self.near_high_tolerance_pct = float(self.cfg.get("near_high_tolerance_pct", 0.005))
        self.max_short_term_spike_pct = float(self.cfg.get("max_short_term_spike_pct", 1.8))
        self.require_price_above_recent_avg = bool(
            self.cfg.get("require_price_above_recent_avg", True)
        )

        # 최근 틱 저장
        self.tick_history: Dict[str, Deque[dict]] = defaultdict(
            lambda: deque(maxlen=self.history_size)
        )

        # 진입/청산 시간 기록
        self.last_entry_time: Dict[str, datetime] = {}
        self.last_exit_time: Dict[str, datetime] = {}

        # ENTRY_FAIL 이유 기록
        self.last_block_reason: Dict[str, str] = {}

    def generate_signal(self, tick: Any, portfolio=None) -> Optional[Signal]:
        has_position = self._has_position(tick, portfolio)
        return self.on_tick(tick, has_position=has_position)

    def mark_exit(self, symbol: str, when: Optional[datetime] = None):
        self.last_exit_time[symbol] = when or datetime.now()

    def mark_entry(self, symbol: str, when: Optional[datetime] = None):
        self.last_entry_time[symbol] = when or datetime.now()

    def get_last_block_reason(self, symbol: str) -> str:
        return self.last_block_reason.get(symbol, "")

    def _reject(self, symbol: str, reason: str) -> Optional[Signal]:
        self.last_block_reason[symbol] = reason
        return None

    def _clear_block_reason(self, symbol: str):
        self.last_block_reason.pop(symbol, None)

    def on_tick(self, tick: Any, has_position: bool = False) -> Optional[Signal]:
        symbol = self._get_symbol(tick)
        if not symbol:
            return None

        self._clear_block_reason(symbol)

        if self.watchlist and symbol not in self.watchlist:
            return self._reject(symbol, "watchlist 제외 종목")

        now = self._get_timestamp(tick)

        self._append_tick(symbol, tick)

        if has_position:
            return self._reject(symbol, "이미 보유중")

        if self._is_in_cooldown(symbol, now):
            return self._reject(symbol, f"재진입 쿨다운 {self.entry_cooldown_sec}초 이내")

        if len(self.tick_history[symbol]) < self.min_history_for_entry:
            return self._reject(
                symbol,
                f"히스토리 부족 {len(self.tick_history[symbol])}/{self.min_history_for_entry}",
            )

        return self._check_entry(symbol, tick)

    def _check_entry(self, symbol: str, tick: Any) -> Optional[Signal]:
        price = self._get_price(tick)
        if price <= 0:
            return self._reject(symbol, f"유효하지 않은 가격 price={price}")

        price_change_pct = self._get_price_change_pct(tick)
        trade_strength = self._get_trade_strength(tick)
        volume_ratio = self._get_volume_ratio(tick, symbol)
        news_score = self._get_news_score(tick)
        theme_score = self._get_theme_score(tick)
        leader_score = self._get_leader_score(tick)

        if price_change_pct < self.min_price_change_pct:
            return self._reject(
                symbol,
                f"등락률 부족 chg={price_change_pct:.2f} < min={self.min_price_change_pct:.2f}",
            )

        if trade_strength < self.min_trade_strength:
            return self._reject(
                symbol,
                f"체결강도 부족 strength={trade_strength:.1f} < min={self.min_trade_strength:.1f}",
            )

        if volume_ratio < self.volume_ratio_hard_floor:
            return self._reject(
                symbol,
                f"거래량비율 하드플로어 미달 vr={volume_ratio:.2f} < floor={self.volume_ratio_hard_floor:.2f}",
            )

        if volume_ratio < self.entry_volume_ratio_min:
            return self._reject(
                symbol,
                f"진입 거래량비율 부족 vr={volume_ratio:.2f} < min={self.entry_volume_ratio_min:.2f}",
            )

        if theme_score < self.min_theme_score_for_entry:
            return self._reject(
                symbol,
                f"테마점수 부족 theme={theme_score:.2f} < min={self.min_theme_score_for_entry:.2f}",
            )

        if leader_score < self.min_leader_score_for_entry:
            return self._reject(
                symbol,
                f"대장주점수 부족 leader={leader_score:.2f} < min={self.min_leader_score_for_entry:.2f}",
            )

        if price_change_pct >= self.max_chase_price_change_pct:
            return self._reject(
                symbol,
                f"급등 추격 차단 chg={price_change_pct:.2f} >= max_chase={self.max_chase_price_change_pct:.2f}",
            )

        if price_change_pct >= self.hot_move_price_change_pct:
            if trade_strength < self.hot_move_trade_strength:
                return self._reject(
                    symbol,
                    f"hot_move 체결강도 부족 strength={trade_strength:.1f} < hot_min={self.hot_move_trade_strength:.1f}",
                )
            if volume_ratio < 1.3:
                return self._reject(
                    symbol,
                    f"hot_move 거래량 부족 vr={volume_ratio:.2f} < 1.30",
                )
            if news_score < self.min_news_score_for_hot_move:
                return self._reject(
                    symbol,
                    f"hot_move 뉴스점수 부족 news={news_score:.2f} < min={self.min_news_score_for_hot_move:.2f}",
                )

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
            return self._reject(
                symbol,
                "모멘텀 조건 미충족 "
                f"(base: chg>={self.min_price_change_pct:.2f}, str>={self.min_trade_strength:.1f}, vr>={self.min_volume_ratio:.2f} / "
                f"strong: chg>={self.strong_momentum_price_change_pct:.2f}, str>={self.strong_momentum_trade_strength:.1f}, vr>={self.strong_momentum_volume_ratio:.2f}) "
                f"현재(chg={price_change_pct:.2f}, str={trade_strength:.1f}, vr={volume_ratio:.2f})"
            )

        if not self._is_price_flow_positive(symbol):
            return self._reject(symbol, "최근 가격 흐름 약화(연속 하락 또는 급꺾임)")

        if not self._is_structure_healthy(symbol, price):
            return self._reject(symbol, "자리 불량(최근 평균 이탈 또는 최근 고점 대비 밀림)")

        score, detail = self._calculate_entry_score_with_detail(
            symbol=symbol,
            price=price,
            price_change_pct=price_change_pct,
            trade_strength=trade_strength,
            volume_ratio=volume_ratio,
            news_score=news_score,
            theme_score=theme_score,
            leader_score=leader_score,
        )

        if self.use_score_filter and score < self.min_entry_score:
            return self._reject(
                symbol,
                f"점수 부족 score={score:.1f} < min_entry_score={self.min_entry_score:.1f} detail={self._format_score_detail(detail)}",
            )

        reason = (
            f"ENTRY score={score:.1f} "
            f"chg={price_change_pct:.2f}% "
            f"str={trade_strength:.1f} "
            f"vol_ratio={volume_ratio:.2f} "
            f"news={news_score:.2f} "
            f"theme={theme_score:.2f} "
            f"leader={leader_score:.2f} "
            f"detail={self._format_score_detail(detail)}"
        )

        signal = self._build_buy_signal(symbol, price, reason)
        self.last_entry_time[symbol] = self._get_timestamp(tick)
        self._clear_block_reason(symbol)
        return signal

    def _has_position(self, tick: Any, portfolio) -> bool:
        if portfolio is None:
            return False

        symbol = self._get_symbol(tick)
        if not symbol:
            return False

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

        get_position = getattr(portfolio, "get_position", None)
        if callable(get_position):
            pos = get_position(symbol)
            qty = getattr(pos, "qty", 0)
            return float(qty or 0) > 0

        return False

    def _calculate_entry_score(
        self,
        symbol: str,
        price: float,
        price_change_pct: float,
        trade_strength: float,
        volume_ratio: float,
        news_score: float,
        theme_score: float,
        leader_score: float,
    ) -> float:
        score, _ = self._calculate_entry_score_with_detail(
            symbol=symbol,
            price=price,
            price_change_pct=price_change_pct,
            trade_strength=trade_strength,
            volume_ratio=volume_ratio,
            news_score=news_score,
            theme_score=theme_score,
            leader_score=leader_score,
        )
        return score

    def _calculate_entry_score_with_detail(
        self,
        symbol: str,
        price: float,
        price_change_pct: float,
        trade_strength: float,
        volume_ratio: float,
        news_score: float,
        theme_score: float,
        leader_score: float,
    ) -> Tuple[float, Dict[str, float]]:
        detail = {
            "chg": 0.0,
            "str": 0.0,
            "vol": 0.0,
            "news": 0.0,
            "theme": 0.0,
            "leader": 0.0,
            "near_high": 0.0,
            "far_mean": 0.0,
            "vertical": 0.0,
            "chase_penalty": 0.0,
        }

        if price_change_pct >= 0.3:
            detail["chg"] += 6
        if price_change_pct >= 0.6:
            detail["chg"] += 10
        if price_change_pct >= 1.0:
            detail["chg"] += 12
        if price_change_pct >= 1.5:
            detail["chg"] += 6

        if price_change_pct >= 1.8:
            detail["chg"] -= 10
        if price_change_pct >= 2.3:
            detail["chg"] -= 15
        if price_change_pct >= 3.0:
            detail["chg"] -= 10

        if price_change_pct >= self.max_chase_price_change_pct:
            detail["chase_penalty"] -= 30

        if trade_strength >= 110:
            detail["str"] += 6
        if trade_strength >= 120:
            detail["str"] += 8
        if trade_strength >= 135:
            detail["str"] += 10
        if trade_strength >= 160:
            detail["str"] += 6
        if trade_strength >= 180:
            detail["str"] -= 8
        if trade_strength >= 190:
            detail["str"] -= 4

        if volume_ratio >= 1.0:
            detail["vol"] += 6
        if volume_ratio >= 1.2:
            detail["vol"] += 10
        if volume_ratio >= 1.5:
            detail["vol"] += 10
        if volume_ratio >= 2.0:
            detail["vol"] += 6
        if volume_ratio >= 3.2:
            detail["vol"] -= 4
        if volume_ratio >= 4.0:
            detail["vol"] -= 6

        detail["news"] = news_score * 10 * self.news_weight
        detail["theme"] = theme_score * 6
        detail["leader"] = leader_score * 6

        if self._is_near_recent_high(symbol, price):
            detail["near_high"] += 2

        if self._is_too_far_from_recent_mean(symbol, price):
            detail["far_mean"] -= 10

        if self._is_short_term_vertical(symbol):
            detail["vertical"] -= 8

        score = round(sum(detail.values()), 2)
        return score, detail

    def _format_score_detail(self, detail: Dict[str, float]) -> str:
        ordered_keys = [
            "chg", "str", "vol", "news", "theme",
            "leader", "near_high", "far_mean",
            "vertical", "chase_penalty",
        ]
        parts = []
        for key in ordered_keys:
            value = float(detail.get(key, 0.0))
            if abs(value) > 0.0001:
                parts.append(f"{key}:{value:+.1f}")
        return ",".join(parts) if parts else "none"

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

        if prices[-2] > 0:
            drop_pct = (prices[-1] - prices[-2]) / prices[-2]
            if drop_pct <= -self.pullback_tolerance_pct:
                return False

        return True

    def _is_structure_healthy(self, symbol: str, price: float) -> bool:
        hist = self.tick_history[symbol]
        items = list(hist)
        prices = [x["price"] for x in items if x["price"] > 0]

        if len(prices) < 5:
            return True

        if self.require_price_above_recent_avg:
            recent = prices[-5:]
            avg_recent = sum(recent) / len(recent)
            if price < avg_recent:
                return False

        recent_high = max(prices[-7:])
        if recent_high > 0:
            dist_from_high = (recent_high - price) / recent_high
            if dist_from_high > self.pullback_tolerance_pct:
                return False

        return True

    def _is_near_recent_high(self, symbol: str, price: float) -> bool:
        hist = self.tick_history[symbol]
        prices = [x["price"] for x in hist if x["price"] > 0]
        if len(prices) < 4:
            return False

        recent_high = max(prices[-6:])
        if recent_high <= 0:
            return False

        gap = abs(recent_high - price) / recent_high
        return gap <= self.near_high_tolerance_pct

    def _is_too_far_from_recent_mean(self, symbol: str, price: float) -> bool:
        hist = self.tick_history[symbol]
        prices = [x["price"] for x in hist if x["price"] > 0]
        if len(prices) < 4:
            return False

        recent = prices[-4:]
        mean_price = sum(recent) / len(recent)
        if mean_price <= 0:
            return False

        spike_pct = ((price / mean_price) - 1.0) * 100.0
        return spike_pct >= self.max_short_term_spike_pct

    def _is_short_term_vertical(self, symbol: str) -> bool:
        hist = self.tick_history[symbol]
        prices = [x["price"] for x in hist if x["price"] > 0]
        if len(prices) < 4:
            return False

        p1, p2, p3, p4 = prices[-4:]
        return p1 < p2 < p3 < p4

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