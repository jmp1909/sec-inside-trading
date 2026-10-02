"""
Pull daily adjusted-close prices for the universe from Yahoo Finance's chart API,
concurrently with a shared rate limiter (unofficial endpoint, so kept conservative).

The point-in-time universe contains companies that were later acquired or delisted.
Yahoo often has no history for those, and sometimes the old ticker now belongs to a
different company. For every company that is no longer an index member, the name
Yahoo reports for the ticker is checked against the company name and the series is
rejected on a mismatch. Coverage (how many companies / member-days have prices) is
written to data/price_coverage.csv so the remaining gap is visible, not hidden.

Also pulls the MDY ETF (SPDR S&P MidCap 400) as an investable, survivorship-free
benchmark.
"""
import argparse
import threading
import time

import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import ETF_BENCHMARK, STUDY_END, STUDY_START, load_membership, name_similarity

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
RATE_PER_SEC = 5  # conservative -- unofficial endpoint, no published limit
MAX_WORKERS = 8
MIN_NAME_SIMILARITY = 0.5

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


def fetch_prices(ticker: str, yahoo_ticker: str, expected_name: str | None = None):
    """Returns (df or None, status)."""
    if not isinstance(yahoo_ticker, str) or not yahoo_ticker:
        return None, "no_symbol"
    _limiter.acquire()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
    params = {"period1": 0, "period2": int(time.time()), "interval": "1d"}
    try:
        r = _session.get(url, params=params, timeout=20)
    except requests.RequestException:
        return None, "request_error"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"
    d = r.json()
    result = d.get("chart", {}).get("result")
    if not result:
        return None, "empty"
    result = result[0]
    ts = result.get("timestamp")
    if not ts:
        return None, "empty"
    status = "ok"
    if expected_name:
        meta = result.get("meta", {})
        yahoo_name = meta.get("longName") or meta.get("shortName")
        if yahoo_name is None:
            status = "ok_name_unverified"
        elif name_similarity(expected_name, yahoo_name) < MIN_NAME_SIMILARITY:
            return None, f"name_mismatch:{yahoo_name}"
    adjclose = result["indicators"]["adjclose"][0]["adjclose"]
    df = pd.DataFrame({"date": pd.to_datetime(ts, unit="s").normalize(), "adj_close": adjclose})
    df["ticker"] = ticker
    df = df.dropna(subset=["adj_close"])
    return df, status


def coverage_report(universe: pd.DataFrame, prices: pd.DataFrame, statuses: dict) -> pd.DataFrame:
    """Share of point-in-time member-days (inside the study window) that have a price."""
    m = load_membership()
    days = pd.bdate_range(STUDY_START, STUDY_END)
    have = prices.groupby("ticker")["date"].agg(["min", "max"]) if len(prices) else pd.DataFrame(columns=["min", "max"])
    rows = []
    for row in universe.itertuples():
        iv = m[m["ticker"] == row.ticker]
        member_days = sum(((days >= r.start_date) & (days < r.end_date)).sum() for r in iv.itertuples())
        covered = 0
        if row.ticker in have.index:
            lo, hi = have.loc[row.ticker, "min"], have.loc[row.ticker, "max"]
            covered = sum(((days >= max(r.start_date, lo)) & (days < r.end_date) & (days <= hi)).sum()
                          for r in iv.itertuples())
        rows.append({"ticker": row.ticker, "name": row.name, "member_at_study_end": row.member_at_study_end,
                     "status": statuses.get(row.ticker, "not_requested"),
                     "member_days": member_days, "member_days_priced": covered})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="data/prices.csv")
    args = parser.parse_args()

    universe = pd.read_csv("data/universe.csv")
    if args.limit:
        universe = universe.head(args.limit)
    # renamed companies verified by hand (data/cik_overrides.csv) skip the name check
    verified = set(pd.read_csv("data/cik_overrides.csv")["ticker"])
    jobs = [(r.ticker, r.yahoo_ticker, None if (r.member_at_study_end or r.ticker in verified) else r.name)
            for r in universe.itertuples()]
    jobs.append((ETF_BENCHMARK, ETF_BENCHMARK, None))

    print(f"Fetching daily prices for {len(jobs)} tickers...", flush=True)
    t0 = time.time()
    frames = []
    statuses = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_prices, *job): job[0] for job in jobs}
        done = 0
        for fut in as_completed(futures):
            t = futures[fut]
            df, status = fut.result()
            done += 1
            if df is None or df.empty:
                statuses[t] = status if df is None else "empty"
            else:
                statuses[t] = status
                frames.append(df)
            if done % 25 == 0 or done == len(jobs):
                n_failed = sum(not v.startswith("ok") for v in statuses.values())
                print(f"  {done}/{len(jobs)} done, {n_failed} failed so far "
                      f"(elapsed {time.time()-t0:.0f}s)", flush=True)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    combined.to_csv(args.out, index=False)
    print(f"\nWrote {len(combined)} price rows for {combined['ticker'].nunique() if len(combined) else 0} tickers to {args.out}")
    failed = {t: s for t, s in statuses.items() if not s.startswith("ok")}
    if failed:
        print(f"No usable prices for {len(failed)} tickers: {failed}")

    cov = coverage_report(universe, combined, statuses)
    cov.to_csv("data/price_coverage.csv", index=False)
    removed = cov[~cov["member_at_study_end"]]
    print(f"\nPoint-in-time coverage: {cov['member_days_priced'].sum() / cov['member_days'].sum():.1%} of all "
          f"member-days priced; companies removed during the window: "
          f"{(removed['member_days_priced'] > 0).sum()}/{len(removed)} have prices "
          f"({removed['member_days_priced'].sum() / max(removed['member_days'].sum(), 1):.1%} of their member-days)")
    print("Wrote data/price_coverage.csv")
    print(f"Total time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
