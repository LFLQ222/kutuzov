import os
from dotenv import load_dotenv

load_dotenv()

POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
