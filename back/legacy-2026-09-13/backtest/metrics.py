# backtest/metrics.py
# 성과지표 계산 파일

from math import sqrt


def calculate_max_drawdown(equity_curve):
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value

        dd = (value - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    return max_dd


def calculate_sharpe(returns, risk_free_rate=0.0):
    if not returns:
        return 0.0

    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std = variance ** 0.5

    if std == 0:
        return 0.0

    return (avg_return - risk_free_rate) / std * sqrt(len(returns))


def summarize_result(trades, equity_curve, initial_cash, final_cash):
    total_return = ((final_cash - initial_cash) / initial_cash) if initial_cash > 0 else 0.0

    win_trades = [t for t in trades if t["pnl"] > 0]
    loss_trades = [t for t in trades if t["pnl"] <= 0]
    win_rate = (len(win_trades) / len(trades)) if trades else 0.0

    # 체결 단위 수익률
    trade_returns = []
    for t in trades:
        entry_amount = t["entry_price"] * t["qty"]
        if entry_amount > 0:
            trade_returns.append(t["pnl"] / entry_amount)

    mdd = calculate_max_drawdown(equity_curve)
    sharpe = calculate_sharpe(trade_returns)

    return {
        "trades": len(trades),
        "wins": len(win_trades),
        "losses": len(loss_trades),
        "win_rate": round(win_rate, 4),
        "total_return": round(total_return, 4),
        "mdd": round(mdd, 4),
        "sharpe": round(sharpe, 4),
        "final_cash": round(final_cash, 2),
    }