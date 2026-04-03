# utils/news_theme_score.py

from datetime import datetime, timedelta


POSITIVE_NEWS_KEYWORDS = [
    "수주", "계약", "실적개선", "호실적", "흑자전환", "증설", "신사업", "파트너십",
    "MOU", "승인", "허가", "특허", "양산", "공급", "투자유치", "매출증가",
    "영업이익증가", "상향", "돌파", "최대실적", "신기록", "성장", "급등",
]

NEGATIVE_NEWS_KEYWORDS = [
    "적자", "적자전환", "하향", "실적부진", "감소", "소송", "리콜", "중단",
    "악재", "유상증자", "전환사채", "CB", "BW", "횡령", "배임", "상장폐지",
    "급락", "불성실", "정지", "지연", "철회",
]

HOT_THEMES = [
    "반도체", "AI", "인공지능", "로봇", "2차전지", "바이오", "제약", "HBM",
    "전력", "원전", "방산", "자율주행", "우주항공", "양자", "데이터센터",
]

LEADER_KEYWORDS = [
    "대장", "주도", "상한가", "신고가", "거래대금상위", "시총상위", "강세",
]


def _normalize_text(text):
    if text is None:
        return ""
    return str(text).strip().lower()


def _count_keyword_score(text, positive_keywords, negative_keywords, positive_unit=3, negative_unit=3):
    raw = _normalize_text(text)
    if not raw:
        return 0.0

    score = 0.0

    for kw in positive_keywords:
        if kw.lower() in raw:
            score += positive_unit

    for kw in negative_keywords:
        if kw.lower() in raw:
            score -= negative_unit

    return score


def score_news_items(news_items):
    """
    news_items 예시:
    [
        {
            "title": "삼성전자, HBM 공급 확대 기대",
            "summary": "AI 반도체 수요 증가...",
            "published_at": datetime(...)
        }
    ]
    """
    if not news_items:
        return 0.0

    total_score = 0.0
    now = datetime.now()

    for item in news_items:
        title = item.get("title", "")
        summary = item.get("summary", "")
        published_at = item.get("published_at")

        base_text = f"{title} {summary}".strip()
        score = _count_keyword_score(
            base_text,
            POSITIVE_NEWS_KEYWORDS,
            NEGATIVE_NEWS_KEYWORDS,
            positive_unit=4,
            negative_unit=4,
        )

        # 최근 뉴스일수록 가중치
        recency_weight = 1.0
        if isinstance(published_at, datetime):
            age = now - published_at
            if age <= timedelta(hours=3):
                recency_weight = 1.5
            elif age <= timedelta(hours=12):
                recency_weight = 1.3
            elif age <= timedelta(days=1):
                recency_weight = 1.1
            else:
                recency_weight = 0.8

        total_score += score * recency_weight

    # 과도한 점수 제한
    return round(max(min(total_score, 30.0), -30.0), 2)


def score_theme(theme_texts):
    """
    theme_texts 예시:
    ["AI 반도체", "HBM", "반도체"]
    """
    if not theme_texts:
        return 0.0

    if isinstance(theme_texts, str):
        theme_texts = [theme_texts]

    joined = " ".join(str(x) for x in theme_texts if x is not None)
    joined = _normalize_text(joined)

    if not joined:
        return 0.0

    score = 0.0
    hit_count = 0

    for theme in HOT_THEMES:
        if theme.lower() in joined:
            score += 4.0
            hit_count += 1

    # 여러 강한 테마가 중첩되면 추가점
    if hit_count >= 2:
        score += 3.0
    if hit_count >= 3:
        score += 3.0

    return round(min(score, 20.0), 2)


def score_leader_status(leader_texts=None, market_rank=None, is_upper_limit=False, is_new_high=False):
    """
    leader_texts 예시:
    ["반도체 대장", "거래대금상위"]
    market_rank:
        거래대금/상승률 등 자체 랭크 숫자 (1이 가장 강함)
    """
    score = 0.0

    if leader_texts:
        if isinstance(leader_texts, str):
            leader_texts = [leader_texts]

        joined = " ".join(str(x) for x in leader_texts if x is not None)
        joined = _normalize_text(joined)

        for kw in LEADER_KEYWORDS:
            if kw.lower() in joined:
                score += 3.0

    if market_rank is not None:
        try:
            rank = int(market_rank)
            if rank <= 3:
                score += 10.0
            elif rank <= 10:
                score += 6.0
            elif rank <= 20:
                score += 3.0
        except Exception:
            pass

    if is_upper_limit:
        score += 8.0

    if is_new_high:
        score += 5.0

    return round(min(score, 20.0), 2)


def build_external_scores(
    news_items=None,
    theme_texts=None,
    leader_texts=None,
    market_rank=None,
    is_upper_limit=False,
    is_new_high=False,
):
    news_score = score_news_items(news_items or [])
    theme_score = score_theme(theme_texts or [])
    leader_score = score_leader_status(
        leader_texts=leader_texts or [],
        market_rank=market_rank,
        is_upper_limit=is_upper_limit,
        is_new_high=is_new_high,
    )

    total_external_score = round(news_score + theme_score + leader_score, 2)

    return {
        "news_score": news_score,
        "theme_score": theme_score,
        "leader_score": leader_score,
        "total_external_score": total_external_score,
    }