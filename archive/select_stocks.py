
# select_stocks.py

import json

def score(item):
    return (
        item["news_score"] * 0.3 +
        (item["volume"] / item["avg_volume_20d"]) * 20 +
        (item["foreign_net_buy"] + item["institution_net_buy"]) / 1e9
    )

def main():
    with open("selection_candidates.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    scored = sorted(data["candidates"], key=score, reverse=True)
    top = [x["symbol"] for x in scored[:3]]

    with open("selected_stocks.json", "w", encoding="utf-8") as f:
        json.dump({"selected_symbols": top}, f, indent=2)

    print("선정 완료:", top)

if __name__ == "__main__":
    main()
