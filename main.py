"""Pump.fun paper-trading bot: young launch sniper with a bundle filter.

Strategy, in one paragraph: every new bonding curve is watched from its
CreateEvent on. A coin is bought only while it is still young (at most 200
slots old), only once its real SOL reserves reach 3 SOL (so the harness's
1%-of-reserves size cap allows a full 0.012 SOL order), and only if at most
three distinct wallets have bought it so far and its creator has not sold
(a crowded early tape usually means a creator cluster about to dump).
The stake is a flat 0.012 SOL per coin. The position is then held for a
very short swing only: sell the whole position when its value is up 15%
on cost, down 12% on cost, or after 10 slots held. No shorts, no leverage,
no clock, no randomness, no network: every decision comes from the hello
/ batch / orders / slot stream the harness feeds us, so two runs on the
same replay agree byte for byte.

Why this shape: on the kit's dev window (24h, 1222 mints) buying every
curve and holding for a 10-20% swing lost about 1 SOL after the real
2-slot fill latency, and the kit's own momentum and reversion pilots lost
far more. A latency-aware offline replay of the same window showed the
loss concentrates in crowded, late, long-held entries: capping the buyer
count, requiring real reserves, and cutting every hold to 10 slots
brought the same replay to roughly -0.08 SOL, the best of every shape
tried, while still cycling 177 coins in 24 hours (about 44 in a 6-hour
final window, comfortably above the 20-coin guardrail).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bot  # noqa: E402

SOL = makefun_bot.LAMPORTS_PER_SOL

# --- tunables (lamports / bps / slots) -------------------------------------
STAKE_LAMPORTS = SOL * 12 // 1000      # 0.012 SOL per coin
MIN_REAL_SOL_LAMPORTS = 3 * SOL        # entry needs >= 3 SOL real reserves
MIN_BUY_LAMPORTS = SOL // 100          # 0.01 SOL: guardrail round-trip floor
MAX_AGE_SLOTS = 200                    # only young curves
MAX_BUYERS = 3                         # crowded early tape = likely bundle
TAKE_PROFIT_BPS = 1500                 # +15% on cost
STOP_LOSS_BPS = 1200                   # -12% on cost
MAX_HOLD_SLOTS = 10                    # ultra-short swing
BUY_SLIPPAGE_BPS = 10000
SELL_SLIPPAGE_BPS = 10000

# --- per-run bookkeeping (insertion-ordered dicts only; no sets of str) ---
decided = {}      # mint -> True once bought (or skipped as complete)
create_slot = {}  # mint -> slot of its CreateEvent
creator = {}      # mint -> creator pubkey
buyers = {}       # mint -> dict of buyer pubkeys seen (insertion-ordered)
dev_sold = {}     # mint -> True once the creator sold
buy_slot = {}     # mint -> slot of the buy batch


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

    # --- learn the tape: creators, buyers, creator sells -----------------
    for event in batch["events"]:
        mint = event["mint"]
        if event["event"] == "CreateEvent":
            create_slot[mint] = event["slot"]
            creator[mint] = event.get("creator")
            buyers[mint] = {}
        elif event["event"] == "TradeEvent":
            if event["is_buy"]:
                buyers.setdefault(mint, {})[event["user"]] = True
            elif event["user"] == creator.get(mint):
                dev_sold[mint] = True

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
        cost = holding.cost_lamports
        if cost <= 0:
            continue
        gain_bps = (value - cost) * 10000 // cost
        held = state.slot - buy_slot.get(mint, state.slot)
        if (
            gain_bps >= TAKE_PROFIT_BPS
            or gain_bps <= -STOP_LOSS_BPS
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
            buy_slot.pop(mint, None)

    # --- entries: one snipe per young, uncrowded, funded curve -----------
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
            if mint not in create_slot:
                continue
            if state.slot - create_slot[mint] > MAX_AGE_SLOTS:
                continue
            if dev_sold.get(mint):
                continue
            if len(buyers.get(mint, {})) > MAX_BUYERS:
                continue
            if curve.real_quote_reserves < MIN_REAL_SOL_LAMPORTS:
                continue
            cap = state.max_buy_lamports(mint)
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
            free -= amount + tx
            slots_left -= 1

    return orders


if __name__ == "__main__":
    makefun_bot.run(on_batch)
