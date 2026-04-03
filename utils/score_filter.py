def calculate_score(price_change_pct, volume_ratio):
    score = 0

    # 상승률
    if price_change_pct > 1:
        score += 2
    elif price_change_pct > 0.5:
        score += 1

    # 거래량
    if volume_ratio > 3:
        score += 3
    elif volume_ratio > 2:
        score += 2
    elif volume_ratio > 1.5:
        score += 1

    return score