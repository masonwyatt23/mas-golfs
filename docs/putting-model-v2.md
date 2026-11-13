# Mas Golfs — Putting Model v2

**Date:** Nov 13, 2026
**Status:** Design only. No sim code changed.
**Reads:** `docs/sim-engine.md` §3.5 (putting model), §3.6 (form), §2 (events); `docs/research/pga-tour-broadcast.md` §1 (putting coverage); `docs/research/best-golf-games.md` (putting presentation, §7 flagstick, §10 consensus); `docs/research/golf-clash-mechanics.md` §1–2 (putting system, flagstick); `docs/course-design-v3.md` (green complexes); `docs/commentary-prompts.md` §3–4; `docs/broadcast-stack.md` §2 (director, PIN camera).

## 0. What v2 is, and what it is not

Putting v1 (shipped, `sim/putting.py`) is a **make-probability + distance-control model with no green geometry at all**. It draws a break from a triangular distribution scaled by distance, draws make/miss from a table, and draws a leave distance. The ball is then moved in a straight line toward the pin by the roll-out distance (`sim/engine.py`, putt sub-loop). There is no green in the sim: `sim/course.py` `Hole` has a `green_radius_ft` (default 42 ft) and an elevation, but no slope, no contour, no pin position on the green surface. The broadcast renders a green from its own art, not from sim data.

That means the overlay and the physics already disagree *in principle* — which is exactly the failure the research caught in EA Sports PGA Tour: their putting beads were sampled coarser than the physics, so the beads showed break one way while the putt broke the other way, and putting became "a lesson in irritation." Our v1 has the same structural flaw, only hidden, because the broadcast has never tried to show a green read at all.

**Putting v2 adds the green.** One heightfield per green is the single source of truth for the ball's roll, the broadcast's green-read overlay, and the putt-path trace. The make-probability table stays exactly as it is — it is the calibrated contract, and the harness gate (±5% on every metric, `sim-engine.md` §3.7) still applies to it. What changes is that the *path* of every putt becomes a real integration over real geometry, and the broadcast can finally show the putt honestly.

**Frozen (do not touch):** the §3.5 make-probability table, the missed-putt leave-distance distributions, the three-putt rate target (~2–3% of greens), the green-speed (stimp) adjustment formulas, the 12%/8% long/short pace draws, and the calibration harness itself. Putting has no dispersion σ — there is nothing to freeze there — but the table and the leave distributions play the same role, and they do not move.

**What changes:** a green heightfield per hole; the break is computed from the field instead of drawn; the putt's path is integrated over the field; new events carry the path, the preview line, the live make probability, and the lip classification; the booth gets a putt-read template and lip-out language; form gets a putting-pace effect and per-round reporting.

---

## 1. The green heightfield — one source of truth

### 1.1 The problem, stated plainly

Today the sim knows three things about a putt: how far it is, how much it breaks (drawn), and whether it drops (drawn). The broadcast knows none of them from geometry. Any green-read overlay the broadcast draws today would be decoration — it could not be wrong, because it would not be connected to anything. EA's failure is the warning: the moment the overlay and the physics are computed from *different* samplings of the green, they will disagree on camera, in front of viewers, and the show loses trust. The rule for v2 is therefore:

> **The overlay and the ball read the same array. If they ever disagree, the overlay is wrong, never the ball.**

### 1.2 What the heightfield is

A `Green` object per hole, added to `sim/course.py` next to `Hole`:

| Field | Meaning | Source |
|---|---|---|
| `green_slope_pct` | Overall slope, back-to-front, in percent | `course-design-v3.md` per-green spec (12th flattest 0.8%, 16th Redan steepest 2.5%, severe greens 2.5–3%) |
| `green_fall_dir_deg` | Downhill direction of the fall line, degrees from the hole's centreline | v3 per-green spec (putts break toward the water on 8 and 12, away from the fall-off on 5 and 13, over a spine on 4 and 10) |
| `green_tiers` | Tier structure: list of steps/spines/bowls, each with a location, a height, and a shape (spine, bowl, false front, crown, thumbprint) | v3 per-green spec (e.g. 1st: two-tier, back tier 18 in higher; 4th: three sections separated by a spine; 3rd: crowned with a thumbprint hollow) |
| `green_radius_ft` | Already exists on `Hole` (default 42 ft) | Existing |
| `green_grid_m` | Grid spacing, **0.5 m** | Fixed by this spec |
| `heightfield` | 2D array of heights (mm above the green's low corner), deterministic from `(course_id, hole_no)` | Generated once per hole at round start |

The field covers the green **plus a 2 m collar** into the fringe and apron, because the engine allows putter from the fringe (`sim-engine.md` §4, `sim/engine.py` putt-from-fringe path) and a fringe putt's roll starts off the green. Without the collar, fringe putts would have no geometry.

**Resolution.** A green is ~20–30 m across. At 0.5 m spacing the field is roughly 50 × 60 = ~3,000 points per green. Heights quantize to int16 millimetres: ~6 KB per hole raw, ~2.5 KB as a compact base64 payload. That is cheap enough to ship in the `hole_start` event (see §1.5) and small enough that the web build can hold all 18 fields in memory at once.

**Why 0.5 m and not coarser.** EA sampled elevation at grid corners and missed the slope variation *between* grid points — that is the exact mechanism of their bead failure. A 0.5 m grid is finer than the ball (4.27 cm diameter is the ball, but the *break* the viewer reads is a feature of the surface at the scale of a foot or two). Tiers and spines in v3 are features of 1–3 m; a 0.5 m grid resolves them, a 2 m grid would not. Finer than 0.5 m buys nothing a viewer can see.

**Determinism.** The heightfield is generated from `(course_id, hole_no)` only — never from the round seed. Greens do not change between rounds; pins do. The same green plays differently by pin because the ball starts and finishes at different points on the same surface. This also makes the field cacheable: generate once per hole, reuse for every round, and the broadcast can trust that the field it rendered on round 12 is the field the sim integrated on round 47.

### 1.3 Outcome first, path second — how the table and the field coexist

The make-probability table is the calibrated contract. It must not be replaced by a pure physics roll, because a pure roll would need its own calibration from scratch and would break the harness. Instead v2 keeps the two-step structure the sim already has, and makes the second step geometric:

1. **Outcome draw (unchanged).** `make_probability(distance_ft, break_ft, green_speed)` from the §3.5 table, with the existing stimp and break adjustments, decides make/miss. The pace class (`good` / `long` / `short`) and the leave distance are drawn exactly as today. These are the calibrated numbers; they do not move.
2. **Path integration (new).** Given the drawn outcome, the putt's path is a real integration over the heightfield, conditioned on that outcome:
   - If the putt is **made**, the start line is solved so that integrating the roll on the field carries the ball into the cup at a dying pace. The solver searches start lines within a small cone around the ideal line (the ideal line is the line the broadcast's preview shows) until the integrated path drops. This is a cheap search — a handful of integrations per putt, each a few dozen steps.
   - If the putt is **missed**, the start line and initial velocity are solved so the integrated path stops at the drawn `leave_ft` from the cup, with the drawn pace class (a `long` miss runs past, a `short` miss dies early, a `good` miss burns the edge or slides by). The leave distance the viewer sees is the leave distance the table drew — the geometry is fitted to the outcome, not the other way around.

The point of this ordering: **the path is a real integration, not a drawn curve, and it is guaranteed consistent with the result.** The viewer can watch the ball follow the break the overlay promised, and the ball will do what the sim said it would do. The harness still gates the table, and the path adds the honesty the table alone cannot provide.

### 1.4 Break comes from the field, not from a draw

Today `draw_break()` in `sim/putting.py` draws break from a triangular distribution (`0` to `distance × 0.15`, mode `distance × 0.05`), unrelated to any green. In v2, `break_ft` is **measured from the integrated path**: the maximum lateral deviation of the path from the straight ball-to-hole line, in feet. The existing break adjustment in `make_probability()` (`× (1 − 0.04 × break_ft)` for break over 2 ft) stays, but its input is now a measured quantity.

This changes the distribution of `break_ft` slightly — a putt across a 2.5% Redan slope will break more than a putt across the flat 12th, which is the point. The effect on make rates is second-order (the break adjustment only bites above 2 ft of break), but the harness must be re-run after the change and must still pass ±5% on `make_rate_by_distance_bucket`. If a bucket drifts, the fix is in the solver's start-line cone, not in the table.

### 1.5 Green speed becomes friction

Today green speed (stimp) enters only as a multiplier on make probability for putts over 10 ft. In v2 it also enters the roll integrator as rolling friction: the ball decelerates at `μ · g`, with `μ` scaled by `(11.0 / green_speed)` — faster greens, less friction, longer roll on the same pace. The exact `μ` is **fitted, not asserted**: the fit procedure is to run the integrator over the §3.5 leave-distance distributions and choose `μ` so that a `good`-pace putt from 20 ft stops inside the drawn leave band, and a `long`-pace putt runs to the drawn `long` leave. The fitted constant is recorded in `sim/constants.py` with its fit procedure, the way the flight-model corrections are recorded in `sim/README.md`. Until the fit is run, any `μ` value in code is an estimate — see the honesty table in §6.

**Uphill/downhill.** The field's gradient already encodes uphill and downhill: a putt struck uphill decelerates faster (gravity component against the roll), a downhill putt runs on. The integrator handles this from the field alone — no separate uphill/downhill adjustment is needed, and none should be added. This is also why the v3 greens' slope percentages matter as *numbers*, not adjectives: they are the input to the integrator.

### 1.6 How the broadcast gets the field

Two options, in order of preference:

1. **Ship it in `hole_start`.** The bus's `hole_start` event gains a `green` object: the quantized heightfield (base64), the grid spacing, the green centre in course coordinates, and the fall-line direction. The web build renders slope arrows and the grid from this array; the Unreal slice later feeds the same array into its landscape. One source, three consumers.
2. **Deterministic re-computation (fallback).** The web build ports the same generator (`green_heightfield(hole, seed)`) and computes the field from `(course_id, hole_no)`. This works only if both implementations are byte-identical — a test must assert that, and any drift breaks the rule in §1.1. Prefer option 1; keep option 2 as the offline fallback.

**Implementable changes (§1):**
- `sim/course.py` — add `Green` dataclass (`green_slope_pct`, `green_fall_dir_deg`, `green_tiers`, `green_grid_m = 0.5`, `heightfield`); add `green: Green` to `Hole`; add `green_heightfield(hole) -> np.ndarray` (deterministic, seeded by `(course_id, hole_no)`); extend the field 2 m into the fringe collar.
- `sim/putting.py` — add `roll_path(field, start, start_line, velocity, green_speed) -> list[(x, y)]` (the integrator; gradient descent + rolling friction + gravity component); add `measure_break(path) -> float`; add `solve_start_line(field, ball, pin, outcome, leave_ft, pace) -> (start_line, velocity)` (the outcome-conditioned solver).
- `sim/putting.py` — replace `draw_break()` with a field-derived break: `break_ft` is measured from the integrated path, not drawn. Keep the function name as a thin wrapper only if callers need it; otherwise delete it.
- `sim/constants.py` — add the fitted rolling-friction constant with its fit procedure in a comment (fitted at implementation time, not asserted now).
- `sim/engine.py` — putt sub-loop: call the solver after the outcome draw, store the integrated `path` on the emitted event (see §2), and move the ball along the integrated path's endpoint rather than in a straight line toward the pin.
- `bus/translate.py` — pass the `green` object on `hole_start` through to the broadcast envelope unchanged.
- `docs/sim-engine.md` §3.5 — add the heightfield, the outcome-first/path-second ordering, and the field-derived break as the v2 amendment, in the same style as the existing spec.
- `docs/course-design-v3.md` — no change needed; it already specifies per-green slope, tiers, and contour. If a green's spec is missing a number the `Green` dataclass needs, the gap is filled in the v3 doc first, not improvised in code.

---

## 2. The putt-path trace event

The Tour debuted the ShotLink putt-path trace at the Sony Open in January 2026: the ball's actual path mapped on the green, built on a LiDAR base layer of the green's slopes. The broadcast research calls it the single highest-value new graphic in golf — it makes every putt watchable even for a viewer who doesn't know golf. We get it free, because our LiDAR layer is the heightfield and our ball tracking is the sim itself.

### 2.1 Two lines, not one

There are two lines, and they must never be confused:

| Line | When it is drawn | What it is |
|---|---|---|
| **Predicted path (preview)** | During the read, before the stroke | The integrator run from the ball with the *ideal* start line and nominal pace. It is the "should" line. It is computed **before the outcome is drawn**, or from the ideal line alone, so it can never leak the result. |
| **Actual path (trace)** | During and after the roll | The integrated path from the outcome-conditioned solver (§1.3). It is the "did" line. It is drawn as the ball rolls, and stays on screen for a beat after the putt stops. |

The drama of a putt is the gap between those two lines. On a make they converge; on a miss they diverge, and the viewer sees exactly where the read or the pace went wrong. Golf Clash's putt-preview feature is the same idea from the player's side; the Tour's trace is the same idea from the viewer's side. We show both, which neither does.

### 2.2 The `putt_read` event (new, before the stroke)

Emitted with the `decision` event for a putt (`shot_type == "putt"`), before the stroke:

```json
{
  "type": "putt_read",
  "hole": 12,
  "putt": {
    "distance_ft": 14.1,
    "distance_in": 169,
    "break_ft": 1.8,
    "break_dir": "left_to_right",
    "make_pct": 0.23,
    "green_speed": 11.4,
    "predicted_path": [[0.0, 0.0], [0.9, 0.2], "..."],
    "is_comebacker": false
  },
  "fifty_nine_watch": { "on": false }
}
```

- `distance_in` is the distance in inches (14 ft 1 in — the Tour states putt distance precisely, and precision is what makes the putt feel measurable).
- `make_pct` is the **pre-stroke** probability from `make_probability()`, after the form multiplier (§4). It is shown during the read ("he makes about one in four of these") and never recomputed after the outcome — recomputing it after the ball drops would be inventing a number.
- `predicted_path` is in green-local feet, origin at the ball, x-axis along the straight ball-to-hole line, y-axis lateral. One point per foot of putt length, capped at 60 points. Small enough to ride in the flat event.
- `is_comebacker` is true when `putts_on_hole > 0` — the read is framed as the comebacker (see §3.4).

### 2.3 The `putt_result` extension (existing event, new fields)

```json
{
  "type": "putt_result",
  "hole": 12,
  "shot_no": 3,
  "putt": {
    "distance_ft": 14.1,
    "break_ft": 1.8,
    "break_dir": "left_to_right",
    "speed": "good",
    "made": true,
    "leave_ft": 0,
    "make_pct": 0.23,
    "path": [[0.0, 0.0], [0.9, 0.2], "..."],
    "pace_ft_s": 1.2,
    "past_hole_ft": 0.0,
    "lip": false,
    "closest_in": 0.0
  },
  "putts_on_hole": 1
}
```

- `make_pct` repeats the pre-stroke probability for the record and for the lower-third.
- `path` is the integrated actual path, same coordinate system as `predicted_path`, one point per foot, capped at 60.
- `pace_ft_s` is the ball's speed as it reaches the hole, in ft/s. On a make, a dying pace (~1–2 ft/s) is the "perfect pace" story; on a miss, it is the evidence.
- `past_hole_ft` is how far past the hole the ball *would* have rolled if the cup had not caught it — the number the Tour's analysts quote on a firm putt ("that was running three feet by"). Zero when the ball dies short. Computed by continuing the integration past the cup.
- `lip` / `closest_in` — the lip classification (§2.4).

### 2.4 Lip-out, measured

A lip-out is not a vibe; it is a measurement. The integrator knows the ball's closest approach to the cup centre:

| Classification | Closest approach to cup centre | Meaning |
|---|---|---|
| `lip` (on the lip) | < 3 in | The ball's edge caught the cup's edge and stayed out. The "SO CLOSE" trigger. |
| `burned_edge` | 3–6 in | The ball passed within a ball's width of the hole. High drama, but not a lip-out. |
| `missed` | > 6 in | An ordinary miss. |

(Hole radius is 2.125 in, ball radius 0.84 in — the ball's edge touches the cup's edge when the centres are ~3 in apart.)

`lip: true` is emitted only for the < 3 in case. `closest_in` is always emitted so the broadcast and the clip pipeline can rank near-misses: "on the lip" outranks "burned the edge" in the drama model, and both outrank an ordinary miss. The existing `speed` field already distinguishes a `long` miss (longer comebacker) from a `good` miss — the lip flag is orthogonal to it.

### 2.5 What the broadcast draws

- During the read: the predicted path as a thin dotted gold arc, the slope arrows and faint grid from the heightfield (§1.6), and the putt graphic lower-third — distance to the inch, break in plain language ("2 ft, left to right"), live make percentage ("23%").
- During the roll: the actual path draws itself behind the ball in real time, in the tracer's colour. The camera is the low green-side `PIN` cam, held through the whole roll — no cutting mid-putt (the Tour's rule, and already the director's rule in `broadcast-stack.md`).
- After the putt stops: the full actual path stays on screen for ~3 seconds beside the predicted path, so the viewer can compare them. On a make, the path ends in the cup with the gold ripple; on a lip-out, the path visibly bends around the edge.

**Implementable changes (§2):**
- `sim/engine.py` — emit `putt_read` with the `decision` event for putts (before the stroke; compute the predicted path from the ideal line *before* drawing the outcome). Extend the `putt_result` emission with `make_pct`, `path`, `pace_ft_s`, `past_hole_ft`, `lip`, `closest_in`.
- `sim/putting.py` — add `predicted_path(field, ball, pin, green_speed)` and `classify_miss(path, pin) -> (lip, closest_in)`; add `pace_at_hole(path)` and `past_hole(path)` helpers on the integrator.
- `bus/translate.py` — map `putt_read` and the extended `putt_result` into the broadcast envelope; `putt_read` maps to the director's read phase, `putt_result` to the roll/result phase.
- `docs/broadcast-stack.md` §1.2 — add `putt_read` to the event table and the new `putt_result` fields; add the "two lines" rule to the director section.
- `docs/qa-plan.md` §1 — add a check that `predicted_path` is computed before the outcome draw (a test that replays the same seed and asserts the preview line is identical whether the putt is made or missed).

---

## 3. Putting theatre events

Putting is the most-covered shot in golf, and the broadcast's grammar for it is rigid. The research gives us the whole playbook; v2 wires the sim's events to it.

### 3.1 The flagstick — one coherent behaviour

The research is unanimous on one point and split on another, so this spec picks one behaviour and states it:

- **Unanimous:** no game in the study models flagstick removal, and the flag is a static visual anchor in all five games. Golf Clash has no flag-out animation at all — the ball drops with the flag in place.
- **The split:** Mason's direction is that the flag comes out when the ball gets close (a Mas Golfs invention, worth doing because it is ours). The Tour's broadcast practice is the *tend*: the caddie holds the flagstick and pulls it cleanly the instant the putter strikes, moving clear before the ball arrives. Since the 2019 Rules change a player may putt with the flag in, but the tend is still the classic broadcast moment — and when it goes wrong it becomes the story (DeChambeau's stuck flagstick at the 2021 Ryder Cup).

**The v2 behaviour (tend/pull):** the flag is **tended during the read** (held, slightly lifted, the caddie figure beside the cup), and **pulls cleanly out of the cup the instant the putter strikes**, laid down on the green. The ball then rolls at an open cup. This honours Mason's direction — the flag does come out — in the form a golfer recognises, and it gives the broadcast its most dramatic small prop. The web build's current "flag vanishes when Mas is on the green and close" is replaced by this two-beat version: tend during the read, pull at the strike. The flag stays out for the tap-in — a small running beat the audience learns to watch for.

**The alternative, recorded not adopted:** flag-in putting (legal since 2019), in which the flag stays in the hole and dips/wobbles on the make. If Mason prefers that version, it is a one-line change to this section and to the director rule — but the tend/pull is the default because it is the broadcast moment, and because a dipping flag on every make would get old faster than a pulled flag does.

### 3.2 The make — three beats

From the WGT and Golf Clash research, the hole-out ceremony is three beats, in order, and it is short:

1. **Tight hole/flag close-up as the ball rolls in.** The low green-side camera pushes in. The cup is open (flag pulled). The ball drops.
2. **Big centred result word + sound.** "BIRDIE" in gold, a cup-rattle sound (a short wooden rattle, not a generic chime — the broadcast mics every green so the drop is audible), and a crowd swell. The booth says one short line or nothing (see §5).
3. **Instant scorebug update.** The score changes on screen in the same beat.

The whole ceremony is ~6 seconds and is auto-clipped as the shareable highlight (the clip pipeline already scores hole-outs at 100; the ceremony is the clip). The celebration is deliberately bigger than the shot — that is the Golf Clash lesson — but it is *brief*: WGT's version works because it is short, loud, and legible. Do not linger.

### 3.3 The lip-out — its own language

A made putt and a missed putt are two different kinds of television. The lip-out gets the *replay* treatment, not the live treatment:

- **Slow-motion replay from the low green-side camera**, 0.5×, showing exactly how the ball caught the edge. The director already scores near-misses 70–85 in the drama model (`broadcast-stack.md`); a `lip: true` putt scores 85 and triggers the replay automatically.
- **A "SO CLOSE" / "HOW?" lower-third** in the broadcast's voice, not a generic miss graphic. The canonical example is Knapp's ball on the lip at the 2026 3M Open ("HOW IS THAT POSSIBLE?!") — the near-miss *was* the content.
- **The comebacker as its own beat** (see §3.4).

The clip pipeline scores lip-outs above ordinary near-misses: "on the lip" outranks "burned the edge" (see §2.4). The 59 Watch record book already tracks closest calls; a lip-out on a 59-chase putt is an automatic second clip of the day.

### 3.4 The comebacker — its own beat

After a miss, the broadcast does not rush past the tap-in. The leave distance is stated ("leaves himself 4 feet for par"), the camera stays low, and the comebacker is shown — because the comebacker is where the drama compounds. In v2 this is a director rule driven by the event stream, not a new event:

- When `putt_read.is_comebacker` is true, the read is framed as the comebacker: the lower-third states the leave distance and the putt it is for ("4 ft for par"), and the camera stays on the low green-side angle.
- A missed comebacker (a three-putt in progress) escalates the booth: the host names it plainly ("that's a three-putt coming"), once, without dwelling. The three-putt rate target (~2–3% of greens) is the guardrail — if comebackers start missing often enough to be a story, the leave distribution is wrong, not the broadcast.

### 3.5 Sound on the green

The putt gets its own sound moment, in order: the soft click of the putter, near-silence during the roll (the ambient bed ducks, the booth says nothing — silence during the roll is free and it is the most broadcast-like thing in the research), and the distinct cup rattle on a make. The ambient engine already has layered audio with sidechain ducking (`broadcast-stack.md` §5); the putt is the place to use it most aggressively. A lip-out gets the crowd gasp — a short, sharp intake, not a groan — because the gasp is what makes the replay land.

**Implementable changes (§3):**
- `docs/broadcast-stack.md` §2 (director) — add the flag tend/pull as a director rule: flag tended during `putt_read`, pulled at the putt's `strike`, laid on the green; camera holds low `PIN` through the roll; reaction hold 3 s on the make (already specified for `hole_end` — extend it to the putt itself). Add the lip-out replay rule (`lip: true` → 0.5× replay from low `PIN` + "SO CLOSE" lower-third) and the comebacker framing rule (`is_comebacker` → leave distance stated on screen, camera stays low).
- `docs/broadcast-stack.md` §5 (audio) — add the putt sound sequence: putter click → ducked ambient + silence during the roll → cup rattle on the make, crowd gasp on a lip-out.
- `clip-pipeline/clip_pipeline/scoring.py` — rank `lip` above `burned_edge` above ordinary miss in the near-miss drama scores; ensure a lip-out on a 59-chase putt is an automatic second clip.
- Web build / Unreal slice — replace the current "flag vanishes on the green" with the two-beat tend/pull. This is a presentation change in the artifact, not a sim change.
- `docs/commentary-prompts.md` — see §5 for the booth side of these beats.

---

## 4. Hot and cold putting days

### 4.1 What exists today

`sim-engine.md` §3.6 already defines form modulation, and `sim/constants.py` already carries it:

```python
FORM_PUTT_MULT = dict(hot=1.08, neutral=1.00, cold=0.92)
```

Applied in `sim/putting.py` `putt()` as a multiplier on the make probability. Form is derived from data (§7.4), never set arbitrarily, and a cold stretch is a story ("he's lost it on the greens — three rounds running"), not a difficulty setting. The exit condition is defined: the form persists until the 3-round rolling average returns within 0.5 strokes of the last-10 average.

### 4.2 The interface the variability design owns

The variability design (`docs/variability.md`, in progress at the time of writing) owns **how form is derived and how long it lasts** — the day-to-day form draw, the momentum rules, the pressure effects. Putting v2 owns **what form does to putting**, and defines the interface between the two as a single knob plus two reporting fields:

- **The knob:** `form_putt_mult` (0.92–1.08), already the parameter `putt()` takes. The variability design sets it; putting v2 consumes it. Nothing else about form crosses the boundary.
- **The reporting:** `round_end.round_stats` gains `putting_form` (the form state that round) and `putts_gained` (strokes gained putting vs. the §3.5 expectation for the distances faced, from the existing `strokes_gained.putt` split). The booth needs these to tell the story — a cold putting stretch is only a story if the broadcast can name it with a number.

### 4.3 The one new putting effect: pace on cold days

A multiplier on make probability is the right outcome effect, but it misses the *visible* signature of a cold putting day: the putts come up short. Golfers do not miss cold putts by the same margin; they leave them short. So v2 adds one pace effect, gated to the same form knob:

| Form | Make % multiplier | Pace-draw shift |
|---|---|---|
| `hot` | 1.08 | `long`-miss rate 12% → 8% on putts over 20 ft (hot putters do not run it by) |
| `neutral` | 1.00 | As specified in §3.5 |
| `cold` | 0.92 | `short`-miss rate 8% → 12% on all putts (cold putters leave it short) |

The pace shift is implemented in `putt()` as a form-dependent adjustment to the pace-draw thresholds, next to the existing `form_putt_mult` application. It is a small effect by design: it changes *how* putts miss, not whether the round is makeable, and it gives the broadcast something visible to call ("he's left another one short — that's the third time today").

### 4.4 What stays frozen, and the gate

Frozen: the make-probability table, the leave-distance distributions, the three-putt rate target, the ±8% form multipliers themselves. Form scales the probability and nudges the pace draws; it never rewrites the table.

**The gate (new, for `qa-plan.md` §1):** the calibration harness must be run three times — form forced `hot`, forced `neutral`, forced `cold` — and all three runs must pass the ±5% band on every metric, including `putts_per_round` and `make_rate_by_distance_bucket`. A cold run that pushes putts/round up by more than 5% means the form effect is too strong, and the multipliers come down, not the table up. The expected effect is small (a cold round costs ~0.3–0.5 putts vs. neutral — an estimate, see §6), so the gate should pass; if it does not, the gate is right and the estimate was wrong.

### 4.5 One spec/code drift to fix while here

`sim-engine.md` §3.6 says the make-% modifier applies to "putts > 10 ft". `sim/putting.py` `putt()` applies `form_putt_mult` to *all* putts, including tap-ins. A 3-footer at 99% × 0.92 is still 91% — the drift is small, but it is a drift, and tap-ins should not be form-dependent (a cold putter still makes a 3-footer). Fix: gate the multiplier to `distance_ft > 10` in `putt()`, matching the spec. Record the fix in the §3.6 amendment, not as a silent code change.

**Implementable changes (§4):**
- `sim/putting.py` `putt()` — gate `form_putt_mult` to `distance_ft > 10` (spec/code drift fix); add the form-dependent pace-draw shift (cold: `short` rate 8% → 12%; hot: `long` rate 12% → 8% over 20 ft).
- `sim/engine.py` — add `putting_form` and `putts_gained` to `round_end.round_stats`.
- `docs/sim-engine.md` §3.6 — record the >10 ft gating fix and the pace-draw shift as the v2 amendment.
- `docs/qa-plan.md` §1 — add the three-run form gate (hot / neutral / cold, all within ±5%).
- `docs/variability.md` (owner: variability design) — consumes the `form_putt_mult` knob and the pace-shift table defined here; do not redefine them there.

---

## 5. How the booth calls putts

### 5.1 What exists today

`docs/commentary-prompts.md` §4.4 (putt result, host, as the putt stops, 10–25 words: a made putt gets the call and the score it gives him; a missed putt gets only what is left). The hard rules already cover the essentials: never speak over a swing (§3, and the putt stroke counts as a swing — "she is silent during the swing and the putt stroke"), never invent a stat (make % only from the sim), never second-guess a decision after it fails (rule 12 — applies to putt reads as much as to shot decisions), one line per 15 seconds, max four lines per hole. The booth already has the discipline; v2 gives it the material.

### 5.2 The putt read — a new template (before the stroke)

The read is the one place the booth is allowed to be informative about a putt, because it happens before the stroke, when the viewer is waiting. New template §4.4a:

- **Trigger:** `putt_read` event. **Speaker:** host (the read is a host's job — it is a fact, not a decision). **Timing:** during the read, before the putter moves.
- **Fields used:** `dist_ft`, `distance_in`, `break_ft`, `break_dir`, `make_pct`, `is_comebacker`, `fifty_nine_watch`.
- **Word budget:** 15–30 words.
- **Form:** distance first, break in plain language, make probability as a human fraction — never a raw percentage on air ("he makes about one in four of these", never "twenty-three percent"). A comebacker names what it is for ("four feet for par"). A 59 Watch putt names the stakes once ("for 59, this has to drop") and then the booth stops.

```
User prompt:
Putt from {{dist_ft}} feet ({{distance_in}} inches), breaking
{{break_ft}} feet {{break_dir}}. He makes about {{make_pct_human}}
of these. {{is_comebacker ? "This is the comebacker, for " + score_name + "." : ""}}
{{fifty_nine_watch.on ? "For 59, this has to drop." : ""}}
Read the putt in one sentence, plain language, no numbers beyond
the distance. Then stop.
```

### 5.3 During the roll — silence

Nobody speaks during the roll. Not the host, not the color. The putt stroke is a swing, the roll is the flight, and the existing rule ("never speak over a swing") covers both. The Tour's sound design (§1.4 of the broadcast research) is the model: the putter clicks, the ambient bed ducks, the booth says nothing, and the cup rattles or it doesn't. Silence during the roll is free and it is the most broadcast-like thing in the research. The commentary service already enforces this by holding any queued line until `landing` — the putt equivalent is holding until the putt stops. No new code is needed for the silence itself; the new requirement is that **no putt line may be scheduled to fire during the roll window**, which the service's director hold already guarantees if `putt_read` lines are consumed before the stroke and `putt_result` lines after the stop.

### 5.4 The make — one short line, or nothing

Extend §4.4 with the fields v2 adds (`lip`, `leave_ft`, `make_pct`, `putts_this_hole` already there):

- **Routine make:** host, one short line, name the score it gives him. ("The putt drops. Birdie on 12, and Mas moves to three under.") The existing template already does this; it now has `make_pct` available if the make was an upset ("from fourteen feet — he makes one in four of those — and it's a birdie").
- **Big make (drama ≥ 90, 59 Watch on the line):** the host may say **nothing at all for one beat**. Nantz at the 2019 Masters said "a return to glory" and then let ~3 minutes of silence do the work. The template needs an explicit silence option: the service may emit `SILENCE` for a putt result when the drama score is ≥ 90, and the broadcast holds the reaction shot instead. Silence is a line. It is the best line on the biggest putts.
- **Never** hype words on a routine tap-in. A tap-in gets no call at all — the scorebug updates and the broadcast moves on. The existing template's word budget already implies this; state it.

### 5.5 The lip-out — human, short, then the leave

The lip-out is the one miss that earns a real line, because the viewer just watched something unfair happen:

- **Host, one line, human.** ("Oh, how does that stay out?") Short, no analysis, no second-guessing the read — the read was fine, the ball did not cooperate. Rule 12 (never second-guess a decision after it fails) is the guardrail: the booth never says "he misread it" after a lip-out, because the sim's read and the ball's path are both on screen and the viewer can see the read was right.
- **Then the leave, plainly.** The comebacker line states the distance ("four feet left for par") and stops. The existing §4.4 missed-putt rule ("say only what is left") already covers this; the lip-out adds the one human line before it.
- **Color stays out of it.** A lip-out is a host moment. Color speaking over a lip-out would sound like analysis of a cruelty, which is the wrong register. The color's job on the green is the read (§5.2 is the host's) — no, the read is the host's too. The color speaks on the green only when the putt changes the round's story (a 59 Watch putt, a third straight lip-out), and then only after the host's line, never instead of it.

### 5.6 59 Watch putts

When 59 Watch is on, the putt read carries the stakes exactly once per hole (see §5.2), and the make gets the escalation the 59 Watch spec already defines — the bug pulses, the probability updates, and on the 18th the moment goes full-screen. The booth does not repeat the stakes on every putt of the hole; repetition kills the tension the bug is building. One naming per hole, then silence and the bug do the work.

**Implementable changes (§5):**
- `docs/commentary-prompts.md` — add template §4.4a (putt read, host, before the stroke, fields: `dist_ft`, `distance_in`, `break_ft`, `break_dir`, `make_pct`, `is_comebacker`, `fifty_nine_watch`); extend §4.4 (putt result) with `lip`, `leave_ft`, `make_pct` and the explicit `SILENCE` option for drama ≥ 90; add the tap-in rule (no call on tap-ins); add the lip-out line and the color-stays-out rule; add the 59 Watch once-per-hole rule.
- `commentary/service.py` — the `putt_read` event routes to the §4.4a template; the `putt_result` event routes to §4.4 with the new fields; the director hold already covers the roll window — add a test asserting no line is emitted between a putt's stroke and its stop.
- `commentary/prompts.py` — add the §4.4a system prompt and template; add `make_pct_human` to the normalization table (0.23 → "one in four", 0.38 → "about two in five", 0.90 → "nine in ten" — the table is fixed, not computed on the fly, so the booth never invents a fraction).
- `commentary/cache.py` — the putt-read line is never cached (it depends on the live `make_pct` and break); the routine make line may use the cached standard lines; the lip-out line is never cached (it must sound human once, not repeated).

---

## 6. Build order, and what is estimated vs. measured

### Build order

1. **`Green` + heightfield** (§1.2, §1.6) — the foundation. Everything else reads from it. Ship the field in `hole_start`.
2. **Outcome-conditioned solver + field-derived break** (§1.3, §1.4) — the path becomes real. Re-run the harness; the table must still pass.
3. **`putt_read` + extended `putt_result`** (§2) — the events the broadcast and booth consume. The trace is drawable as soon as these land.
4. **Theatre** (§3) — director rules, flag tend/pull, lip-out replay, comebacker framing, putt sound. Mostly broadcast-side; the sim work is done by step 3.
5. **Form pace shift + reporting + three-run gate** (§4) — small, last, because it touches the calibrated numbers and needs the harness green from step 2 first.
6. **Booth templates** (§5) — last, because they consume the events from step 3 and the drama scores from step 4's gate.

### Estimated vs. measured

| Claim in this doc | Status |
|---|---|
| Make-probability table (§3.5), leave distributions, three-putt target | **Measured** — Tour baselines, already in the shipped sim and gated by the harness |
| 0.5 m grid spacing resolves tiers and spines | **Estimated** — reasoned from v3 feature sizes (1–3 m); to be confirmed by rendering the field and the overlay side by side |
| Rolling-friction constant `μ` | **Not yet fitted** — fit procedure defined in §1.5; any value in code before the fit is an estimate |
| Solver cost ("a handful of integrations per putt") | **Estimated** — the integrator is a few dozen steps; the search is bounded; measure at implementation, must stay under the decision-engine budget |
| Cold round costs ~0.3–0.5 putts vs. neutral | **Estimated** — arithmetic from the ±8% multiplier, not a harness run; the three-run gate (§4.4) is what confirms or refutes it |
| Pace-draw shifts (cold short 8% → 12%, hot long 12% → 8%) | **Estimated** — chosen to be visible without moving the round totals; the three-run gate confirms |
| Green slope percentages per hole (0.8%–3%) | **Measured as design input** — from `course-design-v3.md`; the v3 numbers are the spec, not measurements of a real course |
| Tour putt-path trace debuted Sony Open Jan 2026; Penge 14'1" at 23% | **Measured** — from the broadcast research, sourced |
| EA bead failure mechanism (grid-corner sampling) | **Measured** — from EA's own forum explanation, via the games research |
| No game models flagstick removal | **Measured** — across all five games in the research; the tend/pull is the Tour's broadcast practice, not a game mechanic |
| "Silence is the best line on the biggest putts" | **Measured** — Nantz, 2019 Masters, via the broadcast research |

### The one-sentence version

Putting v2 makes the green real: one heightfield feeds the ball, the overlay, and the trace; the outcome stays calibrated, the path becomes honest, the flag tends and pulls, the lip-out gets its replay, the comebacker gets its beat, cold days leave putts short, and the booth shuts up during the roll.
