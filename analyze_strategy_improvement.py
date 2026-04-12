from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import config_live as config


@dataclass
class TradeWithSignal:
    trade: sqlite3.Row
    signal: sqlite3.Row | None


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def print_section(title: str):
    print(f"\n[{title}]")


def load_recent_trades(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, trade_date, test_name, symbol, entry_time, exit_time,
               entry_price, exit_price, qty, pnl, pnl_pct, result, exit_reason
        FROM trades
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def match_trade_to_signal(conn: sqlite3.Connection, trade: sqlite3.Row) -> sqlite3.Row | None:
    if not trade["entry_time"]:
        return None
    return conn.execute(
        """
        SELECT id, created_at, symbol, reason, tick_price, price_change_pct,
               trade_strength, volume_ratio, news_score, theme_score, leader_score
        FROM signals
        WHERE allowed = 1
          AND symbol = ?
          AND created_at <= ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (trade["symbol"], trade["entry_time"]),
    ).fetchone()


def load_trade_signal_pairs(conn: sqlite3.Connection, limit: int) -> list[TradeWithSignal]:
    pairs: list[TradeWithSignal] = []
    for trade in load_recent_trades(conn, limit):
        pairs.append(TradeWithSignal(trade=trade, signal=match_trade_to_signal(conn, trade)))
    return pairs


def hourly_stats(pairs: list[TradeWithSignal]):
    stats = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "net_pct": 0.0})
    for pair in pairs:
        entry_time = pair.trade["entry_time"] or ""
        if len(entry_time) < 13:
            continue
        hour = entry_time[11:13]
        item = stats[hour]
        item["count"] += 1
        pnl = float(pair.trade["pnl"] or 0.0)
        pnl_pct = float(pair.trade["pnl_pct"] or 0.0)
        item["net_pnl"] += pnl
        item["net_pct"] += pnl_pct
        if pnl > 0:
            item["wins"] += 1
        elif pnl < 0:
            item["losses"] += 1
    return stats


def reason_stats(pairs: list[TradeWithSignal]):
    stats = defaultdict(
        lambda: {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "net_pnl": 0.0,
            "net_pct": 0.0,
            "trade_strength_sum": 0.0,
            "volume_ratio_sum": 0.0,
            "price_change_sum": 0.0,
        }
    )
    for pair in pairs:
        reason = (pair.signal["reason"] if pair.signal else "") or "UNKNOWN"
        item = stats[reason]
        item["count"] += 1
        pnl = float(pair.trade["pnl"] or 0.0)
        pnl_pct = float(pair.trade["pnl_pct"] or 0.0)
        item["net_pnl"] += pnl
        item["net_pct"] += pnl_pct
        item["trade_strength_sum"] += float((pair.signal["trade_strength"] if pair.signal else 0.0) or 0.0)
        item["volume_ratio_sum"] += float((pair.signal["volume_ratio"] if pair.signal else 0.0) or 0.0)
        item["price_change_sum"] += float((pair.signal["price_change_pct"] if pair.signal else 0.0) or 0.0)
        if pnl > 0:
            item["wins"] += 1
        elif pnl < 0:
            item["losses"] += 1
    return stats


def exit_reason_stats(pairs: list[TradeWithSignal]):
    stats = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "net_pct": 0.0})
    for pair in pairs:
        reason = (pair.trade["exit_reason"] or "").strip() or "UNKNOWN"
        item = stats[reason]
        item["count"] += 1
        pnl = float(pair.trade["pnl"] or 0.0)
        pnl_pct = float(pair.trade["pnl_pct"] or 0.0)
        item["net_pnl"] += pnl
        item["net_pct"] += pnl_pct
        if pnl > 0:
            item["wins"] += 1
        elif pnl < 0:
            item["losses"] += 1
    return stats


def print_overview(pairs: list[TradeWithSignal]):
    print_section("전체 개요")
    if not pairs:
        print("분석할 거래 데이터가 없습니다.")
        return

    total = len(pairs)
    wins = sum(1 for x in pairs if float(x.trade["pnl"] or 0.0) > 0)
    losses = sum(1 for x in pairs if float(x.trade["pnl"] or 0.0) < 0)
    flats = total - wins - losses
    net_pnl = sum(float(x.trade["pnl"] or 0.0) for x in pairs)
    avg_win = [float(x.trade["pnl_pct"] or 0.0) for x in pairs if float(x.trade["pnl"] or 0.0) > 0]
    avg_loss = [float(x.trade["pnl_pct"] or 0.0) for x in pairs if float(x.trade["pnl"] or 0.0) < 0]
    win_rate = (wins / total * 100.0) if total else 0.0
    print(f"분석 거래 수: {total}")
    print(f"승/패/보합: {wins}/{losses}/{flats}")
    print(f"승률: {win_rate:.2f}%")
    print(f"누적 손익: {net_pnl:.0f}")
    print(f"평균 익절률: {(sum(avg_win) / len(avg_win)) if avg_win else 0.0:.2f}%")
    print(f"평균 손절률: {(sum(avg_loss) / len(avg_loss)) if avg_loss else 0.0:.2f}%")


def print_hourly_analysis(pairs: list[TradeWithSignal]):
    print_section("시간대별 성과")
    stats = hourly_stats(pairs)
    if not stats:
        print("시간대 분석 가능한 데이터가 없습니다.")
        return

    ranked = []
    for hour, item in sorted(stats.items()):
        count = item["count"]
        win_rate = (item["wins"] / count * 100.0) if count else 0.0
        avg_pnl = item["net_pnl"] / count if count else 0.0
        avg_pct = item["net_pct"] / count if count else 0.0
        ranked.append((hour, item["net_pnl"], count, win_rate))
        print(
            f"{hour}시 | 거래={count} | 승률={win_rate:.2f}% | "
            f"평균손익={avg_pnl:.0f} | 평균수익률={avg_pct:.2f}% | 누적손익={item['net_pnl']:.0f}"
        )

    best = max(ranked, key=lambda x: x[1])
    worst = min(ranked, key=lambda x: x[1])
    print(f"\n좋은 시간대 후보: {best[0]}시 (누적손익 {best[1]:.0f}, 거래 {best[2]}회, 승률 {best[3]:.2f}%)")
    print(f"주의 시간대 후보: {worst[0]}시 (누적손익 {worst[1]:.0f}, 거래 {worst[2]}회, 승률 {worst[3]:.2f}%)")


def print_reason_analysis(pairs: list[TradeWithSignal]):
    print_section("진입 사유별 성과")
    stats = reason_stats(pairs)
    if not stats:
        print("진입 사유를 연결할 수 있는 데이터가 없습니다.")
        return

    ranked = sorted(stats.items(), key=lambda x: x[1]["net_pnl"], reverse=True)
    for reason, item in ranked[:10]:
        count = item["count"]
        win_rate = (item["wins"] / count * 100.0) if count else 0.0
        print(
            f"{reason} | 거래={count} | 승률={win_rate:.2f}% | 누적손익={item['net_pnl']:.0f} | "
            f"평균강도={(item['trade_strength_sum'] / count) if count else 0.0:.2f} | "
            f"평균VR={(item['volume_ratio_sum'] / count) if count else 0.0:.2f} | "
            f"평균등락률={(item['price_change_sum'] / count) if count else 0.0:.2f}"
        )


def print_exit_analysis(pairs: list[TradeWithSignal]):
    print_section("청산 사유별 성과")
    stats = exit_reason_stats(pairs)
    ranked = sorted(stats.items(), key=lambda x: x[1]["net_pnl"])
    if not ranked:
        print("청산 사유 데이터가 없습니다.")
        return

    for reason, item in ranked[:10]:
        count = item["count"]
        win_rate = (item["wins"] / count * 100.0) if count else 0.0
        avg_pct = item["net_pct"] / count if count else 0.0
        print(
            f"{reason} | 거래={count} | 승률={win_rate:.2f}% | 평균수익률={avg_pct:.2f}% | "
            f"누적손익={item['net_pnl']:.0f}"
        )


def print_condition_analysis(conn: sqlite3.Connection, condition_name: str):
    print_section(f"{condition_name} 조건 이벤트 분석")
    rows = conn.execute(
        """
        SELECT event_type, COUNT(*) AS cnt
        FROM condition_events
        WHERE condition_name = ?
        GROUP BY event_type
        ORDER BY cnt DESC
        """,
        (condition_name,),
    ).fetchall()
    if not rows:
        print("조건 이벤트 데이터가 없습니다.")
        return

    for row in rows:
        print(f"{row['event_type']}: {row['cnt']}회")

    active_rows = conn.execute(
        """
        SELECT symbol, name, first_seen_at, last_seen_at
        FROM condition_active_symbols
        WHERE condition_name = ? AND is_active = 1
        ORDER BY last_seen_at DESC
        """,
        (condition_name,),
    ).fetchall()
    print(f"\n현재 활성 종목 수: {len(active_rows)}")
    for row in active_rows[:20]:
        label = f"{row['symbol']}({row['name']})" if row["name"] else row["symbol"]
        print(f"{label} | first={row['first_seen_at']} | last={row['last_seen_at']}")


def build_recommendations(conn: sqlite3.Connection, pairs: list[TradeWithSignal], condition_name: str):
    print_section("자동 추천")
    recommendations: list[str] = []

    hour_map = hourly_stats(pairs)
    if hour_map:
        worst_hour = min(hour_map.items(), key=lambda x: x[1]["net_pnl"])
        best_hour = max(hour_map.items(), key=lambda x: x[1]["net_pnl"])
        if worst_hour[1]["count"] >= 3 and worst_hour[1]["net_pnl"] < 0:
            recommendations.append(
                f"{worst_hour[0]}시대는 누적손익이 {worst_hour[1]['net_pnl']:.0f}로 가장 약합니다. "
                f"이 시간대 신규 진입 제한을 검토해보세요."
            )
        if best_hour[1]["count"] >= 3 and best_hour[1]["net_pnl"] > 0:
            recommendations.append(
                f"{best_hour[0]}시대는 누적손익이 {best_hour[1]['net_pnl']:.0f}로 가장 좋습니다. "
                f"이 시간대는 주문 금액 확대나 진입 허용 완화를 검토할 수 있습니다."
            )

    exit_map = exit_reason_stats(pairs)
    if exit_map:
        worst_exit = min(exit_map.items(), key=lambda x: x[1]["net_pnl"])
        if worst_exit[1]["count"] >= 2 and worst_exit[1]["net_pnl"] < 0:
            recommendations.append(
                f"청산 사유 '{worst_exit[0]}'가 누적손익 {worst_exit[1]['net_pnl']:.0f}로 가장 약합니다. "
                f"손절 폭, 시간 초과 청산, 트레일링 조건을 다시 보세요."
            )

    signal_rows = conn.execute(
        """
        SELECT block_reason, COUNT(*) AS cnt
        FROM signals
        WHERE allowed = 0
        GROUP BY block_reason
        ORDER BY cnt DESC
        LIMIT 3
        """
    ).fetchall()
    if signal_rows:
        top_block = signal_rows[0]
        recommendations.append(
            f"가장 많은 주문 차단 사유는 '{top_block['block_reason']}' ({top_block['cnt']}회) 입니다. "
            f"이 필터가 너무 강한지, 혹은 오히려 필요한 방어인지 확인해보세요."
        )

    active_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM condition_active_symbols
        WHERE condition_name = ? AND is_active = 1
        """,
        (condition_name,),
    ).fetchone()[0]
    recommendations.append(
        f"{condition_name} 현재 활성 종목 수는 {active_count}개입니다. "
        f"종목 수가 너무 많으면 진입 점수 상한을 올리고, 너무 적으면 점수 기준을 완화하는 방식으로 조절할 수 있습니다."
    )

    if not recommendations:
        recommendations.append("추천을 만들 데이터가 아직 부족합니다. 거래와 조건 이벤트를 조금 더 쌓아보세요.")

    for idx, text in enumerate(recommendations, start=1):
        print(f"{idx}. {text}")


def main():
    parser = argparse.ArgumentParser(description="자동매매 수익 개선 분석 리포트")
    parser.add_argument("--db", default=config.SQLITE_DB_PATH, help="SQLite DB 경로")
    parser.add_argument("--limit", type=int, default=200, help="최근 거래 분석 개수")
    parser.add_argument("--condition-name", default="주도주_스나이퍼", help="조건식 이름")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB 파일이 없습니다: {db_path}")
        return

    conn = connect_db(str(db_path))
    try:
        pairs = load_trade_signal_pairs(conn, args.limit)
        print(f"DB: {db_path}")
        print_overview(pairs)
        print_hourly_analysis(pairs)
        print_reason_analysis(pairs)
        print_exit_analysis(pairs)
        print_condition_analysis(conn, args.condition_name)
        build_recommendations(conn, pairs, args.condition_name)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
