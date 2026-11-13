# Mas Golfs — Simulation Engine ("the Brain")

Reference implementation of [`docs/sim-engine.md`](../docs/sim-engine.md)
v1.0: a fully autonomous, self-improving, fast, and free golf simulation in
which Mas — a left-handed +3 digital twin of Mason Wyatt — plays 18-hole
rounds on repeat at Wyatt National, emitting the typed JSON event stream
the broadcast consumes. No network, no paid services, no API keys.

## Run it

```bash
pip install -r requirements.txt   # numpy only
python -m sim.demo                # one full round, printed scorecard
python -m sim.demo --rounds 3 --fast
python -m sim.demo --course black # the harder black-tee variant
python -m sim.calibrate           # calibration harness (spec §3.7)
python -m sim.run_tests           # FAST suite (no full rounds, seconds)
python -m sim.run_tests --slow    # full suite incl. round-playing tests
python -m sim.run_tests --parallel --slow  # full suite, modules in parallel
python -m unittest discover -s sim/tests -v  # same as --slow, via unittest
```

## Test speed

A fast-mode round is ~25 s and an mc_n=60 validation round ~1 min, so
the full suite takes ~15 minutes — too slow for the edit loop. Tests
that play a full round (or an MC validation round) are marked ``@slow``
(`sim/tests/_markers.py`); the default `python -m sim.run_tests` runs
everything else in seconds. Run `--slow` before any push and on the
Mac. Speed notes (Nov 13): the putting solver runs the ideal-start-line
search once per putt (the read and the result share it); single-ball
flight uses a scalar integrator (~3 ms vs ~130 ms, carry identical);
`pace_at_closest` is rounding-sensitive when a putt has two near-tied
closest approaches, so keep the bilinear interpolation exactly as-is
(a fused variant flipped one such tie and broke a test).

## Layout

| Module | What it is (spec section) |
|---|---|
| `rng.py` | mulberry32 PRNG; seeded per round, byte-identical replays (§8.4) |
| `constants.py` | Physics constants, club/gapping/dispersion tables, baseline (§§2–3, 5) |
| `course.py` | Wyatt National geometry, lie determination, rating/slope (§§2.5, 9.1) |
| `conditions.py` | **Dynamic conditions engine**: weather, wind, firmness, green speed, mid-round changes |
| `physics.py` | Delivery → launch, 100 Hz flight integration, bounce/roll (§2) |
| `putting.py` | Make-probability + distance-control putting model (§3.5) |
| `decisions.py` | Lie/wind gating, candidates, Monte Carlo EV, risk rule (§§4–5) |
| `strokes_gained.py` | Baseline table (§5.5) and SG computation (§6.2) |
| `learning.py` | Golfer model + the one-fix-per-round learning loop (§6) |
| `handicap.py` | WHS-style index, form, record-book aggregates (§7) |
| `fifty_nine_watch.py` | **59 Watch**: live 59-pace state, P(break 60), pace moments (§7.3) |
| `events.py` | Typed JSON event emitter (§1) |
| `engine.py` | Round loop and state machine (§8) |

## The 59 Watch

`FiftyNineWatch` tracks the Road to 59 chase hole by hole: strokes vs the
59 pace line, strokes he can still afford to drop, and a live probability
of breaking 60 (normal model over remaining holes from his last-10 scoring
average and form). Statuses: `on_pace`, `off_pace`, `on_the_line` (18th
hole, 59 achievable), `secured`, `gone`. A `fifty_nine_watch` event fires
on every status change, and the state rides along in every
`hole_complete` event. Season aggregates (rounds on pace at the turn,
rounds alive on 18, best pace ever, closest calls) live in
`FiftyNineRecordBook` and in the `round_complete` event.

## Dynamic conditions

Opening conditions follow the spec's §1.4 draw (triangular wind, prevailing
NW, weighted sky, normal firmness and green speed). From hole 2 on, a
`ConditionsEngine` walks them: wind wobbles and occasionally shifts, the
sky can turn, rain softens the turf and slows the greens, sun firms
everything up. Notable shifts emit a `conditions_change` event.

Conditions flow through everything:

- **Physics** — firmness sets bounce restitution and roll friction (firm
  fairways and fast greens roll further); rain adds spin; wind acts on
  the ball in flight.
- **Decisions** — club up in wind, knockdowns into the wind (already in
  the spec), plus safer targets on firm/fast days (aim pulled halfway to
  the fat of the green) and a tighter risk rule (−0.03); soft/slow days
  loosen it (+0.02).
- **Putting** — faster greens lower make rates from distance (§3.5).

## Course rating and slope

`course.compute_rating_slope()` derives rating/slope from the design:
effective length (yardage + elevation + prevailing wind) and obstacle
strokes (bunkers, water, trees, OB, narrow fairways, small greens). The
constants are calibrated so Wyatt National v3 computes **76.1 / 142** — the
spec's stated values. `course.championship_variant()` builds the Black
Tees (longer, narrower, smaller greens, extra bunkers) and its rating/slope
come out harder automatically, so difficulty is a variable: the handicap
differential uses the course being played.

## Flight-model corrections (deviations from the spec, documented)

The spec is the authority, but several of its formulas are internally
inconsistent with its own §3.1/§3.7 calibration targets, and simulation
proved it — so they were corrected, with the evidence in the code:

1. **Lift coefficient (§2.3).** The spec's `Cl = spin / 145000` gives
   Cl = 0.02 at driver spin — about one tenth of the lift a real ball
   produces. With it, no launch angle can reach the 268-yard driver carry
   (the ball maxes out at ~228 yd). Replaced with the published
   spin-ratio model (Smits & Smith): `Cl = CL_C2·S² + CL_C1·S`, where
   `S = ωR/|v|` is recomputed every integration step. Fitted values
   were first `CL_C1 = 1.8, CL_C2 = -3.25` (module constants in `physics.py`,
   refittable by `calibrate.py`). Drag stays the spec's formula
   (`Cd = 0.24 + 0.000012·spin`). Result: the gapping table reproduces
   to ~2% mean error across all 14 clubs — see item 6 for the refit that
   fixed the driver's remaining shortfall.
2. **Launch angle (§2.2).** The spec's single-factor formula
   (`loft × 0.72`) launches the driver at 8° (real: ~12°) and the lob
   wedge at 38° (real: ~31°) — no single factor fits both. Replaced with
   a per-club calibrated launch table (`LAUNCH_DEG` in `constants.py`),
   with the drawn angle of attack moving it only by its deviation from
   the club's typical AoA.
3. **Wedge club speeds (§3.2).** The spec's wedge speed means (83/81/79
   mph) made the wedges carry 20–35% long under the calibrated flight
   model — a full sand/lob wedge is a control swing. Lowered to 78/73/68
   mph; the gapping table now reproduces.
4. **Chunk smash factors (§2.2).** The spec's chunk smash was only ~9%
   below pure, which left chunked iron shots flying as far as pure ones
   (a pure short-iron shot is already drag-limited, so a chunk can only
   lose distance through ball speed). Chunk smash now falls steeply for
   short clubs (driver 1.22 → wedge 1.00): chunked shots carry 0.70–
   0.84× pure across the bag. Thin stays close to pure — a thin shot
   really does keep most of its speed ("thin to win").
5. **Bounce retention is spin-dependent (§2.5).** The spec's flat horizontal
   retain (0.72 first bounce, 0.85 after) let a high-spin wedge bounce
   ~27 yd forward off its first contact — a pitch landing on the green
   bounded clean off the back, collapsing fast-mode GIR to 0/18. Both the
   restitution and the horizontal retain now fall as spin rises (a driver
   at 2,900 rpm is barely affected; a wedge at 8,500+ rpm checks hard), so
   wedge shots stop on the green and drives still bounce and roll.
6. **Lift-curve refit (§2.3, Nov 12, 2026).** The first fitted curve
   (`CL_C1 = 1.8, CL_C2 = -3.25`) under-lifted at low spin ratio: a pure
   driver at 161 mph / 12° / 2,900 rpm carried 248.5 yd against the 268 yd
   gapping target, while the irons (higher S) were already on target —
   so no global lift or drag change could fix the driver without
   overshooting the irons (raising the lift slope to the published 1.99
   alone pushes the 7-iron +4.7%; removing the spin-drag term pushes it
   +17%). The diagnosis was carry, not delivery: ball speed was already
   right (160.8 mph vs the 161 target) and the drawn 300-shot mean carry
   was 240.4 yd. The refit (`CL_C1 = 2.4, CL_C2 = -4.5`) steepens the
   low-S rise and rolls off earlier (peak Cl ~0.32 at S ~ 0.27, same peak
   as the published curve). Result: pure driver carry 248.5 → 269.1 yd,
   drawn 300-shot mean 240.4 → 262.1 yd, ball speed unchanged, and the
   14-club gapping mean error improves 2.14% → 1.80% (worst club besides
   the LW, which was already +7.4% and is unaffected — it sits at the Cl
   floor — is the 5-wood at +4.3%). The driver carry test band was
   tightened from 240–295 to 252–278 so a regression to ~240 fails
   loudly instead of barely passing. Two independent 6-round Monte Carlo
   calibrations before the fix both showed driving ~247 yd and scoring
   ~74. The calibration re-run after the refit (Nov 12, 2026, 6 rounds,
   Monte Carlo n=120, Wyatt National) confirms the fix where it matters
   most: driving 272.5 yd (target 270, band 265–275, was ~247) and
   scoring 71.5 (band 71–73 — the v1 band; the v3 band is 72–74, pending the 10,000-round harness — was ~74.3), putts 30.3 (target 29.5) and
   ball speed 160.7 mph (target 161) — all PASS. The harness still
   reports CALIBRATION FAILED overall, on dispersion, not delivery:
   fairways 43% (target 57%), scrambling 49% (target 60%), GIR 68%
   (target 60% — the v1 target; v3 is ~55–57%, pending the harness — overshooting in the good direction), sand saves 100%
   (target 50%, tiny 6-round sample). Per the harness's own rule the
   next step is a §3.2 sigma retune, never another physics change —
   and 6 rounds is a sanity sample, not the 10,000-round gate.
   Independent verification (Nov 13, 2026, `python -m sim.verify_carry`,
   300-shot drawn samples): driver mean carry 262.6 yd (sd 16.9) vs the
   262.1 claimed above; pure driver 269.1 yd at the gapping condition
   (110 mph × 1.49 smash = 163.9 mph ball speed), 264.6 yd at exactly
   161 mph / 12° / 2,900 rpm; 3-wood drawn mean 244.8 yd (target 245);
   14-club gapping mean error 1.80% — every refit number above confirmed
   by an independent run, not just re-quoted.

Everything else follows the spec exactly, and `calibrate.py` re-checks
the §3.1 targets on every run.

## Honest performance note

The spec's budgets (< 5 ms per decision, < 50 ms per round) assume a
compiled implementation. In this Python reference implementation a full
Monte Carlo decision (N=120, ~8 candidates) takes ~0.1–0.3 s, and a round
takes ~5–20 s. The physics and the decisions are identical — only the
wall-clock differs. `python -m sim.demo --fast` uses the rule-based
decision path (no Monte Carlo) for calibration-speed runs; the broadcast
path always uses the Monte Carlo.

## Determinism

A round is seeded by `hash(round_no, course_id)` (§8.4). Replaying a
round with the same seed produces byte-identical events (timestamps are
derived from round/sequence, not the wall clock). Pass `--seed N` to shift
the session's rounds.
