"""
Scan the universe for companies that filed for Chapter 11 (or receivership) during
our study window, via 8-K Item 1.03 ("Bankruptcy or Receivership") filings.
Each hit's 8-K was read by hand: filings about a subsidiary's bankruptcy (or mis-tagged
filings) are listed in data/bankruptcy_false_positives.csv and dropped here. For the
remaining companies the price series stops at the petition date with a delisting
return (see common.load_prices_long), because pre/post-reorganization prices are not
a continuous return series.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests

from common import STUDY_END, STUDY_START

HEADERS = {"User-Agent": "Research Project joaomatteop@gmail.com"}
RATE_PER_SEC = 9
MAX_WORKERS = 15
START_DATE = STUDY_START.date().isoformat()
END_DATE = STUDY_END.date().isoformat()

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


def check_bankruptcy(cik_padded: str, ticker: str):
    _limiter.acquire()
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    r = _session.get(url, timeout=20)
    if r.status_code != 200:
        return None
    d = r.json()
    recent = d["filings"]["recent"]
    hits = []
    for i in range(len(recent["form"])):
        if recent["form"][i] != "8-K":
            continue
        items = recent["items"][i] or ""
        if "1.03" in items.split(","):
            fdate = recent["filingDate"][i]
            if START_DATE <= fdate <= END_DATE:
                hits.append(fdate)
    if hits:
        return {"ticker": ticker, "cik": cik_padded, "bankruptcy_8k_dates": hits}
    return None


def main():
    universe = pd.read_csv("data/universe.csv", dtype={"cik_padded": str})
    universe = universe[universe["cik_padded"].notna()]
    print(f"Scanning {len(universe)} companies for Item 1.03 (bankruptcy) 8-Ks since {START_DATE}...", flush=True)

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(check_bankruptcy, row["cik_padded"], row["ticker"]): row["ticker"]
            for _, row in universe.iterrows()
        }
        done = 0
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)
                print(f"  BANKRUPTCY FOUND: {res['ticker']} on {res['bankruptcy_8k_dates']}", flush=True)
            done += 1
            if done % 100 == 0 or done == len(universe):
                print(f"  scanned {done}/{len(universe)} (elapsed {time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(results)
    fp = pd.read_csv("data/bankruptcy_false_positives.csv")
    dropped = out[out["ticker"].isin(fp["ticker"])]
    if len(dropped):
        print(f"Dropping {len(dropped)} verified false positives (subsidiary filings etc.): {list(dropped['ticker'])}")
    out = out[~out["ticker"].isin(fp["ticker"])].sort_values("ticker")
    out.to_csv("data/bankruptcies.csv", index=False)
    print(f"\nFound {len(out)} companies with Item 1.03 filings in the window")
    print(f"Wrote data/bankruptcies.csv")
    print(f"Total time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
