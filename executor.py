from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from config import POLYMARKET_API_KEY, PRIVATE_KEY, CLOB_API_URL, DRY_RUN, BET_BUDGET
from analyzer import compute_bet_amounts
from notifier import notify_execution


def execute_opportunity(opportunity, budget=None):
    """place bets on the top k outcomes of an opportunity"""
    budget = budget or BET_BUDGET
    bets = compute_bet_amounts(opportunity, budget)

    if DRY_RUN:
        print("[executor] DRY_RUN — not placing real orders")
        for b in bets:
            print(f"  buy {b['shares']:.2f} YES shares of '{b['question']}' @ {b['price']:.4f} for ${b['amount']:.2f}")
        return bets

    client = ClobClient(CLOB_API_URL, key=POLYMARKET_API_KEY, chain_id=137, funder=PRIVATE_KEY)
    client.set_api_creds(client.create_or_derive_api_creds())
    placed = []

    for bet in bets:
        if not bet["yes_token_id"]:
            print(f"[executor] skipping '{bet['question']}' — no token id")
            continue
        try:
            signed = client.create_order(OrderArgs(
                price=bet["price"], size=bet["shares"], side="BUY", token_id=bet["yes_token_id"],
            ))
            result = client.post_order(signed, OrderType.GTC)
            print(f"[executor] placed: {bet['question']} -> {result}")
            bet["order_result"] = result
            placed.append(bet)
        except Exception as e:
            print(f"[executor] failed '{bet['question']}': {e}")

    notify_execution(opportunity["event_title"], placed, sum(b["amount"] for b in placed))
    return placed
