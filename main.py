import argparse
from apscheduler.schedulers.blocking import BlockingScheduler
from discovery import discover
from analyzer import analyze_events, format_opportunity
from executor import execute_opportunity
from monitor import check_positions
from notifier import notify_opportunity
from config import BET_BUDGET, MIN_PROFIT_MARGIN


def scan():
    """one-shot scan for arbitrage opportunities"""
    events = discover()
    if not events:
        print("no multi-outcome events found")
        return []

    opportunities = analyze_events(events)
    if not opportunities:
        print("no arbitrage opportunities found")
        return []

    print(f"\nfound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(format_opportunity(opp, budget=BET_BUDGET))
        print()

    return opportunities


def scan_and_notify():
    """scan and send telegram alerts for qualifying opportunities"""
    print("running scheduled scan...")
    events = discover()
    if not events:
        return

    opportunities = analyze_events(events)
    for opp in opportunities:
        if opp["profit_margin"] >= MIN_PROFIT_MARGIN:
            print(format_opportunity(opp, budget=BET_BUDGET))
            notify_opportunity(opp, budget=BET_BUDGET)

    check_positions()


def execute(event_id):
    """manually execute on a specific event"""
    events = discover()
    opportunities = analyze_events(events)

    target = None
    for opp in opportunities:
        if str(opp["event_id"]) == str(event_id):
            target = opp
            break

    if not target:
        print(f"no arbitrage opportunity found for event {event_id}")
        return

    print(format_opportunity(target, budget=BET_BUDGET))
    print(f"\nexecuting with ${BET_BUDGET:.2f} budget...")
    execute_opportunity(target, budget=BET_BUDGET)


def main():
    parser = argparse.ArgumentParser(description="polymarket multi-outcome arbitrage bot")
    parser.add_argument("--scan", action="store_true", help="one-shot scan")
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
        #continuous scanner mode
        print("starting continuous scanner (every 30 min)...")
        print("press ctrl+c to stop\n")

        #run once immediately
        scan_and_notify()

        scheduler = BlockingScheduler()
        scheduler.add_job(scan_and_notify, "interval", minutes=30)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("\nshutting down")


if __name__ == "__main__":
    main()
