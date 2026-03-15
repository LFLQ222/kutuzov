import os
from dotenv import load_dotenv

load_dotenv()

#api credentials
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_SECRET = os.getenv("POLYMARKET_SECRET", "")
POLYMARKET_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

#telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

#trading params
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
BET_BUDGET = float(os.getenv("BET_BUDGET", "10"))
MIN_PROFIT_MARGIN = float(os.getenv("MIN_PROFIT_MARGIN", "0.02"))

#discovery filters
MAX_EVENT_DAYS = 90
MIN_CONCENTRATION = 0.90
MAX_TOP_K = 4

#api urls
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
