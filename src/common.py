"""
Shared constants and helpers used across the pipeline: study window, point-in-time
universe membership, wide price panel, Fama-French factors, and performance stats.

Two universe modes are supported by every analysis script (--universe):
  pit      point-in-time S&P MidCap 400 membership (default). A company only counts
           (as an event, a portfolio candidate, or a benchmark member) on dates when
           it was actually in the index. Removed / acquired / delisted names are kept.
  current  the original methodology: the companies that were members at the end of
           the study window, applied retroactively to the whole period. Kept only so
           the size of the survivorship bias can be measured (pit minus current).
"""
import re
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

HEADERS = {"User-Agent": "Research Project joaomatteop@gmail.com"}

STUDY_START = pd.Timestamp("2018-08-13")
STUDY_END = pd.Timestamp("2026-08-11")
# first/last monthly rebalance; 6 months after STUDY_START leaves room for the longest lookback
BACKTEST_START = pd.Timestamp("2019-02-01")
BACKTEST_END = pd.Timestamp("2026-07-01")

# investable, survivorship-free benchmark: SPDR S&P MidCap 400 ETF (cap-weighted, net of its fee)
ETF_BENCHMARK = "MDY"

UNIVERSE_MODES = ("pit", "current")


# ---------------------------------------------------------------- names / tickers

_NAME_STOPWORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc",
    "holdings", "holding", "group", "the", "trust", "sa", "nv", "lp", "llc", "class", "a", "b",
    "new", "de", "international", "intl",
}


def normalize_name(name) -> str:
    if not isinstance(name, str):
        return ""
    s = re.sub(r"\[.*?\]", "", name.lower()).replace("'", "").replace("\u2019", "")  # Casey's -> caseys
    s = re.sub(r"[^a-z0-9 ]+", " ", s.replace("&", " and "))
    return " ".join(t for t in s.split() if t not in _NAME_STOPWORDS)


def name_similarity(a, b) -> float:
    """0..1 similarity between two company names, robust to Inc/Corp/punctuation noise."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    containment = len(ta & tb) / min(len(ta), len(tb))
    return max(SequenceMatcher(None, na, nb).ratio(), containment)


def yahoo_symbol(ticker: str) -> str:
    # Yahoo uses '-' for share classes (MOG.A -> MOG-A, BRK.B -> BRK-B)
    return ticker.replace(".", "-").replace("/", "-")


# ---------------------------------------------------------------- universe

def load_universe() -> pd.DataFrame:
    return pd.read_csv("data/universe.csv", dtype={"cik_padded": str})


def load_membership() -> pd.DataFrame:
    m = pd.read_csv("data/universe_membership.csv", parse_dates=["start_date", "end_date"])
    m["start_date"] = m["start_date"].fillna(pd.Timestamp("1900-01-01"))
    m["end_date"] = m["end_date"].fillna(pd.Timestamp("2262-01-01"))
    return m


def universe_tickers(mode: str) -> list:
    u = load_universe()
    if mode == "current":
        u = u[u["member_at_study_end"]]
    return sorted(u["ticker"].dropna().unique())


def membership_mask(dates: pd.DatetimeIndex, tickers, mode: str) -> pd.DataFrame:
    """Boolean (date x ticker) frame: True where the ticker counts as a universe member.

    Membership intervals are [start_date, end_date): a company added on D is a member
    from D on; a company removed on D is no longer a member on D.
    """
    tickers = list(tickers)
    mask = pd.DataFrame(False, index=dates, columns=tickers)
    if mode == "current":
        current = set(universe_tickers("current"))
        for t in tickers:
            if t in current:
                mask[t] = True
        return mask
    m = load_membership()
    m = m[m["ticker"].isin(tickers)]
    d = dates.values
    for row in m.itertuples(index=False):
        sel = (d >= row.start_date.to_datetime64()) & (d < row.end_date.to_datetime64())
        mask.loc[sel, row.ticker] = True
    return mask


def is_member_on(tickers: pd.Series, dates: pd.Series, mode: str) -> np.ndarray:
    """Vectorized point-in-time membership test for (ticker, date) pairs."""
    if mode == "current":
        return tickers.isin(set(universe_tickers("current"))).to_numpy()
    m = load_membership()
    df = pd.DataFrame({"ticker": tickers.to_numpy(), "date": pd.to_datetime(dates).to_numpy(),
                       "_i": np.arange(len(tickers))})
    j = df.merge(m, on="ticker", how="inner")
    hit = j[(j["date"] >= j["start_date"]) & (j["date"] < j["end_date"])]["_i"].unique()
    out = np.zeros(len(tickers), dtype=bool)
    out[hit] = True
    return out


def suffix(mode: str) -> str:
    return "" if mode == "pit" else f"_{mode}"


# ---------------------------------------------------------------- prices

def load_prices_long() -> pd.DataFrame:
    prices = pd.read_csv("data/prices.csv")
    prices["date"] = pd.to_datetime(prices["date"], format="mixed")
    return prices


def build_price_panel(prices: pd.DataFrame):
    """Wide (date x ticker) adjusted-close panel on a common trading calendar.

    After a stock's last real print (acquisition, delisting) its last price is carried
    forward, i.e. the position is treated as converted to cash at the final close rather
    than silently dropped -- dropping it would be survivorship bias inside the backtest.
    Returns (panel, last_valid_date per ticker).
    """
    wide = prices.pivot_table(index="date", columns="ticker", values="adj_close", aggfunc="last").sort_index()
    last_valid = wide.apply(lambda s: s.last_valid_index())
    wide = wide.ffill()
    first_valid = prices.groupby("ticker")["date"].min()
    for t in wide.columns:  # ffill must never back-propagate before the first real print
        wide.loc[wide.index < first_valid[t], t] = np.nan
    return wide, last_valid


# ---------------------------------------------------------------- factors

FACTOR_COLS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]


def load_factors_daily() -> pd.DataFrame:
    f = pd.read_csv("data/ff_factors_daily.csv", parse_dates=["date"]).set_index("date").sort_index()
    return f  # decimal returns, columns FACTOR_COLS + RF


def compound_factors(factors_daily: pd.DataFrame, period_starts, period_ends) -> pd.DataFrame:
    """Compound daily factor returns over each holding period (start, end].

    Mkt-RF is rebuilt as compounded market minus compounded RF so the excess return is
    exact; the long-short factors are compounded directly (standard approximation).
    Periods not fully covered by the factor file get NaN.
    """
    last = factors_daily.index.max()
    mkt = factors_daily["Mkt-RF"] + factors_daily["RF"]
    rows = []
    for s, e in zip(period_starts, period_ends):
        if e > last:
            rows.append({c: np.nan for c in FACTOR_COLS + ["RF"]})
            continue
        sl = factors_daily.loc[(factors_daily.index > s) & (factors_daily.index <= e)]
        rf = (1 + sl["RF"]).prod() - 1
        row = {"RF": rf, "Mkt-RF": (1 + mkt.loc[sl.index]).prod() - 1 - rf}
        for c in FACTOR_COLS[1:]:
            row[c] = (1 + sl[c]).prod() - 1 if c in sl else np.nan
        rows.append(row)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(period_starts))


# ---------------------------------------------------------------- performance

def max_drawdown(returns: pd.Series) -> float:
    curve = (1 + returns.dropna()).cumprod()
    return (curve / curve.cummax() - 1).min()


def performance_stats(returns: pd.Series, rf: pd.Series | None = None, periods_per_year: int = 12) -> dict:
    """Annualized stats for a periodic return series.

    Sharpe = mean(r - rf) / std(r - rf) * sqrt(12), i.e. on excess returns over the
    T-bill rate. (The original version divided CAGR by vol with no risk-free rate,
    which flatters every strategy in a period when T-bills paid up to ~5%.)
    """
    r = returns.dropna()
    if rf is None:
        rf = pd.Series(0.0, index=r.index)
    rf = rf.reindex(r.index)
    ok = rf.notna()
    ex = (r - rf)[ok]
    n_years = len(r) / periods_per_year
    cum = (1 + r).prod() - 1
    ann_ret = (1 + cum) ** (1 / n_years) - 1 if n_years > 0 else np.nan
    ann_vol = r.std() * np.sqrt(periods_per_year)
    sharpe = ex.mean() / ex.std() * np.sqrt(periods_per_year) if ex.std() > 0 else np.nan
    downside = ex[ex < 0]
    dd_dev = np.sqrt((downside ** 2).sum() / len(ex)) * np.sqrt(periods_per_year) if len(ex) else np.nan
    sortino = ex.mean() * periods_per_year / dd_dev if dd_dev else np.nan
    mdd = max_drawdown(r)
    return {
        "cum_return": cum, "ann_return": ann_ret, "ann_vol": ann_vol,
        "ann_excess_return": ex.mean() * periods_per_year,
        "sharpe": sharpe, "sortino": sortino, "max_drawdown": mdd,
        "calmar": ann_ret / abs(mdd) if mdd else np.nan,
        "n_periods": len(r), "rf_coverage": ok.mean() if len(ok) else np.nan,
    }
