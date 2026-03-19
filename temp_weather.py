import os
import requests
import pandas as pd
from datetime import datetime, timedelta


CACHE_DIR = "temp_data"


def c_to_f(c):
    return c * 9 / 5 + 32


def fetch_historical(lat, lon, start_date, end_date):
    """fetch daily weather from open-meteo archive api"""
    cache_key = f"{lat}_{lon}_{start_date}_{end_date}.csv"
    cache_path = os.path.join(CACHE_DIR, cache_key)

    if os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["date"])

    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean,surface_pressure_mean",
            "timezone": "auto",
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()["daily"]

    df = pd.DataFrame({
        "date": pd.to_datetime(data["time"]),
        "tmax": data["temperature_2m_max"],
        "tmin": data["temperature_2m_min"],
        "precip": data["precipitation_sum"],
        "wind": data["wind_speed_10m_max"],
        "humidity": data["relative_humidity_2m_mean"],
        "pressure": data["surface_pressure_mean"],
    })
    df = df.dropna(subset=["tmax"])

    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_csv(cache_path, index=False)
    return df


def fetch_forecast(lat, lon):
    """fetch 7-day forecast from open-meteo"""
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean,surface_pressure_mean",
            "timezone": "auto",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["daily"]

    return pd.DataFrame({
        "date": pd.to_datetime(data["time"]),
        "tmax": data["temperature_2m_max"],
        "tmin": data["temperature_2m_min"],
        "precip": data["precipitation_sum"],
        "wind": data["wind_speed_10m_max"],
        "humidity": data["relative_humidity_2m_mean"],
        "pressure": data["surface_pressure_mean"],
    })


def fetch_recent_and_forecast(lat, lon, days_back=30):
    """fetch recent history + forecast, combined into one df"""
    end = datetime.now().date()
    start = end - timedelta(days=days_back)
    hist = fetch_historical(lat, lon, str(start), str(end - timedelta(days=1)))
    fcast = fetch_forecast(lat, lon)
    return pd.concat([hist, fcast], ignore_index=True).drop_duplicates(subset=["date"])
