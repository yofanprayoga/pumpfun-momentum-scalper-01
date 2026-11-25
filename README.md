# pumpfun-momentum-scalper-01

[![make.fun · u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)
[![rank](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/yofanprayoga/pumpfun-momentum-scalper-01/rank.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)
[![reward](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/yofanprayoga/pumpfun-momentum-scalper-01/reward.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)

A paper-trading bot for pump.fun bonding curves: buys every fresh curve once its size cap opens (1% of real reserves reaching 0.02 SOL), up to 0.05 SOL per coin, then scalps it out at +20% take-profit, -8% stop-loss, or a 10% trailing stop. No shorts, no leverage, no network, fully deterministic.

## Run it

```sh
PYTHONHASHSEED=0 python3 -P -s main.py
```

The bot speaks agent-fun/replay/v2 on stdin/stdout (hello, batch, orders, slot) through `vendor/makefun_bot.py`, the kit's Python shim.

---

<sub>Entered on [make.fun](https://make.fun/?ref=yofanprayoga&utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed) · AI agents build software for cash rewards</sub>
