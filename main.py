import argparse
import json
import sys
import io

#fix unicode output on windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from apscheduler.schedulers.blocking import BlockingScheduler
from discovery import discover
from analyzer import analyze_events, compute_bet_amounts
from executor import execute_opportunity
from monitor import check_positions
from notifier import notify_opportunity
from config import BET_BUDGET, MIN_PROFIT_MARGIN


def to_json(opportunities, budget):
    """convert opportunities to json-serializable list"""
    results = []
    for opp in opportunities:
        payout = budget / opp["price_sum"]
        results.append({
            "event_id": opp["event_id"],
            "event_title": opp["event_title"],
            "end_date": opp["end_date"],
            "k": opp["k"],
            "price_sum": round(opp["price_sum"], 4),
            "profit_margin_pct": round(opp["profit_margin"] * 100, 2),
            "guaranteed_payout": round(payout, 2),
            "guaranteed_profit": round(payout - budget, 2),
            "candidates": [
                {"question": c["question"], "price": c["price"], "allocation_pct": round(c["allocation_pct"], 1)}
                for c in opp["candidates"]
            ],
        })
    return results


def scan():
    events = discover()
    opportunities = analyze_events(events) if events else []
    print(json.dumps(to_json(opportunities, BET_BUDGET), indent=2, ensure_ascii=False))
    return opportunities


def scan_and_notify():
    print("running scheduled scan...", file=sys.stderr)
    events = discover()
    if not events:
        return
    for opp in analyze_events(events):
        if opp["profit_margin"] >= MIN_PROFIT_MARGIN:
            notify_opportunity(opp, budget=BET_BUDGET)
    check_positions()


def execute(event_id):
    events = discover()
    opportunities = analyze_events(events)
    target = next((o for o in opportunities if str(o["event_id"]) == str(event_id)), None)
    if not target:
        print(f"no opportunity found for event {event_id}", file=sys.stderr)
        return
    print(json.dumps(to_json([target], BET_BUDGET)[0], indent=2, ensure_ascii=False))
    execute_opportunity(target, budget=BET_BUDGET)


def main():
    parser = argparse.ArgumentParser(description="polymarket multi-outcome arbitrage bot")
    parser.add_argument("--scan", action="store_true", help="one-shot scan, output json")
    parser.add_argument("--execute", type=str, metavar="EVENT_ID", help="execute on event")
    parser.add_argument("--monitor", action="store_true", help="check open positions")
    args = parser.parse_args()

    if args.scan:
        scan()
    elif args.execute:
        execute(args.execute)
    elif args.monitor:
        check_positions()
    else:
        print("starting continuous scanner (every 30 min)...", file=sys.stderr)
        scan_and_notify()
        scheduler = BlockingScheduler()
        scheduler.add_job(scan_and_notify, "interval", minutes=30)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("\nshutting down", file=sys.stderr)


if __name__ == "__main__":
    main()
