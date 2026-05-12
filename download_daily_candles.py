# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from PyQt5.QtWidgets import QApplication

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
    return parser.parse_args()


def clean_symbols(raw_symbols: str) -> list[str]:
    symbols = []
    for item in str(raw_symbols or "").split(","):
        symbol = item.strip()
        if symbol:
            symbols.append(symbol)
    return sorted(dict.fromkeys(symbols))


def resolve_symbol_name(symbol: str, broker: KiwoomBroker) -> str:
    """기본 감시 종목은 고정 매핑을 우선 사용해 한글 깨짐을 막는다."""
    if symbol in DEFAULT_SYMBOLS:
        return DEFAULT_SYMBOLS[symbol]
    return broker.get_code_name(symbol) or symbol


def write_daily_csv(path: Path, symbol: str, name: str, candles: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(candles or [], key=lambda row: str(row.get("date", "")))
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
