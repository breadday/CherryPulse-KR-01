# utils/score_filter.py

def calculate_score(data):
    """
    통합 점수 계산
    data 예시:
    {
        "symbol": "005930",
        "price": 70500,
        "price_change_pct": 1.2,
        "trade_strength": 145,
        "volume_ratio": 2.3,
        "trade_volume": 1000000,
        "news_score": 8.0,
        "theme_score": 6.0,
        "leader_score": 4.0,
    }
    """
    price_change_pct = float(data.get("price_change_pct", 0.0) or 0.0)
    trade_strength = float(data.get("trade_strength", 0.0) or 0.0)
    volume_ratio = float(data.get("volume_ratio", 0.0) or 0.0)
    trade_volume = float(data.get("trade_volume", 0.0) or 0.0)

    news_score = float(data.get("news_score", 0.0) or 0.0)
    theme_score = float(data.get("theme_score", 0.0) or 0.0)
    leader_score = float(data.get("leader_score", 0.0) or 0.0)

    score = 0.0

    # -------------------------
    # 가격 상승률
    # -------------------------
    if price_change_pct >= 0:
        score += min(price_change_pct * 8.0, 20.0)
    else:
        score += max(price_change_pct * 5.0, -10.0)

    # -------------------------
    # 체결강도
    # -------------------------
    if trade_strength >= 100:
        score += min((trade_strength - 100) * 0.25, 20.0)
    else:
        score -= min((100 - trade_strength) * 0.1, 10.0)

    # -------------------------
    # 거래량 비율
    # -------------------------
    if volume_ratio >= 1.0:
        score += min((volume_ratio - 1.0) * 10.0, 15.0)

    # -------------------------
    # 거래량 절대값 (가벼운 가산)
    # -------------------------
    if trade_volume >= 5_000_000:
        score += 10.0
    elif trade_volume >= 1_000_000:
        score += 6.0
    elif trade_volume >= 300_000:
        score += 3.0

    # -------------------------
    # 외부 점수
    # -------------------------
    score += news_score
    score += theme_score
    score += leader_score

    return round(score, 2)