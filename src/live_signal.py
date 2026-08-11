"""
Live insider-buying signal: today's ranked list of S&P MidCap 400 companies
by trailing net insider dollar value, using the same methodology validated
in the backtest (net dollar value, 3-month window, top 50).

Unlike the historical pipeline, this does NOT use SEC's bulk quarterly files
(those lag by roughly a quarter). It scrapes individual Form 4 filings
directly, but only within the trailing window, which keeps it fast: a few
thousand filings across 400 companies, not the ~165,000 a full 8-year scrape
would require.

Run this periodically (e.g. weekly) to get a fresh signal. Each run is saved
as a dated snapshot in data/live/, so re-running builds a track record.
"""
import argparse
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

HEADERS = {"User-Agent": "Research Project joaomatteop@gmail.com"}
RATE_PER_SEC = 9
MAX_WORKERS = 20
LOOKBACK_DAYS = 90  # matches the 3-month window that performed best in the backtest
TOP_N = 50

_session = requests.Session()
_session.headers.update(HEADERS)


class RateLimiter:
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.next_time = time.time()

    def acquire(self):
        with self.lock:
            now = time.time()
            wait = self.next_time - now
            if wait > 0:
                time.sleep(wait)
                now = time.time()
            self.next_time = max(now, self.next_time) + self.interval


_limiter = RateLimiter(RATE_PER_SEC)


def throttled_get(url, **kwargs):
    _limiter.acquire()
    return _session.get(url, timeout=20, **kwargs)


def list_recent_form4(cik_padded: str, start_date: str) -> list[dict]:
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    r = throttled_get(url)
    if r.status_code != 200:
        return []
    recent = r.json()["filings"]["recent"]
    results = []
    for i in range(len(recent["form"])):
        if recent["form"][i] != "4":
            continue
        fdate = recent["filingDate"][i]
        if fdate >= start_date:
            results.append({
                "accession": recent["accessionNumber"][i],
                "primary_doc": recent["primaryDocument"][i],
                "filing_date": fdate,
            })
    return results


def parse_form4_xml(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    def text_of(elem, path):
        node = elem.find(path)
        return node.text if node is not None else None

    owner_name = text_of(root, "reportingOwner/reportingOwnerId/rptOwnerName")
    officer_title = text_of(root, "reportingOwner/reportingOwnerRelationship/officerTitle")

    out = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = text_of(tx, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        shares = text_of(tx, "transactionAmounts/transactionShares/value")
        price = text_of(tx, "transactionAmounts/transactionPricePerShare/value")
        out.append({
            "owner_name": owner_name,
            "officer_title": officer_title,
            "trans_code": code,
            "trans_date": text_of(tx, "transactionDate/value"),
            "shares": shares,
            "price_per_share": price,
        })
    return out


def fetch_and_parse_filing(job: dict) -> list[dict]:
    acc_nodash = job["accession"].replace("-", "")
    basename = job["primary_doc"].split("/")[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/{job['cik_int']}/{acc_nodash}/{basename}"
    r = throttled_get(url)
    if r.status_code != 200:
        return []
    txs = parse_form4_xml(r.text)
    for tx in txs:
        tx["ticker"] = job["ticker"]
        tx["filing_date"] = job["filing_date"]
    return txs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    parser.add_argument("--top-n", type=int, default=TOP_N)
    args = parser.parse_args()

    universe = pd.read_csv("data/universe.csv", dtype={"cik_padded": str})
    start_date = (date.today() - timedelta(days=args.lookback_days)).isoformat()
    today = date.today().isoformat()

    print(f"Scanning {len(universe)} companies for Form 4 filings since {start_date}...", flush=True)
    t0 = time.time()

    jobs = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(list_recent_form4, row["cik_padded"], start_date): row
            for _, row in universe.iterrows()
        }
        done = 0
        for fut in as_completed(futures):
            row = futures[fut]
            for f in fut.result():
                jobs.append({**f, "cik_int": int(row["cik_padded"]), "ticker": row["ticker"]})
            done += 1
            if done % 100 == 0 or done == len(universe):
                print(f"  listed {done}/{len(universe)} companies, {len(jobs)} filings found "
                      f"(elapsed {time.time()-t0:.0f}s)", flush=True)

    print(f"\nFetching {len(jobs)} filings...", flush=True)
    all_rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_and_parse_filing, job) for job in jobs]
        done = 0
        for fut in as_completed(futures):
            all_rows.extend(fut.result())
            done += 1
            if done % 200 == 0 or done == len(jobs):
                print(f"  fetched {done}/{len(jobs)} (elapsed {time.time()-t0:.0f}s)", flush=True)

    txs = pd.DataFrame(all_rows)
    if txs.empty:
        print("No P/S transactions found in this window.")
        return

    txs["shares"] = pd.to_numeric(txs["shares"], errors="coerce")
    txs["price_per_share"] = pd.to_numeric(txs["price_per_share"], errors="coerce")
    txs["trade_value"] = txs["shares"] * txs["price_per_share"]
    txs["signed_value"] = txs["trade_value"].where(txs["trans_code"] == "P", -txs["trade_value"])

    signal = txs.groupby("ticker").agg(
        net_dollar_value=("signed_value", "sum"),
        n_purchases=("trans_code", lambda s: (s == "P").sum()),
        n_sales=("trans_code", lambda s: (s == "S").sum()),
        n_distinct_insiders=("owner_name", "nunique"),
    ).sort_values("net_dollar_value", ascending=False)

    top = signal.head(args.top_n).reset_index()
    print(f"\nTop {args.top_n} by trailing {args.lookback_days}-day net insider dollar value (as of {today}):\n")
    print(top.to_string(index=False))

    out_dir = Path("data/live")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"live_signal_{today}.csv"
    signal.reset_index().to_csv(out_path, index=False)
    print(f"\nWrote full ranked signal ({len(signal)} companies) to {out_path}")
    print(f"Total time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
