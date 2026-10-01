# Does Insider Buying Predict Returns?

An end-to-end quantitative research project testing whether corporate insiders'
disclosed stock purchases and sales (SEC Form 4) predict future returns, using
87,500+ transactions across the S&P MidCap 400 (2018-2026). Includes an event
study, a monthly-rebalanced portfolio backtest, a live signal tool, and a
machine-learning validation pass, built entirely on free, verified data
sources: SEC EDGAR's bulk structured filings and Yahoo Finance daily prices.

**[Read the full report](https://jmp1909.github.io/sec-inside-trading/)**
(interactive charts, full methodology, all results)

**[See today's live signal](https://jmp1909.github.io/sec-inside-trading/live-signal.html)**
(rerunnable snapshot, ranked by trailing 90-day net insider dollar value)

## The short version

> **Methodology revision in progress.** The numbers below (and in the published
> report) come from the original backtest, which used today's index members for
> the whole period, ignored trading costs and the risk-free rate, and did no factor
> adjustment. The pipeline has since been rebuilt to fix those issues (see
> [Methodology revisions](#methodology-revisions)); the report will be updated
> with the re-run results. Until then, read the figures below with those caveats
> in mind.

Insider buying predicts returns, but it's a modest tilt, not a golden signal.

- Open-market purchases beat an unconditional benchmark at every horizon
  tested (1 day to 2 years), with strong statistical significance
  (p < 0.02 everywhere, mostly p < 0.0001). Sales underperform the same
  benchmark just as consistently.
- Turned into an actual monthly-rebalanced portfolio (rank the universe by
  trailing 3-month net insider dollar buying, hold the top 50, equal-weight),
  it beats a diversified buy-and-hold on both raw return (24.0% vs 19.1%
  annualized) and risk-adjusted return (Sharpe 0.86 vs 0.83).
- The edge is thin, though: only the more diversified configurations
  survive risk-adjustment. A concentrated "top 10 highest-conviction bets"
  portfolio posts a flashier raw return but a *worse* Sharpe ratio than just
  holding the market, because concentration adds drawdown faster than it
  adds return.

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
*after* the filing date (Form 4s are often filed after the close), and the step
that builds `event_study_final.csv` is part of `event_study.py` instead of
being missing from the pipeline.

## Data sources

Every source below was hit with a live test pull before being relied on.
A few candidates (CoinGecko, Stooq, OpenSky's historical endpoint) were
tried and dropped after failing that check.

| Source | Used for |
|---|---|
| [Wikipedia: List of S&P 400 companies](https://en.wikipedia.org/wiki/List_of_S%26P_400_companies) | Current constituents + index change history (point-in-time universe) |
| [SEC `company_tickers.json`](https://www.sec.gov/files/company_tickers.json) | Ticker &rarr; CIK mapping |
| [SEC insider transactions bulk data sets](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets) | Form 4 purchase/sale transactions, 2018Q3&ndash;2026Q1 |
| [SEC EDGAR submissions API](https://data.sec.gov/submissions/) | 8-K Item 1.03 scan (bankruptcy exclusions) |
| [Yahoo Finance chart API](https://query1.finance.yahoo.com/v8/finance/chart/) | Daily adjusted close prices, incl. the MDY ETF benchmark |
| [Kenneth French data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) | Daily Fama-French 5 factors, momentum, risk-free rate |

## Repo structure

```
src/
  common.py               # shared: study window, point-in-time membership, price panel, stats
  build_universe.py       # point-in-time S&P 400 membership -> tickers -> CIKs
  collect_form4.py        # pull SEC bulk quarterly Form 4 data (+ CIKs for delisted names)
  clean_form4.py          # parse dates, compute reporting lag
  find_bankruptcies.py    # scan for Chapter 11 (8-K Item 1.03) exclusions
  collect_prices.py       # daily prices for the universe + MDY, price coverage report
  collect_factors.py      # Fama-French 5 factors + momentum + risk-free rate
  compute_returns.py      # forward + market-adjusted returns at 7 horizons
  build_benchmark.py      # unconditional "any random day" benchmark
  event_study.py          # event-level P vs S, clustered SEs, by-year breakdown
  portfolio_backtest.py   # monthly-rebalanced portfolio grid backtest, with costs
  portfolio_backtest_v2.py  # signal comparison (dollar value / buyer count / concentration)
  robustness.py           # factor alphas, placebo, drawdowns, regimes, survivorship
  live_signal.py          # live, rerunnable insider-buying signal (see below)
data/                      # pipeline outputs (large raw files gitignored -- see below)
  ticker_overrides.csv      # hand-checked ticker renames / reused tickers for the universe
  live/                     # dated live-signal snapshots, one per run
run_pipeline.sh            # runs everything below in order
index.html                 # the published report, self-contained, served via GitHub Pages
live-signal.html            # live signal dashboard, same design system, also on GitHub Pages
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
  delisted tickers. Those member-days can't be priced and drop out;
  `data/price_coverage.csv` reports exactly how much. Companies that filed for
  Chapter 11 are still excluded (their pre/post-reorganization price series aren't
  continuous). Both gaps would need a survivorship-free price database (e.g. CRSP)
  to close fully.
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
