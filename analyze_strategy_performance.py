from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import config_live as config


BASE_DIR = Path(__file__).resolve().parent


def parse_args():
    parser = argparse.ArgumentParser(description="전략별 성과 비교 리포트")
    parser.add_argument("--db", default=config.SQLITE_DB_PATH, help="SQLite DB 경로")
    parser.add_argument("--date", help="조회 날짜 (YYYY-MM-DD). 기본값은 오늘")
    parser.add_argument("--compare-date", help="비교 날짜 (YYYY-MM-DD)")
    return parser.parse_args()


def resolve_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def fetch_rows(conn: sqlite3.Connection, trade_date: str):
    return conn.execute(
        """
        SELECT
            COALESCE(strategy_name, '') AS strategy_name,
            COALESCE(selector_name, '') AS selector_name,
            COALESCE(universe_name, '') AS universe_name,
            COUNT(*) AS total_trades,
            SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
            ROUND(COALESCE(AVG(pnl_pct), 0), 4) AS avg_pnl_pct,
            ROUND(COALESCE(SUM(pnl), 0), 2) AS net_pnl,
            ROUND(COALESCE(AVG(CASE WHEN result = 'WIN' THEN pnl_pct END), 0), 4) AS avg_win_pct,
            ROUND(COALESCE(AVG(CASE WHEN result = 'LOSS' THEN pnl_pct END), 0), 4) AS avg_loss_pct
        FROM trades
        WHERE trade_date = ?
        GROUP BY strategy_name, selector_name, universe_name
        ORDER BY net_pnl DESC, total_trades DESC, strategy_name
        """,
        (trade_date,),
    ).fetchall()


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    columns = {row[1] for row in rows}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def ensure_strategy_columns(conn: sqlite3.Connection):
    targets = [
        ("signals", "strategy_name", "TEXT"),
        ("signals", "selector_name", "TEXT"),
        ("signals", "universe_name", "TEXT"),
        ("orders", "strategy_name", "TEXT"),
        ("orders", "selector_name", "TEXT"),
        ("orders", "universe_name", "TEXT"),
        ("fills", "strategy_name", "TEXT"),
        ("fills", "selector_name", "TEXT"),
        ("fills", "universe_name", "TEXT"),
        ("trades", "strategy_name", "TEXT"),
        ("trades", "selector_name", "TEXT"),
        ("trades", "universe_name", "TEXT"),
    ]
    for table_name, column_name, column_type in targets:
        ensure_column(conn, table_name, column_name, column_type)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            test_name TEXT,
            strategy_name TEXT NOT NULL,
            selector_name TEXT,
            universe_name TEXT,
            total_trades INTEGER,
            wins INTEGER,
            losses INTEGER,
            win_rate REAL,
            net_pnl REAL,
            avg_pnl_pct REAL,
            raw_payload TEXT,
            UNIQUE(trade_date, test_name, strategy_name, selector_name, universe_name)
        )
        """
    )
    conn.commit()


def fetch_signal_order_rows(conn: sqlite3.Connection, trade_date: str):
    return conn.execute(
        """
        WITH signal_stats AS (
            SELECT
                COALESCE(strategy_name, '') AS strategy_name,
                COALESCE(selector_name, '') AS selector_name,
                COALESCE(universe_name, '') AS universe_name,
                COUNT(*) AS signal_count,
                SUM(CASE WHEN allowed = 1 THEN 1 ELSE 0 END) AS allowed_signal_count
            FROM signals
            WHERE substr(created_at, 1, 10) = ?
            GROUP BY strategy_name, selector_name, universe_name
        ),
        order_stats AS (
            SELECT
                COALESCE(strategy_name, '') AS strategy_name,
                COALESCE(selector_name, '') AS selector_name,
                COALESCE(universe_name, '') AS universe_name,
                COUNT(*) AS order_count
            FROM orders
            WHERE substr(created_at, 1, 10) = ?
            GROUP BY strategy_name, selector_name, universe_name
        ),
        keys AS (
            SELECT strategy_name, selector_name, universe_name FROM signal_stats
            UNION
            SELECT strategy_name, selector_name, universe_name FROM order_stats
        )
        SELECT
            COALESCE(k.strategy_name, '') AS strategy_name,
            COALESCE(k.selector_name, '') AS selector_name,
            COALESCE(k.universe_name, '') AS universe_name,
            COALESCE(s.signal_count, 0) AS signal_count,
            COALESCE(s.allowed_signal_count, 0) AS allowed_signal_count,
            COALESCE(o.order_count, 0) AS order_count
        FROM keys k
        LEFT JOIN signal_stats s
          ON k.strategy_name = s.strategy_name
         AND k.selector_name = s.selector_name
         AND k.universe_name = s.universe_name
        LEFT JOIN order_stats o
          ON k.strategy_name = o.strategy_name
         AND k.selector_name = o.selector_name
         AND k.universe_name = o.universe_name
        ORDER BY order_count DESC, allowed_signal_count DESC, signal_count DESC
        """,
        (trade_date, trade_date),
    ).fetchall()


def fetch_exit_reason_rows(conn: sqlite3.Connection, trade_date: str):
    return conn.execute(
        """
        SELECT
            COALESCE(strategy_name, '') AS strategy_name,
            COALESCE(exit_reason, '') AS exit_reason,
            COUNT(*) AS trade_count,
            ROUND(COALESCE(SUM(pnl), 0), 2) AS net_pnl,
            ROUND(COALESCE(AVG(pnl_pct), 0), 4) AS avg_pnl_pct
        FROM trades
        WHERE trade_date = ?
        GROUP BY strategy_name, exit_reason
        ORDER BY strategy_name, trade_count DESC, net_pnl DESC
        """,
        (trade_date,),
    ).fetchall()


def fetch_active_condition_symbols(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT DISTINCT symbol
        FROM condition_active_symbols
        WHERE is_active = 1
        ORDER BY symbol
        """
    ).fetchall()


def fetch_strategy_universe_rows(conn: sqlite3.Connection, trade_date: str):
    return conn.execute(
        """
        SELECT
            strategy_name,
            universe_name,
            source_type,
            symbol,
            name
        FROM strategy_universe_symbols
        WHERE trade_date = ?
        ORDER BY strategy_name, source_type, symbol
        """,
        (trade_date,),
    ).fetchall()


def load_snapshot_symbols():
    snapshot_path = BASE_DIR / "condition_snapshot.json"
    if not snapshot_path.exists():
        return []
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("codes", [])
    return sorted(
        {
            str(row.get("symbol", "")).strip()
            for row in rows
            if isinstance(row, dict) and str(row.get("symbol", "")).strip()
        }
    )


def print_report(rows, trade_date: str):
    print(f"[전략별 성과] {trade_date}")
    if not rows:
        print("거래 데이터가 없습니다.")
        return

    for row in rows:
        total = int(row["total_trades"] or 0)
        wins = int(row["wins"] or 0)
        win_rate = (wins / total * 100.0) if total else 0.0
        strategy_name = row["strategy_name"] or "(미지정)"
        selector_name = row["selector_name"] or "(미지정)"
        universe_name = row["universe_name"] or "(미지정)"
        print(
            f"- 전략={strategy_name} | selector={selector_name} | universe={universe_name} | "
            f"trades={total} wins={wins} losses={int(row['losses'] or 0)} win_rate={win_rate:.2f}% | "
            f"net_pnl={float(row['net_pnl'] or 0):,.0f} | avg_pnl_pct={float(row['avg_pnl_pct'] or 0):.4f}% | "
            f"avg_win_pct={float(row['avg_win_pct'] or 0):.4f}% | avg_loss_pct={float(row['avg_loss_pct'] or 0):.4f}%"
        )


def print_signal_order_report(rows, trade_date: str):
    print(f"[전략별 신호/주문] {trade_date}")
    if not rows:
        print("신호/주문 데이터가 없습니다.")
        return

    for row in rows:
        print(
            f"- 전략={row['strategy_name'] or '(미지정)'} | "
            f"selector={row['selector_name'] or '(미지정)'} | "
            f"universe={row['universe_name'] or '(미지정)'} | "
            f"signals={int(row['signal_count'] or 0)} | "
            f"allowed={int(row['allowed_signal_count'] or 0)} | "
            f"orders={int(row['order_count'] or 0)}"
        )


def print_exit_reason_report(rows, trade_date: str):
    print(f"[전략별 청산 사유] {trade_date}")
    if not rows:
        print("청산 데이터가 없습니다.")
        return

    for row in rows:
        print(
            f"- 전략={row['strategy_name'] or '(미지정)'} | "
            f"exit_reason={row['exit_reason'] or '(없음)'} | "
            f"trades={int(row['trade_count'] or 0)} | "
            f"net_pnl={float(row['net_pnl'] or 0):,.0f} | "
            f"avg_pnl_pct={float(row['avg_pnl_pct'] or 0):.4f}%"
        )


def print_close_buy_next_day_report(rows, trade_date: str):
    print(f"[종가매수 익일 청산] {trade_date}")
    target_rows = [
        row for row in rows
        if (row["strategy_name"] or "") == "close_buy"
        and str(row["exit_reason"] or "").startswith("close_buy_next_day_")
    ]
    if not target_rows:
        print("종가매수 익일 청산 데이터가 없습니다.")
        return

    for row in target_rows:
        print(
            f"- 사유={row['exit_reason']} | "
            f"trades={int(row['trade_count'] or 0)} | "
            f"net_pnl={float(row['net_pnl'] or 0):,.0f} | "
            f"avg_pnl_pct={float(row['avg_pnl_pct'] or 0):.4f}%"
        )


def print_strategy_universe_config():
    print("[전략별 유니버스 설정]")
    universe_cfg = getattr(config, "STRATEGY_UNIVERSE_CONFIG", {}) or {}
    if not universe_cfg:
        print("설정된 전략 유니버스가 없습니다.")
        return

    for strategy_name, cfg in universe_cfg.items():
        cfg = cfg or {}
        print(
            f"- 전략={strategy_name} | "
            f"use_snapshot={bool(cfg.get('use_snapshot', False))} | "
            f"use_condition={bool(cfg.get('use_condition', True))}"
        )


def print_strategy_universe_status(condition_symbols, universe_rows):
    print("[전략별 유니버스 현황]")
    universe_cfg = getattr(config, "STRATEGY_UNIVERSE_CONFIG", {}) or {}
    if universe_rows:
        grouped = {}
        for row in universe_rows:
            strategy_name = str(row["strategy_name"] or "").strip()
            symbol = str(row["symbol"] or "").strip()
            if not strategy_name or not symbol:
                continue
            grouped.setdefault(strategy_name, set()).add(symbol)

        for strategy_name in sorted(grouped):
            symbols = sorted(grouped[strategy_name])
            preview = ", ".join(symbols[:8]) if symbols else "(없음)"
            print(
                f"- 전략={strategy_name} | "
                f"count={len(symbols)} | "
                f"sample={preview}"
            )
        return

    snapshot_symbols = load_snapshot_symbols()
    condition_symbols = sorted(
        {
            str(row["symbol"]).strip()
            for row in condition_symbols
            if str(row["symbol"]).strip()
        }
    )

    if not universe_cfg:
        print("전략 유니버스 설정이 없습니다.")
        return

    for strategy_name, cfg in universe_cfg.items():
        cfg = cfg or {}
        symbols = set()
        if bool(cfg.get("use_snapshot", False)):
            symbols.update(snapshot_symbols)
        if bool(cfg.get("use_condition", True)):
            symbols.update(condition_symbols)
        preview = ", ".join(sorted(symbols)[:8]) if symbols else "(없음)"
        print(
            f"- 전략={strategy_name} | "
            f"count={len(symbols)} | "
            f"sample={preview}"
        )


def build_universe_counts(universe_rows, condition_symbols):
    if universe_rows:
        grouped = {}
        for row in universe_rows:
            strategy_name = str(row["strategy_name"] or "").strip()
            symbol = str(row["symbol"] or "").strip()
            if not strategy_name or not symbol:
                continue
            grouped.setdefault(strategy_name, set()).add(symbol)
        return {strategy_name: len(symbols) for strategy_name, symbols in grouped.items()}

    universe_cfg = getattr(config, "STRATEGY_UNIVERSE_CONFIG", {}) or {}
    snapshot_symbols = load_snapshot_symbols()
    condition_symbols = sorted(
        {
            str(row["symbol"]).strip()
            for row in condition_symbols
            if str(row["symbol"]).strip()
        }
    )
    result = {}
    for strategy_name, cfg in universe_cfg.items():
        cfg = cfg or {}
        symbols = set()
        if bool(cfg.get("use_snapshot", False)):
            symbols.update(snapshot_symbols)
        if bool(cfg.get("use_condition", True)):
            symbols.update(condition_symbols)
        result[strategy_name] = len(symbols)
    return result


def print_strategy_summary_table(trade_date: str, universe_counts: dict, signal_rows, performance_rows):
    print(f"[전략별 유니버스+성과 요약] {trade_date}")
    strategy_names = set(universe_counts.keys())
    strategy_names.update(str(row["strategy_name"] or "").strip() for row in signal_rows if str(row["strategy_name"] or "").strip())
    strategy_names.update(str(row["strategy_name"] or "").strip() for row in performance_rows if str(row["strategy_name"] or "").strip())

    if not strategy_names:
        print("요약할 전략 데이터가 없습니다.")
        return

    signal_map = {}
    for row in signal_rows:
        strategy_name = str(row["strategy_name"] or "").strip()
        if not strategy_name:
            continue
        bucket = signal_map.setdefault(strategy_name, {"signals": 0, "allowed": 0, "orders": 0})
        bucket["signals"] += int(row["signal_count"] or 0)
        bucket["allowed"] += int(row["allowed_signal_count"] or 0)
        bucket["orders"] += int(row["order_count"] or 0)

    perf_map = {}
    for row in performance_rows:
        strategy_name = str(row["strategy_name"] or "").strip()
        if not strategy_name:
            continue
        bucket = perf_map.setdefault(strategy_name, {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "avg_pnl_pct": 0.0})
        bucket["trades"] += int(row["total_trades"] or 0)
        bucket["wins"] += int(row["wins"] or 0)
        bucket["losses"] += int(row["losses"] or 0)
        bucket["net_pnl"] += float(row["net_pnl"] or 0.0)
        bucket["avg_pnl_pct"] = float(row["avg_pnl_pct"] or 0.0)

    for strategy_name in sorted(strategy_names):
        signals = signal_map.get(strategy_name, {})
        perf = perf_map.get(strategy_name, {})
        print(
            f"- 전략={strategy_name} | "
            f"universe_count={int(universe_counts.get(strategy_name, 0))} | "
            f"signals={int(signals.get('signals', 0))} | "
            f"allowed={int(signals.get('allowed', 0))} | "
            f"orders={int(signals.get('orders', 0))} | "
            f"trades={int(perf.get('trades', 0))} | "
            f"wins={int(perf.get('wins', 0))} | "
            f"net_pnl={float(perf.get('net_pnl', 0.0)):,.0f} | "
            f"avg_pnl_pct={float(perf.get('avg_pnl_pct', 0.0)):.4f}%"
        )


def print_compare_report(compare_date: str, current_counts: dict, current_signal_rows, current_perf_rows, compare_counts: dict, compare_signal_rows, compare_perf_rows):
    print(f"[전략별 날짜 비교] {compare_date} -> 현재")
    strategy_names = set(current_counts.keys()) | set(compare_counts.keys())
    strategy_names.update(str(row["strategy_name"] or "").strip() for row in current_signal_rows if str(row["strategy_name"] or "").strip())
    strategy_names.update(str(row["strategy_name"] or "").strip() for row in compare_signal_rows if str(row["strategy_name"] or "").strip())
    strategy_names.update(str(row["strategy_name"] or "").strip() for row in current_perf_rows if str(row["strategy_name"] or "").strip())
    strategy_names.update(str(row["strategy_name"] or "").strip() for row in compare_perf_rows if str(row["strategy_name"] or "").strip())

    def aggregate_signal(rows):
        data = {}
        for row in rows:
            name = str(row["strategy_name"] or "").strip()
            if not name:
                continue
            bucket = data.setdefault(name, {"signals": 0, "orders": 0})
            bucket["signals"] += int(row["signal_count"] or 0)
            bucket["orders"] += int(row["order_count"] or 0)
        return data

    def aggregate_perf(rows):
        data = {}
        for row in rows:
            name = str(row["strategy_name"] or "").strip()
            if not name:
                continue
            bucket = data.setdefault(name, {"trades": 0, "net_pnl": 0.0})
            bucket["trades"] += int(row["total_trades"] or 0)
            bucket["net_pnl"] += float(row["net_pnl"] or 0.0)
        return data

    current_signal_map = aggregate_signal(current_signal_rows)
    compare_signal_map = aggregate_signal(compare_signal_rows)
    current_perf_map = aggregate_perf(current_perf_rows)
    compare_perf_map = aggregate_perf(compare_perf_rows)

    if not strategy_names:
        print("비교할 전략 데이터가 없습니다.")
        return

    for strategy_name in sorted(strategy_names):
        universe_delta = int(current_counts.get(strategy_name, 0)) - int(compare_counts.get(strategy_name, 0))
        signal_delta = int(current_signal_map.get(strategy_name, {}).get("signals", 0)) - int(compare_signal_map.get(strategy_name, {}).get("signals", 0))
        order_delta = int(current_signal_map.get(strategy_name, {}).get("orders", 0)) - int(compare_signal_map.get(strategy_name, {}).get("orders", 0))
        trade_delta = int(current_perf_map.get(strategy_name, {}).get("trades", 0)) - int(compare_perf_map.get(strategy_name, {}).get("trades", 0))
        pnl_delta = float(current_perf_map.get(strategy_name, {}).get("net_pnl", 0.0)) - float(compare_perf_map.get(strategy_name, {}).get("net_pnl", 0.0))
        print(
            f"- 전략={strategy_name} | "
            f"universe_delta={universe_delta:+d} | "
            f"signal_delta={signal_delta:+d} | "
            f"order_delta={order_delta:+d} | "
            f"trade_delta={trade_delta:+d} | "
            f"net_pnl_delta={pnl_delta:+,.0f}"
        )


def main():
    args = parse_args()
    db_path = resolve_db_path(args.db)
    trade_date = args.date or __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    compare_date = args.compare_date

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_strategy_columns(conn)
        rows = fetch_rows(conn, trade_date)
        signal_order_rows = fetch_signal_order_rows(conn, trade_date)
        exit_reason_rows = fetch_exit_reason_rows(conn, trade_date)
        active_condition_symbols = fetch_active_condition_symbols(conn)
        strategy_universe_rows = fetch_strategy_universe_rows(conn, trade_date)
        compare_rows = fetch_rows(conn, compare_date) if compare_date else []
        compare_signal_order_rows = fetch_signal_order_rows(conn, compare_date) if compare_date else []
        compare_active_condition_symbols = fetch_active_condition_symbols(conn) if compare_date else []
        compare_strategy_universe_rows = fetch_strategy_universe_rows(conn, compare_date) if compare_date else []
    finally:
        conn.close()

    universe_counts = build_universe_counts(strategy_universe_rows, active_condition_symbols)
    compare_universe_counts = build_universe_counts(compare_strategy_universe_rows, compare_active_condition_symbols) if compare_date else {}

    print_signal_order_report(signal_order_rows, trade_date)
    print()
    print_strategy_universe_config()
    print()
    print_strategy_universe_status(active_condition_symbols, strategy_universe_rows)
    print()
    print_strategy_summary_table(trade_date, universe_counts, signal_order_rows, rows)
    print()
    print_report(rows, trade_date)
    print()
    print_exit_reason_report(exit_reason_rows, trade_date)
    print()
    print_close_buy_next_day_report(exit_reason_rows, trade_date)
    if compare_date:
        print()
        print_compare_report(
            compare_date,
            universe_counts,
            signal_order_rows,
            rows,
            compare_universe_counts,
            compare_signal_order_rows,
            compare_rows,
        )


if __name__ == "__main__":
    main()
