# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import QApplication

import config_live as config
from broker.kiwoom_broker import KiwoomBroker
from utils.logger import setup_logger


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "daily"
DEFAULT_SYMBOLS = {
    "253590": "네오셈",
    "092870": "엑시콘",
    "432720": "퀄리타스반도체",
    "042700": "한미반도체",
    "089030": "테크윙",
    "222800": "심텍",
    "058470": "리노공업",
    "036810": "에프에스티",
    "036930": "주성엔지니어링",
    "084370": "유진테크",
    "240810": "원익IPS",
    "039030": "이오테크닉스",
    "067310": "하나마이크론",
    "101490": "에스앤에스텍",
    "095340": "ISC",
    "064760": "티씨케이",
    "095610": "테스",
    "281740": "레이크머티리얼즈",
    "000660": "SK하이닉스",
    "005930": "삼성전자",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="키움 OpenAPI로 일봉 데이터를 내려받아 CSV로 저장합니다.")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS.keys()),
        help="쉼표로 구분한 종목코드 목록. 기본값은 반도체 장비/소재 확장 종목군입니다.",
    )
    parser.add_argument("--count", type=int, default=300, help="종목별 조회할 일봉 개수")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="CSV 저장 폴더")
    parser.add_argument("--sleep-sec", type=float, default=0.8, help="종목 조회 사이 대기시간")
    parser.add_argument(
        "--allow-early",
        action="store_true",
        help="07:05 이전에도 강제로 실행합니다. 보통은 키움 서버 재시작 때문에 권장하지 않습니다.",
    )
    return parser.parse_args()


def clean_symbols(raw_symbols: str) -> list[str]:
    symbols = []
    for item in str(raw_symbols or "").split(","):
        symbol = item.strip()
        if symbol:
            symbols.append(symbol)
    return sorted(dict.fromkeys(symbols))


def parse_hhmm(value: str, default: str = "07:05"):
    text = str(value or default).strip() or default
    try:
        return datetime.strptime(text, "%H:%M").time()
    except Exception:
        return datetime.strptime(default, "%H:%M").time()


def should_block_early_run(allow_early: bool) -> tuple[bool, str]:
    if allow_early:
        return False, "강제 실행 옵션 사용"

    resume_hhmm = str(getattr(config, "KIWOOM_RELOGIN_RESUME_HHMM", "07:05"))
    resume_at = parse_hhmm(resume_hhmm)
    now = datetime.now().time()
    if now < resume_at:
        return True, (
            f"현재 {datetime.now().strftime('%H:%M')}입니다. "
            f"키움 서버 재시작 이후 안정 실행 권장 시각은 {resume_hhmm} 이후입니다."
        )
    return False, "OK"


def resolve_symbol_name(symbol: str, broker: KiwoomBroker) -> str:
    """기본 감시 종목은 고정 매핑을 우선 사용해 한글 깨짐을 막는다."""
    if symbol in DEFAULT_SYMBOLS:
        return DEFAULT_SYMBOLS[symbol]
    return broker.get_code_name(symbol) or symbol


def is_suspicious_daily_stub(row: dict) -> bool:
    """장전 조회 때 현재가만 들어간 가짜 일봉 행을 저장하지 않기 위한 방어."""
    try:
        open_price = abs(int(row.get("open", 0) or 0))
        high_price = abs(int(row.get("high", 0) or 0))
        low_price = abs(int(row.get("low", 0) or 0))
        close_price = abs(int(row.get("close", 0) or 0))
        volume = abs(int(row.get("volume", 0) or 0))
    except Exception:
        return False

    same_ohlc = open_price == high_price == low_price == close_price
    return same_ohlc and volume < 1_000


def write_daily_csv(path: Path, symbol: str, name: str, candles: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        [row for row in candles or [] if not is_suspicious_daily_stub(row)],
        key=lambda row: str(row.get("date", "")),
    )
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["code", "name", "date", "open", "high", "low", "close", "volume", "trade_value"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "code": symbol,
                    "name": name,
                    "date": row.get("date", ""),
                    "open": abs(int(row.get("open", 0) or 0)),
                    "high": abs(int(row.get("high", 0) or 0)),
                    "low": abs(int(row.get("low", 0) or 0)),
                    "close": abs(int(row.get("close", 0) or 0)),
                    "volume": abs(int(row.get("volume", 0) or 0)),
                    "trade_value": abs(int(row.get("trade_value", 0) or 0)),
                }
            )


def main() -> int:
    args = parse_args()
    symbols = clean_symbols(args.symbols)
    if not symbols:
        raise ValueError("조회할 종목코드가 없습니다.")

    blocked, block_reason = should_block_early_run(args.allow_early)
    if blocked:
        print(f"일봉 다운로드 중단 | {block_reason}")
        print("07:05 이후 다시 실행하거나, 정말 필요할 때만 --allow-early 옵션을 사용하세요.")
        return 2

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = BASE_DIR / output_dir

    app = QApplication(sys.argv)
    logger = setup_logger("download_daily_candles")
    broker = KiwoomBroker(logger=logger)

    try:
        logger.info(f"일봉 다운로드 시작 | symbols={symbols} count={args.count} output_dir={output_dir}")
        broker.connect()

        for idx, symbol in enumerate(symbols, start=1):
            name = resolve_symbol_name(symbol, broker)
            logger.info(f"일봉 조회 | {idx}/{len(symbols)} symbol={symbol} name={name}")
            candles = broker.get_daily_candles(symbol, count=args.count)
            safe_name = str(name or symbol).replace("/", "_").replace("\\", "_").strip()
            output_path = output_dir / f"{symbol}_{safe_name}.csv"
            write_daily_csv(output_path, symbol, name, candles)
            logger.info(f"일봉 CSV 저장 완료 | symbol={symbol} rows={len(candles)} path={output_path}")
            if idx < len(symbols):
                time.sleep(max(0.0, float(args.sleep_sec)))
    finally:
        try:
            broker.shutdown()
        except Exception:
            pass
        app.quit()

    logger.info("일봉 다운로드 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
