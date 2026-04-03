# strategy/momentum_intraday.py

from datetime import datetime, timedelta

from core.models import Signal, Side, OrderType
from utils.score_filter import calculate_score


class MomentumIntradayStrategy:
    def __init__(self, config=None):
        self.config = config or {}

        # -------------------------
        # 진입 조건
        # -------------------------
        self.min_trade_strength = self.config.get("min_trade_strength", 120)
        self.min_price_change_pct = self.config.get("min_price_change_pct", 0.5)

        # volume_ratio 정교화 반영
        self.min_volume_ratio = self.config.get("min_volume_ratio", 1.1)
        self.volume_ratio_hard_floor = self.config.get("volume_ratio_hard_floor", 0.7)

        # 일반 진입용 추가 거래량 필터
        self.entry_volume_ratio_min = self.config.get("entry_volume_ratio_min", 1.2)

        # 강한 종목은 거래량비 기준을 조금 완화
        self.strong_momentum_trade_strength = self.config.get("strong_momentum_trade_strength", 160)
        self.strong_momentum_price_change_pct = self.config.get("strong_momentum_price_change_pct", 1.2)
        self.strong_momentum_volume_ratio = self.config.get("strong_momentum_volume_ratio", 0.95)

        self.max_positions = self.config.get("max_positions", 3)

        # -------------------------
        # 점수 필터
        # -------------------------
        self.use_score_filter = self.config.get("use_score_filter", True)
        self.min_entry_score = self.config.get("min_entry_score", 40)

        # 뉴스 가중치
        self.news_weight = self.config.get("news_weight", 1.5)

        # -------------------------
        # [다음 업그레이드]
        # 추격매수 방지 / 뉴스 없는 급등 배제
        # -------------------------
        self.hot_move_price_change_pct = self.config.get("hot_move_price_change_pct", 2.5)
        self.hot_move_trade_strength = self.config.get("hot_move_trade_strength", 150)

        self.max_chase_price_change_pct = self.config.get("max_chase_price_change_pct", 4.5)
        self.max_chase_volume_ratio = self.config.get("max_chase_volume_ratio", 3.5)

        self.min_news_score_for_hot_move = self.config.get("min_news_score_for_hot_move", 3.0)
        self.min_theme_score_for_entry = self.config.get("min_theme_score_for_entry", 0.0)
        self.min_leader_score_for_entry = self.config.get("min_leader_score_for_entry", 0.0)

        # -------------------------
        # 청산 조건
        # -------------------------
        self.stop_loss_pct = self.config.get("stop_loss_pct", -2.0)
        self.take_profit_pct = self.config.get("take_profit_pct", 3.0)
        self.partial_take_profit_pct = self.config.get("partial_take_profit_pct", 2.0)
        self.partial_take_profit_ratio = self.config.get("partial_take_profit_ratio", 0.5)
        self.trailing_start_pct = self.config.get("trailing_start_pct", 1.5)
        self.trailing_gap_pct = self.config.get("trailing_gap_pct", 1.0)

        # -------------------------
        # 재진입 / 백테스트용
        # -------------------------
        self.entry_cooldown_sec = self.config.get("entry_cooldown_sec", 30)
        self.allow_reentry = self.config.get("allow_reentry", False)

        self.last_entry_time = {}

    # -------------------------
    # 내부 유틸
    # -------------------------
    def _safe_now(self, ts):
        if ts is None:
            return datetime.now()
        return ts

    def _get_active_position_count(self, portfolio):
        if portfolio is None or not hasattr(portfolio, "positions"):
            return 0

        count = 0
        for pos in portfolio.positions.values():
            if getattr(pos, "qty", 0) > 0:
                count += 1
        return count

    def _build_market_data(self, tick):
        return {
            "symbol": getattr(tick, "symbol", ""),
            "price": getattr(tick, "price", 0),
            "price_change_pct": getattr(tick, "price_change_pct", 0.0),
            "trade_strength": getattr(tick, "trade_strength", 0.0),
            "volume_ratio": getattr(tick, "volume_ratio", 1.0),
            "trade_volume": getattr(tick, "volume", getattr(tick, "trade_volume", 0)),
            "news_score": getattr(tick, "news_score", 0.0),
            "theme_score": getattr(tick, "theme_score", 0.0),
            "leader_score": getattr(tick, "leader_score", 0.0),
            "timestamp": self._safe_now(getattr(tick, "ts", None)),
        }

    def _calculate_entry_score(self, symbol, market_data):
        score_data = {
            "symbol": symbol,
            "price": market_data.get("price", 0),
            "price_change_pct": market_data.get("price_change_pct", 0.0),
            "trade_strength": market_data.get("trade_strength", 0.0),
            "volume_ratio": market_data.get("volume_ratio", 1.0),
            "trade_volume": market_data.get("trade_volume", 0),
            "news_score": market_data.get("news_score", 0.0),
            "theme_score": market_data.get("theme_score", 0.0),
            "leader_score": market_data.get("leader_score", 0.0),
            "timestamp": market_data.get("timestamp"),
        }

        base_score = calculate_score(score_data)

        # 뉴스 점수 가중 반영
        news_score = float(market_data.get("news_score", 0.0) or 0.0)
        weighted_news_bonus = news_score * (self.news_weight - 1.0)

        return round(base_score + weighted_news_bonus, 2)

    def _is_strong_momentum(self, market_data):
        trade_strength = float(market_data.get("trade_strength", 0.0) or 0.0)
        price_change_pct = float(market_data.get("price_change_pct", 0.0) or 0.0)

        return (
            trade_strength >= self.strong_momentum_trade_strength
            and price_change_pct >= self.strong_momentum_price_change_pct
        )

    def _is_hot_move(self, market_data):
        trade_strength = float(market_data.get("trade_strength", 0.0) or 0.0)
        price_change_pct = float(market_data.get("price_change_pct", 0.0) or 0.0)

        return (
            price_change_pct >= self.hot_move_price_change_pct
            or trade_strength >= self.hot_move_trade_strength
        )

    # -------------------------
    # 진입 시그널
    # -------------------------
    def generate_signal(self, tick, portfolio):
        symbol = tick.symbol

        # 이미 보유 중이면 진입 안함
        pos = portfolio.get_position(symbol)
        if pos.qty > 0:
            return None

        market_data = self._build_market_data(tick)

        ok, reason = self.can_enter(symbol, market_data, portfolio)
        if not ok:
            return None

        score = self._calculate_entry_score(symbol, market_data)

        if self.use_score_filter and score < self.min_entry_score:
            return None

        qty = 1

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=qty,
            price=0,
            order_type=OrderType.MARKET,
            reason=(
                f"momentum_entry:{reason}:"
                f"score={score}:"
                f"news={market_data.get('news_score', 0.0)}:"
                f"theme={market_data.get('theme_score', 0.0)}:"
                f"leader={market_data.get('leader_score', 0.0)}:"
                f"chg={market_data.get('price_change_pct', 0.0)}:"
                f"strength={market_data.get('trade_strength', 0.0)}:"
                f"vr={market_data.get('volume_ratio', 0.0)}"
            ),
        )

    # -------------------------
    # 진입 가능 여부 판단
    # -------------------------
    def can_enter(self, symbol, market_data, portfolio=None):
        price_change_pct = float(market_data.get("price_change_pct", 0.0) or 0.0)
        trade_strength = float(market_data.get("trade_strength", 0.0) or 0.0)
        volume_ratio = float(market_data.get("volume_ratio", 0.0) or 0.0)
        news_score = float(market_data.get("news_score", 0.0) or 0.0)
        theme_score = float(market_data.get("theme_score", 0.0) or 0.0)
        leader_score = float(market_data.get("leader_score", 0.0) or 0.0)
        now = self._safe_now(market_data.get("timestamp"))

        # 재진입 제한
        if symbol in self.last_entry_time:
            diff = now - self.last_entry_time[symbol]
            if diff < timedelta(seconds=self.entry_cooldown_sec):
                return False, "entry_cooldown"

        # 포트폴리오 최대 보유 수 제한
        if portfolio is not None:
            active_count = self._get_active_position_count(portfolio)
            if active_count >= self.max_positions:
                return False, "max_positions"

        if trade_strength < self.min_trade_strength:
            return False, "trade_strength"

        if price_change_pct < self.min_price_change_pct:
            return False, "price_change_pct"

        # 테마 / 주도 최소 기준
        if theme_score < self.min_theme_score_for_entry:
            return False, "theme_score"

        if leader_score < self.min_leader_score_for_entry:
            return False, "leader_score"

        # 너무 약한 거래량 흐름은 무조건 차단
        if volume_ratio < self.volume_ratio_hard_floor:
            return False, "volume_ratio_hard_floor"

        # 일반 진입은 entry_volume_ratio_min 이상이어야 함
        # 다만 강한 모멘텀 종목은 아래 strong_momentum 조건으로 완화
        if not self._is_strong_momentum(market_data):
            if volume_ratio < self.entry_volume_ratio_min:
                return False, "entry_volume_ratio_min"

        # 강한 모멘텀 종목은 volume_ratio 기준을 소폭 완화
        if self._is_strong_momentum(market_data):
            if volume_ratio < self.strong_momentum_volume_ratio:
                return False, "volume_ratio_strong_momentum"
        else:
            if volume_ratio < self.min_volume_ratio:
                return False, "volume_ratio"

        # -------------------------
        # [업그레이드]
        # 뉴스 없는 급등주 배제
        # -------------------------
        if self._is_hot_move(market_data):
            if news_score < self.min_news_score_for_hot_move:
                return False, "hot_move_without_news"

        # -------------------------
        # [업그레이드]
        # 과열 추격 방지
        # -------------------------
        if price_change_pct >= self.max_chase_price_change_pct:
            return False, "overheat_price_chase"

        if volume_ratio >= self.max_chase_volume_ratio and news_score <= 0:
            return False, "overheat_volume_chase"

        return True, "ok"

    def mark_entry(self, symbol, timestamp=None):
        self.last_entry_time[symbol] = timestamp or datetime.now()

    # -------------------------
    # 청산 조건 판단
    # -------------------------
    def should_exit(self, position, market_data):
        current_price = market_data.get("price")
        if not current_price or position["avg_price"] <= 0:
            return None

        avg_price = float(position["avg_price"])
        pnl_pct = ((current_price - avg_price) / avg_price) * 100.0

        highest_return_pct = float(position.get("highest_return_pct", pnl_pct))
        if pnl_pct > highest_return_pct:
            highest_return_pct = pnl_pct
            position["highest_return_pct"] = highest_return_pct

        # 손절
        if pnl_pct <= self.stop_loss_pct:
            return {
                "action": "FULL_SELL",
                "reason": "stop_loss",
                "pnl_pct": pnl_pct,
            }

        # 부분 익절
        if (not position.get("partial_taken", False)) and pnl_pct >= self.partial_take_profit_pct:
            return {
                "action": "PARTIAL_SELL",
                "reason": "partial_take_profit",
                "ratio": self.partial_take_profit_ratio,
                "pnl_pct": pnl_pct,
            }

        # 고정 익절
        if pnl_pct >= self.take_profit_pct:
            return {
                "action": "FULL_SELL",
                "reason": "take_profit",
                "pnl_pct": pnl_pct,
            }

        # 트레일링 스탑
        if highest_return_pct >= self.trailing_start_pct:
            drawdown_from_peak = highest_return_pct - pnl_pct
            if drawdown_from_peak >= self.trailing_gap_pct:
                return {
                    "action": "FULL_SELL",
                    "reason": "trailing_stop",
                    "pnl_pct": pnl_pct,
                    "peak_pct": highest_return_pct,
                }

        return None