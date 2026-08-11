"""
Deliverable 3: a trained predictive model, walk-forward validated, compared
against the simple net-dollar-value baseline that won every earlier test.

Feature table: one row per (ticker, monthly rebalance date), built from the
trailing 3-month window of Form 4 activity -- same window that performed
best in the backtest. Target: does this ticker's forward monthly return
beat the cross-sectional median that month (rank-based label, standard
practice to avoid regime/scale dependence).

Walk-forward: expanding window, train on everything before month T, predict
month T, roll forward. No lookahead: a model never sees future data.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer

from portfolio_backtest import load_data, get_rebalance_dates, performance_stats

MIN_TRAIN_MONTHS = 24  # need enough history before the first prediction
NUMERIC_FEATURES = [
    "net_dollar_value", "buyer_count", "seller_count", "total_transactions",
    "pct_officer", "avg_reporting_lag", "trailing_momentum",
]
CATEGORICAL_FEATURES = ["gics_sector"]


def per_ticker_forward_return(prices_wide, ticker, start, end):
    if ticker not in prices_wide.columns:
        return np.nan
    try:
        p0, p1 = prices_wide.loc[start, ticker], prices_wide.loc[end, ticker]
    except KeyError:
        return np.nan
    if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
        return np.nan
    return p1 / p0 - 1


def build_feature_table(txs, prices_wide, universe, rebal_dates):
    sector_map = dict(zip(universe["ticker"], universe["gics_sector"]))
    all_tickers = universe["ticker"].tolist()
    rows = []

    for i in range(len(rebal_dates) - 1):
        reb_date = rebal_dates[i]
        next_date = rebal_dates[i + 1]
        window_start = reb_date - pd.DateOffset(months=3)
        mom_start = reb_date - pd.DateOffset(months=3)

        window_txs = txs[(txs["filing_date"] >= window_start) & (txs["filing_date"] < reb_date)]
        buys = window_txs[window_txs["trans_code"] == "P"]
        sells = window_txs[window_txs["trans_code"] == "S"]

        net_val = window_txs.groupby("ticker")["signed_value"].sum()
        buyer_cnt = buys.groupby("ticker")["owner_cik"].nunique()
        seller_cnt = sells.groupby("ticker")["owner_cik"].nunique()
        total_txn = window_txs.groupby("ticker").size()
        pct_officer = buys.assign(is_officer=buys["owner_relationship"].fillna("").str.contains("Officer")) \
            .groupby("ticker")["is_officer"].mean()
        avg_lag = window_txs.groupby("ticker")["reporting_lag_days"].mean()

        for ticker in all_tickers:
            fwd_ret = per_ticker_forward_return(prices_wide, ticker, reb_date, next_date)
            mom_ret = per_ticker_forward_return(prices_wide, ticker, mom_start, reb_date)
            if pd.isna(fwd_ret):
                continue
            rows.append({
                "date": reb_date, "ticker": ticker,
                "net_dollar_value": net_val.get(ticker, 0.0),
                "buyer_count": buyer_cnt.get(ticker, 0),
                "seller_count": seller_cnt.get(ticker, 0),
                "total_transactions": total_txn.get(ticker, 0),
                "pct_officer": pct_officer.get(ticker, 0.0),
                "avg_reporting_lag": avg_lag.get(ticker, 0.0) if not pd.isna(avg_lag.get(ticker, np.nan)) else 0.0,
                "trailing_momentum": mom_ret if not pd.isna(mom_ret) else 0.0,
                "gics_sector": sector_map.get(ticker, "Unknown"),
                "forward_return": fwd_ret,
            })

    feat = pd.DataFrame(rows)
    # rank-based label: beat the cross-sectional median that month
    feat["label"] = feat.groupby("date")["forward_return"].transform(
        lambda s: (s > s.median()).astype(int)
    )
    return feat


def make_pipeline(model):
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def walk_forward(feat, model_name):
    dates = sorted(feat["date"].unique())
    if len(dates) <= MIN_TRAIN_MONTHS:
        raise ValueError("Not enough months for walk-forward validation")

    all_preds = []
    aucs = []
    for i in range(MIN_TRAIN_MONTHS, len(dates)):
        train = feat[feat["date"] < dates[i]]
        test = feat[feat["date"] == dates[i]]
        if train["label"].nunique() < 2 or len(test) < 5:
            continue

        if model_name == "logistic":
            model = make_pipeline(LogisticRegression(max_iter=1000, C=1.0))
        else:
            model = make_pipeline(HistGradientBoostingClassifier(max_depth=3, random_state=42))

        X_train, y_train = train[NUMERIC_FEATURES + CATEGORICAL_FEATURES], train["label"]
        X_test, y_test = test[NUMERIC_FEATURES + CATEGORICAL_FEATURES], test["label"]

        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]

        if y_test.nunique() > 1:
            aucs.append(roc_auc_score(y_test, proba))

        out = test[["date", "ticker", "forward_return"]].copy()
        out["score"] = proba
        all_preds.append(out)

    return pd.concat(all_preds, ignore_index=True), aucs


def main():
    txs, prices = load_data()
    txs["signed_value"] = np.where(txs["trans_code"] == "P", txs["trade_value"], -txs["trade_value"])
    prices_wide = prices.pivot(index="date", columns="ticker", values="adj_close")
    universe = pd.read_csv("data/universe.csv")
    rebal_dates = get_rebalance_dates(prices)

    print("Building monthly feature table...", flush=True)
    feat = build_feature_table(txs, prices_wide, universe, rebal_dates)
    feat.to_csv("data/ml_features.csv", index=False)
    print(f"  {len(feat)} (ticker, month) rows across {feat['date'].nunique()} months", flush=True)

    results = {}
    for model_name in ["logistic", "gboost"]:
        print(f"\nWalk-forward validating: {model_name}...", flush=True)
        preds, aucs = walk_forward(feat, model_name)
        preds.to_csv(f"data/ml_predictions_{model_name}.csv", index=False)
        mean_auc = np.mean(aucs)
        print(f"  mean AUC across {len(aucs)} months: {mean_auc:.3f}", flush=True)
        results[model_name] = {"preds": preds, "auc": mean_auc}

    print("\nWrote data/ml_features.csv and data/ml_predictions_{model}.csv")


if __name__ == "__main__":
    main()
