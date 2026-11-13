# Clubhouse Coins — the Mas Golfs prediction economy

Free play money. Earned by watching and predicting. Never purchasable,
never convertible to anything of value, never transferable, never cashable
out. Status, leaderboard rank, and cosmetic perks only.

Implements [docs/coins-economy.md](../docs/coins-economy.md) — the whole
spec. Stdlib-only Python, no dependencies. Run the tests with:

```
python3 -m unittest discover -s coins/tests
```

Run the demo (one hole, three viewers, deterministic) with:

```
python3 -m coins.demo
```

## The legal boundary (read first)

The closed loop is structural, not just policy (spec §12):

- **No transfer function exists.** No method, API, or command moves coins
  between viewers. Coins cannot move between wallets, period.
- **No purchase path.** No store, no price, no payment flow. Coins enter
  only through the documented faucets: starting bankroll, daily allowance,
  watch time, prediction winnings, streak bonuses, achievements.
- **No withdrawal, redemption, or cash-out path.** No cash, gift cards,
  crypto, or merchandise redemption. Cosmetics are status only,
  time-limited (7 days), and non-transferable.
- **No marketplace** for coins, cosmetics, or accounts.
- Any change to these rules requires a written review from counsel first.
  The "eventually crypto" idea stays off the roadmap until counsel
  reviews it. This is the single biggest legal risk in the project.

A test (`TestLegalBoundary`) asserts the forbidden methods do not exist.

## API

```python
from coins import Economy
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
econ = Economy()
now = datetime(2026, 11, 12, 14, 0, tzinfo=ET)

# Wallets — one per platform identity; 1,000 CC starting bankroll.
wallet = econ.get_or_create_wallet("twitch:12345678", "twitch",
                                   "FairwayFan", now)

# Earning — 500 CC/day allowance (no stacking), 10 CC per 10 min watched,
# capped at 360 CC/day. Both credit the weekly balance only.
econ.record_watch("twitch:12345678", 70, now)   # +70 CC

# Markets — base probabilities from Mas's rolling stats, adjusted by
# form (0.85–1.15), hole (0.70–1.30), conditions (0.80–1.20).
market = econ.create_market(
    "r42-h12-gir", "per_shot", "GIR on 12?",
    {"yes": 0.60, "no": 0.40},
    form=1.05, hole=0.95, condition=1.00, round_no=42, hole_no=12)
market.opening          # {'yes': 1.67, 'no': 2.5} — decimal odds, no overround
market.current_odds()   # 50/50 model/pool blend, capped at ±25% from open

# Predictions — stake caps: per-shot 10–100, per-hole 10–250,
# round-level 25–500 CC. One position per market; locked at close.
econ.place_prediction("twitch:12345678", "r42-h12-gir", "yes", 100, now)
econ.close_market("r42-h12-gir")
payouts = econ.resolve_market("r42-h12-gir", "yes", now)

# Skins — un-won pots carry to the next hole; a win splits pot + carryover.
econ.resolve_skin_market("r42-h12-skin", skin_won=True, now)

# Voids — full refund, streaks untouched.
econ.void_market("r42-h12-gir", now)

# Cosmetics — weekly coins only, 7 days, never an advantage.
econ.buy_cosmetic("twitch:12345678", "chat_badge", now)  # 500 CC

# Leaderboards — weekly (Monday 00:00 ET reset), all-time (never),
# daily (net winnings today), biggest wins.
econ.weekly_leaderboard()
econ.alltime_leaderboard()
econ.daily_leaderboard(now)
econ.biggest_wins()
```

The market lifecycle (§5.5) is `announce → open → close → resolve →
settle`, driven by sim events on the bus: `decision` announces,
`shot_start` closes, `landing` / `putt_result` / `hole_end` /
`round_end` resolves. `Economy.create_market` opens the market
immediately (announce + open are one step in this service); the caller
closes it on the sim's close trigger.

The economy is storage-agnostic: wallets, markets, and the append-only
ledger live in memory. The free-tier stack (spec §10.4) persists the
ledger in SQLite and the live pools in memory/Redis — the same rules,
a different store.

## Worked example — the parimutuel payout (§6.1)

Market: "Birdie or better on 12?" Pools: **Yes 1,200 CC / No 800 CC**.
Mas birdies. Total pool: 2,000 CC.

A viewer who staked **100 CC on Yes** gets:

```
100 × (2,000 / 1,200) = 166.67 → 166 CC back (rounded down, §6.7)
```

That's **+66 profit** at effective odds of **1.67**. The 8 CC of dust
(2,000 − 12 × 166) accrues to the bonus pool.

The other side of the same pool: a 100 CC stake on No would have
returned 100 × (2,000 / 800) = **250 CC** at effective odds of **2.50**
— that is the spec §6.1 example (Yes 800 / No 1,200, outcome Yes).

Displayed odds at stake time are a 50/50 blend of the model price and
the pool price, capped at ±25% from the opening odds (§5.4); the final
payout depends on where the money lands, and the screen must say so:
"Payouts are split from the pool — final odds depend on where the money
lands."

## What the engine implements (spec section → module)

| Feature | Spec | Where |
|---|---|---|
| Two balances, Monday 00:00 ET weekly reset | §2.1, §7.1 | `wallet.py`, `economy.py` |
| Starting bankroll 1,000 CC | §3.1 | `wallet.py` |
| Daily allowance 500 CC, no stacking | §3.2 | `wallet.py` |
| Watch time 10 CC / 10 min, 360 CC/day cap | §3.3 | `wallet.py` |
| Stake caps 10–100 / 10–250 / 25–500 | §4.1 | `market.py` |
| One position per market, no edits after close | §4.2–4.3 | `market.py`, `economy.py` |
| Decimal odds, no overround | §5.1 | `odds.py` |
| Base probabilities from rolling stats | §5.2 | `odds.py` (`BASE_*_RATES`) |
| Form / hole / condition adjustments | §5.3 | `odds.py` |
| 50/50 volume blend, ±25% movement cap | §5.4 | `odds.py` |
| Market lifecycle announce→settle | §5.5 | `market.py`, `economy.py` |
| Parimutuel payouts, no house cut, floor rounding | §6.1–6.2, §6.7 | `market.py` |
| Skins with carryover | §6.3 | `market.py`, `economy.py` |
| Nassau +25% sweep bonus | §6.4 | `economy.py` |
| Road to 59 season markets | §6.5 | `economy.py` (type `season`) |
| Bonus pool 10,000 CC/week, Monday refill | §6.6 | `economy.py` |
| Voided markets refund in full | §6.8 | `economy.py` |
| Weekly / all-time / daily / biggest-wins boards | §7 | `economy.py` |
| Streak bonuses +10/+25/+50/+100% of profit | §8.1 | `economy.py` |
| 11 achievements, one-time grants | §8.2 | `economy.py` |
| Cosmetics only, 7 days, weekly coins | §8.3 | `wallet.py`, `economy.py` |
| One wallet per platform identity | §9.1 | `economy.py` |
| 60 predictions/hour rate limit | §9.2 | `economy.py` |
| No transfers, no secondary market | §9.3, §12 | structural — see top |
| Append-only ledger, every transaction | §9.4, §10.2 | `economy.py` |

## Judgement calls (where the spec left a gap)

- **Streak bonus timing.** §8.1's table is headed "Bonus on next win":
  the bonus applies to *every* win while the streak is at or above a
  tier, at the highest tier reached (3 → +10%, 5 → +25%, 8 → +50%,
  12+ → +100% of that win's *profit*). A 5-win streak therefore pays
  +10% on wins 3 and 4 and +25% on win 5.
- **Skins "no skin" side.** When a skin is not won, the whole pool
  carries (§6.3) — so a correct "no skin" call pays nothing and its
  stake feeds the pot. Its streak neither extends nor breaks (status
  `pushed`): the prediction was right, it just didn't pay. A wrong
  "skin" call breaks the streak as usual.
- **Nobody on the winning side.** The whole pool is dust and accrues to
  the bonus pool — there is nobody to pay.
- **Bonus pool shortfall.** If the pool holds less than a bonus, the
  bonus pays what remains; if empty, bonuses pause until the Monday
  refill (§10.5). Stakes and payouts are never affected.
- **Daily leaderboard.** Ranked by net winnings that day (payouts +
  bonuses − stakes), per §7.3; achievement grants are not winnings.
- **Weekly winner tie-break.** Earlier to reach the balance wins (§7.1):
  the engine tracks each wallet's weekly high and the first time it was
  reached.
- **Monday rollover.** Triggered lazily on the first touch after Monday
  00:00 ET (no background job needed); the weekly winner is archived
  and crowned Clubhouse Champion for the following week.

## Not built (deliberately)

- No persistence (SQLite/Redis wiring is the deploy step, spec §10.4).
- No NodeCG replicant wiring, chat commands, or web prediction panel —
  the engine exposes `Market.to_replicant()` in the broadcast-stack §4.3
  shape for that layer to consume.
- No platform identity verification or CAPTCHA (§9.2) — those live in
  the platform layer, not the economy.
- No enforcement tooling (flags, freezes, bans) beyond logging — §9.4
  requires human review before any ban or balance adjustment.
