"""
Collect Form 4 insider transactions (open-market P/S only) for the universe,
over the last 8 years, using SEC's official quarterly bulk structured datasets
(NONDERIV_TRANS.tsv / SUBMISSION.tsv / REPORTINGOWNER.tsv) instead of scraping
individual filing XMLs one by one.

The point-in-time universe includes companies that were later acquired or delisted,
whose tickers are no longer in SEC's current company_tickers.json. Their CIKs are
resolved here from the issuer trading symbols that filers typed into the Form 4s
themselves (SUBMISSION.tsv), restricted to the company's membership window and
cross-checked on issuer name, then written back to data/universe.csv.

Quarterly zips are cached in data/sec_bulk/ (gitignored) so reruns don't refetch.

Source: https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
"""
import argparse
import io
import re
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from common import HEADERS, name_similarity

BASE_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets"
CACHE_DIR = Path("data/sec_bulk")
MIN_NAME_SIMILARITY = 0.6


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


def quarter_start(quarter: str) -> pd.Timestamp:
    y, q = int(quarter[:4]), int(quarter[-1])
    return pd.Timestamp(year=y, month=3 * (q - 1) + 1, day=1)


def fetch_zip(quarter: str) -> zipfile.ZipFile | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{quarter}_form345.zip"
    if not path.exists():
        r = requests.get(f"{BASE_URL}/{quarter}_form345.zip", headers=HEADERS, timeout=120)
        if r.status_code != 200:
            return None
        path.write_bytes(r.content)
    return zipfile.ZipFile(io.BytesIO(path.read_bytes()))


def normalize_symbols(raw) -> list[str]:
    """ISSUERTRADINGSYMBOL is free text: 'nyse:xyz', 'GEF, GEF.B', 'NONE', ... -> ['XYZ']"""
    if not isinstance(raw, str):
        return []
    s = raw.upper()
    s = re.sub(r"\b(NYSE|NASDAQ|NASD|AMEX|NYSEMKT|NYSE AMERICAN|OTC)\s*[:\-]\s*", "", s)
    out = []
    for tok in re.split(r"[,;/\s]+", s):
        tok = tok.strip(" .()")
        if tok and tok not in {"NONE", "N/A", "NA"}:
            out.append(tok)
    return out


def read_quarter(z: zipfile.ZipFile):
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
    return merged, subs


def symbol_table(subs: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """(symbol, cik, issuer name, quarter, n_filings) for every issuer filing in the quarter."""
    s = subs[["ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL"]].copy()
    s["symbol"] = s["ISSUERTRADINGSYMBOL"].map(normalize_symbols)
    s = s.explode("symbol").dropna(subset=["symbol"])
    g = s.groupby(["symbol", "ISSUERCIK"]).agg(issuer_name=("ISSUERNAME", "first"), n_filings=("ISSUERNAME", "size"))
    g = g.reset_index().rename(columns={"ISSUERCIK": "cik"})
    g["quarter_start"] = quarter_start(quarter)
    return g


def resolve_missing_ciks(universe: pd.DataFrame, symbols: pd.DataFrame) -> pd.DataFrame:
    membership = pd.read_csv("data/universe_membership.csv", parse_dates=["start_date", "end_date"])
    universe = universe.copy()
    resolved, failed = [], []
    for i, row in universe[universe["cik"].isna()].iterrows():
        base = row["ticker"].split("~")[0].upper()
        cands = {base, base.replace(".", "-"), base.replace(".", ""), *base.split("/")}
        iv = membership[membership["ticker"] == row["ticker"]]
        lo = iv["start_date"].min() - pd.DateOffset(years=1) if iv["start_date"].notna().all() else pd.Timestamp("1900-01-01")
        hi = iv["end_date"].max() + pd.DateOffset(months=3) if iv["end_date"].notna().all() else pd.Timestamp("2262-01-01")
        hits = symbols[symbols["symbol"].isin(cands) & (symbols["quarter_start"] >= lo) & (symbols["quarter_start"] <= hi)]
        if hits.empty:
            failed.append(row["ticker"])
            continue
        by_cik = hits.groupby("cik").agg(n=("n_filings", "sum"), issuer_name=("issuer_name", "first")).sort_values("n", ascending=False)
        best_cik, best = by_cik.index[0], by_cik.iloc[0]
        if name_similarity(row["name"], best["issuer_name"]) < MIN_NAME_SIMILARITY:
            failed.append(f"{row['ticker']} (symbol matched '{best['issuer_name']}', name mismatch)")
            continue
        universe.loc[i, ["cik", "cik_padded", "cik_source"]] = [int(best_cik), f"{int(best_cik):010d}", "form4_symbol"]
        resolved.append(row["ticker"])
    print(f"Resolved {len(resolved)} more CIKs from Form 4 issuer symbols; {len(failed)} still unresolved:")
    for f in failed:
        print("   ", f)
    return universe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--start-q", type=int, default=3)
    parser.add_argument("--out", default="data/form4_transactions_raw.csv")
    args = parser.parse_args()

    quarters = quarters_since(args.start_year, args.start_q)
    print(f"Fetching {len(quarters)} quarterly bulk files: {quarters[0]} .. {quarters[-1]}", flush=True)

    universe = pd.read_csv("data/universe.csv", dtype={"cik_padded": str})
    known_ciks = set(universe["cik"].dropna().astype(int))
    # symbols of the not-yet-resolved companies: keep their candidate issuers' rows too,
    # so the whole national file never has to sit in memory
    unresolved_symbols = set()
    for t in universe.loc[universe["cik"].isna(), "ticker"]:
        b = t.split("~")[0].upper()
        unresolved_symbols |= {b, b.replace(".", "-"), b.replace(".", ""), *b.split("/")}

    trans_frames, symbol_frames = [], []
    for q in quarters:
        z = fetch_zip(q)
        if z is None:
            print(f"  {q}: not available yet, skipping", flush=True)
            continue
        merged, subs = read_quarter(z)
        sym = symbol_table(subs, q)
        symbol_frames.append(sym)
        keep = known_ciks | set(sym.loc[sym["symbol"].isin(unresolved_symbols), "cik"])
        trans_frames.append(merged[merged["ISSUERCIK"].isin(keep)])
        print(f"  {q}: {len(merged)} total P/S rows in bulk file, {len(trans_frames[-1])} kept", flush=True)

    symbols = pd.concat(symbol_frames, ignore_index=True)
    if universe["cik"].isna().any():
        universe = resolve_missing_ciks(universe, symbols)
        universe["cik"] = universe["cik"].astype("Int64")
        universe.to_csv("data/universe.csv", index=False)
        print("Updated data/universe.csv with the newly resolved CIKs")

    universe_ciks = set(universe["cik"].dropna().astype(int))
    combined = pd.concat(trans_frames, ignore_index=True)
    combined = combined[combined["ISSUERCIK"].isin(universe_ciks)]
    combined.to_csv(args.out, index=False)
    print(f"\nWrote {len(combined)} P/S transactions for our universe to {args.out}")


if __name__ == "__main__":
    main()
