import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from config import CITIES, TEMP_EDGE_THRESHOLD, TEMP_BET_BUDGET, TEMP_LOOKBACK_YEARS
import temp_weather
import temp_model


def climatological_probs(history_df, target_doy, ranges):
    """compute baseline probabilities from historical frequency around this day of year"""
    #use +/- 15 day window across all years
    doys = history_df["date"].dt.dayofyear
    window = history_df[(doys - target_doy).abs() % 365 <= 15]
    temps = window["tmax"].dropna().values

    if len(temps) < 10:
        return [{**r, "market": 1.0 / len(ranges)} for r in ranges]

    for r in ranges:
        low, high = r["low"], r["high"]
        if low is None:
            r["market"] = float(np.mean(temps < high))
        elif high is None:
            r["market"] = float(np.mean(temps >= low))
        else:
            r["market"] = float(np.mean((temps >= low) & (temps < high)))
        #add noise to simulate market inefficiency
        r["market"] = max(0.01, r["market"] + np.random.normal(0, 0.03))

    #normalize
    total = sum(r["market"] for r in ranges)
    for r in ranges:
        r["market"] = r["market"] / total

    return ranges


def generate_ranges(tmax_values, unit):
    """generate 2-degree range buckets covering the historical range"""
    lo = int(np.floor(np.percentile(tmax_values, 1) / 2) * 2)
    hi = int(np.ceil(np.percentile(tmax_values, 99) / 2) * 2)

    ranges = [{"low": None, "high": float(lo)}]
    for start in range(lo, hi, 2):
        ranges.append({"low": float(start), "high": float(start + 2)})
    ranges.append({"low": float(hi), "high": None})
    return ranges


def backtest_city(city_key, start_date, end_date, edge_threshold=None, budget=None):
    """walk-forward backtest for a city"""
    edge_threshold = edge_threshold or TEMP_EDGE_THRESHOLD
    budget = budget or TEMP_BET_BUDGET
    city = CITIES[city_key]
    unit = city["unit"]

    #fetch full history
    hist_start = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=365 * TEMP_LOOKBACK_YEARS)
    print(f"fetching history for {city_key}...")
    full_df = temp_weather.fetch_historical(city["lat"], city["lon"], str(hist_start.date()), end_date)

    if unit == "F":
        full_df["tmax"] = full_df["tmax"].apply(temp_weather.c_to_f)
        full_df["tmin"] = full_df["tmin"].apply(temp_weather.c_to_f)

    ranges = generate_ranges(full_df["tmax"].dropna().values, unit)

    test_start = pd.Timestamp(start_date)
    test_end = pd.Timestamp(end_date)
    test_days = full_df[(full_df["date"] >= test_start) & (full_df["date"] <= test_end)]

    results = []
    model = None
    last_train_month = None

    for _, day_row in test_days.iterrows():
        target_date = day_row["date"]
        actual_temp = day_row["tmax"]
        if pd.isna(actual_temp):
            continue

        #retrain monthly for speed
        month_key = (target_date.year, target_date.month)
        if month_key != last_train_month:
            train_end = target_date - timedelta(days=1)
            train_start = train_end - timedelta(days=365 * TEMP_LOOKBACK_YEARS)
            train_df = full_df[(full_df["date"] >= pd.Timestamp(train_start)) & (full_df["date"] < pd.Timestamp(target_date))]

            if len(train_df) < 365:
                continue

            feat_df = temp_model.build_features(train_df).dropna(subset=temp_model.FEATURE_COLS + ["tmax"])
            split = len(feat_df) - 365
            if split < 100:
                continue

            from xgboost import XGBRegressor
            model = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05, verbosity=0)
            X_train = feat_df.iloc[:split][temp_model.FEATURE_COLS].values
            y_train = feat_df.iloc[:split]["tmax"].values
            X_val = feat_df.iloc[split:][temp_model.FEATURE_COLS].values
            y_val = feat_df.iloc[split:]["tmax"].values

            model.fit(X_train, y_train)
            residuals = y_val - model.predict(X_val)
            residual_std = float(np.std(residuals))
            last_train_month = month_key

        if model is None:
            continue

        #predict for target day
        recent = full_df[full_df["date"] < pd.Timestamp(target_date)].tail(60)
        pred_df = temp_model.build_features(recent)
        pred_row = pred_df.dropna(subset=temp_model.FEATURE_COLS).tail(1)
        if pred_row.empty:
            continue

        mu = float(model.predict(pred_row[temp_model.FEATURE_COLS].values)[0])
        sigma = residual_std

        #simulate market from climatology
        day_ranges = [dict(r) for r in ranges]
        target_doy = target_date.dayofyear
        history_before = full_df[full_df["date"] < pd.Timestamp(target_date)]
        day_ranges = climatological_probs(history_before, target_doy, day_ranges)

        #compute model probabilities
        day_ranges = temp_model.range_probabilities(mu, sigma, day_ranges)

        #find edges and bet
        for r in day_ranges:
            edge = r["model"] - r["market"]
            if edge < edge_threshold:
                continue
            kelly = min(edge / (1 - r["market"]), 0.25)
            bet_amount = budget * kelly
            if bet_amount < 0.50:
                continue

            #check if actual temp falls in this range
            low, high = r["low"], r["high"]
            if low is None:
                won = actual_temp < high
            elif high is None:
                won = actual_temp >= low
            else:
                won = low <= actual_temp < high

            payout = bet_amount / r["market"] if won else 0
            profit = payout - bet_amount

            results.append({
                "date": str(target_date.date()),
                "range": f"{low}-{high}",
                "market": r["market"],
                "model": r["model"],
                "edge": edge,
                "bet": bet_amount,
                "won": won,
                "profit": profit,
                "actual": actual_temp,
                "predicted": mu,
            })

    return results


def backtest_report(results, city_key):
    """print backtest summary"""
    if not results:
        print("no bets placed")
        return

    df = pd.DataFrame(results)
    total_bet = df["bet"].sum()
    total_profit = df["profit"].sum()
    roi = total_profit / total_bet * 100 if total_bet > 0 else 0
    win_rate = df["won"].mean() * 100
    unique_days = df["date"].nunique()
    pred_errors = (df["actual"] - df["predicted"]).abs()

    print(f"\nbacktest: {city_key} {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
    print(f"  days with bets: {unique_days}")
    print(f"  total bets: {len(df)}")
    print(f"  profit: ${total_profit:.2f} ({roi:.1f}% ROI)")
    print(f"  win rate: {win_rate:.1f}%")
    print(f"  avg edge: {df['edge'].mean():.1%}")
    print(f"  avg prediction error: {pred_errors.mean():.1f}°")


def main():
    if len(sys.argv) < 2:
        print("usage: python temp_backtest.py <city> [--start YYYY-MM-DD] [--end YYYY-MM-DD]")
        return

    city_key = sys.argv[1].lower()
    if city_key not in CITIES:
        print(f"unknown city: {city_key}. available: {', '.join(CITIES.keys())}")
        return

    start = "2024-01-01"
    end = "2024-12-31"
    if "--start" in sys.argv:
        start = sys.argv[sys.argv.index("--start") + 1]
    if "--end" in sys.argv:
        end = sys.argv[sys.argv.index("--end") + 1]

    results = backtest_city(city_key, start, end)
    backtest_report(results, city_key)


if __name__ == "__main__":
    main()
