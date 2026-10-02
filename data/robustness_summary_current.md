# Robustness checks (current universe, 25 bps one-way costs)

## Headline (net of costs)

| | CAGR | vol | Sharpe (excess of T-bills) | Sortino | max DD |
|---|---|---|---|---|---|
| strategy (3m, top 50) | +21.5% | 28.0% | 0.74 | 1.23 | -43.2% |
| EW benchmark | +18.8% | 23.1% | 0.74 | 1.17 | -37.0% |
| MDY ETF | +11.8% | 20.9% | 0.50 | 0.75 | -34.0% |
| strategy, gross of costs | +24.1% | 28.0% | 0.81 | 1.37 | -42.9% |

Average one-way turnover 35% per month; on average 34 of the 50 holdings have net insider *buying*; any remaining slots go to the names with the least net selling.

## 1. Factor-adjusted alpha (Newey-West t, annualized alpha)

| series | CAPM | FF3 | FF5 | FF5+Mom | SMB beta | HML beta | Mom beta |
|---|---|---|---|---|---|---|---|
| strategy_net | +3.0% (t=0.4) | +7.8% (t=1.8) | +7.5% (t=1.9) | +8.6% (t=2.7) | +0.99 | +0.16 | -0.15 |
| strategy_gross | +5.1% (t=0.7) | +9.9% (t=2.2) | +9.6% (t=2.4) | +10.7% (t=3.4) | +0.99 | +0.16 | -0.15 |
| ew_benchmark_net | +0.8% (t=0.2) | +3.9% (t=2.8) | +3.9% (t=3.1) | +4.6% (t=3.8) | +0.65 | +0.16 | -0.09 |
| mdy | -4.4% (t=-1.3) | -1.9% (t=-1.4) | -1.8% (t=-1.5) | -1.6% (t=-1.3) | +0.53 | +0.16 | -0.03 |
| strategy_minus_ew | +2.2% (t=0.6) | +3.8% (t=1.0) | +3.5% (t=1.0) | +4.0% (t=1.4) | +0.35 | +0.00 | -0.06 |
| strategy_minus_mdy | +7.4% (t=1.6) | +9.6% (t=2.1) | +9.3% (t=2.2) | +10.3% (t=3.0) | +0.46 | -0.00 | -0.12 |
| purchases_only_1m | +0.6% (t=0.1) | +8.6% (t=0.8) | +8.0% (t=0.8) | +6.8% (t=0.8) | +1.73 | -0.06 | +0.16 |
| sales_only_1m | -4.1% (t=-1.6) | -0.7% (t=-0.3) | -0.6% (t=-0.3) | -0.5% (t=-0.2) | +0.64 | +0.02 | -0.00 |
| purchases_only_3m | +1.9% (t=0.3) | +6.9% (t=1.5) | +6.7% (t=1.6) | +7.3% (t=2.0) | +1.02 | +0.20 | -0.07 |
| sales_only_3m | -1.1% (t=-0.4) | +1.7% (t=1.1) | +1.8% (t=1.1) | +1.8% (t=1.2) | +0.58 | +0.10 | -0.01 |
| purchases_minus_sales_3m | +3.0% (t=0.6) | +5.2% (t=1.1) | +5.0% (t=1.1) | +5.4% (t=1.3) | +0.44 | +0.10 | -0.06 |

Read: if the FF5+Mom alpha of `strategy_net` / `strategy_minus_ew` is small or its t-stat is below ~2, the edge is explained by factor tilts rather than insider information.

## 2. Purchases-only calendar-time portfolios (one observation per month)

| portfolio | avg stocks held | months with no holdings | ann. return | Sharpe | max DD |
|---|---|---|---|---|---|
| purchases_only_1m | 22.8 | 2 | +17.6% | 0.52 | -45% |
| sales_only_1m | 126.3 | 2 | +13.0% | 0.53 | -32% |
| purchases_only_3m | 58.3 | 0 | +20.2% | 0.70 | -43% |
| sales_only_3m | 212.0 | 0 | +16.3% | 0.67 | -34% |

## 3. Placebo: 1000 random 50-stock portfolios from the same universe

Strategy Sharpe 0.74 beats 99.8% of random portfolios (placebo median 0.51, 95th pct 0.64); CAGR +21.5% beats 100.0% (placebo median +12.8%). One-sided p-value for Sharpe = 0.002.

## 4. Drawdowns

Max drawdown: strategy -43.2%, EW benchmark -37.0%, MDY -34.0%. Strategy beta to MDY = 1.23.

- **Volatility-matched** (strategy scaled by 0.83 to the EW benchmark's volatility, rest in T-bills): CAGR +18.8%, max DD -36.3%, vs EW benchmark +18.8% / -37.0%.
- **Market-hedged** (short 1.23x MDY): CAGR +10.5%, Sharpe 0.70, max DD -6.4%.

| benchmark drawdown (peak -> trough) | EW benchmark | MDY | strategy |
|---|---|---|---|
| 2020-01-02 -> 2020-04-01 | -37.0% | -34.0% | -43.2% |
| 2022-01-03 -> 2022-10-03 | -17.3% | -19.6% | -10.7% |
| 2023-08-01 -> 2023-11-01 | -11.5% | -12.2% | -14.0% |
| 2024-12-02 -> 2025-05-01 | -13.1% | -14.2% | -14.9% |

## 5. Market regimes

| year | months | strategy | EW benchmark | MDY | strategy - EW |
|---|---|---|---|---|---|
| 2019 | 11.0 | +22.2% | +21.0% | +13.9% | +1.2% |
| 2020 | 12.0 | +14.7% | +21.4% | +11.6% | -6.8% |
| 2021 | 12.0 | +81.4% | +38.1% | +26.5% | +43.3% |
| 2022 | 12.0 | +1.1% | -9.4% | -13.9% | +10.5% |
| 2023 | 12.0 | +20.4% | +26.0% | +16.2% | -5.6% |
| 2024 | 12.0 | +9.4% | +17.5% | +13.7% | -8.1% |
| 2025 | 12.0 | +13.6% | +15.6% | +8.9% | -2.0% |
| 2026 | 6.0 | +10.3% | +13.8% | +14.6% | -3.5% |

Years the strategy beat the EW benchmark: 3 of 8.

| regime | months | strategy avg/mo | EW avg/mo | MDY avg/mo | capture vs MDY | strategy - EW avg/mo |
|---|---|---|---|---|---|---|
| MDY up months | 51 | +6.75% | +5.88% | +5.02% | 1.34 | +0.87% |
| MDY down months | 38 | -4.45% | -3.97% | -4.12% | 1.08 | -0.48% |

The study window (2019-2026) contains two sharp drawdowns (COVID 2020, 2022) but no prolonged bear market like 2000-02 or 2008-09. SEC's insider data sets start in 2006, but Wikipedia's index-change history (used for the point-in-time universe) only goes back to 2012, so extending the window to cover 2008 needs a different constituent-history source.

## Survivorship bias: point-in-time vs today's constituents

| config | cost | universe | CAGR | Sharpe | max DD | EW bench CAGR | EW bench Sharpe |
|---|---|---|---|---|---|---|---|
| 3m / top 50 | 0 bps | today's members (old) | +24.1% | 0.81 | -42.9% | +19.1% | 0.75 |
| 3m / top 50 | 25 bps | today's members (old) | +21.5% | 0.74 | -43.2% | +18.8% | 0.74 |
| 3m / top 50 | 0 bps | point-in-time | +10.9% | 0.42 | -43.9% | +12.5% | 0.51 |
| 3m / top 50 | 25 bps | point-in-time | +8.6% | 0.34 | -44.2% | +12.2% | 0.50 |

Price coverage of point-in-time member-days: 87.0% overall; 203 of 349 companies removed during the window have Yahoo prices (62.7% of their member-days). The unpriced remainder (mostly acquired companies, whose tickers Yahoo drops) is a residual survivorship gap; acquisitions usually close at a premium, so this gap is more likely to understate than overstate benchmark returns.

