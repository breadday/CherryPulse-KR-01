import csv
import sys
from pathlib import Path
from datetime import datetime


def parse_float(v, default=0.0):
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default


def parse_dt(v):
    try:
        return datetime.strptime(str(v).strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def load_rows(csv_path: Path):
    rows = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry_dt = parse_dt(row.get("entry_time", ""))
            exit_dt = parse_dt(row.get("exit_time", ""))
            holding_minutes = None
            if entry_dt and exit_dt:
                holding_minutes = round((exit_dt - entry_dt).total_seconds() / 60.0, 2)

            rows.append({
                "symbol": str(row.get("symbol", "")).strip(),
                "entry_time": row.get("entry_time", ""),
                "exit_time": row.get("exit_time", ""),
                "entry_price": parse_float(row.get("entry_price", 0)),
                "exit_price": parse_float(row.get("exit_price", 0)),
                "qty": int(parse_float(row.get("qty", 0))),
                "pnl": parse_float(row.get("pnl", 0)),
                "pnl_pct": parse_float(row.get("pnl_pct", 0)),
                "result": str(row.get("result", "")).strip().upper(),
                "exit_reason": str(row.get("exit_reason", "")).strip(),
                "holding_minutes": holding_minutes,
                "entry_dt": entry_dt,
                "exit_dt": exit_dt,
            })
    return rows


def find_latest_trade_csv(log_dir: Path) -> Path:
    files = sorted(log_dir.glob("trades_*.csv"))
    if not files:
        raise FileNotFoundError(f"거래 CSV가 없습니다: {log_dir}")
    return files[-1]


def build_summary(rows):
    total = len(rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    losses = sum(1 for r in rows if r["result"] == "LOSS")
    flats = sum(1 for r in rows if r["result"] == "FLAT")

    win_rate = round((wins / total) * 100, 2) if total else 0.0

    profits = [r["pnl_pct"] for r in rows if r["pnl_pct"] > 0]
    losses_pct = [r["pnl_pct"] for r in rows if r["pnl_pct"] < 0]
    gross_profit = round(sum(r["pnl"] for r in rows if r["pnl"] > 0), 2)
    gross_loss = round(sum(r["pnl"] for r in rows if r["pnl"] < 0), 2)
    net_pnl = round(sum(r["pnl"] for r in rows), 2)
    expectancy = round(sum(r["pnl_pct"] for r in rows) / total, 4) if total else 0.0

    holding_values = [r["holding_minutes"] for r in rows if r["holding_minutes"] is not None]
    avg_holding = round(sum(holding_values) / len(holding_values), 2) if holding_values else 0.0

    best_trade = max(rows, key=lambda x: x["pnl_pct"]) if rows else None
    worst_trade = min(rows, key=lambda x: x["pnl_pct"]) if rows else None

    profit_factor = 0.0
    if gross_loss < 0:
        profit_factor = round(abs(gross_profit / gross_loss), 4)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate_pct": win_rate,
        "avg_profit_pct": round(sum(profits) / len(profits), 4) if profits else 0.0,
        "avg_loss_pct": round(sum(losses_pct) / len(losses_pct), 4) if losses_pct else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor,
        "expectancy_pct": expectancy,
        "avg_holding_minutes": avg_holding,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
    }


def aggregate_by_symbol(rows):
    grouped = {}
    for r in rows:
        s = r["symbol"] or "UNKNOWN"
        grouped.setdefault(s, []).append(r)

    out = []
    for symbol, items in grouped.items():
        total = len(items)
        wins = sum(1 for x in items if x["result"] == "WIN")
        losses = sum(1 for x in items if x["result"] == "LOSS")
        pos = [x["pnl_pct"] for x in items if x["pnl_pct"] > 0]
        neg = [x["pnl_pct"] for x in items if x["pnl_pct"] < 0]
        hold = [x["holding_minutes"] for x in items if x["holding_minutes"] is not None]

        out.append({
            "symbol": symbol,
            "trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round((wins / total) * 100, 2) if total else 0.0,
            "net_pnl": round(sum(x["pnl"] for x in items), 2),
            "avg_pnl_pct": round(sum(x["pnl_pct"] for x in items) / total, 4) if total else 0.0,
            "avg_profit_pct": round(sum(pos) / len(pos), 4) if pos else 0.0,
            "avg_loss_pct": round(sum(neg) / len(neg), 4) if neg else 0.0,
            "avg_holding_minutes": round(sum(hold) / len(hold), 2) if hold else 0.0,
        })

    out.sort(key=lambda x: (x["net_pnl"], x["win_rate_pct"], x["trades"]), reverse=True)
    return out


def aggregate_by_exit_reason(rows):
    grouped = {}
    for r in rows:
        reason = r["exit_reason"] or "UNKNOWN"
        grouped.setdefault(reason, []).append(r)

    out = []
    for reason, items in grouped.items():
        total = len(items)
        wins = sum(1 for x in items if x["result"] == "WIN")
        out.append({
            "exit_reason": reason,
            "trades": total,
            "wins": wins,
            "win_rate_pct": round((wins / total) * 100, 2) if total else 0.0,
            "net_pnl": round(sum(x["pnl"] for x in items), 2),
            "avg_pnl_pct": round(sum(x["pnl_pct"] for x in items) / total, 4) if total else 0.0,
        })

    out.sort(key=lambda x: (x["trades"], x["net_pnl"]), reverse=True)
    return out


def aggregate_by_entry_hour(rows):
    grouped = {}
    for r in rows:
        if r["entry_dt"] is None:
            continue
        hour = r["entry_dt"].hour
        grouped.setdefault(hour, []).append(r)

    out = []
    for hour, items in sorted(grouped.items(), key=lambda x: x[0]):
        total = len(items)
        wins = sum(1 for x in items if x["result"] == "WIN")
        out.append({
            "entry_hour": hour,
            "trades": total,
            "wins": wins,
            "win_rate_pct": round((wins / total) * 100, 2) if total else 0.0,
            "net_pnl": round(sum(x["pnl"] for x in items), 2),
            "avg_pnl_pct": round(sum(x["pnl_pct"] for x in items) / total, 4) if total else 0.0,
        })
    return out


def write_csv(path: Path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary_txt(path: Path, source_csv: Path, summary: dict):
    lines = [
        "=== 거래 성과 요약 ===",
        f"원본 CSV: {source_csv}",
        f"총 거래수: {summary['total_trades']}",
        f"승: {summary['wins']}",
        f"패: {summary['losses']}",
        f"보합: {summary['flats']}",
        f"승률(%): {summary['win_rate_pct']}",
        f"평균 수익률(%): {summary['avg_profit_pct']}",
        f"평균 손실률(%): {summary['avg_loss_pct']}",
        f"기대값(%): {summary['expectancy_pct']}",
        f"총 손익(원): {summary['net_pnl']}",
        f"Gross Profit: {summary['gross_profit']}",
        f"Gross Loss: {summary['gross_loss']}",
        f"Profit Factor: {summary['profit_factor']}",
        f"평균 보유시간(분): {summary['avg_holding_minutes']}",
    ]

    if summary["best_trade"]:
        bt = summary["best_trade"]
        lines.append(f"최고 거래: {bt['symbol']} / {bt['pnl_pct']}% / {bt['pnl']}원")
    if summary["worst_trade"]:
        wt = summary["worst_trade"]
        lines.append(f"최저 거래: {wt['symbol']} / {wt['pnl_pct']}% / {wt['pnl']}원")

    path.write_text("\n".join(lines), encoding="utf-8-sig")


def main():
    project_root = Path(__file__).resolve().parent
    log_dir = project_root / "logs"

    if len(sys.argv) >= 2:
        csv_path = Path(sys.argv[1]).resolve()
    else:
        csv_path = find_latest_trade_csv(log_dir)

    rows = load_rows(csv_path)
    summary = build_summary(rows)
    symbol_rows = aggregate_by_symbol(rows)
    reason_rows = aggregate_by_exit_reason(rows)
    hour_rows = aggregate_by_entry_hour(rows)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_txt = log_dir / f"trade_summary_light_{stamp}.txt"
    by_symbol_csv = log_dir / f"trade_by_symbol_{stamp}.csv"
    by_reason_csv = log_dir / f"trade_by_exit_reason_{stamp}.csv"
    by_hour_csv = log_dir / f"trade_by_entry_hour_{stamp}.csv"

    write_summary_txt(summary_txt, csv_path, summary)
    write_csv(by_symbol_csv, symbol_rows, [
        "symbol", "trades", "wins", "losses", "win_rate_pct",
        "net_pnl", "avg_pnl_pct", "avg_profit_pct", "avg_loss_pct", "avg_holding_minutes"
    ])
    write_csv(by_reason_csv, reason_rows, [
        "exit_reason", "trades", "wins", "win_rate_pct", "net_pnl", "avg_pnl_pct"
    ])
    write_csv(by_hour_csv, hour_rows, [
        "entry_hour", "trades", "wins", "win_rate_pct", "net_pnl", "avg_pnl_pct"
    ])

    print("거래 성과 요약")
    print(f"- 총 거래수: {summary['total_trades']}")
    print(f"- 승/패/보합: {summary['wins']}/{summary['losses']}/{summary['flats']}")
    print(f"- 승률: {summary['win_rate_pct']}%")
    print(f"- 평균 수익률: {summary['avg_profit_pct']}%")
    print(f"- 평균 손실률: {summary['avg_loss_pct']}%")
    print(f"- 기대값: {summary['expectancy_pct']}%")
    print(f"- 순손익: {summary['net_pnl']}원")
    print(f"- Profit Factor: {summary['profit_factor']}")
    print(f"- 평균 보유시간: {summary['avg_holding_minutes']}분")
    print()
    print(f"요약 TXT 저장: {summary_txt}")
    print(f"종목별 CSV 저장: {by_symbol_csv}")
    print(f"청산사유별 CSV 저장: {by_reason_csv}")
    print(f"진입시간대별 CSV 저장: {by_hour_csv}")


if __name__ == "__main__":
    main()
