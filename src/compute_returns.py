"""
For each Form 4 filing, compute forward returns at multiple horizons, anchored
on filing_date (not transaction_date) to avoid lookahead bias -- see project notes.

Horizons: 1, 5, 10, 20 trading days, and ~6mo/1yr/2yr approximated as 126/252/504
trading days (21 trading days/month is the standard finance-industry approximation).

Changes vs the first version:
  * Entry is the close of the first trading day *after* the filing date by default
    (--entry next_day). Form 4s are frequently accepted after the 4pm close, so
    entering at the filing day's own close is a small lookahead.
  * Prices sit on a common trading calendar and a stock that stops trading (acquired,
    delisted) keeps its last price, so its return runs to the delisting date instead of
    the event silently dropping out at long horizons.
  * Each event also gets a contemporaneous benchmark: the equal-weighted average return
    of all universe members (as of the entry date) over the *same* window. abn_<h> =
    ret_<h> - bench_<h> is the market-adjusted return, so a rising market (2019-2021,
    2023-2025) can't masquerade as insider skill. Both the point-in-time (bench_pit_*)
    and the original current-constituent (bench_current_*) versions are stored.
"""
import argparse
import warnings

import numpy as np
import pandas as pd

from common import build_price_panel, is_member_on, load_membership, load_prices_long, membership_mask

HORIZONS = {"1d": 1, "5d": 5, "10d": 10, "20d": 20, "6m": 126, "1y": 252, "2y": 504}


def forward_return_panels(panel: pd.DataFrame) -> dict:
    vals = panel.to_numpy()
    out = {}
    for label, h in HORIZONS.items():
        fwd = np.full_like(vals, np.nan)
        if h < len(vals):
            fwd[:-h] = vals[h:] / vals[:-h] - 1
        out[label] = fwd
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", choices=["next_day", "same_day"], default="next_day")
    args = parser.parse_args()

    txs = pd.read_csv("data/form4_transactions_clean.csv")
    txs["trans_date"] = pd.to_datetime(txs["trans_date"])
    txs["filing_date"] = pd.to_datetime(txs["filing_date"])

    # ISSUERTRADINGSYMBOL in the SEC bulk data is filer-entered free text (lowercase,
    # "NYSE:XXX" prefixes, multi-class tickers like "GEF,GEF.B", even literal "NONE").
    # Use issuer_cik -> our verified universe.csv ticker mapping instead of trusting it.
    universe = pd.read_csv("data/universe.csv").dropna(subset=["cik"])
    universe["cik"] = universe["cik"].astype(int)
    txs["ticker"] = txs["issuer_cik"].map(universe.drop_duplicates("cik", keep="first").set_index("cik")["ticker"])
    # a CIK can sit behind two index tickers over time (e.g. Chemical Financial CHFC was
    # renamed TCF in 2019): use whichever ticker was the index member on the filing date
    shared = universe[universe["cik"].duplicated(keep=False)]
    if len(shared):
        membership = load_membership()
        for cik, grp in shared.groupby("cik"):
            iv = membership[membership["ticker"].isin(grp["ticker"])]
            rows = txs.index[txs["issuer_cik"] == cik]
            for i in rows:
                d = txs.at[i, "filing_date"]
                dist = np.where(d < iv["start_date"], (iv["start_date"] - d).dt.days,
                                np.where(d >= iv["end_date"], (d - iv["end_date"]).dt.days, 0))
                txs.at[i, "ticker"] = iv["ticker"].iloc[int(np.argmin(dist))]
    txs = txs.dropna(subset=["ticker"]).reset_index(drop=True)

    prices = load_prices_long()
    panel, last_valid = build_price_panel(prices)
    dates = panel.index
    fwd = forward_return_panels(panel)
    col_idx = {t: i for i, t in enumerate(panel.columns)}

    # contemporaneous equal-weighted benchmark, per entry date and horizon
    bench = {}
    for mode in ("pit", "current"):
        mask = membership_mask(dates, panel.columns, mode).to_numpy()
        for label in HORIZONS:
            r = np.where(mask, fwd[label], np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN rows near the data end
                bench[(mode, label)] = np.nanmean(r, axis=1)

    side = "right" if args.entry == "next_day" else "left"
    entry_pos = np.searchsorted(dates.values, txs["filing_date"].values, side=side)

    results = {f"ret_{h}": np.full(len(txs), np.nan) for h in HORIZONS}
    for mode in ("pit", "current"):
        for h in HORIZONS:
            results[f"bench_{mode}_{h}"] = np.full(len(txs), np.nan)
    entry_date = np.full(len(txs), np.datetime64("NaT"), dtype="datetime64[ns]")
    missing_ticker = no_entry_price = 0

    for i, (ticker, pos) in enumerate(zip(txs["ticker"], entry_pos)):
        j = col_idx.get(ticker)
        if j is None:
            missing_ticker += 1
            continue
        if pos >= len(dates) or np.isnan(panel.iat[pos, j]) or dates[pos] > last_valid[ticker]:
            no_entry_price += 1
            continue
        entry_date[i] = dates[pos]
        for h in HORIZONS:
            results[f"ret_{h}"][i] = fwd[h][pos, j]
            for mode in ("pit", "current"):
                results[f"bench_{mode}_{h}"][i] = bench[(mode, h)][pos]

    out = txs.assign(entry_date=entry_date, **results)
    for h in HORIZONS:  # bench_* is only meaningful where the stock's own return exists
        for mode in ("pit", "current"):
            out.loc[out[f"ret_{h}"].isna(), f"bench_{mode}_{h}"] = np.nan
    out["price_series_end"] = out["ticker"].map(last_valid)
    out["member_pit"] = is_member_on(out["ticker"], out["filing_date"], "pit")
    out["member_current"] = is_member_on(out["ticker"], out["filing_date"], "current")
    out.to_csv("data/form4_with_returns.csv", index=False)

    print(f"Entry convention: {args.entry}")
    print(f"Computed returns for {out['entry_date'].notna().sum()}/{len(txs)} transactions")
    print(f"  skipped (ticker has no price data): {missing_ticker}")
    print(f"  skipped (no price on/after filing date): {no_entry_price}")
    print(f"  filed while a point-in-time index member: {out['member_pit'].sum()}")
    print(f"\nReturn coverage by horizon (non-null count):")
    for label in HORIZONS:
        col = f"ret_{label}"
        print(f"  {label}: {out[col].notna().sum()}/{len(out)}")
    print(f"\nWrote data/form4_with_returns.csv")


if __name__ == "__main__":
    main()
