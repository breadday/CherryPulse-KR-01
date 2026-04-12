from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

import config_live as config


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def print_section(title: str):
    print(f"\n[{title}]")


def cmd_summary(conn: sqlite3.Connection, days: int):
    print_section("일별 요약")
    rows = conn.execute(
        """
        SELECT trade_date, test_name, total_trades, wins, losses, win_rate,
               avg_profit_pct, avg_loss_pct, net_pnl, cash, realized_pnl,
               daily_order_count, max_daily_orders, engine_protected
        FROM daily_summary
        ORDER BY trade_date DESC
        LIMIT ?
        """,
        (days,),
    ).fetchall()

    if not rows:
        print("저장된 일별 요약이 없습니다.")
    else:
        for row in rows:
            print(
                f"{row['trade_date']} | 전략={row['test_name']} | 거래={row['total_trades']} | "
                f"승/패={row['wins']}/{row['losses']} | 승률={row['win_rate']:.2f}% | "
                f"순손익={row['net_pnl']:.0f} | 실현손익={row['realized_pnl'] or 0:.0f} | "
                f"주문={row['daily_order_count']}/{row['max_daily_orders']} | 보호={bool(row['engine_protected'])}"
            )

    print_section("최근 거래")
    trades = conn.execute(
        """
        SELECT trade_date, symbol, entry_time, exit_time, qty, pnl, pnl_pct, result, exit_reason
        FROM trades
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    if not trades:
        print("저장된 거래 내역이 없습니다.")
    else:
        for row in trades:
            print(
                f"{row['trade_date']} | {row['symbol']} | {row['result']} | "
                f"손익={row['pnl']:.0f} ({row['pnl_pct']:.2f}%) | 수량={row['qty']} | "
                f"청산사유={row['exit_reason']}"
            )


def cmd_hourly(conn: sqlite3.Connection):
    print_section("시간대별 성과")
    rows = conn.execute(
        """
        SELECT
            substr(entry_time, 12, 2) AS hour_slot,
            COUNT(*) AS trade_count,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses,
            AVG(pnl) AS avg_pnl,
            AVG(pnl_pct) AS avg_pnl_pct,
            SUM(pnl) AS net_pnl
        FROM trades
        WHERE entry_time IS NOT NULL AND entry_time <> ''
        GROUP BY substr(entry_time, 12, 2)
        ORDER BY hour_slot
        """
    ).fetchall()

    if not rows:
        print("시간대 분석용 거래 데이터가 없습니다.")
        return

    for row in rows:
        trade_count = row["trade_count"] or 0
        wins = row["wins"] or 0
        win_rate = (wins / trade_count * 100.0) if trade_count else 0.0
        print(
            f"{row['hour_slot']}시 | 거래={trade_count} | 승률={win_rate:.2f}% | "
            f"평균손익={row['avg_pnl'] or 0:.0f} | 평균수익률={row['avg_pnl_pct'] or 0:.2f}% | "
            f"누적손익={row['net_pnl'] or 0:.0f}"
        )

    print_section("진입 사유 상위")
    signal_rows = conn.execute(
        """
        SELECT reason, COUNT(*) AS signal_count
        FROM signals
        WHERE allowed = 1 AND reason IS NOT NULL AND reason <> ''
        GROUP BY reason
        ORDER BY signal_count DESC
        LIMIT 10
        """
    ).fetchall()

    if not signal_rows:
        print("허용된 진입 신호 기록이 없습니다.")
    else:
        for row in signal_rows:
            print(f"{row['signal_count']:>3}회 | {row['reason']}")


def cmd_condition(conn: sqlite3.Connection, condition_name: str, recent: int):
    print_section(f"{condition_name} 현재 활성 종목")
    rows = conn.execute(
        """
        SELECT symbol, name, source, first_seen_at, last_seen_at
        FROM condition_active_symbols
        WHERE condition_name = ? AND is_active = 1
        ORDER BY last_seen_at DESC, symbol
        """,
        (condition_name,),
    ).fetchall()

    if not rows:
        print("현재 활성 종목이 없습니다.")
    else:
        for row in rows:
            label = f"{row['symbol']}({row['name']})" if row["name"] else row["symbol"]
            print(
                f"{label} | source={row['source']} | "
                f"first={row['first_seen_at']} | last={row['last_seen_at']}"
            )

    print_section(f"{condition_name} 최근 이벤트")
    events = conn.execute(
        """
        SELECT created_at, symbol, name, event_type, source, condition_index
        FROM condition_events
        WHERE condition_name = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (condition_name, recent),
    ).fetchall()

    if not events:
        print("조건 이벤트 기록이 없습니다.")
    else:
        for row in events:
            label = f"{row['symbol']}({row['name']})" if row["name"] else row["symbol"]
            print(
                f"{row['created_at']} | {row['event_type']} | {label} | "
                f"source={row['source']} | index={row['condition_index']}"
            )


def cmd_signal_blocks(conn: sqlite3.Connection, limit: int):
    print_section("최근 주문 차단 사유")
    rows = conn.execute(
        """
        SELECT created_at, symbol, block_reason, price_change_pct, trade_strength, volume_ratio
        FROM signals
        WHERE allowed = 0
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    if not rows:
        print("주문 차단 기록이 없습니다.")
        return

    for row in rows:
        print(
            f"{row['created_at']} | {row['symbol']} | 차단={row['block_reason']} | "
            f"chg={row['price_change_pct']} strength={row['trade_strength']} vr={row['volume_ratio']}"
        )


def main():
    parser = argparse.ArgumentParser(description="CherryPulse SQLite 분석 도구")
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=["summary", "hourly", "condition", "blocks"],
        help="조회할 분석 종류",
    )
    parser.add_argument(
        "--db",
        default=config.SQLITE_DB_PATH,
        help="SQLite DB 경로",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=10,
        help="summary에서 보여줄 일수",
    )
    parser.add_argument(
        "--condition-name",
        default="주도주_스나이퍼",
        help="condition 조회 대상 조건식 이름",
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=20,
        help="condition/blocks 최근 건수",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB 파일이 없습니다: {db_path}")
        return

    conn = connect_db(str(db_path))
    try:
        print(f"DB: {db_path}")
        if args.command == "summary":
            cmd_summary(conn, days=args.days)
        elif args.command == "hourly":
            cmd_hourly(conn)
        elif args.command == "condition":
            cmd_condition(conn, condition_name=args.condition_name, recent=args.recent)
        elif args.command == "blocks":
            cmd_signal_blocks(conn, limit=args.recent)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
