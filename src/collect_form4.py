"""
Collect Form 4 insider transactions (open-market P/S only) for the universe,
over the last 8 years, using SEC's official quarterly bulk structured datasets
(NONDERIV_TRANS.tsv / SUBMISSION.tsv / REPORTINGOWNER.tsv) instead of scraping
individual filing XMLs one by one.

Source: https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
"""
import argparse
import io
import zipfile
from datetime import date

import pandas as pd
import requests

HEADERS = {"User-Agent": "Research Project joaomatteop@gmail.com"}
BASE_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets"


def quarters_since(start_year: int, start_q: int) -> list[str]:
    today = date.today()
    end_year, end_q = today.year, (today.month - 1) // 3 + 1
    quarters = []
    y, q = start_year, start_q
    while (y, q) <= (end_year, end_q):
        quarters.append(f"{y}q{q}")
        q += 1
        if q > 4:
            q = 1
            y += 1
    return quarters


def fetch_quarter(quarter: str) -> dict | None:
    url = f"{BASE_URL}/{quarter}_form345.zip"
    r = requests.get(url, headers=HEADERS, timeout=60)
    if r.status_code != 200:
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))

    trans = pd.read_csv(z.open("NONDERIV_TRANS.tsv"), sep="\t", low_memory=False)
    trans = trans[trans["TRANS_CODE"].isin(["P", "S"])]

    subs = pd.read_csv(
        z.open("SUBMISSION.tsv"), sep="\t", low_memory=False,
        usecols=["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL"],
    )
    owners = pd.read_csv(
        z.open("REPORTINGOWNER.tsv"), sep="\t", low_memory=False,
        usecols=["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE"],
    )
    # a filing can have multiple reporting owners in rare joint-filing cases; keep first
    owners = owners.drop_duplicates(subset="ACCESSION_NUMBER", keep="first")

    merged = trans.merge(subs, on="ACCESSION_NUMBER", how="left").merge(owners, on="ACCESSION_NUMBER", how="left")
    return {"quarter": quarter, "data": merged}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--start-q", type=int, default=3)
    parser.add_argument("--out", default="data/form4_transactions_raw.csv")
    args = parser.parse_args()

    universe = pd.read_csv("data/universe.csv", dtype={"cik_padded": str})
    universe_ciks = set(universe["cik"].astype(int))

    quarters = quarters_since(args.start_year, args.start_q)
    print(f"Fetching {len(quarters)} quarterly bulk files: {quarters[0]} .. {quarters[-1]}", flush=True)

    all_frames = []
    for q in quarters:
        result = fetch_quarter(q)
        if result is None:
            print(f"  {q}: not available yet, skipping", flush=True)
            continue
        df = result["data"]
        df_universe = df[df["ISSUERCIK"].isin(universe_ciks)]
        all_frames.append(df_universe)
        print(f"  {q}: {len(df)} total P/S rows in bulk file, {len(df_universe)} in our universe", flush=True)

    combined = pd.concat(all_frames, ignore_index=True)
    combined.to_csv(args.out, index=False)
    print(f"\nWrote {len(combined)} P/S transactions for our universe to {args.out}")


if __name__ == "__main__":
    main()
