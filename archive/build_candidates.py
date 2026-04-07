
# build_candidates.py
# 전일 데이터 + 뉴스 기반 후보 생성

import json
from datetime import datetime

def generate_mock_data():
    # 실제로는 API / CSV로 교체
    return [
        {
            "symbol": "005930",
            "name": "삼성전자",
            "close": 70000,
            "prev_high_5d": 74000,
            "volume": 12000000,
            "avg_volume_20d": 6000000,
            "trade_value": 800000000000,
            "foreign_net_buy": 12000000000,
            "institution_net_buy": 8000000000,
            "ma5": 70500,
            "ma20": 69000,
            "rsi": 52,
            "news_score": 80,
        },
        {
            "symbol": "000660",
            "name": "SK하이닉스",
            "close": 188000,
            "prev_high_5d": 200000,
            "volume": 5000000,
            "avg_volume_20d": 3000000,
            "trade_value": 900000000000,
            "foreign_net_buy": 20000000000,
            "institution_net_buy": 9000000000,
            "ma5": 189000,
            "ma20": 180000,
            "rsi": 50,
            "news_score": 85,
        }
    ]

def main():
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "candidates": generate_mock_data()
    }

    with open("selection_candidates.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("후보 데이터 생성 완료")

if __name__ == "__main__":
    main()
