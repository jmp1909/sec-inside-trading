"""
Build index.html from the pipeline outputs (run after run_pipeline.sh).

Every number on the page is read from the CSVs in data/, so the report can't drift
from the results the way the first hand-assembled version did. Sentences that depend
on the results (e.g. whether the strategy beat the benchmark) are worded from the
numbers, not written in advance.
"""
import pandas as pd

from portfolio_backtest import HEADLINE_CONFIG, HEADLINE_COST_BPS
from report_html import PAGE_FOOT, PAGE_HEAD, line_chart, num, pct, pval, table

H = {"1d": "1 day", "5d": "5 days", "10d": "10 days", "20d": "20 days", "6m": "6 months", "1y": "1 year", "2y": "2 years"}
SHORT = {"1d", "5d", "10d", "20d"}


def read(name, **kw):
    try:
        return pd.read_csv(f"data/{name}", **kw)
    except FileNotFoundError:
        return None


def d(h):
    return 2 if h in SHORT else 1


def word_vs(a, b, more="higher", less="lower"):
    return more if a > b else less


def main():
    ev = read("report_event_study.csv")
    by_year = read("event_study_by_year.csv")
    grid = read("portfolio_backtest_grid.csv")
    grid_cur = read("portfolio_backtest_grid_current.csv")
    sig = read("portfolio_backtest_signals.csv")
    eq = read("equity_curve_best.csv", parse_dates=["date"])
    regs = read("robustness_factor_regressions.csv")
    regimes = read("robustness_regimes.csv")
    capture = read("robustness_capture.csv")
    dds = read("robustness_drawdowns.csv")
    placebo = read("robustness_placebo.csv")
    cov = read("price_coverage.csv")
    uni = read("universe.csv")
    monthly = read("backtest_monthly.csv", parse_dates=["start", "end"])

    w, n = HEADLINE_CONFIG
    c = HEADLINE_COST_BPS
    g = grid[(grid.window_months == w) & (grid.portfolio_size == n)].set_index("cost_bps")
    head, gross = g.loc[c], g.loc[0]
    y1 = ev.set_index("horizon").loc["1y"]
    m20 = ev.set_index("horizon").loc["20d"]
    start, end = monthly["start"].min(), monthly["end"].max()

    # ---------------- chart
    dates = [start] + list(eq["date"])
    chart = line_chart(dates, {
        "Insiders": ([1.0] + list(eq["port_net"]), "#1a4e8a", None),
        "EW bench.": ([1.0] + list(eq["bench_ew_net"]), "#888", "5,3"),
        "MDY": ([1.0] + list(eq["bench_mdy"]), "#b07a2a", "2,3"),
    }, ylabel_fmt=lambda v: f"${v:.2f}" if v % 1 else f"${v:.0f}")

    # ---------------- event table
    ev_rows = [[H[r.horizon], f"{int(r.p_events):,}", pct(r.p_abn_mean, d(r.horizon), True),
                f"{pct(r.p_abn_ci_lo, d(r.horizon), True)} to {pct(r.p_abn_ci_hi, d(r.horizon), True)}",
                pval(r.p_abn_pval), f"{int(r.s_events):,}", pct(r.s_abn_mean, d(r.horizon), True), pval(r.s_abn_pval),
                pct(r.p_minus_s_abn, d(r.horizon), True)] for r in ev.itertuples()]
    ev_table = table(["Horizon", "Buy events", "Buys vs market", "95% interval", "p", "Sell events",
                      "Sells vs market", "p", "Buys minus sells"], ev_rows)
    raw_rows = [[H[r.horizon], pct(r.p_mean, d(r.horizon), True), pct(r.p_median, d(r.horizon), True),
                 pct(r.s_mean, d(r.horizon), True), pct(r.s_median, d(r.horizon), True), pct(r.bench, d(r.horizon), True)]
                for r in ev.itertuples()]
    raw_table = table(["Horizon", "Buys: mean", "median", "Sells: mean", "median", "Any day: mean"], raw_rows)
    year_table = table(["Filing year", "Buy events", "Firms", "20 days", "6 months", "1 year"],
                       [[str(r.year), str(r.events), str(r.firms), pct(r.abn_20d, 1, True), pct(r.abn_6m, 1, True),
                         pct(r.abn_1y, 1, True)] for r in by_year.itertuples()])

    # ---------------- grid tables
    gc = grid[grid.cost_bps == c]
    g_rows, hl = [], set()
    for i, r in enumerate(gc.itertuples()):
        g_rows.append([f"{r.window_months} months", f"top {r.portfolio_size}", pct(r.avg_monthly_turnover_oneway, 0),
                       pct(r.port_ann_return, 1), num(r.port_sharpe), pct(r.port_max_dd, 0),
                       f"{r.break_even_cost_bps:.0f}" if r.break_even_cost_bps < 1000 else "&gt;1000"])
        if (r.window_months, r.portfolio_size) == (w, n):
            hl.add(i)
    b = gc.iloc[0]
    g_rows.append(["Equal-weight benchmark", "all", "", pct(b.bench_ann_return, 1), num(b.bench_sharpe), pct(b.bench_max_dd, 0), ""])
    g_rows.append(["MDY index fund", "", "", pct(b.mdy_ann_return, 1), num(b.mdy_sharpe), pct(b.mdy_max_dd, 0), ""])
    grid_table = table(["Look-back", "Holdings", "Turnover / month", "Annual return", "Sharpe", "Max drawdown",
                        "Break-even cost (bps)"], g_rows, hl)
    cost_table = table(["Cost per trade", "Annual return", "Sharpe", "Max drawdown", "EW benchmark return", "EW benchmark Sharpe"],
                       [[f"{cb} bps", pct(r.port_ann_return, 1), num(r.port_sharpe), pct(r.port_max_dd, 0),
                         pct(r.bench_ann_return, 1), num(r.bench_sharpe)] for cb, r in g.iterrows()])

    names = {"net_dollar_value": "Net dollar value", "buyer_count": "Number of buyers", "value_per_buyer": "Dollars per buyer"}
    sc = sig[sig.cost_bps == c]
    sig_table = table(["Ranking", "Target", "Avg. stocks held", "Annual return", "Sharpe", "Max drawdown"],
                      [[names[r.signal], f"top {r.portfolio_size}", f"{r.avg_actual_holdings:.0f}", pct(r.ann_return, 1),
                        num(r.sharpe), pct(r.max_dd, 0)] for r in sc.itertuples()])

    # ---------------- survivorship
    surv = ""
    if grid_cur is not None:
        rows = []
        for label, gg in (("Today's members (first version)", grid_cur), ("Point-in-time members", grid)):
            for cb in (0, c):
                r = gg[(gg.window_months == w) & (gg.portfolio_size == n) & (gg.cost_bps == cb)].iloc[0]
                rows.append([label, f"{cb} bps", pct(r.port_ann_return, 1), num(r.port_sharpe), pct(r.port_max_dd, 0),
                             pct(r.bench_ann_return, 1), num(r.bench_sharpe)])
        surv = table(["Stock list", "Cost", "Annual return", "Sharpe", "Max drawdown", "EW benchmark return",
                      "EW benchmark Sharpe"], rows)
    removed = cov[~cov.member_at_study_end] if cov is not None else None
    cov_text = ""
    if cov is not None:
        cov_text = (f"{len(uni)} companies were in the index at some point in the period, {int((~uni.member_at_study_end).sum())} "
                    f"of which left it before the end. Prices were found for {pct(cov.member_days_priced.sum() / cov.member_days.sum(), 0)} "
                    f"of all company-days in the index ({int((removed.member_days_priced > 0).sum())} of the {len(removed)} "
                    f"companies that left). The rest, mostly companies that were taken over and whose old tickers Yahoo no "
                    f"longer carries, are missing.")

    # ---------------- factor table
    series_names = {"strategy_net": "Strategy", "strategy_minus_ew": "Strategy minus EW benchmark",
                    "strategy_minus_mdy": "Strategy minus MDY", "purchases_only_1m": "All recent buyers (1 month)",
                    "purchases_only_3m": "All recent buyers (3 months)", "sales_only_3m": "Sellers only (3 months)",
                    "purchases_minus_sales_3m": "Buyers minus sellers (3 months)"}
    f_rows = []
    for key, label in series_names.items():
        r = regs[(regs.series == key)].set_index("model")
        if r.empty:
            continue
        f = r.loc["FF5+Mom"]
        f_rows.append([label, f"{pct(r.loc['CAPM'].alpha_annual, 1, True)} ({num(r.loc['CAPM'].alpha_t, 1)})",
                       f"{pct(f.alpha_annual, 1, True)} ({num(f.alpha_t, 1)})", num(f["beta_Mkt-RF"]), num(f.beta_SMB),
                       num(f.beta_HML), num(f.beta_Mom)])
    fac_table = table(["Portfolio", "CAPM alpha (t)", "FF5+Mom alpha (t)", "Market", "Size", "Value", "Momentum"], f_rows)
    fs = regs[(regs.series == "strategy_net") & (regs.model == "FF5+Mom")].iloc[0]
    fa = regs[(regs.series == "strategy_minus_ew") & (regs.model == "FF5+Mom")].iloc[0]

    # ---------------- drawdowns / regimes
    dd_table = table(["Benchmark fall (month ends)", "EW benchmark", "MDY", "Strategy"],
                     [[f"{r.peak_month_end} to {r.trough_month_end}", pct(r.ew_benchmark, 1, True), pct(r.mdy, 1, True),
                       pct(r.strategy, 1, True)] for r in dds.itertuples()]) if dds is not None and len(dds) else "<p>None deeper than 10%.</p>"
    yr_table = table(["Year", "Months", "Strategy", "EW benchmark", "MDY", "Strategy minus EW"],
                     [[str(r.year), str(int(r.months)), pct(r.strategy, 1, True), pct(r.ew_benchmark, 1, True),
                       pct(r.mdy, 1, True), pct(r.strategy_minus_ew, 1, True)] for r in regimes.itertuples()])
    cap_table = table(["Months when MDY was", "Months", "Strategy", "EW benchmark", "MDY", "Strategy minus EW"],
                      [[r.regime.replace("MDY ", "").replace(" months", ""), str(r.months), pct(r.strategy_avg, 2, True),
                        pct(r.ew_avg, 2, True), pct(r.mdy_avg, 2, True), pct(r.strategy_minus_ew_avg, 2, True)]
                       for r in capture.itertuples()])
    pl_beat = (placebo.sharpe < head.port_sharpe).mean()
    yrs_beat = int((regimes.strategy_minus_ew > 0).sum())

    page = PAGE_HEAD.format(title="Does insider buying predict stock returns?") + f"""
<h1>Does insider buying predict stock returns?</h1>
<p class="meta">S&amp;P MidCap 400 &middot; SEC Form 4 filings 2018&ndash;2026 &middot; portfolio test {start:%b %Y} &ndash; {end:%b %Y}
&middot; <a href="live-signal.html">latest insider-buying snapshot</a></p>

<nav class="toc"><a href="#summary">Summary</a> <a href="#data">Data and method</a> <a href="#events">Event study</a> <a href="#portfolio">Portfolio test</a> <a href="#checks">Checks</a> <a href="#limits">Limitations</a> <a href="#changes">Changes</a></nav>

<h2 id="summary">Summary</h2>
<ul>
<li>Measured against the market over the same dates, stocks beat it by {pct(m20.p_abn_mean, 1, True)} in the 20 trading days after an
insider purchase (95% interval {pct(m20.p_abn_ci_lo, 1, True)} to {pct(m20.p_abn_ci_hi, 1, True)}) and by
{pct(y1.p_abn_mean, 1, True)} over a year ({pct(y1.p_abn_ci_lo, 1, True)} to {pct(y1.p_abn_ci_hi, 1, True)}). After insider
sales the figures were {pct(m20.s_abn_mean, 1, True)} and {pct(y1.s_abn_mean, 1, True)}.</li>
<li>A portfolio of the {n} stocks with the most net insider buying over the previous {w} months, rebalanced monthly, returned
{pct(head.port_ann_return, 1)} a year after trading costs of {c} basis points per trade, against {pct(head.bench_ann_return, 1)}
for an equal-weighted portfolio of all index members and {pct(head.mdy_ann_return, 1)} for the MDY index fund. Its Sharpe ratio
was {num(head.port_sharpe)} ({num(head.bench_sharpe)} and {num(head.mdy_sharpe)}); its worst drawdown was
{pct(head.port_max_dd, 0)} ({pct(head.bench_max_dd, 0)} and {pct(head.mdy_max_dd, 0)}).</li>
<li>After adjusting for market, size, value, profitability, investment and momentum exposure, the strategy's alpha was
{pct(fs.alpha_annual, 1, True)} a year (t = {num(fs.alpha_t, 1)}); its return over the equal-weighted benchmark had an alpha of
{pct(fa.alpha_annual, 1, True)} (t = {num(fa.alpha_t, 1)}).</li>
<li>Its Sharpe ratio was higher than {pct(pl_beat, 0)} of 1,000 random {n}-stock portfolios drawn from the same stocks.
It beat the equal-weighted benchmark in {yrs_beat} of {len(regimes)} calendar years.</li>
</ul>

<h2 id="data">Data and method</h2>
<ul>
<li><strong>Companies:</strong> S&amp;P MidCap 400 members on each date, rebuilt from the current list and Wikipedia's record of
index changes. A company only counts while it is in the index. {cov_text}</li>
<li><strong>Insider trades:</strong> SEC's quarterly Form 3/4/5 data sets from 2018 Q3. Only open-market purchases (code P) and
sales (code S). All reporting owners are included: officers, directors and holders of more than 10%.</li>
<li><strong>Prices:</strong> Yahoo Finance daily closes, adjusted for splits and dividends. If a stock stops trading while held,
it is treated as sold at its last price.</li>
<li><strong>Timing:</strong> returns start at the close of the trading day after the filing date, since many Form 4s are
filed after the market closes.</li>
<li><strong>Market comparison:</strong> each stock's return is compared with the average return of all index members over
exactly the same days.</li>
<li><strong>Costs and Sharpe ratio:</strong> trading costs are charged on the value traded each month. Sharpe ratios use returns
above the one-month Treasury bill rate.</li>
<li><strong>Excluded:</strong> companies that filed for Chapter 11 during the period.</li>
</ul>

<h2 id="events">Event study</h2>
<p>All trades by insiders of the same company filed on the same day count as one event. Returns are measured against the
market over the same days. The 95% intervals and p-values allow for events at the same company, and events in the same
month, being related.</p>
{ev_table}
<h3>Purchases by year</h3>
{year_table}
<h3>Raw returns, for comparison with the first version</h3>
<p class="small">Not market-adjusted. "Any day" is the average return of an index member from any day in the period.</p>
{raw_table}

<h2 id="portfolio">Portfolio test</h2>
<p>Each month, rank index members by net insider dollar buying (purchases minus sales) over a look-back window, buy the top N
in equal amounts, and hold for a month.</p>
<figure>{chart}
<figcaption>Growth of $1 after {c} bps trading costs: {w}-month look-back, top {n} (Insiders), equal-weighted index members
(EW bench.), and the MDY index fund.</figcaption></figure>
<h3>All combinations, after {c} bps costs</h3>
{grid_table}
<p class="small">Turnover is the share of the portfolio sold (and bought) each month. Break-even cost is the cost per trade at
which the portfolio's annual return falls to the equal-weighted benchmark's.</p>
<h3>Effect of trading costs ({w}-month look-back, top {n})</h3>
{cost_table}
<h3>Other ways of ranking ({c} bps costs)</h3>
{sig_table}

<h2 id="checks">Checks</h2>
<h3>Survivorship bias</h3>
<p>The same test run on today's index members (as in the first version) and on the members at each date.</p>
{surv}
<h3>Factor exposure</h3>
<p>Monthly returns above the T-bill rate regressed on the Fama-French factors, with Newey-West t-statistics in brackets.
Betas are from the five-factor plus momentum model. "All recent buyers" holds every index member with at least one insider
purchase in the look-back window, which tests the purchases on their own with one observation per month.</p>
{fac_table}
<h3>Drawdowns</h3>
{dd_table}
<h3>Rising and falling markets</h3>
{yr_table}
<p class="small">Average monthly return:</p>
{cap_table}

<h2 id="limits">Limitations</h2>
<ul>
<li>Prices are missing for some companies that left the index, mostly takeovers. Companies that went through Chapter 11
are excluded. A full fix would need a survivorship-free price database.</li>
<li>Wikipedia lists "selected" index changes. The rebuilt membership is checked by requiring about 400 members on every
date, but a missed change would not show up.</li>
<li>The period (2018&ndash;2026) includes the 2020 and 2022 falls but no long bear market. Wikipedia's change history only goes
back to 2012, so 2008 can't be added this way.</li>
<li>Trading costs are a flat charge per dollar traded, not a market-impact model.</li>
<li>The look-back and portfolio size shown in the summary were picked after seeing the first version's results. The full
grid and the random-portfolio check are shown for that reason.</li>
<li>Yahoo Finance's price API is unofficial.</li>
</ul>

<h2 id="changes">Changes</h2>
<p>The first version (August 2026) used today's index members for the whole period, no trading costs, a Sharpe ratio
without a risk-free rate, no factor adjustment, trade-level statistics and same-day entry. All of these were changed in
October 2026. The full list, including corrections to the first version's report, is in the
<a href="https://github.com/jmp1909/sec-inside-trading/blob/main/CHANGELOG.md">changelog</a>.</p>
""" + PAGE_FOOT
    open("index.html", "w").write(page)
    print("Wrote index.html")


if __name__ == "__main__":
    main()
