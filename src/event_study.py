"""
Event study: do open-market insider purchases (P) predict positive forward
returns, and do sales (S) predict negative ones? Compares P vs S vs an
equal-weighted universe benchmark at each horizon.

Inference is done at the *event* level, not the trade level:
  * One Form 4 often reports many lots, and several insiders at one company often buy
    on the same day. Treating each lot as an independent observation (the original
    6,443 "purchases") overstates the sample. Rows are collapsed to one event per
    company x filing date x direction, and the report says how many distinct events,
    companies and insiders sit behind each number.
  * Returns are market-adjusted against the same-window equal-weighted universe
    return (abn_<h>, see compute_returns.py), so a bull market lifts both sides equally.
  * Standard errors are clustered two ways, by company and by filing month, because
    events at the same firm / in the same month are not independent and long-horizon
    windows overlap. The calendar-time portfolio test in robustness.py is the stricter
    check for the 6m-2y horizons.
  * Results are also broken out by filing year, to show whether the effect is driven by
    one or two years.

The original trade-level comparison against the pooled unconditional benchmark is
still printed and saved (columns p_mean ... bench) for continuity with the report.
"""
import argparse
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from common import suffix

HORIZONS = ["1d", "5d", "10d", "20d", "6m", "1y", "2y"]


def build_final(mode: str) -> pd.DataFrame:
    """form4_with_returns -> event_study_final: universe filter, has a price.

    Chapter 11 companies are no longer dropped: their returns run to the petition date
    plus a delisting return (see common.load_prices_long)."""
    df = pd.read_csv("data/form4_with_returns.csv", parse_dates=["filing_date", "entry_date"])
    df = df[df[f"member_{mode}"]]
    df = df[df["entry_date"].notna()]
    for h in HORIZONS:
        df[f"bench_{h}"] = df[f"bench_{mode}_{h}"]
        df[f"abn_{h}"] = df[f"ret_{h}"] - df[f"bench_{h}"]
    return df


def collapse_to_events(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["ticker", "filing_date", "trans_code"]
    agg = {"trade_value": "sum", "owner_cik": "nunique", "ACCESSION_NUMBER": "nunique"}
    agg.update({f"{p}_{h}": "first" for h in HORIZONS for p in ("ret", "bench", "abn")})
    ev = df.groupby(keys).agg(agg).reset_index()
    ev = ev.rename(columns={"owner_cik": "n_insiders", "ACCESSION_NUMBER": "n_filings"})
    ev["n_trades"] = df.groupby(keys).size().to_numpy()
    ev["filing_month"] = ev["filing_date"].dt.to_period("M").astype(str)
    return ev


def clustered_mean(y: pd.Series, firms: pd.Series, months: pd.Series | None) -> dict:
    ok = y.notna()
    y, firms = y[ok], firms[ok]
    if len(y) < 3:
        return {"mean": np.nan, "se": np.nan, "t": np.nan, "pval": np.nan, "ci_lo": np.nan, "ci_hi": np.nan}
    groups = pd.factorize(firms)[0]
    if months is not None:
        groups = np.column_stack([groups, pd.factorize(months[ok])[0]])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = sm.OLS(y.to_numpy(), np.ones(len(y))).fit(cov_type="cluster", cov_kwds={"groups": groups})
    m, se = fit.params[0], fit.bse[0]
    return {"mean": m, "se": se, "t": m / se, "pval": fit.pvalues[0], "ci_lo": m - 1.96 * se, "ci_hi": m + 1.96 * se}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["pit", "current"], default="pit")
    args = parser.parse_args()
    sfx = suffix(args.universe)

    df = build_final(args.universe)
    df.to_csv(f"data/event_study_final{sfx}.csv", index=False)
    events = collapse_to_events(df)

    bench_series = pd.read_csv(f"data/unconditional_benchmark{sfx}.csv", index_col=0)["mean_ret"]

    print("=" * 78)
    print(f"SAMPLE ({args.universe} universe)")
    print("=" * 78)
    for code in ["P", "S"]:
        d, e = df[df["trans_code"] == code], events[events["trans_code"] == code]
        print(f"  {code}: {len(d):>6} trade rows -> {len(e):>6} company-day events, "
              f"{e['ticker'].nunique():>4} companies, {d['owner_cik'].nunique():>5} distinct insiders")

    rows = []
    print("\n" + "=" * 78)
    print("EVENT LEVEL: market-adjusted return (stock minus same-window EW universe)")
    print("two-way clustered by company and filing month")
    print("=" * 78)
    for h in HORIZONS:
        row = {"horizon": h, "bench": bench_series[h]}
        # trade-level, original methodology (kept for continuity)
        for code, pre in (("P", "p"), ("S", "s")):
            r = df.loc[df["trans_code"] == code, f"ret_{h}"].dropna()
            row[f"{pre}_mean"] = r.mean()
            row[f"{pre}_median"] = r.median()
            row[f"{pre}_n"] = len(r)
            row[f"{pre}_win"] = (r > 0).mean()
            row[f"{pre}_pval"] = stats.ttest_1samp(r, bench_series[h]).pvalue if len(r) > 2 else np.nan
        # event-level, market-adjusted, clustered
        line = f"{h:>4}"
        for code, pre in (("P", "p"), ("S", "s")):
            e = events[events["trans_code"] == code]
            a = e[f"abn_{h}"]
            res = clustered_mean(a, e["ticker"], e["filing_month"])
            row.update({
                f"{pre}_events": a.notna().sum(), f"{pre}_firms": e.loc[a.notna(), "ticker"].nunique(),
                f"{pre}_abn_mean": res["mean"], f"{pre}_abn_median": a.median(),
                f"{pre}_abn_beat": (a.dropna() > 0).mean(),
                f"{pre}_abn_t": res["t"], f"{pre}_abn_pval": res["pval"],
                f"{pre}_abn_ci_lo": res["ci_lo"], f"{pre}_abn_ci_hi": res["ci_hi"],
            })
            line += (f"   {code}: abn={res['mean']:+.4f} [{res['ci_lo']:+.4f},{res['ci_hi']:+.4f}] "
                     f"t={res['t']:+.2f} (n={a.notna().sum()})")
        # P minus S, same clustering
        e = events.dropna(subset=[f"abn_{h}"])
        X = sm.add_constant((e["trans_code"] == "P").astype(float).to_numpy())
        groups = np.column_stack([pd.factorize(e["ticker"])[0], pd.factorize(e["filing_month"])[0]])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = sm.OLS(e[f"abn_{h}"].to_numpy(), X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        row["p_minus_s_abn"], row["p_minus_s_t"], row["p_minus_s_pval"] = fit.params[1], fit.tvalues[1], fit.pvalues[1]
        print(line + f"   P-S={fit.params[1]:+.4f} t={fit.tvalues[1]:+.2f}")
        rows.append(row)

    report = pd.DataFrame(rows)
    report.to_csv(f"data/report_event_study{sfx}.csv", index=False)

    # --- stability over time: purchases' market-adjusted return by filing year
    print("\n" + "=" * 78)
    print("PURCHASES BY FILING YEAR (market-adjusted, clustered by company)")
    print("=" * 78)
    by_year = []
    p_events = events[events["trans_code"] == "P"].copy()
    p_events["year"] = p_events["filing_date"].dt.year
    for year, e in p_events.groupby("year"):
        row = {"year": year, "events": len(e), "firms": e["ticker"].nunique()}
        for h in ["20d", "6m", "1y"]:
            res = clustered_mean(e[f"abn_{h}"], e["ticker"], None)
            row.update({f"abn_{h}": res["mean"], f"t_{h}": res["t"], f"n_{h}": e[f"abn_{h}"].notna().sum()})
        by_year.append(row)
        print(f"  {year}: {row['events']:>4} events / {row['firms']:>3} firms   "
              f"20d {row['abn_20d']:+.3f} (t={row['t_20d']:+.2f})   6m {row['abn_6m']:+.3f} (t={row['t_6m']:+.2f})   "
              f"1y {row['abn_1y']:+.3f} (t={row['t_1y']:+.2f})")
    pd.DataFrame(by_year).to_csv(f"data/event_study_by_year{sfx}.csv", index=False)

    print(f"\nWrote data/event_study_final{sfx}.csv, data/report_event_study{sfx}.csv, "
          f"data/event_study_by_year{sfx}.csv")


if __name__ == "__main__":
    main()
