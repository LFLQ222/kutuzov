import requests
from datetime import datetime, timedelta, timezone
from config import GAMMA_API_URL, MAX_EVENT_DAYS


def fetch_events():
    """fetch open events from gamma api with pagination"""
    all_events = []
    offset = 0
    limit = 100

    while True:
        resp = requests.get(
            f"{GAMMA_API_URL}/events",
            params={"closed": "false", "limit": limit, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_events.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return all_events


def filter_multi_outcome_events(events):
    """keep events with >3 outcomes and end_date within MAX_EVENT_DAYS"""
    cutoff = datetime.now(timezone.utc) + timedelta(days=MAX_EVENT_DAYS)
    filtered = []

    for event in events:
        markets = event.get("markets", [])
        if len(markets) <= 3:
            continue

        end_date_str = event.get("endDate") or event.get("end_date")
        if not end_date_str:
            continue

        try:
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        if end_date > cutoff:
            continue

        filtered.append(event)

    return filtered


def get_market_prices(event):
    """extract outcome names and prices from an event's markets"""
    outcomes = []
    for market in event.get("markets", []):
        outcome = {
            "question": market.get("question", ""),
            "condition_id": market.get("conditionId", ""),
            "token_id": market.get("clobTokenIds"),
            "price": None,
            "outcome": market.get("outcome", ""),
        }

        #price from outcomePrices or bestAsk
        prices_str = market.get("outcomePrices")
        if prices_str:
            try:
                #outcomePrices is typically a JSON string like "[\"0.5\", \"0.5\"]"
                import json
                prices = json.loads(prices_str)
                #first price is YES price
                outcome["price"] = float(prices[0])
            except (json.JSONDecodeError, IndexError, TypeError):
                pass

        if outcome["price"] is None:
            best_ask = market.get("bestAsk")
            if best_ask:
                outcome["price"] = float(best_ask)

        #get YES token id (first token in the pair)
        token_ids = market.get("clobTokenIds")
        if token_ids:
            try:
                import json
                ids = json.loads(token_ids) if isinstance(token_ids, str) else token_ids
                outcome["yes_token_id"] = ids[0] if ids else None
            except (json.JSONDecodeError, IndexError, TypeError):
                outcome["yes_token_id"] = None

        if outcome["price"] is not None:
            outcomes.append(outcome)

    return outcomes


def discover():
    """main discovery pipeline: fetch, filter, extract prices"""
    print("fetching events from gamma api...")
    events = fetch_events()
    print(f"found {len(events)} open events")

    multi = filter_multi_outcome_events(events)
    print(f"found {len(multi)} multi-outcome events within {MAX_EVENT_DAYS} days")

    results = []
    for event in multi:
        outcomes = get_market_prices(event)
        if len(outcomes) > 3:
            results.append({
                "id": event.get("id"),
                "title": event.get("title", ""),
                "slug": event.get("slug", ""),
                "end_date": event.get("endDate") or event.get("end_date"),
                "outcomes": outcomes,
            })

    print(f"found {len(results)} events with valid multi-outcome pricing")
    return results
