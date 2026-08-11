"""
Pull daily adjusted-close prices for the universe from Yahoo Finance's chart API,
concurrently with a shared rate limiter (unofficial endpoint, so kept conservative).
"""
import argparse
import threading
import time

import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
RATE_PER_SEC = 5  # conservative -- unofficial endpoint, no published limit
MAX_WORKERS = 8

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


def fetch_prices(ticker: str) -> pd.DataFrame | None:
    _limiter.acquire()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"period1": 0, "period2": int(time.time()), "interval": "1d"}
    try:
        r = _session.get(url, params=params, timeout=20)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    d = r.json()
    result = d.get("chart", {}).get("result")
    if not result:
        return None
    result = result[0]
    ts = result.get("timestamp")
    if not ts:
        return None
    adjclose = result["indicators"]["adjclose"][0]["adjclose"]
    df = pd.DataFrame({"date": pd.to_datetime(ts, unit="s").normalize(), "adj_close": adjclose})
    df["ticker"] = ticker
    df = df.dropna(subset=["adj_close"])
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="data/prices.csv")
    args = parser.parse_args()

    universe = pd.read_csv("data/universe.csv")
    tickers = universe["ticker"].tolist()
    if args.limit:
        tickers = tickers[: args.limit]

    print(f"Fetching daily prices for {len(tickers)} tickers...", flush=True)
    t0 = time.time()
    frames = []
    failed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_prices, t): t for t in tickers}
        done = 0
        for fut in as_completed(futures):
            t = futures[fut]
            df = fut.result()
            done += 1
            if df is None or df.empty:
                failed.append(t)
            else:
                frames.append(df)
            if done % 25 == 0 or done == len(tickers):
                print(f"  {done}/{len(tickers)} done, {len(failed)} failed so far "
                      f"(elapsed {time.time()-t0:.0f}s)", flush=True)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    combined.to_csv(args.out, index=False)
    print(f"\nWrote {len(combined)} price rows for {combined['ticker'].nunique() if len(combined) else 0} tickers to {args.out}")
    if failed:
        print(f"Failed tickers ({len(failed)}): {failed}")
    print(f"Total time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
