"""
One-off data fix: 4 transactions (out of 87,528) have a price_per_share
wildly inconsistent with the real market price on that date -- clear
SEC-filing data-entry errors (e.g. a misplaced decimal), not a bug in our
pipeline. All 4 are sell transactions, so they only ever affected the
bottom of the net-dollar-value ranking (harmless for the "top N buys"
portfolio backtest), but they badly distort feature scaling for the ML
model. Recompute trade_value for these rows using the real market price.
"""
import pandas as pd

txs = pd.read_csv("data/event_study_final.csv")
txs["trans_date"] = pd.to_datetime(txs["trans_date"])

prices = pd.read_csv("data/prices.csv")
prices["date"] = pd.to_datetime(prices["date"], format="mixed")
prices_idx = prices.set_index(["ticker", "date"])["adj_close"]

merged = txs.merge(prices, left_on=["ticker", "trans_date"], right_on=["ticker", "date"],
                    how="left", suffixes=("", "_mkt"))
ratio = merged["price_per_share"] / merged["adj_close"]
bad_mask = ((ratio > 20) | (ratio < 0.05)) & (merged["price_per_share"] > 0)

print(f"Found {bad_mask.sum()} transactions with implausible price_per_share:")
print(merged.loc[bad_mask, ["ticker", "owner_name", "trans_code", "shares",
                             "price_per_share", "adj_close", "trade_value"]].to_string())

corrected_value = merged.loc[bad_mask, "shares"] * merged.loc[bad_mask, "adj_close"]
txs.loc[bad_mask, "trade_value"] = corrected_value.values
txs.loc[bad_mask, "price_per_share"] = merged.loc[bad_mask, "adj_close"].values

txs.to_csv("data/event_study_final.csv", index=False)
print(f"\nCorrected trade_value using real market price for {bad_mask.sum()} rows.")
print("Wrote data/event_study_final.csv")
