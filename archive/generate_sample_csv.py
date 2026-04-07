# generate_sample_csv.py

from pathlib import Path
from datetime import datetime, timedelta
import random


def generate_csv(symbol: str, start_price: int):
    path = Path(f"data/sample/{symbol}_1m.csv")
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime(2026, 3, 1, 9, 0)
    price = start_price

    with open(path, "w", encoding="utf-8") as f:
        f.write("datetime,open,high,low,close,volume,code\n")

        for i in range(60):  # 60분 데이터
            open_p = price
            change = random.randint(-200, 200)
            close_p = max(1000, price + change)
            high_p = max(open_p, close_p) + random.randint(0, 50)
            low_p = min(open_p, close_p) - random.randint(0, 50)
            volume = random.randint(1000, 20000)

            f.write(
                f"{now},{open_p},{high_p},{low_p},{close_p},{volume},{symbol}\n"
            )

            price = close_p
            now += timedelta(minutes=1)


if __name__ == "__main__":
    generate_csv("005930", 70000)
    generate_csv("000660", 120000)
    generate_csv("035720", 60000)

    print("샘플 CSV 생성 완료 👍")