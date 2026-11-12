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
python -m unittest discover -s sim/tests -v
```

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
constants are calibrated so Wyatt National computes **74.6 / 138** — the
spec's stated values. `course.championship_variant()` builds the Black
Tees (longer, narrower, smaller greens, extra bunkers) and its rating/slope
come out harder automatically, so difficulty is a variable: the handicap
differential uses the course being played.

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
