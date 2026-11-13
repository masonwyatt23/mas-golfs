# Mas Golfs — Guest Twins Path A: Phone Video Submission

**Status:** design only. Path C (stat profile) is implemented in
`sim/twins.py`; the validation round, twin card, and approval flow it
uses already exist. This document designs the default submission path
— the phone video — on top of that finished foundation. Nothing here
changes the physics, the decision engine, or the validation bands.

**The one-sentence version:** the guest films five short clips on
their phone; a free, on-device pose model measures what a phone video
can genuinely measure (handedness, tempo, swing-path direction,
balance); everything a phone video *cannot* measure stays on the
benchmark tables; and the video's job is to check the guest's claims,
not to invent numbers.

---

## 0. Relationship to the existing system

| Piece | Status | Path A's relationship |
|---|---|---|
| `docs/guest-twins.md` §2–§3 | Spec | This doc implements §2 Path A and §3's calibration for it. |
| `sim/twins.py` `build_twin(profile, measured)` | Implemented | Path A ends here. The `measured` dict is the plug-in point; see §4. |
| `sim/twins.py` `calibrate_twin` / validation bands | Implemented | Path A twins validate exactly like Path C twins (§5). |
| `sim/twins.py` `twin_card_dict` / `approve_twin` / `can_air` | Implemented | Path A changes nothing about the gate: no approval, no air. |
| `TwinRegistry.recalibrate` | Implemented | A Path C guest upgrades to Path A through this; record kept, approval resets. |

**Path A is video *plus* the Path C profile, not video *instead* of it.**
The guest still gives their handicap and the five honest answers
(usual miss, best part, worst part, between clubs, one proud number).
The video refines specific fields and sanity-checks the claims. Every
field the video cannot measure still comes from the handicap-benchmark
tables in `twins.py` — exactly as Path C does.

**What the video never does:** it never becomes a likeness. Pose
landmarks are skeleton points used only as calibration numbers. The
on-air golfer is the show's generic golfer model; the twin's identity
on screen is its name, its card, and its golf (§6, §7).

---

## 1. What the guest films

Total ask: **five clips, under 10 minutes at the range, no equipment
beyond their phone.** The instructions below are written to be sent
verbatim to the guest (see the copy-paste block at the end of this
section).

### 1.1 The five clips

| # | Clip | Club | View | Why it exists |
|---|---|---|---|---|
| 1 | Full swing 1 | Driver | Down-the-line | Handedness, path direction, balance, tempo |
| 2 | Full swing 2 | Driver | Down-the-line | Second sample; path consistency |
| 3 | Full swing | 7-iron | Down-the-line | Delivery tells more than the driver does (spec §2) |
| 4 | Full swing | Driver | Face-on | Tempo cross-check; the only view the speed estimator can use (§3.4) |
| 5 | Short game | Putter ×3, chip ×2 | Face-on for putts, down-the-line for chips | Stroke tempo + contact sanity check on the short-game claim (§3.5) |

Clips 1–2 are the minimum for a Path A twin. Clips 3–5 are strongly
asked for; a guest who sends only 1–2 still gets a twin, with the
missing fields marked "estimated" on the card.

### 1.2 Camera setup (the same for every clip)

- **Distance:** 8–10 feet from the golfer. Close enough that the
  whole body fills the frame; far enough that the clubhead stays in
  frame at the top of the backswing.
- **Height:** lens at hip height (about 3 feet off the ground — a
  range basket, a bag, or a friend's hand at their side). Not from
  the ground, not from chest height. A high or low camera is the
  largest single source of error in everything that follows: it
  bends the apparent swing plane and corrupts the path direction.
- **Down-the-line:** the phone sits on the target line, directly
  behind the golfer, looking down the line the ball will travel.
  The ball, the feet, and the full body must be in frame. The
  golfer's target must be visible in the background (a flag, a
  target net) so the target line can be verified afterwards.
- **Face-on:** the phone sits square to the golfer's chest at
  address, on the line through the ball perpendicular to the target
  line. Same distance, same height.
- **Orientation:** landscape, always. Portrait crops the clubhead
  out of the frame at the top.
- **Frame rate:** slo-mo if the phone offers it — 120 fps preferred,
  240 fps ideal (iPhone back-camera slo-mo is 240 fps; most Android
  flagships offer 120 or 240 fps). **60 fps is the minimum for tempo
  work; 30 fps is accepted for handedness, path, and balance only,
  and the card says so.** Below 30 fps, ask for a re-film.
- **Light:** daylight or bright range lighting, sun behind the
  camera, not behind the golfer. Motion blur is what costs accuracy;
  good light is the cheapest accuracy there is.
- **Steady:** the phone does not move during the swing. A range
  basket, a tripod, or a friend holding it still. A moving camera
  makes the swing unmeasurable and the clip is rejected.

### 1.3 What the guest reports per swing

The video alone cannot say where the ball went. The guest reports,
per swing, in one line each:

- Club, intended shape ("trying to draw it"), actual result
  ("drew it, about 250", "pushed it right, short").
- Anything unusual ("caught it thin", "topped the chip").

"About 250" is enough. A precise number is not required and not
believed more for being precise — the intake treats the result as a
plausibility signal, not a measurement (§3.6).

### 1.4 What not to do (in the instructions)

- Don't film face-on only — the down-the-line view is the one that
  shows path direction.
- Don't crop the feet or the clubhead out of frame.
- Don't film in the dark, into the sun, or with a filter.
- Don't send a swing from a simulator screen or a TV broadcast —
  the pipeline needs the golfer, not a picture of a golfer.
- Don't send a compilation, a lesson video, or a swing with
  coaching audio over it. One swing per clip, clean.

### 1.5 How the video gets to the show (v1: no new infrastructure)

The guest sends a link — Google Drive, Dropbox, iCloud, WhatsApp,
iMessage, whatever they already use. The show owns a private intake
folder (see §7 for storage and retention). No upload portal is built
in v1; a link the guest already knows how to send is lower friction
than an account they have to create. If the intake volume ever
justifies it, a simple upload page is a later step, not a launch
requirement.

### 1.6 Copy-paste filming instructions (send verbatim)

> **Film your swing in 10 minutes — 5 clips, phone only.**
>
> 1. **Driver, down-the-line (×2).** Phone on the target line,
>    directly behind you, 8–10 feet back, lens at hip height
>    (rest it on your range basket). Landscape. Full body, ball,
>    and clubhead in frame. Slo-mo if your phone has it (120 fps
>    or 240 fps is ideal, 60 fps minimum).
> 2. **7-iron, down-the-line (×1).** Same setup.
> 3. **Driver, face-on (×1).** Phone square to your chest at
>    address, same distance and height.
> 4. **Putts (×3) and chips (×2).** 10-foot putts, face-on; chips,
>    down-the-line.
> 5. **For each swing, tell us one line:** club, what you tried to
>    do, what happened ("drew it, about 250").
>
> Plus your handicap and five quick answers (usual miss, best part
> of your game, worst part, aggressive or conservative between
> clubs, one number you're proud of). Send it all as a Drive or
> Dropbox link. That's it — your twin plays from there.

---

## 2. The measurement pipeline (free, on-device, no cloud video AI)

### 2.1 The tool: MediaPipe Pose Landmarker

**Pick: MediaPipe Pose Landmarker** (Google AI Edge, the Tasks API —
not the legacy Solutions API, which is deprecated). It is the
browser-first, phone-first pose option, and it is free.

Verified facts (Google AI Edge docs, checked Nov 2026):

- Outputs **33 body landmarks** in image coordinates and in 3D
  world coordinates (origin at hip midpoint), plus per-landmark
  visibility and presence.
- Three model bundles — Lite (~5.8 MB), Full (~9.4 MB), Heavy
  (~30.7 MB) — all float16, detector input 224×224×3, landmarker
  input 256×256×3. The landmarker is a BlazePose-derived model
  (GHUM 3D human-shape pipeline) with a MobileNetV2-like backbone,
  optimised for on-device real-time use.
- Runs on Android, iOS, web (JavaScript/WASM), and Python — the same
  pipeline can run in a browser page or on the show's machine.
- Single-person video is the intended use, which is exactly what a
  swing clip is.
- The MediaPipe repository and code samples are Apache 2.0. One
  licensing caveat to carry into the build: Google does not publish a
  separate licence statement for the Pose Landmarker **model weights**
  on the model page (third-party redistributions label them
  Apache 2.0, but Google's own page does not state it). This is a
  use-the-model question, not a redistribution question — the show
  runs the published bundle, it does not redistribute it — and the
  build should re-check the licence page before shipping and record
  what it says. If the weights' status ever becomes a blocker, the
  fallback is RTMPose (OpenMMLab, Apache 2.0, 17 keypoints, CPU —
  a server-side replacement with the same interface, not a redesign).

**Where it runs:** on the show's machine, in Python, over the
received video file. Not in the cloud, not through a third-party
video-AI service, and not on the guest's phone in v1 (a browser
version that processes on the guest's own device is a later step —
it is strictly better for privacy, but it is not required to launch).
The raw video never leaves the show's private intake folder and is
never uploaded to any AI service.

**What the pipeline outputs:** per frame, the 33 landmarks with
visibility; from those, a **landmark time series** (joint angles over
time) and a **per-swing measurement record** (see §3). The landmark
time series is the guest's data — it is stored with the video and
deleted with it (§7), never posted, never used to train anything.

### 2.2 Pipeline stages

1. **Ingest + quality gate.** Check the file: duration, frame rate,
   resolution, single person in frame. Reject (ask for a re-film)
   when: full body not in frame at address; camera off the target
   line by more than ~15° (estimated from the shoulder line vs the
   reported target); frame rate below 30 fps; the ball not visible
   at address; another person in frame; heavy motion blur (mean
   landmark visibility below 0.5 on wrists and shoulders). A
   rejected clip is a re-film request, not a silent downgrade — the
   guest is told exactly what to fix.
2. **Landmark extraction.** Pose Landmarker, Full bundle, over the
   clip. Output: 33 landmarks per frame, with visibility.
3. **Event detection.** Address, takeaway, top of backswing, impact,
   finish — found from the wrist/shoulder trajectories and the
   ball's disappearance from the address position. Impact is the
   frame the ball leaves; at 30 fps the clubhead moves ~4.4 feet
   between frames at 90 mph, so impact timing at 30 fps is ±1
   frame and the pipeline says so.
4. **Measurement.** The per-swing record (§3), each value with a
   confidence and the camera conditions it was measured under.
5. **Intake report.** One JSON per guest: the measurement record,
   the quality flags, the measured dict for `build_twin` (§4), and
   the calibration notes for the card (§6). A human reviewer reads
   this report before the twin is built (§8) — the pipeline proposes,
   it does not decide, in v1.

### 2.3 Why MediaPipe and not the alternatives

- **OpenPose:** non-commercial licence only. Ruled out.
- **RTMPose (OpenMMLab, Apache 2.0):** the server-side fallback.
  More accurate per frame on a CPU, but no first-party browser
  binding — the wrong shape for a phone-first intake. Kept as the
  fallback if the MediaPipe weights' licence ever blocks us.
- **Apple Vision body pose (iOS 14+, 19 joints 2D; 3D on iOS 17+):**
  free and on-device, but iOS-only and fewer landmarks. Not the
  intake — half the guests are on Android.
- **Paid swing-analysis apps / cloud video AI:** ruled out by the
  $0 rule and by privacy (§7). No per-call cost is acceptable; no
  video leaves the show's machines.

---

## 3. What each measurement can and cannot prove

The governing rule: **frame timing is a measurement; everything else
is a model output, and the intake says which is which on the record,
not in a footnote.** A single phone camera films a swing in two
dimensions; the swing happens in three. Depth is reconstructed by a
model that has never seen this body, using assumptions about human
proportion that hold on average and fail on individuals. The
pipeline's job is to know the difference.

### 3.1 The measurement table

| Measurement | How | What it proves | Error bars / limits | Used for |
|---|---|---|---|---|
| **Handedness** | Which side of the target line the golfer stands on; lead-shoulder side from landmarks | Certain. The one measurement a phone video cannot get wrong. | None material. | `measured["handedness"]` (§4) |
| **Tempo (backswing : downswing)** | Frame count from takeaway → top → impact | A real number. Frame timing is the thing video genuinely measures. At 120 fps the top-to-impact interval is known to ~8 ms. | ±1 frame on each event. Downswing ~0.25 s = 15 frames at 60 fps (±7%), 30 frames at 120 fps (±3%), 60 frames at 240 fps (±2%). Reference: a Tour-tempo ratio is ~3:1. | Descriptive only — recorded in `measured["tempo"]`, shown on the card. The engine has no tempo parameter yet (see `twins.py`); tempo does not change the delivery. |
| **Swing-path direction** | Hand/clubhead path through impact, down-the-line view: in-to-out vs out-to-in, from the wrist trajectory relative to the target line | A tendency, not a number. Direction is robust; magnitude in degrees is not. | Degrades when the camera is off the target line, high, low, or close. Reported as a direction (in-to-out / square / out-to-in) with a confidence, never as a precise path angle. | `measured["shot_shape"]` + `measured["face_bias_deg"]`, triangulated with the ball flight and the stated miss (§3.3) |
| **Balance** | Head displacement from address to finish; trail-foot lift; finish position held or fallen away | A qualitative grade: balanced / slight loss / clear loss. | Scored by the human reviewer from the landmark trace + the video, not auto-scored in v1. A model that auto-grades balance from landmarks alone would invent precision. | Sanity check only (§3.6). A clear balance loss downgrades a distance claim; it never upgrades one. |
| **Club speed / ball speed** | **NOT produced in v1.** See §3.4. | — | — | Nothing in v1. Benchmark-derived speed stays. |
| **Carry distance** | **NOT produced in v1.** See §3.4. | — | — | Nothing in v1. Benchmark-derived driving stays. |
| **Face angle at impact / spin / launch / smash** | **NOT produced, ever, from a phone clip.** At 30 fps the clubhead crosses well over a metre between exposures near impact; what lands on the sensor is a smear, not an object. | — | — | Nothing. Path B (launch monitor) is the only source for these. |
| **Putt stroke tempo** | Backstroke : through-stroke frame count from the putt clips | A real number, same timing argument as full-swing tempo. | Same ±1-frame limits. A 3-putt sample is a tendency, not a make-rate curve. | Descriptive only, shown on the card. Does not set `putt_mult` (§3.5). |
| **Short-game contact** | Head movement and turf interaction visible on chip clips; thin/chunk visible as a strike event | A sanity check on the short-game claim. | Qualitative, reviewer-scored. | Sanity check only (§3.6). |

### 3.2 Tempo, precisely

Tempo is the one genuinely quantitative measurement Path A adds over
Path C, and it is worth stating exactly what it is:

- **Events:** takeaway (clubhead first moves), top (wrist
  trajectory reverses), impact (ball leaves). All three are found
  from the landmark time series, not eyeballed.
- **Output:** backswing seconds, downswing seconds, and the ratio
  (e.g. 0.90 s : 0.30 s = 3.0:1), plus the frame rate the clip was
  shot at, so the error bars are visible on the record.
- **What it is used for in v1:** shown on the twin card
  ("Tempo 3.1:1 — quick, Tour-like" / "Tempo 4.2:1 — deliberate"),
  and recorded in `twin.measured["tempo"]`. It does **not** change
  the delivery distribution, because the engine has no tempo
  parameter. If a tempo parameter is ever added to the engine, the
  mapping is a new design — tempo must not be silently wired into
  sigma or speed, because tempo and dispersion are not the same
  thing and a fast tempo is not a wild tempo.
- **What it is not:** a speed estimate. A quick tempo does not prove
  a fast clubhead, and a slow tempo does not prove a slow one.

### 3.3 Shot shape: triangulation, not a single signal

No single signal in a phone video proves shot shape. Path A
triangulates three signals, in this priority order:

1. **The ball's observed flight** (guest-reported result + the ball
   visible leaving the frame): the ball went left or right, drew or
   faded. This is the strongest signal — it is the outcome, not a
   proxy.
2. **The guest's stated usual miss** (Path C answer): the golfer's
   own long-run knowledge of their game.
3. **The pose-derived path direction** (in-to-out / square /
   out-to-in): the weakest of the three, because it is a model
   output sensitive to camera position.

**The rule:** if all three agree, the shape is set with high
confidence. If the ball flight and the stated miss agree and the
pose disagrees, the pose is treated as a camera-position artefact
and the shape follows the first two. If the ball flight and the
stated miss disagree, the ball flight wins (the round just played
beats the self-description), and the disagreement is written on the
card as a calibration note. The pose signal alone never sets the
shape.

### 3.4 Speed and carry: the honest position (and the gated stretch)

**In v1, Path A produces no club speed, no ball speed, and no carry
distance.** This is a deliberate design decision, not a gap waiting
to be filled by optimism. The evidence:

- At 30 fps a 90 mph clubhead travels ~4.4 feet between frames
  (2.2 feet at 60 fps, ~13 inches at 120 fps, ~6.6 inches at
  240 fps). Near impact there is no frame that shows the clubhead
  where it was at impact — only a smear.
- Software that prints a speed in mph from a phone video is
  inferring it from body motion and presenting the inference as a
  reading. That is a marketing decision, not a technical one. Mas
  Golfs does not do it.

**The gated stretch — double-pendulum estimation, only after it
proves itself on Mas:** the research basis exists. A double-pendulum
model of the swing (arms as one pendulum, club as a second),
driven by pose landmarks, can estimate clubhead speed from the
angular velocities at impact, and an open-source pipeline (OpenCap
video analysis → double-pendulum forward simulation → ball
trajectory model) has validated carry prediction against known
carry distances and clubhead velocities. Commercial implementations
of the same idea (e.g. GolfSpeed: 17 joints, face-on clip, needs
the guest's shoulder-to-wrist length as the one real-world scale
reference, 60 fps or more ideal) are explicit that the output is an
estimate for tracking trends, not a radar reading.

The gate for ever shipping it:

1. **Calibrate on Mas first.** Film Mas's own swing (the swing
   video the show already has), run the estimator, and compare
   against Mas's known numbers (club speed ~110 mph, ball speed
   ~161 mph, driving ~265–275 yd). The estimator must land within
   **±5 mph of Mas's known club speed on 5 swings** before it is
   offered to any guest.
2. **If it passes, it ships as an estimate with error bars**
   (±8–12 mph, stated on the card), used only to nudge the speed
   factor *within* the claim-tolerance band
   (`CLAIM_DRIVING_TOL_YD = 15` in `twins.py`) — never to override
   the benchmark, and never to upgrade a claim past the benchmark.
3. **If it fails the Mas gate, it does not ship.** The twin still
   works — Path A without a speed number is still a better twin
   than Path C, because handedness, tempo, shape, and the sanity
   check are real.

**Face-on is required for the estimator** (the pendulum is measured
in the swing plane); that is why clip 4 exists. A down-the-line
clip cannot feed it.

### 3.5 Putting and short game: what the clips can and cannot do

- **Putts (clip 5):** stroke tempo is measurable (same timing
  argument as §3.2) and is recorded descriptively. **Make rates
  are not measurable from three putts on camera** — a make-rate
  curve needs dozens of putts at known distances. `putt_mult`
  stays benchmark-derived (or from the guest's Path C proud
  number, claim-checked the same way). A visibly decelerating or
  yippy stroke is a reviewer note on the card, not a number.
- **Chips (clip 5):** contact quality is visible (thin / chunk /
  clean) and the reviewer notes it. It sanity-checks the
  short-game strength/weakness claim (§3.6). It does not set a
  sigma — two chips cannot estimate a dispersion.

### 3.6 The sanity check (the video's real job)

The video's most important function is not measuring — it is
**checking**. The intake compares the guest's claims against what
the video supports, and the rule is one-directional:

> **The video can only downgrade a claim, never upgrade one.**
> A great-looking swing does not prove 300 yards. A swing that
> loses its balance, has a 4.5:1 tempo, and an out-to-in path
> attached to a 300-yard claim disproves it.

Concretely, the intake applies the claim tolerances already in
`twins.py` (`CLAIM_DRIVING_TOL_YD = 15 yd`, `CLAIM_FAIRWAY_TOL_PTS
= 0.10`, `CLAIM_PUTTS_TOL = 2.0`) and adds the video veto:

| Claim | Video evidence | Outcome |
|---|---|---|
| Driving distance within tolerance of the benchmark | Tempo 2.5–3.5:1, balanced finish, path consistent with the stated shape | Accepted as stated |
| Driving distance above benchmark + tolerance | Any video | Calibrated down to the benchmark (existing Path C rule — the video adds nothing here) |
| Driving distance within tolerance, but the swing contradicts it (clear balance loss, 4.5:1+ tempo, path opposite the stated shape) | The contradiction itself | Calibrated down to the benchmark, with a note: "Video shows [balance loss / tempo / path]; driving calibrated to the benchmark, not the claim." |
| Driving distance below the benchmark | Any video | Accepted as stated — a guest who undersells is believed. The twin is only ever better than the guest if the numbers say so, and a modest claim is a number that says so. |
| Fairways / putts claims | Same tolerances as Path C | Video does not arbitrate these — a swing clip cannot show a fairway percentage. |

Every downgrade lands in `calibration_notes` and is shown on the
twin card, in plain language, before the guest approves. The guest
is never silently calibrated down — the card is where they see it
and where they can dispute it (§6).

---

## 4. Mapping into the existing twin interface

### 4.1 The `measured` dict (the plug-in point)

`build_twin(profile, measured)` in `sim/twins.py` accepts these
keys. Path A populates exactly these — nothing else, and nothing the
video cannot support:

| `measured` key | Path A source | v1? | Rules |
|---|---|---|---|
| `handedness` | Landmark side / stance, certain (§3.1) | Yes | `"left"` / `"right"`. Overrides the profile's handedness. |
| `shot_shape` | Triangulation (§3.3) | Yes | `"draw"` / `"fade"` / `"straight"` only. |
| `face_bias_deg` | Path direction, converted to engine frame (§4.2) | Yes | Capped at **±1.0°** — the same bound as Path C's `_FACE_BIAS_DEG`. |
| `tempo` | Frame timing (§3.2) | Yes — descriptive | Recorded in `twin.measured["tempo"]` and shown on the card. `build_twin` stores it but does not consume it; it changes no delivery value. |
| `balance` | Reviewer grade (§3.1) | Yes — descriptive | Recorded in `twin.measured["balance"]` (`"balanced"` / `"slight loss"` / `"clear loss"`) and in `calibration_notes` when it triggers a downgrade. Changes no delivery value directly. |
| `source` | — | Yes | Set to `"path_a"` so the card shows the provenance. |
| `club_speed_mph` | Double-pendulum estimator (§3.4) | **No — gated stretch only.** Never populated until the Mas gate passes. | If ever populated, it sets `speed_factor = club_speed / 110.0` in `build_twin` — the intake must therefore pass the *estimated* speed with its error bar in the intake report, and the card must show it as an estimate. **Code note:** `build_twin` currently hardcodes `"(Path B)"` in the calibration note it appends for a measured carry or club speed. If the estimator ever ships, that note must become source-aware (`"(Path A estimate)"`) or a Path A measurement will be mislabelled as a launch-monitor reading on the card. |
| `carry_yd` | Same estimator | **No — gated stretch only.** | Same rule; takes precedence over `club_speed_mph` in `build_twin` when both are present. |
| `sig_face_deg` / `sig_path_deg` | Multi-swing path spread | **No — later step (§8).** 2–3 swings cannot estimate a standard deviation. | Only from a 10-swing set, with its own validation gate (see §8). |
| `putt_mult` | — | **No.** Video cannot measure make rates (§3.5). | Stays benchmark / Path C answer. |

### 4.2 The face-bias sign conversion (read this before implementing)

`build_twin` computes the face bias from the guest's stated miss
*before* applying the `measured` overrides — and the measured
override replaces `face_bias_deg` outright, bypassing that sign
logic. **The intake must therefore convert the guest-side shape
into engine frame before passing it in.** The engine frame's
+lateral is the golfer's right *for a left-handed golfer*
(`sim/course.py` §1.2), so:

- Left-handed guest, miss right (fade): `face_bias_deg = +1.0`
  (capped).
- Left-handed guest, miss left (draw): `face_bias_deg = −1.0`.
- Right-handed guest, miss right (fade): `face_bias_deg = −1.0`.
- Right-handed guest, miss left (draw): `face_bias_deg = +1.0`.
- Straight: `0.0`.

The intake performs this conversion and records both the
guest-side shape and the engine-frame value in the intake report,
so a sign error is visible in review instead of silent in the
twin.

### 4.3 What Path A does not override

- **Speed factor / sigma multiplier:** stay benchmark-derived
  (from the accepted driving distance and the handicap anchors)
  unless the gated estimator ships (§3.4). The video does not
  move them in v1.
- **Strength / weakness:** still from the guest's own words
  (Path C answers), bounded to one handicap band. The video can
  *confirm* a strength/weakness ("the iron swing is pure, the
  claim checks out") or *contradict* it (a "great putter" claim
  with a visibly decelerating stroke gets a reviewer note) — it
  does not reassign them.
- **Aggression (risk threshold):** still from the between-clubs
  answer. Tempo is not aggression: a quick tempo does not make a
  golfer aggressive, and the intake must not conflate them.
- **Handicap:** still guest-stated, still sanity-checked against
  the benchmark tables. The video cannot measure a handicap.

### 4.4 The intake report (the handoff document)

One JSON per guest, produced by the pipeline and read by the human
reviewer before the twin is built:

```json
{
  "guest": "Name",
  "clips": [
    {"clip": 1, "club": "driver", "view": "down-the-line",
     "fps": 120, "quality": "pass",
     "tempo": {"backswing_s": 0.92, "downswing_s": 0.30, "ratio": 3.1},
     "path": "in-to-out",
     "path_confidence": "high",
     "balance": "balanced",
     "ball_flight": "drew, ~250 yd (guest-reported)"}
  ],
  "measured": {
    "source": "path_a",
    "handedness": "right",
    "shot_shape": "draw",
    "face_bias_deg": 1.0,
    "tempo": "3.1:1",
    "balance": "balanced"
  },
  "claim_check": [
    {"claim": "drives 250 yd", "verdict": "accepted",
     "reason": "within tolerance of the 235 yd benchmark; tempo and balance support it"}
  ],
  "quality_flags": [],
  "reviewer_notes": ""
}
```

Fields the pipeline cannot fill are left empty with a reason —
never filled with a plausible-looking guess. An empty field is a
visible gap; a guessed field is a fake number.

---

## 5. Validation flow

Path A twins validate **exactly like Path C twins** — same code
(`calibrate_twin`), same bands, same gate. Nothing about the
validation changes; what changes is what the twin is built from.

### 5.1 The bands (from `sim/twins.py`, restated for the record)

| Check | Band |
|---|---|
| Scoring (running mean) | ±3 strokes of the handicap benchmark |
| Driving (running mean, driver-only) | ±8 yd of the calibrated number |
| Fairways / GIR (running mean) | ±10 points of the calibrated numbers |
| Longest drive | ≤ benchmark + 75 yd |
| Long putts holed (≥40 ft) | ≤ 1 per round |

The gate is the **running mean across validation rounds** (minimum
2 rounds), not any single round — one round's score carries a ~5–6
stroke standard deviation, and Mas himself scored 71–89 across six
seeds on this engine. A well-calibrated twin passes the ±3-stroke
band only about two times in three even when the calibration is
right; the loop records the mean and the per-round history so the
miss is visible instead of hidden (`twins.py` `_mean_validation`).

### 5.2 What Path A changes about validation (and what it doesn't)

- **It does not change the bands.** A Path A twin must play like
  its handicap, same as a Path C twin. Measured handedness, shape,
  and tempo do not earn a wider band.
- **It changes the starting point.** A measured shape and a
  video-checked driving claim mean the twin starts closer to its
  true numbers, so the validation loop should need fewer
  adjustments. That is an expectation, not a guarantee — if the
  loop still adjusts, the adjustment is recorded the same way.
- **It adds one pre-validation check:** the intake report's quality
  flags must be clear before validation runs. A twin is never
  validated from a clip the pipeline flagged as unreliable — the
  re-film happens first.
- **Measured vs estimated is visible in the validation record.**
  The twin's `validation` record and card show which numbers were
  measured (handedness, shape, tempo) and which were estimated
  (everything else), so a validation miss can be traced to the
  right source.

### 5.3 When the video disagrees with the guest's stated profile

The disagreement rules, in order:

1. **Measured wins.** Where the video measures something (handedness,
   path direction, tempo, balance) and the guest's stated profile
   says otherwise, the measured value is used and the guest is told
   why — on the twin card, in `calibration_notes`, in plain
   language. Example: *"Video shows an out-to-in path and a fade;
   usual miss set to right, not left as stated."*
2. **The ball flight wins over the self-description.** If the
   guest says "I draw it" and the ball faded on both driver clips,
   the shape is fade. The guest is told, with the evidence cited
   (the two clips).
3. **The guest can dispute.** The twin card is the dispute
   mechanism (§6): "If this doesn't look like your game, tell us
   and we'll fix it." A dispute triggers `request_fix` — approval
   resets, the note is recorded, and the intake is re-reviewed by
   a human with the video open. The pipeline's measurement is
   re-checked, not re-asserted. If the human reviewer agrees with
   the guest (e.g. the camera was off-line and the path reading was
   an artefact), the measurement is corrected and the twin is
   re-built.
4. **The guest can re-film.** A re-film is always an option, and it
   is free. A guest who thinks the video caught a bad day can send
   a better one; the twin is re-calibrated through
   `TwinRegistry.recalibrate` and the approval resets.

**What never happens:** the show does not argue with the guest
about their own game, and it does not override a measurement
without evidence. The card shows the evidence; the guest decides
whether it looks like them.

---

## 6. The twin card (Path A additions)

The card is the same one-page card as Path C (`twin_card_dict` /
`render_twin_card`), with three Path A additions:

1. **Provenance line:** `SOURCE path_a (phone video)` — and, per
   field, measured vs estimated. Handedness, shape, and tempo are
   marked measured; driving, fairways, GIR, scoring, and putts are
   marked estimated (benchmark) unless the gated estimator ships.
2. **Tempo line:** `TEMPO 3.1:1 — measured from video (120 fps)`.
   The frame rate is shown, so the error bar is visible.
3. **Video notes:** the sanity-check outcomes, in plain language
   ("Video shows a balanced finish and a 3.1:1 tempo — the 250 yd
   claim is accepted" / "Video shows a clear balance loss — driving
   calibrated to the benchmark, not the claim").

The approval line is unchanged: *"This is how your twin plays. If
this doesn't look like your game, tell us and we'll fix it."* The
guest approves the card before the match airs — no exceptions, same
as Path C.

---

## 7. Privacy and honesty

The video is the guest's. It contains their face and body. The
rules are strict because the format's trust depends on them.

### 7.1 Consent and use

- **Explicit consent:** the guest sends the video for the purpose
  of building their twin. That consent covers calibration only —
  not posting, not training, not any other use.
- **Used only for their twin.** The video and its landmark time
  series are used to calibrate that guest's twin and nothing else.
- **Never posted.** The video never appears on air, on social, in
  a clip, or in any thumbnail. The audience sees the twin card and
  the twin's golf — never the guest's swing video.
- **Never used to train anything.** The video and landmarks are
  never fed to any model-training process, and never shared with
  any third-party AI service. Processing runs on the show's own
  machine with a local, free pose model (§2.1).
- **No likeness, ever.** Pose landmarks are skeleton points. They
  are never rendered as a body, never used to animate an avatar
  that looks like the guest, and never combined with a face or a
  voice. The twin is a skill model with a name (§1 of the spec).

### 7.2 Storage and retention

- **Where:** a private intake folder (Drive, access: Mason + the
  twin system only). No public link, no shared folder, no
  third-party upload.
- **What is kept:** the twin *profile* (numbers) is kept — the twin
  has to persist for rematches and the Record Book. The raw video
  and the landmark time series are **deleted 30 days after the
  twin card is approved**, unless the guest asks to keep them for
  re-calibration.
- **Deletion on request:** immediate, no questions. The guest asks,
  the video and landmarks are deleted the same day, and the guest
  is told it is done.
- **Deletion on retirement:** when a twin is retired (§8 of the
  spec), the video and landmarks are deleted with it, within the
  same 7-day window as the profile removal. The Record Book keeps
  the match history, not the video.
- **Access log:** who opened the intake folder and when, in the
  same spirit as the rest of the show's records. The guest can ask
  and be told.

### 7.3 Honesty rules (carried from the spec, restated for Path A)

- **A twin is only better than the guest if the numbers say so.**
  The video can downgrade a claim; it can never upgrade one
  (§3.6). A measured tempo does not make a twin faster than its
  handicap, and a beautiful swing does not make a twin longer than
  its benchmark.
- **No invented results.** The validation record shows the numbers
  the twin actually played; the card shows the calibrated numbers.
  The two are kept separate and never mixed.
- **Measured vs estimated is shown, not hidden.** The card marks
  every number with its provenance. A guest who sees "estimated"
  next to their driving distance knows exactly how much of their
  twin is their video and how much is the table — and can upgrade
  to Path B (launch monitor) if they want the rest measured.
- **The pipeline refuses rather than guesses.** A figure the
  pipeline cannot stand behind is left empty with a reason, not
  printed with false confidence (§2.2, §4.4).

---

## 8. Build order (with exit criteria) — and what stays manual

Follows the spec's build order (§9): Path C first (done), then
Path A, then the validation round (done), then card + approval
(done). Path A slots into the finished flow; it does not rebuild it.

| Step | What | Exit criteria | Manual / automated |
|---|---|---|---|
| 1. **Intake kit** | Filming instructions (§1.6), submission form (handicap + five answers), private intake folder (§7.2) | Mas films his own five clips following the instructions, and they process end-to-end through step 2. If the instructions fail on Mas, they fail on a guest — fix the instructions, not the guest. | Manual: the instructions are written by a human. Automated: nothing yet. |
| 2. **Pose pipeline** | MediaPipe Pose Landmarker (Tasks API, Full bundle) in Python; landmark extraction; event detection (address / top / impact / finish); tempo + path + balance measurement (§2–§3) | On Mas's clips: handedness correct 10/10; tempo ratio within ±0.1 of a manual frame count; path direction matches the known shot shape on 5/5 swings; quality gate rejects a deliberately bad clip (cropped feet, 30 fps, off-line camera). | Automated: extraction + measurement. Manual: the reviewer reads the intake report (§2.2 step 5). |
| 3. **Sanity-check rules** | Claim tolerances (§3.6) + the video veto + triangulation (§3.3) + the face-bias sign conversion (§4.2) | A deliberately inflated claim (300 yd on a 20-hcp profile, choppy swing) is downgraded with the right note; a plausible claim passes through untouched; a sign-conversion test (left-handed guest, miss right) produces `+1.0` in engine frame. | Automated: the rules. Manual: the reviewer checks the notes read like plain language, not machine output. |
| 4. **Full Path A twin** | Intake → measured dict → `build_twin` → `calibrate_twin` → card → approval (§4–§6) | A Path A twin for a test guest passes the same validation bands as Path C; the card shows measured vs estimated distinctly; the guest (played by Mason in the test) approves it. | Automated: build + validate + card. Manual: guest approval (never automated). |
| 5. **Double-pendulum speed estimator** (gated stretch) | Face-on 120 fps+ clips → pendulum model → club-speed estimate with error bars (§3.4) | **The Mas gate:** within ±5 mph of Mas's known club speed (~110 mph) on 5 swings. If it fails, it does not ship — Path A works without it. | Automated: the estimator. Manual: the decision to ship it, made on the Mas-gate evidence. |
| 6. **Multi-swing dispersion** (later step) | A 10-swing set (same club, same session) → path-spread estimate → `sig_face_deg` / `sig_path_deg` | Path-spread sigma is stable across two sessions for the same golfer (within ±20%); only then does it feed the measured dict. | Automated: the spread. Manual: the decision to trust it, on the stability evidence. |

### What stays manual, permanently

- **The reviewer's read of the intake report** (§2.2 step 5). A
  human watches the video and checks the pipeline's measurements
  against it before the twin is built. This is the quality control
  that stops a bad camera angle from becoming a wrong twin.
- **The guest's approval of the twin card.** Never automated, never
  skipped, never assumed from silence.
- **The dispute resolution** (§5.3 step 3). A guest who says
  "that's not my game" gets a human with the video open, not a
  re-run of the pipeline.
- **The decision to ship the speed estimator** (step 5) and the
  dispersion step (step 6). Both are gated on evidence, and the
  evidence is judged by a human.

### What is automated, end to end

- Landmark extraction, event detection, tempo and path measurement,
  the measured-dict assembly, the claim-check rules, the validation
  rounds, and the card generation. Once the reviewer clears the
  intake report, the rest of the flow runs without a human in the
  loop — the same autonomy as the rest of the show.

---

## 9. Open questions (decided here, not left open)

- **Should the guest film in slo-mo, or is 60 fps enough?**
  Decided: slo-mo preferred (120 fps), 60 fps minimum for tempo,
  30 fps accepted for shape/balance/handedness only. The
  instructions ask for slo-mo; the pipeline degrades gracefully.
- **Should the pipeline run on the guest's phone (browser) or on
  the show's machine?** Decided: on the show's machine in v1
  (simpler, one environment, no guest-side debugging). Browser
  on-device processing is the privacy upgrade for later — it is
  strictly better, but it is not a launch requirement.
- **Should video-measured speed ever override the benchmark?**
  Decided: no. Even if the estimator ships, it nudges within the
  claim tolerance only (§3.4). The benchmark is the anchor; the
  video is a check on it.
- **What if a guest has no range and films in their backyard into
  a net?** Accepted — the pipeline needs the swing, not the ball
  flight. The guest-reported result becomes "into a net, felt
  solid" and the ball-flight signal drops out of the triangulation
  (§3.3); the stated miss + path direction carry it. The card
  notes the net.
- **What if the guest is left-handed?** Handled end to end:
  handedness is measured (§3.1), the face-bias sign conversion is
  handedness-aware (§4.2), and the twin plays left-handed in the
  engine like Mas does. No left-handed guest is treated as a
  mirror-image afterthought.

---

## 10. What this design deliberately does not do

- **No speed number in v1.** Stated three times in this document
  because it is the decision most likely to be re-litigated under
  pressure from a guest who wants a number. The answer stays no
  until the Mas gate passes (§3.4).
- **No face, voice, or body likeness.** Not from the video, not
  from the landmarks, not ever (§7.1).
- **No upload portal in v1.** A link the guest already knows how
  to send beats an account they have to create (§1.5).
- **No cloud video AI.** No video leaves the show's machines, no
  per-call cost, no third-party model sees the guest (§2.1, §7).
- **No new validation bands.** Path A twins prove themselves
  against the same bands as Path C (§5.1). A measured twin that
  fails validation is a calibration problem, not a reason to move
  the goalposts.
- **No Path B in this document.** Launch-monitor intake is the
  most precise path and the last build step in the spec's order
  (§9, step 10) — it gets its own design when Path A is live.

---

## 11. Sources and verification notes

- **MediaPipe Pose Landmarker** — Google AI Edge docs,
  `developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker`
  (checked Nov 2026): 33 landmarks, image + 3D world coordinates,
  BlazePose GHUM 3D, Lite/Full/Heavy bundles, on-device
  (Android/iOS/web/Python), Apache 2.0 repository and code samples.
  **Licence caveat:** Google does not publish a separate licence
  statement for the model weights on the model page — re-check
  before shipping; RTMPose (Apache 2.0) is the fallback (§2.1).
- **What video can and cannot measure** — "Swing analysis from
  ordinary phone video", `aigolfcoach.im` (checked Nov 2026):
  frame timing is genuinely measured (120 fps → ~8 ms on the
  top-to-impact interval); joint angles are model outputs with
  confidence bands; club head speed, ball speed, spin, launch,
  smash, face angle, and carry are not recoverable from a phone
  clip; software printing a speed from video is inferring from
  body motion. This document's §3 follows that account.
- **Clubhead travel between frames** — FrameFlo, "Golf Swing Slow
  Motion" (checked Nov 2026): at 90 mph, ~4.4 ft per frame at
  30 fps, ~2.2 ft at 60 fps, ~13 in at 120 fps, ~6.6 in at
  240 fps.
- **Double-pendulum estimation** — Gokhale, "Golf swing simulation
  and carry distance prediction from smartphone motion capture
  estimates" (OpenCap video analysis → double-pendulum model →
  trajectory model, validated against known carry and clubhead
  velocities); GolfSpeed, `willconia.com` (checked Nov 2026):
  17 joints, face-on clip, shoulder-to-wrist length as the scale
  reference, 60 fps or more ideal, explicitly an estimate for
  trend-tracking, not a radar reading.
- **Engine numbers used as anchors** — `sim/twins.py` (read Nov
  2026): Mas's measured driver-only mean 284.0 yd; `MAS_DRIVER_ROLL_YD
  = 20.6`; claim tolerances 15 yd / 0.10 / 2.0 putts; validation
  bands ±3 strokes / ±8 yd / ±10 points; face-bias bound ±1.0°;
  the `measured` dict keys and the sign-conversion rule (§4.2).
  Mas's club speed ~110 mph / ball speed ~161 mph from the sim
  spec (`sim-engine.md` §3, as referenced by `twins.py`).
- **Unverified in this document (flagged, not asserted):** Kinovea
  (free, open-source video analysis) as a manual frame-by-frame
  review tool for the human reviewer — a candidate for step 2's
  review workflow, to be verified at build time; it is not load-
  bearing for the design. Exact MediaPipe Python package version
  and the Tasks API call shape for video mode — to be pinned at
  build time from the current docs, not from this document.
