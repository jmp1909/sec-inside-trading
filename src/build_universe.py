"""
Build a point-in-time S&P MidCap 400 universe: which companies were in the index on
which dates, plus ticker -> company name -> SEC CIK for every one of them.

The original version used today's 400 constituents for the whole 8-year window,
which is survivorship bias in both directions: it drops companies that were mid-caps
then but later got acquired, delisted, or demoted, and it includes companies that only
joined the index *after* strong runs (promotions from the SmallCap 600 are mostly past
winners).

Method: start from the current constituent list and walk Wikipedia's "Selected past
and announced changes" table backwards in time, undoing each change. Ticker renames
and reused tickers are canonicalized with the hand-checked data/ticker_overrides.csv;
data/cik_overrides.csv covers renamed companies whose SEC name no longer matches.
The reconstruction is sanity-checked by printing the member count over time (it should
stay ~400; one-day 401s around spin-offs are real).

Outputs
  data/universe.csv             one row per company that was a member at any point in
                                the study window (superset of today's list)
  data/universe_membership.csv  membership intervals [start_date, end_date)

CIKs that can't be resolved from SEC's current company_tickers.json (typically
acquired / delisted companies) are filled in later by collect_form4.py from the
issuer symbols in SEC's Form 4 bulk data.
"""
import argparse
import io
import re

import pandas as pd
import requests

from common import HEADERS, STUDY_START, STUDY_END, name_similarity, yahoo_symbol

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
# walk changes back to a year before the study start so the starting membership is exact
WALK_FLOOR = STUDY_START - pd.DateOffset(years=1)
MIN_NAME_SIMILARITY = 0.6


def fetch_wikipedia_tables(html_path: str | None):
    if html_path:
        html = open(html_path, encoding="utf-8").read()
    else:
        r = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
    tables = pd.read_html(io.StringIO(html))
    current = changes = None
    for t in tables:
        cols = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
        if current is None and "Symbol" in cols and "Security" in cols:
            current = t[["Symbol", "Security", "GICS Sector"]].copy()
            current.columns = ["ticker", "name", "gics_sector"]
        elif changes is None and any("Added" in c for c in cols) and any("Removed" in c for c in cols):
            changes = t.copy()
            changes.columns = ["date", "added_ticker", "added_name", "removed_ticker", "removed_name", "reason"]
    if current is None or changes is None:
        raise RuntimeError("Could not find the constituents and changes tables on the Wikipedia page")
    changes["date"] = pd.to_datetime(
        changes["date"].astype(str).str.replace(r"\[.*?\]", "", regex=True).str.strip(), format="%B %d, %Y")
    for c in ["added_ticker", "removed_ticker"]:
        changes[c] = changes[c].map(lambda x: re.sub(r"\[.*?\]", "", x).strip() if isinstance(x, str) else None)
    return current, changes


def load_overrides(path="data/ticker_overrides.csv"):
    o = pd.read_csv(path, dtype=str)
    general = {r.ticker: r.canonical for r in o.itertuples() if pd.isna(r.date)}
    specific = {(r.ticker, pd.Timestamp(r.date), r.side): r.canonical for r in o.itertuples() if pd.notna(r.date)}
    return general, specific


def canonical(ticker, date, side, general, specific):
    if not isinstance(ticker, str) or not ticker:
        return None
    if (ticker, date, side) in specific:
        return specific[(ticker, date, side)]
    return general.get(ticker, ticker)


def reconstruct_membership(current: pd.DataFrame, changes: pd.DataFrame, as_of: pd.Timestamp):
    general, specific = load_overrides()
    names = dict(zip(current["ticker"], current["name"]))
    active = {t: None for t in current["ticker"]}  # ticker -> end_date of its open interval
    intervals, warnings, counts = [], [], []

    todo = changes[(changes["date"] <= as_of) & (changes["date"] >= WALK_FLOOR)]
    for date, grp in todo.sort_values("date", ascending=False).groupby("date", sort=False):
        for row in grp.itertuples():
            a = canonical(row.added_ticker, date, "added", general, specific)
            r = canonical(row.removed_ticker, date, "removed", general, specific)
            if a:
                names.setdefault(a, row.added_name)
                if a in active:
                    intervals.append({"ticker": a, "start_date": date, "end_date": active.pop(a)})
                else:
                    warnings.append(f"{date.date()} added {row.added_ticker} ({row.added_name}) was not a later member")
            if r:
                names.setdefault(r, row.removed_name)
                if r in active:
                    warnings.append(f"{date.date()} removed {row.removed_ticker} ({row.removed_name}) already active")
                else:
                    active[r] = date
        counts.append((date, len(active)))
    for t, end in active.items():
        intervals.append({"ticker": t, "start_date": pd.NaT, "end_date": end})

    membership = pd.DataFrame(intervals)
    membership["end_date"] = pd.to_datetime(membership["end_date"])
    membership["name"] = membership["ticker"].map(names)
    return membership, warnings, pd.DataFrame(counts, columns=["date", "n_members"])


def fetch_sec_ticker_map() -> pd.DataFrame:
    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=HEADERS, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json().values())
    df["ticker"] = df["ticker"].str.upper()
    return df.rename(columns={"cik_str": "cik", "title": "sec_name"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wiki-html", help="use a saved copy of the Wikipedia page instead of fetching it")
    parser.add_argument("--as-of", default=None, help="date the constituent list reflects (default: today)")
    args = parser.parse_args()
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.today().normalize()

    print("Fetching S&P MidCap 400 constituents + change history from Wikipedia...")
    current, changes = fetch_wikipedia_tables(args.wiki_html)
    print(f"  {len(current)} current constituents, {len(changes)} change rows "
          f"({changes['date'].min().date()} .. {changes['date'].max().date()})")

    membership, warnings, counts = reconstruct_membership(current, changes, as_of)
    in_window = counts[(counts["date"] >= STUDY_START) & (counts["date"] <= STUDY_END)]["n_members"]
    print(f"\nReconstructed member count inside study window: min {in_window.min()}, max {in_window.max()} "
          f"(should be ~400)")
    if warnings:
        print(f"{len(warnings)} reconstruction warnings (renames/reused tickers not in ticker_overrides.csv):")
        for w in warnings:
            print("   ", w)

    # keep only companies that were members at some point inside the study window
    start = membership["start_date"].fillna(pd.Timestamp("1900-01-01"))
    end = membership["end_date"].fillna(pd.Timestamp("2262-01-01"))
    membership = membership[(start <= STUDY_END) & (end > STUDY_START)].copy()
    start, end = start[membership.index], end[membership.index]

    companies = membership.groupby("ticker").agg(name=("name", "first")).reset_index()
    current_set = set(current["ticker"])
    companies["current_member"] = companies["ticker"].isin(current_set)
    at_end = membership[(start <= STUDY_END) & (end > STUDY_END)]["ticker"]
    companies["member_at_study_end"] = companies["ticker"].isin(set(at_end))
    companies = companies.merge(current[["ticker", "gics_sector"]], on="ticker", how="left")

    print("\nFetching SEC ticker->CIK map...")
    sec = fetch_sec_ticker_map().drop_duplicates("ticker")
    sec_by_ticker = sec.set_index("ticker")

    def resolve(row):
        if "~" in row.ticker:  # reused ticker: SEC's current map points at the successor company
            return pd.Series({"cik": None, "cik_source": None})
        for t in (row.ticker.upper(), row.ticker.upper().replace(".", "-"), row.ticker.upper().replace("/", "-")):
            if t in sec_by_ticker.index:
                hit = sec_by_ticker.loc[t]
                # current members are trusted (same as the original pipeline); removed names must
                # also match on company name, otherwise the ticker has likely been reused
                if row.current_member or name_similarity(row["name"], hit["sec_name"]) >= MIN_NAME_SIMILARITY:
                    return pd.Series({"cik": int(hit["cik"]), "cik_source": "company_tickers"})
        return pd.Series({"cik": None, "cik_source": None})

    companies[["cik", "cik_source"]] = companies.apply(resolve, axis=1)
    # hand-verified renames where the SEC legal name no longer resembles the index name
    overrides = pd.read_csv("data/cik_overrides.csv")
    for o in overrides.itertuples():
        hit = companies["ticker"] == o.ticker
        if hit.any() and companies.loc[hit, "cik"].isna().all():
            companies.loc[hit, ["cik", "cik_source"]] = [o.cik, "cik_overrides"]
    companies["cik"] = companies["cik"].astype("Int64")
    companies["cik_padded"] = companies["cik"].map(lambda c: f"{int(c):010d}" if pd.notna(c) else None)
    companies["yahoo_ticker"] = companies["ticker"].map(lambda t: None if "~" in t else yahoo_symbol(t))

    n_unres = companies["cik"].isna().sum()
    print(f"\n{len(companies)} companies were S&P 400 members at some point in "
          f"{STUDY_START.date()}..{STUDY_END.date()} ({companies['member_at_study_end'].sum()} at the end, "
          f"{(~companies['member_at_study_end']).sum()} removed along the way)")
    print(f"CIK resolved for {len(companies) - n_unres}; {n_unres} left for collect_form4.py to resolve "
          f"from Form 4 issuer symbols: {sorted(companies.loc[companies['cik'].isna(), 'ticker'])}")

    cols = ["ticker", "name", "gics_sector", "cik", "cik_padded", "cik_source", "yahoo_ticker",
            "current_member", "member_at_study_end"]
    companies[cols].to_csv("data/universe.csv", index=False)
    membership[["ticker", "name", "start_date", "end_date"]].sort_values(["ticker", "start_date"]).to_csv(
        "data/universe_membership.csv", index=False, date_format="%Y-%m-%d")
    print("\nWrote data/universe.csv and data/universe_membership.csv")


if __name__ == "__main__":
    main()
