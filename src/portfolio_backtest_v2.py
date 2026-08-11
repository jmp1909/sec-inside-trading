"""
Extends portfolio_backtest.py with alternate ranking signals that combine
net dollar value and distinct-buyer count, to see whether "concentration"
(big bet from one insider) or "breadth" (many insiders independently buying)
refines the base net-dollar-value signal.
"""
import numpy as np
import pandas as pd

from portfolio_backtest import (
    load_data, get_rebalance_dates, compute_monthly_return, performance_stats,
)

MIN_BUYERS_FOR_CONCENTRATION = 2  # avoid ranking single noisy transactions as "concentrated conviction"


def signal_net_dollar_value(window_txs: pd.DataFrame) -> pd.Series:
    return window_txs.groupby("ticker")["signed_value"].sum().sort_values(ascending=False)


def signal_buyer_count(window_txs: pd.DataFrame) -> pd.Series:
    buys = window_txs[window_txs["trans_code"] == "P"]
    return buys.groupby("ticker")["owner_cik"].nunique().sort_values(ascending=False)


def signal_value_per_buyer(window_txs: pd.DataFrame) -> pd.Series:
    buys = window_txs[window_txs["trans_code"] == "P"]
    grouped = buys.groupby("ticker").agg(total_value=("trade_value", "sum"), n_buyers=("owner_cik", "nunique"))
    grouped = grouped[grouped["n_buyers"] >= MIN_BUYERS_FOR_CONCENTRATION]
    return (grouped["total_value"] / grouped["n_buyers"]).sort_values(ascending=False)


SIGNALS = {
    "net_dollar_value": signal_net_dollar_value,
    "buyer_count": signal_buyer_count,
    "value_per_buyer": signal_value_per_buyer,
}


def run_backtest_generic(txs, prices_wide, rebal_dates, window_months, portfolio_size, signal_fn):
    portfolio_returns = []
    for i in range(len(rebal_dates) - 1):
        reb_date = rebal_dates[i]
        next_date = rebal_dates[i + 1]
        window_start = reb_date - pd.DateOffset(months=window_months)

        window_txs = txs[(txs["filing_date"] >= window_start) & (txs["filing_date"] < reb_date)]
        signal = signal_fn(window_txs)
        top_tickers = signal.head(portfolio_size).index.tolist()

        port_ret = compute_monthly_return(prices_wide, top_tickers, reb_date, next_date)
        portfolio_returns.append({"date": reb_date, "ret": port_ret, "n_holdings": len(top_tickers)})

    return pd.DataFrame(portfolio_returns)


def main():
    txs, prices = load_data()
    prices_wide = prices.pivot(index="date", columns="ticker", values="adj_close")
    rebal_dates = get_rebalance_dates(prices)

    # focus on the window/size that had the best risk-adjusted result in v1 (3mo, top 50),
    # plus top 20 for comparison, across all three signals
    configs = [(3, 20), (3, 50)]

    results = []
    print(f"{'signal':>18} {'window':>7} {'size':>5}   {'ann_ret':>9} {'sharpe':>7} {'max_dd':>8} {'avg_n':>6}")
    for signal_name, signal_fn in SIGNALS.items():
        for window_months, size in configs:
            port_df = run_backtest_generic(txs, prices_wide, rebal_dates, window_months, size, signal_fn)
            stats = performance_stats(port_df["ret"])
            avg_n = port_df["n_holdings"].mean()
            results.append({
                "signal": signal_name, "window_months": window_months, "portfolio_size": size,
                "avg_actual_holdings": round(avg_n, 1),
                "ann_return": stats["ann_return"], "sharpe": stats["sharpe"], "max_dd": stats["max_drawdown"],
            })
            print(f"{signal_name:>18} {window_months:>6}mo {size:>5}   "
                  f"{stats['ann_return']:>+9.2%} {stats['sharpe']:>7.2f} {stats['max_drawdown']:>8.2%} {avg_n:>6.1f}")

    pd.DataFrame(results).to_csv("data/portfolio_backtest_signals.csv", index=False)
    print("\nWrote data/portfolio_backtest_signals.csv")


if __name__ == "__main__":
    main()
