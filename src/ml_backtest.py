"""
Convert each model's walk-forward predicted scores into the same top-N
monthly portfolio construction used for the net-dollar-value baseline, so
performance is comparable on equal footing: does a trained model produce
a better *portfolio*, even if its raw classification AUC is weak?
"""
import numpy as np
import pandas as pd

from portfolio_backtest import load_data, get_rebalance_dates, compute_monthly_return, run_backtest, performance_stats

TOP_N = 50


def backtest_from_scores(preds, prices_wide, rebal_dates):
    dates = sorted(preds["date"].unique())
    date_to_next = {rebal_dates[i]: rebal_dates[i + 1] for i in range(len(rebal_dates) - 1)}

    rows = []
    for d in dates:
        d_ts = pd.Timestamp(d)
        if d_ts not in date_to_next:
            continue
        month_preds = preds[preds["date"] == d].sort_values("score", ascending=False)
        top_tickers = month_preds.head(TOP_N)["ticker"].tolist()
        ret = compute_monthly_return(prices_wide, top_tickers, d_ts, date_to_next[d_ts])
        rows.append({"date": d_ts, "ret": ret})
    return pd.DataFrame(rows)


def main():
    txs, prices = load_data()
    prices_wide = prices.pivot(index="date", columns="ticker", values="adj_close")
    rebal_dates = get_rebalance_dates(prices)

    # IMPORTANT: the ML models only have predictions for the months after the walk-forward
    # training burn-in (~65 of 89 months). Comparing their Sharpe to the baseline's FULL-period
    # Sharpe is misleading -- the excluded early months include the 2020 COVID crash, which drags
    # the baseline's full-period number down. Always restrict every comparison to the identical
    # test window so this is apples-to-apples.
    baseline_port, baseline_bench = run_backtest(txs, prices_wide, rebal_dates, window_months=3, portfolio_size=50)

    print(f"{'model':>12} {'ann_ret':>9} {'sharpe':>7} {'max_dd':>8} {'n_months':>9}")

    results = {}
    for model_name in ["logistic", "gboost"]:
        preds = pd.read_csv(f"data/ml_predictions_{model_name}.csv")
        preds["date"] = pd.to_datetime(preds["date"])
        port = backtest_from_scores(preds, prices_wide, rebal_dates)
        stats = performance_stats(port["ret"])
        print(f"{model_name:>12} {stats['ann_return']:>+9.2%} {stats['sharpe']:>7.2f} {stats['max_drawdown']:>8.2%} {len(port):>9}")
        port.to_csv(f"data/ml_portfolio_{model_name}.csv", index=False)
        results[model_name] = port

        test_dates = port["date"]
        base_restricted = baseline_port[baseline_port["date"].isin(test_dates)]
        bench_restricted = baseline_bench[baseline_bench["date"].isin(test_dates)]
        bstats = performance_stats(base_restricted["ret"])
        benchstats = performance_stats(bench_restricted["ret"])
        print(f"{'  baseline':>12} {bstats['ann_return']:>+9.2%} {bstats['sharpe']:>7.2f} {bstats['max_drawdown']:>8.2%} {len(base_restricted):>9}  (same window as {model_name})")
        print(f"{'  bench':>12} {benchstats['ann_return']:>+9.2%} {benchstats['sharpe']:>7.2f} {benchstats['max_drawdown']:>8.2%} {len(bench_restricted):>9}  (same window as {model_name})")


if __name__ == "__main__":
    main()
