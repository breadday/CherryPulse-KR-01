import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import config_live as config


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_PATH = BASE_DIR / "logs" / "trading.log"

TICK_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+\|\s+INFO\s+\|\s+\[TICK\]\s+"
    r"(?P<symbol>\S+)\s+tick_no=(?P<tick_no>\d+)\s+price=(?P<price>\d+)\s+vol=(?P<vol>-?\d+)\s+"
    r"chg=(?P<chg>-?\d+(?:\.\d+)?)\s+strength=(?P<strength>-?\d+(?:\.\d+)?)\s+"
    r"vr=(?P<vr>-?\d+(?:\.\d+)?)\s+news=(?P<news>-?\d+(?:\.\d+)?)\s+theme=(?P<theme>-?\d+(?:\.\d+)?)\s+"
    r"leader=(?P<leader>-?\d+(?:\.\d+)?)$"
)

SEMICONDUCTOR_KEYWORDS = (
    "반도체",
    "semicon",
    "semiconductor",
    "메모리",
    "fab",
    "파운드리",
)
SEMICONDUCTOR_PACKAGING_KEYWORDS = (
    "심텍",
    "패키지",
    "패키징",
    "pcb",
    "substrate",
    "기판",
)
SEMICONDUCTOR_SYMBOLS = {
    "000660",  # SK하이닉스
    "005930",  # 삼성전자
    "042700",  # 한미반도체
    "058470",  # 리노공업
    "086520",  # 에코프로비엠? (strictly not semiconductor, but keep keywords primary)
    "222800",  # 심텍
}


@dataclass
class TickRow:
    ts: str
    trade_date: str
    symbol: str
    tick_no: int
    price: int
    volume: int
    price_change_pct: float
    trade_strength: float
    volume_ratio: float
    news_score: float
    theme_score: float
    leader_score: float


@dataclass
class SimTrade:
    strategy: str
    symbol: str
    name: str
    trade_date: str
    entry_ts: str
    exit_ts: str
    entry_price: int
    exit_price: int
    qty: int
    invested_amount: int
    exit_amount: int
    pnl: int
    pnl_pct: float
    note: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="4개 전략 비교 리포트")
    parser.add_argument("--db", default=config.SQLITE_DB_PATH, help="SQLite DB 경로")
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH), help="로그 파일 경로")
    parser.add_argument("--date", help="비교할 거래일(YYYY-MM-DD). 기본값은 로그 마지막 날짜")
    parser.add_argument("--trade-amount", type=int, default=1_000_000, help="전략 1회 매수 금액")
    parser.add_argument("--fee-rate", type=float, default=0.00015, help="편도 수수료율")
    parser.add_argument("--tax-rate", type=float, default=0.0018, help="매도 세금율")
    return parser.parse_args()


def resolve_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_ticks(log_path: Path) -> list[TickRow]:
    ticks: list[TickRow] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TICK_RE.match(line.strip())
        if not m:
            continue
        ts = m.group("ts")
        ticks.append(
            TickRow(
                ts=ts,
                trade_date=ts[:10],
                symbol=m.group("symbol"),
                tick_no=int(m.group("tick_no")),
                price=int(m.group("price")),
                volume=int(m.group("vol")),
                price_change_pct=float(m.group("chg")),
                trade_strength=float(m.group("strength")),
                volume_ratio=float(m.group("vr")),
                news_score=float(m.group("news")),
                theme_score=float(m.group("theme")),
                leader_score=float(m.group("leader")),
            )
        )
    return ticks


def group_ticks_by_day_symbol(ticks: Iterable[TickRow]) -> dict[str, dict[str, list[TickRow]]]:
    out: dict[str, dict[str, list[TickRow]]] = {}
    for tick in ticks:
        out.setdefault(tick.trade_date, {}).setdefault(tick.symbol, []).append(tick)
    for day_map in out.values():
        for rows in day_map.values():
            rows.sort(key=lambda item: (item.ts, item.tick_no))
    return out


def load_symbol_names(conn: sqlite3.Connection) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in conn.execute(
        """
        SELECT symbol, name FROM condition_events
        WHERE name IS NOT NULL AND TRIM(name) <> ''
        ORDER BY created_at
        """
    ):
        names[str(row["symbol"])] = str(row["name"])
    return names


def load_snapshot_symbols(conn: sqlite3.Connection, trade_date: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT symbol
        FROM condition_events
        WHERE substr(created_at, 1, 10) = ?
          AND event_type = 'SNAPSHOT'
        ORDER BY symbol
        """,
        (trade_date,),
    ).fetchall()
    return [str(row["symbol"]) for row in rows]


def is_semiconductor(symbol: str, name: str) -> bool:
    lowered = (name or "").lower()
    if any(keyword in lowered for keyword in SEMICONDUCTOR_KEYWORDS):
        return True
    if any(keyword in lowered for keyword in SEMICONDUCTOR_PACKAGING_KEYWORDS):
        return True
    if symbol in SEMICONDUCTOR_SYMBOLS:
        return True
    return "심텍" in (name or "")


def time_to_hhmmss(ts: str) -> str:
    return ts.split(" ")[-1]


def parse_time(ts: str) -> datetime.time:
    return datetime.strptime(time_to_hhmmss(ts), "%H:%M:%S").time()


def build_trade(
    strategy: str,
    symbol: str,
    name: str,
    trade_date: str,
    entry_tick: TickRow,
    exit_tick: TickRow,
    trade_amount: int,
    note: str,
    fee_rate: float,
    tax_rate: float,
) -> SimTrade | None:
    qty = trade_amount // int(entry_tick.price)
    if qty <= 0:
        return None
    invested_amount = qty * int(entry_tick.price)
    gross_exit_amount = qty * int(exit_tick.price)
    buy_fee = round(invested_amount * fee_rate)
    sell_fee = round(gross_exit_amount * fee_rate)
    sell_tax = round(gross_exit_amount * tax_rate)
    exit_amount = gross_exit_amount - sell_fee - sell_tax
    pnl = exit_amount - invested_amount - buy_fee
    pnl_pct = (pnl / invested_amount * 100.0) if invested_amount else 0.0
    return SimTrade(
        strategy=strategy,
        symbol=symbol,
        name=name,
        trade_date=trade_date,
        entry_ts=entry_tick.ts,
        exit_ts=exit_tick.ts,
        entry_price=int(entry_tick.price),
        exit_price=int(exit_tick.price),
        qty=qty,
        invested_amount=invested_amount,
        exit_amount=exit_amount,
        pnl=pnl,
        pnl_pct=pnl_pct,
        note=note,
    )


def simulate_snapshot_next_day(
    trade_date: str,
    day_ticks: dict[str, list[TickRow]],
    snapshot_symbols: list[str],
    names: dict[str, str],
    trade_amount: int,
    fee_rate: float,
    tax_rate: float,
) -> list[SimTrade]:
    trades: list[SimTrade] = []
    for symbol in snapshot_symbols:
        ticks = day_ticks.get(symbol, [])
        if len(ticks) < 2:
            continue
        trade = build_trade(
            strategy="1. 전날검색-다음날매수",
            symbol=symbol,
            name=names.get(symbol, symbol),
            trade_date=trade_date,
            entry_tick=ticks[0],
            exit_tick=ticks[-1],
            trade_amount=trade_amount,
            note="snapshot 종목을 당일 첫 틱에 매수, 당일 마지막 관측가에 청산",
            fee_rate=fee_rate,
            tax_rate=tax_rate,
        )
        if trade:
            trades.append(trade)
    return trades


def simulate_intraday_breakout(
    trade_date: str,
    day_ticks: dict[str, list[TickRow]],
    names: dict[str, str],
    trade_amount: int,
    fee_rate: float,
    tax_rate: float,
) -> list[SimTrade]:
    trades: list[SimTrade] = []
    min_entry_time = datetime.strptime("09:05:00", "%H:%M:%S").time()
    for symbol, ticks in day_ticks.items():
        if len(ticks) < 6:
            continue
        open_price = ticks[0].price
        entry_tick: TickRow | None = None
        morning_high = max(tick.price for tick in ticks[:3])
        for idx, tick in enumerate(ticks[3:], start=3):
            if parse_time(tick.ts) < min_entry_time:
                continue
            recent_window = ticks[max(0, idx - 3):idx]
            recent_high = max(item.price for item in recent_window)
            recent_avg_volume = sum(max(0, item.volume) for item in recent_window) / max(1, len(recent_window))
            price_breakout = tick.price >= max(morning_high, recent_high)
            open_momentum = tick.price >= int(open_price * 1.003)
            volume_confirmed = tick.volume_ratio >= 0.8 or tick.volume >= int(recent_avg_volume * 0.8)
            change_confirmed = tick.price_change_pct >= 0.2
            strength_confirmed = tick.trade_strength <= 0.0 or tick.trade_strength >= 80.0
            if price_breakout and open_momentum and volume_confirmed and change_confirmed and strength_confirmed:
                entry_tick = tick
                break
        if not entry_tick:
            continue
        trade = build_trade(
            strategy="2. 당일장중-돌파매수",
            symbol=symbol,
            name=names.get(symbol, symbol),
            trade_date=trade_date,
            entry_tick=entry_tick,
            exit_tick=ticks[-1],
            trade_amount=trade_amount,
            note="09:05 이후 초반 고점 재돌파 + 시가 대비 0.3% 이상 + 거래량 확인",
            fee_rate=fee_rate,
            tax_rate=tax_rate,
        )
        if trade:
            trades.append(trade)
    return trades


def simulate_close_next_day(
    trade_date: str,
    grouped_ticks: dict[str, dict[str, list[TickRow]]],
    names: dict[str, str],
    trade_amount: int,
    fee_rate: float,
    tax_rate: float,
) -> tuple[list[SimTrade], str]:
    all_dates = sorted(grouped_ticks.keys())
    if trade_date not in grouped_ticks:
        return [], "해당 거래일 틱이 없습니다."
    try:
        next_index = all_dates.index(trade_date) + 1
        next_trade_date = all_dates[next_index]
    except (ValueError, IndexError):
        return [], "다음 거래일 로그가 아직 없어서 비교할 수 없습니다."

    trades: list[SimTrade] = []
    day_ticks = grouped_ticks[trade_date]
    next_ticks = grouped_ticks[next_trade_date]
    for symbol, ticks in day_ticks.items():
        if symbol not in next_ticks or not ticks or not next_ticks[symbol]:
            continue
        trade = build_trade(
            strategy="3. 당일종가-다음날매도",
            symbol=symbol,
            name=names.get(symbol, symbol),
            trade_date=trade_date,
            entry_tick=ticks[-1],
            exit_tick=next_ticks[symbol][0],
            trade_amount=trade_amount,
            note=f"당일 마지막 관측가 매수, 다음 거래일 첫 틱({next_trade_date}) 청산",
            fee_rate=fee_rate,
            tax_rate=tax_rate,
        )
        if trade:
            trades.append(trade)
    return trades, ""


def simulate_semiconductor_pullback(
    trade_date: str,
    day_ticks: dict[str, list[TickRow]],
    names: dict[str, str],
    trade_amount: int,
    fee_rate: float,
    tax_rate: float,
) -> list[SimTrade]:
    trades: list[SimTrade] = []
    min_entry_time = datetime.strptime("09:05:00", "%H:%M:%S").time()
    for symbol, ticks in day_ticks.items():
        name = names.get(symbol, symbol)
        if len(ticks) < 7 or not is_semiconductor(symbol, name):
            continue
        open_price = ticks[0].price
        intraday_high = open_price
        previous_tick = ticks[0]
        entry_tick: TickRow | None = None
        rally_seen = False
        for idx, tick in enumerate(ticks[1:], start=1):
            if parse_time(tick.ts) < min_entry_time:
                previous_tick = tick
                intraday_high = max(intraday_high, tick.price)
                if idx <= 8 and tick.price >= int(open_price * 1.004):
                    rally_seen = True
                continue
            intraday_high = max(intraday_high, tick.price)
            if idx <= 8 and tick.price >= int(open_price * 1.004):
                rally_seen = True
            pullback_ratio = (intraday_high - tick.price) / intraday_high if intraday_high else 0.0
            price_above_open = tick.price >= int(open_price * 0.998)
            rebound_confirmed = tick.price > previous_tick.price
            volume_confirmed = tick.volume_ratio >= 0.6 or tick.volume >= max(1, previous_tick.volume)
            change_confirmed = tick.price_change_pct >= 0.1
            strength_confirmed = tick.trade_strength <= 0.0 or tick.trade_strength >= 70.0
            if (
                rally_seen
                and 0.003 <= pullback_ratio <= 0.015
                and price_above_open
                and rebound_confirmed
                and volume_confirmed
                and change_confirmed
                and strength_confirmed
            ):
                entry_tick = tick
                break
            previous_tick = tick
        if not entry_tick:
            continue
        trade = build_trade(
            strategy="4. 반도체-눌림목매매",
            symbol=symbol,
            name=name,
            trade_date=trade_date,
            entry_tick=entry_tick,
            exit_tick=ticks[-1],
            trade_amount=trade_amount,
            note="09:05 이후 초기 상승 후 0.3~1.5% 눌림, 시가 부근 지지 + 반등 확인",
            fee_rate=fee_rate,
            tax_rate=tax_rate,
        )
        if trade:
            trades.append(trade)
    return trades


def simulate_leader_pullback(
    trade_date: str,
    day_ticks: dict[str, list[TickRow]],
    names: dict[str, str],
    trade_amount: int,
    fee_rate: float,
    tax_rate: float,
) -> list[SimTrade]:
    trades: list[SimTrade] = []
    min_entry_time = datetime.strptime("09:05:00", "%H:%M:%S").time()
    for symbol, ticks in day_ticks.items():
        if len(ticks) < 7:
            continue
        open_price = ticks[0].price
        intraday_high = open_price
        previous_tick = ticks[0]
        entry_tick: TickRow | None = None
        leader_seen = False
        for idx, tick in enumerate(ticks[1:], start=1):
            intraday_high = max(intraday_high, tick.price)
            leader_score = tick.news_score + tick.theme_score + tick.leader_score
            if (
                idx <= 10
                and (
                    tick.price >= int(open_price * 1.004)
                    or tick.volume_ratio >= 1.0
                    or leader_score >= 1.0
                )
            ):
                leader_seen = True
            if parse_time(tick.ts) < min_entry_time:
                previous_tick = tick
                continue

            pullback_ratio = (intraday_high - tick.price) / intraday_high if intraday_high else 0.0
            price_above_open = tick.price >= int(open_price * 0.998)
            rebound_confirmed = tick.price > previous_tick.price
            liquidity_confirmed = tick.volume_ratio >= 0.7 or tick.volume >= max(1, previous_tick.volume)
            momentum_confirmed = tick.price_change_pct >= 0.15
            score_confirmed = leader_score >= 0.5
            if (
                leader_seen
                and 0.003 <= pullback_ratio <= 0.02
                and price_above_open
                and rebound_confirmed
                and liquidity_confirmed
                and momentum_confirmed
                and score_confirmed
            ):
                entry_tick = tick
                break
            previous_tick = tick
        if not entry_tick:
            continue
        trade = build_trade(
            strategy="5. 주도주-눌림매매",
            symbol=symbol,
            name=names.get(symbol, symbol),
            trade_date=trade_date,
            entry_tick=entry_tick,
            exit_tick=ticks[-1],
            trade_amount=trade_amount,
            note="09:05 이후 주도 점수 확인 + 초기 상승 후 0.3~2.0% 눌림 + 반등 진입",
            fee_rate=fee_rate,
            tax_rate=tax_rate,
        )
        if trade:
            trades.append(trade)
    return trades


def summarize(trades: list[SimTrade]) -> dict[str, float | int]:
    if not trades:
        return {
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "invested_amount": 0,
            "exit_amount": 0,
            "pnl": 0,
            "avg_pnl_pct": 0.0,
            "win_rate": 0.0,
        }
    wins = sum(1 for trade in trades if trade.pnl > 0)
    losses = sum(1 for trade in trades if trade.pnl < 0)
    invested_amount = sum(trade.invested_amount for trade in trades)
    exit_amount = sum(trade.exit_amount for trade in trades)
    pnl = sum(trade.pnl for trade in trades)
    avg_pnl_pct = sum(trade.pnl_pct for trade in trades) / len(trades)
    win_rate = wins / len(trades) * 100.0
    return {
        "trade_count": len(trades),
        "wins": wins,
        "losses": losses,
        "invested_amount": invested_amount,
        "exit_amount": exit_amount,
        "pnl": pnl,
        "avg_pnl_pct": avg_pnl_pct,
        "win_rate": win_rate,
    }


def print_summary(strategy_name: str, trades: list[SimTrade], unavailable_reason: str = ""):
    print(f"\n[{strategy_name}]")
    if unavailable_reason:
        print(f"- 상태: 비교 불가")
        print(f"- 사유: {unavailable_reason}")
        return
    stats = summarize(trades)
    print(f"- 거래 수: {stats['trade_count']}")
    print(f"- 승/패: {stats['wins']}/{stats['losses']}")
    print(f"- 승률: {stats['win_rate']:.1f}%")
    print(f"- 총투입금: {stats['invested_amount']:,}원")
    print(f"- 총청산금: {stats['exit_amount']:,}원")
    print(f"- 총손익: {stats['pnl']:,}원")
    print(f"- 평균 수익률: {stats['avg_pnl_pct']:.2f}%")
    for trade in trades[:10]:
        print(
            f"  {trade.symbol}({trade.name}) | {trade.entry_ts[-8:]} {trade.entry_price:,} -> "
            f"{trade.exit_ts[-8:]} {trade.exit_price:,} | qty={trade.qty} | pnl={trade.pnl:,}원 "
            f"({trade.pnl_pct:.2f}%)"
        )
    if len(trades) > 10:
        print(f"  ... 외 {len(trades) - 10}건")


def choose_trade_date(grouped_ticks: dict[str, dict[str, list[TickRow]]], requested_date: str | None) -> str:
    if requested_date:
        return requested_date
    if not grouped_ticks:
        raise ValueError("로그에서 틱 데이터를 찾지 못했습니다.")
    return sorted(grouped_ticks.keys())[-1]


def main():
    args = parse_args()
    db_path = resolve_db_path(args.db)
    log_path = Path(args.log)

    ticks = parse_ticks(log_path)
    grouped_ticks = group_ticks_by_day_symbol(ticks)
    trade_date = choose_trade_date(grouped_ticks, args.date)

    with connect_db(db_path) as conn:
        names = load_symbol_names(conn)
        snapshot_symbols = load_snapshot_symbols(conn, trade_date)

    day_ticks = grouped_ticks.get(trade_date, {})
    strategy1 = simulate_snapshot_next_day(
        trade_date, day_ticks, snapshot_symbols, names, args.trade_amount, args.fee_rate, args.tax_rate
    )
    strategy2 = simulate_intraday_breakout(
        trade_date, day_ticks, names, args.trade_amount, args.fee_rate, args.tax_rate
    )
    strategy3, reason3 = simulate_close_next_day(
        trade_date, grouped_ticks, names, args.trade_amount, args.fee_rate, args.tax_rate
    )
    strategy4 = simulate_semiconductor_pullback(
        trade_date, day_ticks, names, args.trade_amount, args.fee_rate, args.tax_rate
    )
    strategy5 = simulate_leader_pullback(
        trade_date, day_ticks, names, args.trade_amount, args.fee_rate, args.tax_rate
    )

    print(f"비교 대상 거래일: {trade_date}")
    print(f"매수 금액 기준: {args.trade_amount:,}원")
    print("가정:")
    print(f"- 편도 수수료율 {args.fee_rate:.5f}, 매도 세금율 {args.tax_rate:.5f} 반영")
    print("- 당일 전략은 로그의 마지막 관측가 기준으로 청산")
    print("- 종가매수 전략은 다음 거래일 첫 틱이 있어야 계산 가능")

    print_summary("1. 전날검색-다음날매수", strategy1)
    print_summary("2. 당일장중-돌파매수", strategy2)
    print_summary("3. 당일종가-다음날매도", strategy3, unavailable_reason=reason3)
    print_summary("4. 반도체-눌림목매매", strategy4)
    print_summary("5. 주도주-눌림매매", strategy5)


if __name__ == "__main__":
    main()
