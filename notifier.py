import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(message):
    """send a message via telegram bot api"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[notifier] telegram not configured, skipping")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[notifier] telegram failed: {e}")
        return False


def notify_opportunity(opp, budget=None):
    """send a formatted opportunity alert"""
    lines = [
        f"*arb opportunity*",
        f"event: {opp['event_title']}",
        f"margin: {opp['profit_margin']*100:.2f}%",
        f"top {opp['k']} sum: {opp['price_sum']:.4f}",
        "",
    ]
    for c in opp["candidates"]:
        lines.append(f"- {c['question']}: {c['price']:.4f} ({c['allocation_pct']:.1f}%)")
    if budget:
        profit = budget * (1.0 / opp["price_sum"] - 1.0)
        lines.append(f"\nbudget: ${budget:.2f}, profit: ${profit:.2f}")
    return send_telegram("\n".join(lines))


def notify_execution(event_title, bets, total_spent):
    lines = [f"*bets placed*", f"event: {event_title}", f"total: ${total_spent:.2f}", ""]
    for b in bets:
        lines.append(f"- {b['question']}: ${b['amount']:.2f} @ {b['price']:.4f}")
    return send_telegram("\n".join(lines))


def notify_price_shift(event_title, candidate, old_price, new_price):
    change = (new_price - old_price) / old_price * 100
    return send_telegram(
        f"*price shift*\n{event_title}\n{candidate}: {old_price:.4f} -> {new_price:.4f} ({change:+.1f}%)"
    )


def notify_resolution(event_title, pnl):
    return send_telegram(f"*resolved*\n{event_title}\nP&L: ${pnl:+.2f}")
