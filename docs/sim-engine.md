# Mas Golfs — Simulation Engine Specification

**Version 1.0 · 2026-11-12 · Implementation-ready**

This document specifies the simulation engine ("the Brain") for Mas Golfs: a fully autonomous, self-improving, fast, and free (no paid services) golf simulation in which Mas — a left-handed +3 digital twin of Mason Wyatt — plays 18-hole rounds on repeat at Wyatt National (par 72, 7,602 yards; 4 par 3s, 4 par 5s, 10 par 4s; see `course-design-v3.md`).

The engine has one job: **produce believable golf, forever, with no human input and no server.** Every design decision in this spec serves one of four constraints:

1. **Autonomous** — the round loop never blocks on input, a network call, or a human decision.
2. **Self-improving** — every round changes the next round, through a measured learning loop.
3. **Fast** — a full shot decision in < 5 ms on a mid-range phone; a full round simulated in < 50 ms of CPU (rendering excluded). All computation is local and synchronous.
4. **Free** — zero paid services. No LLM API, no TTS API, no hosted physics. All data is embedded constants or computed locally. Persistence is localStorage / a local JSON file.

## Design principles

- **Shots are generated from launch conditions, never from a dice roll on distance.** The engine draws club delivery first (clubhead speed, path, face angle, strike location, angle of attack), converts it to launch conditions (ball speed, launch angle, spin rate, spin axis), then integrates the ball flight through gravity, drag, and Magnus lift. A thin, a chunk, a toe strike, and a draw *behave* differently — they do not merely land in different places.
- **Calibrate to a real +3, not to Tour numbers.** If Mas drives it 300 and hits 75% of greens, every golfer watching knows it is fake. All calibration targets in this spec come from real scratch/+3 benchmarks (§3).
- **The lie and wind gate the shot choice.** The situation determines which shots are even available. That constraint is what forces real decisions.
- **One fix per round.** The learning loop surfaces exactly one adjustment per round (§6). A data dump is not training.
- **Everything is an event.** The sim emits typed JSON events (§1). The renderer, the director, the overlays, the commentary, and the record book all consume the same event stream. Nothing reads engine internals directly.

---

## 1. JSON event schema

Every observable thing the engine does is emitted as a typed JSON event. Consumers (renderer, broadcast director, NodeCG overlays, commentary, clip pipeline, record book) subscribe to the event stream and never touch engine state directly.

### 1.1 Envelope (all events)

```json
{
  "type": "shot_result",
  "v": 1,
  "event_id": "evt_20261112_0042_0137",
  "ts": 1731450000000,
  "round_id": "R0042",
  "round_no": 42,
  "hole": 7,
  "shot_no": 2,
  "seq": 137
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | Event type (see §1.2). |
| `v` | int | Schema version. Always `1` for now. Bump on any breaking field change. |
| `event_id` | string | Unique id: `evt_<YYYYMMDD>_<round_no 4-digit>_<seq 4-digit>`. |
| `ts` | int | Unix epoch ms when the event was emitted. |
| `round_id` | string | `R` + zero-padded round number. |
| `round_no` | int | 1-based round counter, increments forever. |
| `hole` | int | 1–18, or `0` for round-level events. |
| `shot_no` | int | 1-based shot number within the hole, or `0` for non-shot events. |
| `seq` | int | Monotonic sequence number within the round, starting at 1. |

### 1.2 Event types

#### `round_start`

Emitted once per round, before hole 1.

```json
{
  "type": "round_start",
  "round_id": "R0042", "round_no": 42,
  "course": { "name": "Wyatt National", "par": 72, "yardage": 7602, "rating": 76.1, "slope": 142 },
  "conditions": { "wind_mph": 9, "wind_dir_deg": 310, "temp_f": 58, "sky": "partly_cloudy", "firmness": 0.62, "green_speed": 11.2 },
  "handicap_index": 3.1,
  "target_score": 59,
  "ghost_target": 68,
  "last10_avg": 71.4,
  "form": "hot",
  "focus_fix": { "area": "approach_150_175", "adjustment": "aim 4 ft further right on approaches from 150-175 yd", "source_round": "R0041" }
}
```

| Field | Description |
|---|---|
| `course.rating` / `course.slope` | USGA-style course rating and slope for Wyatt National from the back tees: **76.1 / 142**, the single v3 number (`course-rating-v3.md`). The web build's old 74.1 / 141 pair is retired — no derivation reproduces it; the identical method reproduces 74.6 / 138 for the v1 design, which survives only as a back-check. Used for handicap differentials (§7). |
| `conditions` | Round-level weather, drawn once per round (§1.4). `wind_dir_deg` is the direction the wind blows *from* (meteorological convention). `firmness` 0–1 (0 = soft, 1 = firm) scales bounce/roll. `green_speed` in feet on the Stimpmeter. |
| `handicap_index` | Mas's live WHS index at round start (§7). Note: a +3 is stored as a *negative* index in WHS terms; this spec stores it as a signed number where **positive = strokes better than scratch** (so +3.1 means 3.1 better than scratch) and displays it as `+3.1`. Document this convention wherever the value is rendered. |
| `target_score` | Always `59` — the Road to 59 season target. |
| `ghost_target` | Mason's real-world reference score for this course (default 68; configurable). Mas is "playing against" this ghost. |
| `last10_avg` | Scoring average over the most recent 10 completed rounds. |
| `form` | `hot` / `neutral` / `cold`, derived from last-3 rounds vs. last-10 average (see §7.4). Drives commentary tone and slight dispersion modulation (§3.6). |
| `focus_fix` | The single fix carried into this round from the previous round's learning loop (§6). `null` on round 1. |

#### `hole_start`

```json
{
  "type": "hole_start",
  "hole": 7, "par": 5, "yardage": 586, "name": "The Valley",
  "tee": "back",
  "pin": { "x_ft": 18, "y_ft": -6, "zone": "back_right", "difficulty": 0.71 },
  "hole_wind": { "mph": 11, "dir_deg": 295, "effect": "into_and_left" },
  "score_to_par": -2,
  "score_vs_target": 3,
  "strokes_to_59_pace": 2
}
```

| Field | Description |
|---|---|
| `pin` | Pin position in feet relative to green centre (x = left/right, + = right; y = front/back, + = back). `zone` is one of `front_left`, `front_center`, `front_right`, `mid_left`, `mid_center`, `mid_right`, `back_left`, `back_center`, `back_right`. `difficulty` 0–1 combines pin depth, tier, and nearby hazards. |
| `hole_wind` | Wind resolved for this hole's playing direction. `effect` is one of `into`, `down`, `into_and_left`, `into_and_right`, `down_and_left`, `down_and_right`, `cross_left`, `cross_right`, `calm`. |
| `score_to_par` | Cumulative score to par entering the hole. |
| `score_vs_target` | Strokes vs. the Road to 59 pace (par 72 course: 59 pace = −13; so at −2 through 6 holes he is 3 behind 59 pace after accounting for holes remaining — see §7.5). |
| `strokes_to_59_pace` | Strokes he can still afford to drop against 59 pace over the remaining holes. |

#### `shot_decision`

Emitted *before* the shot is struck. This is the decision the commentary reads aloud, so viewers can judge the execution.

```json
{
  "type": "shot_decision",
  "hole": 7, "shot_no": 2,
  "situation": { "lie": "fairway", "distance_yd": 238, "elevation_ft": 14, "wind_mph": 11, "wind_effect": "into_and_left", "to_pin_yd": 238, "hazard": "cross_bunker_90" },
  "decision": {
    "shot_type": "knockdown",
    "club": "5-iron",
    "target": { "aim_point": "right edge of green", "aim_offset_ft": 12, "intended_shape": "fade", "intended_traj": "low", "intended_carry_yd": 226 },
    "reasoning": "Uphill into the wind — club up one, knock it down, aim right edge and let the wind bring it back.",
    "alternatives_considered": [
      { "shot_type": "full", "club": "4-iron", "ev_strokes": 3.31 },
      { "shot_type": "layup", "club": "7-iron", "ev_strokes": 3.42 }
    ],
    "ev_strokes": 3.24,
    "risk": 0.31,
    "confidence": 0.78
  }
}
```

| Field | Description |
|---|---|
| `situation.lie` | One of `tee`, `fairway`, `rough_light`, `rough_heavy`, `bunker_fairway`, `bunker_green`, `trees`, `fringe`, `green`. |
| `situation.distance_yd` | Distance to the hole (yards). |
| `situation.elevation_ft` | Elevation change to the target, + = uphill. |
| `situation.hazard` | Nearest relevant hazard, or `null`. Free text from the course data (`cross_bunker_90`, `water_left`, `ob_right`, …). |
| `decision.shot_type` | One of `full`, `knockdown`, `draw`, `fade`, `punch`, `flop`, `bunker_splash`, `bunker_pick`, `chip`, `pitch`, `putt`, `layup`. Gated by lie and wind (§4). |
| `decision.club` | Club label, e.g. `driver`, `3-wood`, `5-wood`, `hybrid`, `4-iron` … `9-iron`, `PW`, `GW`, `SW`, `LW`, `putter`. |
| `decision.target` | Aim point in plain language + numeric offset (feet from pin, + = right of pin) + intended shape (`straight` / `draw` / `fade`), trajectory (`low` / `normal` / `high`), and intended carry. |
| `decision.reasoning` | One sentence, plain language, CBS/NBC cadence. This is the commentary line. |
| `decision.alternatives_considered` | Up to 2 rejected options with their expected strokes. Present so viewers (and Mason) can see the decision was a decision. |
| `decision.ev_strokes` | Expected strokes to hole out from this situation *if this shot is played* (including this shot). Computed by the decision engine (§5). |
| `decision.risk` | 0–1 probability that this shot ends in a penalty or recovery situation (water, OB, trees, plugged bunker). |
| `decision.confidence` | 0–1, the engine's confidence in the choice (high when one option dominates on EV, low when options are close). |

#### `shot_result`

Emitted when the ball comes to rest (or is holed / penalized).

```json
{
  "type": "shot_result",
  "hole": 7, "shot_no": 2,
  "club": "5-iron", "shot_type": "knockdown",
  "contact": { "quality": "pure", "strike_x_mm": 2, "strike_y_mm": -1, "face_deg": 0.8, "path_deg": -1.2, "club_speed_mph": 96 },
  "launch": { "ball_speed_mph": 139, "launch_deg": 15.2, "spin_rpm": 5200, "spin_axis_deg": -4.5, "apex_ft": 74, "carry_yd": 221, "total_yd": 232, "curve_ft": -9, "offline_ft": -7 },
  "outcome": { "lie": "green", "distance_to_pin_ft": 14, "on_green": true, "fairway_hit": null, "gir": true, "hazard": null, "penalty": 0, "in_water": false, "ob": false },
  "shot_quality": 0.82,
  "commentary": "Knocked down beautifully — rode the wind back to 14 feet.",
  "drama": 0.34
}
```

| Field | Description |
|---|---|
| `contact.quality` | One of `pure`, `thin`, `chunk`, `toe`, `heel`, `shank` (§2.4). |
| `contact.strike_x_mm` / `strike_y_mm` | Strike location on the face in mm from centre (x + = toe, y + = high on face). |
| `contact.face_deg` / `path_deg` | Face angle and club path at impact, degrees (+ = open / out-to-in for a left-handed golfer — see note below). |
| `contact.club_speed_mph` | Clubhead speed at impact. |
| `launch` | All launch-monitor outputs. `apex_ft` is apex height above the landing elevation. `curve_ft` is lateral curve during flight (+ = right of start line). `offline_ft` is final lateral error from the target line (+ = right). |
| `outcome.fairway_hit` | `true`/`false` on tee shots on par 4s/5s; `null` otherwise. A ball in the first cut counts as a miss. |
| `outcome.gir` | Green in regulation (ball on green in par − 2 strokes). |
| `outcome.penalty` | Penalty strokes incurred by this shot (0, 1, or 2). |
| `shot_quality` | 0–1, how well the shot was executed relative to intent (1 = exactly as planned). Drives the "shot of the day" logic and the clip pipeline. |
| `commentary` | One sentence, result line. Delivered at apex/landing. |
| `drama` | 0–1. Drives replay triggers: ≥ 0.75 = slow-motion instant replay; ≥ 0.9 = "moment" banner + auto-clip. |

> **Left-handed sign convention.** Mas is left-handed. All lateral signs in this spec are expressed **from the golfer's perspective facing the target**: + = to the golfer's right (which for a left-hander is the *opposite* side of the course from a right-hander's right). The renderer must mirror lateral geometry for a left-handed golfer rather than re-signing the numbers. Face/path angles use the same convention: for a left-hander, a `face_deg` of +1.0 (open) produces a fade (curve to the golfer's right); the physics (§2) is handedness-agnostic once start direction and spin axis are computed.

#### `putt_result`

Putting is a separate event type because the model is different (no launch conditions; a make-probability + distance-control model).

```json
{
  "type": "putt_result",
  "hole": 7, "shot_no": 4,
  "putt": { "distance_ft": 14, "break_ft": 1.8, "break_dir": "left_to_right", "speed": "good", "made": true, "leave_ft": 0 },
  "putts_on_hole": 1,
  "commentary": "Fourteen feet, left to right — and he pours it in."
}
```

| Field | Description |
|---|---|
| `putt.break_ft` | Total break in feet. `break_dir` is `left_to_right`, `right_to_left`, or `straight`. |
| `putt.speed` | `short`, `good`, or `long` (pace relative to the hole). A missed putt with `long` speed leaves a longer comebacker. |
| `putt.leave_ft` | Distance remaining after a miss (0 if made). |
| `putts_on_hole` | Running putt count for the hole. |

#### `hole_complete`

```json
{
  "type": "hole_complete",
  "hole": 7, "par": 5, "score": 4, "score_name": "birdie",
  "score_to_par": -3, "strokes_gained": { "ott": 0.12, "app": 0.31, "arg": 0.05, "putt": 0.18, "total": 0.66 },
  "hole_stats": { "fairway_hit": true, "gir": true, "putts": 1, "up_and_down": null, "sand_save": null, "penalties": 0, "driving_yd": 287, "approach_ft": 14 },
  "commentary": "Birdie at the Valley. Three under through seven — and the Road to 59 is alive."
}
```

| Field | Description |
|---|---|
| `score_name` | `eagle`, `birdie`, `par`, `bogey`, `double`, `triple_plus`, `hole_in_one`, `albatross`. |
| `strokes_gained` | Strokes gained vs. the +3 baseline for this hole, split by category (§6.2). |
| `hole_stats.up_and_down` | `true`/`false` when a miss-green recovery was attempted; `null` when the green was hit in regulation. |
| `hole_stats.sand_save` | `true`/`false` when a greenside-bunker up-and-down was attempted; `null` otherwise. |
| `hole_stats.driving_yd` | Tee-shot total distance (par 4s/5s only; `null` on par 3s). |
| `hole_stats.approach_ft` | Proximity of the first approach shot that reached the green, in feet (`null` if never on green). |

#### `round_complete`

```json
{
  "type": "round_complete",
  "round_id": "R0042", "round_no": 42, "score": 69, "score_to_par": -3,
  "stats": {
    "fairways": "9/14", "fairway_pct": 0.64, "gir": "12/18", "gir_pct": 0.67,
    "putts": 29, "putts_per_gir": 1.58, "scrambling_pct": 0.67, "sand_saves": "2/3",
    "driving_avg_yd": 271, "driving_longest_yd": 298,
    "approach_prox_ft": 27.4, "prox_100_125_ft": 21.0, "prox_150_175_ft": 28.5, "prox_175_200_ft": 36.0,
    "penalties": 1, "birdies": 5, "bogeys": 2, "eagles": 0
  },
  "strokes_gained": { "ott": 0.42, "app": 1.18, "arg": -0.22, "putt": 0.61, "total": 1.99 },
  "handicap": { "index_before": 3.1, "index_after": 3.2, "differential": -2.9 },
  "focus_fix": { "area": "approach_150_175", "adjustment": "aim 4 ft further right on approaches from 150-175 yd", "expected_gain": 0.4 },
  "records": { "course_record": false, "personal_best": false, "best_front9": false, "season_best": true },
  "road_to_59": { "rounds_played": 42, "rounds_under_70": 11, "best_score": 63, "strokes_from_59": 4 }
}
```

#### `milestone`

Emitted when a record, streak, or threshold is crossed mid-round or at round end.

```json
{
  "type": "milestone",
  "kind": "course_record_tied",
  "hole": 18,
  "text": "Mas ties the course record — 63 at Wyatt National.",
  "value": 63, "previous_best": 63
}
```

`kind` values: `course_record`, `course_record_tied`, `personal_best`, `season_best`, `streak_birdie_3`, `streak_bogey_free_9`, `streak_rounds_under_par`, `handicap_milestone`, `road_to_59_step`, `hole_in_one`, `eagle`, `first_eagle`, `rounds_milestone_50`, `rounds_milestone_100`.

### 1.3 Event bus contract

- Events are emitted synchronously, in order, to all subscribers. No async queue: the engine is deterministic given a seed, and async delivery would break replay determinism (§8.4).
- Each event carries `seq` (per round) so consumers can detect a dropped event.
- The renderer may throttle *display* of events (e.g. batch overlay updates) but must never drop `round_complete` or `milestone` events.
- The event stream is the **only** interface between the engine and everything else. The Unreal build, the OBS director, and NodeCG all consume this same schema — that is what makes the engine portable across the web prototype and the Unreal broadcast.

### 1.4 Round conditions model

Drawn once per round at `round_start`, from a seeded RNG:

| Variable | Distribution | Notes |
|---|---|---|
| `wind_mph` | 0–18, triangular peaking at 6 | 0–4 calm (35%), 5–10 moderate (45%), 11–18 strong (20%). |
| `wind_dir_deg` | Uniform 0–360, but biased: prevailing wind from the NW (300–330°) on 50% of rounds | Prevailing wind makes holes 4, 8, 11 play into the wind most days — by design. |
| `temp_f` | Normal(62, 10), clamped 38–88 | Affects carry: +1°F ≈ +0.15 yd carry on a driver (modelled in §2.5). |
| `sky` | Weighted: `clear` 40%, `partly_cloudy` 35%, `overcast` 15%, `light_rain` 10% | Light rain reduces roll (firmness −0.15) and raises spin slightly. |
| `firmness` | Normal(0.6, 0.12), clamped 0.25–0.9 | Scales bounce/roll (§2.5). |
| `green_speed` | Normal(11.0, 0.6), clamped 9.5–12.5 | Stimpmeter feet. Faster greens = more break, lower make rates from distance (§3.5). |
| Pin positions | Uniform over the 9 zones, one per hole, no repeats of the same zone on consecutive holes | Pin difficulty (§1.2 `hole_start`) feeds the decision engine's risk model. |

Per-hole wind is derived from round wind + hole azimuth: `hole_wind_mph = round wind × cos(angle between wind direction and hole direction)`, plus a per-hole gust factor `N(1.0, 0.12)`. The engine stores the hole azimuth for every hole in the course data so this is a pure function.

---

## 2. Shot generation: from delivery to ball flight

### 2.1 Pipeline (in order — never reorder)

```
1. SITUATION        lie, distance, elevation, wind, hazard, pin
2. DECISION         shot_type + club + target (decision engine, §5)
3. DELIVERY DRAW    club speed, path, face, strike location, angle of attack
4. CONTACT          contact quality from strike location (§2.4)
5. LAUNCH           ball speed, launch angle, spin, spin axis (§2.2)
6. FLIGHT           integrate gravity + drag + Magnus (§2.3)
7. LANDING          bounce, roll, lie determination (§2.5)
8. OUTCOME          green/fairway/hazard/penalty, distance to pin
```

Steps 3–5 are where skill lives. Steps 6–8 are physics and course geometry — identical for a +3 and a 20-handicapper. That separation is what makes the model honest: **Mas is better because his delivery distribution is tighter, not because the physics is kinder.**

### 2.2 Delivery → launch conditions

Draw the delivery from per-club normal distributions (σ values in §3.2), then convert:

**Ball speed.** `ball_speed = club_speed × smash_factor`, where smash factor depends on club and strike quality:

| Club | Smash (pure strike) | Smash (thin) | Smash (chunk) | Smash (toe/heel) |
|---|---|---|---|---|
| Driver | 1.49 | 1.44 | 1.31 | 1.40 |
| Fairway wood | 1.47 | 1.42 | 1.30 | 1.38 |
| Hybrid | 1.44 | 1.40 | 1.29 | 1.36 |
| Long iron (4–5) | 1.40 | 1.36 | 1.26 | 1.33 |
| Mid iron (6–7) | 1.38 | 1.34 | 1.25 | 1.31 |
| Short iron (8–9) | 1.35 | 1.31 | 1.23 | 1.29 |
| Wedge | 1.30 | 1.26 | 1.20 | 1.25 |

**Launch angle.** `launch_deg = loft_deg × 0.72 + aoa_effect + strike_effect`, where:
- `aoa_effect`: angle of attack contribution — driver hit up (+2° to +4° AoA adds ~1.5° launch); irons hit down (−3° to −5° AoA subtracts ~1°).
- `strike_effect`: thin strike (low on face) launches ~2° lower and hotter; chunk launches ~1.5° higher with spin loss; high-face strike launches ~1° higher.

**Spin rate.** Base spin per club (see §3.2 table), then:
- Thin: spin × 0.72 (low spin = hot, running ball).
- Chunk: spin × 0.55 and carry −12% (heavy contact kills speed and spin).
- Toe/heel: spin × 0.88.
- Rough lie: spin × 0.70 (flyer lie) or × 1.15 (heavy rough grabs the face — draw one of the two at random; a "flyer" jumps, a "grabber" spins up and falls short). This is the lie model (§4.2).
- Wind has no effect on spin; it acts on the ball in flight (§2.3).

**Spin axis (curve).** `spin_axis_deg = (face_deg − path_deg) × 0.9 + gear_effect`, where:
- Face-to-path is the primary curve driver: face open to path → fade (for a left-hander, curve to the golfer's right); face closed to path → draw.
- **Gear effect** (§2.4): off-centre strikes rotate the face at impact. Toe strike → face opens → fade bias; heel strike → face closes → draw bias. Magnitude: `gear_deg = strike_x_mm × 0.55` (toe +x opens the face for a left-hander — same sign convention as §1.2).

**Start direction.** `start_dir_deg = face_deg × 0.75 + path_deg × 0.25` (the ball starts predominantly where the face points). Intended shape is applied by biasing the *drawn* face/path values toward the target shape before conversion (§5.3).

### 2.3 Ball flight integration

Integrate with a fixed timestep of **dt = 0.01 s** (100 Hz), semi-implicit Euler. This is fast enough to be stable and cheap enough to run thousands of shots per second if needed (Monte Carlo in the decision engine, §5.4).

State: position `p` (m), velocity `v` (m/s), spin vector `ω` (rad/s, axis = spin axis).

Per step:

```
F_gravity = (0, -9.81, 0) × m
F_drag    = -0.5 × ρ × Cd × A × |v_rel| × v_rel        (v_rel = v - wind_vector)
F_magnus  = 0.5 × ρ × Cl × A × |v_rel|² × (ω̂ × v̂_rel)  (Cl ∝ spin rate)
a = (F_gravity + F_drag + F_magnus) / m
v += a × dt ; p += v × dt
```

Constants (do not tune per shot — these are the physics):

| Constant | Value | Notes |
|---|---|---|
| Ball mass `m` | 0.04593 kg | Regulation. |
| Ball diameter | 42.67 mm | Regulation. Area `A` = π(d/2)². |
| Air density `ρ` | 1.225 kg/m³ at 59°F, sea level | Adjust for temperature: `ρ = 1.225 × (288.15 / T_kelvin)`. Altitude: Wyatt National is ~1,400 ft — apply `ρ × 0.955` as a fixed course constant. |
| Drag coefficient `Cd` | 0.24 + 0.000012 × spin_rpm | Spin increases drag slightly (dimple effect). |
| Lift coefficient `Cl` | `spin_rpm / 145000` (clamped 0.02–0.35) | Linear in spin; this is the Magnus term that keeps the ball up. |
| Wind vector | From round conditions, resolved per hole | Applied as `v_rel` — the ball moves through moving air. A 10 mph headwind costs ~10–12 yd on a driver; a 10 mph tailwind gains ~6–8 yd (asymmetric because drag is quadratic). |

**Outputs captured during integration:** apex height (max y above launch elevation), carry distance (x-distance at first ground contact), total distance (carry + bounce/roll), curve (lateral displacement at landing vs. start line), flight time, and a sampled trajectory polyline (every 0.05 s, max ~120 points) for the tracer renderer.

**Performance note:** 100 Hz × ~6 s flight = ~600 steps per shot, each ~10 flops. A single shot costs ~6k flops. The decision engine's Monte Carlo (§5.4) runs 200 candidate simulations per shot = ~1.2M flops ≈ < 2 ms on any modern device. This is why the engine is fast: the physics is cheap, and there is no network.

### 2.4 Contact quality and named mishits

Strike location is drawn first, from a per-club bivariate normal (§3.2). Contact quality is then classified by strike location:

| Quality | Condition | Probability (driver, +3) | Probability (iron, +3) | Effect |
|---|---|---|---|---|
| `pure` | \|strike\| < 6 mm from centre | ~78% | ~82% | Full smash, intended launch/spin. |
| `thin` | strike_y < −8 mm (low on face) | ~7% | ~6% | Launch −2°, spin × 0.72, ball comes out hot and low, runs through the green. Smash −0.05. |
| `chunk` | strike_y < −12 mm *and* ground contact first (heavy) | ~4% | ~5% | Carry −12%, spin × 0.55, smash −0.18. Ball falls short, often in the front bunker. |
| `toe` | strike_x > +8 mm (toe side) | ~5% | ~4% | Gear effect opens face (+4–6° effective), distance −4%, curve toward fade. |
| `heel` | strike_x < −8 mm (heel side) | ~4% | ~3% | Gear effect closes face, distance −4%, curve toward draw. |
| `shank` | strike_x < −14 mm (hosel) | ~0.3% | ~0.2% | Ball rockets low and right (golfer's right), ~40% distance, usually OB or deep trouble. Rare, but it must exist — a +3 who *never* shanks is a cartoon. |

**Gear effect formula.** `gear_face_deg = strike_x_mm × 0.55`, added to face angle before launch conversion. A 10 mm toe strike adds ~5.5° of open face — a visible fade. A 10 mm heel strike subtracts ~5.5° — a visible draw. This is the single most important formula for making mishits *look* right on the tracer: the ball does not just land short, it curves.

**Thin/chunk interaction with lie.** From the fairway, thin and chunk rates are as tabled. From light rough: chunk rate × 1.6 (grass grabs the club). From heavy rough: chunk rate × 2.2, thin rate × 0.7. From a fairway bunker: thin rate × 1.8 (the classic skulled bunker shot). These multipliers are what make lies matter beyond distance.

### 2.5 Landing: bounce, roll, and lie determination

At first ground contact:

1. **Bounce.** Vertical velocity reverses with restitution `e = 0.35 × firmness + 0.15` (firm ground bounces more). Horizontal velocity retains `0.72` on the first bounce, `0.85` on subsequent bounces.
2. **Roll.** After bounces decay (vertical velocity < 1 m/s), the ball rolls with deceleration `a_roll = 9.81 × μ`, where `μ` = 0.09 (fairway), 0.16 (rough), 0.05 (green, Stimp 11), 0.22 (sand). Roll distance is integrated until velocity < 0.3 m/s.
3. **Spin effect on landing.** Backspin > 5,000 rpm on a green approach checks the ball (roll < 3 yd). Backspin < 3,000 rpm releases (roll 5–12 yd). This is why a thin (low spin) runs through the green and a chunk (low spin + short) stops in the front bunker.
4. **Lie determination.** The final resting position is tested against the course geometry (fairway polygon, rough, green, bunker shapes, water, trees, OB). The result is the next shot's `lie` (§1.2). A ball within 2 ft of a bunker edge is in the bunker. A ball in water or OB triggers the penalty procedure (§8.3).

---

## 3. Dispersion and calibration

### 3.1 The +3 benchmark table (the truth the engine must hit)

These are the targets the engine is calibrated against. They are **measured outputs** — after implementing §§2–3, run 10,000 simulated rounds and verify the engine lands within ±5% of each target. If it does not, adjust the σ values in §3.2, never the physics.

| Metric | Target (+3) | Scratch reference | Tour reference |
|---|---|---|---|
| Club speed, driver | 110 mph | 110 mph | 115–117 mph |
| Ball speed, driver | 161 mph | 161 mph | 168–172 mph |
| Smash factor, driver | 1.49 | 1.49 | 1.50 |
| Driver spin | ~2,900 rpm | ~2,900 rpm | ~2,600 rpm |
| Driving distance (total) | 265–275 yd | 244–259 yd | 282–288 yd carry |
| Fairways hit | 55–60% | ~50% | ~60% |
| Greens in regulation | ~55–57% | ~56% | ~66% |
| Scoring average | 72–74 | 72–74 | ~70 |
| Putts per round | 29–30 | ~30 | ~29 |
| Scrambling | 55–65% | ~55% | ~60% |
| Sand saves | 45–55% | ~45% | ~55% |

> **v3 note (course-design-v3.md §5.3):** the Scoring average (72–74) and GIR (~55–57%) targets above are **estimates for the 7,602-yard v3 course, pending confirmation by the 10,000-round calibration harness**. The v1 targets were 71–73 and ~60%. If the harness says otherwise, the harness is right — update this table from its results, do not argue with it.

### 3.2 Per-club delivery distributions

All values are standard deviations (σ) of normal distributions, drawn per shot. Means are the intended values from the decision engine.

| Club | Club speed σ (mph) | Face σ (deg) | Path σ (deg) | Strike x σ (mm) | Strike y σ (mm) | Carry σ (yd)¹ |
|---|---|---|---|---|---|---|
| Driver | 2.1 | 1.15 | 1.30 | 6.5 | 5.0 | 9.5 |
| 3-wood | 1.9 | 1.05 | 1.20 | 6.0 | 4.8 | 8.0 |
| 5-wood / hybrid | 1.8 | 0.95 | 1.10 | 5.5 | 4.5 | 7.0 |
| 4-iron | 1.7 | 0.90 | 1.05 | 5.2 | 4.2 | 6.0 |
| 5-iron | 1.6 | 0.85 | 1.00 | 5.0 | 4.0 | 5.5 |
| 6-iron | 1.5 | 0.80 | 0.95 | 4.8 | 3.8 | 5.0 |
| 7-iron | 1.5 | 0.75 | 0.90 | 4.5 | 3.6 | 4.5 |
| 8-iron | 1.4 | 0.70 | 0.85 | 4.2 | 3.4 | 4.0 |
| 9-iron | 1.3 | 0.65 | 0.80 | 4.0 | 3.2 | 3.5 |
| PW | 1.2 | 0.60 | 0.75 | 3.8 | 3.0 | 3.0 |
| GW | 1.1 | 0.55 | 0.70 | 3.5 | 2.8 | 2.8 |
| SW | 1.0 | 0.50 | 0.65 | 3.2 | 2.6 | 2.5 |
| LW | 1.0 | 0.50 | 0.65 | 3.2 | 2.6 | 2.5 |
| Putter | — | — | — | — | — | — (see §3.5) |

¹ Carry σ is the *emergent* standard deviation of carry distance after the full pipeline — listed here as a calibration check, not an input. If simulated carry σ differs from this column by > 10%, re-tune face/path/strike σ.

**Shot-type modifiers** (multiply the face/path σ):

| Shot type | Face/path σ multiplier | Carry σ multiplier | Notes |
|---|---|---|---|
| `full` | 1.00 | 1.00 | Baseline. |
| `knockdown` | 0.85 | 0.80 | Shorter, controlled swing = tighter dispersion. The point of the shot. |
| `draw` / `fade` (shaped) | 1.15 | 1.10 | Working the ball costs dispersion. |
| `punch` | 0.80 | 0.75 | Low, abbreviated swing under trees. |
| `flop` | 1.40 | 1.35 | High-risk, high-variance by design. |
| `bunker_splash` | 1.20 | 1.25 | Distance control is the weakness. |
| `chip` / `pitch` | 0.70 | 0.70 | Short shots are inherently tighter. |
| `layup` | 0.85 | 0.80 | Controlled, conservative swing. |

**Power modifier.** A "power" swing (driver at 105% effort, e.g. when trying to drive a par 4 or reach a par 5 in two) multiplies club-speed mean by 1.04 and face/path σ by 1.25. Power trades dispersion for distance — the decision engine must price that trade (§5.4).

### 3.3 Approach proximity truth table

Mean proximity (feet from pin) of the first approach shot that reaches the green, by distance. These are the calibration targets for the approach model:

| Distance | Target mean proximity (+3) | Tour mean |
|---|---|---|
| 50–75 yd | 9–11 ft | 8–9 ft |
| 75–100 yd | 13–15 ft | 12–13 ft |
| 100–125 yd | 17–20 ft | 15–17 ft |
| 125–150 yd | 21–24 ft | 19–21 ft |
| 150–175 yd | 25–30 ft | 24–28 ft |
| 175–200 yd | 33–38 ft | 30–34 ft |
| 200+ yd | 38–45 ft | 36–41 ft |

Proximity from the rough is ~25% worse; from a fairway bunker ~35% worse; from heavy rough ~45% worse. The engine must reproduce these differentials — they are what make the decision engine's lay-up logic correct (§5).

### 3.4 Short game truth table

| Situation | Target outcome (+3) |
|---|---|
| Chip from fringe (< 10 yd) | Leaves 3–5 ft on average; 1-putt 55% of the time. |
| Pitch 20–40 yd | Leaves 6–10 ft; up-and-down ~55%. |
| Pitch 40–60 yd | Leaves 10–16 ft; up-and-down ~45%. |
| Greenside bunker | Leaves 8–12 ft; sand save ~50%. |
| Fairway bunker (100–150 yd) | Reaches green ~55%; proximity ~40 ft when it does. |

### 3.5 Putting model

Putting does not use launch conditions. It uses a make-probability + distance-control model:

**Make probability** (Tour baselines, adjusted for a +3 who putts slightly worse than Tour from long range and equal from short range):

| Distance | Make % (Mas) | Tour make % |
|---|---|---|
| 3 ft | 99% | 99% |
| 4 ft | 97% | 97% |
| 5 ft | 90% | 91% |
| 6 ft | 78% | 80% |
| 8 ft | 58% | 60% |
| 10 ft | 38% | 40% |
| 15 ft | 22% | 24% |
| 20 ft | 13% | 14% |
| 25 ft | 8% | 9% |
| 30 ft | 5% | 6% |
| 40 ft | 2.5% | 3% |
| 50 ft+ | 1.2% | 1.5% |

Interpolate linearly between table points. Adjust for green speed: `make_pct × (11.0 / green_speed)^0.5` for putts over 10 ft (faster greens = harder from distance); no adjustment inside 10 ft. Adjust for break: `make_pct × (1 − 0.04 × break_ft)` for break over 2 ft.

**Missed-putt leave distance.** If the putt is missed, the remaining distance is drawn from: `leave_ft = putt_distance_ft × N(0.08, 0.05)` for a well-paced putt, clamped to [0.5, 6] ft. A putt with `speed = long` (drawn 12% of the time on putts over 20 ft) leaves `putt_distance_ft × N(0.18, 0.06)`, clamped to [2, 10] ft — the three-putt risk. A putt with `speed = short` (drawn 8% of the time) leaves `putt_distance_ft × N(0.15, 0.05)`.

**Three-putt rate target:** ~2–3% of greens (Tour ~2.5%). If the simulated rate exceeds 4%, the leave-distance distribution is too wide.

**Lag-putt distance control.** On putts over 25 ft, the *intended* leave is the hole; the *actual* leave follows the distribution above. This produces realistic two-putt rates (~92% from 30 ft) without a separate model.

### 3.6 Form modulation

Mas's form (§1.2) modulates dispersion slightly — enough to create hot and cold stretches, not enough to break calibration:

| Form | Face/path σ multiplier | Make % modifier (putts > 10 ft) | Duration |
|---|---|---|---|
| `hot` | 0.94 | +8% relative | Until 3-round rolling average returns within 0.5 strokes of last-10 average. |
| `neutral` | 1.00 | — | Default. |
| `cold` | 1.07 | −8% relative | Same exit condition. |

Form is derived from data (§7.4), never set arbitrarily. A cold stretch is a story ("he's lost it off the tee — three rounds running"), not a difficulty setting.

### 3.7 Calibration harness (required)

The engine ships with a calibration mode (not part of the broadcast):

```
simulate(rounds=10000, seed=fixed) → aggregate:
  driving_avg, fairway_pct, gir_pct, scoring_avg, putts_per_round,
  scrambling_pct, prox_by_distance_bucket, make_rate_by_distance_bucket
compare against §3.1 / §3.3 / §3.5 targets
report: PASS/FAIL per metric with deviation %
```

Run this harness after any change to §3.2 σ values or §2 constants. The harness must pass within ±5% on every metric before a build ships. This is the single most important quality gate in the project: **if the numbers are wrong, the show is fake.**

---

## 4. Lie and wind gating of shot choice

The decision engine (§5) may only choose from the shots the situation allows. This table is the gate — it is enforced in code, not suggested.

### 4.1 Shot availability by lie

| Lie | Allowed shot types | Forbidden | Notes |
|---|---|---|---|
| `tee` | `full`, `knockdown`, `draw`, `fade`, `layup` | `punch`, `flop`, `bunker_*`, `chip`, `pitch`, `putt` | Tee shots are full swings only (plus lay-up with an iron). |
| `fairway` | All except `bunker_*`, `punch` | `bunker_splash`, `bunker_pick` | `punch` is allowed from the fairway only when trees block the line (see §4.3). |
| `rough_light` | `full`, `knockdown`, `draw`, `fade`, `layup`, `pitch`, `chip` | `flop`, `bunker_*` | Flyer lie possible (§2.2 spin). |
| `rough_heavy` | `full`, `knockdown`, `layup`, `punch`, `pitch`, `chip` | `draw`, `fade`, `flop`, `bunker_*` | Cannot shape the ball from heavy rough — the grass grabs the face. Chunk rate × 2.2 (§2.4). Club up 2–3 clubs for distance (§4.2). |
| `bunker_fairway` | `full`, `knockdown`, `layup` | Everything else | Ball sits clean; play it like a fairway shot with a slightly open face. Thin rate × 1.8. |
| `bunker_green` | `bunker_splash`, `bunker_pick` | Everything else | `splash` (open face, sand first) is the default; `pick` (clean contact) only when the ball is sitting up. |
| `trees` | `punch`, `layup` (sideways/backwards allowed), `full` (only if a gap exists — see §4.3) | `draw`, `fade`, `flop`, `knockdown`, `bunker_*` | The punch-out is the signature recovery shot. |
| `fringe` | `chip`, `pitch`, `putt` | All full-swing types | Putter from the fringe is allowed and often correct. |
| `green` | `putt` | Everything else | |

### 4.2 Lie effects on distance and spin

| Lie | Distance factor | Spin factor | Direction control |
|---|---|---|---|
| `fairway` | 1.00 | 1.00 | Baseline. |
| `rough_light` | 0.97 | 0.70 (flyer) or 1.15 (grabber), 50/50 | Face/path σ × 1.15. |
| `rough_heavy` | 0.88, and club up 2–3 clubs | 0.60 | Face/path σ × 1.35. Carry is unreliable — the decision engine must price this. |
| `bunker_fairway` | 0.97 | 0.85 | Face/path σ × 1.10. |
| `bunker_green` | N/A (short shot) | High (splash) | Distance σ × 1.25 (§3.2). |
| `trees` (punch) | 0.55–0.70 of a full shot | Low (running) | Punch is a low runner — it stays under the branches and rolls. |

### 4.3 Wind gating

Wind does not merely move the ball — it changes which shots are correct, and the decision engine must show that reasoning:

| Wind condition | Required decision pattern |
|---|---|
| Into the wind ≥ 8 mph | Prefer `knockdown` + club up 1 (sometimes 2). Full high ball into the wind is penalized: spin × 1.15 (ballooning), carry −8%. The commentary must say so. |
| Into the wind ≥ 15 mph | `knockdown` is mandatory for approaches over 150 yd. A full shot into a 15 mph wind is a decision error the learning loop will flag (§6). |
| Downwind ≥ 8 mph | Prefer `full` with normal or high trajectory. Carry +6–8%. Knockdown downwind is a decision error (leaves the ball short). |
| Crosswind ≥ 10 mph | Aim offset must account for drift: `aim_offset_ft = wind_mph × carry_yd × 0.011` (empirical; ~15 yd drift on a 250 yd drive in a 10 mph crosswind). Shaped shots *into* the crosswind (fade into a left-to-right wind) are preferred — the wind holds the shape. |
| Uphill ≥ 10 ft elevation | Club up 1 per 12 ft of elevation (standard: 1 club per 10–15 ft). |
| Downhill ≥ 10 ft elevation | Club down 1 per 15 ft of elevation. |

### 4.4 The tree problem (draw around a tree / punch out)

When the direct line to the target is blocked by trees:

1. **If a shaped shot can go around:** the decision engine evaluates `draw` or `fade` around the obstacle (allowed only from `fairway` or `rough_light`). The required curve is computed from the obstacle position; if the required curve exceeds 25 ft of lateral movement, the shaped shot is rejected as too risky and the engine falls back to a lay-up or punch.
2. **If no shaped shot works:** `punch` (low runner under the branches) or `layup` (sideways to the fairway). The engine picks whichever has the lower expected strokes (§5.4).
3. **The hero shot is never the default.** A full shot *through* a gap is allowed only when the gap is ≥ 15 ft wide and the required carry over trouble is < 150 yd. Otherwise it is excluded by the gate. Mas is a +3, not a daredevil — and when he *does* take the hero shot and pulls it off, the drama score (§1.2) spikes, because it was genuinely rare.

---

## 5. The local on-device decision engine

### 5.1 What it is

A compact, deterministic decision procedure — **not** a neural network, **not** an API call. It is a small set of golf rules + a Monte Carlo expected-strokes evaluator, running entirely in the page (or in the sim process for the Unreal build). It is "local models" in the sense that matters: a small, focused model that knows golf deeply, runs in milliseconds, and never leaves the device.

Why not a neural network? Because the decision problem is small and structured: ~10 candidate shots × a physics model that is already exact. A Monte Carlo over the true physics beats a learned approximation on accuracy, is fully explainable (the commentary can quote *why*), costs nothing to run, and cannot hallucinate. If a learned model is ever added, it belongs as a *prior* over candidate ranking (which shots to simulate first), never as a replacement for the physics evaluation.

### 5.2 Decision procedure (per shot)

```
INPUT: situation (lie, distance, elevation, wind, hazard, pin, score state)
1. GATHER candidates: all (shot_type, club) pairs allowed by the §4 gate
   for this lie. Typically 4–10 candidates.
2. For each candidate:
   a. Compute intended launch conditions (club + shot-type modifiers).
   b. MONTE CARLO: simulate N=200 shots through the §2 pipeline,
      drawing delivery from the §3.2 distributions (with form modulation).
   c. For each simulated outcome, compute strokes-to-hole-out from the
      resulting position using the baseline table (§5.5) + 1 for the shot.
   d. ev_strokes = mean(strokes-to-hole-out). risk = P(penalty or recovery).
3. RANK by ev_strokes. Apply the risk rule (§5.3).
4. SELECT the best candidate. Emit shot_decision (§1.2) with the top 2
   rejected alternatives and their EV.
5. EXECUTE: draw ONE delivery from the distributions and run the real shot
   through §2. (The Monte Carlo is for decision-making; the actual shot is
   a single fresh draw — never reuse a Monte Carlo sample as the real shot.)
OUTPUT: shot_decision event, then shot_result event.
```

### 5.3 Risk rule

Pure EV minimization produces a golfer who takes every hero shot — the math says a 30% chance of eagle is worth it, but a human +3 does not play that way, and viewers would not believe it. The risk rule:

- Compute `ev_best` (lowest EV) and `ev_safe` (lowest EV among candidates with `risk ≤ 0.15`).
- If `ev_safe − ev_best ≤ 0.15` strokes, choose the safe candidate. (A hero shot must be worth at least 0.15 strokes to be worth the risk.)
- On the **last 3 holes of a round**, when Mas is within 2 strokes of the course record or the Road to 59 pace, the threshold tightens to 0.08 (he gets more aggressive when the record is in reach — and the commentary says so).
- When Mas is **4+ strokes behind 59 pace** with ≤ 6 holes left, the threshold loosens to 0.25 (he presses; the comeback is the story).
- The risk rule is the single most important tuning knob for believability. If Mas looks reckless, tighten it. If he looks cowardly, loosen it.

### 5.4 Performance budget

| Operation | Budget | How |
|---|---|---|
| Candidate generation | < 0.1 ms | Table lookups only. |
| Monte Carlo (200 sims × ~8 candidates) | < 2 ms | §2.3 physics at ~6k flops/shot = ~10M flops total. Typed arrays, no allocation in the hot loop. Pre-allocate the trajectory buffer once. |
| Baseline lookup (§5.5) | < 0.01 ms | Interpolated table, no computation. |
| Total per shot | **< 5 ms** | Measured on a 2021 mid-range phone. If it exceeds 5 ms, reduce N to 120 (still statistically stable for EV ranking — the standard error on EV at N=120 is ~0.03 strokes). |

**No caching across shots** (each situation is different), but the baseline table (§5.5) and the per-club distribution parameters are loaded once at startup and never recomputed. The engine holds no state between shots except the golfer model (§6) and the round state (§8) — this makes it trivially restartable and testable.

### 5.5 Strokes-to-hole-out baseline table

Expected strokes to hole out from a given situation, for a +3 golfer, used inside the Monte Carlo (step 2c). This is the engine's "putting a value on every position" — it is what makes lay-ups, hero shots, and punch-outs comparable.

| Situation | Expected strokes to hole out |
|---|---|
| On green, 5 ft | 1.10 |
| On green, 10 ft | 1.62 |
| On green, 20 ft | 1.87 |
| On green, 30 ft | 1.95 |
| On green, 50 ft | 1.99 |
| Fairway, 50 yd | 2.55 |
| Fairway, 100 yd | 2.75 |
| Fairway, 150 yd | 2.95 |
| Fairway, 200 yd | 3.20 |
| Fairway, 250 yd (par 5, going for it) | 3.45 |
| Rough (light), 100 yd | 2.95 |
| Rough (light), 150 yd | 3.15 |
| Rough (heavy), 100 yd | 3.25 |
| Rough (heavy), 150 yd | 3.50 |
| Greenside bunker | 2.75 |
| Fairway bunker, 150 yd | 3.30 |
| Trees (punch-out to fairway) | 3.60 |
| Water / OB (after penalty drop) | 4.10 |

Interpolate linearly between distances. The table is for a +3; the learning loop (§6) adjusts it per-golfer over time (e.g. if Mas's actual scrambling is better than baseline, his table improves and he takes slightly more aggressive lines — that is the self-improvement, visible in the decisions).

### 5.6 Club gapping (the golfer's bag)

Fixed carry distances (calm, sea level, flat) for Mas's bag. The decision engine uses these to select clubs; the physics (§2) produces the actual carry with wind/elevation/lie applied.

| Club | Carry (yd) | Loft | Notes |
|---|---|---|---|
| Driver | 268 | 9.0° | Total ~272 with roll. |
| 3-wood | 245 | 15° | |
| 5-wood | 228 | 18° | |
| Hybrid (3) | 218 | 20° | |
| 4-iron | 205 | 23° | |
| 5-iron | 193 | 26° | |
| 6-iron | 182 | 29° | |
| 7-iron | 171 | 32° | |
| 8-iron | 160 | 36° | |
| 9-iron | 148 | 40° | |
| PW | 136 | 44° | |
| GW | 122 | 50° | |
| SW | 108 | 54° | |
| LW | 92 | 58° | |
| Putter | — | — | |

Club selection rule: choose the club whose carry (adjusted for wind/elevation/lie per §4.3) is closest to the required carry, preferring to be slightly long on approaches (long is safer than short on most holes — the course design guarantees this) and slightly short on tee shots into trouble.

---

## 6. The strokes-gained learning loop

### 6.1 Why approach and driving first

Mark Broadie's finding holds at every level: the long game (> 100 yd) explains ~⅔ of scoring variation; putting explains only ~15% of the gap between top-10 and average Tour pros. Going from 90 → 80, approach is ~40% of the improvement, driving ~28%, short game ~17–19%, putting ~14–15%. **The learning loop therefore optimizes approach proximity and driving first.** A +3's practice priorities are not "make more putts" — and the broadcast should teach this.

### 6.2 Strokes-gained computation

After every shot, compute strokes gained vs. the +3 baseline (§5.5):

```
SG_shot = baseline_strokes_from_start_position
        - (1 + baseline_strokes_from_end_position)
        - penalty_strokes
```

Categorize each shot:

| Category | Shots |
|---|---|
| `ott` (off the tee) | Tee shots on par 4s and 5s. |
| `app` (approach) | All shots from > 100 yd that are not tee shots, plus par-3 tee shots. |
| `arg` (around the green) | Shots from ≤ 100 yd that are not on the green and not putts. |
| `putt` | All putts. |

Accumulate per hole and per round. The round totals in `round_complete` (§1.2) are the primary learning signal.

### 6.3 The one-fix rule

After each round, the learning loop:

1. **Ranks the four categories by strokes gained** (worst first).
2. **Drills into the worst category** by sub-bucket:
   - `ott`: by miss direction (left/right) and by hole type (tight vs. open).
   - `app`: by distance bucket (100–125, 125–150, 150–175, 175–200, 200+).
   - `arg`: by situation (bunker, rough, pitch distance).
   - `putt`: by distance bucket (inside 6 ft, 6–15 ft, 15+ ft lag).
3. **Finds the single worst sub-bucket** with at least 3 samples in the last 5 rounds (small samples are noise — never "fix" something based on one shot).
4. **Produces exactly one fix**, in this format:

```json
{
  "area": "approach_150_175",
  "finding": "Losing 0.42 strokes/round on approaches from 150-175 yd — missing 68% left of the pin.",
  "adjustment": "aim 4 ft further right on approaches from 150-175 yd",
  "expected_gain": 0.4,
  "mechanism": "aim_offset_ft",
  "magnitude": 4,
  "applies_to": { "category": "app", "distance_min_yd": 150, "distance_max_yd": 175 }
}
```

5. **Applies the fix mechanically.** The `mechanism` field names a real engine parameter that changes:
   - `aim_offset_ft`: shifts the aim point on the affected shots by `magnitude` feet (toward the miss correction).
   - `club_up`: takes one more club on the affected shots.
   - `trajectory`: forces `knockdown` (or `high`) on the affected shots.
   - `target_line`: aims at the fat of the green instead of the pin on the affected shots.
   - `aggression`: adjusts the risk-rule threshold (§5.3) by ±0.03 for the affected situations.
6. **The fix persists** until a later round's loop replaces it. Only one fix is active at a time. The active fix is shown in `round_start.focus_fix` and on the broadcast as "Mas's one thing this week."

**Worked example.** After round 41, the loop finds Mas is losing 0.42 strokes/round on 150–175 yd approaches, missing 68% left. The fix: aim 4 ft further right on those shots. In round 42, his 150–175 yd approaches aim 4 ft right of the computed target. If the miss pattern corrects, the category SG improves, the fix is marked "working," and the loop moves to the next-worst area. If it does not correct after 3 rounds, the loop escalates the magnitude (4 ft → 7 ft) or switches mechanism (aim → club_up). This is visible, mechanical self-improvement — not a label.

### 6.4 The golfer model (what actually changes)

The learning loop modifies three things, and only three things:

| Component | What changes | Effect |
|---|---|---|
| Aim biases | Per-distance-bucket aim offsets (± ft) | Corrects systematic misses. |
| Risk threshold | §5.3 threshold ±0.03 | Corrects systematic over/under-aggression. |
| Baseline table | §5.5 values, adjusted by ±0.05 strokes per bucket based on observed performance over the last 20 rounds | The engine's *expectations* adapt to Mas's actual skill. If his scrambling is genuinely better than baseline, the table improves and he takes slightly more aggressive lines. |

The dispersion σ values (§3.2) do **not** change with the learning loop. Mas does not magically get a tighter swing from thinking about it — he gets *smarter*. If a future version wants swing improvement, it comes from a separate, slower mechanism (e.g. a "practice" system that tightens σ by 1% per 20 rounds, capped at 5% total). That is out of scope for v1.0.

### 6.5 What the loop must never do

- Never adjust based on a single round (minimum 3 rounds of data in the affected bucket).
- Never stack multiple fixes (one active fix, always).
- Never change the physics constants (§2.3) or the calibration targets (§3.1).
- Never make Mas worse on purpose for drama. Cold stretches come from form modulation (§3.6) and honest variance, not from sabotage.

---

## 7. Handicap, leaderboard, and records

### 7.1 Live WHS-style handicap index

Mas's handicap is a live, moving number — the season arc in one number.

**Differential per round.** `differential = (score − course_rating) × 113 / slope`. Wyatt National: rating 76.1, slope 142 (from the back tees — `course-rating-v3.md`). A score of 69 gives `(69 − 76.1) × 113 / 142 = −5.6`. A score of 74 gives `−1.7`. (Negative differentials are *good* — they mean better than the course rating.)

**Index calculation (simplified WHS).** Take the best 8 differentials from the most recent 20 rounds, average them, multiply by 0.96. If fewer than 20 rounds exist, use the WHS table for small samples (best 1 of 3, best 2 of 6, best 3 of 9, etc.). If fewer than 3 rounds exist, no index is shown — display "establishing."

**Display convention.** This spec stores the index as a signed number where **positive = strokes better than scratch** (so +3.1 displays as `+3.1`). Internally, `display_index = −(whs_index)` where `whs_index` is the standard WHS value (negative for a plus handicap). Document this wherever the value is rendered. A +3 golfer's WHS index is approximately −3.0; Mas starts at +3.1 and moves with form.

**Update cadence.** The index updates once per round, at `round_complete`. The broadcast shows the live index in the scorebug, the trend (▲/▼/— vs. last round), and a sparkline of the last 20 rounds.

### 7.2 Leaderboard aggregates

All aggregates are computed from the completed-rounds store. They are displayed in the Record Book.

| Aggregate | Definition |
|---|---|
| **All-time score** | Sum of (score − par) across all completed rounds. Displayed as e.g. "−41 over 42 rounds" and as an average ("−0.98 per round"). |
| **Last-10 aggregate** | Sum and average of (score − par) over the most recent 10 rounds. The form line viewers follow. |
| **Last-10 scoring average** | Mean score over the most recent 10 rounds (e.g. 71.4). |
| **Best round** | Lowest score, with date/round number. |
| **Worst round** | Highest score, with date/round number. |
| **Best front 9 / back 9** | Lowest 9-hole scores, with round numbers. |
| **Course record** | Lowest score at Wyatt National (== best round on this course; kept separate so future courses have their own records). |
| **Streaks** | Current and best: rounds under par, bogey-free rounds, rounds with a birdie or better on every par 5, consecutive fairways hit, consecutive greens hit. |
| **Road to 59** | Rounds played, rounds under 70, best score, strokes from 59 (59 − best score, or "achieved" with date). |
| **Handicap history** | Index after every round (sparkline + table). |

### 7.3 Season framing: Road to 59

59 is the number. The season is framed as the chase for a sub-60 round:

- The broadcast always shows `strokes_from_59` (59 − best score) and the live 59 pace during a round (§1.2 `hole_start.score_vs_target`).
- 59 pace on a par-72 course is −13. The pace tracker shows, at every hole, how many strokes he can still afford to drop against that pace.
- When Mas finishes a round within 3 strokes of 59, the next round's `round_start` flags it (`road_to_59: { "in_contention": true }`) and the commentary leans into it.
- If/when he shoots 59 (or better), it is a `milestone` event (§1.2), the season resets to a new chase (Road to 58), and the achievement is permanently recorded with its date.

### 7.4 Form

Derived, never set:

```
last3_avg = mean score of last 3 rounds
last10_avg = mean score of last 10 rounds
if last3_avg <= last10_avg - 1.5: form = "hot"
elif last3_avg >= last10_avg + 1.5: form = "cold"
else: form = "neutral"
```

Form drives §3.6 dispersion modulation and commentary tone. It is recomputed at every `round_complete`.

### 7.5 59-pace arithmetic (for implementers)

```
par = 72
target = 59
pace_to_par = target - par = -13            # total strokes under par needed
holes_played = n
par_for_holes_played = sum of par for holes 1..n
expected_score_at_pace = par_for_holes_played + pace_to_par × (n / 18)
score_vs_target = actual_score_so_far - expected_score_at_pace
strokes_to_59_pace = (par_for_remaining_holes) + pace_to_par × (remaining / 18) - (score needed)
```

Simpler operational version (what the broadcast shows): `strokes_remaining_vs_59 = 59 − (score_so_far + par_remaining)`. If positive, he can still afford that many over-par strokes on the remaining holes and shoot 59. If negative, 59 is gone for this round (the broadcast says so once, then moves on — no dwelling).

---

## 8. The round loop and state machine

### 8.1 Top-level state machine

```
IDLE → ROUND_START → HOLE_START → SHOT_DECISION → SHOT_EXECUTION
  → SHOT_RESULT → (PUTT_RESULT)* → HOLE_COMPLETE → HOLE_START (next)
  → ROUND_COMPLETE → LEARNING_LOOP → ROUND_START (next round)
  → forever
```

There is no terminal state. The loop runs indefinitely. The only exits are process shutdown and explicit pause (screensaver/ambient mode pauses *rendering*, never the simulation — the sim can run headless and the renderer catches up on resume).

### 8.2 Hole state machine

```
HOLE_START
  → position = tee, shot_no = 1
  → LOOP:
      DECISION  (decision engine, §5; emits shot_decision)
      EXECUTION (physics, §2; ball flight + landing)
      RESULT    (emits shot_result; update position, lie, score)
      IF ball holed: → HOLE_COMPLETE
      IF ball in water/OB: apply penalty (§8.3), drop, continue LOOP
      IF ball on green: switch to PUTT sub-loop
      ELSE: shot_no += 1, continue LOOP
  → PUTT sub-loop:
      LOOP:
        DECISION (putt: read break, choose pace — a simplified §5 with
                  only the putting model §3.5)
        EXECUTION (putt_result event)
        IF holed: → HOLE_COMPLETE
        ELSE: shot_no += 1, continue PUTT sub-loop
  → HOLE_COMPLETE (emits hole_complete; update round score, stats, SG)
```

**Shot cap.** A hole is capped at 12 shots (including penalties). If the cap is reached without holing out, the hole is recorded at 12 with a `triple_plus` score and the loop advances. This is a safety valve against pathological states (e.g. repeated water balls); it should essentially never trigger, and if it does more than once in 1,000 rounds, that is a bug in the physics or the decision engine, not a feature.

### 8.3 Penalties and drops

| Situation | Procedure |
|---|---|
| Ball in water | 1 penalty stroke. Drop at the designated drop zone (course data) or behind the hazard on the line of entry. Next shot is played from the drop position. |
| Ball out of bounds | Stroke and distance (1 penalty + replay from the previous position). This is the correct rule and the harshest outcome — it is why the risk rule (§5.3) prices OB so heavily. |
| Ball unplayable (e.g. under a tree root, against a boundary) | 1 penalty stroke, drop within two club-lengths. Drawn rarely (only when the lie is `trees` and the punch-out fails badly). |
| Lost ball | Treated as OB (stroke and distance). |

Penalty strokes are counted in the score and in the `penalties` stat. The decision engine's Monte Carlo prices them through the baseline table (§5.5: water/OB = 4.10 expected strokes).

### 8.4 Determinism and replay

- The engine is seeded per round: `seed = hash(round_no, course_id)`. All RNG draws (weather, delivery, contact, putts) come from a single seeded PRNG (mulberry32 or equivalent — fast, small, deterministic across platforms).
- Given the same seed, the engine produces the identical round. This enables:
  - **Replay:** any round can be re-simulated exactly for the clip pipeline or a "watch that round again" feature.
  - **Testing:** the calibration harness (§3.7) uses fixed seeds.
  - **Debugging:** a reported weird shot can be reproduced from its round/shot number.
- The live broadcast uses `seed = hash(round_no, course_id, session_start_timestamp)` so each session's rounds differ from previous sessions, while remaining reproducible within the session.

### 8.5 Timing and pacing (broadcast vs. simulation)

The simulation and the broadcast run on **separate clocks**:

- **Simulation clock:** as fast as possible. A full round simulates in < 50 ms of CPU. The engine can (and does) run ahead — simulating the next 2–3 holes while the broadcast is still showing the current one. This is what makes the director's job possible: it knows what's coming.
- **Broadcast clock:** human-paced. A shot takes ~8–15 seconds of screen time (address, waggle, swing, flight, reaction, walk). A hole takes ~2–4 minutes. A round takes ~45–70 minutes. The broadcast consumes events from a queue at broadcast pace; the sim fills the queue as fast as it can.
- **The queue is the decoupling point.** If rendering stalls, the sim keeps going and the queue grows. If the viewer pauses, the sim pauses too (the queue stops being consumed, and the sim stops producing once the queue reaches 3 holes of lookahead — no unbounded memory growth).
- **Speed controls** (1×, 2×, 4×, Turbo) change only the broadcast consumption rate, never the simulation. Turbo mode is how the audit verified 6 holes in minutes — the sim had already finished the round.

### 8.6 Persistence

| Data | Store | Notes |
|---|---|---|
| Completed rounds (full event log) | Local JSON file / localStorage, capped at last 200 rounds | Older rounds are summarized (score + stats only) and the full log discarded. |
| Aggregates (leaderboard, records, handicap history) | Same store, updated at each `round_complete` | Recomputed from the rounds store on load (never trusted blindly — recompute is cheap). |
| Golfer model (aim biases, risk threshold, baseline adjustments) | Same store | Loaded at startup, saved after each learning-loop run. |
| Clubhouse Coins balances | localStorage (per viewer) | Viewers' coins are client-side; the broadcast never depends on them. |
| Current round state | In-memory only | If the page reloads mid-round, the round restarts from hole 1 with the same seed (deterministic — the viewer sees the same shots). |

### 8.7 Failure modes and invariants

The engine must maintain these invariants at all times; violating one is a bug:

1. **The ball always ends up somewhere legal.** After every shot, the ball has a valid lie. No NaN positions, no ball stuck inside geometry.
2. **The score always adds up.** Sum of hole scores == round score. Sum of shot counts (including penalties) == hole score.
3. **The loop never blocks.** No network, no I/O, no user input in the hot path. The only I/O is persistence at `round_complete`.
4. **The loop never ends.** `ROUND_COMPLETE` always transitions to `LEARNING_LOOP` → `ROUND_START`. There is no code path that stops the loop except process shutdown.
5. **Events are emitted in order.** `shot_decision` always precedes its `shot_result`. `hole_complete` always follows the final shot of the hole.
6. **The handicap never jumps absurdly.** Index change per round is clamped to ±0.5. If the computed change exceeds that, the computation is wrong.

---

## 9. Data tables the implementer needs

### 9.1 Course data format (Wyatt National)

One JSON object per course. The engine reads it at startup; the renderer reads the same file for geometry. (The `rating`/`slope` in the example are the v3 values — 76.1 / 142, see §1.2. Hole yardages below are v3: hole 1 is 432 yards.)

```json
{
  "id": "wyatt_national",
  "name": "Wyatt National",
  "location": "Staunton, VA",
  "par": 72, "rating": 76.1, "slope": 142,
  "holes": [
    {
      "hole": 1, "par": 4, "yardage": 432, "name": "The Handshake",
      "tee": { "x": 0, "y": 0, "elev_ft": 0 },
      "fairway": { "poly": [[...]], "width_yd": 32 },
      "green": { "cx": 380, "cy": 12, "elev_ft": -8, "radius_ft": 42, "tiers": 2 },
      "bunkers": [ { "cx": 290, "cy": -14, "rx_ft": 24, "ry_ft": 14, "type": "fairway" } ],
      "water": [],
      "trees": [ { "x": 200, "y": -30, "r_ft": 12 } ],
      "dogleg": { "at_yd": 0, "angle_deg": 0 },
      "azimuth_deg": 42
    }
  ]
}
```

Coordinates are in a per-hole local frame: x = distance along the hole's centreline (yards), y = lateral offset (yards, + = golfer's right). The engine converts to world coordinates only for the renderer. `azimuth_deg` is the hole's playing direction (for wind resolution, §1.4).

### 9.2 Golfer profile (Mas)

```json
{
  "id": "mas",
  "name": "Mas",
  "full_name": "Mason Wyatt",
  "handedness": "left",
  "handicap_index": 3.1,
  "bag": "standard_14_clubs",
  "swing": { "tempo": "smooth", "finish": "high_balanced", "ball_flight": "slight_draw" },
  "tendencies": { "miss_bias": "left", "miss_bias_strength": 0.12 }
}
```

`tendencies.miss_bias` is the *starting* aim bias the learning loop corrects over time (§6.3). Mas's natural miss is left (a slight draw that overcooks) — this is a real, human detail that gives the learning loop something to fix in the early rounds.

---

## 10. Verification checklist (ship gates)

Before any build ships, verify:

- [ ] Calibration harness (§3.7) passes within ±5% on all metrics over 10,000 rounds.
- [ ] A single round simulates in < 50 ms of CPU (excluding rendering).
- [ ] A single shot decision completes in < 5 ms.
- [ ] 1,000 consecutive rounds complete with zero invariant violations (§8.7).
- [ ] The loop runs 24 hours unattended with no memory growth beyond the 3-hole lookahead queue (§8.5).
- [ ] Every event type in §1.2 is emitted at least once in a 10-round sample, in the correct order.
- [ ] The learning loop produces exactly one fix per round, and the fix changes a real engine parameter (§6.3).
- [ ] The handicap moves by ≤ 0.5 per round and trends sensibly over 100 rounds.
- [ ] A replayed round (same seed) produces byte-identical events (§8.4).
- [ ] No network calls, no paid services, no API keys anywhere in the engine.

---

## Appendix A. Glossary

| Term | Meaning |
|---|---|
| **Brain** | The simulation engine specified here. |
| **Director** | The broadcast state machine that cuts cameras on events. |
| **EV (expected strokes)** | Mean strokes to hole out from a position, used to rank decisions. |
| **GIR** | Green in regulation (on the green in par − 2 strokes). |
| **Ghost target** | Mason's real-world reference score (default 68) that Mas plays against. |
| **Road to 59** | The season arc: the chase for a sub-60 round. |
| **SG** | Strokes gained vs. the +3 baseline. |
| **WHS** | World Handicap System. |
| **Clubhouse Coins** | Closed-loop play money for viewer predictions. Free, earned by watching, never purchasable or convertible. |

## Appendix B. What is deliberately out of scope for v1.0

- Neural-network decision models (the Monte Carlo + rules engine is the v1.0 decision engine; a learned prior over candidate ranking is a v2.0 option).
- Swing improvement (σ tightening) — v1.0 improves *decisions*, not the swing (§6.4).
- Multiplayer / ghost rounds against other players' data.
- Real-money or crypto features — permanently out of scope until counsel reviews (see `livestream-plan.md` §5).
- Weather beyond the §1.4 model (no lightning delays, no frost delays — the stream never stops).
