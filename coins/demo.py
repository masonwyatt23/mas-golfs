"""Demo: one hole of Clubhouse Coins markets, end to end.

Run:  python3 -m coins.demo
(or:  python3 demo.py from this directory)

Plays hole 12 ("The Picture", par 3, 172 yd) with three viewers, a
per-shot market, a per-hole market, and a skin market with a carryover —
then prints balances, streaks, the weekly leaderboard, and the ledger
summary. All numbers are deterministic; run it twice, get the same output.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .economy import Economy

ET = ZoneInfo("America/New_York")


def main() -> None:
    # Thursday Nov 12, 2026, 2:00pm ET — mid-round, hole 12.
    now = datetime(2026, 11, 12, 14, 0, tzinfo=ET)
    econ = Economy()

    alice = econ.get_or_create_wallet("twitch:111", "twitch", "FairwayFan", now)
    bob = econ.get_or_create_wallet("twitch:222", "twitch", "BogeyBob", now)
    carol = econ.get_or_create_wallet("youtube:333", "youtube", "CactusCarol", now)
    for w in (alice, bob, carol):
        print(f"{w.display_name}: weekly {w.weekly_balance} CC "
              f"(1,000 starting bankroll + 500 day-1 allowance), "
              f"all-time {w.alltime_balance} CC")

    # --- per-shot market: "GIR on 12?" -------------------------------------
    # Base GIR from 150 yd is 0.60; form 1.05, hole 0.95 (downhill over
    # water), conditions 1.00 → p = 0.60 * 1.05 * 0.95 = 0.5985.
    m1 = econ.create_market(
        "r42-h12-gir", "per_shot", "GIR on 12?",
        {"yes": 0.60, "no": 0.40},
        form=1.05, hole=0.95, condition=1.00, round_no=42, hole_no=12,
    )
    print(f"\nMarket: {m1.question}  opening odds {m1.opening}")
    econ.place_prediction("twitch:111", "r42-h12-gir", "yes", 100, now)
    econ.place_prediction("twitch:222", "r42-h12-gir", "no", 100, now)
    econ.place_prediction("youtube:333", "r42-h12-gir", "yes", 50, now)
    print(f"Pools: {m1.pools}  displayed odds now {m1.current_odds()}")
    econ.close_market("r42-h12-gir")
    payouts = econ.resolve_market("r42-h12-gir", "yes", now)
    print(f"Mas sticks it close — GIR. Payouts: {payouts}")
    print(f"FairwayFan wins {payouts['twitch:111']} CC on a 100 CC stake "
          f"(pool 250, yes side 150 → 100 × 250/150 = 166)")

    # --- per-hole market: "Birdie or better on 12?" ------------------------
    m2 = econ.create_market(
        "r42-h12-birdie", "per_hole", "Birdie or better on 12?",
        {"yes": 0.12, "no": 0.88},
        form=1.05, hole=1.10, condition=1.00, round_no=42, hole_no=12,
    )
    print(f"\nMarket: {m2.question}  opening odds {m2.opening}")
    econ.place_prediction("twitch:111", "r42-h12-birdie", "yes", 100, now)
    econ.place_prediction("twitch:222", "r42-h12-birdie", "no", 250, now)
    econ.close_market("r42-h12-birdie")
    payouts = econ.resolve_market("r42-h12-birdie", "yes", now)
    print(f"Birdie! Payouts: {payouts}")

    # --- skin market, hole 11 carried over ----------------------------------
    econ.skin_carryover = 400  # hole 11's pot carried over
    m3 = econ.create_market(
        "r42-h12-skin", "skin", "Mas wins the skin on 12?",
        {"skin": 0.12, "no_skin": 0.88},
        round_no=42, hole_no=12,
    )
    print(f"\nSkin pot entering hole 12: {m3.carryover_in} CC carried over")
    econ.place_prediction("twitch:111", "r42-h12-skin", "skin", 100, now)
    econ.place_prediction("twitch:222", "r42-h12-skin", "no_skin", 100, now)
    econ.close_market("r42-h12-skin")
    payouts = econ.resolve_skin_market("r42-h12-skin", True, now)
    print(f"Skin won — pot (400 carryover + 200 pool) split: {payouts}")
    print(f"Carryover now: {econ.skin_carryover} CC")

    # --- watch time + a cosmetic ---------------------------------------------
    print(f"\nCactusCarol watches 70 minutes: "
          f"+{econ.record_watch('youtube:333', 70, now)} CC")
    print(f"FairwayFan buys a chat badge: "
          f"{econ.buy_cosmetic('twitch:111', 'chat_badge', now)['type']} "
          f"for 500 CC")

    print("\n--- balances ---")
    for w in (alice, bob, carol):
        print(f"{w.display_name}: weekly {w.weekly_balance} CC, "
              f"all-time {w.alltime_balance} CC, streak {w.streak_current}, "
              f"achievements {sorted(w.achievements)}")
    print("\n--- weekly leaderboard ---")
    for row in econ.weekly_leaderboard():
        print(f"  {row['display_name']}: {row['balance']} CC")
    print(f"\nBonus pool: {econ.bonus_pool} CC")
    print(f"Ledger entries: {len(econ.ledger)} "
          f"(types: {sorted({e['type'] for e in econ.ledger})})")


if __name__ == "__main__":
    main()
