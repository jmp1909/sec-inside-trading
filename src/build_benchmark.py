"""
Build a proper 'unconditional' benchmark: forward returns at each horizon
starting from EVERY trading day for every universe ticker (not just days with
an insider filing), restricted to our 8-year study window. This is what "the
average mid-cap stock does over horizon h" actually looks like, uncontaminated
by the fact that insider-transaction days might systematically differ from
random days.
"""
import numpy as np
import pandas as pd

HORIZONS = {"1d": 1, "5d": 5, "10d": 10, "20d": 20, "6m": 126, "1y": 252, "2y": 504}
START_DATE = pd.Timestamp("2018-08-13")
END_DATE = pd.Timestamp("2026-08-11")

# same 3 Chapter 11 tickers excluded from the event study, for consistency
BANKRUPT_TICKERS = set(pd.read_csv("data/bankruptcies.csv")["ticker"])


def main():
    prices = pd.read_csv("data/prices.csv")
    prices["date"] = pd.to_datetime(prices["date"], format="mixed")
    prices = prices[~prices["ticker"].isin(BANKRUPT_TICKERS)]

    all_means = {h: [] for h in HORIZONS}
    all_counts = {h: 0 for h in HORIZONS}
    all_sums = {h: 0.0 for h in HORIZONS}

    for ticker, grp in prices.groupby("ticker"):
        g = grp.sort_values("date").reset_index(drop=True)
        closes = g["adj_close"].values
        dates = g["date"].values
        n = len(g)

        # only start dates within our study window count as "events"
        in_window = (dates >= START_DATE.to_datetime64()) & (dates <= END_DATE.to_datetime64())
        start_idxs = np.where(in_window)[0]

        for label, h in HORIZONS.items():
            target_idxs = start_idxs + h
            valid = target_idxs < n
            si = start_idxs[valid]
            ti = target_idxs[valid]
            entry = closes[si]
            fwd = closes[ti]
            mask = (entry > 0) & ~np.isnan(entry) & ~np.isnan(fwd)
            rets = fwd[mask] / entry[mask] - 1
            all_sums[label] += rets.sum()
            all_counts[label] += len(rets)

    print("Unconditional ('any random day') benchmark, equal-weighted across all ticker-days:")
    print(f"{'horizon':>8} {'mean_ret':>10} {'n_obs':>10}")
    bench = {}
    for label in HORIZONS:
        mean_ret = all_sums[label] / all_counts[label]
        bench[label] = mean_ret
        print(f"{label:>8} {mean_ret:>+10.4f} {all_counts[label]:>10}")

    pd.Series(bench).to_csv("data/unconditional_benchmark.csv", header=["mean_ret"])
    print("\nWrote data/unconditional_benchmark.csv")


if __name__ == "__main__":
    main()
