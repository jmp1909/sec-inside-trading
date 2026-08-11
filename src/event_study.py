"""
Event study: do open-market insider purchases (P) predict positive forward
returns, and do sales (S) predict negative ones? Compares P vs S vs an
equal-weighted universe benchmark at each horizon.
"""
import numpy as np
import pandas as pd

HORIZONS = ["1d", "5d", "10d", "20d", "6m", "1y", "2y"]


def main():
    df = pd.read_csv("data/event_study_final.csv")
    ret_cols = [f"ret_{h}" for h in HORIZONS]

    # unconditional benchmark: mean forward return from EVERY trading day for
    # every universe ticker (not just insider-filing days) -- see build_benchmark.py
    bench_series = pd.read_csv("data/unconditional_benchmark.csv", index_col=0)["mean_ret"]
    benchmark = pd.Series({f"ret_{h}": bench_series[h] for h in HORIZONS})

    print("=" * 70)
    print("EVENT STUDY: mean forward return by transaction type")
    print("=" * 70)
    summary = df.groupby("trans_code")[ret_cols].agg(["mean", "median", "count"])
    for h in HORIZONS:
        col = f"ret_{h}"
        p_mean = df[df["trans_code"] == "P"][col].mean()
        p_median = df[df["trans_code"] == "P"][col].median()
        s_mean = df[df["trans_code"] == "S"][col].mean()
        s_median = df[df["trans_code"] == "S"][col].median()
        bench = benchmark[col]
        print(f"\n{h:>4}  benchmark(all)={bench:+.4f}")
        print(f"      P: mean={p_mean:+.4f}  median={p_median:+.4f}  (n={df[df.trans_code=='P'][col].notna().sum()})")
        print(f"      S: mean={s_mean:+.4f}  median={s_median:+.4f}  (n={df[df.trans_code=='S'][col].notna().sum()})")
        print(f"      P - benchmark: {p_mean - bench:+.4f}   S - benchmark: {s_mean - bench:+.4f}")

    # --- win rate: % of purchases with positive forward return
    print("\n" + "=" * 70)
    print("WIN RATE: % of transactions with positive forward return")
    print("=" * 70)
    for h in HORIZONS:
        col = f"ret_{h}"
        p_win = (df[df["trans_code"] == "P"][col] > 0).mean()
        s_win = (df[df["trans_code"] == "S"][col] > 0).mean()
        print(f"{h:>4}  P win rate: {p_win:.1%}   S win rate: {s_win:.1%}")

    # --- statistical significance: simple t-test, P mean vs benchmark
    from scipy import stats
    print("\n" + "=" * 70)
    print("SIGNIFICANCE: one-sample t-test, P returns vs benchmark mean")
    print("=" * 70)
    for h in HORIZONS:
        col = f"ret_{h}"
        p_returns = df[df["trans_code"] == "P"][col].dropna()
        bench = benchmark[col]
        tstat, pval = stats.ttest_1samp(p_returns, bench)
        sig = "***" if pval < 0.01 else ("**" if pval < 0.05 else ("*" if pval < 0.1 else ""))
        print(f"{h:>4}  t={tstat:+.2f}  p={pval:.4f} {sig}")

    df.to_csv("data/event_study_final.csv", index=False)


if __name__ == "__main__":
    main()
