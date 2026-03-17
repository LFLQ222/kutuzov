import json
import sys
import re
import math
import requests
import numpy as np
import yfinance as yf
from scipy.stats import norm
from datetime import datetime, timezone
from config import GAMMA_API_URL, BET_BUDGET


def fetch_btc_events():
    """find all open 'Bitcoin price on' daily events"""
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
            if "bitcoin price on" in e.get("title", "").lower():
                events.append(e)
        if len(batch) < 100:
            break
        offset += 100
    return sorted(events, key=lambda e: e.get("endDate", ""))


def parse_range(question):
    """extract (low, high) from market question"""
    q = question.lower().replace(",", "")
    m = re.search(r"between \$(\d+) and \$(\d+)", q)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"greater than \$(\d+)", q)
    if m:
        return int(m.group(1)), int(m.group(1)) + 100000
    m = re.search(r"less than \$(\d+)", q)
    if m:
        return 0, int(m.group(1))
    return None


def parse_event_markets(event):
    """extract active ranges with prices and token ids"""
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
        r = parse_range(m.get("question", ""))
        if not r:
            continue

        token_id = None
        tids = m.get("clobTokenIds")
        if tids:
            try:
                ids = json.loads(tids) if isinstance(tids, str) else tids
                token_id = ids[0] if ids else None
            except (json.JSONDecodeError, IndexError):
                pass

        markets.append({
            "question": m["question"],
            "low": r[0],
            "high": r[1],
            "price": price,
            "yes_token_id": token_id,
        })

    markets.sort(key=lambda x: x["low"])
    return markets


def get_btc_volatility(lookback_days=90):
    """daily log-return mean and std from recent BTC history"""
    btc = yf.download("BTC-USD", period=f"{lookback_days}d", interval="1d", progress=False)
    closes = btc["Close"].values.flatten()
    log_returns = np.diff(np.log(closes))
    return closes[-1], np.mean(log_returns), np.std(log_returns)


def model_probabilities(current_price, mu, sigma, markets, days_ahead):
    """model probability for each range using log-normal distribution"""
    log_price = math.log(current_price)
    drift = mu * days_ahead
    vol = sigma * math.sqrt(days_ahead)

    for m in markets:
        low, high = m["low"], m["high"]
        if low == 0:
            m["model_prob"] = norm.cdf((math.log(high) - log_price - drift) / vol)
        elif high >= 100000:
            m["model_prob"] = 1.0 - norm.cdf((math.log(low) - log_price - drift) / vol)
        else:
            z_lo = (math.log(low) - log_price - drift) / vol
            z_hi = (math.log(high) - log_price - drift) / vol
            m["model_prob"] = norm.cdf(z_hi) - norm.cdf(z_lo)

    return markets


def format_range(m):
    """human readable range label"""
    if m["low"] == 0:
        return f"<${m['high']:,}"
    if m["high"] >= 100000:
        return f">${m['low']:,}"
    return f"${m['low']:,}-${m['high']:,}"


def compute_bets(markets, budget):
    """pick ranges to bet on and allocate budget.

    strategy:
    1. if top-k ranges have pure arb (sum < 1), bet proportional to price
    2. otherwise bet on ranges where model_prob > market_price, sized by edge
    """
    by_price = sorted(markets, key=lambda x: x["price"], reverse=True)

    #check for pure arb
    for k in range(2, min(5, len(by_price) + 1)):
        top_k = by_price[:k]
        price_sum = sum(m["price"] for m in top_k)
        if price_sum < 1.0:
            payout = budget / price_sum
            bets = []
            for m in top_k:
                amount = budget * m["price"] / price_sum
                bets.append({
                    "range": format_range(m),
                    "price": m["price"],
                    "bet": round(amount, 2),
                    "shares": round(amount / m["price"], 2),
                    "yes_token_id": m["yes_token_id"],
                })
            return {
                "strategy": "arbitrage",
                "note": f"top {k} ranges sum to {price_sum:.4f} — guaranteed payout if BTC lands in any",
                "price_sum": round(price_sum, 4),
                "guaranteed_payout": round(payout, 2),
                "guaranteed_profit": round(payout - budget, 2),
                "tail_risk": round(1.0 - sum(m["model_prob"] for m in top_k), 4),
                "bets": bets,
            }

    #no arb — bet on underpriced ranges weighted by edge
    edges = [{"m": m, "edge": m["model_prob"] - m["price"]} for m in markets if m["model_prob"] > m["price"] + 0.02]
    if not edges:
        edges = sorted([{"m": m, "edge": m["model_prob"] - m["price"]} for m in markets], key=lambda x: x["edge"], reverse=True)[:2]

    total_edge = sum(e["edge"] for e in edges)
    bets = []
    for e in edges:
        m = e["m"]
        amount = budget * e["edge"] / total_edge if total_edge > 0 else budget / len(edges)
        bets.append({
            "range": format_range(m),
            "price": m["price"],
            "model_prob": round(m["model_prob"], 4),
            "edge": round(e["edge"], 4),
            "bet": round(amount, 2),
            "shares": round(amount / m["price"], 2),
            "payout_if_wins": round(amount / m["price"], 2),
            "yes_token_id": m["yes_token_id"],
        })

    return {
        "strategy": "edge",
        "note": "no pure arb — betting on ranges underpriced vs volatility model",
        "bets": bets,
    }


def analyze_event(event, current_price, mu, sigma, budget):
    """full analysis for one btc daily event"""
    markets = parse_event_markets(event)
    if not markets:
        return None

    end_str = event.get("endDate", "")
    try:
        end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        days_ahead = max(0.5, (end_date - datetime.now(timezone.utc)).total_seconds() / 86400)
    except (ValueError, AttributeError):
        days_ahead = 1

    markets = model_probabilities(current_price, mu, sigma, markets, days_ahead)
    bets = compute_bets(markets, budget)

    return {
        "event_id": event.get("id"),
        "title": event.get("title"),
        "end_date": end_str,
        "btc_price": round(current_price, 0),
        "days_ahead": round(days_ahead, 1),
        "daily_vol": round(sigma, 4),
        "budget": budget,
        **bets,
        "all_ranges": [
            {
                "range": format_range(m),
                "market": round(m["price"], 4),
                "model": round(m["model_prob"], 4),
                "edge": round(m["model_prob"] - m["price"], 4),
            }
            for m in sorted(markets, key=lambda x: x["price"], reverse=True)
        ],
    }


def main():
    print("fetching btc volatility...", file=sys.stderr)
    current_price, mu, sigma = get_btc_volatility()
    print(f"BTC: ${current_price:,.0f}, vol: {sigma:.4f}", file=sys.stderr)

    print("fetching btc daily events...", file=sys.stderr)
    events = fetch_btc_events()
    print(f"found {len(events)} events", file=sys.stderr)

    results = []
    for event in events:
        analysis = analyze_event(event, current_price, mu, sigma, BET_BUDGET)
        if analysis:
            results.append(analysis)

    with open("btc_ranges.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"wrote {len(results)} events to btc_ranges.json")


if __name__ == "__main__":
    main()
