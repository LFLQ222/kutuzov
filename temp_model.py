import os
import json
import numpy as np
import pandas as pd
from scipy.stats import norm
from xgboost import XGBRegressor
from datetime import datetime, timedelta
from config import CITIES, TEMP_LOOKBACK_YEARS
import temp_weather


MODELS_DIR = "temp_models"


def build_features(df):
    """engineer features from daily weather data"""
    df = df.copy().sort_values("date").reset_index(drop=True)

    for i in range(1, 8):
        df[f"tmax_lag{i}"] = df["tmax"].shift(i)

    df["tmax_rolling7"] = df["tmax"].rolling(7).mean()
    df["tmax_rolling30"] = df["tmax"].rolling(30).mean()

    doy = df["date"].dt.dayofyear
    df["day_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["day_cos"] = np.cos(2 * np.pi * doy / 365.25)

    df["tmin_lag1"] = df["tmin"].shift(1)
    df["precip_lag1"] = df["precip"].shift(1)
    df["wind_lag1"] = df["wind"].shift(1)
    df["humidity_lag1"] = df["humidity"].shift(1)
    df["pressure_lag1"] = df["pressure"].shift(1)

    #slope of last 7 days highs
    df["temp_trend"] = df["tmax"].rolling(7).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 7 else 0, raw=False
    )

    return df


FEATURE_COLS = [
    "tmax_lag1", "tmax_lag2", "tmax_lag3", "tmax_lag4", "tmax_lag5", "tmax_lag6", "tmax_lag7",
    "tmax_rolling7", "tmax_rolling30", "day_sin", "day_cos",
    "tmin_lag1", "precip_lag1", "wind_lag1", "humidity_lag1", "pressure_lag1", "temp_trend",
]


def train_city_model(city_key):
    """train xgboost model for a city, return (model, residual_std, mae)"""
    city = CITIES[city_key]
    end = datetime.now().date() - timedelta(days=1)
    start = end - timedelta(days=365 * TEMP_LOOKBACK_YEARS)

    print(f"fetching {TEMP_LOOKBACK_YEARS}y history for {city_key}...")
    df = temp_weather.fetch_historical(city["lat"], city["lon"], str(start), str(end))

    if city["unit"] == "F":
        df["tmax"] = df["tmax"].apply(temp_weather.c_to_f)
        df["tmin"] = df["tmin"].apply(temp_weather.c_to_f)

    df = build_features(df).dropna(subset=FEATURE_COLS + ["tmax"])

    #split: last 365 days = validation
    split_idx = len(df) - 365
    train_df = df.iloc[:split_idx]
    val_df = df.iloc[split_idx:]

    X_train = train_df[FEATURE_COLS].values
    y_train = train_df["tmax"].values
    X_val = val_df[FEATURE_COLS].values
    y_val = val_df["tmax"].values

    model = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05, verbosity=0)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_val)
    residuals = y_val - y_pred
    residual_std = float(np.std(residuals))
    mae = float(np.mean(np.abs(residuals)))

    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = os.path.join(MODELS_DIR, f"{city_key}_model.json")
    model.save_model(model_path)

    meta = {"residual_std": residual_std, "mae": mae, "unit": city["unit"], "trained": str(datetime.now().date())}
    with open(os.path.join(MODELS_DIR, f"{city_key}_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  {city_key}: MAE={mae:.2f}°{city['unit']}, residual_std={residual_std:.2f}")
    return model, residual_std, mae


def load_model(city_key):
    """load trained model + metadata"""
    model_path = os.path.join(MODELS_DIR, f"{city_key}_model.json")
    meta_path = os.path.join(MODELS_DIR, f"{city_key}_meta.json")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"no model for {city_key} — run --train {city_key} first")
    model = XGBRegressor()
    model.load_model(model_path)
    with open(meta_path) as f:
        meta = json.load(f)
    return model, meta


def predict_distribution(city_key, target_date=None):
    """predict (mu, sigma) for a city's daily high on target_date"""
    city = CITIES[city_key]
    model, meta = load_model(city_key)

    df = temp_weather.fetch_recent_and_forecast(city["lat"], city["lon"])

    if city["unit"] == "F":
        df["tmax"] = df["tmax"].apply(temp_weather.c_to_f)
        df["tmin"] = df["tmin"].apply(temp_weather.c_to_f)

    df = build_features(df)

    if target_date:
        target = pd.Timestamp(target_date)
    else:
        target = df["date"].max()

    row = df[df["date"] == target]
    if row.empty:
        raise ValueError(f"no data for {target_date} — check forecast availability")

    X = row[FEATURE_COLS].values
    mu = float(model.predict(X)[0])
    sigma = meta["residual_std"]
    return mu, sigma


def range_probabilities(mu, sigma, ranges):
    """compute probability for each (low, high) range using gaussian cdf"""
    for r in ranges:
        low, high = r["low"], r["high"]
        if low is None:
            r["model"] = float(norm.cdf(high, mu, sigma))
        elif high is None:
            r["model"] = float(1.0 - norm.cdf(low, mu, sigma))
        else:
            r["model"] = float(norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma))
    return ranges
