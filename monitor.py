import json
import os
from datetime import datetime, timezone
from discovery import parse_event_outcomes, fetch_events
from notifier import notify_price_shift, notify_resolution

POSITIONS_FILE = "positions.json"
PRICE_SHIFT_THRESHOLD = 0.05


def load_positions():
    if not os.path.exists(POSITIONS_FILE):
        return []
    with open(POSITIONS_FILE, "r") as f:
        return json.load(f)


def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


def add_position(opportunity, bets):
    """record a new position after execution"""
    positions = load_positions()
    positions.append({
        "event_id": opportunity["event_id"],
        "event_title": opportunity["event_title"],
        "end_date": opportunity["end_date"],
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "total_spent": sum(b["amount"] for b in bets),
        "candidates": [
            {
                "question": b["question"],
                "yes_token_id": b["yes_token_id"],
                "entry_price": b["price"],
                "current_price": b["price"],
                "amount_spent": b["amount"],
                "shares": b["shares"],
            }
            for b in bets
        ],
    })
    save_positions(positions)


def check_positions():
    """check open positions for price changes"""
    positions = load_positions()
    if not positions:
        print("[monitor] no open positions")
        return

    events = fetch_events()
    events_by_id = {str(e.get("id")): e for e in events}
    updated = []

    for pos in positions:
        event = events_by_id.get(str(pos["event_id"]))
        if event is None:
            notify_resolution(pos["event_title"], 0)
            continue

        outcomes = parse_event_outcomes(event)
        price_map = {o.get("yes_token_id"): o["price"] for o in outcomes}

        for c in pos["candidates"]:
            new_price = price_map.get(c.get("yes_token_id"))
            if new_price and c["current_price"] > 0:
                change = abs(new_price - c["current_price"]) / c["current_price"]
                if change >= PRICE_SHIFT_THRESHOLD:
                    notify_price_shift(pos["event_title"], c["question"], c["current_price"], new_price)
                c["current_price"] = new_price

        updated.append(pos)

    save_positions(updated)
    print(f"[monitor] checked {len(updated)} positions")
