import json
import sys
import requests
from datetime import datetime, timedelta, timezone
from config import GAMMA_API_URL, MAX_EVENT_DAYS


def fetch_events():
    """fetch all open events from gamma api"""
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


def parse_event_outcomes(event):
    """extract active outcome names, prices, and token ids from an event"""
    outcomes = []
    for market in event.get("markets", []):
        if not market.get("active", False):
            continue

        price = None
        prices_str = market.get("outcomePrices")
        if prices_str:
            try:
                price = float(json.loads(prices_str)[0])
            except (json.JSONDecodeError, IndexError, TypeError, ValueError):
                pass
        if price is None:
            continue

        token_id = None
        token_ids = market.get("clobTokenIds")
        if token_ids:
            try:
                ids = json.loads(token_ids) if isinstance(token_ids, str) else token_ids
                token_id = ids[0] if ids else None
            except (json.JSONDecodeError, IndexError, TypeError):
                pass

        outcomes.append({
            "question": market.get("question", ""),
            "price": price,
            "yes_token_id": token_id,
        })

    return outcomes


def discover():
    """find multi-outcome events ending within MAX_EVENT_DAYS with valid pricing"""
    print("fetching events from gamma api...", file=sys.stderr)
    events = fetch_events()
    print(f"found {len(events)} open events", file=sys.stderr)

    cutoff = datetime.now(timezone.utc) + timedelta(days=MAX_EVENT_DAYS)
    results = []

    for event in events:
        #filter by end date
        end_str = event.get("endDate") or event.get("end_date")
        if not end_str:
            continue
        try:
            end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if end_date > cutoff:
            continue

        #filter by active outcome count
        outcomes = parse_event_outcomes(event)
        if len(outcomes) <= 3:
            continue

        results.append({
            "id": event.get("id"),
            "title": event.get("title", ""),
            "end_date": end_str,
            "outcomes": outcomes,
        })

    print(f"found {len(results)} multi-outcome events", file=sys.stderr)
    return results
