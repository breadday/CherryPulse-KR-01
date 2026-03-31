# data/csv_loader.py    : CSV 로더 만들기

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd


@dataclass
class BarData:
    code: str
    dt: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class CsvDataLoader:
    REQUIRED_COLUMNS = ["datetime", "open", "high", "low", "close", "volume"]

    def __init__(self, filepath: str | Path, code: Optional[str] = None):
        self.filepath = Path(filepath)
        self.default_code = code or "UNKNOWN"

    def load_dataframe(self) -> pd.DataFrame:
        if not self.filepath.exists():
            raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {self.filepath}")

        df = pd.read_csv(self.filepath)

        missing = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing:
            raise ValueError(f"CSV 필수 컬럼 누락: {missing}")

        df = df.copy()
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

        if "code" not in df.columns:
            df["code"] = self.default_code

        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["datetime", "open", "high", "low", "close", "volume"])
        df = df.sort_values("datetime").reset_index(drop=True)

        return df

    def load_bars(self) -> List[BarData]:
        df = self.load_dataframe()

        bars: List[BarData] = []
        for row in df.itertuples(index=False):
            bars.append(
                BarData(
                    code=str(row.code),
                    dt=row.datetime,
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=float(row.volume),
                )
            )
        return bars