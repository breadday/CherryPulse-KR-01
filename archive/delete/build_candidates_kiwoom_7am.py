# -*- coding: utf-8 -*-
"""
build_candidates_kiwoom_7am.py

07:00 장전 실행용 후보 생성기
- 키움 로그인 후 전일 일봉(opt10081) + 투자자기관별(opt10060) 조회
- 뉴스/테마 override를 합쳐 selection_candidates.json 생성
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PyQt5.QtWidgets import QApplication

import config_live as config
from broker.kiwoom_broker import KiwoomBroker
from utils.logger import setup_logger


def sma(values):
    vals = [float(x) for x in values if x is not None]
    return sum(vals) / len(vals) if vals else 0.0


def compute_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = float(closes[i - 1]) - float(closes[i])
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def main():
    base_dir = Path(__file__).resolve().parent
    universe_path = base_dir / getattr(config, "SELECTION_UNIVERSE_FILE", "selection_universe.json")
    news_path = base_dir / getattr(config, "SELECTION_NEWS_OVERRIDES_FILE", "selection_news_overrides.json")
    output_path = base_dir / getattr(config, "SELECTION_CANDIDATES_FILE", "selection_candidates.json")

    universe = load_json(
        universe_path,
        {
            "symbols": [
                {"symbol": "005930", "name": "삼성전자"},
                {"symbol": "000660", "name": "SK하이닉스"},
                {"symbol": "035420", "name": "NAVER"},
            ]
        },
    )
    news_overrides = load_json(news_path, {"overrides": {}}).get("overrides", {})

    app = QApplication(sys.argv)
    logger = setup_logger("build_candidates_kiwoom_7am")
    broker = KiwoomBroker(logger=logger)
    broker.connect()

    results = []
    target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    for item in universe.get("symbols", []):
        symbol = str(item.get("symbol", "")).strip()
        name = str(item.get("name", "")).strip()
        if not symbol:
            continue

        logger.info(f"후보 생성 시작 | symbol={symbol} name={name}")

        try:
            candles = broker.get_daily_candles(symbol=symbol, count=20, base_date=target_date)
            if len(candles) < 5:
                logger.warning(f"일봉 데이터 부족 | symbol={symbol} count={len(candles)}")
                continue

            latest = candles[0]
            closes = [x["close"] for x in candles[:20]]
            highs_5 = [x["high"] for x in candles[:5]]
            volumes_20 = [x["volume"] for x in candles[:20]]

            ma5 = sma(closes[:5])
            ma20 = sma(closes[:20])
            avg_volume_20d = sma(volumes_20)
            prev_high_5d = max(highs_5) if highs_5 else latest["high"]
            rsi = compute_rsi(closes, period=14)

            investor = broker.get_investor_flow(symbol=symbol, date_yyyymmdd=latest["date"])
            override = news_overrides.get(symbol, {})

            results.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "close": latest["close"],
                    "prev_high_5d": prev_high_5d,
                    "volume": latest["volume"],
                    "avg_volume_20d": avg_volume_20d,
                    "trade_value": latest["trade_value"],
                    "foreign_net_buy": investor.get("foreign", 0),
                    "institution_net_buy": investor.get("institution", 0),
                    "ma5": round(ma5, 2),
                    "ma20": round(ma20, 2),
                    "rsi": round(rsi, 2),
                    "news_count_7d": int(override.get("news_count_7d", 0)),
                    "news_count_prev_7d": int(override.get("news_count_prev_7d", 0)),
                    "theme_hot_score": float(override.get("theme_hot_score", 0)),
                    "search_trend_score": float(override.get("search_trend_score", 0)),
                }
            )

            logger.info(
                f"후보 생성 완료 | symbol={symbol} close={latest['close']} trade_value={latest['trade_value']} "
                f"foreign={investor.get('foreign', 0)} institution={investor.get('institution', 0)}"
            )
        except Exception as e:
            logger.exception(f"후보 생성 실패 | symbol={symbol} err={e}")

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "as_of": target_date,
        "candidates": results,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"selection_candidates 저장 완료 | path={output_path} count={len(results)}")

    try:
        broker.shutdown()
    except Exception:
        pass

    app.quit()


if __name__ == "__main__":
    main()
