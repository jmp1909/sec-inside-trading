"""
Robustness checks for the headline strategy (3-month net insider dollar value, top 50,
monthly rebalance), each aimed at one specific objection to the original backtest:

  1. Factor exposure  -- is the "edge" just a size / value / profitability / investment /
     momentum tilt? Regress monthly excess returns on CAPM, FF3, FF5 and FF5+Momentum,
     Newey-West (3 lags) t-stats. Run on the strategy, on the strategy minus the EW
     benchmark, and on the purchases-only calendar-time portfolios.
  2. Thin purchase sample -- calendar-time portfolios that hold *every* member with an
     open-market purchase in the last 1 / 3 months (Lakonishok-Lee / Jeng-Metrick-
     Zeckhauser style). One return per month, so clustering of events and overlapping
     windows can't inflate the t-stat the way trade-level tests can.
  3. Luck / data-mining -- placebo: 1,000 random 50-stock portfolios drawn from the same
     point-in-time universe each month, same rebalancing and costs. Where does the
     strategy's Sharpe fall in that distribution?
  4. Drawdown -- drawdown episodes of the benchmark and what the strategy did in each;
     the strategy rescaled to the benchmark's volatility; and the market-hedged
     (active) return stream's own drawdown.
  5. Bull-market period -- calendar-year breakdown and up- vs down-market months
     (upside / downside capture vs MDY).

Run after portfolio_backtest.py and collect_factors.py. Writes data/robustness_*.csv
and a readable summary to data/robustness_summary.md.
"""
import argparse
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import max_drawdown, performance_stats, suffix
from portfolio_backtest import (
    HEADLINE_CONFIG, HEADLINE_COST_BPS, BacktestData, net_of_costs, run_ew_benchmark, run_strategy, simulate,
)

MODELS = {
    "CAPM": ["Mkt-RF"],
    "FF3": ["Mkt-RF", "SMB", "HML"],
    "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "FF5+Mom": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"],
}
N_PLACEBO = 1000
HAC_LAGS = 3


# ------------------------------------------------------------------ helpers

def factor_regression(y: pd.Series, factors: pd.DataFrame, cols: list) -> dict:
    d = pd.concat([y.rename("y"), factors[cols]], axis=1).dropna()
    if len(d) < 24:
        return {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = sm.OLS(d["y"], sm.add_constant(d[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    out = {"n_months": len(d), "alpha_monthly": fit.params["const"], "alpha_annual": fit.params["const"] * 12,
           "alpha_t": fit.tvalues["const"], "alpha_pval": fit.pvalues["const"], "r2": fit.rsquared}
    for c in cols:
        out[f"beta_{c}"] = fit.params[c]
        out[f"t_{c}"] = fit.tvalues[c]
    return out


def signal_any_purchase(window_txs: pd.DataFrame) -> pd.Series:
    buys = window_txs[window_txs["trans_code"] == "P"]
    return buys.groupby("ticker")["trade_value"].sum().sort_values(ascending=False)


def signal_sales_only(window_txs: pd.DataFrame) -> pd.Series:
    has_buy = set(window_txs.loc[window_txs["trans_code"] == "P", "ticker"])
    sells = window_txs[(window_txs["trans_code"] == "S") & ~window_txs["ticker"].isin(has_buy)]
    return sells.groupby("ticker")["trade_value"].sum().sort_values(ascending=False)


def calendar_time_portfolio(data, window_months, signal_fn, cost_bps):
    """Hold every eligible stock the signal selects, equal-weighted; T-bills in empty months."""
    port = run_strategy(data, window_months, 10_000, signal_fn)
    net = net_of_costs(port["gross"].to_numpy(), port["turnover"].to_numpy(), cost_bps)
    empty = port["n_holdings"].to_numpy() == 0
    net = np.where(empty, data.rf.reindex(port.index).fillna(0).to_numpy(), net)
    return pd.Series(net, index=port.index), port["n_holdings"]


def placebo(data, size, cost_bps, rng) -> pd.DataFrame:
    rows = []
    for _ in range(N_PLACEBO):
        W = np.zeros_like(data.R)
        for t in range(len(W)):
            elig = np.flatnonzero(data.E[t])
            pick = rng.choice(elig, size=min(size, len(elig)), replace=False)
            W[t, pick] = 1.0 / len(pick)
        gross, turnover = simulate(W, data.R)
        s = performance_stats(pd.Series(net_of_costs(gross, turnover, cost_bps), index=data.starts), data.rf)
        rows.append({"ann_return": s["ann_return"], "sharpe": s["sharpe"], "max_drawdown": s["max_drawdown"]})
    return pd.DataFrame(rows)


def drawdown_episodes(r: pd.Series, threshold=-0.10) -> list:
    """Peak-to-trough episodes deeper than threshold, as (peak_start, trough_end) month labels."""
    curve = (1 + r).cumprod()
    peak_val, peak_i, episodes, i = curve.iloc[0], 0, [], 0
    in_dd, trough_i = False, 0
    for i in range(len(curve)):
        if curve.iloc[i] >= peak_val:
            if in_dd and curve.iloc[trough_i] / peak_val - 1 <= threshold:
                episodes.append((peak_i, trough_i))
            peak_val, peak_i, in_dd, trough_i = curve.iloc[i], i, False, i
        else:
            if not in_dd or curve.iloc[i] < curve.iloc[trough_i]:
                trough_i = i
            in_dd = True
    if in_dd and curve.iloc[trough_i] / peak_val - 1 <= threshold:
        episodes.append((peak_i, trough_i))
    return episodes


def period_return(r: pd.Series, i0: int, i1: int) -> float:
    """Compounded return over months (i0, i1], i.e. from the end of month i0 to the end of i1."""
    return (1 + r.iloc[i0 + 1:i1 + 1]).prod() - 1


# ------------------------------------------------------------------ main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["pit", "current"], default="pit")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    sfx = suffix(args.universe)
    md = [f"# Robustness checks ({args.universe} universe, {HEADLINE_COST_BPS} bps one-way costs)\n"]

    data = BacktestData(args.universe)
    if data.factors is None:
        raise SystemExit("Run src/collect_factors.py first (factor regressions and Sharpe need RF + factors)")
    F = data.factors
    rf = data.rf
    w, n = HEADLINE_CONFIG
    port = run_strategy(data, w, n)
    bench = run_ew_benchmark(data)
    p_net = pd.Series(net_of_costs(port["gross"].to_numpy(), port["turnover"].to_numpy(), HEADLINE_COST_BPS), index=port.index)
    p_gross = port["gross"]
    b_net = pd.Series(net_of_costs(bench["gross"].to_numpy(), bench["turnover"].to_numpy(), HEADLINE_COST_BPS), index=bench.index)
    mdy = data.etf_returns()

    # ---------------- 1 + 2: factor regressions, incl. purchases-only calendar-time portfolios
    ct = {}
    for wm in (1, 3):
        ct[f"purchases_only_{wm}m"] = calendar_time_portfolio(data, wm, signal_any_purchase, HEADLINE_COST_BPS)
        ct[f"sales_only_{wm}m"] = calendar_time_portfolio(data, wm, signal_sales_only, HEADLINE_COST_BPS)

    series = {
        "strategy_net": p_net - rf, "strategy_gross": p_gross - rf, "ew_benchmark_net": b_net - rf,
        "mdy": mdy - rf, "strategy_minus_ew": p_net - b_net, "strategy_minus_mdy": p_net - mdy,
    }
    for k, (r, _) in ct.items():
        series[k] = r - rf
    series["purchases_minus_sales_3m"] = ct["purchases_only_3m"][0] - ct["sales_only_3m"][0]

    reg_rows = []
    for name, y in series.items():
        for model, cols in MODELS.items():
            res = factor_regression(y, F, cols)
            if res:
                reg_rows.append({"series": name, "model": model, **res})
    regs = pd.DataFrame(reg_rows)
    regs.to_csv(f"data/robustness_factor_regressions{sfx}.csv", index=False)

    md.append("## 1. Factor-adjusted alpha (Newey-West t, annualized alpha)\n")
    md.append("| series | CAPM | FF3 | FF5 | FF5+Mom | SMB beta | HML beta | Mom beta |\n|---|---|---|---|---|---|---|---|")
    for name in series:
        r = regs[regs["series"] == name].set_index("model")
        if r.empty:
            continue
        cells = [f"{r.loc[m, 'alpha_annual']:+.1%} (t={r.loc[m, 'alpha_t']:.1f})" if m in r.index else "" for m in MODELS]
        full = r.loc["FF5+Mom"] if "FF5+Mom" in r.index else None
        betas = [f"{full[f'beta_{c}']:+.2f}" if full is not None else "" for c in ("SMB", "HML", "Mom")]
        md.append(f"| {name} | " + " | ".join(cells + betas) + " |")
    md.append("\nRead: if the FF5+Mom alpha of `strategy_net` / `strategy_minus_ew` is small or its t-stat is "
              "below ~2, the edge is explained by factor tilts rather than insider information.\n")

    md.append("## 2. Purchases-only calendar-time portfolios (one observation per month)\n")
    md.append("| portfolio | avg stocks held | months with no holdings | ann. return | Sharpe | max DD |\n|---|---|---|---|---|---|")
    for k, (r, nh) in ct.items():
        s = performance_stats(r, rf)
        md.append(f"| {k} | {nh.mean():.1f} | {(nh == 0).sum()} | {s['ann_return']:+.1%} | {s['sharpe']:.2f} | {s['max_drawdown']:.0%} |")
    md.append("")

    # ---------------- 3: placebo random portfolios
    rng = np.random.default_rng(args.seed)
    plc = placebo(data, n, HEADLINE_COST_BPS, rng)
    plc.to_csv(f"data/robustness_placebo{sfx}.csv", index=False)
    ps, bs, ms = performance_stats(p_net, rf), performance_stats(b_net, rf), performance_stats(mdy, rf)
    pct_sr = (plc["sharpe"] < ps["sharpe"]).mean()
    pct_ret = (plc["ann_return"] < ps["ann_return"]).mean()
    md.append(f"## 3. Placebo: {N_PLACEBO} random {n}-stock portfolios from the same universe\n")
    md.append(f"Strategy Sharpe {ps['sharpe']:.2f} beats {pct_sr:.1%} of random portfolios "
              f"(placebo median {plc['sharpe'].median():.2f}, 95th pct {plc['sharpe'].quantile(.95):.2f}); "
              f"CAGR {ps['ann_return']:+.1%} beats {pct_ret:.1%} (placebo median {plc['ann_return'].median():+.1%}). "
              f"One-sided p-value for Sharpe = {1 - pct_sr:.3f}.\n")

    # ---------------- 4: drawdowns
    dd_rows = []
    for i0, i1 in drawdown_episodes(b_net):
        dd_rows.append({
            "peak_month_end": port["end"].iloc[i0].date(), "trough_month_end": port["end"].iloc[i1].date(),
            "ew_benchmark": period_return(b_net, i0, i1), "mdy": period_return(mdy, i0, i1),
            "strategy": period_return(p_net, i0, i1),
        })
    dds = pd.DataFrame(dd_rows)
    dds.to_csv(f"data/robustness_drawdowns{sfx}.csv", index=False)

    beta = sm.OLS((p_net - rf).dropna(), sm.add_constant((mdy - rf).reindex((p_net - rf).dropna().index))).fit().params.iloc[1]
    hedged = p_net - beta * (mdy - rf)  # long strategy, short beta x MDY (financed at rf)
    vol_scale = b_net.std() / p_net.std()
    vol_matched = rf + vol_scale * (p_net - rf)
    vm = performance_stats(vol_matched, rf)
    hs = performance_stats(hedged, rf)
    md.append("## 4. Drawdowns\n")
    md.append(f"Max drawdown: strategy {ps['max_drawdown']:.1%}, EW benchmark {bs['max_drawdown']:.1%}, "
              f"MDY {ms['max_drawdown']:.1%}. Strategy beta to MDY = {beta:.2f}.\n")
    md.append(f"- **Volatility-matched** (strategy scaled by {vol_scale:.2f} to the EW benchmark's volatility, rest in "
              f"T-bills): CAGR {vm['ann_return']:+.1%}, max DD {vm['max_drawdown']:.1%}, vs EW benchmark "
              f"{bs['ann_return']:+.1%} / {bs['max_drawdown']:.1%}.")
    md.append(f"- **Market-hedged** (short {beta:.2f}x MDY): CAGR {hs['ann_return']:+.1%}, Sharpe {hs['sharpe']:.2f}, "
              f"max DD {hs['max_drawdown']:.1%}.\n")
    if len(dds):
        md.append("| benchmark drawdown (peak -> trough) | EW benchmark | MDY | strategy |\n|---|---|---|---|")
        for r in dds.itertuples():
            md.append(f"| {r.peak_month_end} -> {r.trough_month_end} | {r.ew_benchmark:+.1%} | {r.mdy:+.1%} | {r.strategy:+.1%} |")
        md.append("")

    # ---------------- 5: regimes
    years = p_net.groupby(p_net.index.year)
    reg = pd.DataFrame({
        "strategy": years.apply(lambda r: (1 + r).prod() - 1),
        "ew_benchmark": b_net.groupby(b_net.index.year).apply(lambda r: (1 + r).prod() - 1),
        "mdy": mdy.groupby(mdy.index.year).apply(lambda r: (1 + r).prod() - 1),
        "months": years.size().astype(int),
    })
    reg["strategy_minus_ew"] = reg["strategy"] - reg["ew_benchmark"]
    up, down = mdy > 0, mdy <= 0
    capture = pd.DataFrame([{
        "regime": name, "months": int(m.sum()),
        "strategy_avg": p_net[m].mean(), "ew_avg": b_net[m].mean(), "mdy_avg": mdy[m].mean(),
        "capture_vs_mdy": p_net[m].mean() / mdy[m].mean(),
        "strategy_minus_ew_avg": (p_net - b_net)[m].mean(),
    } for name, m in (("MDY up months", up), ("MDY down months", down))])
    reg.to_csv(f"data/robustness_regimes{sfx}.csv", index_label="year")
    capture.to_csv(f"data/robustness_capture{sfx}.csv", index=False)

    md.append("## 5. Market regimes\n")
    md.append("| year | months | strategy | EW benchmark | MDY | strategy - EW |\n|---|---|---|---|---|---|")
    for y, r in reg.iterrows():
        md.append(f"| {y} | {r['months']} | {r['strategy']:+.1%} | {r['ew_benchmark']:+.1%} | {r['mdy']:+.1%} | {r['strategy_minus_ew']:+.1%} |")
    md.append(f"\nYears the strategy beat the EW benchmark: {(reg['strategy_minus_ew'] > 0).sum()} of {len(reg)}.\n")
    md.append("| regime | months | strategy avg/mo | EW avg/mo | MDY avg/mo | capture vs MDY | strategy - EW avg/mo |\n|---|---|---|---|---|---|---|")
    for r in capture.itertuples():
        md.append(f"| {r.regime} | {r.months} | {r.strategy_avg:+.2%} | {r.ew_avg:+.2%} | {r.mdy_avg:+.2%} | "
                  f"{r.capture_vs_mdy:.2f} | {r.strategy_minus_ew_avg:+.2%} |")
    md.append("\nThe study window (2019-2026) contains two sharp drawdowns (COVID 2020, 2022) but no prolonged bear "
              "market like 2000-02 or 2008-09. SEC's insider data sets start in 2006, but Wikipedia's index-change "
              "history (used for the point-in-time universe) only goes back to 2012, so extending the window to "
              "cover 2008 needs a different constituent-history source.\n")

    # ---------------- headline comparison
    md.insert(1, "## Headline (net of costs)\n\n| | CAGR | vol | Sharpe (excess of T-bills) | Sortino | max DD |\n|---|---|---|---|---|---|\n"
              + "\n".join(f"| {k} | {s['ann_return']:+.1%} | {s['ann_vol']:.1%} | {s['sharpe']:.2f} | {s['sortino']:.2f} | {s['max_drawdown']:.1%} |"
                          for k, s in (("strategy (3m, top 50)", ps), ("EW benchmark", bs), ("MDY ETF", ms),
                                       ("strategy, gross of costs", performance_stats(p_gross, rf))))
              + f"\n\nAverage one-way turnover {port['turnover'].mean() / 2:.0%} per month; on average "
              f"{port['n_positive_signal'].mean():.0f} of the {port['n_holdings'].mean():.0f} holdings have net insider "
              f"*buying*; any remaining slots go to the names with the least net selling.\n")

    # ---------------- survivorship: point-in-time vs today's-constituents universe
    try:
        g_pit = pd.read_csv("data/portfolio_backtest_grid.csv")
        g_cur = pd.read_csv("data/portfolio_backtest_grid_current.csv")
        cov = pd.read_csv("data/price_coverage.csv")
        md.append("## Survivorship bias: point-in-time vs today's constituents\n")
        md.append("| config | cost | universe | CAGR | Sharpe | max DD | EW bench CAGR | EW bench Sharpe |\n|---|---|---|---|---|---|---|---|")
        for g, label in ((g_cur, "today's members (old)"), (g_pit, "point-in-time")):
            for c in (0, HEADLINE_COST_BPS):
                r = g[(g["window_months"] == w) & (g["portfolio_size"] == n) & (g["cost_bps"] == c)].iloc[0]
                md.append(f"| {w}m / top {n} | {c} bps | {label} | {r['port_ann_return']:+.1%} | {r['port_sharpe']:.2f} | "
                          f"{r['port_max_dd']:.1%} | {r['bench_ann_return']:+.1%} | {r['bench_sharpe']:.2f} |")
        removed = cov[~cov["member_at_study_end"]]
        md.append(f"\nPrice coverage of point-in-time member-days: {cov['member_days_priced'].sum() / cov['member_days'].sum():.1%} "
                  f"overall; {(removed['member_days_priced'] > 0).sum()} of {len(removed)} companies removed during the window "
                  f"have Yahoo prices ({removed['member_days_priced'].sum() / max(removed['member_days'].sum(), 1):.1%} of their "
                  f"member-days). The unpriced remainder (mostly acquired companies, whose tickers Yahoo drops) is a residual "
                  f"survivorship gap; acquisitions usually close at a premium, so this gap is more likely to understate "
                  f"than overstate benchmark returns.\n")
    except (FileNotFoundError, IndexError):
        pass

    out = f"data/robustness_summary{sfx}.md"
    open(out, "w").write("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nWrote {out} and data/robustness_*{sfx}.csv")


if __name__ == "__main__":
    main()
