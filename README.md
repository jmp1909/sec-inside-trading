# Does Insider Buying Predict Returns?

A research project testing whether open-market stock purchases and sales by
company insiders, as disclosed on SEC Form 4, predict later returns. It covers
about 87,500 transactions in S&P MidCap 400 companies from 2018 to 2026 and
includes an event study, a monthly-rebalanced portfolio backtest and a script
that produces a current snapshot of the same ranking. Data come from SEC EDGAR's
bulk filings and Yahoo Finance daily prices.

**[Report](https://jmp1909.github.io/sec-inside-trading/)** &middot;
**[Latest insider-buying snapshot](https://jmp1909.github.io/sec-inside-trading/live-signal.html)** &middot;
[Changelog](CHANGELOG.md)

## Results (revised method, October 2026)

After correcting the method, **there is no evidence that following insider
buying beat the market in S&P MidCap 400 stocks over 2019-2026.**

- A portfolio of the 50 stocks with the most net insider buying over the
  previous 3 months, rebalanced monthly, returned 8.6% a year after
  25 bps trading costs, against 12.2% for an equal-weighted portfolio
  of all index members and 11.8% for the MDY index fund. Its Sharpe
  ratio was 0.34 (benchmarks 0.50 and 0.50) and its worst
  drawdown -44% (-37% and -34%). None of the 9 look-back / size
  combinations beat the benchmark after costs.
- Factor-adjusted alpha (Fama-French 5 factors + momentum): -2.9% a
  year, t = -1.4. Against 1,000 random 50-stock portfolios, p = 0.17.
- One year after an insider purchase, stocks beat the average index member over
  the same days by 4.4% (95% interval -2.4% to 11.2%), which is not
  statistically significant.
- The first version's edge came mostly from survivorship bias. On today's
  members, as before, the same portfolio returns 24.1% a year before
  costs against 19.1% for its benchmark; on the members at each date,
  10.9% against 12.5%. The event-study numbers were also inflated by
  counting related trades separately, comparing with returns from different
  dates (insiders bought heavily in the March 2020 crash), and entering on the
  filing day itself.

The report has the full tables, and `data/robustness_summary.md` has every
check. The [changelog](CHANGELOG.md) lists what changed and the corrections to
the first version.

## Methodology revisions

Each of the main objections to the first version, and what the pipeline now does about it:

| Concern | Fix | Where |
|---|---|---|
| **Survivorship bias**: today's 400 members used for all 8 years | Point-in-time membership rebuilt from Wikipedia's index-change history (walked back from today's list, renames / reused tickers handled in `data/ticker_overrides.csv`). A stock only counts as an event, a portfolio candidate, or a benchmark member on days it was actually in the index. Removed / acquired names are kept: CIKs come from the Form 4 issuer symbols, and a held stock that delists stays in the portfolio at its last price instead of dropping out. `--universe current` re-runs the old setup so the size of the bias is reported directly. | `build_universe.py`, `collect_form4.py`, `collect_prices.py`, `common.py` |
| **Sharpe without a risk-free rate; no trading costs** | Sharpe and Sortino are now on excess returns over the 1-month T-bill (Fama-French RF, compounded over each exact holding period). Turnover is tracked from drifted vs target weights; every result is reported at 0 / 10 / 25 / 50 bps one-way, with 25 bps as the headline, plus the break-even cost at which the edge over the benchmark disappears. | `portfolio_backtest.py` |
| **Deeper drawdown than the benchmark** | Drawdown is reported next to an investable benchmark (MDY ETF) and the EW benchmark. `robustness.py` adds the strategy's return in every benchmark drawdown episode, a volatility-matched version (same vol as the benchmark), and a market-hedged version (short beta x MDY). | `robustness.py` |
| **No factor adjustment** | Monthly excess returns regressed on CAPM, FF3, FF5 and FF5 + momentum (Newey-West t-stats), for the strategy, the strategy minus its benchmark, and purchases-only portfolios. | `collect_factors.py`, `robustness.py` |
| **Small purchase sample** (~6,400 purchase rows vs ~81,000 sales) | Trade rows collapsed into company x filing-day events, with the number of events, companies and insiders reported. Event returns are market-adjusted (stock minus the same-window EW return of index members), with SEs clustered by company and by month. Calendar-time portfolios holding every recent purchaser (one observation per month) give a test that clustered events can't inflate. A placebo of 1,000 random 50-stock portfolios gives a luck baseline. | `event_study.py`, `robustness.py` |
| **Mostly a bull market** | Market-adjusted event returns remove the common market move. Results are broken out by calendar year, and by up vs down months (upside / downside capture). | `event_study.py`, `robustness.py` |

Also fixed along the way: event-study entry is now the close of the trading day
*after* the filing date (Form 4s are often filed after the close); companies that
filed for Chapter 11 stay in the study up to the filing with a -30% delisting
return, instead of being dropped (filings checked by hand, false positives in
`data/bankruptcy_false_positives.csv`); and the step that builds
`event_study_final.csv` is part of `event_study.py` instead of being missing
from the pipeline.

## Data sources

Every source below was hit with a live test pull before being relied on.
A few candidates (CoinGecko, Stooq, OpenSky's historical endpoint) were
tried and dropped after failing that check.

| Source | Used for |
|---|---|
| [Wikipedia: List of S&P 400 companies](https://en.wikipedia.org/wiki/List_of_S%26P_400_companies) | Current constituents + index change history (point-in-time universe) |
| [SEC `company_tickers.json`](https://www.sec.gov/files/company_tickers.json) | Ticker &rarr; CIK mapping |
| [SEC insider transactions bulk data sets](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets) | Form 4 purchase/sale transactions, 2018Q3&ndash;2026Q1 |
| [SEC EDGAR submissions API](https://data.sec.gov/submissions/) | 8-K Item 1.03 scan (Chapter 11 filings) |
| [Yahoo Finance chart API](https://query1.finance.yahoo.com/v8/finance/chart/) | Daily adjusted close prices, incl. the MDY ETF benchmark |
| [Kenneth French data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) | Daily Fama-French 5 factors, momentum, risk-free rate |

## Repo structure

```
src/
  common.py               # shared: study window, point-in-time membership, price panel, stats
  build_universe.py       # point-in-time S&P 400 membership -> tickers -> CIKs
  collect_form4.py        # pull SEC bulk quarterly Form 4 data (+ CIKs for delisted names)
  clean_form4.py          # parse dates, compute reporting lag
  find_bankruptcies.py    # find Chapter 11 filings (8-K Item 1.03), minus hand-checked false positives
  collect_prices.py       # daily prices for the universe + MDY, price coverage report
  collect_factors.py      # Fama-French 5 factors + momentum + risk-free rate
  compute_returns.py      # forward + market-adjusted returns at 7 horizons
  build_benchmark.py      # unconditional "any random day" benchmark
  event_study.py          # event-level P vs S, clustered SEs, by-year breakdown
  portfolio_backtest.py   # monthly-rebalanced portfolio grid backtest, with costs
  portfolio_backtest_v2.py  # signal comparison (dollar value / buyer count / concentration)
  robustness.py           # factor alphas, placebo, drawdowns, regimes, survivorship
  build_report.py         # writes index.html from the pipeline outputs
  live_signal.py          # current insider-buying snapshot from recent Form 4 filings
  build_live_page.py      # writes live-signal.html from the latest snapshot
  report_html.py          # table / chart helpers shared by the two page builders
data/                      # pipeline outputs (large raw files gitignored -- see below)
  ticker_overrides.csv      # hand-checked ticker renames / reused tickers for the universe
  live/                     # dated live-signal snapshots, one per run
run_pipeline.sh            # runs everything below in order
index.html                 # the report (GitHub Pages); generated, don't edit by hand
live-signal.html           # the latest snapshot page (GitHub Pages); generated
style.css                  # plain stylesheet shared by both pages
CHANGELOG.md               # what changed and when, including corrections
## Running it

```
pip install -r requirements.txt
./run_pipeline.sh
```

or step by step (with `PYTHONPATH=src`):

```
python src/build_universe.py
python src/collect_form4.py
python src/clean_form4.py
python src/find_bankruptcies.py
python src/collect_prices.py
python src/collect_factors.py
python src/compute_returns.py
python src/build_benchmark.py      --universe current   # then again with --universe pit
python src/event_study.py          --universe current   #   "
python src/portfolio_backtest.py   --universe current   #   "
python src/portfolio_backtest_v2.py --universe current  #   "
python src/robustness.py
python src/build_report.py
```

To refresh the snapshot page:

```
python src/live_signal.py
python src/build_live_page.py
```

`--universe pit` (the default) is the point-in-time universe used for the main
results; `--universe current` reproduces the original today's-constituents setup
and writes its outputs with a `_current` suffix, so the two can be compared.
`robustness.py` writes a readable summary to `data/robustness_summary.md`.

`data/prices.csv`, `form4_transactions_raw.csv`, `form4_transactions_clean.csv`,
`form4_with_returns.csv`, `event_study_final*.csv`, `ff_factors_daily.csv` and the
cached SEC zips in `data/sec_bulk/` are gitignored (15&ndash;90MB each) and get
regenerated by the pipeline above. The smaller summary outputs (`universe.csv`,
`portfolio_backtest_grid.csv`, `robustness_*.csv`, etc.) are committed as-is.

## Known limitations

- **Residual survivorship gap**: the point-in-time universe includes companies
  that left the index, but Yahoo Finance has no history for many acquired or
  delisted tickers. Those member-days can't be priced and drop out (13% of all
  member-days; `data/price_coverage.csv` has the detail). Chapter 11 filers get
  a flat -30% delisting return at the petition date, an average from the
  literature rather than each company's actual loss. Closing these gaps fully
  needs a survivorship-free price database such as CRSP.
- **Wikipedia as the constituent history**: the change table is labelled
  "selected" changes. The reconstruction is checked by requiring the member count
  to stay at ~400 through the whole window, but a missed change would go unnoticed.
- **Short, mostly rising sample**: 2018-2026 has two sharp sell-offs (2020, 2022)
  and no long bear market. SEC's Form 4 data sets go back to 2006, but the
  Wikipedia change history only reaches 2012, so the 2008 crisis can't be added
  without another constituent source.
- **Transaction costs are assumed, not measured**: a flat cost per dollar traded,
  with no market-impact model. The break-even cost column shows how much room
  there is.
- **Mean vs. median**: headline mean returns, especially at the 1&ndash;2yr
  horizons, are pulled up by a fat right tail of large winners. Medians are
  reported alongside every mean for this reason.
- **Yahoo Finance's price API is unofficial and undocumented.** Widely used
  in practice, but not an SLA-backed source the way SEC EDGAR is.

## License

MIT &mdash; see [LICENSE](LICENSE).

Not investment advice.
