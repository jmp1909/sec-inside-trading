"""
Extends portfolio_backtest.py with alternate ranking signals that combine
net dollar value and distinct-buyer count, to see whether "concentration"
(big bet from one insider) or "breadth" (many insiders independently buying)
refines the base net-dollar-value signal.

Uses the same engine as portfolio_backtest.py: point-in-time universe, turnover-based
trading costs, and Sharpe on excess returns over the T-bill rate.
"""
import argparse

import pandas as pd

from portfolio_backtest import (
    COSTS_BPS, HEADLINE_COST_BPS, BacktestData, net_of_costs, run_strategy, signal_net_dollar_value,
)
from common import performance_stats, suffix

MIN_BUYERS_FOR_CONCENTRATION = 2  # avoid ranking single noisy transactions as "concentrated conviction"


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["pit", "current"], default="pit")
    args = parser.parse_args()

    data = BacktestData(args.universe)
    # the headline configuration (3mo, top 50) plus top 20 for comparison, across all
    # three signals; 3mo / top 50 was the best risk-adjusted result in the first version
    configs = [(3, 20), (3, 50)]

    results = []
    print(f"{'signal':>18} {'window':>7} {'size':>5} {'cost':>5}   {'ann_ret':>9} {'sharpe':>7} {'max_dd':>8} {'avg_n':>6}")
    for signal_name, signal_fn in SIGNALS.items():
        for window_months, size in configs:
            port = run_strategy(data, window_months, size, signal_fn)
            for cost in COSTS_BPS:
                net = pd.Series(net_of_costs(port["gross"].to_numpy(), port["turnover"].to_numpy(), cost), index=port.index)
                stats = performance_stats(net, data.rf)
                results.append({
                    "signal": signal_name, "window_months": window_months, "portfolio_size": size, "cost_bps": cost,
                    "avg_actual_holdings": round(port["n_holdings"].mean(), 1),
                    "avg_monthly_turnover_oneway": port["turnover"].mean() / 2,
                    "ann_return": stats["ann_return"], "sharpe": stats["sharpe"], "max_dd": stats["max_drawdown"],
                })
                if cost in (0, HEADLINE_COST_BPS):
                    print(f"{signal_name:>18} {window_months:>6}mo {size:>5} {cost:>4}b   "
                          f"{stats['ann_return']:>+9.2%} {stats['sharpe']:>7.2f} {stats['max_drawdown']:>8.2%} "
                          f"{port['n_holdings'].mean():>6.1f}")

    out = f"data/portfolio_backtest_signals{suffix(args.universe)}.csv"
    pd.DataFrame(results).to_csv(out, index=False)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
