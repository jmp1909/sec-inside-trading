"""
Clean the raw Form 4 P/S transactions: parse dates properly, keep both
trans_date (when the insider actually traded) and filing_date (when the
market could have learned about it) -- filing_date is what we'll anchor
the eventual return analysis on, to avoid lookahead bias.
"""
import pandas as pd

df = pd.read_csv("data/form4_transactions_raw.csv", low_memory=False)

df["trans_date"] = pd.to_datetime(df["TRANS_DATE"], format="%d-%b-%Y", errors="coerce")
df["filing_date"] = pd.to_datetime(df["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
df["reporting_lag_days"] = (df["filing_date"] - df["trans_date"]).dt.days

keep = [
    "ACCESSION_NUMBER", "ISSUERCIK", "ISSUERTRADINGSYMBOL", "ISSUERNAME",
    "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE",
    "trans_date", "filing_date", "reporting_lag_days",
    "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE",
    "TRANS_ACQUIRED_DISP_CD", "SHRS_OWND_FOLWNG_TRANS", "DIRECT_INDIRECT_OWNERSHIP",
]
clean = df[keep].rename(columns={
    "ISSUERCIK": "issuer_cik", "ISSUERTRADINGSYMBOL": "ticker", "ISSUERNAME": "issuer_name",
    "RPTOWNERCIK": "owner_cik", "RPTOWNERNAME": "owner_name",
    "RPTOWNER_RELATIONSHIP": "owner_relationship", "RPTOWNER_TITLE": "owner_title",
    "TRANS_CODE": "trans_code", "TRANS_SHARES": "shares", "TRANS_PRICEPERSHARE": "price_per_share",
    "TRANS_ACQUIRED_DISP_CD": "acquired_disposed", "SHRS_OWND_FOLWNG_TRANS": "shares_owned_after",
    "DIRECT_INDIRECT_OWNERSHIP": "direct_indirect",
})
clean["trade_value"] = clean["shares"] * clean["price_per_share"]

clean.to_csv("data/form4_transactions_clean.csv", index=False)

print(f"Wrote {len(clean)} cleaned transactions to data/form4_transactions_clean.csv")
print(f"\nReporting lag stats (days between transaction and filing):")
print(clean["reporting_lag_days"].describe())
print(f"\nRows with lag > 30 days (late filers): {(clean['reporting_lag_days'] > 30).sum()}")
print(f"Rows with negative lag (data issue - filed before trade?): {(clean['reporting_lag_days'] < 0).sum()}")
