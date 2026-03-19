import json
import sys
import re
import time
import requests
from datetime import datetime, timezone
from config import (
    GAMMA_API_URL, CITIES, TEMP_EDGE_THRESHOLD, TEMP_BET_BUDGET, DRY_RUN,
    POLYMARKET_API_KEY, PRIVATE_KEY, CLOB_API_URL,
)
import temp_model

POSITIONS_FILE = "temp_positions.json"


def fetch_temp_events():
    """find all open temperature events from gamma api"""
    events = []
    offset = 0
    while True:
        resp = requests.get(
            f"{GAMMA_API_URL}/events",
            params={"closed": "false", "limit": 100, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for e in batch:
            title = e.get("title", "").lower()
            if "temperature" in title and any(c in title for c in CITIES):
                events.append(e)
        if len(batch) < 100:
            break
        offset += 100
    return sorted(events, key=lambda e: e.get("endDate", ""))


def detect_city(title):
    """match event title to a city key"""
    title_lower = title.lower()
    for key in CITIES:
        if key in title_lower:
            return key
    #handle "new york" -> nyc
    if "new york" in title_lower or "nyc" in title_lower:
        return "nyc"
    return None


def parse_temp_range(question):
    """parse market question into (low, high) temperature range"""
    q = question.lower().replace("°", " ").replace("  ", " ")

    #"between 72 and 73" or "72-73"
    m = re.search(r"between\s+(-?\d+\.?\d*)\s*(?:and|-)\s*(-?\d+\.?\d*)", q)
    if m:
        return float(m.group(1)), float(m.group(2))

    m = re.search(r"(-?\d+\.?\d*)\s*-\s*(-?\d+\.?\d*)", q)
    if m:
        return float(m.group(1)), float(m.group(2))

    #"greater than 80" / "above 80"
    m = re.search(r"(?:greater than|above|over|more than)\s+(-?\d+\.?\d*)", q)
    if m:
        return float(m.group(1)), None

    #"less than 68" / "below 68"
    m = re.search(r"(?:less than|below|under)\s+(-?\d+\.?\d*)", q)
    if m:
        return None, float(m.group(1))

    return None


def format_temp_range(low, high, unit):
    if low is None:
        return f"<{high:.0f}°{unit}"
    if high is None:
        return f">{low:.0f}°{unit}"
    return f"{low:.0f}-{high:.0f}°{unit}"


def parse_event_markets(event):
    """extract markets with prices and token ids"""
    markets = []
    for m in event.get("markets", []):
        if not m.get("active"):
            continue
        op = m.get("outcomePrices")
        if not op:
            continue
        try:
            price = float(json.loads(op)[0])
        except (json.JSONDecodeError, IndexError, ValueError):
            continue
        if price <= 0.001:
            continue
        r = parse_temp_range(m.get("question", ""))
        if not r:
            continue
        tokens = m.get("clobTokenIds")
        yes_token = None
        if tokens:
            try:
                yes_token = json.loads(tokens)[0]
            except (json.JSONDecodeError, IndexError):
                pass
        markets.append({"low": r[0], "high": r[1], "price": price, "yes_token": yes_token})

    markets.sort(key=lambda x: (x["low"] is None, x["low"] or 0))
    return markets


def compute_edge_bets(markets, mu, sigma, budget, threshold):
    """find ranges where model_prob - market_price > threshold, size by kelly"""
    markets = temp_model.range_probabilities(mu, sigma, markets)
    bets = []
    for m in markets:
        edge = m["model"] - m["price"]
        if edge < threshold:
            continue
        kelly = min(edge / (1 - m["price"]), 0.25)
        amount = budget * kelly
        if amount < 0.50:
            continue
        bets.append({
            "low": m["low"],
            "high": m["high"],
            "price": m["price"],
            "model": m["model"],
            "edge": edge,
            "bet": round(amount, 2),
            "shares": round(amount / m["price"], 2),
            "yes_token": m.get("yes_token"),
        })
    return markets, bets


def place_orders(bets):
    """place orders via clob client"""
    if DRY_RUN:
        print("[temp] DRY_RUN — not placing real orders", file=sys.stderr)
        for b in bets:
            unit = "°"
            rng = format_temp_range(b["low"], b["high"], unit)
            print(f"  buy {b['shares']:.2f} YES @ {b['price']:.4f} for ${b['bet']:.2f} on {rng}", file=sys.stderr)
        return bets

    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType

    client = ClobClient(CLOB_API_URL, key=POLYMARKET_API_KEY, chain_id=137, funder=PRIVATE_KEY)
    client.set_api_creds(client.create_or_derive_api_creds())

    for bet in bets:
        if not bet["yes_token"]:
            continue
        try:
            signed = client.create_order(OrderArgs(
                price=bet["price"], size=bet["shares"], side="BUY", token_id=bet["yes_token"],
            ))
            result = client.post_order(signed, OrderType.GTC)
            print(f"[temp] placed: {result}", file=sys.stderr)
        except Exception as e:
            print(f"[temp] order failed: {e}", file=sys.stderr)

    return bets


def save_positions(events_bets):
    """save bets to positions file"""
    positions = []
    for event_title, end_date, city, bets in events_bets:
        for b in bets:
            positions.append({
                "event": event_title,
                "end_date": end_date,
                "city": city,
                "low": b["low"],
                "high": b["high"],
                "entry_price": b["price"],
                "model_prob": b["model"],
                "edge": b["edge"],
                "shares": b["shares"],
                "bet": b["bet"],
                "yes_token": b["yes_token"],
            })
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)
    print(f"\nsaved {len(positions)} positions to {POSITIONS_FILE}", file=sys.stderr)


def scan_events(execute=False, save=False):
    """scan temperature events, detect edges, optionally trade"""
    print("fetching temperature events...", file=sys.stderr)
    events = fetch_temp_events()

    now = datetime.now(timezone.utc)
    active = []
    for e in events:
        try:
            end = datetime.fromisoformat(e.get("endDate", "").replace("Z", "+00:00"))
            if (end - now).total_seconds() > 7200:
                active.append(e)
        except (ValueError, AttributeError):
            continue

    if not active:
        print("no active temperature events found")
        return

    print(f"\nfound {len(active)} temperature events | edge threshold: {TEMP_EDGE_THRESHOLD:.0%} | budget: ${TEMP_BET_BUDGET}\n")

    all_bets = []
    for event in active:
        title = event["title"]
        city_key = detect_city(title)
        if not city_key:
            continue

        city = CITIES[city_key]
        markets = parse_event_markets(event)
        if not markets:
            continue

        try:
            end = datetime.fromisoformat(event["endDate"].replace("Z", "+00:00"))
            days_ahead = max(0.1, (end - now).total_seconds() / 86400)

            #extract target date from event end
            target_date = end.strftime("%Y-%m-%d")
            mu, sigma = temp_model.predict_distribution(city_key, target_date)
        except Exception as e:
            print(f"  skipping {city_key}: {e}", file=sys.stderr)
            continue

        markets, bets = compute_edge_bets(markets, mu, sigma, TEMP_BET_BUDGET, TEMP_EDGE_THRESHOLD)

        unit = city["unit"]
        print(f"--- {title} ({days_ahead:.1f}d ahead) ---")
        print(f"  model: mu={mu:.1f} sig={sigma:.1f} ({unit})")
        print()

        print(f"  {'range':>15s}  market  model    edge")
        for m in sorted(markets, key=lambda x: x["price"], reverse=True):
            rng = format_temp_range(m["low"], m["high"], unit)
            edge = m["model"] - m["price"]
            marker = " *" if any(
                b["low"] == m["low"] and b["high"] == m["high"] for b in bets
            ) else ""
            print(f"  {rng:>15s}  {m['price']:5.1%}  {m['model']:5.1%}  {edge:+5.1%}{marker}")

        if bets:
            print()
            print(f"  {'range':>15s}  {'price':>6s}  {'model':>6s}  {'edge':>6s}  {'bet':>7s}  shares")
            for b in bets:
                rng = format_temp_range(b["low"], b["high"], unit)
                print(f"  {rng:>15s}  {b['price']:5.1%}  {b['model']:5.1%}  {b['edge']:+5.1%}  ${b['bet']:6.2f}  {b['shares']:.1f}")

            if execute:
                place_orders(bets)
            if save:
                end_str = event.get("endDate", "")
                all_bets.append((title, end_str, city_key, bets))
        else:
            print("  no edges found")

        print()

    if save and all_bets:
        save_positions(all_bets)


def train_models(cities=None):
    """train models for specified cities (or all)"""
    targets = cities if cities else list(CITIES.keys())
    for city_key in targets:
        if city_key not in CITIES:
            print(f"unknown city: {city_key}", file=sys.stderr)
            continue
        temp_model.train_city_model(city_key)


def main():
    if "--train" in sys.argv:
        #train specific cities or all
        cities = [a for a in sys.argv[1:] if a != "--train" and not a.startswith("-")]
        train_models(cities if cities else None)
        return

    execute = "--execute" in sys.argv
    save = "--save" in sys.argv
    loop = "--loop" in sys.argv

    if loop:
        while True:
            scan_events(execute=execute, save=save)
            print("sleeping 30 min...", file=sys.stderr)
            time.sleep(1800)
    else:
        scan_events(execute=execute, save=save)


if __name__ == "__main__":
    main()
