#!/usr/bin/env bash
# Full pipeline, in order. Needs network access to en.wikipedia.org, www.sec.gov,
# data.sec.gov, query1.finance.yahoo.com and mba.tuck.dartmouth.edu.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src

python src/build_universe.py        # point-in-time S&P 400 membership
python src/collect_form4.py         # SEC bulk Form 4 data (+ CIKs for delisted names)
python src/clean_form4.py
python src/find_bankruptcies.py
python src/collect_prices.py        # Yahoo prices + MDY, writes price_coverage.csv
python src/collect_factors.py       # Fama-French 5 factors + momentum + RF
python src/compute_returns.py       # forward + market-adjusted returns per filing

# "pit" = point-in-time universe (main results); "current" = the original
# today's-constituents universe, kept only to measure survivorship bias
for u in current pit; do
  python src/build_benchmark.py      --universe "$u"
  python src/event_study.py          --universe "$u"
  python src/portfolio_backtest.py   --universe "$u"
  python src/portfolio_backtest_v2.py --universe "$u"
done
python src/robustness.py --universe pit   # reads both grids for the survivorship comparison
python src/build_report.py                # regenerates index.html from the results
