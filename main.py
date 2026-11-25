"""Pump.fun paper-trading bot: early-cap momentum scalper.

Strategy, in one paragraph: every new bonding curve is watched from its
CreateEvent on. As soon as the curve has enough real SOL in it for a
meaningful order (the harness caps one batch's buys on a mint at 1% of its
real quote reserves, so we wait until that cap reaches 0.02 SOL), we buy
once, up to 0.05 SOL, and never re-enter that mint. The position is then
held for a quick swing only: sell the whole position when its value is up
20% on cost, down 8% on cost, down 10% from its own peak value, or after
12,000 slots held. No shorts, no leverage, no clock, no randomness, no
network: every decision comes from the hello / batch / orders / slot
stream the harness feeds us, so two runs on the same replay agree byte
for byte.

Why this shape: on the kit's dev window (24h, 1222 mints) most curves die
fast and a minority spike hard shortly after launch. Buying every curve
that reaches 2 SOL of real reserves and cutting losers at -8% while
letting winners run to +20% (with a 10% trailing stop) was profitable in
both halves of that window in an offline replay, where a momentum filter
that tried to pick only "strong" curves was not. The edge, if any, is the
asymmetric exit, not picking winners in advance.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bot  # noqa: E402

SOL = makefun_bot.LAMPORTS_PER_SOL

# --- tunables (lamports / bps / slots) -------------------------------------
STAKE_LAMPORTS = SOL // 20          # 0.05 SOL max per position
MIN_CAP_LAMPORTS = SOL // 50        # 0.02 SOL: smallest buy worth sending
MIN_BUY_LAMPORTS = SOL // 100       # 0.01 SOL: guardrail round-trip floor
TAKE_PROFIT_BPS = 2000              # +20% on cost
STOP_LOSS_BPS = 800                 # -8% on cost
TRAIL_BPS = 1000                    # -10% from peak value
MAX_HOLD_SLOTS = 12000
BUY_SLIPPAGE_BPS = 500
SELL_SLIPPAGE_BPS = 10000

# --- per-run bookkeeping (insertion-ordered dicts only; no sets of str) ---
decided = {}   # mint -> True once bought (or skipped as complete)
peak_value = {}  # mint -> best position value in lamports seen so far
buy_slot = {}  # mint -> slot of the buy batch


def curve_price_lamports(curve):
    """Lamports per token unit from virtual reserves, or None."""
    vt = curve.virtual_token_reserves
    if vt <= 0:
        return None
    return curve.virtual_quote_reserves / vt


def position_value_lamports(state, mint, holding):
    curve = state.curves.get(mint)
    if curve is None:
        return None
    price = curve_price_lamports(curve)
    if price is None:
        return None
    return int(holding.token_amount * price)


def on_batch(state, batch):
    orders = []
    caps = state.hello["caps"]
    max_orders = caps["max_orders_per_batch"]
    tx = state.tx_fee_lamports()
    free = state.free_cash_lamports()

    # --- exits first: one sell per held position that trips a rule -------
    # A sell already in flight (pending) must not be sent again: the next
    # batch's account may still show the position until its fill lands.
    pending_sells = {
        p.order["mint"] for p in state.pending.values() if p.order["side"] == "sell"
    }
    for mint in list(state.positions.keys()):
        if mint in pending_sells:
            continue
        holding = state.positions[mint]
        value = position_value_lamports(state, mint, holding)
        if value is None:
            continue
        if value > peak_value.get(mint, 0):
            peak_value[mint] = value
        cost = holding.cost_lamports
        if cost <= 0:
            continue
        gain_bps = (value - cost) * 10000 // cost
        trail_bps = (value - peak_value[mint]) * 10000 // peak_value[mint]
        held = state.slot - buy_slot.get(mint, state.slot)
        if (
            gain_bps >= TAKE_PROFIT_BPS
            or gain_bps <= -STOP_LOSS_BPS
            or trail_bps <= -TRAIL_BPS
            or held > MAX_HOLD_SLOTS
        ):
            if len(orders) >= max_orders:
                continue
            orders.append(
                {
                    "side": "sell",
                    "mint": mint,
                    "token_amount": holding.token_amount,
                    "max_slippage_bps": SELL_SLIPPAGE_BPS,
                }
            )
            free -= tx
            peak_value.pop(mint, None)
            buy_slot.pop(mint, None)

    # --- entries: one buy per fresh curve whose size cap just opened -----
    slots_left = caps["max_open_positions"] - state.committed_position_count()
    if slots_left > 0:
        for event in batch["events"]:
            if len(orders) >= max_orders or slots_left <= 0:
                break
            mint = event["mint"]
            if mint in decided or mint in state.positions:
                continue
            curve = state.curves.get(mint)
            if curve is None or curve.complete:
                decided[mint] = True
                continue
            cap = state.max_buy_lamports(mint)
            if cap < MIN_CAP_LAMPORTS:
                continue
            amount = STAKE_LAMPORTS if STAKE_LAMPORTS < cap else cap
            if amount < MIN_BUY_LAMPORTS or free < amount + tx:
                continue
            orders.append(
                {
                    "side": "buy",
                    "mint": mint,
                    "quote_lamports": amount,
                    "max_slippage_bps": BUY_SLIPPAGE_BPS,
                }
            )
            decided[mint] = True
            buy_slot[mint] = state.slot
            peak_value[mint] = amount
            free -= amount + tx
            slots_left -= 1

    return orders


if __name__ == "__main__":
    makefun_bot.run(on_batch)
