"""
Build a proper 'unconditional' benchmark: forward returns at each horizon
starting from EVERY trading day for every universe member (not just days with
an insider filing), restricted to our 8-year study window. This is what "the
average mid-cap stock does over horizon h" actually looks like, uncontaminated
by the fact that insider-transaction days might systematically differ from
random days.

With --universe pit (default) a ticker-day only counts if the company was an index
member that day. Note this pooled benchmark still mixes different calendar periods;
the event study's main comparison is now the contemporaneous, same-window benchmark
computed per event in compute_returns.py (abn_* returns).
"""
import argparse

import numpy as np
import pandas as pd

from common import STUDY_END, STUDY_START, build_price_panel, load_prices_long, membership_mask, suffix
from compute_returns import HORIZONS, forward_return_panels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["pit", "current"], default="pit")
    args = parser.parse_args()

    prices = load_prices_long()
    panel, _ = build_price_panel(prices)
    fwd = forward_return_panels(panel)
    mask = membership_mask(panel.index, panel.columns, args.universe).to_numpy()
    in_window = ((panel.index >= STUDY_START) & (panel.index <= STUDY_END))[:, None]

    print(f"Unconditional ('any random day') benchmark, equal-weighted across all member-days "
          f"({args.universe} universe):")
    print(f"{'horizon':>8} {'mean_ret':>10} {'n_obs':>10}")
    bench = {}
    for label in HORIZONS:
        r = fwd[label][mask & in_window]
        r = r[~np.isnan(r)]
        bench[label] = r.mean()
        print(f"{label:>8} {r.mean():>+10.4f} {len(r):>10}")

    out = f"data/unconditional_benchmark{suffix(args.universe)}.csv"
    pd.Series(bench).to_csv(out, header=["mean_ret"])
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
