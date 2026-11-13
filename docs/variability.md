# Mas Golfs — Performance Variability: Audit & Design

**Status:** audit + design only. No sim code changed. Implementation follows
the flight-model retune. Written Nov 13, 2026.

**The directive (Mason, Nov 13, 2026, ~12:00am EST):** the golfer's
performance needs enough variability to actually be interesting like a real
golfer — ideal golf is boring, but a scratch/+3 can't be that boring or he'd
shoot perfect scores all the time. It's got to be real: the journey from
scratch to breaking 59.

**The one-line verdict:** the sim's round-to-round standard deviation is
already realistic (2.89 strokes, vs ~2.6–3.0 for a real scratch player) —
but the distribution is wrong in the ways that matter for a broadcast. The
low tail is too thin for the 59 chase to ever start, birdies never cluster
into runs, doubles barely exist, and there is no day-to-day form: every
round is drawn from the same machine, so the season is 200 rounds of
66–76 with no story. The fix is not "make him worse" — it is to add the
round-level latent variation real golfers have (form days, putting days,
pressure) while keeping the mean at +3.

---

## 1. What was measured

**Code state:** `sim/` as of Nov 13, 2026, 00:05 EST — post flight-model
refit (`CL_C1 = 2.4, CL_C2 = -4.5`, driver carry fixed), pre flight-model
retune, and **pre v3-course implementation** (see the §8 addendum: v3
landed in `sim/` at 00:22 EST while this audit was running — the §2
numbers are the 7,214-yard v2 course; re-run after the retune + v3
settle).

**Samples:**
- **Monte Carlo (the broadcast path, `mc_n=120`): 20 rounds**, seed
  offset 0, ~33–44 s/round on this VM (872 s total). Small sample — tail
  probabilities are indicative, not precise.
- **Fast rule-based path: 60 rounds**, seed offset 1000 (371 s total).
  The fast path is a *known-bad* decision engine (mean ~81 vs ~74 for MC,
  per `calibrate.py`) — used here only for streak structure and
  distribution shape, never for absolute levels.
- **Per-hole birdie/bogey rates (fast path, v3 course): 60 rounds**,
  seed offset 2000 — see §4.

**Method:** `RoundEngine.play_round()` in sequence (so the learning loop
and the lagging form label evolve exactly as they do in production), then
per-round and per-hole statistics: mean/SD/min/max, sub-70 and 77+
frequencies, doubles/eagles/birdie runs/bogey stretches, alive-at-the-turn
for 59, lag-1 autocorrelation of hole score-to-par, and conditional rates
(P(birdie | previous hole birdie) vs base rate). Run probabilities under
independence were computed exactly by dynamic programming over the
measured per-hole rates.

**Caveats:** n=20 on the MC path means a 0/20 observation has a 95%
upper bound of ~14% — the zeros below are evidence, not proof. The
learning loop mutates the model across rounds, so rounds are not iid;
that is the real behaviour, not a measurement artifact.

---

## 2. Measured distribution (MC, the broadcast path, n=20)

| Metric | Measured (MC) | Real reference |
|---|---|---|
| Scoring mean | **72.4** | +3 on a 74.6-rated course: mean ≈ 72–74 |
| Scoring SD | **2.89** | Scratch ≈ 2.6–3.0 (USGA odds table; see §3) |
| Range | 66–76 | Scratch 20-round sample: 70–79 (caddiehq) |
| P(sub-70) | 20% (4/20) | Scratch: ~25–30% of rounds |
| P(77+) | **0% (0/20)** | Scratch: ~10–15% of rounds |
| P(≤65) | **0% (0/20)** | Rare but real: a scratch player's best in 20 is ~68–70 |
| P(≤62) / P(≤59) | **0 / 0** | See §5 — the core problem |
| Front-9 mean / SD | 36.3 / 2.26 | — |
| Front-9 min | 32 | 59 pace at the turn is 29.5 |
| **On pace at the turn (≤29)** | **0% (0/20)** | The chase never starts |
| **Alive at the turn (≤32)** | **5% (1/20)** | 59 must be reachable at the turn to be a story |
| Doubles / round | **0.2** (1.1% of holes) | Tour field ≈ 2–3% of holes (see honesty note) |
| Eagles / round | **0.0** | Tour elite ≈ 0.1–0.15/round |
| Birdies / round | 3.6 | Scratch ≈ 3–4 |
| Bogeys / round | 3.6 | Scratch ≈ 3–4 |
| Pars / round | 10.6 | — |
| 3-putts / round | 0.7 | Tour ≈ 0.5–0.7 — fine |
| Putts / round | 30.65 ± 2.22 | Scratch 29–32 — fine |
| GIR | 67.3% ± 9 pp | Scratch 65–70% — fine |
| Fairways | 47.5% ± 12 pp | Scratch 60–65% — **low, known calibration FAIL** |

Scores in order: 69, 66, 76, 74, 68, 76, 71, 75, 71, 72, 75, 71, 72, 73,
76, 73, 73, 73, 68, 76. Front nines: 33, 32, 40, 37, 34, 37, 35, 38, 36,
38, 40, 37, 34, 36, 39, 34, 36, 37, 34, 39.

**The fast path (n=60, for shape only):** mean 81.2, SD 5.24, range
73–99, P(77+) = 85%, doubles 1.87/round, birdies 2.12, bogeys 5.72.
The fast path is *too* variable in the wrong way (bad decisions → blow-up
rounds) — it proves the MC decision engine is doing real damage control,
and that decision quality is the sim's main variance suppressor.

### 2.1 The 59 arithmetic

59 is 13.4 strokes below the measured mean (72.4). With SD 2.89 that is
z = −4.6σ → P ≈ 2×10⁻⁶ per round under a normal approximation. Even
allowing fat tails, the front-nine distribution says the same thing from
the other end: the best front nine in 20 rounds was 32 (−4); 59 pace at
the turn is 29.5 (−6.5). A front nine of ≤29 is ~3.2σ below the measured
front-nine mean (36.3 ± 2.26) — roughly 1 round in 1,400.

**The Road to 59, as the sim stands, is a chase that cannot arrive.**
The conditions doc's "~0.5% daily P(59)" was derived from the spec's
assumed distribution, not measured — it is inconsistent with the measured
one by roughly three orders of magnitude. See §5 for what P(59) ≈ 0.3–0.5%
actually requires.

---

## 3. What a real +3 looks like (sourced)

**Round-to-round spread.** The USGA's own odds table (analysed at
[editdistance.dev](https://www.editdistance.dev/posts/your-handicap-is-not-your-average)
over 229,333 real Tour rounds, 2021–2026) puts the score spread at **2.6
strokes for the best players**, rising to 5.3 for a 30-handicap. A
GolfWRX discussion of the same question gives scratch golfers **SD ≈
2.7–3 strokes**. So our measured 2.89 is *already right* — the sim is not
too consistent in the aggregate. The problem is the shape, not the width.

**The WHS identity.** A Handicap Index is the average of the best 8 of
the last 20 differentials, which sits on average **0.93σ below the
player's mean** — the index measures potential, not average. A scratch
player's index flatters them by ~1.9 strokes; a +3's by ~2.4. That is why
a real scratch golfer's 20-round card reads 70–79 with a mean of ~74.2
([caddiehq sample](https://www.caddiehq.com/resources/what-does-a-scratch-golfer-shoot):
75, 71, 74, 73, 78, 72, 74, 76, 70, 75, 74, 77, 73, 72, 79, 74, 71, 75,
73, 74) — good days 68–70, bad days 77–78, and both are completely
normal. **Our sim has the good days (66, 68, 68) but not the bad days
(no 77+ in 20 rounds, max 76).**

**Where round variance comes from.** DataGolf's ShotLink analysis
([datagolf.com/model-talk/variance](https://datagolf.com/model-talk/variance))
finds the standard deviation of SG:APP varies most across rounds,
followed by PUTT, then OTT/ARG — when a round's scores spread out, the
most likely cause is approach-play variance, then putting variance. Only
~25% of round-variance differences are explained by course
characteristics; **~75% is randomness in golfer performance**. That 75%
is what the sim is missing: it has course-driven variance (conditions)
but almost no golfer-driven variance.

**Streakiness: the honest science.** Three studies, one conclusion —
hole-to-hole momentum in real golf is essentially zero:
- Clark (2005): 35 PGA Tour players, 747 tournaments — **no hole-to-hole
  streakiness at all**; after a birdie, a player was just as likely to go
  above par on the next hole as to stay at par or better.
- Urbaczewski & Elmore (Univ. of Denver, 2013–14 ShotLink, 113,723 holes,
  213 players): tested birdie-after-birdie and bogey-after-bogey directly.
- A 2021–22 to 2024 PGA Tour study: a **cold-hand effect exists and is
  statistically significant but small**; **minimal evidence for a hot
  hand** — birdie streaks are largely random variation.

The design implication is sharp: **real birdie runs come from variance,
not momentum.** A viewer watching a real round sees 3-birdie runs because
a 20%-per-hole birdie rate produces them by chance — about 10% of rounds
at a uniform 20% rate (exact dynamic-programming calculation; see §4) —
not because the golfer is "heating up". The sim must produce runs at the
*independent* rate. It currently produces them at a near-zero rate
because its per-hole birdie rates are too low (§4), which is a different
failure from fake momentum — and just as unrealistic.

**Pressure: the Furyk case study.** Jim Furyk's 58 (Aug 7, 2016, TPC
River Highlands, par 70) is the template for what a 59 chase looks like
when it happens: front nine 27 (−8) with a holed wedge for eagle early
and **seven straight birdies (holes 6–12)**, then the back nine 31 (−4)
— the record was built early and *survived* late. Under pressure he
**laid up on the par-5 13th instead of going for the green in two**
(protecting, not pressing), lipped out at 14, watched a birdie try do a
360° lip-out at 15, then birdied 16 from 23'8". He called it "the mental
hurdle" of breaking 60 — a feat Snead (career low 60), Nicklaus (62),
Hogan (62), Palmer (62) and Woods (61) never achieved. Two design
lessons: (1) pressure changes *decisions* (lay up, protect) as much as
execution; (2) a record round is front-loaded — the chase is alive at the
turn or it is not a chase at all.

---

## 4. Gap analysis — where the sim is too boring, mechanism by mechanism

### Gap 1 — No day-to-day form (the biggest gap)
**What exists:** `form` is a lagging label in `handicap.py`
(`form_from_scores`: hot if last-3 ≤ last-10 − 1.5, cold if ≥ +1.5),
with only three states and `FORM_SIG_MULT` hot 0.94 / neutral 1.00 /
cold 1.07, `FORM_PUTT_MULT` hot 1.08 / neutral 1.00 / cold 0.92. It
changes *after* rounds, never *between* them, and it can only react to
scores that already happened. There is no exogenous "today the swing is
off / today everything clicks" draw.
**Why it matters:** shot-level dispersion is iid Gaussian, so 18 holes of
averaging washes it out (central limit theorem). The only round-level
variation is conditions (wind/firmness/green speed). A 65 requires a whole
round of slightly-better shots — a correlated shift — and nothing in the
engine can produce one. This is the main reason the low tail is thin and
P(59) ≈ 0.

### Gap 2 — Birdie runs never happen, because birdie *looks* are too rare
**Measured:** MC max-birdie-run ≥ 3 in **0/20 rounds** (mean max run
1.2); fast path **0/60 rounds** (mean max run 1.05). Lag-1
autocorrelation of hole score-to-par is **−0.12 (MC) / −0.08 (fast)**.
P(birdie | previous hole birdie) = **8.3% vs a 20% base rate (MC, n=72)**
and 9.9% vs 12.1% (fast, n=131).
**Mechanism — confirmed by the per-hole run (fast path, n=60, v3
course):** birdie rates by par are par 5 **15.8%**, par 4 **6.2%**, par 3
**1.7%**. Birdies live on the par 5s (holes 7 and 15 birdie at 21.7% and
23.3%), and par 5s are never adjacent — so a 3-run needs birdies on
three consecutive non-par-5 holes at ~2–10% each. The exact
dynamic-programming calculation settles it: under independence at the
*measured per-hole rates*, P(3+ birdie run) = **0.5% per round** —
expected 0.30 rounds in 60, observed 0. **The sim is not anti-streaky;
it is independence-consistent. The drought is a rate problem, not a
clustering problem.** (For comparison, a uniform 20% birdie rate would
give 10.1% of rounds with a run.) The same test on bogeys: independence
predicts a 3+ bogey run in 73% of rounds, observed 55% — bogeys are, if
anything, slightly *under*-clustered too, consistent with the MC
engine's damage control.
**So the fix is not a momentum mechanic — it is more birdie looks:**
raise the par-4 birdie rate toward ~12–15% (Tour players birdie par 4s
roughly 15–18% of the time) via approach proximity on the short par 4s,
which is the retune step's lever. At par-4 ~13% / par-5 ~25% / par-3
~5%, the independence prediction for a 3+ run rises to ~8–12% of
rounds — runs become a regular feature without faking any momentum.
**Note the contrast:** bogey runs are *not* suppressed (max bogey run ≥3
in 10% of MC rounds, 55% of fast rounds). The sim can grind, it just
can't roll — because it doesn't get enough birdie looks.
**Side finding (fast path only):** the blow-up holes are where the
design intends them — hole 12 ("The Picture", par 3 over water) doubles
at 55%, hole 17 (Road Hole) at 56.7% with an 81.7% bogey rate, hole 14
at 28.3%. The course's teeth are in the right places; the MC engine
just never bites, because it plays them well. That is a decision-quality
story (Gap 6), not a course-design problem.

### Gap 3 — Pressure is display-only, and its one decision effect points the wrong way
**What exists:** `FiftyNineWatch` computes pace and P(break 60) and emits
events — but nothing feeds back into execution. The decision engine's
only record-chase effect is in `decisions.py::risk_threshold`: with ≤3
holes left and within 2 of pace, the hero threshold drops to **0.08
(more aggressive)**; with ≤6 holes left and ≥4 ahead of pace, it rises
to 0.25 (pressing for the comeback). There is no execution effect
(dispersion never changes under pressure) and no *protective* direction:
Furyk laid up on 13 while chasing 59 — the sim would go *more*
aggressive. A chase that reaches the back nine currently plays exactly
like any other round, so it can neither collapse nor be clutched — it
just regresses to the mean, which is why "closest calls" don't exist as
a story.

### Gap 4 — Putting days don't exist
**What exists:** each putt is an independent Bernoulli from the §3.5
make table, with only the lagging form multiplier (0.92–1.08) as a
day-level factor. Putt outcomes within a round are uncorrelated by
construction.
**Why it matters:** DataGolf ranks putting variance as the #2 driver of
round-score variance, and the iconic record rounds are putting stories
(Furyk: 10 putts on the front nine of the 58). The sim's putts/round SD
is 2.22 — respectable — but it comes from binomial noise, not from hot
and cold putting days. There is no round where the putter is white-hot
and no round where nothing drops, so SG:putt never swings a round.

### Gap 5 — Doubles barely exist; recovery is too safe
**Measured:** MC doubles 0.2/round (1.1% of holes), eagles 0.0/round.
The punch-out from trouble is safe by design (`risk = 0.05` in
`fast_ev`; trees only bite via the 5% unplayable rule). The MC engine's
damage control is excellent — that is realistic for a +3 in the sense
that blow-ups are rare, but a season with 0.2 doubles/round has no
"grind" rounds and no 77s. The fast path's 1.87 doubles/round shows the
other extreme: bad decisions, not bad swings, are what create doubles
in this engine — and the MC engine never makes a bad decision.

### Gap 6 — The decision engine never has a human day
**What exists:** the MC engine picks the EV-maximizing candidate every
time, with a fixed risk rule (± conditions ± learning-loop delta). No
stubbornness, no feel plays, no "going for it because the moment demands
it", no conservative day. The learning loop changes aim biases and risk
thresholds slowly across rounds — it is a drift mechanism, not a
variability mechanism. A viewer can never say "Mas is pressing today" or
"Mas is playing safe today", because neither is true.

---

## 5. The P(59) honesty note

The brief's target — P(59) ≈ 0.3–0.5% per round with the mean held at
~72 — is **not achievable under any realistic +3 distribution**. The
real Tour number is ~7 sub-60 rounds in ~1.5 million Tour rounds
(≈0.0005% per round), and a real +3 with SD ≈ 2.9 has P(59) ≈ 10⁻⁶.
To reach 0.3–0.5% with mean 72.4 you need a genuinely fat left tail,
e.g. a mixture: ~90% of rounds from N(73, 2.2) and ~10% from a rare
"everything clicks" state near N(64, 2.5) — mean 72.1, SD ≈ 3.5,
P(59) ≈ 0.23%, P(77+) ≈ 3%. That is a **deliberate broadcast choice,
not WHS realism**: one round in ten, Mas wakes up playing like a +9.
It is defensible — the show needs a 59 to be a real possibility, and a
rare hot state is how every sports broadcast's "career day" works — but
it must be named as entertainment calibration, and the handicap story
must stay honest (the WHS index is best-8-of-20, so a few hot rounds
pull the *index* down without changing the *mean* — exactly how real
handicaps work).

The existing `qa-plan.md` gate R-03 already has the right shape
(≥1 round ≤62 in 10,000, 0–2 rounds ≤59) — that is P(59) ≈ 0–0.02%,
the realistic number. If the 0.3–0.5% target stands, R-03 must be
rewritten to match it, and the v3 course (7,602 yards, scoring band
plausibly 72–74) must be re-baselined first: longer courses push the
mean up ~1 stroke, which pushes 59 further away unless the hot state
gets stronger.

---

## 6. Design proposals (concrete, implementable against the existing sim)

Frozen throughout: per-club dispersion σ (§3.2), physics constants,
calibration targets, course data. Nothing below changes σ — every
proposal works through multipliers, draws, and decision parameters the
spec already allows (form multipliers, risk threshold, baseline table),
or through new *explicit, logged* latent draws that sit alongside σ.
Each proposal states what changes, what stays frozen, the expected
effect, and how to verify it.

### Proposal A — Daily form draw (the main lever) [build #1]
**What changes:** at `round_start`, draw a round-level form state from
an explicit distribution — e.g. cold 12% / neutral 63% / warm 15% /
hot 7% / *zone* 3% — that persists the whole round and is stored on the
round (and emitted in `round_start` so the broadcast can name it: "Mas
woke up striped today"). It drives three existing multipliers, extended
in range: `FORM_SIG_MULT` (delivery dispersion: cold 1.10, neutral 1.00,
warm 0.96, hot 0.92, zone 0.88), `FORM_PUTT_MULT` (cold 0.90, neutral
1.00, warm 1.06, hot 1.12, zone 1.18), and mishit draw rates (thin/chunk
probabilities ×1.3 on cold days, ×0.8 on hot days). The lagging
`form_from_scores` label is *retired as an input* (keep it as a display
diagnostic only) — form becomes exogenous, not reactive.
**Stays frozen:** base σ per club; the multiplier is a separate,
logged factor, exactly as `FORM_SIG_MULT` already is.
**Expected effect:** round-score SD 2.89 → **3.4–3.6**; mean unchanged
(the draw is symmetric around neutral except for the small zone tail);
P(77+) 0% → ~3–5%; P(≤65) 0% → ~1–2%; P(59) via the zone state,
~0.2–0.3% (see §5). Front-nine SD widens so "alive at the turn"
(≤32) goes 5% → ~8–10%.
**Verify:** 1,000-round fast harness (form effects are
decision-independent enough to measure there) + 100-round MC spot
check; distribution gates in §7. The form distribution itself is a
calibration parameter: if the mean drifts, rebalance the draw weights,
never σ.

### Proposal B — Hot/cold putting day [build #2, with A]
**What changes:** a round-level putting latent drawn *with* the form
state (correlated, not identical — a golfer can stripe it and putt
cold): a make-probability multiplier in [0.85, 1.18] applied in
`putting.putt()` (clamped by the existing 0.995 cap) plus a
distance-control factor on `leave_ft` (hot days lag it closer, cold days
leave 6-footers). Emitted on `round_start` as `putting_day` so the booth
can say "the putter is warm today" — and so the audience can *see* the
story before the first putt drops.
**Stays frozen:** the §3.5 make table itself (the marginal make rates
stay the calibration target — the multiplier is mean-1 over the season).
**Expected effect:** putts/round SD 2.22 → **~2.8**; SG:putt becomes the
round's swing variable (DataGolf's #2 variance driver); the "putter is
white-hot" round (Furyk: 10 putts on a front nine) becomes possible.
**Verify:** putts/round distribution gate; SG:putt per-round SD gate;
marginal make rates by distance unchanged within ±2 points over 1,000
rounds.

### Proposal C — Pressure: 59 Watch feeds back [build #3]
**What changes:** the watch state (`on_pace` / `on_the_line` /
`secured` / `gone`, plus `strokes_vs_pace`) feeds two places.
(1) *Decisions:* the risk rule gains a protective direction — when on
pace with 4–9 holes left, the hero threshold **rises** (0.15 → 0.20:
protect the round, Furyk laying up on 13), and only in the last 3 holes
does it fall (0.15 → 0.08: now chase it). When behind pace but alive,
it falls (press). (2) *Execution:* a small pressure multiplier on the
form factor for high-leverage shots only — putts to save par and tee
shots on 17/18 while on pace: dispersion ×1.03–1.05. Pressure *widens*
variance; it does not just cause chokes — the same widening produces
clutch makes, which is why the audience stays.
**Stays frozen:** σ; the pressure multiplier is a bounded, logged
form-factor adjustment, and the risk rule already has a record-chase
branch (`decisions.py::risk_threshold`) — this extends it, it does not
replace it.
**Expected effect:** chases that reach the back nine end in both
directions — some 59s, some 62s that slipped away on 17/18. The
"closest call" becomes a real story instead of a regression to the mean.
**Verify:** in the harness, tag rounds on pace at the turn and report
their finish distribution — P(finish ≤59 | on pace at turn) 10–25%,
P(finish ≥65 | on pace at turn) 25–40%. A chase must sometimes fail.

### Proposal D — More birdie looks (par-4 birdie rate) [build #4, gate + diagnosis]
**What changes:** the per-hole run (§4, Gap 2) confirmed the diagnosis:
birdie rates are par 5 15.8% / par 4 6.2% / par 3 1.7%, and the sim is
already independence-consistent — the drought is a *rate* problem. The
fix is to raise the par-4 birdie rate toward **12–15%** (par-3 toward
~5%) via approach proximity on the short par 4s (the drivable 5th, the
388-yard 14th), which is the retune step's own lever (dispersion
retune, not physics). Add per-hole birdie rates to the calibration
harness output. Do *not* add a momentum multiplier to manufacture runs:
the science (§3) says runs come from variance, and the sim's
independence is something it currently gets right.
**Stays frozen:** physics; the hole routing and pars.
**Expected effect:** at par-4 ~13% / par-5 ~25% / par-3 ~5%, the
independence prediction for a 3+ birdie run rises to ~8–12% of rounds
— runs become a regular feature without faking any momentum.
**Verify:** the independence gate itself — compute the expected run
rate from the measured per-hole birdie rates (exact DP) and compare;
plus the par-4 birdie-rate gate (12–15%).

### Proposal E — Bounded momentum: cold hand first [build #5]
**What changes:** two small, asymmetric effects, both bounded and
reset by a par-or-better. (1) *Cold hand (real, per the 2021–24
study):* after 2+ consecutive bogey-or-worse holes, dispersion ×1.02–
1.03 and the risk rule tightens by 0.02 (protect the round) until a
par-or-better resets it. (2) *Rolling (broadcast, not physics):* after
2+ consecutive birdies, the risk rule loosens slightly (hero threshold
0.15 → 0.12) and the booth gets a "he's feeling it" line — but **no
dispersion tightening**: the runs come from variance (Proposal D), and
we do not fake a hot hand the science says is mostly random.
**Stays frozen:** σ; the momentum state is a transient, logged
multiplier with a hard cap and an automatic reset.
**Expected effect:** bogey runs get slightly longer tails (the grind
rounds get worse, which is the point — bad days must exist); birdie
runs arrive at the independence rate with a narrative attached.
Round-score SD +0.1–0.2 on top of Proposal A.
**Verify:** lag-1 autocorr stays within ±0.05 of 0; P(birdie|birdie)
stays within sampling error of the base rate (no fake hot hand);
P(bogey|bogey) may rise modestly — that is the cold-hand effect, and it
is the one the literature supports.

### Proposal F — Doubles and recovery variance [build #6]
**What changes:** (1) on cold-form days, the mishit table's tail
fattens — toe/heel/shank draw probabilities rise (the table already
has these outcomes; only the draw weights shift). (2) Recovery shots
from trees/rough get a wider outcome distribution: the punch-out is no
longer safe by design (its 0.05 risk is a placeholder for "always fine"
— sometimes it stays in the junk, sometimes it finds the fairway).
(3) Water/OB stays as-is — penalties are already priced by the MC
engine.
**Stays frozen:** σ; the mishit *mechanism* (classify_contact) — only
its draw weights move, and only on cold days.
**Expected effect:** doubles 0.2 → **0.4–0.5/round**; the occasional
77–79; more "grind" rounds; scrambling stays in band (the recovery
variance cuts both ways).
**Verify:** doubles/round gate 0.35–0.60; triple-or-worse rate gate;
scrambling 55–65% (existing target).

### Proposal G — Decision variance: a human day [build #7, last]
**What changes:** a small per-round "aggression" latent drawn with the
form state that shifts the risk threshold ±0.03 (inside the ±0.06 range
the learning loop already uses), and a rare "feel play": ~1–2% of
decisions where the EV gap to the 2nd-best candidate is <0.05 strokes,
take the 2nd-best (a hero ball, a lay-up that costs a shot). Logged in
the `shot_decision` event as `feel_play: true`.
**Stays frozen:** the MC evaluation itself; the EV ranking; σ.
**Expected effect:** more varied round shapes — occasional hero-ball
and occasional over-caution; mean SG unchanged by construction
(EV-neutral: the feel play only fires when the EV gap is negligible).
**Verify:** decision-distribution gate (hero-shot rate, lay-up rate);
mean SG per category unchanged within ±0.05 strokes/round over 1,000
rounds. This is last because it is the smallest effect and the easiest
to get wrong — a "dumb" decision reads as a bug, not a personality.

---

## 7. Ranked build order and calibration gates

**Build order** (each step lands, re-runs the harness, and only then
does the next start — one change at a time, per `self-improvement.md`):
1. **A — daily form draw.** The single biggest lever; unlocks B, C, F, G.
2. **B — hot/cold putting day.** Pairs with A; same draw; DataGolf's #2
   variance driver.
3. **C — pressure (59 Watch feedback).** Needs A first: chases must
   reach the back nine before pressure has anything to act on.
4. **D — more birdie looks.** Gate + diagnosis; the fix itself is
   owned by the retune step (proximity).
5. **E — bounded momentum (cold hand first).** Small, honest, capped.
6. **F — doubles and recovery variance.** Tail texture.
7. **G — decision variance.** Last; smallest effect, most risk of
   reading as a bug.

**Calibration gates** (prove "interesting but still +3" — all measured
on the MC path unless noted; fast-path gates marked F):
| Gate | Target | Was (measured) |
|---|---|---|
| Scoring mean | 71–73 (unchanged) | 72.4 ✓ |
| Scoring SD | **3.2–3.6** | 2.89 |
| P(77+) | 3–7% | 0% |
| P(≤65) | 1–2% | 0% |
| P(≤62) | 0.3–1% | 0% |
| P(59) | 0.1–0.5% (see §5 — needs the zone state; realistic WHS number is ~0.01%) | ~0% |
| On pace at turn (front ≤29) | 1–3% | 0% |
| Alive at turn (front ≤32) | 5–10% | 5% |
| Par-4 birdie rate | 12–15% | ~6% (fast path; MC unmeasured) |
| P(3+ birdie run / round) | within sampling error of independence (target ~8–12% once the par-4 rate lands) | 0% |
| Lag-1 autocorr (hole to par) | −0.05 to +0.05 | −0.12 |
| P(birdie\|birdie) vs base | within sampling error | 8.3% vs 20% |
| Doubles / round | 0.35–0.60 | 0.2 |
| Eagles / round | 0.05–0.15 | 0.0 |
| Putts / round SD | 2.6–3.0 | 2.22 |
| 3-putts / round | 0.5–0.9 | 0.7 ✓ |
| P(finish ≤59 \| on pace at turn) | 10–25% | unmeasured (no chases reached the turn) |
| P(finish ≥65 \| on pace at turn) | 25–40% | unmeasured |
| Handicap index | +2.5 to +3.5 | +3.1 start ✓ |
| Existing §3.1 targets (driving, FW, GIR, scrambling, putts, ball speed) | unchanged | FW 47.5% already FAILs (target 57%) — the retune owns this |

**Re-baseline note:** the v3 course (7,602 yards, `docs/course-design-v3.md`)
shifts the scoring band plausibly to 72–74. When v3 lands in the sim,
re-baseline the mean gate first, then re-derive the tail gates from the
new mean. Do not carry the 71–73 band onto a longer course.

---

## 8. What I could not measure or verify

- **Tail probabilities precisely.** n=20 on the MC path means every
  0/20 above has a 95% upper bound of ~14%. The zeros are strong
  evidence (especially 0 birdie runs in 80 rounds across both paths),
  but P(59) and P(≤62) need the 1,000-round harness — which, on the MC
  path at ~35–45 s/round on this VM, is a ~10-hour job. The fast path
  cannot substitute (it measures a different decision engine).
- **Tour double-bogey rate.** No Tour double-or-worse per-hole rate was
  verified from a primary source in this session; the "≈2–3% of holes"
  figure is a field-average approximation. The doubles gate in §7 should
  be set against a sourced ShotLink number before implementation.
- **The birdie-run mechanism — CONFIRMED.** The per-hole run (fast path,
  n=60, v3 course) confirmed birdies concentrate on par 5s (15.8% vs
  6.2% par 4, 1.7% par 3), and the exact DP calculation shows the sim
  is independence-consistent (P(3+ run) = 0.5% at the measured rates;
  expected 0.30 in 60 rounds, observed 0). The drought is a *rate*
  problem, not a clustering problem. The MC-path per-hole rates were not
  measured (MC is ~35 s/round) — the par-4 birdie-rate gate in §7 should
  be measured on the MC path before Proposal D's fix is judged.
- **The flight-model retune and v3 course in progress.** A retune agent
  is working on `sim/` concurrently, and the v3 course (7,602 yards,
  semi-rough lie) landed in `sim/course.py`, `sim/constants.py` and
  `sim/decisions.py` at 00:22 EST, mid-audit. A separate readiness audit
  (Nov 13, ~00:21 EST) found the sim broken at that moment — `KeyError
  'semi'`, the v3 semi-rough lie missing its `LIE_EFFECTS` entry; the
  entry (`dist 0.97, spin 0.95, sig 1.15`, to-be-confirmed) is present
  in the tree now, so the fix appears to have landed since. The §2
  numbers are a snapshot of the pre-v3, post-refit code as of Nov 13,
  00:05 EST — **re-run §2 on the settled code before implementing
  anything in §6.**
- **Real +3 (not scratch) distributions.** The sourced numbers above
  are mostly for scratch (0.0) and Tour players. A +3's distribution is
  a scratch distribution shifted ~2–3 strokes better with a slightly
  tighter spread — no published +3-specific round-to-round SD was found.
  The gates in §7 are set from the scratch numbers plus the sim's own
  measured baseline, which is the honest basis available.
- **Putting make-rate tables vs the sim's.** The sim's §3.5 table was
  not re-derived against Tour make rates in this audit; Proposal B
  assumes the table is right and only adds a day-level multiplier.
