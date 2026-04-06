# -*- coding: utf-8 -*-
"""
select_stocks_7am.py
- 장전 7시 선정기
- 체결강도는 장전 사용 불가 → 중립값 50
- 상위 점수 3개 종목을 selected_stocks.json 저장
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import config_live as config


def safe_float(v, default=0.0):
    try:
        if v in ("", None):
            return default
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default


def clamp(v, low=0.0, high=100.0):
    return max(low, min(high, v))


def volume_score(item):
    volume = safe_float(item.get("volume", 0))
    avg20 = safe_float(item.get("avg_volume_20d", 0))
    if avg20 <= 0:
        return 0.0
    return clamp((volume / avg20) * 50.0)


def strength_score():
    return 50.0


def supply_score(item):
    foreign_buy = safe_float(item.get("foreign_net_buy", 0))
    inst_buy = safe_float(item.get("institution_net_buy", 0))
    total_buy = foreign_buy + inst_buy
    normalized = clamp((total_buy / 3_000_000_000) * 10.0)
    bonus = 20.0 if foreign_buy > 0 and inst_buy > 0 else 0.0
    return clamp(normalized + bonus)


def technical_score(item):
    close = safe_float(item.get("close", 0))
    prev_high = safe_float(item.get("prev_high_5d", 0))
    ma5 = safe_float(item.get("ma5", 0))
    ma20 = safe_float(item.get("ma20", 0))
    rsi = safe_float(item.get("rsi", 50))

    score = 0.0
    reasons = []

    if prev_high > 0:
        drawdown = ((close - prev_high) / prev_high) * 100.0
        if -8.0 <= drawdown <= -3.0:
            score += 50.0
            reasons.append("눌림목구간")
        elif -3.0 < drawdown <= -1.0:
            score += 20.0
            reasons.append("고점근접")
        elif drawdown < -8.0:
            score += 10.0
            reasons.append("과도한하락")

    if ma5 > ma20:
        score += 25.0
        reasons.append("5일선상향")

    if 40.0 <= rsi <= 60.0:
        score += 25.0
        reasons.append("RSI중립강세")

    return clamp(score), reasons


def theme_score(item):
    hot = safe_float(item.get("theme_hot_score", 0))
    search = safe_float(item.get("search_trend_score", 0))
    news_now = safe_float(item.get("news_count_7d", 0))
    news_prev = safe_float(item.get("news_count_prev_7d", 0))

    news_growth = 0.0
    if news_prev <= 0 and news_now > 0:
        news_growth = 100.0
    elif news_prev > 0:
        news_growth = ((news_now - news_prev) / news_prev) * 100.0

    news_score = clamp(news_growth)
    return clamp((hot * 0.5) + (search * 0.2) + (news_score * 0.3))


def passes(item):
    reasons = []

    if safe_float(item.get("trade_value", 0)) < 50_000_000_000:
        reasons.append("거래대금부족")

    ma5 = safe_float(item.get("ma5", 0))
    ma20 = safe_float(item.get("ma20", 0))
    if ma5 <= ma20:
        reasons.append("추세약함")

    rsi = safe_float(item.get("rsi", 50))
    if not (40 <= rsi <= 60):
        reasons.append("RSI범위이탈")

    close = safe_float(item.get("close", 0))
    prev_high = safe_float(item.get("prev_high_5d", 0))
    if prev_high > 0 and close > 0:
        drawdown = ((close - prev_high) / prev_high) * 100.0
        if not (-8.0 <= drawdown <= -3.0):
            reasons.append("눌림목범위이탈")

    return len(reasons) == 0, reasons


def score_item(item):
    v = volume_score(item)
    s = strength_score()
    su = supply_score(item)
    t, tech_reasons = technical_score(item)
    th = theme_score(item)
    total = (v * 0.25) + (s * 0.20) + (su * 0.20) + (t * 0.15) + (th * 0.20)
    ok, fail_reasons = passes(item)

    return {
        "symbol": str(item.get("symbol", "")).strip(),
        "name": str(item.get("name", "")).strip(),
        "score_total": round(total, 2),
        "volume_score": round(v, 2),
        "strength_score": round(s, 2),
        "supply_score": round(su, 2),
        "technical_score": round(t, 2),
        "theme_score": round(th, 2),
        "technical_reasons": tech_reasons,
        "passed_hard_filters": ok,
        "fail_reasons": fail_reasons,
        "raw": item,
    }


def main():
    parser = argparse.ArgumentParser(description="오전 7시 종목 선정기")
    parser.add_argument("--input", type=str, default=getattr(config, "SELECTION_CANDIDATES_FILE", "selection_candidates.json"))
    parser.add_argument("--output", type=str, default=getattr(config, "SELECTED_STOCKS_FILE", "selected_stocks.json"))
    parser.add_argument("--top-n", type=int, default=getattr(config, "SELECTION_TOP_N", 3))
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    input_path = (base_dir / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    output_path = (base_dir / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates", [])

    scored = [score_item(x) for x in candidates]
    passed = [x for x in scored if x["passed_hard_filters"]]
    pool = passed if passed else scored
    pool.sort(key=lambda x: (x["score_total"], x["theme_score"], x["supply_score"]), reverse=True)

    selected = pool[: args.top_n]
    selected_symbols = [x["symbol"] for x in selected if x.get("symbol")]

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "selection_mode": "7am_real_data",
        "selected_symbols": selected_symbols,
        "selected_items": selected,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print("오전 7시 종목 선정 완료")
    print(f"input : {input_path}")
    print(f"output: {output_path}")
    print(f"selected_symbols: {', '.join(selected_symbols)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
