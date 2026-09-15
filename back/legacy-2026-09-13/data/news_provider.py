# data/news_provider.py

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from utils.news_theme_score import build_external_scores


class NewsProvider:
    """
    1차 뉴스 점수 공급기

    특징:
    - 외부 API가 없어도 안전하게 동작
    - 종목별 수동 뉴스/테마/주도주 점수 입력 가능
    - 캐시 사용
    - 실패 시 항상 0점 fallback

    현재 버전:
    - RSS 없음
    - 수동 뉴스 / 기본 데모 뉴스 사용
    """

    def __init__(self, logger=None, cache_ttl_sec: int = 60):
        self.logger = logger
        self.cache_ttl_sec = cache_ttl_sec

        # symbol -> {"ts": float, "scores": {...}}
        self._score_cache: Dict[str, Dict] = {}

        # -------------------------
        # 1차 수동 테마/주도주 매핑
        # -------------------------
        self.theme_map = {
            "005930": ["반도체", "AI", "HBM"],
            "000660": ["반도체", "AI", "HBM"],
        }

        self.leader_map = {
            "005930": ["반도체 대장", "시총상위"],
            "000660": ["HBM 대장", "강세"],
        }

        self.market_rank_map = {
            "005930": 5,
            "000660": 3,
        }

        # -------------------------
        # 1차 수동 뉴스 매핑
        # -------------------------
        self.manual_news_map = {
            "005930": [],
            "000660": [],
        }

    # -------------------------
    # 기본 뉴스 제공
    # -------------------------
    def _get_default_news_items(self, symbol: str) -> List[dict]:
        now = datetime.now()

        default_news_map = {
            "005930": [
                {
                    "title": "삼성전자, AI 반도체 수요 확대 기대",
                    "summary": "HBM 및 고성능 반도체 관련 기대감 부각",
                    "published_at": now - timedelta(hours=1),
                }
            ],
            "000660": [
                {
                    "title": "SK하이닉스, HBM 공급 확대 기대",
                    "summary": "AI 서버용 메모리 수요 증가 반영",
                    "published_at": now - timedelta(hours=2),
                }
            ],
        }

        return default_news_map.get(symbol, [])

    # -------------------------
    # 수동 뉴스 주입
    # -------------------------
    def set_manual_news(
        self,
        symbol: str,
        news_items: Optional[List[dict]] = None,
        theme_texts: Optional[List[str]] = None,
        leader_texts: Optional[List[str]] = None,
        market_rank: Optional[int] = None,
    ):
        if news_items is not None:
            self.manual_news_map[symbol] = news_items

        if theme_texts is not None:
            self.theme_map[symbol] = theme_texts

        if leader_texts is not None:
            self.leader_map[symbol] = leader_texts

        if market_rank is not None:
            self.market_rank_map[symbol] = market_rank

        self._score_cache.pop(symbol, None)

    # -------------------------
    # 캐시 조회
    # -------------------------
    def _get_cached(self, symbol: str):
        cached = self._score_cache.get(symbol)
        if not cached:
            return None

        ts = cached.get("ts", 0.0)
        if time.time() - ts > self.cache_ttl_sec:
            self._score_cache.pop(symbol, None)
            return None

        return cached.get("scores")

    def _set_cached(self, symbol: str, scores: dict):
        self._score_cache[symbol] = {
            "ts": time.time(),
            "scores": scores,
        }

    # -------------------------
    # 실점수 계산
    # -------------------------
    def _build_scores_from_manual_data(self, symbol: str) -> dict:
        news_items = self.manual_news_map.get(symbol, [])

        # 뉴스가 비어 있으면 기본 데모 뉴스 사용
        if not news_items:
            news_items = self._get_default_news_items(symbol)

        theme_texts = self.theme_map.get(symbol, [])
        leader_texts = self.leader_map.get(symbol, [])
        market_rank = self.market_rank_map.get(symbol)

        scores = build_external_scores(
            news_items=news_items,
            theme_texts=theme_texts,
            leader_texts=leader_texts,
            market_rank=market_rank,
            is_upper_limit=False,
            is_new_high=False,
        )

        if self.logger:
            self.logger.info(
                f"[NEWS_PROVIDER] symbol={symbol} "
                f"news_items={len(news_items)} "
                f"news_score={scores.get('news_score', 0.0)} "
                f"theme_score={scores.get('theme_score', 0.0)} "
                f"leader_score={scores.get('leader_score', 0.0)}"
            )

        return scores

    # -------------------------
    # 외부 공개 메서드
    # -------------------------
    def get_scores(self, symbol: str) -> dict:
        try:
            cached = self._get_cached(symbol)
            if cached is not None:
                return cached

            scores = self._build_scores_from_manual_data(symbol)
            self._set_cached(symbol, scores)
            return scores

        except Exception as e:
            if self.logger:
                self.logger.exception(f"뉴스 점수 계산 실패 | symbol={symbol} err={e}")

            return {
                "news_score": 0.0,
                "theme_score": 0.0,
                "leader_score": 0.0,
                "total_external_score": 0.0,
            }

    # -------------------------
    # 테스트용 샘플 뉴스 주입
    # -------------------------
    def seed_demo_news(self):
        now = datetime.now()

        self.set_manual_news(
            symbol="005930",
            news_items=[
                {
                    "title": "삼성전자, AI 반도체 수요 확대 기대",
                    "summary": "HBM 및 고성능 반도체 관련 기대감 부각",
                    "published_at": now - timedelta(hours=1),
                }
            ],
            theme_texts=["반도체", "AI", "HBM"],
            leader_texts=["반도체 대장", "시총상위"],
            market_rank=5,
        )

        self.set_manual_news(
            symbol="000660",
            news_items=[
                {
                    "title": "SK하이닉스, HBM 공급 확대 기대",
                    "summary": "AI 서버용 메모리 수요 증가 반영",
                    "published_at": now - timedelta(hours=2),
                }
            ],
            theme_texts=["반도체", "AI", "HBM"],
            leader_texts=["HBM 대장", "강세"],
            market_rank=3,
        )

        if self.logger:
            self.logger.info("데모 뉴스 점수 주입 완료")