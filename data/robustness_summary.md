# Robustness checks (pit universe, 25 bps one-way costs)

## Headline (net of costs)

| | CAGR | vol | Sharpe (excess of T-bills) | Sortino | max DD |
|---|---|---|---|---|---|
| strategy (3m, top 50) | +8.6% | 26.2% | 0.34 | 0.51 | -44.2% |
| EW benchmark | +12.2% | 22.6% | 0.50 | 0.76 | -36.9% |
| MDY ETF | +11.8% | 20.9% | 0.50 | 0.75 | -34.0% |
| strategy, gross of costs | +10.9% | 26.2% | 0.42 | 0.63 | -43.9% |

Average one-way turnover 35% per month; on average 34 of the 50 holdings have net insider *buying*; any remaining slots go to the names with the least net selling.

## 1. Factor-adjusted alpha (Newey-West t, annualized alpha)

| series | CAPM | FF3 | FF5 | FF5+Mom | SMB beta | HML beta | Mom beta |
|---|---|---|---|---|---|---|---|
| strategy_net | -8.4% (t=-1.5) | -5.2% (t=-1.9) | -5.3% (t=-2.2) | -2.9% (t=-1.4) | +0.64 | +0.31 | -0.30 |
| strategy_gross | -6.3% (t=-1.1) | -3.1% (t=-1.2) | -3.2% (t=-1.3) | -0.8% (t=-0.4) | +0.64 | +0.31 | -0.31 |
| ew_benchmark_net | -4.6% (t=-1.2) | -1.8% (t=-1.2) | -1.8% (t=-1.3) | -0.8% (t=-0.6) | +0.58 | +0.19 | -0.13 |
| mdy | -4.4% (t=-1.3) | -1.9% (t=-1.4) | -1.8% (t=-1.5) | -1.6% (t=-1.3) | +0.53 | +0.16 | -0.03 |
| strategy_minus_ew | -3.8% (t=-1.7) | -3.4% (t=-2.0) | -3.4% (t=-2.1) | -2.1% (t=-1.4) | +0.06 | +0.12 | -0.17 |
| strategy_minus_mdy | -4.0% (t=-1.4) | -3.4% (t=-1.5) | -3.4% (t=-1.7) | -1.3% (t=-0.8) | +0.11 | +0.14 | -0.27 |
| purchases_only_1m | -12.4% (t=-2.3) | -9.1% (t=-2.7) | -8.9% (t=-2.9) | -8.0% (t=-2.8) | +0.76 | +0.32 | -0.11 |
| sales_only_1m | -8.4% (t=-3.0) | -5.4% (t=-2.9) | -5.4% (t=-3.0) | -5.3% (t=-2.7) | +0.60 | +0.07 | -0.01 |
| purchases_only_3m | -7.2% (t=-1.4) | -3.8% (t=-1.6) | -3.7% (t=-1.6) | -2.0% (t=-1.0) | +0.68 | +0.36 | -0.22 |
| sales_only_3m | -5.7% (t=-1.8) | -3.0% (t=-1.9) | -3.0% (t=-2.0) | -2.8% (t=-1.8) | +0.57 | +0.11 | -0.03 |
| purchases_minus_sales_3m | -1.5% (t=-0.5) | -0.7% (t=-0.4) | -0.7% (t=-0.4) | +0.8% (t=0.5) | +0.11 | +0.25 | -0.18 |

Read: if the FF5+Mom alpha of `strategy_net` / `strategy_minus_ew` is small or its t-stat is below ~2, the edge is explained by factor tilts rather than insider information.

## 2. Purchases-only calendar-time portfolios (one observation per month)

| portfolio | avg stocks held | months with no holdings | ann. return | Sharpe | max DD |
|---|---|---|---|---|---|
| purchases_only_1m | 22.1 | 2 | +4.2% | 0.19 | -46% |
| sales_only_1m | 107.5 | 2 | +7.9% | 0.33 | -34% |
| purchases_only_3m | 55.8 | 0 | +9.6% | 0.38 | -43% |
| sales_only_3m | 186.2 | 0 | +10.9% | 0.46 | -35% |

## 3. Placebo: 1000 random 50-stock portfolios from the same universe

Strategy Sharpe 0.34 beats 83.0% of random portfolios (placebo median 0.28, 95th pct 0.39); CAGR +8.6% beats 86.1% (placebo median +6.7%). One-sided p-value for Sharpe = 0.170.

## 4. Drawdowns

Max drawdown: strategy -44.2%, EW benchmark -36.9%, MDY -34.0%. Strategy beta to MDY = 1.20.

- **Volatility-matched** (strategy scaled by 0.86 to the EW benchmark's volatility, rest in T-bills): CAGR +8.3%, max DD -38.8%, vs EW benchmark +12.2% / -36.9%.
- **Market-hedged** (short 1.20x MDY): CAGR -1.1%, Sharpe -0.49, max DD -16.0%.

| benchmark drawdown (peak -> trough) | EW benchmark | MDY | strategy |
|---|---|---|---|
| 2020-01-02 -> 2020-04-01 | -36.9% | -34.0% | -44.2% |
| 2022-01-03 -> 2022-10-03 | -19.3% | -19.6% | -19.3% |
| 2023-08-01 -> 2023-11-01 | -12.6% | -12.2% | -14.7% |
| 2024-12-02 -> 2025-05-01 | -14.6% | -14.2% | -16.0% |

## 5. Market regimes

| year | months | strategy | EW benchmark | MDY | strategy - EW |
|---|---|---|---|---|---|
| 2019 | 11 | +11.1% | +12.7% | +13.9% | -1.6% |
| 2020 | 12 | +0.0% | +13.2% | +11.6% | -13.2% |
| 2021 | 12 | +38.1% | +29.9% | +26.5% | +8.2% |
| 2022 | 12 | -8.0% | -11.4% | -13.9% | +3.4% |
| 2023 | 12 | +15.5% | +19.2% | +16.2% | -3.7% |
| 2024 | 12 | +5.1% | +10.8% | +13.7% | -5.6% |
| 2025 | 12 | +1.5% | +8.3% | +8.9% | -6.8% |
| 2026 | 6 | +6.0% | +11.8% | +14.6% | -5.8% |

Years the strategy beat the EW benchmark: 2 of 8.

| regime | months | strategy avg/mo | EW avg/mo | MDY avg/mo | capture vs MDY | strategy - EW avg/mo |
|---|---|---|---|---|---|---|
| MDY up months | 51 | +5.61% | +5.33% | +5.02% | 1.12 | +0.28% |
| MDY down months | 38 | -5.22% | -4.39% | -4.12% | 1.27 | -0.83% |

The study window (2019-2026) contains two sharp drawdowns (COVID 2020, 2022) but no prolonged bear market like 2000-02 or 2008-09. SEC's insider data sets start in 2006, but Wikipedia's index-change history (used for the point-in-time universe) only goes back to 2012, so extending the window to cover 2008 needs a different constituent-history source.

## Survivorship bias: point-in-time vs today's constituents

| config | cost | universe | CAGR | Sharpe | max DD | EW bench CAGR | EW bench Sharpe |
|---|---|---|---|---|---|---|---|
| 3m / top 50 | 0 bps | today's members (old) | +24.1% | 0.81 | -42.9% | +19.1% | 0.75 |
| 3m / top 50 | 25 bps | today's members (old) | +21.5% | 0.74 | -43.2% | +18.8% | 0.74 |
| 3m / top 50 | 0 bps | point-in-time | +10.9% | 0.42 | -43.9% | +12.5% | 0.51 |
| 3m / top 50 | 25 bps | point-in-time | +8.6% | 0.34 | -44.2% | +12.2% | 0.50 |

Price coverage of point-in-time member-days: 87.0% overall; 203 of 349 companies removed during the window have Yahoo prices (62.7% of their member-days). The unpriced remainder (mostly acquired companies, whose tickers Yahoo drops) is a residual survivorship gap; acquisitions usually close at a premium, so this gap is more likely to understate than overstate benchmark returns.

