# Mas Golfs — Self-Improvement System

**The promise:** Mas gets better fully autonomously, forever, without a human
touching a dial. He does not get better by hitting it further or straighter —
he gets better by getting *smarter*. The system is a measured learning loop
on top of the simulation engine, and this document is the complete design for
it: what is kept, what is allowed to change, how a real weakness is told
apart from noise, how improvement is paced, how it is shown to viewers, and
how it is prevented from breaking the show.

**Reference docs:** `sim-engine.md` (§3 calibration, §5 decision engine,
§6 learning loop, §7 handicap and form), `qa-plan.md` (§1 calibration
harness, §1.5 the 59 check, L-05 improvement cap), `broadcast-stack.md`
(§3 NodeCG graphics, §4 commentary), `coins-economy.md` (§5 odds).

**Design principles:**

1. **Improvement is decision improvement, not swing improvement.** Mas's
   dispersion (σ) never changes. He learns where to aim, when to club up,
   when to take the safe line. A viewer who watches for a month should be
   able to say *what* he learned, not just that his score went down.
2. **Improvement is slow, visible, and non-monotonic.** The QA cap is
   0.0–1.5 strokes over 200 rounds (qa-plan L-05). Form slumps are real and
   frequent. A straight line down would be boring television and bad golf.
3. **One fix at a time, always.** Exactly one active fix, exactly one
   learning signal per round. A data dump is not training.
4. **The system must be auditable.** Every change to the golfer model is
   logged with the evidence that caused it. If it isn't written down, it
   didn't happen (qa-plan appendix).

---

## 1. Learning architecture

### 1.1 The two stores

The system keeps exactly two persistent stores. Nothing else is learned
from; nothing else is written to.

| Store | Contents | Written by | Read by |
|---|---|---|---|
| **Round store** | Every completed round: full shot-by-shot event log (the same JSON events the broadcast emits, `sim-engine.md` §1), per-category strokes-gained totals, score, conditions (wind, firmness, pin), and the active fix at the time. Append-only. Never edited, never deleted within a season. | The round loop, at `round_complete`. | The learning loop, the handicap/leaderboard aggregates, the QA harness. |
| **Golfer model** | The mutable parameters the learning loop is allowed to change (§1.3), plus metadata: fix history (every fix ever applied, with its evidence and outcome), the current form state, and the season counters. Versioned — every write bumps a version number and appends to a change log. | The learning loop, once per round, at `LEARNING_LOOP`. | The decision engine (every shot), the broadcast (ONE FIX line), the odds engine. |

The round loop state machine (`sim-engine.md` §8.1) already has the
`LEARNING_LOOP` step between `ROUND_COMPLETE` and the next `ROUND_START`.
This document specifies what happens inside that step.

### 1.2 What data is kept (and for how long)

| Data | Retention | Why |
|---|---|---|
| Shot-level events (all shots, all rounds) | Whole season | Strokes-gained by sub-bucket needs shot-level history; the QA harness replays it. |
| Per-round category SG totals (`ott` / `app` / `arg` / `putt`) | Whole season | The primary learning signal and the season trend line. |
| Fix history (fix, evidence, outcome) | Whole season + archived across seasons | The learning arc *is* the story; past seasons' fixes are the "what he worked on" record. |
| Handicap index after every round | Whole season | The season arc in one number. |
| Form inputs (last-3 and last-10 scoring averages) | Rolling window only | Derived at `round_complete`; the raw rounds behind them are in the round store anyway. |
| Conditions per round (wind, temp, firmness, green speed, pin) | Whole season | A weakness that only appears in wind is a different fix from one that appears in calm. The loop must not "fix" a wind problem on a calm week. |

Storage cost is trivial: a round is ~70–90 shots, each event a few hundred
bytes. A 200-round season is a few megabytes. Keep it in the same store as
the round store (SQLite in the reference implementation); there is no reason
to build a separate analytics pipeline.

### 1.3 What is allowed to change vs. what never changes

This is the load-bearing table of the whole system. It is identical in
substance to `sim-engine.md` §6.4, extended with the limits this document
adds.

**Allowed to change (the golfer model):**

| Component | What changes | Hard limits |
|---|---|---|
| Aim biases | Per-distance-bucket aim offsets, in feet, toward the corrected miss. | ±12 ft per bucket, cumulative. A single fix may move a bucket at most 7 ft. |
| Risk threshold | The §5.3 hero-shot threshold. | Baseline ±0.09 total, in steps of 0.03. (Three steps in either direction, ever.) |
| Baseline table | §5.5 strokes-to-hole-out expectations, per bucket. | ±0.05 strokes per bucket, adjusted only from the last 20 rounds of observed performance. |
| Trajectory preference | Which trajectory the decision engine defaults to in a given situation (e.g. knockdown into wind). | Only via the `trajectory` fix mechanism; only one situation at a time. |

**Never changes:**

| Component | Why it is frozen |
|---|---|
| Dispersion σ values (`sim-engine.md` §3.2) | Mas does not get a tighter swing from thinking about it. Changing σ would silently re-calibrate the whole engine and break every benchmark in qa-plan §1. |
| Physics constants (§2.3: gravity, drag, Magnus, air density) | Physics is physics. The world does not get easier because Mas practiced. |
| Calibration targets (§3.1: the +3 benchmark table) | The targets are the measuring stick. Moving the stick is cheating. |
| Course data (Wyatt National yardages, pars, ratings) | The course is the fixed exam. Mas improves against it; it does not shrink for him. |
| The one-fix rule itself | One active fix, always. The loop may not stack fixes, even when two areas look bad at once. |

**The one deliberate exception — the "practice" mechanism (v2, not v1).**
`sim-engine.md` §6.4 already names it: a separate, slower mechanism that
tightens σ by 1% per 20 rounds, capped at 5% total. It is **not** part of
v1.0 and must not be implemented by accident. When it is eventually built,
it is a *different* system with its own log, its own cap, and its own
broadcast line ("Mas's swing is 2% tighter than in April"), and it must
re-run the full qa-plan §1 calibration harness before it ships. Until then,
any proposal that tightens σ is rejected at review.

### 1.4 The learning loop's inputs and outputs

Per round, at `LEARNING_LOOP`:

**Inputs:**
- The just-completed round's per-category SG totals and shot log.
- The rolling windows: last 5 rounds (fix detection), last 20 rounds
  (baseline-table adjustment), last 10 rounds (form).
- The current golfer model (aim biases, risk threshold, baseline table).
- The current active fix and its age (rounds since applied).
- The season counters (round number, rounds remaining, season phase).

**Outputs (exactly one of these per round):**
- A new fix (replacing the old one), **or**
- The current fix marked `working` / `escalated` / `retired`, **or**
- No change (`no_fix` — see §4.4 for when the loop deliberately does
  nothing).

**Side effects (always):**
- The golfer-model change log is appended (fix applied / escalated /
  retired / no change, with the evidence).
- The `round_start` event for the next round carries `focus_fix` (the
  active fix or `null`).
- The odds engine (`coins-economy.md` §5) is notified, because a fix that
  improves approach play changes the base probabilities for GIR markets.

---

## 2. The improvement ladder over a season

### 2.1 Where Mas starts, and where he can go

Mas starts at **+3.1** (display index; `sim-engine.md` §7.1). His scoring
average over the first 20 rounds should sit at **72–74** on a par-72
course rated TBD / slope TBD (v3 recompute pending — see `conditions-system.md` §4.1; the recompute must produce one rating/slope used everywhere, replacing both v1 pairs). **The 72–74 band is a v3 estimate, pending confirmation by the 10,000-round harness** (`course-design-v3.md` §5.3) — and so is every rung of the ladder below, which is the same band shifted by the improvement budget.

The ladder is defined by scoring average and handicap, not by any single
round. A season is 200 rounds for ladder purposes (the qa-plan L-05 window).

| Rung | Scoring average (last-20) | Display handicap | What changed to get here | Broadcast framing |
|---|---|---|---|---|
| 0 — **The baseline** | 72.5–73.5 | +3.1 | — | "Mas, the +3." |
| 1 — **Smarter, not longer** | 72.0–73.0 | +3.5 | Aim biases corrected on the worst 2–3 approach buckets; one or two bad misses removed. | "He's stopped missing left." |
| 2 — **The aggressive line** | 71.5–72.5 | +4.0 | Baseline table improved on scrambling; risk threshold nudged up one step where the data earned it. | "He's taking lines he wouldn't have taken in April." |
| 3 — **Plus-four territory** | 71.0–72.0 | +4.5 | Compounded fixes across approach + driving; the worst category is no longer a weakness, just the least-strong area. | "Mas is a +4 now. The number moved." |
| 4 — **The ceiling** | 70.5–71.5 | +5.0 | The practical ceiling of decision-only improvement. Further gains need the v2 practice mechanism. | "This is what a +5 looks like when the swing never changed." |

**The ladder is a description of what the loop is allowed to produce, not
a schedule.** Mas may sit on rung 1 for 80 rounds, jump to rung 2 in a hot
month, and fall back to rung 0 in a cold one. The loop never targets a rung
directly; it only ever fixes the worst sub-bucket. The rungs emerge.

### 2.2 The improvement budget

The total budget is the qa-plan L-05 cap: **scoring average over rounds
180–200 improves by 0.0–1.5 strokes vs. rounds 1–20**. That is the whole
season's improvement, and it is small on purpose. It decomposes as:

| Source | Expected contribution | Mechanism |
|---|---|---|
| Aim-bias corrections | 0.5–0.9 strokes | Removing systematic misses in the worst approach buckets. |
| Risk-threshold correction | 0.1–0.3 strokes | Fewer hero shots that lose strokes; more aggression where the data earned it. |
| Baseline-table adaptation | 0.1–0.3 strokes | Better expectations → better lines. |
| **Total** | **0.7–1.5 strokes** | |

If the measured improvement after 200 rounds is **above 1.5 strokes**,
the loop is overpowered and the season is invalid (qa-plan L-05 FAIL).
If it is **below 0.0** (he got worse), something is broken — the loop
must never make Mas worse on purpose, and a worsening trend is a bug,
not a storyline (`sim-engine.md` §6.5).

### 2.3 How a fix turns into strokes

A single fix is worth, on average, **0.1–0.4 strokes per round** in its
category — and only while the weakness it addresses is actually present.
Worked example from `sim-engine.md` §6.3: Mas loses 0.42 strokes/round
on 150–175 yd approaches, missing 68% left. The fix aims 4 ft right.
If the miss pattern corrects, the category recovers ~0.3–0.4 strokes/round.
That is a real, visible improvement — and it is also small enough that a
viewer can watch it happen over a week rather than overnight.

**Fixes do not stack into a super-golfer.** Because only one fix is active
at a time and each fix addresses one sub-bucket, the marginal gain of each
successive fix shrinks: the worst weakness gets fixed first (biggest gain),
the next-worst is smaller, and so on. This diminishing return is what keeps
the 1.5-stroke cap honest without any extra governor.

### 2.4 The season arc in numbers

A healthy season looks like this (scoring average, 20-round rolling):

```
Round   1-20:  73.1  (baseline, +3.1)
Round  21-60:  72.8  (first fixes land; aim biases correcting)
Round  61-100: 72.4 (rung 1; the worst miss is gone)
Round 101-140: 72.6  (cold stretch — see §3; the average ticks back up)
Round 141-180: 72.0  (rung 2; recovery + second wave of fixes)
Round 181-200: 71.8  (rung 2/3; season improvement ~1.3 strokes)
```

*(v3: every number above is the v1 arc shifted +1.0 stroke for the 7,602-yard course — an estimate, pending the 10,000-round harness. The shape is the point — down, up, down again — not the decimals.)*

The line goes down, up, and down again. That is the design. A season
whose rolling average is monotone decreasing is a system failure, not a
success — it means form modulation is not working or the loop is
overpowered.

---

## 3. Form: slumps and recoveries

### 3.1 Why form exists

If improvement were a straight line, there would be no drama, no
Road to 59 tension, and no reason to watch on a Tuesday. Real golfers —
including plus handicaps — have hot and cold stretches that have nothing
to do with what they are working on. The form system (`sim-engine.md`
§3.6, §7.4) is what creates them, and it is deliberately *separate* from
the learning loop: form is weather, the loop is climate.

### 3.2 The form model

Form is **derived, never set** (`sim-engine.md` §7.4):

```
last3_avg  = mean score of last 3 rounds
last10_avg = mean score of last 10 rounds
if last3_avg <= last10_avg - 1.5: form = "hot"
elif last3_avg >= last10_avg + 1.5: form = "cold"
else: form = "neutral"
```

Form modulates dispersion slightly (enough to create hot and cold
stretches, not enough to break calibration) and drives commentary tone.
It is recomputed at every `round_complete`.

**The important subtlety:** form is computed from *scores*, and scores
are affected by the learning loop. As Mas improves, his last-10 average
falls, which raises the bar for "hot" and lowers the bar for "cold."
That is correct and intended — a +4's cold stretch is a better golfer's
cold stretch, and the broadcast should say so ("He's cold *for him*").

### 3.3 What a slump looks like, and how long it lasts

| Form state | Typical duration | Scoring effect | What the viewer sees |
|---|---|---|---|
| `hot` | 3–8 rounds | 1.0–2.0 strokes better than the rolling average | Birdie runs, 59 Watch turning on, commentary leaning in. The best clip material of the season. |
| `neutral` | 5–15 rounds | Within ±1.0 strokes of the rolling average | The normal show. Fixes land or don't, quietly. |
| `cold` | 3–8 rounds | 1.0–2.0 strokes worse than the rolling average | Missed greens, short putts lipping out, the ONE FIX line getting harder questions. The most relatable material of the season. |

**Rules:**

- A cold stretch is never "fixed" by the learning loop. The loop fixes
  *systematic* weaknesses (a miss pattern in a bucket over 5 rounds);
  a cold stretch is *variance* across all buckets. If the loop tries to
  fix a cold stretch, it is chasing noise (§4).
- A cold stretch does not pause the learning loop. Fixes still apply, and
  their effect is measured *after* the cold stretch ends — the loop
  compares the bucket's SG before the fix vs. after, over 3-round windows
  on either side, so a cold stretch in the middle does not falsely mark a
  fix as failed.
- The broadcast must never claim a slump is caused by the fix, or that a
  hot stretch proves the fix worked. The commentary line for a cold
  stretch is "form," not "the fix isn't working." The learning arc is
  told in the Record Book and the ONE FIX line, not in single-round
  commentary.

### 3.4 Recoveries

A recovery is not a fix. It is form returning to neutral or hot after a
cold stretch, which happens on its own as the last-3 window rolls forward.
The learning loop's contribution to a recovery is indirect: if a real
weakness was fixed *during* the cold stretch, the recovery lands on a
slightly better baseline, and the post-recovery rolling average is lower
than the pre-slump one. That is the mechanism by which improvement
survives a slump — and it is the only mechanism. There is no "bounce-back
bonus," no form reset, no intervention.

**The storyline rule:** a recovery is narrated as Mas *playing through
it*, never as the system rescuing him. The show is about a golfer
learning, not about a machine tuning a golfer.

---

## 4. Detecting a real weakness vs. noise

This is the section that keeps the system honest. Most "insights" from
small samples are noise, and a loop that acts on noise will oscillate,
contradict itself, and eventually make Mas worse.

### 4.1 Minimum sample sizes

| Level | Minimum sample | Window |
|---|---|---|
| Category (e.g. `app`) | 3 rounds with ≥ 5 shots in the category | Last 5 rounds |
| Sub-bucket (e.g. `app` 150–175 yd) | 3 shots in the bucket | Last 5 rounds |
| Miss-direction claim (e.g. "68% left") | 10 shots in the bucket | Last 5 rounds |
| Baseline-table adjustment | 20 rounds | Last 20 rounds |
| Fix outcome verdict (working / not working) | 3 rounds *after* the fix | The 3 rounds following application |

**No fix is ever produced from a single round.** `sim-engine.md` §6.5
states this as a never-do, and this document makes it a hard gate in the
algorithm (§5, step 3). A single round can produce a *candidate* — a
bucket flagged for watching — but a candidate is not a fix.

### 4.2 Confidence thresholds

A sub-bucket becomes a fix candidate only if **all** of these hold:

1. **Magnitude:** the bucket is losing ≥ 0.25 strokes/round (SG per round
   in that bucket, averaged over the last 5 rounds). Below 0.25, the loss
   is within the noise floor of the category.
2. **Consistency:** the bucket is negative in at least 3 of the last 5
   rounds. A bucket that is −0.8 in one round and +0.1 in the other four
   is one bad round, not a weakness.
3. **Direction (for aim fixes):** the miss pattern is directional — ≥ 60%
   of misses in the bucket fall on the same side (left/right, long/short).
   A bucket with misses scattered in all directions is a dispersion
   problem, and dispersion is frozen (§1.3). There is nothing to fix
   there, and the loop must say so.
4. **Separation:** the bucket is at least 0.15 strokes/round worse than
   the next-worst candidate bucket. If two buckets are within 0.15 of each
   other, the loop picks the one with the larger sample; if still tied, it
   picks the one whose fix mechanism is cheapest (aim offset before club
   up before trajectory). Ties are broken by rule, never at random, so the
   loop is deterministic given the same history.

### 4.3 The noise floor

Every category has a noise floor — the SG swing you would expect from
pure variance with no systematic weakness at all. The loop must know it,
or it will "fix" randomness.

| Category | Noise floor (SG/round, 5-round window) |
|---|---|
| `ott` | ±0.20 |
| `app` | ±0.25 |
| `arg` | ±0.20 |
| `putt` | ±0.30 |

These are derived from the dispersion model, not guessed: simulate 10,000
rounds with the learning loop disabled and measure the 5-round SG spread
per category. The floor is the 90th percentile of that spread. If a
category's 5-round SG is inside its floor, there is no weakness to fix in
that category, whatever the raw number says.

**Putting deserves a special note.** Putting has the widest noise floor
(±0.30) and the smallest real improvement available (~15% of the gap,
`sim-engine.md` §6.1). The loop will therefore almost never produce a
putting fix — and that is correct. A system that "fixes" putting every
other week is a system that does not understand golf. When a putting fix
*is* produced, it is a significant event and the broadcast should treat
it as one.

### 4.4 When the loop deliberately does nothing

`no_fix` is a valid and common output. The loop produces no new fix when:

- No bucket clears all four thresholds in §4.2 (the usual case — most
  rounds end in `no_fix`, and the current fix simply continues).
- The current fix is less than 3 rounds old (it has not had its verdict
  window yet — see §5, step 2).
- The worst bucket's problem is dispersion, not direction (§4.2.3) — there
  is nothing to fix, and the loop logs `no_actionable_weakness` rather
  than inventing one.
- It is the first 3 rounds of a season (insufficient history — the loop
  watches and accumulates, and the broadcast says "establishing" rather
  than pretending to know).

A `no_fix` round is not a failure of the system. It is the system working:
the golfer is either already well-tuned in every bucket, or the data is
not yet strong enough to act on. The broadcast's ONE FIX line simply
carries the current fix forward, and the Record Book shows the streak of
rounds since the last new fix.

---

## 5. The "one fix" selection algorithm

This is the complete algorithm, as the learning loop runs it at every
`LEARNING_LOOP` step. It is deterministic: same round store, same output.

```
LEARNING_LOOP(round R):
  1. COMPUTE per-category and per-sub-bucket SG over the last 5 rounds
     (from the round store; R-4 .. R).

  2. VERDICT on the current active fix (if any):
     a. If the fix is < 3 rounds old: verdict = "pending"; skip to step 6.
     b. Else, compare the target bucket's SG in the 3 rounds before the
        fix vs. the 3 rounds after it:
        - improved by >= 0.15 strokes/round → verdict = "working"
        - changed by < 0.15 in either direction → verdict = "no_effect"
        - worsened by >= 0.15 → verdict = "harmful" (should be ~impossible;
          if it happens, log it loudly — it means a bug, not a bad fix)
     c. If verdict is "working": mark the fix in the fix history as
        resolved; the bucket's aim bias / threshold change STAYS in the
        golfer model (fixes are permanent — see §5.1). Proceed to step 3
        to find the next fix.
     d. If verdict is "no_effect": escalate (§5.2). Proceed to step 3
        only if the escalation produces a different fix; otherwise the
        escalated fix remains active and the loop ends for this round.
     e. If verdict is "harmful": revert the fix's parameter change,
        mark it "reverted" in the history, and proceed to step 3.

  3. FIND candidates:
     a. For each category, for each sub-bucket: compute SG/round over the
        last 5 rounds.
     b. Discard any bucket with < 3 shots in the window (§4.1).
     c. Discard any bucket whose SG/round is > -0.25 (inside the noise
        floor, §4.3).
     d. Discard any bucket negative in < 3 of the last 5 rounds (§4.2.2).
     e. Rank the survivors by SG/round, worst first.

  4. SELECT the fix:
     a. Take the worst surviving bucket.
     b. If the top two buckets are within 0.15 strokes/round, apply the
        tie-breaks in §4.2.4 (larger sample, then cheapest mechanism).
     c. Determine the mechanism from the bucket's evidence:
        - Directional miss (>= 60% one side) → "aim_offset_ft",
          magnitude = 4 ft (first application) toward the correction.
        - Short on distance (approaches consistently short) → "club_up".
        - Wind-related losses (>= 15 mph headwind rounds) → "trajectory"
          (knockdown).
        - Pin-hunting losses (missing long / above the hole) → "target_line"
          (aim at the fat of the green).
        - Hero-shot losses (aggressive lines losing strokes) → "aggression"
          (threshold -0.03).
     d. If no candidate survives: output "no_fix" (see §4.4). End.

  5. APPLY the fix:
     a. Write the parameter change into the golfer model (aim bias,
        threshold, trajectory preference, or baseline-table note).
     b. Append to the change log: fix object (the §6.3 format from
        sim-engine.md), the evidence (bucket SG, sample size, miss
        direction %), and the expected gain.
     c. Set the fix as the single active fix. The previous fix, if any,
        is marked "resolved" or "superseded" in the history — its
        parameter change REMAINS in the model (§5.1).
     d. Emit the fix in the next round's `round_start.focus_fix`.

  6. BASELINE-TABLE maintenance (every round, independent of fixes):
     a. If >= 20 rounds of history exist, recompute the §5.5 baseline
        expectations per bucket from observed performance.
     b. Adjust any bucket by at most ±0.05 strokes, and only if the
        observed value differs from the stored value by >= 0.10 (dead
        band — do not chase 0.06-stroke wobbles).
     c. Log the adjustment. Baseline changes are not "fixes" and do not
        appear on the ONE FIX line; they appear in the Record Book as
        "the book on Mas."
```

### 5.1 Fixes are permanent (the ratchet)

When a fix is resolved or superseded, its parameter change **stays** in
the golfer model. The aim bias that corrected a left miss does not
revert when the loop moves on to driving. This is the ratchet that makes
improvement cumulative: each fix locks in a small permanent gain, and the
next fix works from the improved baseline.

The only exceptions are:
- A fix verdict of `harmful` (§5 step 2e) — reverted immediately.
- A season reset (§8) — the model is archived, not carried forward
  wholesale (see §8.2 for exactly what survives).

### 5.2 Escalation

If a fix has had its 3-round verdict window and shows `no_effect`, the
loop escalates rather than abandoning the bucket — the weakness is real
(it cleared the thresholds), so the fix was too weak or the wrong
mechanism:

| Escalation step | What changes |
|---|---|
| 1st | Magnitude increases: aim offset 4 ft → 7 ft. |
| 2nd | Mechanism switches: aim → `club_up` (or `trajectory`, whichever the evidence supports). |
| 3rd | The bucket is marked `resistant` and the loop moves on to the next-worst bucket. The resistant bucket is revisited only after 10 rounds, and only if it is still the worst bucket by ≥ 0.30 strokes/round. |

A bucket can be escalated at most twice. The third step is the loop
admitting that this particular weakness is not fixable by decision
changes — which is itself useful information, and the broadcast can say
so honestly ("The 150-yard shot is still his nemesis").

---

## 6. How improvement is surfaced to viewers

Improvement that nobody can see is not a storyline. The system surfaces
it in four places, all driven by the same golfer-model data — never by a
separate "narrative" layer that could drift from the truth.

### 6.1 The ONE FIX line

The single most important surfacing element. It appears on:

- **The scorebug / player card** (broadcast-stack §3): "ONE FIX: Aim 4 ft
  right on 150–175 yd approaches." One line, always current, always the
  active fix. It changes only when the loop produces a new fix — never
  mid-round, never for commentary convenience.
- **The leaderboard / Record Book**: the active fix plus the count of
  rounds since it was applied, and its status (`working` / `pending` /
  `escalated`).
- **The round-start card**: each round opens with the fix, so a viewer
  joining mid-season immediately knows what Mas is working on.

**Rules for the line:**
- It states the fix in plain golf language, never in parameter language.
  "Aim 4 ft right on 150–175" — not "aim_offset_ft magnitude 4."
- It states the *finding* alongside the fix at least once per round
  (usually on the round-start card): "Losing 0.42 strokes/round on
  150–175 approaches, missing 68% left."
- When a fix is resolved, the line does not disappear — it is replaced by
  the next fix, and the resolved one moves to the Record Book's "fixed"
  list. The viewer should always be able to answer "what is he working
  on right now?"

### 6.2 The learning arc as a storyline

The season is told as a learning arc, in three acts that the system
produces automatically from the fix history:

| Act | When | What the broadcast says |
|---|---|---|
| **Act 1 — The diagnosis** | Rounds 1–20 | "We're learning what Mas's game actually is." The fix history is short; the ONE FIX line changes often as the loop finds the real weaknesses. The storyline is discovery. |
| **Act 2 — The work** | Rounds 21–120 | "He's fixing it, one thing at a time." Fixes resolve, new ones appear, the handicap ticks down. The storyline is grind: the rolling average falls in fits and starts, cold stretches interrupt it, recoveries land on better baselines. |
| **Act 3 — The ceiling** | Rounds 121–200 | "How good can decisions alone make him?" The worst buckets are now small; fixes are subtler (a trajectory preference, a risk-threshold step). The storyline is the approach to the ceiling — and the open question of what the v2 practice mechanism would unlock. |

The commentary system (`broadcast-stack.md` §4) is fed the act, the
active fix, and the fix history — so the color commentator can say "he's
been working on the 150-yard shot for three weeks and it's finally
holding" because it is *true*, not because a writer wrote it.

### 6.3 The numbers viewers follow

| Number | Where it lives | What it means |
|---|---|---|
| Handicap index (+3.1 → +5.0) | Scorebug, player card, Record Book | The season arc in one number. Moves once per round. |
| Last-10 scoring average | Leaderboard, Record Book | The form line. The number that moves week to week. |
| Fix count (resolved / active / resistant) | Record Book | "He's fixed 7 things this season." The learning arc, counted. |
| Category SG trend (sparkline per category) | Record Book | Which part of the game is actually improving, and which is flat. |
| Strokes from 59 | Scorebug, 59 Watch | The chase. Improvement makes 59 more plausible; the 59 check (§7) keeps it rare. |

### 6.4 What the system never says

- Never "Mas is getting better every round." He is not. Say what
  improved, by how much, and in which bucket.
- Never attribute a hot round to a fix, or a cold round to a fix failing.
  Fixes are measured over 3-round windows; single rounds are variance.
- Never promise a rung ("He'll be +4 by June"). The ladder (§2.1) is a
  description of what the loop can produce, not a schedule.
- Never hide a `no_fix` round. If the loop found nothing actionable, the
  ONE FIX line carries the current fix and the Record Book shows the
  streak. Honesty about "nothing to fix this week" is part of the
  credibility.

---

## 7. Safeguards against runaway improvement

The nightmare scenario is a loop that compounds until Mas shoots 65 every
round, 59 becomes routine, and the show dies. These safeguards make that
structurally impossible in v1.0.

### 7.1 The structural safeguards (no governor needed)

| Safeguard | How it works |
|---|---|
| **σ is frozen** (§1.3) | The swing never tightens. The single biggest lever on scoring is off the table, so improvement is capped by what decisions alone can do — and decisions alone are worth ~1.5 strokes (qa-plan L-05). |
| **One fix at a time** | Fixes cannot compound in parallel. Each fix addresses one bucket; the marginal gain shrinks as the worst buckets are fixed. |
| **Diminishing returns are built in** | The worst weakness is fixed first (biggest gain). The second fix is smaller, the third smaller still. The improvement curve is concave by construction. |
| **Hard parameter caps** (§1.3) | Aim ±12 ft, risk threshold ±0.09, baseline ±0.05. Even if the loop wanted to, it cannot push a parameter past its cap. |
| **Escalation dead-ends** (§5.2) | A resistant bucket is abandoned after two escalations. The loop cannot keep hammering one bucket forever. |

### 7.2 The monitoring safeguards (alarms, not governors)

Run these checks after every 20 rounds, automatically, as part of the
calibration harness (qa-plan §1):

| Check | Threshold | Action if breached |
|---|---|---|
| Season improvement vs. L-05 cap | > 1.5 strokes over 200 rounds (projected) | **Halt the loop.** Freeze the golfer model, log the breach, and require a human review before the loop resumes. This is a system failure, not a tuning opportunity. |
| 59 frequency | > 2 rounds ≤ 59 in any 10,000-round window, or any 59 in the first 50 rounds of a season | **Halt and investigate.** A 59 in the first 50 rounds means the calibration is wrong, not that Mas is a genius (qa-plan §1.5). |
| Best-round sanity | Any round ≤ 62 in the first 20 rounds | Flag for review. Possible in principle (R-01 requires ≥ 1 round ≤ 62 in 10,000), but in the first 20 rounds it is suspicious. |
| Fix churn | > 1 new fix per 2 rounds over any 20-round window | The loop is chasing noise. Halt, review the thresholds in §4.2, and re-run the noise-floor derivation (§4.3). |
| Category SG drift | Any category's 20-round SG moves by > 1.0 stroke in either direction | The baseline table or a fix is misbehaving. Halt and review. |

**"Halt" means:** the learning loop stops producing new fixes. The golfer
model freezes at its current state. The broadcast continues with the
frozen model (the show does not stop), and the ONE FIX line shows the last
active fix with a "reviewing" marker. A halt is visible in the change log
and in the Record Book. It is never silent.

### 7.3 The 59 check, restated for this system

From qa-plan §1.5, as it constrains the learning loop specifically:

- 59 must be **possible**: in 10,000 simulated rounds, at least one round
  scores ≤ 62 (the engine can produce a hot day).
- 59 must be **rare**: 0–2 rounds ≤ 59 in 10,000.
- Any low round must be **earned**: GIR ≥ 15, putts ≤ 26, no 50-footer
  holed.

The learning loop is allowed to make 59 *more plausible* over a season —
that is the point of the ladder — but it is not allowed to make it
*likely*. If the loop ever pushes the 59 rate above the 0–2 per 10,000
band, the monitoring check in §7.2 fires and the loop halts. The season
arc bends toward 59; it never arrives on schedule.

---

## 8. Season-reset rules

### 8.1 When a season ends

A season is **200 rounds** (the qa-plan L-05 window). When round 200
completes, the season ends and the reset runs before round 201. (The
broadcast never goes dark for this — the reset is a data operation between
rounds, and the next round starts on schedule.)

If Mas shoots 59 (or better) before round 200, the season ends early
(`sim-engine.md` §7.3): the chase becomes Road to 58, and the reset runs
immediately. This is the only early-reset trigger.

### 8.2 What survives the reset, and what does not

| Item | Survives? | Detail |
|---|---|---|
| Round store (all 200 rounds) | Archived, not deleted | Moved to the season archive. The new season's loop starts with an empty round store. |
| Fix history | Archived, shown in the Record Book | "What he fixed in Season 1" is permanent lore. The new season starts a fresh fix history. |
| Aim biases | **No** — reset to the Season 1 starting biases | A new season is a new golfer in the only sense that matters: the loop must re-earn every fix from fresh data. Carrying biases forward would compound improvement across seasons and break the 1.5-stroke cap. |
| Risk threshold | **No** — reset to baseline | Same reason. |
| Baseline table | **No** — reset to the +3 baseline | Same reason. |
| Handicap index | **No** — re-established from the new season's rounds | The index is computed from the last 20 rounds; a new season has no rounds yet, so the display reads "establishing" until 3 rounds exist (`sim-engine.md` §7.1). |
| Best round / course record | **Yes** — permanent | The course record is the course record. A new season chases it. |
| All-time aggregates | **Yes** — permanent | All-time score, streaks, best/worst rounds. The show's history is cumulative even though the learning resets. |
| 59 Watch records | **Yes** — permanent | Closest calls, rounds on pace at the turn. The chase history is the show's mythology. |
| Season counters | Reset to 0 | Round 1 of the new season is round 1. |

**Why the hard reset on the golfer model:** the 1.5-stroke cap is a
*per-season* budget. If the model carried forward, Season 2 would start
at +4.5 and end at +6, Season 3 at +7 — and within a few seasons Mas
would be shooting 59 regularly, which is exactly the runaway scenario
§7 exists to prevent. The reset is the ultimate safeguard, and it is also
good television: every season opens with Mas re-learning his game, and
viewers who watched Season 1 get to see whether he fixes the same things
in the same order — or finds new weaknesses.

### 8.3 What the reset looks like to viewers

- The season finale (round 200, or the 59 round) is a milestone event:
  a full Record Book review, the final handicap, the fix count, the best
  round, and the "what he learned" summary — all generated from the
  archived data.
- The next round opens as "Season 2, Round 1" with the display index
  "establishing" and the ONE FIX line reading "Learning the game again —
  first fix coming after round 3."
- The broadcast explicitly frames the reset: "The swing is the same. The
  lessons start over. That's the deal." Viewers who understand the reset
  understand the show.

---

## 9. Implementation checklist

For the engineer building this. Each item is independently testable.

1. [ ] **Stores:** round store (append-only, shot-level events) and
   golfer model (versioned, with change log) implemented per §1.1–1.2.
2. [ ] **Parameter caps enforced in code:** aim ±12 ft, risk ±0.09,
   baseline ±0.05, single-fix magnitude ≤ 7 ft. A write that exceeds a
   cap is rejected and logged, never clamped silently.
3. [ ] **Frozen components asserted:** a test that fails if any code path
   writes to σ, physics constants, calibration targets, or course data
   from the learning loop.
4. [ ] **Algorithm implemented exactly as §5**, including the verdict
   step, the four confidence thresholds, the tie-breaks, and the
   escalation ladder. Determinism test: same round store → same fix.
5. [ ] **Noise floors derived, not guessed:** run the 10,000-round
   loop-disabled simulation and record the per-category 90th-percentile
   SG spread (§4.3). The floors in this document are the expected values;
   the measured values are what ships.
6. [ ] **Form system wired** per §3.2, with the cold-stretch rules in
   §3.3 (no fixing cold stretches; verdict windows measured across them).
7. [ ] **ONE FIX line wired** to the golfer model (§6.1) — scorebug,
   player card, Record Book, round-start card — with the plain-language
   rendering rules.
8. [ ] **Monitoring checks automated** (§7.2) — run after every 20 rounds,
   with halt behaviour implemented (loop freezes, broadcast continues,
   change log records the halt).
9. [ ] **Season reset implemented** per §8.2, including the archive step
   and the "establishing" display state.
10. [ ] **Full calibration re-run** (qa-plan §1) with the loop enabled for
    200 rounds: improvement 0.0–1.5 strokes (L-05), 59 check passes
    (§1.5), no fix churn, no category SG drift. The season is not shippable
    until this passes.

---

## Appendix: Glossary

| Term | Meaning |
|---|---|
| **Fix** | One mechanical parameter change (aim offset, club up, trajectory, target line, aggression) produced by the learning loop, with its evidence and expected gain. |
| **Active fix** | The single fix currently applied. Exactly one exists at a time. |
| **Verdict** | The loop's judgement on a fix after its 3-round window: `working`, `no_effect`, or `harmful`. |
| **Escalation** | Increasing a fix's magnitude (4 ft → 7 ft) or switching its mechanism when the verdict is `no_effect`. |
| **Resistant bucket** | A sub-bucket that survived two escalations without improving. Abandoned for 10 rounds. |
| **Ratchet** | The rule that resolved fixes stay in the golfer model permanently (§5.1). |
| **Noise floor** | The SG swing expected from pure variance in a category over 5 rounds. Inside the floor, there is no weakness to fix. |
| **Form** | The derived hot/neutral/cold state from last-3 vs. last-10 scoring averages. Weather, not climate. |
| **Rung** | A level on the improvement ladder (§2.1), defined by scoring average and handicap. Emergent, never targeted. |
| **Halt** | The loop stopping new fixes after a monitoring breach (§7.2). The broadcast continues; the model freezes. |
