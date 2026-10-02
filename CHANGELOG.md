# Changelog

## 2 October 2026: revised results

The revised pipeline was run on the real data. Main results (point-in-time
universe, 25 bps costs, Feb 2019 to Jul 2026):

- The insider-buying portfolio (3-month look-back, top 50) returned 8.6% a
  year against 12.2% for the equal-weighted index members and 11.8% for MDY.
  Sharpe 0.34 vs 0.50; max drawdown -44% vs -37%. None of the 9 combinations
  beat the benchmark after costs.
- FF5 + momentum alpha -2.9% a year (t = -1.4); random-portfolio p = 0.17.
- Market-adjusted return one year after a purchase: +4.4% (95% interval -2.4%
  to +11.2%), not significant.
- On today's members (the first version's setup) the same portfolio returns
  24.1% a year before costs, close to the first version's 24.2%, which confirms
  the pipeline reproduces it. On the members at each date it returns 10.9%.
  The equal-weighted benchmark falls from 19.1% to 12.5%, close to what MDY
  actually earned, which supports the point-in-time reconstruction.

Fixes made while running on real data:

- **Renamed companies.** The name check wrongly rejected CIKs or prices for
  Casey's (apostrophe), Wabtec, AMC Networks, Mednax/Pediatrix, Prestige Brands,
  CMC Materials and Allscripts/Veradigm. Apostrophes are now ignored, and
  `data/cik_overrides.csv` lists hand-verified renames, which also skip the
  Yahoo name check.
- **One CIK, two tickers.** Chemical Financial (CHFC) took the TCF name in 2019.
  Trades are now assigned to whichever ticker was the index member on the filing
  date. (`compute_returns.py`)
- **Bankruptcies.** On the full point-in-time list the 8-K scan found 20
  companies. Reading each filing showed three were not the company's own
  Chapter 11: LendingTree and EchoStar (subsidiary filings) and Granite
  (a note exchange tagged as item 1.03). They are listed in
  `data/bankruptcy_false_positives.csv`. The remaining 17 are no longer dropped
  from the study, since dropping them removes some of the worst outcomes.
  Their prices end at the petition with a -30% delisting return.
  (`common.load_prices_long`)
- `collect_form4.py` now resolves every CIK before filtering transactions. A
  clean run had lost 290 trades of delisted companies whose filings spelled the
  ticker differently in some quarters.
- `find_bankruptcies.py` used "today minus 8 years" as its start date, which
  missed the start of the study window. It now uses the study dates.
- Coverage: 87% of point-in-time member-days have prices; 203 of the 349
  companies that left the index are priced. The rest, mostly acquired
  companies, are missing (see Limitations in the README).

## 1 October 2026: methodology revision

### Method

- **Point-in-time stock list.** S&P 400 membership on each date is rebuilt from
  the current list and Wikipedia's index-change history, walking back from today.
  Ticker renames and reused tickers are handled in `data/ticker_overrides.csv`.
  On the real Wikipedia table the rebuilt list has 400&ndash;401 members on every
  date in the window, 749 companies in total, and the members at the end of the
  window match the first version's 400 exactly.
  (`build_universe.py`, `common.py`)
- **Companies that left the index are kept.** CIKs for delisted companies come
  from the ticker symbols in the Form 4 filings themselves, checked against the
  company name. Yahoo prices for old tickers are rejected if Yahoo's company
  name doesn't match, since tickers get reused. `data/price_coverage.csv`
  reports how many company-days have prices. (`collect_form4.py`,
  `collect_prices.py`)
- **Delistings.** A stock that stops trading while held is treated as sold at
  its last price, instead of quietly dropping out. (`common.build_price_panel`)
- **Trading costs.** Monthly turnover is measured from drifted vs target
  weights. Results are reported at 0, 10, 25 and 50 bps per trade (25 bps
  headline), with the break-even cost. (`portfolio_backtest.py`)
- **Sharpe ratio** now uses returns above the one-month T-bill rate (from Ken
  French's data library), and the Sortino ratio is added. The first version
  divided annual return by volatility with no risk-free rate.
- **MDY** (SPDR S&P MidCap 400 ETF) added as an investable benchmark.
- **Factor regressions** on CAPM, Fama-French 3 and 5 factors, and 5 factors
  plus momentum, with Newey-West t-statistics. (`collect_factors.py`,
  `robustness.py`)
- **Event study.** Trade rows are grouped into one event per company, filing
  day and direction. Returns are compared with the average index member over the
  same days. Standard errors are clustered by company and by month. Results
  are also shown by filing year. (`event_study.py`, `compute_returns.py`)
- **Next-day entry.** Event returns start at the close of the trading day after
  the filing date, since many Form 4s are filed after the close.
- **New checks** in `robustness.py`: portfolios holding every recent buyer
  (one observation per month), 1,000 random portfolios as a luck baseline,
  drawdown episodes, volatility-matched and market-hedged versions, results by
  year and by rising/falling months, and a comparison of the point-in-time and
  today's-members stock lists.
- `--universe current` re-runs everything on today's members, as in the first
  version, so the effect of the survivorship fix can be measured.

### Fixes to the pipeline

- `event_study.py` read `data/event_study_final.csv`, but no script created it.
  It is now built from `form4_with_returns.csv` inside `event_study.py`.
- `live_signal.py` now ranks only current index members (`universe.csv` now
  also lists former members).
- `find_bankruptcies.py` skips companies without a CIK.

### Corrections to the first version's report and README

- The benchmark was called a "buy-and-hold". It is an equal-weighted portfolio
  of all 400 stocks, rebalanced monthly.
- The report said the purchases were by "officers and directors". No filter on
  the owner's role was applied, so holders of more than 10% are included too.
- The report said the alternative rankings (number of buyers, dollars per buyer)
  did worse "on every metric". They had lower returns and Sharpe ratios but
  slightly smaller drawdowns. The "dollars per buyer, top 50" portfolio held
  only about 20 stocks on average.
- The README said "only the more diversified configurations" beat the benchmark
  on Sharpe ratio. Only one of the nine (3-month look-back, top 50) did.
- The report's grid of all nine combinations didn't match the saved file
  `data/portfolio_backtest_grid.csv`. Every cell differed slightly (up to 0.9
  percentage points of annual return and 0.015 of Sharpe ratio). The report's
  numbers match `portfolio_backtest_signals.csv` and `equity_curve_best.csv`,
  which come from a different run. The page now uses the grid file (24.2% a
  year for the main combination instead of 24.0%). Which run is right can't be
  checked without re-running. The revised pipeline produces all of these from
  one run, and `build_report.py` writes the page directly from those files.
- The chart plotted each month's end value at the month's first day. It is now
  plotted at month end.
- The README said the project includes a machine-learning validation. That code
  was deliberately kept out of the repository, so the claim was removed.
- The snapshot page said re-running weekly matched "the reporting lag insiders
  are legally allowed". Form 4s are due within two business days of a trade.
- The snapshot page said the event study "treats sales as a weaker, noisier
  signal". It doesn't; the net-dollar ranking weighs purchases and sales
  equally.
- The snapshot page called the ranking "validated in the backtest". Given the
  problems above, it now says the backtest results are preliminary.

### Report design

- Both pages were rewritten in plainer language and a simpler single-column
  layout with one shared stylesheet (`style.css`). Both are now generated from
  the data (`build_report.py`, `build_live_page.py`) instead of edited by hand.

## August 2026: first version

Event study, portfolio backtest and live snapshot on today's S&P MidCap 400
members, 2018 Q3 to 2026 Q1.
