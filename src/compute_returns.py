"""
For each Form 4 filing, compute forward returns at multiple horizons, anchored
on filing_date (not transaction_date) to avoid lookahead bias -- see project notes.

Horizons: 1, 5, 10, 20 trading days, and ~6mo/1yr/2yr approximated as 126/252/504
trading days (21 trading days/month is the standard finance-industry approximation).
"""
import pandas as pd
import numpy as np

HORIZONS = {"1d": 1, "5d": 5, "10d": 10, "20d": 20, "6m": 126, "1y": 252, "2y": 504}


def main():
    txs = pd.read_csv("data/form4_transactions_clean.csv")
    txs["trans_date"] = pd.to_datetime(txs["trans_date"])
    txs["filing_date"] = pd.to_datetime(txs["filing_date"])

    # ISSUERTRADINGSYMBOL in the SEC bulk data is filer-entered free text (lowercase,
    # "NYSE:XXX" prefixes, multi-class tickers like "GEF,GEF.B", even literal "NONE").
    # Use issuer_cik -> our verified universe.csv ticker mapping instead of trusting it.
    universe = pd.read_csv("data/universe.csv")
    cik_to_ticker = dict(zip(universe["cik"], universe["ticker"]))
    txs["ticker"] = txs["issuer_cik"].map(cik_to_ticker)
    txs = txs.dropna(subset=["ticker"])

    prices = pd.read_csv("data/prices.csv")
    prices["date"] = pd.to_datetime(prices["date"], format="mixed")

    # index prices per ticker as a sorted array for fast positional lookup
    price_by_ticker = {}
    for ticker, grp in prices.groupby("ticker"):
        g = grp.sort_values("date").reset_index(drop=True)
        price_by_ticker[ticker] = g

    results = []
    missing_ticker = 0
    no_entry_price = 0

    for ticker, grp in txs.groupby("ticker"):
        pdf = price_by_ticker.get(ticker)
        if pdf is None:
            missing_ticker += len(grp)
            continue
        dates = pdf["date"].values
        closes = pdf["adj_close"].values
        n = len(dates)

        # searchsorted finds the first trading day >= filing_date (entry point)
        filing_dates = grp["filing_date"].values
        entry_idxs = np.searchsorted(dates, filing_dates, side="left")

        for row_i, entry_idx in zip(grp.index, entry_idxs):
            if entry_idx >= n:
                no_entry_price += 1
                continue
            entry_price = closes[entry_idx]
            if entry_price <= 0 or np.isnan(entry_price):
                no_entry_price += 1
                continue

            row_result = {"row_id": row_i}
            for label, h in HORIZONS.items():
                target_idx = entry_idx + h
                if target_idx < n:
                    fwd_price = closes[target_idx]
                    row_result[f"ret_{label}"] = fwd_price / entry_price - 1
                else:
                    row_result[f"ret_{label}"] = np.nan
            results.append(row_result)

    returns_df = pd.DataFrame(results).set_index("row_id")
    merged = txs.join(returns_df, how="left")
    merged.to_csv("data/form4_with_returns.csv", index=False)

    print(f"Computed returns for {len(returns_df)}/{len(txs)} transactions")
    print(f"  skipped (ticker has no price data): {missing_ticker}")
    print(f"  skipped (filing date after available price history): {no_entry_price}")
    print(f"\nReturn coverage by horizon (non-null count):")
    for label in HORIZONS:
        col = f"ret_{label}"
        print(f"  {label}: {merged[col].notna().sum()}/{len(merged)}")
    print(f"\nWrote data/form4_with_returns.csv")


if __name__ == "__main__":
    main()
