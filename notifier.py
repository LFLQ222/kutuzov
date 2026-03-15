import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(message):
    """send a message via telegram bot api"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[notifier] telegram not configured, skipping")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[notifier] telegram send failed: {e}")
        return False


def notify_opportunity(opp, budget=None):
    """send a formatted opportunity alert"""
    lines = [
        f"*arb opportunity found*",
        f"event: {opp['event_title']}",
        f"margin: {opp['profit_margin']*100:.2f}%",
        f"top {opp['k']} prices sum: {opp['price_sum']:.4f}",
        "",
    ]

    for c in opp["candidates"]:
        lines.append(f"- {c['question']}: {c['price']:.4f} ({c['allocation_pct']:.1f}%)")

    if budget:
        lines.append(f"\nbudget: ${budget:.2f}")
        profit = budget * opp["profit_per_dollar"]
        lines.append(f"expected profit: ${profit:.2f}")

    return send_telegram("\n".join(lines))


def notify_execution(event_title, bets, total_spent):
    """send alert after placing bets"""
    lines = [
        f"*bets placed*",
        f"event: {event_title}",
        f"total spent: ${total_spent:.2f}",
        "",
    ]
    for b in bets:
        lines.append(f"- {b['question']}: ${b['amount']:.2f} @ {b['price']:.4f}")

    return send_telegram("\n".join(lines))


def notify_price_shift(event_title, candidate, old_price, new_price):
    """alert on significant price change"""
    change_pct = (new_price - old_price) / old_price * 100
    msg = (
        f"*price shift*\n"
        f"event: {event_title}\n"
        f"{candidate}: {old_price:.4f} -> {new_price:.4f} ({change_pct:+.1f}%)"
    )
    return send_telegram(msg)


def notify_resolution(event_title, pnl):
    """alert when position resolves"""
    emoji = "profit" if pnl >= 0 else "loss"
    msg = f"*position resolved* ({emoji})\nevent: {event_title}\nP&L: ${pnl:+.2f}"
    return send_telegram(msg)
