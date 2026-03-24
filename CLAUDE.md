## kutuzov — polymarket btc 5-minute trading bot

buys the cheap side of btc 5-minute up/down markets as a contrarian play, takes profit or cuts losses before settlement.

### usage
```
python -m btc5m.run           # continuous loop
python -m btc5m.run --once    # single window
```

### how it works
- `btc5m/price.py` streams real-time btc price via binance websocket
- `btc5m/market.py` fetches 5m markets from gamma api by timestamp slug, places orders via clob api
- `btc5m/bot.py` state machine per window: entry (first 2 min) -> monitor -> stop-loss exit (last min)
- `btc5m/config.py` all thresholds and settings from env vars

### strategy
- buy whichever side is at 0.20-0.30 (contrarian/mean-reversion)
- take profit at 0.40+ via limit sell
- stop-loss in final minute if btc moved hard against position
- skip-until-calm filter: skip volatile windows until market calms down
- arb mode: if up + down sum < 0.95, buy both for guaranteed profit

### rules
- keep code minimal, no fix-on-fix
- DRY_RUN=true by default
- venv at `./venv/`, activate before running
- thresholds in basis points, not dollar amounts
