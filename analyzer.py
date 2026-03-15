from config import MIN_CONCENTRATION, MAX_TOP_K, MIN_PROFIT_MARGIN


def find_arbitrage(event):
    """find the best top-k arbitrage for an event.

    allocate proportional to price so every outcome pays the same:
      S_i = budget * p_i / sum(p_j)
      payout if i wins = S_i / p_i = budget / sum(p_j)
      profitable when sum(p_j) < 1
    """
    outcomes = [o for o in event.get("outcomes", []) if o["price"] > 0]
    if len(outcomes) < 2:
        return None

    outcomes.sort(key=lambda x: x["price"], reverse=True)
    best = None

    for k in range(2, min(MAX_TOP_K + 1, len(outcomes) + 1)):
        top_k = outcomes[:k]
        price_sum = sum(o["price"] for o in top_k)

        if price_sum < MIN_CONCENTRATION or price_sum >= 1.0:
            continue

        margin = 1.0 - price_sum
        if margin < MIN_PROFIT_MARGIN:
            continue

        candidate = {
            "event_id": event.get("id"),
            "event_title": event.get("title"),
            "end_date": event.get("end_date"),
            "k": k,
            "price_sum": price_sum,
            "profit_margin": margin,
            "candidates": [
                {
                    "question": o["question"],
                    "price": o["price"],
                    "allocation_pct": o["price"] / price_sum * 100,
                    "yes_token_id": o.get("yes_token_id"),
                }
                for o in top_k
            ],
        }

        if best is None or margin > best["profit_margin"]:
            best = candidate

    return best


def compute_bet_amounts(opportunity, budget):
    """compute dollar amounts per candidate from allocation percentages"""
    bets = []
    for c in opportunity["candidates"]:
        amount = budget * c["allocation_pct"] / 100.0
        bets.append({
            "question": c["question"],
            "yes_token_id": c["yes_token_id"],
            "price": c["price"],
            "amount": round(amount, 2),
            "shares": round(amount / c["price"], 2),
        })
    return bets


def analyze_events(events):
    """analyze all events, return arbitrage opportunities sorted by margin"""
    opportunities = []
    for event in events:
        opp = find_arbitrage(event)
        if opp:
            opportunities.append(opp)
    opportunities.sort(key=lambda x: x["profit_margin"], reverse=True)
    return opportunities
