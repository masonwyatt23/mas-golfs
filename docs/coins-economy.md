# Mas Golfs — Clubhouse Coins Prediction Economy

**The one-line rule:** Clubhouse Coins are free play money. Earned by watching and predicting. Never purchasable, never convertible to anything of value, never transferable, never cashable out. Status, leaderboard rank, and cosmetic perks only. No cash-out path, no crypto, no secondary market — ever, until counsel reviews it.

This document is the complete, implementation-ready specification of the economy: how coins are earned, how odds are set, what markets exist, how payouts work, how leaderboards and streaks work, how abuse is prevented, what the viewer sees, and where the legal line sits.

Everything here is consistent with the rest of the repo:

- [docs/launch-playbook.md](launch-playbook.md) §5.3 — prediction formats, weekly reset on Mondays, all-time hall of fame.
- [docs/broadcast-stack.md](broadcast-stack.md) §4.3 — the `prediction` replicant (`question`, `odds`, `pool_coins`, `closes_in_s`, `open`).
- [docs/livestream-plan.md](livestream-plan.md) §5 — the closed-loop coin economy.
- [docs/sim-engine.md](sim-engine.md) — Mas's real stats, which are the inputs to the odds model.

---

## 1. Design principles

1. **A stake makes every shot matter.** Watching without a stake is like watching a sport you can't bet on. The coins exist to turn a 30-second wait into a decision.
2. **The house never takes a cut.** Every market is a parimutuel pool: all staked coins go to the winners, split proportionally. There is no vig, no rake, no house edge. This is what makes it a game between viewers, not a product sold to them.
3. **Coins are earned, never bought.** There is no purchase path in the product at all — no store, no "buy coins" button, no price. The only way in is watching and playing well.
4. **A new viewer is never broke.** Starting bankroll plus a daily allowance means anyone can play from the first minute they arrive, with no wait and no payment.
5. **The economy is legible.** Odds, pools, and payouts are shown on screen at all times. A viewer can always answer "what happens if I win?" in one glance.
6. **Losing must be survivable.** Stakes are capped per market, a daily allowance refills the bankroll, and no single prediction can wipe a viewer out. A broke viewer is a viewer who leaves.
7. **The market is the show.** Odds moving, pools growing, and the chat debating a line are three engagement spikes per market — announcement, debate, resolution.

---

## 2. Currency: what a coin is and isn't

| Property | Value |
|---|---|
| Name | Clubhouse Coin |
| Symbol | 🪙 (display only; never an emoji in code — use `CC` in data) |
| Monetary value | **Zero.** No cash value, no redemption value, no exchange rate. |
| Purchasable | **No.** No store, no price, no payment flow. |
| Transferable | **No.** Coins cannot be sent to another viewer. |
| Withdrawable | **No.** No cash-out, no gift cards, no crypto, no merchandise redemption for coins. |
| Expirable | Weekly competition balances reset (see §7). All-time balances never expire. |
| Spendable on | Predictions only, plus cosmetic perks (§8.3). Never on anything with real-world value. |
| Storage | Per-viewer ledger in the economy service (see §10). Balances are server-side; the client never holds authoritative state. |

### 2.1 Two balances, one wallet

Every viewer has **two balances** that share one identity:

| Balance | Purpose | Reset |
|---|---|---|
| **Weekly balance** | The live competition. This is what the weekly leaderboard ranks. | Every Monday 00:00 ET. Resets to the starting bankroll (§3.1). |
| **All-time balance** | The hall of fame. Lifetime earnings, never reset. | Never. |

Why two: a new viewer arriving mid-season can compete for the weekly board on day one (everyone resets together), while long-term viewers keep a permanent record. The weekly board is the game; the all-time board is the legacy.

**Rules:**

- Predictions are always staked from the **weekly balance**. All-time balance is a record, not a spendable pot.
- Winnings are credited to **both** balances (weekly spendable + all-time record) in the same amount.
- The daily allowance (§3.2) credits the **weekly balance** only.
- The weekly leaderboard ranks by weekly balance; the all-time leaderboard ranks by all-time balance.

---

## 3. Earning: how coins enter the economy

Coins enter only through **watching and playing well**. There is no other faucet.

### 3.1 Starting bankroll

| Item | Value |
|---|---|
| New viewer starting weekly balance | **1,000 CC** |
| New viewer starting all-time balance | **1,000 CC** (same grant, recorded once) |

A new viewer gets 1,000 CC the moment their identity is created (first chat message, first prediction attempt, or first watch-time tick — whichever comes first). No wait, no tutorial, no payment. 1,000 CC is enough for ~10–20 predictions at typical stakes, which is enough to learn the game in one session.

### 3.2 Daily allowance

| Item | Value |
|---|---|
| Daily allowance | **500 CC / day** |
| Credited | First activity of the day (any watch-time tick, chat message, or prediction) |
| Accumulation | **No.** Unclaimed days do not stack. One allowance per calendar day (ET), claimed or lost. |
| Cap interaction | The allowance is credited even if the viewer is above the starting bankroll. There is no balance cap. |

The allowance exists for one reason: **a broke viewer must never be stuck.** A viewer who loses everything can come back tomorrow with 500 CC and play again. This is the single most important retention mechanic in the economy.

### 3.3 Watch-time earnings

| Item | Value |
|---|---|
| Watch-time rate | **10 CC per 10 minutes watched** (1 CC/min, credited in 10-CC increments) |
| Requirement | Stream must be the active tab / player unmuted and playing (platform watch-time semantics apply; the economy trusts the platform's watch-time signal, it does not implement its own) |
| Cap | **360 CC per day** from watch time (6 hours). Prevents idle farming (see §9). |
| Credit timing | Credited in arrears every 10 minutes. A viewer who watches 7 minutes earns 0; at 10 minutes, 10 CC. |

Watch time is the slow faucet. It rewards presence, not attention — deliberately, because this is an ambient stream. A viewer who leaves it on in the background is a real viewer.

### 3.4 Prediction winnings

The main faucet. See §6 for payout math. A winning prediction returns the stake plus a proportional share of the losing side's pool.

### 3.5 Streak bonuses

Consecutive correct predictions pay a bonus on top of the pool payout (see §8.1). Streaks are the skill signal: a viewer who reads Mas's game well should get richer faster than a viewer who guesses.

### 3.6 Milestone bonuses

One-time grants for firsts (see §8.2). These are onboarding rewards, not a faucet — each milestone pays once per viewer, ever.

### 3.7 What does NOT earn coins

- Chat messages (no per-message payout — this is the #1 farming vector).
- Follows, subs, or Bits (platform actions are not coin faucets; subs get a cosmetic perk instead, §8.3).
- Referring other viewers (no referral payouts — they are trivially farmed).
- Voting in polls that are not prediction markets.
- Any action that can be scripted without watching.

### 3.8 Economy faucet summary (per viewer, per day, maximum)

| Source | Max / day |
|---|---|
| Daily allowance | 500 CC |
| Watch time (6 h cap) | 360 CC |
| Prediction winnings | Uncapped (skill-based) |
| Streak bonuses | Uncapped (skill-based) |
| Milestones | One-time only |

A passive viewer earns at most **860 CC/day**. An active, skilled predictor earns more — and that is the point.

---

## 4. Staking: how much a viewer can risk

### 4.1 Per-market stake limits

| Market type | Minimum stake | Maximum stake |
|---|---|---|
| Per-shot | 10 CC | 100 CC |
| Per-hole | 10 CC | 250 CC |
| Round-level (Nassau, Road to 59) | 25 CC | 500 CC |

Limits exist so no single market can wipe a bankroll, and so a rich viewer cannot dominate a pool by sheer size. A viewer with 50,000 CC and a viewer with 500 CC both cap at the same stake on any given market — the game is about reading golf, not about being rich.

### 4.2 One position per market

A viewer may stake on **one side only** of any market. You cannot bet both "yes" and "no" on the same question. This prevents risk-free hedging and keeps pools honest.

### 4.3 No stake changes after close

Once a market closes (see §5.4), the stake is locked. No editing, no cancelling, no cashing out early. The bet stands until resolution.

### 4.4 Insufficient funds

If a viewer tries to stake more than their weekly balance, the stake is rejected with a clear message ("Not enough coins — your daily allowance lands tomorrow, or keep watching to earn more"). The client must check the balance before submitting; the server must re-check before accepting.

---

## 5. The odds model: how prices are set and how they move

Odds are **the product's brain**. They must be honest (reflect Mas's real chances), dynamic (move with form, hole, and volume), and legible (a viewer understands them at a glance).

### 5.1 Odds format

All odds are displayed as **decimal odds** (e.g. 2.40 means a winning 100 CC stake returns 240 CC including the stake). Decimal odds are the clearest format for a mixed audience and the easiest to compute from probabilities.

```
decimal_odds = 1 / implied_probability
```

Implied probabilities across all outcomes of a market always sum to **1.00** — there is no overround, no vig, no house margin. The market is a pure reflection of probability.

### 5.2 Base probabilities: from Mas's real stats

Every market's base probability comes from the sim's calibrated model of Mas, not from vibes. The inputs live in the sim engine ([docs/sim-engine.md](sim-engine.md)) and are updated as Mas plays.

**Per-shot base rates (starting calibration, +3 at Wyatt National):**

| Shot / situation | Base probability (fairway / GIR / proximity) |
|---|---|
| Fairway hit, par 4/5 tee shot | 0.55–0.60 |
| Green in regulation, approach 100 yd | 0.68 |
| Green in regulation, approach 150 yd | 0.60 |
| Green in regulation, approach 200 yd | 0.45 |
| Proximity inside 10 ft, approach 100 yd | 0.28 |
| Proximity inside 10 ft, approach 150 yd | 0.20 |
| Proximity inside 10 ft, approach 200 yd | 0.12 |
| Up-and-down from greenside bunker | 0.45 |
| Up-and-down from rough, < 20 yd | 0.55 |
| One-putt from inside 6 ft | 0.85 |
| One-putt from 10 ft | 0.40 |
| One-putt from 20 ft | 0.14 |

**Per-hole base rates (starting calibration):**

| Outcome | Base probability |
|---|---|
| Birdie or better, par 5 | 0.30 |
| Birdie or better, par 4 | 0.16 |
| Birdie or better, par 3 | 0.12 |
| Par or better, any hole | 0.72 |
| Bogey or worse, any hole | 0.28 |

These are starting values. The odds engine must re-derive them from Mas's actual rolling stats (last 10 rounds minimum, last 50 rounds preferred) at least once per round. If Mas's fairway rate over the last 10 rounds is 0.62, the base fairway probability is 0.62 — not the table value.

### 5.3 Adjustments: form, hole, conditions

The base probability is adjusted by three multipliers before odds are set:

```
p_adjusted = clamp(p_base × form_factor × hole_factor × condition_factor, 0.02, 0.98)
```

| Factor | Range | What it captures |
|---|---|---|
| `form_factor` | 0.85–1.15 | Mas's recent form. Computed from his last-10 scoring average vs. his season average: hot (scoring 1.5+ strokes under average) → up to 1.15 on positive outcomes; cold → down to 0.85. Updated once per round. |
| `hole_factor` | 0.70–1.30 | Hole difficulty and shape. From the course design ([docs/course-design.md](course-design.md)): e.g. birdie probability on the drivable par-4 5th is higher than on the 455-yard uphill 13th; fairway probability on the narrow 13th is lower than on the wide 1st. Each hole carries a stored difficulty vector (fairway, GIR, birdie, bogey rates) derived from Mas's actual history on that hole. |
| `condition_factor` | 0.80–1.20 | Wind and lie. Into the wind / from heavy rough / from a bunker → down to 0.80. Downwind / from the fairway with a good lie → up to 1.20. Computed per shot from the sim's live state. |

The adjustment factors are **shown on screen** next to the odds ("Fairway 2.10 — into the wind, narrow hole"), so viewers learn *why* the price is what it is. The odds are a teaching tool, not a black box.

### 5.4 Odds movement: volume-weighted, capped

Once a market opens, odds move with betting volume — but slowly, and within a band.

**Mechanism (parimutuel-implied):**

1. At open, odds are set from `p_adjusted` (§5.3).
2. As stakes arrive, the implied probability of each side is re-computed from the pool split:
   ```
   implied_p(side) = pool(side) / pool(total)
   ```
3. Displayed odds blend the model price and the pool price, 50/50:
   ```
   displayed_p(side) = 0.5 × p_adjusted(side) + 0.5 × implied_p(side)
   displayed_odds(side) = 1 / displayed_p(side)
   ```
4. Movement is **capped**: displayed odds may not move more than ±25% from the opening odds. This prevents a single large stake (or a coordinated group) from swinging a price to absurdity.

**Why the 50/50 blend:** pure pool odds are easily manipulated early (one 100 CC stake on an empty market moves the price to infinity); pure model odds ignore the crowd entirely. The blend keeps the price anchored to reality while letting the crowd's view matter.

**Timing:** odds update at most once per second, and only while the market is open. Odds freeze at market close.

### 5.5 Market lifecycle

Every market follows the same lifecycle, driven by sim events on the event bus:

| Phase | Trigger | Duration | What happens |
|---|---|---|---|
| **Announce** | Sim emits `decision` (the plan for the next shot/hole) | Instant | The market question appears on screen with opening odds and the decision line ("Knockdown 7-iron, into the wind, right edge"). The prediction panel opens. |
| **Open** | Immediately after announce | 20–30 s (per-shot), 60–90 s (per-hole), until tee-off (round-level) | Viewers stake. Odds move per §5.4. Pool total shown live. Countdown shown. |
| **Close** | Sim emits `shot_start` (per-shot), tee shot struck (per-hole), or round start (round-level) | Instant | Stakes lock. Odds freeze. "Bets closed" shown. No new stakes, no changes. |
| **Resolve** | Sim emits the outcome event (`landing`, `putt_result`, `hole_end`, `round_end`) | Instant | Winners determined, payouts credited, results shown on screen (see §6). |
| **Settle** | Immediately after resolve | 5 s | The result card shows: outcome, winners, total pool, your payout. Then the next market announces. |

**Total cycle for a per-shot market: under 30 seconds from announce to settle.** This is the heartbeat of the stream. A viewer who joins mid-hole can be betting within half a minute.

---

## 6. Payout math: proportional pool splits, no house cut

### 6.1 Two-outcome markets (yes/no)

The standard market. All stakes on the losing side are distributed to the winning side, proportional to each winner's stake.

```
pool_total = pool_yes + pool_no
if outcome == yes:
    winners_share = pool_total
    payout(viewer) = stake(viewer) × (pool_total / pool_yes)
else:
    payout(viewer) = stake(viewer) × (pool_total / pool_no)
```

**Worked example:** "Birdie or better on 12?" — 800 CC staked on Yes, 1,200 CC on No. Mas birdies.

- Total pool: 2,000 CC.
- A viewer who staked 100 CC on Yes gets: 100 × (2,000 / 800) = **250 CC** (100 stake returned + 150 profit).
- A viewer who staked 100 CC on No gets: **0 CC**.

The effective odds at resolution (2.50) differ from the displayed odds at stake time (which moved with volume) — this is normal for parimutuel markets and must be explained on screen: "Payouts are split from the pool — final odds depend on where the money lands."

### 6.2 Multi-outcome markets (score on a hole: birdie / par / bogey+)

Same principle, three pools:

```
payout(viewer) = stake(viewer) × (pool_total / pool(winning_outcome))
```

### 6.3 Skins (per-hole pots with carryover)

Each hole is its own pot. Viewers stake on "Mas wins the skin" (birdie or better) vs. "No skin" (par or worse). If Mas does not win the skin, the pot **carries over** to the next hole — so a late hole can be worth several skins' worth of coins. Carryover pots are shown on screen ("Skin pot: 3 skins — 4,200 CC"). When a skin is won, the pot is split proportionally among that hole's winners, and the carryover resets to zero.

### 6.4 Nassau (front 9 / back 9 / overall)

Three linked markets per round. A viewer stakes separately on each leg (front 9 under par? back 9 under par? overall under par?). Each leg resolves independently as a two-outcome pool. A viewer who wins all three legs gets a **Nassau sweep bonus** of +25% on their total Nassau winnings for the round (paid from the bonus pool, §6.6).

### 6.5 Road to 59 season markets

Long-horizon markets, priced from Mas's season stats:

| Market | Resolution | Base probability source |
|---|---|---|
| "Will Mas break 60 this week?" | End of the week (Sunday 23:59 ET) | 1 − (probability no round ≤ 59 in ~21 rounds this week), from his season sub-60 rate |
| "Will Mas break 60 this season?" | End of the season (defined as 90 days from launch) | Season sub-60 rate × rounds remaining |
| "Mas's best round this week: under 65?" | End of the week | His last-10 best-round distribution |

Season markets stay open for days, with odds updating once per round (not per second). Stakes are capped at 500 CC (§4.1). Long odds, big payouts, and a reason to follow the whole season.

### 6.6 The bonus pool (where streak and sweep bonuses come from)

Streak bonuses (§8.1) and Nassau sweep bonuses (§6.4) are paid from a **bonus pool**, not from other viewers' stakes — otherwise winners would be diluted by bonuses.

**Bonus pool funding:** the pool is seeded at **10,000 CC per week** by the system (not by viewers) and refills to 10,000 CC every Monday at reset. It is a fixed, transparent subsidy. If the bonus pool empties mid-week, bonuses pause (shown as "Bonus pool empty — refills Monday") and resume at refill. Bonuses never come from staked coins.

### 6.7 Rounding

All payouts are rounded **down** to the nearest whole coin. Fractional remainders (dust) accrue to the bonus pool. A viewer never receives a fractional coin.

### 6.8 Failed / voided markets

If a market cannot resolve (sim error, stream interruption, outcome event never arrives):

- All stakes are **refunded in full** to the weekly balance.
- The market is marked VOID on screen and in the log.
- Voided markets do not count for or against streaks.
- If a round is abandoned mid-round (stream outage), all open markets for that round are voided and refunded.

---

## 7. Leaderboards

### 7.1 Weekly leaderboard (the live competition)

| Item | Value |
|---|---|
| Ranked by | Weekly balance (highest first) |
| Reset | Every Monday 00:00 ET. Balances reset to 1,000 CC starting bankroll. |
| Display | Top 10 on screen (ticker + leaderboard card); full top 100 on the web leaderboard page |
| Winner celebration | Monday prime-time moment: the winner is named on screen, in chat, and in a clip. Winner gets the "Clubhouse Champion" cosmetic (§8.3) for the week. |
| Tie-break | Earlier to reach the balance wins the tie. |

### 7.2 All-time leaderboard (the hall of fame)

| Item | Value |
|---|---|
| Ranked by | All-time balance (highest first) |
| Reset | Never |
| Display | Top 10 on the leaderboard card; full top 100 on the web page |
| Significance | Permanent record. The all-time board is the legacy — a viewer who was there from day one keeps their place. |

### 7.3 Daily leaderboard

Ranked by coins won **that day** (net winnings, not balance). Resets daily at 00:00 ET. Shown as a small "today's hot hand" strip. Purely for daily bragging rights; no prize beyond the title.

### 7.4 Biggest wins board

A permanent list of the largest single-market payouts (viewer, amount, market, date). Updated live. This is the "did you see that?" board — a 5,000 CC payout on a long-shot Road to 59 market is a clip in itself.

### 7.5 What leaderboards never show

- Real names, emails, or any personal data. Viewers are shown by display name only.
- Any link between coins and real money. The boards are explicitly labeled "Play money — no cash value."

---

## 8. Streaks, achievements, and cosmetics

### 8.1 Streaks

A **streak** is consecutive correct predictions (any market type, any stake size). A wrong prediction or a voided market breaks the streak (voids neither break nor extend it — they are ignored).

| Streak length | Bonus on next win |
|---|---|
| 3 in a row | +10% of that win's profit |
| 5 in a row | +25% of that win's profit |
| 8 in a row | +50% of that win's profit |
| 12+ in a row | +100% of that win's profit (double the profit) |

**Rules:**

- The bonus applies to the **profit** (payout minus stake), not the total payout.
- The bonus is paid from the bonus pool (§6.6), not from other viewers.
- The streak counter is shown on screen next to the viewer's name in chat ("🔥 5" — display only; the counter is the data).
- The longest streak is tracked per viewer (all-time) and shown on their profile card.
- Streaks reset on a wrong prediction. There is no "streak insurance" or streak protection purchase (there is no purchase path at all).

### 8.2 Achievements (milestones)

One-time grants, paid once per viewer ever. Each achievement also unlocks a cosmetic badge (§8.3).

| Achievement | Condition | Grant |
|---|---|---|
| First Bet | Place your first prediction | 100 CC |
| First Win | Win your first prediction | 100 CC |
| Hot Hand | Win 3 in a row | 250 CC |
| Sharpshooter | Win 5 in a row | 500 CC |
| Oracle | Win 8 in a row | 1,000 CC |
| Century Club | Place 100 predictions | 500 CC |
| Skin Collector | Win 10 skins | 500 CC |
| Nassau Sweep | Win all three Nassau legs in one round | 1,000 CC |
| Road to 59 | Win a Road to 59 season market | 2,000 CC |
| Clubhouse Regular | Watch 10 hours total | 500 CC |
| Prime Time | Be present for 5 Monday prime-time moments | 500 CC |

### 8.3 Cosmetic perks (the only thing coins "buy")

Coins can be spent on **cosmetic perks only** — visible status, never advantage, never real-world value:

| Perk | Cost | What it is |
|---|---|---|
| Custom chat badge | 500 CC | A badge next to your name in chat for 7 days |
| Name color | 1,000 CC | A custom chat name color for 7 days |
| Prediction flair | 2,500 CC | A flair shown on your predictions on screen for 7 days |
| Clubhouse Champion | Not purchasable | Weekly leaderboard winner only, for the following week |

**Rules:**

- Cosmetics are time-limited (7 days) and non-transferable.
- Cosmetics never affect odds, payouts, stake limits, or market access. A paying viewer gets no advantage.
- Cosmetic purchases are deducted from the **weekly balance** (they are a spend, not an investment).
- There is no cosmetic that costs real money. There is no real-money purchase path for cosmetics.

---

## 9. Anti-abuse rules

The economy is free and open, which makes it a target. These rules are enforced server-side; the client cannot bypass them.

### 9.1 Identity

- One wallet per platform identity (one Twitch account = one wallet; one YouTube account = one wallet). Cross-platform wallets are **not** merged — a viewer has a separate wallet per platform.
- No wallet creation without a platform identity. Anonymous viewers can watch but cannot predict.
- A viewer who is banned from chat loses prediction access for the duration of the ban. Their balance is preserved.

### 9.2 Farming

| Vector | Mitigation |
|---|---|
| Idle watch-time farming (leaving the stream on muted, 24/7) | Watch-time earnings cap at 360 CC/day (§3.3). Platform watch-time semantics (active tab / unmuted) apply. |
| Bot predictions | Rate limit: max 1 prediction per market per viewer (§4.2); max 60 predictions per hour per viewer (far above human pace, far below script pace). CAPTCHA on wallet creation if abuse is detected. |
| Multi-accounting (many wallets, one person) | One wallet per platform identity; platform-level enforcement. No cross-wallet transfers exist, so multi-accounting gains nothing — coins cannot be pooled. |
| Chat spam for coins | Chat messages earn zero coins (§3.7). There is nothing to farm in chat. |
| Odds manipulation (coordinated staking to move a price) | Odds movement capped at ±25% from open (§5.4); 50/50 model/pool blend anchors the price; per-market stake caps limit any single wallet's influence. |
| Streak farming (tiny stakes on safe markets to build a streak, then a big stake) | Streak bonuses scale with the *profit* of the winning bet, not the streak alone — a 10 CC streak win earns a 10 CC-scale bonus. There is no advantage to farming a streak on minimum stakes. |

### 9.3 No transfers, no secondary market

- There is **no transfer function** in the economy. No API, no UI, no command. Coins cannot move between viewers, period.
- There is **no marketplace** for coins, cosmetics, or accounts. Any third-party market is unsupported and, if discovered, the involved wallets are frozen pending review.
- Cosmetics are non-transferable and expire. They cannot be sold or gifted.

### 9.4 Monitoring and enforcement

- The economy service logs every transaction (earn, stake, payout, bonus, purchase) with viewer ID, timestamp, market ID, and amounts.
- Automated flags: watch-time earnings at cap for 7+ consecutive days; prediction volume > 3 standard deviations above the mean; win rate > 80% over 50+ predictions (possible inside information or a model — investigate, don't auto-ban); rapid wallet creation from one IP.
- Human review before any ban or balance adjustment. No automated balance wipes. Ever.
- All enforcement actions are logged and reversible.

---

## 10. System design: how it is built

### 10.1 Components

```
Sim engine ──JSON events──▶ Event bus (WebSocket, port 4456)
   │
   ├─▶ Odds engine ──▶ Market service ──▶ NodeCG `prediction` replicant ──▶ OBS graphics
   │                                              │
   │                                              └─▶ Prediction panel (chat / web overlay)
   │
   └─▶ Economy service (ledger, balances, payouts, streaks, leaderboards)
            │
            ├─▶ PostgreSQL / SQLite (ledger + balances; append-only transaction log)
            └─▶ Redis (live pools, open markets, odds cache)
```

### 10.2 Data model

**Viewer wallet:**

```json
{
  "viewer_id": "twitch:12345678",
  "platform": "twitch",
  "display_name": "FairwayFan",
  "weekly_balance": 2450,
  "alltime_balance": 18700,
  "daily_allowance_claimed": "2026-11-12",
  "watch_minutes_today": 130,
  "watch_earned_today": 130,
  "streak_current": 4,
  "streak_best": 9,
  "predictions_placed": 142,
  "predictions_won": 81,
  "achievements": ["first_bet", "first_win", "hot_hand"],
  "cosmetics": [{"type": "chat_badge", "expires": "2026-11-19T00:00:00Z"}],
  "created_at": "2026-11-12T14:03:00Z"
}
```

**Market:**

```json
{
  "market_id": "r42-h12-shot2",
  "type": "per_shot",
  "question": "Fairway on 12?",
  "outcomes": ["yes", "no"],
  "opening_odds": {"yes": 1.85, "no": 2.10},
  "current_odds": {"yes": 1.92, "no": 2.02},
  "pools": {"yes": 840, "no": 760},
  "base_probability": {"yes": 0.55, "no": 0.45},
  "adjustments": {"form": 1.05, "hole": 0.95, "condition": 1.00},
  "min_stake": 10,
  "max_stake": 100,
  "opens_at": "2026-11-12T14:03:00Z",
  "closes_at": "2026-11-12T14:03:25Z",
  "status": "open",
  "round": 42,
  "hole": 12,
  "shot": 2
}
```

**Prediction (a single stake):**

```json
{
  "prediction_id": "pred_9f31c2",
  "market_id": "r42-h12-shot2",
  "viewer_id": "twitch:12345678",
  "outcome": "yes",
  "stake": 100,
  "odds_at_stake": 1.92,
  "status": "pending",
  "placed_at": "2026-11-12T14:03:11Z",
  "resolved_at": null,
  "payout": null
}
```

**Ledger entry (append-only):**

```json
{
  "entry_id": "led_00012345",
  "viewer_id": "twitch:12345678",
  "type": "payout",
  "amount": 250,
  "balance_after": 2700,
  "market_id": "r42-h12-shot2",
  "prediction_id": "pred_9f31c2",
  "timestamp": "2026-11-12T14:03:41Z"
}
```

### 10.3 Event flow (per-shot market, end to end)

1. Sim emits `decision` → Market service creates the market (odds from §5), writes the NodeCG `prediction` replicant → OBS shows the question, odds, pool, countdown.
2. Viewer stakes via chat command or web panel → Economy service validates (balance, stake limits, one-position rule, market open) → deducts stake from weekly balance → appends ledger entry → pool updates → odds re-blend (§5.4).
3. Sim emits `shot_start` → Market service closes the market → replicant `open: false` → OBS shows "Bets closed."
4. Sim emits `landing` → Market service determines the winning outcome → Economy service computes payouts (§6), credits winners (weekly + all-time), applies streak bonuses from the bonus pool, appends ledger entries → replicant updates with result → OBS shows the result card for 5 seconds.
5. Next `decision` event → cycle repeats.

**Latency budget:** stake → confirmed in under 1 second. Resolve → payout credited in under 2 seconds. A viewer must see their result before the next market announces.

### 10.4 Free-tier stack

The entire economy runs on free infrastructure:

| Component | Free option |
|---|---|
| Economy service | Node.js on the same box as OBS (no separate server) |
| Ledger / balances | SQLite (single file, append-only log; PostgreSQL if scale demands it — also free) |
| Live pools / odds | In-memory + Redis (free, same box) |
| Graphics | NodeCG (open source) via OBS browser sources |
| Prediction input | Twitch chat commands + YouTube live chat (platform-native, free) |
| Hosting | The same GPU box that renders the stream — no additional hosting cost |

No paid service is required at any point. The economy's marginal cost is zero.

### 10.5 Failure modes

| Failure | Behavior |
|---|---|
| Economy service down, stream up | Markets pause (no new markets open). Open markets void and refund (§6.8). The show continues; the betting pauses. |
| Stream down, economy up | Markets cannot resolve (no outcome events). Open markets void and refund. |
| Odds engine stale (no fresh stats) | Markets fall back to the last computed base probabilities with a "stats delayed" flag on screen. Never invent odds. |
| Bonus pool empty | Bonuses pause with an on-screen note; resume at Monday refill (§6.6). Stakes and payouts are unaffected. |
| Ledger write fails | The transaction is rejected, not partially applied. No payout without a ledger entry. No stake without a ledger entry. |

---

## 11. The viewer experience: a prediction in under 30 seconds

The whole flow, from a new viewer's perspective:

1. **0:00** — Viewer arrives mid-round. The scorebug tells the story in 3 seconds (hole, score to par, Road to 59 target). The prediction panel shows the live market: "Fairway on 12? Yes 1.92 / No 2.02 — pool 1,600 CC — closes in 18 s."
2. **0:05** — Viewer taps "Yes — 50 CC" (or types `!bet yes 50` in chat). The panel confirms instantly: "50 CC on Yes @ 1.92. Good luck."
3. **0:18** — Market closes. "Bets closed." The tracer cam follows the ball.
4. **0:25** — The ball lands in the fairway. The result card appears: "FAIRWAY ✓ — You won 120 CC." The balance updates on screen.
5. **0:30** — The next market announces: "GIR on 12? Yes 1.70 / No 2.30."

**A viewer who has never seen the stream can be betting within 30 seconds of arriving, and winning within a minute.** That is the bar. Anything slower — a tutorial, a wallet setup flow, a deposit screen — is a bug.

**New-viewer onboarding (invisible):** there is no onboarding flow. The starting bankroll is granted silently on first activity. The first market they see includes a one-line hint ("New here? You start with 1,000 free coins — tap to bet"). After their first prediction, the hint never appears again.

---

## 12. The legal boundary: why this stays play money

### 12.1 The three-part test

Gambling law in most jurisdictions turns on three elements: **consideration** (something of value staked), **chance** (outcome determined at least partly by chance), and **prize** (something of value won). This economy is designed so that **consideration and prize are both absent**:

- **No consideration:** coins are free. They cannot be purchased, so no viewer ever stakes anything of value. Watch time is not consideration — it is not a payment, and coins earned by watching have no cash value.
- **No prize:** coins have no cash value, cannot be redeemed, converted, transferred, or spent on anything with real-world value. Cosmetics are status only, time-limited, and non-transferable.
- **Chance is present** (golf outcomes are uncertain) — but chance alone, without consideration and prize, is not gambling. It is a game.

### 12.2 What would change that (do not do any of these)

| Change | Why it breaks the boundary |
|---|---|
| Selling coins for cash | Creates consideration. Instantly gambling-adjacent. |
| Cashing coins out (cash, gift cards, crypto, merch) | Creates a prize. Instantly gambling. |
| Letting viewers transfer coins to each other | Creates a secondary market and a de facto exchange rate. |
| Redeeming coins for merchandise or services | Creates a prize with real-world value. |
| Charging entry for a prediction market | Creates consideration (an entry fee for a chance-based prize). |
| Sponsored coin prizes with real-world value | The sponsor's prize is a prize. Keep sponsors to brand visibility only. |

**The "eventually crypto" idea from the original brief stays off the roadmap until counsel reviews it.** Any conversion path from coins to crypto, tokens, or any asset with market value would reclassify the entire economy. This is the single biggest legal risk in the project and the one rule that does not bend.

### 12.3 Platform compliance

- **Twitch:** Channel Points predictions are the platform-native equivalent and the model for this design. The economy must not circumvent or replace Twitch's own prediction system in a way that violates Twitch's terms — if Twitch's rules change, the economy adapts to them.
- **YouTube:** No real-money betting features are used. The AI-use disclosure (§11 in the livestream plan) covers the stream itself.
- **General:** Keep the "Play money — no cash value" label visible wherever coins appear on screen. Keep the closed-loop rules in the repo ([docs/livestream-plan.md](livestream-plan.md) §5, [docs/launch-playbook.md](launch-playbook.md) §5.3) and enforce them in code, not just in policy.

### 12.4 When to get a lawyer

Before any of the following, get a written review from counsel:

- Any change to the closed-loop rules in this document.
- Any sponsorship involving coins, prizes, or viewer rewards.
- Any expansion to a jurisdiction with stricter social-gaming rules.
- Any feature that lets coins touch anything with real-world value.

Until then, the economy ships exactly as specified here: free in, free out, nothing of value at either end.

---

## 13. Build order

1. **Ledger + wallets** — append-only transaction log, two balances, daily allowance, watch-time earnings. Test: grant, earn, and balance queries all work with zero predictions.
2. **Market service + odds engine** — base probabilities from sim stats, three adjustment factors, 50/50 volume blend, ±25% movement cap. Test: odds match hand-computed values for a known stat line.
3. **Per-shot markets end to end** — announce → open → close → resolve → settle, under 30 seconds, with payouts correct to the coin. Test: a full hole of markets with known outcomes.
4. **Per-hole and round-level markets** — skins with carryover, Nassau with sweep bonus, Road to 59 season markets. Test: a full round, including a carried-over skin.
5. **Streaks, achievements, cosmetics** — bonus pool funding and caps, one-time grants, time-limited cosmetics. Test: a 5-streak win pays the +25% bonus from the pool, not from other viewers.
6. **Leaderboards** — weekly (Monday reset), all-time (never), daily, biggest wins. Test: reset preserves all-time balances and archives the weekly winner.
7. **Anti-abuse** — rate limits, stake caps, farming mitigations, logging, flags. Test: a scripted farming attempt earns nothing beyond the caps.
8. **Viewer experience pass** — 30-second first-bet flow, mobile prediction panel, result cards. Test: a new viewer bets and wins within 60 seconds of arriving.
9. **Failure-mode drills** — economy down, stream down, voided markets, empty bonus pool. Test: every failure refunds correctly and logs the void.
10. **Soak test** — one full week unattended. Markets open and resolve, leaderboards reset on Monday, no manual intervention required.

---

*Clubhouse Coins — free in, free out, and the only thing at stake is bragging rights.*
