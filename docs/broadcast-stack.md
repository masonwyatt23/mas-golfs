# Mas Golfs — Broadcast Stack Implementation Guide

**Purpose:** the complete implementation spec for the autonomous broadcast system that turns the Mas Golfs simulation into a 24/7 livestream. An engineer should be able to build directly from this document without asking questions.

**Design constraints (non-negotiable):**
- **Free-tier only.** OBS Studio (free), NodeCG (open source), YouTube Live + Twitch (free), Restream free tier (2 channels). No paid services anywhere in the stack. Paid options appear only as documented fallbacks.
- **Fully autonomous.** No human operator at any point. The stream runs 24/7, recovers from failures on its own, and never goes dark.
- **Render once, broadcast to everyone.** One render source, one OBS instance, one RTMP feed out. Platforms distribute to unlimited viewers at zero marginal cost.
- **Event-driven, not clock-driven.** Every cut, graphic, replay, commentary line, and sound is triggered by a simulation event — never by a timer.

---

## 0. System overview

```
┌─────────────────────────────────────────────────────────────────┐
│  SIM ENGINE (Python/Node)                                       │
│  - shot physics, decisions, scoring, learning loop              │
│  - emits typed JSON events on the event bus                     │
└──────────────┬──────────────────────────────────────────────────┘
               │ JSON events (WebSocket / local socket)
       ┌───────┼───────────────────────┬───────────────┐
       ▼       ▼                       ▼               ▼
┌────────────┐ ┌────────────┐  ┌──────────────┐ ┌──────────────┐
│ DIRECTOR   │ │ NODECG     │  │ COMMENTARY   │ │ AMBIENT      │
│ (state     │ │ GRAPHICS   │  │ PIPELINE     │ │ AUDIO        │
│  machine)  │ │ (replicant │  │ (LLM → TTS)  │ │ ENGINE       │
│  → OBS     │ │  state)    │  │ → OBS audio  │ │ → OBS audio  │
│  websocket │ │  → browser │  │              │ │              │
│            │ │  sources   │  │              │ │              │
└────────────┘ └────────────┘  └──────────────┘ └──────────────┘
       │              │               │               │
       └──────────────┴───────────────┴───────────────┘
                              ▼
                    ┌──────────────────┐
                    │ OBS STUDIO       │
                    │ scenes + audio   │
                    │ → RTMP → Restream│
                    │ → YouTube + Twitch│
                    └──────────────────┘
```

**One machine, one OBS.** Render source (web build now, Unreal later), OBS, NodeCG, the director, the commentary pipeline, and the ambient engine all run on the same box. No SRT, no NDI Bridge, no remote contribution — those only enter the picture if the render moves to a different machine than the encoder.

**The event bus is the spine.** Every component consumes the same typed JSON events. Build the event bus and the event schema first (Section 1); everything else is a consumer.

---

## 1. Event bus and JSON event schema

### 1.1 Transport

- **Local WebSocket server** (Node.js, `ws` package) on `localhost:4456` — deliberately one port above the OBS websocket (4455) so the two are never confused.
- Sim engine connects as the single publisher. Director, NodeCG server extension, commentary pipeline, and ambient engine connect as subscribers.
- Messages are JSON objects, one event per message, newline-delimited over the socket. No batching: an event is emitted the moment it happens in the sim.
- On subscriber reconnect, the server re-sends the latest `round_state` snapshot (Section 1.3) so a restarted component is never stale.

### 1.2 Event types

Every event has the same envelope:

```json
{
  "event": "<event_type>",
  "seq": 1234,
  "ts": "2026-11-12T06:00:00.000Z",
  "round": 47,
  "hole": 12,
  "data": { "...type-specific fields..." }
}
```

| Event | When emitted | `data` fields |
|---|---|---|
| `round_start` | First tee shot of a new round | `course`, `par`, `target_score` (59), `last10_avg`, `handicap` |
| `hole_start` | Arriving at a new hole | `hole`, `par`, `yards`, `hole_name`, `pin`, `wind_mph`, `wind_dir`, `elevation_ft` |
| `decision` | Golfer has chosen a shot, **before** the swing | `club`, `shot_type` (full / knockdown / draw / fade / punch / flop / chip / putt), `target_yards`, `aim`, `reason`, `risk` (safe / standard / aggressive), `lie`, `wind_mph`, `wind_dir` |
| `shot_start` | Address/waggle begins | `club`, `shot_type` |
| `strike` | Club meets ball (impact frame) | `club_speed_mph`, `ball_speed_mph`, `launch_deg`, `spin_rpm`, `spin_axis_deg`, `smash_factor`, `contact` (pure / thin / chunk / toe / heel) |
| `apex` | Ball reaches apex | `apex_ft`, `carry_yds`, `shape` (draw / fade / straight), `curve_yds` |
| `landing` | Ball comes to rest | `total_yds`, `lie` (fairway / rough / bunker / green / water / trees), `dist_to_pin_ft`, `result` (fairway_hit / green_hit / missed_left / missed_right / short / long / in_water / in_trees) |
| `putt_result` | Each putt | `dist_ft`, `made` (bool), `putts_this_hole` |
| `hole_end` | Hole completed | `score`, `score_to_par`, `fairway_hit`, `gir`, `putts`, `up_and_down`, `strokes_gained` (per category) |
| `milestone` | Records, streaks, thresholds | `type` (course_record_pace / birdie_streak / bogey_free_streak / best_round_pace / handicap_change / round_record), `detail` |
| `round_end` | 18th hole completed | `score`, `score_to_par`, `round_stats` (fairways, gir, putts, up_and_downs, strokes_gained), `learning_fix` (the single fix — see Section 1.4), `new_handicap`, `rank` (all-time) |
| `round_state` | Snapshot, on request/reconnect | Full current state (Section 1.3) |

### 1.3 `round_state` snapshot

Sent on subscriber connect and after every `hole_end`. This is the single source of truth for all graphics:

```json
{
  "golfer": "Mas",
  "round": 47,
  "hole": 12,
  "hole_par": 3,
  "score_to_par": -2,
  "thru": 11,
  "target_score": 59,
  "handicap": "+3.1",
  "last10_avg": 70.4,
  "all_time_score": -41,
  "course_record": 63,
  "best_round": 64,
  "current_hole": { "name": "The Picture", "par": 3, "yards": 164 },
  "scorecard": [ { "hole": 1, "par": 4, "score": 4, "putts": 2 }, "..." ],
  "stats": { "fairways": "6/11", "gir": "7/11", "putts": 19, "up_and_downs": "2/3" },
  "streak": { "birdies": 2, "bogey_free": 5 },
  "coins": { "prediction_open": true, "question": "Birdie or better on 12?", "odds": { "yes": 2.4, "no": 1.6 } }
}
```

### 1.4 The learning fix

`round_end.learning_fix` is a single object, always exactly one item — the biggest strokes-gained leak and the single adjustment:

```json
{ "leak": "approach_125_150", "strokes_lost": 1.8,
  "adjustment": "Aim 5 yards right of pin from 125–150; dispersion is left-biased" }
```

The learning loop (see `docs/architecture.md`) computes this. The broadcast surfaces it on the leaderboard card and in the commentary at the start of the next round. Never more than one fix per round — a data dump is not training.

---

## 2. OBS scene collection

**OBS Studio 33** (current stable). obs-websocket is bundled since v28 — no plugin needed for the API. WebSocket on `localhost:4455`, no authentication on a locked-down local box (or a strong password in the OBS config if the box is shared).

### 2.1 Scenes (8 total)

| # | Scene | Purpose | When active |
|---|---|---|---|
| 1 | `TEE_DTL` | Down-the-line tee camera | Address, waggle, swing, impact |
| 2 | `TRACER` | Ball-flight tracking camera with tracer | Strike → landing |
| 3 | `CATCH` | Down-the-fairway catch camera | Ball flight (alternate angle), landing |
| 4 | `BUNKER` | Low-angle bunker camera | Shots from sand, approaches to bunkered greens |
| 5 | `PIN` | Green-side pin camera | Approaches landing, chips, putts |
| 6 | `AERIAL` | Aerial / drone camera | Between holes, hole flyover |
| 7 | `LEADERBOARD` | Full-screen leaderboard card | Between holes, round end, milestones |
| 8 | `FLYOVER` | Hole flyover (aerial + hole graphic) | Hole start |

Scenes 1–6 are **camera scenes** (different views of the same 3D render). Scenes 7–8 are **card scenes** (graphics-forward). The director (Section 3) switches between them.

### 2.2 Sources per scene

**Camera scenes (1–6) — common source stack:**

| Source | Type | Notes |
|---|---|---|
| `Game Capture` | Game Capture | The render window (web build now; Unreal later). One source, shared across all camera scenes — the *camera* is a property of the render, not of OBS. The director tells the render which camera to use (Section 3.3); OBS just shows the frame. |
| `Scorebug` | Browser Source | NodeCG scorebug graphic (Section 4.1). URL: `http://localhost:9090/bundles/mas-golfs/graphics/scorebug`. 1920×1080, transparent. Always on in camera scenes. |
| `Lower Third` | Browser Source | NodeCG lower-third (Section 4.3). Hidden by default; director shows it on `strike` and `hole_end`. |
| `Ticker` | Browser Source | NodeCG ticker (Section 4.4). Bottom of frame, always on in camera scenes. |
| `Live Bug` | Browser Source | NodeCG "LIVE · MAS GOLFS" bug, top-right. Static HTML, always on. |

**Scene-specific additions:**

| Scene | Extra sources |
|---|---|
| `TRACER` | `Tracer Data` browser source — shot-data panel (ball speed, launch, spin, apex, carry, shape) fed by the `strike`/`apex` events. Appears on `strike`, fades after landing + 3 s. |
| `PIN` | `Green Map` browser source — satellite hole map with the ball position moving across it, fed by `landing` coordinates. |
| `AERIAL` | No extra sources — clean aerial frame; scorebug stays on. |
| `LEADERBOARD` | `Leaderboard Card` browser source (full-screen NodeCG graphic, Section 4.2). Game Capture hidden in this scene. |
| `FLYOVER` | `Hole Card` browser source — hole number, name, par, yardage, wind, pin. Game Capture shows the aerial flyover render. |

**Audio sources (global, all scenes):**

| Source | Type | Notes |
|---|---|---|
| `Commentary` | Audio Input Capture / VLC Source | Commentary pipeline output (Section 5). Ducked under nothing; ambient ducks under it. |
| `Ambient Bed` | VLC Source (loop) or Application Audio Capture | Ambient engine output (Section 6). |
| `Stingers` | Media Source (triggered) | Impact/applause stingers, triggered by events via obs-websocket `TriggerHotkeyByName` or the ambient engine's audio routing. |

### 2.3 OBS settings (baseline)

- **Base canvas:** 1920×1080. **Output:** 1920×1080, 60 fps.
- **Encoder:** x264 (CPU) or NVENC (GPU) — whichever the box has; quality preset `veryfast` (x264) is fine for a mostly-static golf scene. Bitrate 8,000 Kbps video + 160 Kbps audio for 1080p60 to YouTube/Twitch.
- **Replay Buffer:** enabled, 60 s, saved to `~/mas-golfs/replays/`. See Section 3.4.
- **Streaming:** RTMP to Restream (Section 7). Stream key stored in OBS, never in the repo.
- **Recording:** record the program feed locally as a rolling 24 h archive (for VODs and clip extraction) — disk space permitting; otherwise record only replay-buffer saves.

---

## 3. The autonomous director

### 3.1 What it is

A **state machine over phases of play**, not a timer. It lives in a small Node.js process (`director/`) that subscribes to the event bus and drives OBS through obs-websocket (`obsws-python` or Node `obs-websocket-js` — either works; Node keeps the stack one language).

It has exactly one job: **decide which scene is on air, and when to cut.** It never generates content, never touches audio, never writes graphics. It reads events and switches scenes.

### 3.2 Phase → camera map

| Phase (trigger event) | Scene | Notes |
|---|---|---|
| Address / waggle (`shot_start`) | `TEE_DTL` | Down-the-line, hold through the swing |
| Swing → impact (`strike`) | `TEE_DTL` | **Hold. Do not cut.** |
| Ball flight (`strike` → `landing`) | `TRACER` | Cut on `strike`, track the ball, tracer on |
| Landing (`landing`) | `PIN` if on/near green, else `CATCH` | Cut on `landing` |
| Walk to ball (after `landing`, before next `shot_start`) | `CATCH` | Wide follow cam, slow dolly |
| Chip / pitch (`shot_start`, short game) | `PIN` | Low green-side cam |
| Putt (`shot_start`, putter) | `PIN` | Low green-side cam, hold through the roll |
| Hole-out (`hole_end`) | `PIN` → reaction hold 3 s → `LEADERBOARD` or next `FLYOVER` | Reaction cam is `PIN` held; then lower-third with the hole score |
| Between holes (`hole_start`) | `FLYOVER` (3 s) → `TEE_DTL` | Hole card on screen during the flyover |
| Round end (`round_end`) | `LEADERBOARD` | Full leaderboard card, hold 15 s, then next `round_start` → `FLYOVER` hole 1 |
| Milestone (`milestone`) | Stay on current scene; lower-third only | Never cut for a milestone — the graphic carries it |

### 3.3 How the director moves the camera

The render (web build now, Unreal later) exposes a **camera API** the director calls — same event bus, a `camera` message type:

```json
{ "type": "camera", "position": "tee_dtl", "fov": 55, "damping": 0.8, "shake": 0.15 }
```

- **Telephoto feel:** each position has a fixed focal length / FOV — tee cam narrow (telephoto compression, background trees pulled against the player), aerial wide. FOV per position is in the render config, not the director.
- **Inertia:** camera moves use acceleration/deceleration lag (`damping` 0.6–0.9) and micro-shake (`shake` 0.1–0.2) to mimic a human operator on a fluid-head tripod. No snap cuts within a camera move — the *scene cut* is the transition; the *camera move* is always smooth.
- **Haze:** atmospheric haze is a render property, denser at distance. The director never touches it.

The director's rule: **one camera position per phase, and the position only changes on an event boundary.** The render interpolates smoothly between positions; OBS cuts are only between scenes.

### 3.4 Director rules (hard rules — never break these)

1. **Minimum hold: 2–3 seconds per shot.** No scene change within 2 s of the last one, except the `strike` → `TRACER` cut (which is the single allowed fast cut, because the ball is already gone).
2. **Never cut mid-flight.** Once the ball is in the air (`strike` → `landing`), the only allowed cut is `TEE_DTL` → `TRACER` at the strike. No other scene change until `landing`.
3. **Cut on events, never on a clock.** There is no timer in the director. If no event arrives, the director holds the current scene indefinitely.
4. **Every transition has a safe fallback.** If a target scene fails to load, hold the wide cam (`CATCH`) rather than cutting to black. If OBS disconnects, the director re-applies the correct scene on reconnect (the NodeCG venue-graphics pattern: the scheduler re-asserts state).
5. **Between holes, the flyover is mandatory.** Never cut straight from a hole-out to the next tee shot — the viewer needs the reset.

### 3.5 Drama-scored slow-motion replays

Every shot gets a **drama score** (0–100), computed by the director from the `landing`/`hole_end` event:

| Outcome | Drama score | Replay? |
|---|---|---|
| Hole-out / eagle | 95–100 | Yes — 0.5×, full flight |
| Birdie | 75–90 | Yes — 0.5×, flight + landing |
| Near-miss (inside 3 ft, lips out) | 70–85 | Yes — 0.5×, putt only |
| Great recovery (punch-out → GIR, up-and-down from trouble) | 65–80 | Yes — 0.5×, approach only |
| Bad mishit (chunk, shank, water) | 60–75 | Yes — 0.5×, the mishit (viewers love the miss) |
| Routine par / standard shot | 0–40 | No |

**Replay mechanics (OBS):**
- **Replay Buffer** runs continuously (60 s). On a drama score ≥ 60, the director calls `ReplayBuffer.Save` via obs-websocket the moment `landing`/`hole_end` arrives — this saves the last 60 s (the full shot) to disk.
- **Instant Replay plugin** (free, OBS plugin): configured for 0.5× playback at 1% speed precision, with a clip queue. The director triggers the replay scene via websocket: cut to a dedicated `REPLAY` scene (Replay Buffer source + "REPLAY" lower-third), play at 0.5×, then cut back to the live scene (`TEE_DTL` for the next address, or `PIN` if still on the green).
- **Auto-clip save:** every saved replay is also written to `~/mas-golfs/clips/` with a filename encoding the moment (`round47-hole12-birdie-0542.mp4`). The clip pipeline (Section 8) picks these up for Shorts/Reels/TikTok.
- **Replay rules:** maximum one replay per hole unless the drama score is ≥ 90 (a hole-out earns a second look). Never replay a routine shot. Never let a replay delay the next shot by more than 15 s — if the next `shot_start` arrives mid-replay, cut back to live immediately.

---

## 4. NodeCG graphics bundle

**NodeCG** (open source, MIT) is the graphics framework. Graphics are plain HTML/CSS/JS pages, loaded into OBS as browser sources. The bundle is `mas-golfs` with one dashboard and one server extension.

### 4.1 Why NodeCG (and not the alternatives)

- **Replicants** — shared state objects synced server ↔ dashboard ↔ graphics over Socket.IO and persisted. The sim writes shot/score state into replicants; every graphic updates itself. This maps exactly onto the event bus: the NodeCG server extension subscribes to the bus and writes replicants.
- **Messages** — event-based triggers for one-shot graphics (lower-thirds, stingers, milestone banners).
- **Same skill set as the web build** — the graphics are web pages. No new language, no new tooling.
- **Alternatives:** SPX Graphics is the simpler fallback (ready-made control-room UI, REST API on port 5656, rundown model) if the team wants rundowns without building them. CasparCG is overkill — frame-accurate playout is not needed for this show.

### 4.2 Bundle structure

```
bundles/mas-golfs/
├── package.json
├── dashboard/
│   └── panel.html          # phone-friendly control surface (read-only status + manual override)
├── graphics/
│   ├── scorebug.html       # Section 4.3
│   ├── leaderboard.html    # Section 4.4
│   ├── lower-third.html    # Section 4.5
│   ├── ticker.html         # Section 4.6
│   ├── player-card.html    # Section 4.7
│   └── hole-card.html      # Section 4.8
├── extension/
│   └── index.js            # subscribes to event bus, writes replicants, sends messages
└── shared/
    └── style.css           # one design system: dark green + gold, broadcast typography
```

**Design system (all graphics):** dark green (`#0B3D2E` family) + gold (`#C9A227`) on near-black, clean sans-serif broadcast type, no gradients-for-decoration, 1920×1080 transparent backgrounds. Every graphic must be readable at a glance on a phone screen — a viewer should understand the state of the round in 3 seconds.

### 4.3 Replicants (shared state)

The extension writes these replicants from the event bus. Graphics read them and re-render on change — no polling.

| Replicant | Type | Written on | Contents |
|---|---|---|---|
| `roundState` | object | Every event | The full `round_state` snapshot (Section 1.3) |
| `shotData` | object | `strike`, `apex`, `landing` | `club`, `ball_speed_mph`, `launch_deg`, `spin_rpm`, `apex_ft`, `carry_yds`, `total_yds`, `shape`, `contact`, `dist_to_pin_ft`, `lie` |
| `prediction` | object | `hole_start`, `decision` | `question`, `odds` (yes/no), `pool_coins`, `closes_in_s`, `open` (bool) |
| `lastShot` | object | `landing` | One-line result for the ticker: `"7-iron from 164 — 12 ft, birdie putt"` |

### 4.4 Graphics spec — what each one shows and what data it needs

#### Scorebug (always on, top-left in camera scenes)

The single most important graphic. A newcomer must understand the round in 3 seconds.

```
┌─────────────────────────────────────────┐
│ MAS  ·  THRU 11  ·  -2  ·  ROAD TO 59   │
│ H12 · PAR 3 · 164 YDS · +3.1 HCP        │
└─────────────────────────────────────────┘
```

| Field | Source | Notes |
|---|---|---|
| Golfer | `roundState.golfer` | Always "Mas" |
| Thru | `roundState.thru` | Holes completed |
| Score to par | `roundState.score_to_par` | Signed, e.g. `-2`, `E`, `+1` |
| Target | `roundState.target_score` | Always 59 — "ROAD TO 59" |
| Hole / par / yards | `roundState.current_hole` | Current hole |
| Handicap | `roundState.handicap` | Live handicap pill beside the bug |

**Behavior:** updates on every `roundState` change. No animation on update except a 200 ms fade — the scorebug must never distract from the golf.

#### Leaderboard (full-screen card scene + between-holes)

```
MAS — THE RECORD BOOK
All-time: -41 · Last 10 avg: 70.4 · Course record: 63 · Best round: 64
┌──────────────────────────────────────────────────┐
│  #   Round    Score    To par    Date            │
│  1   R41      63       -9        Nov 10          │
│  2   R38      64       -8        Nov 9           │
│  3   R44      65       -7        Nov 11          │
│  ...                                              │
│  ──                                              │
│  47  R47      —        -2 thru 11  LIVE          │
└──────────────────────────────────────────────────┘
ONE FIX (from last round): Aim 5 yards right of pin from 125–150
```

| Field | Source | Notes |
|---|---|---|
| All-time score | `roundState.all_time_score` | Running tally across every round |
| Last-10 average | `roundState.last10_avg` | Form line — how he's playing *now* |
| Course record / best round | `roundState.course_record`, `roundState.best_round` | With dates |
| Round table | Sim history (localStorage / server store) | Top 10 rounds + current round highlighted as LIVE |
| One fix | `round_end.learning_fix` | The single fix from the last completed round |

**Behavior:** shown on `round_end` (hold 15 s), on `milestone` (5 s lower-third version), and between holes on request. Full-screen scene; game capture hidden.

#### Lower-thirds (triggered, 5 s)

Three variants, one graphic, driven by NodeCG messages:

| Variant | Trigger | Content |
|---|---|---|
| Shot data | `strike` | `7-IRON · 164 YDS — Ball 132 mph · Launch 19° · Spin 6,800 · Apex 78 ft · Carry 158` |
| Hole result | `hole_end` | `HOLE 12 — BIRDIE · -3 thru 12 · 2 putts · Up-and-down ✓` |
| Milestone | `milestone` | `COURSE RECORD PACE — Mas is -4 thru 12, record is 63` |

**Behavior:** slides in from the left over 300 ms, holds 5 s, slides out. Never overlaps the scorebug. Shot-data lower-third fires on `strike` and updates with `apex`/`landing` data as it arrives.

#### Ticker (always on, bottom of frame in camera scenes)

A single scrolling line, updated from `lastShot` and `roundState`:

```
MAS -2 THRU 11 · LAST: 7-iron from 164 — 12 ft, birdie putt · NEXT: Par 3, 203 yds · ROAD TO 59 · Last 10 avg 70.4 · Coins open: Birdie or better on 12? (Yes 2.4 / No 1.6)
```

**Behavior:** continuous slow scroll, content refreshes on every `hole_end` and `landing`. Never faster than a comfortable read — this is a broadcast ticker, not a stock feed.

#### Player card (hole start / between holes)

Shown during the `FLYOVER` scene, 3 s:

```
┌──────────────────────────────────────┐
│  MAS — MASON'S DIGITAL TWIN          │
│  +3 handicap · Left-handed           │
│  Driving 268 · Fairways 58% · GIR 61%│
│  Last 10: 70.4 · Best: 63            │
└──────────────────────────────────────┘
```

| Field | Source | Notes |
|---|---|---|
| Identity | Static + `roundState` | "Mas — Mason's digital twin" |
| Handicap | `roundState.handicap` | Live |
| Season stats | Sim stats store | Driving distance, fairways, GIR — season aggregates |
| Form | `roundState.last10_avg`, `roundState.best_round` | |

#### Hole card (hole start, `FLYOVER` scene)

```
HOLE 12 — "THE PICTURE" · PAR 3 · 164 YDS
Wind 12 mph → · Pin back-left · Downhill
```

| Field | Source |
|---|---|
| Hole / name / par / yards | `hole_start` event |
| Wind | `hole_start.wind_mph`, `wind_dir` |
| Pin / elevation | `hole_start.pin`, `hole_start.elevation_ft` |

### 4.5 Dashboard (phone-friendly control surface)

NodeCG's dashboard is a read-only status panel plus a manual override — for Mason, on his phone:

- **Status:** current scene, current phase, stream health (OBS connected, Restream connected, uptime), last event received + timestamp.
- **Manual override (emergency only):** force a scene, force a replay, mute commentary. The system must never *need* these — they exist for the day something breaks.
- **No editing of the sim.** The dashboard cannot change scores, stats, or outcomes. It is a monitor, not a control room.

---

## 5. Event-driven AI commentary pipeline

### 5.1 Pipeline

```
sim JSON event ──▶ LLM (tight system prompt) ──▶ 1–2 sentence line
                                                        │
                                              ┌───────┴───────┐
                                              ▼               ▼
                                    Play-by-play voice   Color voice
                                    (calm host)          (analyst)
                                              │               │
                                              └───────┬───────┘
                                                      ▼
                                              TTS (streaming)
                                                      │
                                                      ▼
                                              OBS audio (ducked bed)
```

### 5.2 The LLM step

- **Model:** any small, fast, cheap hosted LLM — or a local small model (the project's local-models direction). The prompt is doing the work, not the model size.
- **System prompt (tight, fixed):**

> You are a golf broadcast commentator in the CBS/NBC cadence: understated, knowledgeable, concise. One or two sentences maximum. State the plan before a shot; state the result after. Never hype, never shout, never use exclamation marks. You are describing Mas, a +3 left-handed golfer, Mason's digital twin. Do not invent facts not in the event data.

- **Input:** the raw JSON event, nothing else. No conversation history — each line is generated from a single event, so there is no context-window growth over 24 hours.
- **Output:** one or two sentences, plain text. No stage directions, no formatting.

### 5.3 The two voices

| Voice | Role | When it speaks |
|---|---|---|
| **Play-by-play host** (calm, authoritative) | The facts: what happened, the numbers | `landing`, `putt_result`, `hole_end`, `round_end`, `milestone` |
| **Color commentator** (analytical) | The why: the decision, the strategy, the lesson | `decision` (the plan, before the shot), `apex` (reading the flight), `round_end` (the one fix) |

**Timing rules (these are what make it sound like a broadcast):**
- The **decision line** is generated from the `decision` event and spoken **before** the swing — the viewer hears the plan, then watches the execution.
- The **result line** is generated from `apex`/`landing` and spoken **as the ball lands** — the words land as the ball does.
- Never speak over a swing. If a line is still queued when `shot_start` arrives, hold it until `landing`.

### 5.4 TTS — free first, paid fallback

| Option | Cost | Latency | Notes |
|---|---|---|---|
| **Kokoro** (self-hosted, Apache 2.0) | **Free** — ~$11/mo hosted, $0 self-hosted | ~200–300 ms | 54 voices, 8 languages. **Default choice.** Two voice IDs (one per role) picked from the Kokoro set and locked. |
| **ElevenLabs Flash v2.5** | $40 per million characters | ~75 ms model latency, ~188 ms to first audio | **Paid fallback only** if Kokoro quality is judged insufficient. Two voice IDs, same roles. |
| **ElevenLabs v4 Turbo** | $40 per million characters | ~150–192 ms | Alternate paid fallback. |

**Streaming:** TTS streams over WebSocket; audio goes to OBS as a live input. No pre-rendering, no files — the line is spoken as it is generated.

### 5.5 Cost guardrails (the math that decides everything)

Continuous 24/7 commentary at ~150 wpm is ~45,000 characters/hour → ~32M characters/month → **~$1,300/month on ElevenLabs**. That is the trap. The guardrails:

1. **Event-only.** Commentate on decisions, results, milestones, and round boundaries — never continuous narration. Real golf is mostly quiet; the ambient bed carries the silence. This alone cuts volume by roughly an order of magnitude.
2. **Cached lines.** Hole intros, standard calls ("Mas is -2 through 11, chasing 59"), and recurring situations are cached audio — generated once, replayed. Only genuinely new situations hit the LLM/TTS.
3. **Length cap.** One or two sentences per line, enforced in the prompt and hard-capped at 280 characters before TTS.
4. **Rate limit.** Maximum one line per 15 seconds, maximum 4 lines per hole. If events arrive faster, the pipeline drops the lowest-priority line (result lines outrank color lines).
5. **Free-first.** Kokoro self-hosted is the default; ElevenLabs is only engaged if Kokoro is judged insufficient, and only for the play-by-play voice (the color voice stays on Kokoro).

**Monthly cost target: $0.** The paid fallback exists on paper; the system is designed never to need it.

---

## 6. Ambient audio layers

Real golf broadcasts mix in layers — never a single loop. Three layers, all procedural or generated, all free:

### 6.1 Layer 1 — continuous base bed (never silent)

- **Wind in pines** (filtered noise, shaped by the current wind speed from the sim) + **birdsong** (peaks at dawn, thins at midday — driven by the in-world time of day).
- Generated procedurally (WebAudio noise + filtered bird-call samples from a free library, e.g. Freesound CC0 recordings). No looped MP3 — the bed is synthesized from weather/time state so it never audibly repeats.
- **Level:** -24 LUFS, constant. The bed never ducks to silence. Commentary ducks the bed (see 6.4); the bed never ducks to nothing.

### 6.2 Layer 2 — per-hole variation

- Each hole has an acoustic character: the par 3 over water has more water sound; the tree-lined holes have more wind-in-pines; the open holes have more open-air ambience.
- Driven by the `hole_start` event — the bed crossfades to the new hole's mix over 2 s.
- This is what makes the stream feel like a place, not a soundtrack.

### 6.3 Layer 3 — event stingers (scaled to the moment)

| Event | Stinger | Notes |
|---|---|---|
| `strike` | Crisp club-on-ball impact | Always. The single most important sound in the show — it must be *sharp*. |
| `landing` on green | Soft turf/ball-drop | Subtle. |
| Birdie / eagle (`hole_end`) | Gallery murmur swelling to applause | Scaled to the moment — a birdie gets a murmur, an eagle gets applause. |
| Hole-out | Applause + a beat of crowd noise | The biggest stinger in the show. |
| Water / trees (`landing`, bad lie) | A soft groan / rustle | Understated — the sound of a miss, not a joke. |

Stingers are triggered from the same JSON events as the commentary (same bus, same timing). They are short (0.5–3 s) and never overlap the commentary's first word.

### 6.4 Ducking

- **Commentary ducks the bed** by -6 dB for the duration of the line + 0.5 s tail. Implemented in OBS with a sidechain compressor on the Ambient Bed source, keyed from the Commentary source.
- **Stingers do not duck the bed.** They sit on top of it.
- **Nothing ducks the commentary.** The voices are always the loudest thing on the stream.

### 6.5 Sources (all free)

- Wind/bird bed: procedural WebAudio + CC0 field recordings (Freesound).
- Impact sounds: synthesized (filtered noise burst + low thump) or CC0 golf-impact samples.
- Applause: CC0 crowd recordings, layered and scaled by the drama score (Section 3.5).

---

## 7. Transport and multistream (24/7 reliability)

### 7.1 The chain

```
OBS (one instance, one box)
  │ RTMP, 1080p60, 8,000 Kbps video + 160 Kbps audio
  ▼
Restream (free tier — 2 channels)
  ├──────▶ YouTube Live
  └──────▶ Twitch
```

- **Why Restream:** one feed in, two platforms out, merged chat. Free tier covers exactly the two channels this project needs. Standard ($16/mo annual) adds a third channel — only if a third platform is ever added, and only then.
- **Why not direct to each platform:** two separate RTMP outputs from one OBS doubles the encoder load and doubles the failure modes. One feed to Restream is simpler and more reliable.
- **YouTube setup:** live streaming must be enabled on the account first — first activation can take up to 24 hours. Use an encoder-based event with a persistent stream key. Set the **AI-use disclosure** in YouTube Studio from day one (Section 8).
- **Twitch setup:** standard stream key. Affiliate unlocks at ~3 average viewers (subs, Bits) — the first money milestone, but not the goal of month one.

### 7.2 The watchdog (the only "ops" this loop needs)

A 24/7 stream fails in boring ways: OBS crashes, the network drops, Restream hiccups, the render freezes. The watchdog is a small always-on script (Node.js or Python) on the same box:

| Check | Interval | Action on failure |
|---|---|---|
| OBS websocket responsive | 30 s | Restart OBS, re-apply current scene (director state) |
| RTMP stream live (Restream health API) | 60 s | Restart OBS streaming; if still down after 3 tries, restart the box's network stack |
| Render frame advancing | 10 s | Restart the render (web build / Unreal) |
| Event bus alive (last event < 60 s old) | 30 s | Restart the sim engine; re-send `round_state` snapshot |
| Disk space (replays + recordings) | 1 h | Prune replays older than 7 days, recordings older than 24 h |
| Stream uptime alert | On any restart | Log + notify Mason (chat message / email) |

**Rules:**
- The watchdog restarts things; it never *decides* things. It cannot change scores, scenes, or outcomes.
- Every restart is logged with a timestamp. The stream must be able to run a full week without human attention.
- **Treat power, network, and encoder auto-restart as part of the broadcast design** — the box is on a UPS, OBS is set to auto-start on boot, and the watchdog starts on boot.

### 7.3 Failure modes and fallbacks

| Failure | Viewer sees | Recovery |
|---|---|---|
| OBS crash | Brief freeze, then the correct scene re-applied | Watchdog restarts OBS (< 30 s) |
| Network drop | Stream pauses (platform shows "reconnecting") | OBS auto-reconnects; Restream holds the slot |
| Render freeze | Frozen frame with live scorebug/ticker | Watchdog restarts render; director holds `CATCH` wide cam meanwhile |
| Sim engine crash | Golf pauses; graphics hold last state | Watchdog restarts sim; `round_state` snapshot re-sent; play resumes from the last completed shot |
| Total box failure | Stream down | UPS + auto-boot; if the box is dead, the stream is down until the box is replaced — this is the one failure with no automatic recovery, and it is accepted |

---

## 8. Compliance (from day one)

### 8.1 YouTube AI-use disclosure

- **YouTube requires disclosure of realistic AI-generated content** via the "AI use" setting in YouTube Studio. It applies to live streams, not just uploads.
- **Set it on the stream before the first broadcast.** Persistent non-disclosure risks content removal or Partner Program suspension.
- **The label does not limit audience or earnings** — YouTube states this explicitly. Set it and forget it.

### 8.2 Originality (the monetization defense)

YouTube will not monetize generic, template-like AI content. The defense is originality, and this project has it built in:

- A **real person's swing model** (Mason's actual swing, captured).
- **Real course-management decisions** (the decision engine, the learning loop).
- **A learning arc** (Mas improves over weeks; the handicap moves).
- **A visible human identity** — "Mas is Mason's digital twin" is on screen at all times, and the Mason W Golf brand anchors the channel.

Keep the identity visible. Never present the stream as generic golf content.

### 8.3 Coins (closed-loop, always)

Clubhouse Coins are free, earned by watching and predicting, never purchasable, never convertible to anything of value — status, leaderboard rank, and cosmetic perks only. No cash-out path, no crypto, no secondary market. This is a legal boundary, not a feature to revisit without counsel.

---

## 9. 59 Watch

The broadcast's signature feature: a live, always-on chase for the sub-60 round.

- **The trigger.** 59 Watch turns on automatically the moment Mas goes under the 59-pace line (score vs. par through the holes played, against the pace a 59 requires). It turns off if he falls off pace, and back on if he recovers.
- **The bug.** A pulsing gold bug, top-right, showing current score vs. the 59 pace (e.g. "−8 thru 12 · 59 PACE"), the strokes he can still afford to drop, and a live probability of breaking 60 derived from the remaining holes and his current form.
- **The escalation.** The deeper the round, the louder it gets: subtle bug early, a lower-third at the turn when on pace, a full-screen moment on the 18th when 59 is on the line — with the crowd/ambient audio swelling to match.
- **The record book.** Every round logs its 59-watch story: on pace at the turn, best 59-watch moments, closest calls, and the all-time "closest to 59" board. A round that ends 60 or 61 is a near-miss story, not a failure.
- **The sim side.** The sim engine emits pace state on every hole (`fifty_nine_watch` events: on pace / off pace / back on pace / 59 on the line) so graphics, commentary, and the clip pipeline all react to the same truth.
- **The clip angle.** Any 59-watch moment at drama 90+ is an automatic second clip of the day, and a completed 59 is the biggest clip the show will ever make.

## 10. Build order (the checklist)

Build in this order. Each step is independently testable; do not start the next until the current one works end-to-end.

- [ ] **1. Event bus + JSON schema** — sim emits all events in Section 1.2; a test subscriber receives them.
- [ ] **2. OBS scene collection** — all 8 scenes built, all sources placed, replay buffer enabled, RTMP to Restream working to a private test stream.
- [ ] **3. Director** — state machine switching scenes on events; minimum-hold, never-cut-mid-flight, and fallback rules verified by running a full round unattended.
- [ ] **4. NodeCG graphics** — bundle installed; all 6 graphics render from replicants; scorebug readable at a glance on a phone.
- [ ] **5. Replay system** — replay buffer saves on drama ≥ 60; Instant Replay plays at 0.5×; clips land in `~/mas-golfs/clips/`.
- [ ] **6. Commentary pipeline** — event → LLM → TTS, two voices, decision line before the shot, result line at landing; rate limits and cached lines verified; monthly cost $0 on Kokoro.
- [ ] **7. Ambient audio** — three layers audible, bed never silent, ducking working, stingers firing on events.
- [ ] **8. Multistream + watchdog** — YouTube + Twitch live simultaneously via Restream; watchdog restarts OBS on a forced crash; AI-use disclosure set.
- [ ] **9. Clip pipeline** — replay saves auto-cut into vertical clips; first 5 clips posted to Shorts/Reels/TikTok.
- [ ] **10. 24/7 soak test** — one full week unattended. Zero human touches. Uptime, restart count, and cost logged.

---

## 10. Costs (monthly, at 24/7)

| Item | Cost |
|---|---|
| OBS Studio | $0 |
| NodeCG | $0 |
| YouTube Live | $0 |
| Twitch | $0 |
| Restream (free tier, 2 channels) | $0 |
| Kokoro TTS (self-hosted) | $0 |
| LLM (local small model) | $0 |
| Render (web build, static page) | $0 |
| **Total — web build** | **$0** |
| Unreal GPU (when built — RunPod spot RTX 4090, optional) | ~$250/mo |
| ElevenLabs Flash (paid fallback — designed never to be used) | $0 |

The only money in this project is optional, and it buys build speed, not the show itself.

---

*Mas Golfs — the Mason W Golf endless round. Road to 59.*
