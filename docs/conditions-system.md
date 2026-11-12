# Mas Golfs — Dynamic Conditions & Course-Rating System

**Version 1.0 · 2026-11-12 · Implementation-ready**

This document specifies how conditions vary across rounds at Wyatt National — weather, turf firmness, green speed, course setup — and how those conditions change the golf, the broadcast, the betting markets, and the Road to 59 chase.

It is an **extension** of `sim-engine.md`, not a replacement. The round conditions model in sim-engine §1.4 (wind, temperature, sky, firmness, green speed, drawn once per round from a seeded RNG) is the base layer. This document adds:

1. A weather model with mid-round change (§1).
2. Firmness and green-speed **bands** with exact physical effects (§2, §3).
3. A course rating / slope derivation for Wyatt National, plus harder setup tiers (§4).
4. A conditions calendar so no two rounds feel the same, including "major week" setups (§5).
5. The wiring: how conditions feed the sim, graphics, commentary, coins odds, and 59 Watch (§6).

**Design principles**

- **Conditions are drawn, never scripted.** Every round's setup comes from the seeded RNG (sim-engine §8.4). The calendar (§5) shapes the *distribution*, never the outcome — so any round can still be replayed byte-identically from its seed.
- **Conditions change the golf, not just the picture.** A firm, fast, windy day must be measurably harder in the stats (lower GIR, fewer birdies, higher scoring average) — if the numbers don't move, the conditions are decoration.
- **The viewer can always see the conditions.** Temperature, wind, stimp, and firmness are on screen in the conditions bug (§6.2). A viewer who tunes in mid-round must be able to tell, in three seconds, what kind of day it is.
- **Hard is interesting, impossible is not.** Even the hardest setup ("major week", §5.3) must leave a +3 with a real chance at par. The rating/slope math in §4 is what keeps hard honest.

---

## 1. Weather model

### 1.1 Condition types

The sky state from sim-engine §1.4 (`clear` 40%, `partly_cloudy` 35%, `overcast` 15%, `light_rain` 10%) is expanded into a full weather state. Each round draws one weather state at `round_start`, plus a possible mid-round change (§1.3).

| Weather state | Sky | Wind add | Temp shift | Rain | Share of rounds | Visual signature |
|---|---|---|---|---|---|---|
| `clear` | Blue, few clouds | — | +2°F | None | 40% | Hard shadows, bright fairways, blue sky grading |
| `partly_cloudy` | Broken cloud | — | — | None | 35% | Moving cloud shadows across the fairway |
| `overcast` | Grey, flat light | +1 mph | −2°F | None | 15% | Soft shadows, muted colours, flat light on greens |
| `light_rain` | Low cloud | — | −4°F | Light | 8% | Wet shine, rain on lens, darkened bunkers |
| `storm_cells` | Dark, broken | Gusts ×1.5 | −6°F | Intermittent | 2% | Dark sky bands, heavy rain bursts, then sun |

`storm_cells` is the only state with intermittent rain: rain falls in 3–6 hole bursts, then clears. It exists so the broadcast occasionally gets a dramatic sky — and so the commentary occasionally gets to say "and here comes the weather."

### 1.2 Wind: drawn per round, shifting mid-round

Base wind comes from sim-engine §1.4: `wind_mph` triangular 0–18 peaking at 6 (calm 35%, moderate 45%, strong 20%), direction uniform but biased to the prevailing northwest (300–330°) on 50% of rounds. Per-hole wind is derived from round wind × hole azimuth, plus a per-hole gust factor `N(1.0, 0.12)`.

**Mid-round shift (new in this document).** On 15% of rounds, a weather front crosses at the turn (between holes 9 and 10):

- Wind direction rotates 30–60° (clockwise or counter-clockwise, drawn).
- Wind speed changes by −4 to +6 mph (drawn), clamped to 0–22 mph.
- If the state was `partly_cloudy`, it becomes `overcast` or `light_rain` (drawn 50/50). If it was `clear`, it becomes `partly_cloudy`.
- The shift is emitted as a `conditions_change` event (§6.1) so graphics, commentary, and odds all update at the same moment.

The shift is a story device as much as a physics one: a round that starts calm and ends in wind is a different round from a round that starts windy. The broadcast treats it as a segment break — "the wind has turned, and the back nine is a different golf course."

**Gusts.** Within a hole, wind is not constant. The per-hole gust factor (§1.4) is sampled once per *shot*, not once per hole: `gust = N(1.0, 0.12)` per shot, so two shots on the same hole can face different wind. On `storm_cells` rounds the gust σ doubles to 0.24. The tracer and the flag show the gust the shot was actually hit in — the commentary can say "he caught a lull" and mean it.

### 1.3 Temperature and air density

From sim-engine §1.4/§2.3: temperature is `Normal(62, 10)`, clamped 38–88°F. Carry changes with temperature: +1°F ≈ +0.15 yd on a driver. Air density `ρ = 1.225 × (288.15 / T_kelvin) × 0.955` (the 0.955 is Wyatt National's fixed ~1,400 ft altitude factor).

Cold rounds (< 50°F) cost a real distance: a 45°F morning costs ~4 yd of driver carry vs. a 75°F afternoon. The decision engine (§5 of sim-engine) prices this automatically through the physics — no special rule needed — but the broadcast should say it: "cold morning, the ball isn't going anywhere today."

### 1.4 Visual and broadcast effects of weather

Weather is not a filter applied after the fact. Each state changes the scene:

| Effect | Clear | Partly cloudy | Overcast | Light rain | Storm cells |
|---|---|---|---|---|---|
| Sky grading | Blue, high sun | Blue + moving cloud shadows | Flat grey, low contrast | Dark grey, low sun | Dark bands, dramatic light breaks |
| Shadows | Hard, long | Hard, interrupted by cloud shadows | Soft, diffuse | Soft, short | Hard, then gone in rain bursts |
| Fairway sheen | Matte | Matte | Matte | **Wet shine** — specular highlights on fairways and greens, darker turf | Wet shine in bursts |
| Trees | Still, slight sway | Sway ∝ wind | Sway ∝ wind | Sway + rain drip | Heavy sway in gusts |
| Flag | Limp in calm, stiff in wind | As wind | As wind | Heavy, wet | Whipping in gusts |
| Lens | Clean | Clean | Clean | **Rain on lens** — droplets on the virtual camera, wiped between shots | Rain on lens during bursts |
| Water | Calm, reflective | Ripples | Ripples | Rain rings on the pond | Choppy |
| Ambient audio | Birds, light breeze | Birds, breeze | Breeze, fewer birds | Rain patter under everything | Rain + thunder rumble (distant, never over commentary) |

**Rain on lens** is a broadcast texture, not a gameplay effect: it appears on the tracer camera and the pin camera during rain, clears between shots (the "camera operator wipes the lens"), and never obscures the ball at impact. If it ever hides a shot, it is a bug.

**Wind in the trees** is the broadcast's wind indicator: tree sway amplitude and flag stiffness are proportional to the *current* wind in mph, so a viewer can read the wind from the picture without looking at the bug. The pond surface does the same job on holes 2, 8, and 12 — ripples tell Mas (and the viewer) the wind strength before the swing (see course-design-v2 §2, §8, §12).

---

## 2. Turf firmness

### 2.1 The firmness scale

Sim-engine §1.4 draws `firmness` as `Normal(0.6, 0.12)`, clamped 0.25–0.9. This document defines the bands:

| Band | Firmness range | Share of rounds | What it means |
|---|---|---|---|
| `soft` | 0.25–0.45 | ~20% | Rain-softened or overseeded. Ball plugs, stops dead, no roll. |
| `normal` | 0.45–0.70 | ~60% | Standard parkland. The baseline everything is calibrated to. |
| `firm` | 0.70–0.90 | ~20% | Baked-out summer or tournament prep. Ball bounces, runs, releases. |

The band is computed from the drawn value and stored in the `conditions` object, so every consumer can branch on the band name instead of re-deriving it from the number.

### 2.2 Exact physical effects

These effects apply on top of sim-engine §2.5 (landing: bounce, roll, lie determination). All of them are multipliers on the base values in that section — never replacements.

**Bounce.** Restitution `e = 0.35 × firmness + 0.15` (sim-engine §2.5). Numerically:

| Band (firmness) | Restitution e | First-bounce behaviour |
|---|---|---|
| Soft (0.35) | 0.27 | Ball sits. A full iron barely bounces. |
| Normal (0.60) | 0.36 | One honest bounce, then roll. |
| Firm (0.85) | 0.45 | Ball kicks forward hard. A long iron can bounce 15+ yd. |

**Roll.** Roll deceleration `a_roll = 9.81 × μ` with `μ` by surface (sim-engine §2.5: fairway 0.09, rough 0.16, green 0.05, sand 0.22). Firmness scales the *fairway* μ only: `μ_fairway = 0.09 × (1.25 − 0.5 × firmness)`. At firmness 0.85, `μ_fairway ≈ 0.074` — the ball rolls ~20% further. At firmness 0.35, `μ_fairway ≈ 0.097` — ~8% less roll. Green μ is governed by green speed (§3), not firmness.

**Total driving distance by band** (driver, calm, flat, pure strike — for the broadcast to quote):

| Band | Carry | Roll | Total |
|---|---|---|---|
| Soft | 268 yd | ~4 yd | ~272 yd |
| Normal | 268 yd | ~8 yd | ~276 yd |
| Firm | 268 yd | ~14 yd | ~282 yd |

Carry does not change with firmness (the ball is in the air). Roll is where firmness lives. A firm day makes Wyatt National play ~10 yd shorter per par 4/5 tee shot — the course effectively shrinks, and the decision engine's club selection (§5.6 of sim-engine) accounts for it through the physics.

**Spin on landing.** Backspin > 5,000 rpm checks the ball (roll < 3 yd); < 3,000 rpm releases (roll 5–12 yd) — sim-engine §2.5. Firmness multiplies the *release* roll: `release_roll × (0.7 + 0.6 × firmness)`. On a firm day, a low-spin approach that would release 8 yd releases 12 yd — and runs through the green. On a soft day, the same shot stops in 6 yd. This is the mechanism that makes firm greens the defence: the ball will not hold.

**Chunk and thin rates.** From sim-engine §2.4: chunk rate × 1.6 from light rough, × 2.2 from heavy rough. Firmness adds a fairway modifier: on firm turf (`firmness > 0.70`), thin rate × 1.25 — tight lies punish the thin strike, and the broadcast's "he caught it a groove thin" line appears more often. On soft turf, chunk rate × 1.3 from the fairway — the club digs.

### 2.3 Firmness and club selection

Firmness changes the *correct* shot, not just the outcome:

- **Firm + into the wind:** the knockdown (§4.3 of sim-engine) becomes even more valuable — a low ball that lands and runs beats a high ball that lands and bounces through.
- **Firm greens:** approaches must land short and run on. The decision engine's target shifts from "land it at the pin" to "land it 10–15 yd short of the pin and release" on holes 5, 9, 13, and 15 (the run-up holes from course-design-v2). The commentary explains this — it is the ground game, and it is the most watchable golf in the show.
- **Soft greens:** the aerial attack works. The decision engine aims at the pin, spins it, stops it. Birdie rates rise; the 59 Watch probability rises with them (§6.5).
- **Soft fairways:** the ball plugs in its pitch mark. Lie determination (§2.5 of sim-engine) can produce a "plugged" modifier on approach shots from the fairway: spin × 0.8, distance control σ × 1.2. Rare (5% of fairway lies on soft days), but when it happens the commentary notes it.

---

## 3. Green speed

### 3.1 The Stimpmeter bands

Sim-engine §1.4 draws `green_speed` as `Normal(11.0, 0.6)`, clamped 9.5–12.5 ft. This document defines the bands and extends the top end for major-week setups (§5.3, which widens the clamp to 13.0 — a deliberate spec change, flagged here):

| Band | Stimp (ft) | Share of rounds | What it means |
|---|---|---|---|
| `slow` | 9.5–10.5 | ~15% | Winter or recovery greens. Putts hold their line; lag putting is easy. |
| `normal` | 10.5–11.5 | ~55% | Member-play speed. The calibration baseline. |
| `fast` | 11.5–12.5 | ~25% | Tournament speed. Break doubles; downhill putts are terrifying. |
| `tournament` | 12.5–13.0 | ~5% (major week only) | Major-championship speed. The ball will not stop. |

### 3.2 Effects on putting make rates

Sim-engine §3.5 gives the make-probability table and the adjustment `make_pct × (11.0 / green_speed)^0.5` for putts over 10 ft. Worked out by band (10-ft putt, base 38%):

| Band (stimp) | 10-ft make % | 20-ft make % | 30-ft make % | Three-putt rate |
|---|---|---|---|---|
| Slow (10.0) | 40% | 14% | 5.5% | ~1.5% |
| Normal (11.0) | 38% | 13% | 5% | ~2.5% |
| Fast (12.0) | 36% | 12% | 4.5% | ~3.5% |
| Tournament (13.0) | 35% | 11.5% | 4% | ~4.5% |

The differences look small per putt, but over 18 holes they are worth roughly **0.8 strokes per round** between slow and tournament greens. That is the difference between a 69 and a 70 — and between a 59 chase that lives and one that dies on the greens.

**Break.** Break scales with green speed: `break_ft = base_break × (green_speed / 11.0)`. On tournament greens, a 20-footer breaks a full foot more than on slow greens. The putt-reading graphics (§6.2) show the break line, so the viewer sees why the putt missed.

**Leave distance.** On fast greens, a missed putt with `speed = long` (§3.5 of sim-engine) leaves further: the long-speed leave distribution widens by `(green_speed − 11.0) × 0.5 ft`. On tournament greens, a raced 30-footer can leave 8–10 ft coming back. That is where the three-putts come from, and the commentary should name it: "he'll have eight feet back — and that's no gimme at this speed."

### 3.3 Effects on approach strategy

Green speed changes what the approach should do:

- **Fast/tournament greens:** the approach must land below the hole. The decision engine's target shifts to the front of the green on uphill pins, and the `target_line` fix mechanism (§6.3 of sim-engine) aims at the fat of the green rather than the pin on any approach over 175 yd. Above-the-hole is the cardinal sin — the learning loop flags it (§6.3, `putt` sub-bucket: lag putts from above the hole).
- **Slow greens:** the approach can attack the pin directly. The ball stops; the flag is the target. Birdie rates rise ~10% relative to fast greens.
- **Firm + fast (the major-week combination):** the approach must land short, run on, *and* stop below the hole. This is the hardest combination in golf, and it is why major-week scoring averages jump 2–3 strokes (§5.3).

### 3.4 How the stimp is shown on screen

The stimp reading is part of the conditions bug (§6.2) and is announced once per round at `round_start`:

- **Bug:** `STIMP 11.2` next to the wind reading, with a colour code — green (slow), cream (normal), gold (fast), red (tournament).
- **Hole start:** on par 3s, the hole card shows the stimp next to the pin position — "Pin back-left, stimp 12.4" — because the par-3 tee shot is where green speed matters most.
- **Commentary:** the stimp is mentioned by name at most twice per round (at the open, and when it changes a decision). It is a fact, not a catchphrase.

---

## 4. Course rating and slope

### 4.1 Wyatt National from the back tees — the derivation

Sim-engine §1.2 states Wyatt National's rating as **74.6** and slope as **138**. This section shows the derivation, so the numbers are auditable and so harder setups (§4.3) can be computed the same way.

The USGA Course Rating System computes a rating from **effective playing length** and **obstacle factors**, then derives slope from the difference between the bogey rating and the course rating:

```
slope = 5.381 × (bogey_rating − course_rating)
```

**Effective playing length.** Start with measured yardage, then adjust:

| Adjustment | Effect on length | Wyatt National |
|---|---|---|
| Measured yardage | — | 7,214 yd |
| Roll (firmness normal, 0.60) | −120 yd | Firm fairways add roll; the rating assumes normal conditions |
| Elevation (net uphill) | +85 yd | The course climbs ~250 ft net across 18 holes; uphill holes play long |
| Forced carries (water) | +40 yd | Holes 2, 8, 12 require carries that a scratch golfer must make |
| Dogleg adjustment | +30 yd | Doglegs at 2, 6, 10, 17 force lay-ups off the direct line |
| **Effective playing length** | | **7,249 yd** |

At 7,249 effective yards, the USGA length-based rating for a scratch golfer is approximately **73.9** (the length table gives roughly +0.9 strokes per 100 yd over 6,900 yd on a par-72 course; this is the standard table, not a judgement call).

**Obstacle factors.** Each factor is rated 0–10 and adds strokes to the rating for the scratch golfer:

| Obstacle factor | Rating (0–10) | Strokes added | Why (Wyatt National) |
|---|---|---|---|
| Topography | 6 | +0.35 | Constant elevation change; uphill approaches on 4, 11, 13, 18 |
| Fairway width / landing | 5 | +0.25 | Fairways are wide (32–42 yd), but the *angle* matters — the wrong side is a different hole |
| Green target | 6 | +0.30 | Small, tiered, sloping greens; several with false fronts and run-offs |
| Recoverability / rough | 5 | +0.20 | Thick rough on 4, 10, 13; shaved run-offs reward the short game instead |
| Bunkering | 6 | +0.25 | Deep, flashed bunkers; centreline pot on 5; Road Hole bunker on 17 |
| Water / out of bounds | 5 | +0.20 | Water on 2, 8, 12, 14; OB on 17; the hazards guard the bold line |
| Trees | 4 | +0.10 | Pines frame the fairways; the punch-out is a real shot on 6 and 17 |
| Green surface | 6 | +0.30 | Fast (11.0 stimp baseline), tiered, sloping — the green is the defence |
| Psychological | 4 | +0.10 | Water carries and the Road Hole wall; the course asks questions |
| **Total obstacle strokes** | | **+2.05** | |

The obstacle strokes above are the *bogey* weights — the full cost of each obstacle to a 20-handicap golfer. The USGA system applies them at a reduced weight for the scratch rating, because obstacles hurt the bogey golfer roughly twice as much as the scratch golfer (that is the whole point of slope). The scratch weight is ~0.35:

```
course_rating = 73.9 (length) + 2.05 × 0.35 (obstacles at scratch weight) ≈ 74.6
```

**Bogey rating.** The bogey golfer (index ~20) faces the same length and the obstacles at full weight, plus a distance penalty (the bogey golfer cannot carry the forced carries as easily):

```
bogey_rating = 73.9 (length) + 2.05 × 1.0 (obstacles at bogey weight) + 24.3 (distance penalty*)
             ≈ 100.2
```

*The distance penalty is the USGA's standard allowance for a bogey golfer's shorter driving distance on a 7,214-yard course (~24 strokes over the round from length alone, before obstacles). It is the largest single term, and it is why slope is mostly a length number.*

**Slope:**

```
slope = 5.381 × (100.2 − 74.6) = 5.381 × 25.6 ≈ 138
```

The derivation closes on the stated numbers. The takeaway for the show: **Wyatt National is a hard championship course (74.6 / 138) — a +3 should shoot around par most days, threaten 65 on a hot day, and occasionally get humbled.** That is exactly what course-design-v2 promises, and the rating is the proof.

### 4.2 Rating by tee

The rating above is from the back tees (7,214 yd). If the show ever moves Mas forward (it should not, except for a special event), the rating follows the length table:

| Tees | Yardage | Rating | Slope |
|---|---|---|---|
| Back (championship) | 7,214 | 74.6 | 138 |
| Middle | 6,780 | 72.4 | 132 |
| Forward | 6,350 | 70.1 | 126 |

These are computed from the same length table and obstacle factors, with the distance penalty shrinking as yardage falls. The broadcast uses the back-tee numbers unless a special event says otherwise.

### 4.3 Harder setups — how a course gets harder

A setup is not just "the same course, windier." The setup changes the *effective* rating by changing the obstacles and the conditions. Four setup tiers, each with its own rating/slope (used for handicap differentials in sim-engine §7.1 — the differential is computed against the *setup's* rating, not the base rating, so a 71 in major week is worth more than a 71 on a calm day):

| Setup tier | Rating | Slope | What changes |
|---|---|---|---|
| **Daily** (base) | 74.6 | 138 | Normal firmness (0.45–0.70), normal stimp (10.5–11.5), wind 0–10, pins mid-difficulty, rough standard |
| **Championship** | 75.4 | 141 | Firm (0.70–0.80), fast stimp (11.5–12.5), wind 8–15, pins tucked (difficulty ≥ 0.7 on 6+ holes), rough +0.5 inch |
| **Major week** | 76.2 | 145 | Firm (0.80–0.90), tournament stimp (12.5–13.0), wind 10–18, pins tucked (difficulty ≥ 0.8 on 8+ holes), rough +1 inch, fairways narrowed 10% |
| **Soft / scoring** | 73.8 | 134 | Soft (0.25–0.45), slow stimp (9.5–10.5), wind 0–5, pins accessible (difficulty ≤ 0.5), rough standard |

**How each setup lever moves the rating:**

| Lever | Daily → Championship | Championship → Major week |
|---|---|---|
| Firmness (bounce/roll, §2) | +0.2 | +0.2 |
| Green speed (§3) | +0.2 | +0.2 |
| Wind (8–15 → 10–18) | +0.2 | +0.2 |
| Tucked pins (pin difficulty) | +0.1 | +0.1 |
| Longer rough (lie penalties) | +0.1 | +0.1 |
| Narrowed fairways | — | +0.1 |
| **Total** | **+0.8** | **+0.8** |

**What the harder setups do to the stats** (expected, from the calibration harness in sim-engine §3.7 — these are predictions to verify, not assertions):

| Metric | Daily | Championship | Major week |
|---|---|---|---|
| Scoring average (+3) | 71–73 | 72–74 | 73–76 |
| GIR | ~60% | ~55% | ~50% |
| Birdies per round | ~4.5 | ~3.5 | ~2.5 |
| Bogeys per round | ~2.5 | ~3.5 | ~4.5 |
| P(59) per round | ~0.5% | ~0.1% | ~0.02% |
| P(shooting under par) | ~55% | ~40% | ~25% |

A major-week 74 is a better round than a daily 69. The handicap differential (§7.1 of sim-engine) captures that automatically — and the broadcast should say it, because it is the difference between a number and a story.

**Pin difficulty.** The pin `difficulty` field (sim-engine §1.2, 0–1) is drawn per hole. Setup tiers shift its distribution: daily `Normal(0.5, 0.15)`, championship `Normal(0.65, 0.15)`, major week `Normal(0.75, 0.12)`, soft `Normal(0.4, 0.15)`, all clamped 0.15–0.95. A tucked pin (difficulty ≥ 0.8) is within 6 ft of an edge or on a tier — the approach must be precise, and the miss is punished (§4.2 of sim-engine: the wrong miss costs a stroke).

---

## 5. The conditions calendar

### 5.1 The rotation rule

Rounds are grouped into **weeks of 6 rounds** (Monday–Saturday; Sunday is a rest/clip day in the broadcast calendar). Each week draws a setup tier, and the calendar enforces two rules:

1. **No two consecutive rounds share the same setup tier.** If the RNG draws the same tier twice in a row, re-draw. (The viewer should never feel "this is the same round as yesterday.")
2. **No two consecutive weeks share the same weather state.** Same re-draw rule at week level.

The calendar shapes the distribution; the RNG still decides every individual round. A week can still be all wind, or all calm — the rule only prevents *identical* repeats.

### 5.2 The weekly mix

| Week type | Setup tier | Weather bias | Share of weeks | What it feels like |
|---|---|---|---|---|
| **Standard week** | Daily | No bias (base distribution §1.1) | 55% | The show as normal. The baseline. |
| **Scoring week** | Soft / scoring | Warm, calm (wind −3 mph, temp +5°F) | 15% | Birdie fest. The 59 Watch is alive all week. The clip machine feasts. |
| **Championship week** | Championship | Firm, fast, wind +3 mph | 20% | A test. Par is a good score. The grind is the story. |
| **Major week** | Major week | Firm, tournament stimp, wind +5 mph | 10% | The hardest golf the show plays. Even a +3 struggles. The event of the season. |

A major week is roughly **one week in ten** — about five per year of continuous play. That scarcity is the point: if every week were major week, nothing would be major.

### 5.3 Major week — the event

Major week is the show's tentpole. It is announced in advance (the broadcast teases it the week before: "Major week starts Monday — firm, fast, and windy"), and it has its own presentation:

- **Setup:** firm 0.80–0.90, tournament stimp 12.5–13.0 (the clamp in sim-engine §1.4 is widened to 13.0 for major week — the only place the clamp moves), wind 10–18 mph, pins tucked, rough +1 inch, fairways narrowed 10%. Rating 76.2 / slope 145 (§4.3).
- **Graphics:** a gold "MAJOR WEEK" bug replaces the standard conditions bug for the week. The leaderboard shows a separate major-week scoring average.
- **Commentary:** the host frames every round as a major-championship round — "this is the hardest setup Mas has faced" is true, and it stays true because major week is rare.
- **Coins:** the odds model (§6.4) widens — birdie probabilities fall, so birdie payouts rise. The market loves a major week.
- **59 Watch:** the probability of 59 in major week is ~0.02% per round (§4.3). The broadcast does not pretend otherwise — the 59 Watch bug shows the honest number, and the story becomes "can he break par?" instead. When the 59 Watch turns off in major week, the broadcast says so once and moves on (sim-engine §7.5: no dwelling).
- **Aftermath:** the week after major week is always a scoring week (§5.2) — the release after the tension. The contrast is the arc.

### 5.4 Season structure

Rounds accumulate into seasons. A season is 26 weeks (156 rounds) — roughly six months of continuous play — and ends when Mas shoots 59 (the Road to 59 chase in sim-engine §7.3) or when the 26 weeks run out, whichever comes first. The next season starts with a new chase (Road to 58 if he shot 59; Road to 59 again if he didn't).

The conditions calendar is what makes a season feel like a season instead of 156 identical rounds: scoring weeks where the chase is alive, championship weeks where par is a fight, and the major weeks that everyone remembers.

---

## 6. How conditions feed everything

### 6.1 The sim — the `conditions` object (extended)

The `round_start` event (sim-engine §1.2) already carries a `conditions` object. This document extends it with the new fields. Existing fields are unchanged; new fields are additive, so old consumers keep working.

```json
{
  "type": "round_start",
  "round_id": "R0042", "round_no": 42,
  "course": { "name": "Wyatt National", "par": 72, "yardage": 7214, "rating": 76.2, "slope": 145 },
  "conditions": {
    "wind_mph": 14, "wind_dir_deg": 310, "temp_f": 54, "sky": "overcast",
    "firmness": 0.84, "green_speed": 12.8,
    "weather_state": "overcast",
    "firmness_band": "firm",
    "green_speed_band": "tournament",
    "setup_tier": "major_week",
    "week_no": 7, "week_type": "major",
    "front_probability": 0.15,
    "rough_in": 1.0,
    "fairway_narrow_pct": 10
  },
  "handicap_index": 3.1,
  "target_score": 59
}
```

| New field | Meaning |
|---|---|
| `course.rating` / `course.slope` | The *setup's* rating/slope (§4.3), not the base. Used for the differential (§7.1 of sim-engine). |
| `weather_state` | One of the five states in §1.1. |
| `firmness_band` / `green_speed_band` | The band names from §2.1 / §3.1. |
| `setup_tier` | `daily`, `championship`, `major_week`, or `soft`. |
| `week_no` / `week_type` | The calendar position (§5). |
| `front_probability` | The drawn probability of a mid-round front (§1.2). Stored so the event can be reproduced from the seed. |
| `rough_in` | Extra rough height in inches (0 daily, 0.5 championship, 1.0 major week). Feeds the lie model (§4.2 of sim-engine: heavy-rough rates). |
| `fairway_narrow_pct` | Fairway width reduction in percent (0 except major week: 10). Feeds fairway-hit probability. |

**Mid-round front event:**

```json
{
  "type": "conditions_change",
  "hole": 10,
  "change": "front",
  "wind_mph_before": 6, "wind_mph_after": 12,
  "wind_dir_before": 310, "wind_dir_after": 265,
  "weather_before": "partly_cloudy", "weather_after": "light_rain",
  "commentary": "The front has arrived — the wind has turned and the rain is here. The back nine is a different golf course."
}
```

Emitted at the `hole_start` of the hole where the front arrives (always hole 10, the turn — the front crosses at the turn by design, §1.2).

### 6.2 The broadcast graphics

The conditions bug is a permanent on-screen element (NodeCG, per broadcast-stack §4.4):

```
┌─────────────────────────────────┐
│  54°F  ↗ 14 MPH   STIMP 12.8   │
│  FIRM · MAJOR WEEK              │
└─────────────────────────────────┘
```

- **Contents:** temperature, wind speed + arrow (direction the wind blows *toward*, from the viewer's perspective — the arrow points where the ball will drift), stimp with colour code (§3.4), firmness band, and setup tier (shown only when it is not `daily` — on a daily week the bug reads `FIRM` or `NORMAL` alone, so the screen stays quiet).
- **Placement:** bottom-left, above the ticker. It never overlaps the scorebug (top-left) or the 59 Watch bug (top-right).
- **Updates:** the bug updates on `conditions_change` events (mid-round front) with a 1-second fade. The wind arrow animates with the current gust — a live wind indicator, not a static number.
- **Hole card:** the hole card (§4.4 of broadcast-stack) shows the hole's wind (`hole_wind` from sim-engine §1.2) and the pin difficulty, so the viewer sees the conditions *for this hole*, not just for the round.
- **Rain state:** when `weather_state` is `light_rain` or `storm_cells` (in a rain burst), a small rain icon appears in the conditions bug, and the tracer camera shows the rain-on-lens texture (§1.4).

### 6.3 The commentary

Conditions give the commentary its vocabulary. The prompt system (docs/commentary-prompts.md) already forbids inventing stats; conditions are the facts the voices use:

- **At the open:** the host states the conditions once, in one sentence: "Overcast, 54 degrees, wind out of the northwest at 14 — and the greens are running at 12.8 today, which is major-championship speed." That is the whole conditions briefing. It is not repeated.
- **When conditions change a decision:** the color voice names the mechanism, not just the fact. Not "it's windy" — "into this wind he has to club up and knock it down, or the ball balloons and falls short" (sim-engine §4.3). Not "it's firm" — "this green will not hold a high ball — he has to land it short and let it run on."
- **When the front arrives:** the host announces it once, as a segment break (§1.2). The color voice then re-frames the back nine: "everything you thought you knew about the yardages is wrong now."
- **What the commentary never does:** complain about the weather (it is not an excuse — the conditions are the same for the ghost and the record book), or mention conditions more than twice per hole. The golf is the show; the conditions are the context.

### 6.4 The coins odds

The odds model (docs/coins-economy.md) builds base probabilities from Mas's real rolling stats. Conditions adjust those base probabilities *before* the market opens, and the adjustments are shown on screen (the coins doc's rule: odds teach):

| Market | Daily baseline | Firm | Fast greens | Wind ≥ 12 mph | Major week (all three) |
|---|---|---|---|---|---|
| Fairway hit | 0.58 | 0.58 | 0.58 | 0.52 | 0.52 |
| GIR (approach) | 0.60 | 0.55 | 0.55 | 0.53 | 0.48 |
| Birdie or better (par 4) | 0.24 | 0.22 | 0.20 | 0.19 | 0.16 |
| Birdie or better (par 5) | 0.38 | 0.36 | 0.33 | 0.31 | 0.27 |
| Up-and-down | 0.60 | 0.52 | 0.50 | 0.55 | 0.44 |
| Sand save | 0.50 | 0.44 | 0.42 | 0.47 | 0.38 |
| Make putt (10 ft) | 0.38 | 0.38 | 0.36 | 0.38 | 0.35 |
| Make putt (20 ft) | 0.13 | 0.13 | 0.115 | 0.13 | 0.11 |

Adjustments are multiplicative on the base probability, capped at ±25% (the coins doc's volume-move cap applies to the combined adjustment as well). The market sheet shows the condition adjustment as a line: "Wind 14 mph — birdie odds lengthened." A viewer who watches the conditions bug can predict the odds move before the market opens — that is the game working correctly.

### 6.5 The 59 Watch probability

The 59 Watch bug (broadcast-stack §9) shows a live probability of breaking 60. That probability is computed by **Monte Carlo over the remaining holes, conditioned on the current conditions** — the same physics as the decision engine (sim-engine §5.4), run forward from the current state:

```
P(59 | state, conditions) =
    share of N=500 simulated completions of the remaining holes
    (through the §2 physics, with the current conditions object,
     the current score, and Mas's current form)
    that finish at 59 or better
```

- **N = 500** completions, run once per hole (at `hole_start`), not once per shot — the probability updates hole by hole, not shot by shot, so the bug is stable within a hole and the compute cost is trivial (500 × ~6 holes × ~3 shots × 6k flops ≈ 54M flops ≈ 20 ms, once per hole).
- **Conditions enter through the physics:** wind, firmness, and green speed are already in the §2 pipeline, so the Monte Carlo automatically prices a firm, fast, windy back nine as harder. No separate adjustment is needed — and none is applied. If the probability looks wrong, the physics is wrong, not the probability.
- **Display:** the probability is shown as a whole percent in the 59 Watch bug ("59 PACE · 12%"). Below 1% it shows "<1%". When 59 is mathematically impossible (sim-engine §7.5: `strokes_remaining_vs_59 < 0`), the bug shows "59 GONE" once, then disappears — no dwelling.
- **The honest number:** in major week, the probability at the turn on a good round might be 2%. The broadcast shows 2%. It does not inflate it for drama. The credibility of the 59 Watch is the credibility of the show.

### 6.6 The clip pipeline

Conditions tag every clip (clip-pipeline, per docs/launch-playbook.md §1):

- **Clip metadata** includes `conditions` (weather state, firmness band, green speed band, setup tier, wind). The clip title can use it: "The knockdown that held in 14 mph wind" is a better clip than "nice approach."
- **Drama scoring** (§1.1 of the launch playbook) gets a conditions bonus: a birdie in major week scores +10 drama over the same birdie on a scoring week, because it was harder. A 59-watch moment in major week is automatically drama 90+.
- **The conditions calendar is a content calendar.** Scoring weeks produce birdie clips; championship weeks produce grind clips; major weeks produce survival clips. The 60-day content calendar (docs/content-calendar-60-day.md) is built around the weekly themes — the conditions calendar is what makes those themes real instead of labelled.

---

## 7. Verification checklist

Before any build ships with this system:

- [ ] The calibration harness (sim-engine §3.7) passes within ±5% on all metrics **separately for each setup tier** (daily, championship, major week, soft) — not just on average. If major week does not score 2–3 strokes higher than daily, the setup levers are not wired in.
- [ ] The rating/slope derivation in §4.1 reproduces 74.6 / 138 from the length table and obstacle factors (recompute from the course data, not from the stored constants).
- [ ] A mid-round front (15% of rounds) fires exactly once, at hole 10, and the `conditions_change` event updates the bug, the commentary, and the odds at the same moment.
- [ ] The 59 Watch probability (§6.5) is monotone sensible: it falls when conditions worsen and rises when they improve, and it is 0 when 59 is mathematically impossible.
- [ ] The conditions bug is readable at 320 px wide and does not overlap the scorebug or the 59 Watch bug.
- [ ] Rain on lens never obscures the ball at impact (visual check, 10 rain rounds).
- [ ] The coins odds adjustments in §6.4 match the displayed markets within ±1 percentage point (spot-check 20 markets).

---

## 8. What this document changes in other docs

| Document | Change |
|---|---|
| `sim-engine.md` §1.4 | **No change to existing fields.** The `conditions` object gains the additive fields in §6.1. The green-speed clamp widens from 12.5 to 13.0 **only for major-week rounds** (§3.1, §5.3). |
| `sim-engine.md` §2.5 | Firmness roll multiplier on fairway μ (§2.2) and the release-roll multiplier (§2.2) are new; the base bounce/roll formulas are unchanged. |
| `sim-engine.md` §3.5 | Putting make-rate adjustment already exists; §3.2 tabulates it by band. No formula change. |
| `broadcast-stack.md` §4.4 | Add the conditions bug to the graphics spec (§6.2). |
| `broadcast-stack.md` §9 | 59 Watch probability is now defined by the Monte Carlo in §6.5. |
| `coins-economy.md` | Add the conditions adjustment table (§6.4) to the odds model. |
| `course-design-v2.md` | No change. The rating/slope in §4.1 is derived *from* the v2 design. |
| `qa-plan.md` | Add the per-tier calibration check and the conditions-bug checks (§7). |

---

## Sources

- USGA Course Rating System — effective playing length, obstacle factors, scratch vs. bogey weighting, slope formula `5.381 × (bogey − course)` (usga.org).
- USGA / R&A — Stimpmeter readings and green-speed bands; tournament speeds 12–13 ft (usga.org).
- Mark Broadie, *Every Shot Counts* — strokes-gained framework underlying the per-tier scoring expectations (§4.3).
- Trackman / launch-monitor data — temperature effect on carry (~+0.15 yd per °F on a driver), wind effect on carry (~10–12 yd loss into a 10 mph headwind, ~6–8 yd gain downwind) — carried from sim-engine §2.3.
- Sim-engine §1.4, §2.3–§2.5, §3.5, §7.1, §7.5; broadcast-stack §4.4, §9; course-design-v2 (routing, wind rotation, green complexes); coins-economy.md (odds model); launch-playbook.md §1 (drama scoring).
