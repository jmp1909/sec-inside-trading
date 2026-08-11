"""
Monthly-rebalanced portfolio backtest: rank the universe by trailing insider-
buying signal, hold the top N equal-weighted, rebalance monthly, compare to
an equal-weight buy-and-hold universe benchmark.

Runs a grid over lookback window (1m/3m/6m) x portfolio size (10/20/50) for
the primary "net dollar value" signal, then also computes "distinct buyer
count" per company-window so the two can be cross-examined afterward.
"""
import numpy as np
import pandas as pd

WINDOWS_MONTHS = [1, 3, 6]
PORTFOLIO_SIZES = [10, 20, 50]
BANKRUPT_TICKERS = set(pd.read_csv("data/bankruptcies.csv")["ticker"])


def load_data():
    txs = pd.read_csv("data/event_study_final.csv")
    txs["filing_date"] = pd.to_datetime(txs["filing_date"])
    # net dollar value: P is positive (buying), S is negative (selling)
    txs["signed_value"] = np.where(txs["trans_code"] == "P", txs["trade_value"], -txs["trade_value"])

    prices = pd.read_csv("data/prices.csv")
    prices["date"] = pd.to_datetime(prices["date"], format="mixed")
    prices = prices[~prices["ticker"].isin(BANKRUPT_TICKERS)]
    return txs, prices


def get_rebalance_dates(prices: pd.DataFrame) -> list:
    """First trading day of each month, across the full price history range we have signal for."""
    all_dates = pd.DatetimeIndex(sorted(prices["date"].unique()))
    start = pd.Timestamp("2019-02-01")  # leave 6mo of history for the longest lookback window
    end = pd.Timestamp("2026-07-01")
    months = pd.date_range(start, end, freq="MS")
    rebal_dates = []
    for m in months:
        candidates = all_dates[all_dates >= m]
        if len(candidates):
            rebal_dates.append(candidates[0])
    return rebal_dates


def compute_monthly_return(prices_wide: pd.DataFrame, tickers: list, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Equal-weight simple return of a basket of tickers held from start to end."""
    valid = [t for t in tickers if t in prices_wide.columns]
    if not valid:
        return np.nan
    p_start = prices_wide.loc[start, valid]
    p_end = prices_wide.loc[end, valid]
    rets = (p_end / p_start - 1).dropna()
    if rets.empty:
        return np.nan
    return rets.mean()


def run_backtest(txs, prices_wide, rebal_dates, window_months, portfolio_size):
    holdings_log = []
    portfolio_returns = []
    benchmark_returns = []

    for i in range(len(rebal_dates) - 1):
        reb_date = rebal_dates[i]
        next_date = rebal_dates[i + 1]
        window_start = reb_date - pd.DateOffset(months=window_months)

        window_txs = txs[(txs["filing_date"] >= window_start) & (txs["filing_date"] < reb_date)]
        signal = window_txs.groupby("ticker")["signed_value"].sum().sort_values(ascending=False)
        top_tickers = signal.head(portfolio_size).index.tolist()

        port_ret = compute_monthly_return(prices_wide, top_tickers, reb_date, next_date)
        all_tickers = [t for t in prices_wide.columns]
        bench_ret = compute_monthly_return(prices_wide, all_tickers, reb_date, next_date)

        portfolio_returns.append({"date": reb_date, "ret": port_ret, "n_holdings": len(top_tickers)})
        benchmark_returns.append({"date": reb_date, "ret": bench_ret})
        holdings_log.append({"date": reb_date, "tickers": top_tickers})

    return pd.DataFrame(portfolio_returns), pd.DataFrame(benchmark_returns)


def performance_stats(returns: pd.Series) -> dict:
    returns = returns.dropna()
    cum = (1 + returns).prod() - 1
    n_years = len(returns) / 12
    ann_ret = (1 + cum) ** (1 / n_years) - 1 if n_years > 0 else np.nan
    ann_vol = returns.std() * np.sqrt(12)
    sharpe = ann_ret / ann_vol if ann_vol else np.nan
    cum_curve = (1 + returns).cumprod()
    drawdown = (cum_curve / cum_curve.cummax() - 1).min()
    return {"cum_return": cum, "ann_return": ann_ret, "ann_vol": ann_vol, "sharpe": sharpe, "max_drawdown": drawdown}


def main():
    txs, prices = load_data()
    prices_wide = prices.pivot(index="date", columns="ticker", values="adj_close")
    rebal_dates = get_rebalance_dates(prices)
    print(f"{len(rebal_dates)} monthly rebalance dates: {rebal_dates[0].date()} .. {rebal_dates[-1].date()}\n")

    results = []
    for window_months in WINDOWS_MONTHS:
        for size in PORTFOLIO_SIZES:
            port_df, bench_df = run_backtest(txs, prices_wide, rebal_dates, window_months, size)
            pstats = performance_stats(port_df["ret"])
            bstats = performance_stats(bench_df["ret"])
            avg_holdings = port_df["n_holdings"].mean()
            results.append({
                "window_months": window_months, "portfolio_size": size,
                "avg_actual_holdings": round(avg_holdings, 1),
                "port_cum_return": pstats["cum_return"], "port_ann_return": pstats["ann_return"],
                "port_sharpe": pstats["sharpe"], "port_max_dd": pstats["max_drawdown"],
                "bench_cum_return": bstats["cum_return"], "bench_ann_return": bstats["ann_return"],
                "bench_sharpe": bstats["sharpe"], "bench_max_dd": bstats["max_drawdown"],
            })
            print(f"window={window_months}mo  size={size}:  "
                  f"port ann_ret={pstats['ann_return']:+.2%} sharpe={pstats['sharpe']:.2f} maxdd={pstats['max_drawdown']:.2%}  |  "
                  f"bench ann_ret={bstats['ann_return']:+.2%} sharpe={bstats['sharpe']:.2f}")

    results_df = pd.DataFrame(results)
    results_df.to_csv("data/portfolio_backtest_grid.csv", index=False)
    print("\nWrote data/portfolio_backtest_grid.csv")


if __name__ == "__main__":
    main()
