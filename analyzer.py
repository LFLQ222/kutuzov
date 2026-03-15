from config import MIN_CONCENTRATION, MAX_TOP_K, MIN_PROFIT_MARGIN


def find_arbitrage(event):
    """check if top k outcomes of an event create an arbitrage opportunity.

    returns opportunity dict or None.
    """
    outcomes = event.get("outcomes", [])
    if not outcomes:
        return None

    #sort by price descending (highest probability first)
    sorted_outcomes = sorted(outcomes, key=lambda x: x["price"], reverse=True)

    best_opportunity = None

    for k in range(2, min(MAX_TOP_K + 1, len(sorted_outcomes) + 1)):
        top_k = sorted_outcomes[:k]
        price_sum = sum(o["price"] for o in top_k)
        concentration = price_sum  #this IS the concentration since prices ~ probabilities

        #need enough concentration to cover tail risk
        if concentration < MIN_CONCENTRATION:
            continue

        #arbitrage exists when sum of prices < 1
        if price_sum >= 1.0:
            continue

        profit_margin = 1.0 - price_sum
        if profit_margin < MIN_PROFIT_MARGIN:
            continue

        #compute allocations inversely proportional to price
        inv_prices = [1.0 / o["price"] for o in top_k]
        inv_sum = sum(inv_prices)
        allocations = [ip / inv_sum for ip in inv_prices]

        #verify guaranteed profit: min payout across all winning scenarios
        #if outcome i wins: payout = allocation_i / price_i
        payouts = [alloc / o["price"] for alloc, o in zip(allocations, top_k)]
        min_payout = min(payouts)

        #with normalized allocations summing to 1, min_payout should be 1/price_sum
        #profit per dollar = min_payout - 1.0
        profit_per_dollar = min_payout - 1.0

        opportunity = {
            "event_id": event.get("id"),
            "event_title": event.get("title"),
            "end_date": event.get("end_date"),
            "k": k,
            "price_sum": price_sum,
            "concentration": concentration,
            "profit_margin": profit_margin,
            "profit_per_dollar": profit_per_dollar,
            "candidates": [],
        }

        for i, outcome in enumerate(top_k):
            opportunity["candidates"].append({
                "question": outcome["question"],
                "price": outcome["price"],
                "allocation_pct": allocations[i] * 100,
                "yes_token_id": outcome.get("yes_token_id"),
                "payout_if_wins": payouts[i],
            })

        #keep the best k (highest profit margin)
        if best_opportunity is None or profit_margin > best_opportunity["profit_margin"]:
            best_opportunity = opportunity

    return best_opportunity


def compute_bet_amounts(opportunity, budget):
    """given an opportunity and budget, compute exact dollar amounts per candidate"""
    bets = []
    for candidate in opportunity["candidates"]:
        amount = budget * candidate["allocation_pct"] / 100.0
        bets.append({
            "question": candidate["question"],
            "yes_token_id": candidate["yes_token_id"],
            "price": candidate["price"],
            "amount": round(amount, 2),
            "expected_shares": round(amount / candidate["price"], 2),
        })
    return bets


def analyze_events(events):
    """analyze a list of events for arbitrage opportunities"""
    opportunities = []
    for event in events:
        opp = find_arbitrage(event)
        if opp:
            opportunities.append(opp)

    #sort by profit margin descending
    opportunities.sort(key=lambda x: x["profit_margin"], reverse=True)
    return opportunities


def format_opportunity(opp, budget=None):
    """format an opportunity as a readable string"""
    lines = [
        f"{'='*50}",
        f"event: {opp['event_title']}",
        f"end date: {opp['end_date']}",
        f"top {opp['k']} candidates (sum: {opp['price_sum']:.4f})",
        f"profit margin: {opp['profit_margin']*100:.2f}%",
        f"profit per dollar: ${opp['profit_per_dollar']:.4f}",
        "",
    ]

    for c in opp["candidates"]:
        line = f"  {c['question']}: {c['price']:.4f} ({c['allocation_pct']:.1f}%)"
        lines.append(line)

    if budget:
        lines.append(f"\nwith ${budget:.2f} budget:")
        bets = compute_bet_amounts(opp, budget)
        for b in bets:
            lines.append(f"  {b['question']}: ${b['amount']:.2f} -> {b['expected_shares']:.2f} shares")
        total_spent = sum(b["amount"] for b in bets)
        min_payout = min(b["expected_shares"] for b in bets)
        lines.append(f"  total spent: ${total_spent:.2f}")
        lines.append(f"  guaranteed payout: ${min_payout:.2f}")
        lines.append(f"  guaranteed profit: ${min_payout - total_spent:.2f}")

    lines.append(f"{'='*50}")
    return "\n".join(lines)
