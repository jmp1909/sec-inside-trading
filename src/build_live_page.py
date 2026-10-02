"""
Build live-signal.html from the most recent snapshot in data/live/ (written by
live_signal.py). Run both after each refresh:

    python src/live_signal.py
    python src/build_live_page.py
"""
from pathlib import Path

import pandas as pd

from report_html import PAGE_FOOT, PAGE_HEAD, table

LOOKBACK_DAYS = 90
TOP = 25


def money(v):
    s = "&minus;" if v < 0 else "+"
    a = abs(v)
    if a >= 1e6:
        return f"{s}${a / 1e6:,.1f}M"
    if a >= 1e3:
        return f"{s}${a / 1e3:,.0f}K"
    return f"{s}${a:,.0f}"


def rows(df):
    return [[str(i + 1), r.ticker, money(r.net_dollar_value), str(r.n_purchases), str(r.n_sales),
             str(r.n_distinct_insiders)] for i, r in enumerate(df.itertuples())]


def main():
    snap = sorted(Path("data/live").glob("live_signal_*.csv"))[-1]
    as_of = snap.stem.replace("live_signal_", "")
    df = pd.read_csv(snap).sort_values("net_dollar_value", ascending=False)
    buys = df.head(TOP)
    sells = df.tail(TOP).iloc[::-1]
    header = ["#", "Ticker", "Net value", "Purchases", "Sales", "Insiders"]

    page = PAGE_HEAD.format(title="Insider buying snapshot") + f"""
<p class="small"><a href="index.html">&larr; Back to the report</a></p>
<h1>Insider buying snapshot</h1>
<p class="meta">As of {as_of} &middot; Form 4 filings from the previous {LOOKBACK_DAYS} days &middot; current S&amp;P MidCap 400 members</p>

<p>S&amp;P MidCap 400 companies ranked by net insider dollar value (open-market purchases minus sales) over the past
{LOOKBACK_DAYS} days. This is the ranking used in the report's portfolio test. The data come straight from individual
Form 4 filings, because SEC's bulk files used for the historical study are about a quarter behind.</p>

<div class="note">This is a snapshot, not a live feed. Insiders have to file a Form 4 within two business days of a
trade, so the underlying data are fresh when the script runs, but this page only changes when it is re-run. Each run is
saved in <code>data/live/</code>. In the <a href="index.html">report's</a> corrected backtest, a portfolio built on this
ranking did not beat the market, so treat this as information about insider activity, not as a trading signal.</div>

<p>{len(df)} companies had insider purchases or sales in the window: {(df.net_dollar_value > 0).sum()} with more buying
than selling, {(df.net_dollar_value < 0).sum()} with more selling. In total there were {df.n_purchases.sum():,}
purchases and {df.n_sales.sum():,} sales.</p>

<h2>Most net buying</h2>
{table(header, rows(buys))}
<p class="small">Reporting owners include large shareholders (over 10%) as well as officers and directors, so one big
block purchase can put a company at the top of the list.</p>

<h2>Most net selling</h2>
{table(header, rows(sells))}
<p class="small">Insiders sell for many reasons unrelated to their view of the company, such as taxes, diversification
or pre-planned 10b5-1 sales.</p>
""" + PAGE_FOOT
    Path("live-signal.html").write_text(page)
    print(f"Wrote live-signal.html from {snap}")


if __name__ == "__main__":
    main()
