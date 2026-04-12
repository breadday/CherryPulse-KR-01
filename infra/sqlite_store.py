from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable


class SQLiteStore:
    def __init__(self, db_path: str | Path, logger=None):
        self.db_path = Path(db_path)
        self.logger = logger
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    test_name TEXT,
                    strategy_name TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty INTEGER NOT NULL,
                    reason TEXT,
                    allowed INTEGER NOT NULL,
                    block_reason TEXT,
                    signal_price REAL,
                    tick_price REAL,
                    price_change_pct REAL,
                    trade_strength REAL,
                    volume_ratio REAL,
                    news_score REAL,
                    theme_score REAL,
                    leader_score REAL,
                    raw_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    test_name TEXT,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty INTEGER NOT NULL,
                    price REAL,
                    order_type TEXT,
                    status TEXT,
                    reason TEXT,
                    request_price REAL,
                    raw_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    test_name TEXT,
                    order_id TEXT,
                    local_order_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    fill_qty INTEGER NOT NULL,
                    fill_price REAL NOT NULL,
                    unfilled_qty INTEGER,
                    realized_delta REAL,
                    cash_after REAL,
                    realized_pnl_after REAL,
                    raw_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    test_name TEXT,
                    symbol TEXT NOT NULL,
                    entry_time TEXT,
                    exit_time TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    qty INTEGER,
                    pnl REAL,
                    pnl_pct REAL,
                    result TEXT,
                    exit_reason TEXT,
                    raw_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    test_name TEXT,
                    total_trades INTEGER,
                    wins INTEGER,
                    losses INTEGER,
                    win_rate REAL,
                    avg_profit_pct REAL,
                    avg_loss_pct REAL,
                    net_pnl REAL,
                    cash REAL,
                    realized_pnl REAL,
                    daily_order_count INTEGER,
                    max_daily_orders INTEGER,
                    engine_protected INTEGER,
                    raw_payload TEXT,
                    UNIQUE(trade_date, test_name)
                );

                CREATE TABLE IF NOT EXISTS condition_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    condition_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    event_type TEXT NOT NULL,
                    condition_index INTEGER,
                    source TEXT,
                    raw_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS condition_active_symbols (
                    condition_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    source TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    PRIMARY KEY (condition_name, symbol)
                );
                """
            )

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _json(self, payload) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            return "{}"

    def record_signal(self, *, test_name: str, strategy_name: str, signal, tick, allowed: bool, block_reason: str = ""):
        payload = {
            "signal": {
                "symbol": getattr(signal, "symbol", ""),
                "side": str(getattr(signal, "side", "")),
                "qty": getattr(signal, "qty", 0),
                "reason": getattr(signal, "reason", ""),
                "price": getattr(signal, "price", None),
            },
            "tick": {
                "price": getattr(tick, "price", None),
                "price_change_pct": getattr(tick, "price_change_pct", None),
                "trade_strength": getattr(tick, "trade_strength", None),
                "volume_ratio": getattr(tick, "volume_ratio", None),
                "news_score": getattr(tick, "news_score", None),
                "theme_score": getattr(tick, "theme_score", None),
                "leader_score": getattr(tick, "leader_score", None),
            },
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO signals (
                    created_at, test_name, strategy_name, symbol, side, qty, reason,
                    allowed, block_reason, signal_price, tick_price, price_change_pct,
                    trade_strength, volume_ratio, news_score, theme_score, leader_score,
                    raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._now(),
                    test_name,
                    strategy_name,
                    getattr(signal, "symbol", ""),
                    str(getattr(signal, "side", "")),
                    int(getattr(signal, "qty", 0) or 0),
                    getattr(signal, "reason", ""),
                    1 if allowed else 0,
                    block_reason,
                    getattr(signal, "price", None),
                    getattr(tick, "price", None),
                    getattr(tick, "price_change_pct", None),
                    getattr(tick, "trade_strength", None),
                    getattr(tick, "volume_ratio", None),
                    getattr(tick, "news_score", None),
                    getattr(tick, "theme_score", None),
                    getattr(tick, "leader_score", None),
                    self._json(payload),
                ),
            )

    def record_order(self, *, test_name: str, order, request_price=None):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    created_at, test_name, order_id, symbol, side, qty, price,
                    order_type, status, reason, request_price, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._now(),
                    test_name,
                    getattr(order, "order_id", ""),
                    getattr(order, "symbol", ""),
                    str(getattr(order, "side", "")),
                    int(getattr(order, "qty", 0) or 0),
                    getattr(order, "price", None),
                    str(getattr(order, "order_type", "")),
                    str(getattr(order, "status", "")),
                    getattr(order, "reason", ""),
                    request_price,
                    self._json({
                        "filled_qty": getattr(order, "filled_qty", None),
                        "avg_fill_price": getattr(order, "avg_fill_price", None),
                    }),
                ),
            )

    def record_fill(
        self,
        *,
        test_name: str,
        fill,
        local_order_id: str | None,
        unfilled_qty=None,
        realized_delta=None,
        cash_after=None,
        realized_pnl_after=None,
    ):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fills (
                    created_at, test_name, order_id, local_order_id, symbol, side,
                    fill_qty, fill_price, unfilled_qty, realized_delta, cash_after,
                    realized_pnl_after, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._now(),
                    test_name,
                    getattr(fill, "order_id", ""),
                    local_order_id,
                    getattr(fill, "symbol", ""),
                    str(getattr(fill, "side", "")),
                    int(getattr(fill, "fill_qty", 0) or 0),
                    float(getattr(fill, "fill_price", 0.0) or 0.0),
                    unfilled_qty,
                    realized_delta,
                    cash_after,
                    realized_pnl_after,
                    self._json({
                        "ts": getattr(fill, "ts", None),
                    }),
                ),
            )

    def record_trade(self, *, test_name: str, trade_item: dict):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trades (
                    created_at, trade_date, test_name, symbol, entry_time, exit_time,
                    entry_price, exit_price, qty, pnl, pnl_pct, result, exit_reason, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._now(),
                    datetime.now().strftime("%Y-%m-%d"),
                    test_name,
                    trade_item.get("symbol", ""),
                    trade_item.get("entry_time", ""),
                    trade_item.get("exit_time", ""),
                    trade_item.get("entry_price", 0.0),
                    trade_item.get("exit_price", 0.0),
                    trade_item.get("qty", 0),
                    trade_item.get("pnl", 0.0),
                    trade_item.get("pnl_pct", 0.0),
                    trade_item.get("result", ""),
                    trade_item.get("exit_reason", ""),
                    self._json(trade_item),
                ),
            )

    def upsert_daily_summary(
        self,
        *,
        test_name: str,
        summary: dict,
        cash=None,
        realized_pnl=None,
        daily_order_count=None,
        max_daily_orders=None,
        engine_protected: bool = False,
    ):
        trade_date = datetime.now().strftime("%Y-%m-%d")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_summary (
                    created_at, trade_date, test_name, total_trades, wins, losses,
                    win_rate, avg_profit_pct, avg_loss_pct, net_pnl, cash, realized_pnl,
                    daily_order_count, max_daily_orders, engine_protected, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, test_name) DO UPDATE SET
                    created_at=excluded.created_at,
                    total_trades=excluded.total_trades,
                    wins=excluded.wins,
                    losses=excluded.losses,
                    win_rate=excluded.win_rate,
                    avg_profit_pct=excluded.avg_profit_pct,
                    avg_loss_pct=excluded.avg_loss_pct,
                    net_pnl=excluded.net_pnl,
                    cash=excluded.cash,
                    realized_pnl=excluded.realized_pnl,
                    daily_order_count=excluded.daily_order_count,
                    max_daily_orders=excluded.max_daily_orders,
                    engine_protected=excluded.engine_protected,
                    raw_payload=excluded.raw_payload
                """,
                (
                    self._now(),
                    trade_date,
                    test_name,
                    summary.get("total_trades", 0),
                    summary.get("wins", 0),
                    summary.get("losses", 0),
                    summary.get("win_rate", 0.0),
                    summary.get("avg_profit_pct", 0.0),
                    summary.get("avg_loss_pct", 0.0),
                    summary.get("net_pnl", 0.0),
                    cash,
                    realized_pnl,
                    daily_order_count,
                    max_daily_orders,
                    1 if engine_protected else 0,
                    self._json(summary),
                ),
            )

    def replace_condition_snapshot(self, *, condition_name: str, rows: Iterable[dict], source: str):
        now = self._now()
        clean_rows = []
        for row in rows:
            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue
            clean_rows.append(
                {
                    "symbol": symbol,
                    "name": str(row.get("name", "")).strip(),
                }
            )

        with self._connect() as conn:
            conn.execute(
                "UPDATE condition_active_symbols SET is_active=0, last_seen_at=? WHERE condition_name=?",
                (now, condition_name),
            )
            for row in clean_rows:
                conn.execute(
                    """
                    INSERT INTO condition_active_symbols (
                        condition_name, symbol, name, source, first_seen_at, last_seen_at, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(condition_name, symbol) DO UPDATE SET
                        name=excluded.name,
                        source=excluded.source,
                        last_seen_at=excluded.last_seen_at,
                        is_active=1
                    """,
                    (
                        condition_name,
                        row["symbol"],
                        row["name"],
                        source,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO condition_events (
                        created_at, condition_name, symbol, name, event_type, condition_index, source, raw_payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now,
                        condition_name,
                        row["symbol"],
                        row["name"],
                        "SNAPSHOT",
                        None,
                        source,
                        self._json(row),
                    ),
                )

    def record_condition_event(
        self,
        *,
        condition_name: str,
        symbol: str,
        name: str,
        event_type: str,
        condition_index=None,
        source: str = "realtime",
    ):
        now = self._now()
        symbol = str(symbol).strip()
        if not symbol:
            return

        is_active = 1 if event_type.upper() in {"I", "IN", "ENTER", "SNAPSHOT", "INITIAL"} else 0

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO condition_events (
                    created_at, condition_name, symbol, name, event_type, condition_index, source, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    condition_name,
                    symbol,
                    name,
                    event_type,
                    condition_index,
                    source,
                    self._json({"symbol": symbol, "name": name}),
                ),
            )
            conn.execute(
                """
                INSERT INTO condition_active_symbols (
                    condition_name, symbol, name, source, first_seen_at, last_seen_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(condition_name, symbol) DO UPDATE SET
                    name=excluded.name,
                    source=excluded.source,
                    last_seen_at=excluded.last_seen_at,
                    is_active=excluded.is_active
                """,
                (
                    condition_name,
                    symbol,
                    name,
                    source,
                    now,
                    now,
                    is_active,
                ),
            )

