"""
Build the S&P MidCap 400 universe: ticker -> company name -> SEC CIK.
Current constituents only (survivorship bias flagged, see README).
"""
import io
import json
import time
import requests
import pandas as pd

HEADERS = {"User-Agent": "Research Project joaomatteop@gmail.com"}


def fetch_sp400_constituents() -> pd.DataFrame:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    # the constituents table is the first one with a 'Symbol' column
    for t in tables:
        if "Symbol" in t.columns:
            df = t[["Symbol", "Security", "GICS Sector"]].copy()
            df.columns = ["ticker", "name", "gics_sector"]
            return df
    raise RuntimeError("Could not find constituents table on Wikipedia page")


def fetch_sec_ticker_cik_map() -> dict:
    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    # data is {"0": {"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}, ...}
    return {row["ticker"].upper(): row["cik_str"] for row in data.values()}


def main():
    print("Fetching S&P MidCap 400 constituents from Wikipedia...")
    constituents = fetch_sp400_constituents()
    print(f"  got {len(constituents)} rows")

    print("Fetching SEC ticker->CIK map...")
    ticker_to_cik = fetch_sec_ticker_cik_map()
    print(f"  got {len(ticker_to_cik)} SEC-registered tickers")

    # SEC uses '-' where Wikipedia sometimes uses '.' (e.g. BRK.B vs BRK-B)
    def lookup_cik(ticker: str):
        t = ticker.upper()
        if t in ticker_to_cik:
            return ticker_to_cik[t]
        alt = t.replace(".", "-")
        if alt in ticker_to_cik:
            return ticker_to_cik[alt]
        return None

    constituents["cik"] = constituents["ticker"].apply(lookup_cik)
    matched = constituents[constituents["cik"].notna()].copy()
    unmatched = constituents[constituents["cik"].isna()].copy()

    matched["cik"] = matched["cik"].astype(int)
    matched["cik_padded"] = matched["cik"].apply(lambda c: str(c).zfill(10))

    print(f"\nMatched {len(matched)}/{len(constituents)} tickers to a CIK")
    if len(unmatched):
        print(f"Unmatched tickers ({len(unmatched)}):", list(unmatched["ticker"]))

    matched.to_csv("data/universe.csv", index=False)
    print("\nWrote data/universe.csv")
    print(matched.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
