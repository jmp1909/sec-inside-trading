"""
Monthly-rebalanced portfolio backtest: rank the universe by trailing insider-
buying signal, hold the top N equal-weighted, rebalance monthly, compare to
an equal-weight universe benchmark and to the MDY ETF.

Runs a grid over lookback window (1m/3m/6m) x portfolio size (10/20/50) x one-way
transaction cost (0/10/25/50 bps of traded value).

What changed vs the first version, and why:
  * Point-in-time universe (--universe pit, default): a stock can only be bought on a
    rebalance date if it was an S&P 400 member that day; the EW benchmark is built the
    same way. --universe current reproduces the original survivorship-biased setup so
    the bias can be measured directly.
  * Delistings: a held stock that stops trading mid-month keeps its last price (cash at
    the final close) instead of being dropped from the month's average. Chapter 11
    filers are kept too, with a -30% delisting return at the petition (the first version
    dropped them from the study entirely).
  * Trading costs: target weights are compared with the drifted weights from last month
    to get turnover (sum of |trade| / portfolio value, buys + sells). Net return =
    (1 + gross) * (1 - cost * turnover) - 1. The EW benchmark pays the same costs on
    its own (much smaller) turnover; MDY is buy-and-hold, its fee is already in the price.
  * Sharpe ratio is on excess returns over the 1-month T-bill (Fama-French RF),
    compounded over each exact holding period. The old version used CAGR / vol with no
    risk-free rate.
  * MDY (SPDR S&P MidCap 400 ETF) is added as an investable, cap-weighted,
    survivorship-free benchmark.
"""
import argparse

import numpy as np
import pandas as pd

from common import (
    BACKTEST_END, BACKTEST_START, ETF_BENCHMARK, build_price_panel, compound_factors, load_factors_daily,
    load_prices_long, membership_mask, performance_stats, suffix,
)

WINDOWS_MONTHS = [1, 3, 6]
PORTFOLIO_SIZES = [10, 20, 50]
COSTS_BPS = [0, 10, 25, 50]
# headline assumption: 25 bps one-way (50 bps round trip) -- spread + impact for a
# small account trading S&P 400 names; deliberately on the conservative side
HEADLINE_COST_BPS = 25
HEADLINE_CONFIG = (3, 50)


class BacktestData:
    """Everything a backtest needs, precomputed on the monthly rebalance grid.

    R[t, j]  simple return of ticker j from rebalance date t to t+1
    E[t, j]  True if ticker j may be held from date t (index member that day, has a
             current price)
    """

    def __init__(self, mode: str):
        self.mode = mode
        txs = pd.read_csv("data/form4_with_returns.csv", usecols=[
            "ticker", "filing_date", "trans_code", "trade_value", "owner_cik"], parse_dates=["filing_date"])
        txs["signed_value"] = np.where(txs["trans_code"] == "P", txs["trade_value"], -txs["trade_value"])
        self.txs = txs

        prices = load_prices_long()
        panel, last_valid = build_price_panel(prices)
        self.etf = panel[ETF_BENCHMARK] if ETF_BENCHMARK in panel else None
        panel = panel.drop(columns=[ETF_BENCHMARK], errors="ignore")
        last_valid = last_valid.drop(ETF_BENCHMARK, errors="ignore")

        self.rebal_dates = self._rebalance_dates(panel.index)
        self.tickers = np.array(panel.columns)
        P = panel.loc[self.rebal_dates].to_numpy()
        self.R = P[1:] / P[:-1] - 1
        members = membership_mask(pd.DatetimeIndex(self.rebal_dates), panel.columns, mode).to_numpy()
        alive = np.array([[d <= last_valid[t] for t in self.tickers] for d in self.rebal_dates])
        self.E = (members & ~np.isnan(P) & alive)[:-1]
        self.starts = pd.DatetimeIndex(self.rebal_dates[:-1])
        self.ends = pd.DatetimeIndex(self.rebal_dates[1:])
        self.col = {t: j for j, t in enumerate(self.tickers)}

        try:
            f = compound_factors(load_factors_daily(), self.starts, self.ends)
            self.factors = f
            self.rf = f["RF"]
        except FileNotFoundError:
            print("WARNING: data/ff_factors_daily.csv missing (run collect_factors.py); Sharpe uses rf = 0")
            self.factors = None
            self.rf = pd.Series(0.0, index=self.starts)

    @staticmethod
    def _rebalance_dates(all_dates: pd.DatetimeIndex) -> list:
        """First trading day of each month."""
        rebal = []
        for m in pd.date_range(BACKTEST_START, BACKTEST_END, freq="MS"):
            c = all_dates[all_dates >= m]
            if len(c):
                rebal.append(c[0])
        return rebal

    def window_txs(self, t: int, window_months: int) -> pd.DataFrame:
        reb = self.starts[t]
        lo = reb - pd.DateOffset(months=window_months)
        w = self.txs[(self.txs["filing_date"] >= lo) & (self.txs["filing_date"] < reb)]
        eligible = set(self.tickers[self.E[t]])
        return w[w["ticker"].isin(eligible)]

    def etf_returns(self) -> pd.Series:
        if self.etf is None:
            return pd.Series(np.nan, index=self.starts)
        p = self.etf.loc[self.rebal_dates].to_numpy()
        return pd.Series(p[1:] / p[:-1] - 1, index=self.starts)


def signal_net_dollar_value(window_txs: pd.DataFrame) -> pd.Series:
    return window_txs.groupby("ticker")["signed_value"].sum().sort_values(ascending=False)


def simulate(W: np.ndarray, R: np.ndarray):
    """Gross return and turnover for a sequence of target weight vectors (rows sum to 1 or 0)."""
    Rz = np.nan_to_num(R)
    gross = (W * Rz).sum(axis=1)
    turnover = np.zeros(len(W))
    drift = np.zeros(W.shape[1])
    for t in range(len(W)):
        turnover[t] = np.abs(W[t] - drift).sum()
        grown = W[t] * (1 + Rz[t])
        drift = grown / grown.sum() if grown.sum() > 0 else np.zeros_like(grown)
    return gross, turnover


def net_of_costs(gross: np.ndarray, turnover: np.ndarray, cost_bps: float) -> np.ndarray:
    return (1 + gross) * (1 - cost_bps / 1e4 * turnover) - 1


def run_strategy(data: BacktestData, window_months: int, size: int, signal_fn=signal_net_dollar_value) -> pd.DataFrame:
    W = np.zeros_like(data.R)
    n_hold, n_pos = [], []
    for t in range(len(data.starts)):
        sig = signal_fn(data.window_txs(t, window_months))
        top = sig.head(size)
        for tk in top.index:
            W[t, data.col[tk]] = 1.0 / len(top)
        n_hold.append(len(top))
        n_pos.append(int((top > 0).sum()))
    gross, turnover = simulate(W, data.R)
    return pd.DataFrame({"start": data.starts, "end": data.ends, "gross": gross, "turnover": turnover,
                         "n_holdings": n_hold, "n_positive_signal": n_pos}).set_index("start")


def run_ew_benchmark(data: BacktestData) -> pd.DataFrame:
    W = data.E.astype(float)
    W = W / W.sum(axis=1, keepdims=True)
    gross, turnover = simulate(W, data.R)
    return pd.DataFrame({"end": data.ends, "gross": gross, "turnover": turnover,
                         "n_holdings": data.E.sum(axis=1)}, index=data.starts)


def break_even_cost(port: pd.DataFrame, bench: pd.DataFrame) -> float:
    """One-way cost (bps) at which the strategy's net CAGR falls to the EW benchmark's."""
    def gap(c):
        p = performance_stats(pd.Series(net_of_costs(port["gross"].to_numpy(), port["turnover"].to_numpy(), c)))
        b = performance_stats(pd.Series(net_of_costs(bench["gross"].to_numpy(), bench["turnover"].to_numpy(), c)))
        return p["ann_return"] - b["ann_return"]
    lo, hi = 0.0, 1000.0
    if gap(lo) <= 0:
        return 0.0
    if gap(hi) > 0:
        return np.inf
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gap(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["pit", "current"], default="pit")
    args = parser.parse_args()
    sfx = suffix(args.universe)

    data = BacktestData(args.universe)
    print(f"{len(data.starts)} monthly holding periods: {data.starts[0].date()} .. {data.ends[-1].date()} "
          f"({args.universe} universe, avg {data.E.sum(axis=1).mean():.0f} eligible stocks/month)\n")

    bench = run_ew_benchmark(data)
    etf = data.etf_returns()
    etf_stats = performance_stats(etf, data.rf)

    results = []
    for window_months in WINDOWS_MONTHS:
        for size in PORTFOLIO_SIZES:
            port = run_strategy(data, window_months, size)
            be = break_even_cost(port, bench)
            for cost in COSTS_BPS:
                p_net = pd.Series(net_of_costs(port["gross"].to_numpy(), port["turnover"].to_numpy(), cost), index=port.index)
                b_net = pd.Series(net_of_costs(bench["gross"].to_numpy(), bench["turnover"].to_numpy(), cost), index=bench.index)
                ps, bs = performance_stats(p_net, data.rf), performance_stats(b_net, data.rf)
                results.append({
                    "window_months": window_months, "portfolio_size": size, "cost_bps": cost,
                    "avg_actual_holdings": round(port["n_holdings"].mean(), 1),
                    "avg_net_buying_holdings": round(port["n_positive_signal"].mean(), 1),
                    "avg_monthly_turnover_oneway": port["turnover"].mean() / 2,
                    "port_cum_return": ps["cum_return"], "port_ann_return": ps["ann_return"],
                    "port_ann_vol": ps["ann_vol"], "port_sharpe": ps["sharpe"], "port_sortino": ps["sortino"],
                    "port_max_dd": ps["max_drawdown"], "port_calmar": ps["calmar"],
                    "bench_ann_return": bs["ann_return"], "bench_sharpe": bs["sharpe"], "bench_max_dd": bs["max_drawdown"],
                    "mdy_ann_return": etf_stats["ann_return"], "mdy_sharpe": etf_stats["sharpe"],
                    "mdy_max_dd": etf_stats["max_drawdown"],
                    "break_even_cost_bps": be,
                })
            r0 = [r for r in results if r["window_months"] == window_months and r["portfolio_size"] == size]
            g, h = r0[0], next(r for r in r0 if r["cost_bps"] == HEADLINE_COST_BPS)
            print(f"window={window_months}mo size={size:>2}: turnover {g['avg_monthly_turnover_oneway']:.0%}/mo one-way, "
                  f"{g['avg_net_buying_holdings']:.0f} of {g['avg_actual_holdings']:.0f} holdings net-bought | "
                  f"gross {g['port_ann_return']:+.1%} SR {g['port_sharpe']:.2f} | "
                  f"@{HEADLINE_COST_BPS}bps {h['port_ann_return']:+.1%} SR {h['port_sharpe']:.2f} DD {h['port_max_dd']:.0%} | "
                  f"break-even {be:.0f}bps")

    grid = pd.DataFrame(results)
    b0 = grid[grid["cost_bps"] == HEADLINE_COST_BPS].iloc[0]
    print(f"\nEW benchmark @{HEADLINE_COST_BPS}bps: {b0['bench_ann_return']:+.1%}  SR {b0['bench_sharpe']:.2f}  "
          f"DD {b0['bench_max_dd']:.0%}   |   MDY: {etf_stats['ann_return']:+.1%}  SR {etf_stats['sharpe']:.2f}  "
          f"DD {etf_stats['max_drawdown']:.0%}   (rf coverage {etf_stats['rf_coverage']:.0%} of months)")
    grid.to_csv(f"data/portfolio_backtest_grid{sfx}.csv", index=False)

    # headline configuration: monthly series + equity curve
    w, n = HEADLINE_CONFIG
    port = run_strategy(data, w, n)
    monthly = pd.DataFrame({
        "end": port["end"], "port_gross": port["gross"],
        "port_net": net_of_costs(port["gross"].to_numpy(), port["turnover"].to_numpy(), HEADLINE_COST_BPS),
        "port_turnover": port["turnover"], "n_holdings": port["n_holdings"],
        "n_net_buying": port["n_positive_signal"],
        "bench_ew_gross": bench["gross"],
        "bench_ew_net": net_of_costs(bench["gross"].to_numpy(), bench["turnover"].to_numpy(), HEADLINE_COST_BPS),
        "bench_mdy": etf, "rf": data.rf,
    })
    monthly.to_csv(f"data/backtest_monthly{sfx}.csv", index_label="start")
    curve = (1 + monthly[["port_gross", "port_net", "bench_ew_net", "bench_mdy"]]).cumprod()
    curve.index = monthly["end"]
    curve.to_csv(f"data/equity_curve_best{sfx}.csv", index_label="date")
    print(f"\nWrote data/portfolio_backtest_grid{sfx}.csv, data/backtest_monthly{sfx}.csv, "
          f"data/equity_curve_best{sfx}.csv")


if __name__ == "__main__":
    main()
