# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import config_live as config


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SNAPSHOT = BASE_DIR / "condition_snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="일봉 후보 snapshot 최신성을 검증합니다.")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT), help="검증할 snapshot JSON 경로")
    return parser.parse_args()


def parse_date(value: str):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except Exception:
            continue
    return None


def count_trading_days_between(start_date, end_date) -> int:
    """start_date 다음 날부터 end_date 전날까지 빠진 거래일 수를 계산합니다."""
    holidays = {
        str(day).strip()
        for day in getattr(config, "MARKET_HOLIDAYS", [])
        if str(day).strip()
    }
    count = 0
    cursor = start_date
    while True:
        cursor = cursor.fromordinal(cursor.toordinal() + 1)
        if cursor >= end_date:
            break
        if cursor.weekday() >= 5:
            continue
        if cursor.strftime("%Y-%m-%d") in holidays:
            continue
        count += 1
    return count


def validate_snapshot(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"snapshot 파일 없음: {path}"

    payload = json.loads(path.read_text(encoding="utf-8"))
    today = datetime.now().date()
    max_stale_days = int(getattr(config, "SNAPSHOT_MAX_STALE_DAYS", 1) or 1)
    max_missing_trading_days = int(getattr(config, "SNAPSHOT_MAX_MISSING_TRADING_DAYS", 0) or 0)

    generated_at = str(payload.get("generated_at", "") or "").strip()
    generated_date = parse_date(generated_at)
    if generated_date and generated_date != today:
        return False, f"생성일 불일치 generated_at={generated_at} today={today}"

    latest_date = parse_date(str(payload.get("latest_data_date", "") or "").strip())
    for item in payload.get("codes", []) or []:
        if not isinstance(item, dict):
            continue
        item_date = parse_date(str(item.get("last_date", "") or "").strip())
        if item_date and (latest_date is None or item_date > latest_date):
            latest_date = item_date

    if latest_date is None:
        return False, "후보 last_date 없음"

    calendar_days = (today - latest_date).days
    missing_trading_days = count_trading_days_between(latest_date, today)
    if missing_trading_days > max_missing_trading_days:
        return False, (
            f"전일 거래일 데이터 누락 latest_date={latest_date} today={today} "
            f"missing_trading_days={missing_trading_days}>{max_missing_trading_days} "
            f"calendar_days={calendar_days}"
        )

    # 주말이 끼면 달력일수는 3일이어도 거래일 기준으로는 정상입니다.
    trading_stale_days = missing_trading_days
    if trading_stale_days > max_stale_days:
        return False, (
            f"후보 일봉이 오래됨 latest_date={latest_date} today={today} "
            f"trading_stale_days={trading_stale_days}>{max_stale_days} "
            f"calendar_days={calendar_days}"
        )

    count = int(payload.get("count", 0) or 0)
    return True, (
        f"OK count={count} latest_date={latest_date} "
        f"calendar_days={calendar_days} missing_trading_days={missing_trading_days}"
    )


def main() -> int:
    args = parse_args()
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_absolute():
        snapshot_path = BASE_DIR / snapshot_path

    ok, message = validate_snapshot(snapshot_path)
    if not ok:
        print(f"SNAPSHOT_INVALID | {message}")
        return 1

    print(f"SNAPSHOT_OK | {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
