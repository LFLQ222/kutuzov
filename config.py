import os
from dotenv import load_dotenv

load_dotenv()

POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_SECRET = os.getenv("POLYMARKET_SECRET", "")
POLYMARKET_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
BET_BUDGET = float(os.getenv("BET_BUDGET", "10"))
MIN_PROFIT_MARGIN = float(os.getenv("MIN_PROFIT_MARGIN", "0.02"))

MAX_EVENT_DAYS = 90
MIN_CONCENTRATION = 0.90
MAX_TOP_K = 4
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

SELL_THRESHOLD = 0.15
REBALANCE_COVERAGE = 0.80
REBALANCE_INTERVAL = 10

TEMP_EDGE_THRESHOLD = float(os.getenv("TEMP_EDGE_THRESHOLD", "0.08"))
TEMP_BET_BUDGET = float(os.getenv("TEMP_BET_BUDGET", "10"))
TEMP_LOOKBACK_YEARS = 5

CITIES = {
    "miami": {"lat": 25.76, "lon": -80.19, "unit": "F"},
    "london": {"lat": 51.51, "lon": -0.13, "unit": "C"},
    "nyc": {"lat": 40.71, "lon": -74.01, "unit": "F"},
    "singapore": {"lat": 1.35, "lon": 103.82, "unit": "C"},
    "lucknow": {"lat": 26.85, "lon": 80.95, "unit": "C"},
    "milan": {"lat": 45.46, "lon": 9.19, "unit": "C"},
    "madrid": {"lat": 40.42, "lon": -3.70, "unit": "C"},
    "ankara": {"lat": 39.93, "lon": 32.86, "unit": "C"},
}
