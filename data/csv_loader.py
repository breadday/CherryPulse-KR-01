# data/csv_loader.py

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class BarData:
    code: str
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CsvDataLoader:
    DATETIME_CANDIDATES = ["datetime", "timestamp", "dt", "date_time", "일시", "체결시간"]
    DATE_CANDIDATES = ["date", "day", "일자", "날짜"]
    TIME_CANDIDATES = ["time", "hourmin", "시간"]

    OPEN_CANDIDATES = ["open", "o", "시가"]
    HIGH_CANDIDATES = ["high", "h", "고가"]
    LOW_CANDIDATES = ["low", "l", "저가"]
    CLOSE_CANDIDATES = ["close", "c", "종가", "현재가"]
    VOLUME_CANDIDATES = ["volume", "v", "vol", "거래량"]
    CODE_CANDIDATES = ["code", "symbol", "ticker", "종목코드"]

    def __init__(self, filepath: str | Path, code: Optional[str] = None):
        self.filepath = Path(filepath)
        self.default_code = code or "UNKNOWN"

    def _normalize(self, s: str) -> str:
        return str(s).strip().lower().replace(" ", "").replace("_", "")

    def _find_col(self, fieldnames: List[str], candidates: List[str]) -> Optional[str]:
        norm_map = {self._normalize(name): name for name in fieldnames}
        for candidate in candidates:
            key = self._normalize(candidate)
            if key in norm_map:
                return norm_map[key]
        return None

    def _parse_datetime(self, value: str) -> datetime:
        value = str(value).strip()
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y%m%d %H%M%S",
            "%Y%m%d %H%M",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y%m%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ValueError(f"datetime 파싱 실패: {value}")

    def _read_clean_lines(self) -> List[str]:
        if not self.filepath.exists():
            raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {self.filepath}")

        raw_lines = self.filepath.read_text(encoding="utf-8-sig", errors="ignore").splitlines()

        clean_lines: List[str] = []
        for line in raw_lines:
            stripped = line.strip()

            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if stripped.startswith("```"):
                continue

            clean_lines.append(line)

        if not clean_lines:
            raise ValueError(f"유효한 CSV 데이터가 없습니다: {self.filepath}")

        return clean_lines

    def _detect_delimiter(self, lines: List[str]) -> str:
        sample = "\n".join(lines[:5])
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except Exception:
            return ","

    def inspect(self) -> dict:
        lines = self._read_clean_lines()
        delimiter = self._detect_delimiter(lines)
        reader = csv.reader(lines, delimiter=delimiter)
        rows = list(reader)

        header = rows[0] if rows else []
        preview = rows[1:4] if len(rows) > 1 else []

        return {
            "filepath": str(self.filepath),
            "delimiter": repr(delimiter),
            "header": header,
            "preview_rows": preview,
            "line_count": len(lines),
        }

    def load_bars(self) -> List[BarData]:
        lines = self._read_clean_lines()
        delimiter = self._detect_delimiter(lines)

        reader = csv.DictReader(lines, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"CSV 헤더를 읽을 수 없습니다: {self.filepath}")

        headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
        if not headers:
            raise ValueError(f"CSV 헤더가 비어 있습니다: {self.filepath}")

        dt_col = self._find_col(headers, self.DATETIME_CANDIDATES)
        date_col = self._find_col(headers, self.DATE_CANDIDATES)
        time_col = self._find_col(headers, self.TIME_CANDIDATES)

        open_col = self._find_col(headers, self.OPEN_CANDIDATES)
        high_col = self._find_col(headers, self.HIGH_CANDIDATES)
        low_col = self._find_col(headers, self.LOW_CANDIDATES)
        close_col = self._find_col(headers, self.CLOSE_CANDIDATES)
        volume_col = self._find_col(headers, self.VOLUME_CANDIDATES)
        code_col = self._find_col(headers, self.CODE_CANDIDATES)

        missing = []
        if not dt_col and not (date_col and time_col):
            missing.append("datetime(or date+time)")
        if not open_col:
            missing.append("open")
        if not high_col:
            missing.append("high")
        if not low_col:
            missing.append("low")
        if not close_col:
            missing.append("close")
        if not volume_col:
            missing.append("volume")

        if missing:
            raise ValueError(
                f"CSV 필수 컬럼 누락: {missing}\n"
                f"현재 헤더: {headers}\n"
                f"파일: {self.filepath}"
            )

        bars: List[BarData] = []

        for row_num, row in enumerate(reader, start=2):
            try:
                if dt_col:
                    dt_value = row.get(dt_col, "")
                else:
                    dt_value = f"{row.get(date_col, '')} {row.get(time_col, '')}"

                code = self.default_code
                if code_col and row.get(code_col):
                    code = str(row.get(code_col)).strip() or self.default_code

                bar = BarData(
                    code=code,
                    dt=self._parse_datetime(dt_value),
                    open=float(str(row.get(open_col, "")).replace(",", "").strip()),
                    high=float(str(row.get(high_col, "")).replace(",", "").strip()),
                    low=float(str(row.get(low_col, "")).replace(",", "").strip()),
                    close=float(str(row.get(close_col, "")).replace(",", "").strip()),
                    volume=float(str(row.get(volume_col, "")).replace(",", "").strip()),
                )
                bars.append(bar)
            except Exception as e:
                raise ValueError(f"{self.filepath} {row_num}행 파싱 실패: {e}") from e

        if not bars:
            raise ValueError(f"파싱된 bar 데이터가 없습니다: {self.filepath}")

        bars.sort(key=lambda x: x.dt)
        return bars