# Mas Golfs — QA & Verification Test Plan

**Version 1.0 · 2026-11-12**

This is the verification plan for the whole Mas Golfs system: the sim engine, the web build, the broadcast stack, the graphics and commentary, and the Clubhouse Coins economy. Every check below has a **pass/fail criterion** — a number, a log line, or a visible behaviour — not a feeling. A test that cannot fail is not a test.

**How to use it:** run sections in order. §1 (sim calibration) gates the broadcast stack — do not build overlays and commentary on an uncalibrated sim. §3 (web build) gates any public stream. §6 is the single gate for going live.

**Reference docs:** `sim-engine.md` (§3 calibration, §6 learning loop, §7 handicap), `broadcast-stack.md` (§2 director, §3 NodeCG graphics, §4 commentary), `coins-economy.md` (§5 odds, §6 payouts, §8 anti-abuse), `performance-audit.md` (P0-1 memory leak, P0-2 hole-change hitch, verification checklist), `course-design-v3.md` (hole data — championship length, 7,602 yards), `launch-playbook.md` (§4 metrics).

---

## 1. Sim calibration harness — 10,000 rounds against the +3 benchmarks

### 1.1 What the harness is

A headless runner that imports the engine, seeds it, and plays rounds with **rendering disabled** (no Three.js, no DOM, no commentary). It runs N rounds, records every shot, and emits a report comparing measured aggregates to the +3 benchmark table. It must run in a single Node command and finish in under 5 minutes for 10,000 rounds — the engine budget is < 50 ms of CPU per round (sim-engine §5), so a 10,000-round run that takes longer than 5 minutes is itself a failure of the performance budget.

### 1.2 Benchmark table (from sim-engine §3 — do not re-tune these without a written reason)

> **v3 note:** the Scoring average (72–74) and GIR (~55–57%) targets above are **estimates for the 7,602-yard v3 course** ([course-design-v3.md](course-design-v3.md) §5.3), **pending confirmation by the 10,000-round harness**. The v1 targets were 71–73 and ~60%. The pass bands are ±5% around the v3 targets. If the harness says otherwise, the harness is right — update this table from its results.

| Metric | Target (+3) | Pass band (±5%) | Notes |
|---|---|---|---|
| Driving distance (carry + roll, driver, dry/fairway) | 265–275 yd | 252–289 yd mean | Measure mean over all driver tee shots on par 4s/5s |
| Fairways hit | 55–60% | 52–63% | Par 4s/5s only; a tee shot in the first cut counts as a miss |
| Greens in regulation | ~55–57% | 52–60% | Ball on the putting surface in regulation |
| Scoring average | 72–74 | 68.4–77.7 | Mean over the full run |
| Approach proximity, 100 yd | 18–20 ft | 17–21 ft | Mean distance to hole, approach shots only |
| Approach proximity, 150 yd | 24–28 ft | 23–29 ft | Mean distance to hole |
| Approach proximity, 200 yd | 36–41 ft | 34–43 ft | Mean distance to hole |
| Putting: make rate, 3 ft | 99% | 94–100% | Floor is 94% (99% − 5 points), not 94.05% |
| Putting: make rate, 5 ft | 91% | 86–96% | |
| Putting: make rate, 10 ft | 40% | 35–45% | |
| Putting: make rate, 20 ft | 14% | 9–19% | |
| Putting: make rate, 50 ft | 1.2% | 0–6% | Floor 0; check the upper bound |
| Birdies per round | 3–4 | 2.85–4.2 | Mean |
| Bogeys or worse per round | 3–4 | 2.85–4.2 | Mean |
| Rounds under par | 25–35% | 20–40% | Share of rounds < 72 |
| Best round in 10,000 | 63–66 | — | Sanity bound, not a pass band: a 59 must be *possible* but vanishingly rare (see §1.5) |
| Rounds of 59 or better in 10,000 | 0–2 | — | See §1.5 |

### 1.3 Harness checks

| # | Check | Pass criterion |
|---|---|---|
| H-01 | Run 10,000 rounds, seeded, headless | Completes; exits 0; runtime < 5 min; report written to `qa/reports/calibration-<date>.json` |
| H-02 | Every metric in §1.2 inside its pass band | All rows PASS. One row out = FAIL, fix the dispersion table, re-run |
| H-03 | Determinism | Same seed → byte-identical event stream (hash the `seq` + `type` + rounded shot outcomes). Two runs, same seed, identical hash |
| H-04 | Different seeds diverge | 10 different seeds → 10 different round scores; no two identical 18-hole score sequences |
| H-05 | No impossible shots | Zero shots with carry > 340 yd (driver), zero approach shots landing > 80 yd from the pin, zero putts holed from > 60 ft (except a logged fluke, max 1 per 10,000 rounds) |
| H-06 | No stuck states | Zero rounds exceeding the 12-shot-per-hole safety cap; zero holes where the engine emits no `hole_complete` event; zero rounds with no `round_complete` event |
| H-07 | Mishit rates sane | Thin/chunk/toe/heel/shank shares within ±3 points of the spec probabilities; no mishit type at 0% or > 25% of all full shots |
| H-08 | Lie gating enforced | Zero shaped shots (draw/fade) from heavy rough; zero flop shots from a buried lie; zero knockdown shots *not* played into ≥ 15 mph headwind when the spec says knockdown is mandatory |
| H-09 | Decision time | Mean shot-decision time < 5 ms, p99 < 20 ms, measured on a mid-range phone (or the CI runner with a stated equivalent); round sim time < 50 ms mean |
| H-10 | Event schema valid | Every emitted event validates against the schema in sim-engine §1 (required fields present, types correct, `seq` monotonic within a round, `event_id` unique) |
| H-11 | Learning loop moves | After 50 rounds, the one-fix rule has produced at least one applied adjustment (see §1.4); the adjustment field in `round_start` is non-empty and references a real prior round |
| H-12 | Handicap math | Handicap index computed from the last 20 differentials matches a hand-checked spreadsheet for 3 sampled rounds to ±0.1; index is positive (better than scratch) for a +3 |

### 1.4 Learning-loop checks

| # | Check | Pass criterion |
|---|---|---|
| L-01 | One fix only | Exactly one `focus_fix` per round in `round_start`; never two, never zero after round 3 |
| L-02 | Fix is evidence-based | The fix's source area is the worst strokes-gained category over the last 3 rounds, verified by recomputing SG from the event log |
| L-03 | Fix has a mechanism | The adjustment is one of the five allowed mechanisms (aim offset, club up, trajectory, target line, aggression) — never "try harder" or a dispersion change |
| L-04 | Dispersion never changes | The σ values in the golfer model are identical at round 1 and round 200 (diff the config object). Improvement comes only from aim/risk/baseline changes |
| L-05 | Improvement is slow | Scoring average over rounds 1–20 vs. rounds 180–200 improves by 0.0–1.5 strokes. More than 1.5 = the loop is overpowered; a worsening trend = a bug |
| L-06 | No fix churn | The same fix is not repeated for more than 3 consecutive rounds unless the SG data still supports it |

### 1.5 The 59 check (Road to 59 credibility)

The season arc is the chase for 59. The sim must make 59 **possible but extremely rare** — a near-perfect day, not a normal one.

| # | Check | Pass criterion |
|---|---|---|
| R-01 | 59 is reachable | In 10,000 rounds, at least one round scores ≤ 62 (the engine can produce a hot day). On the longer v3 course the ≤ 62 count is expected to fall — the gate still holds, the frequency does not have to match v1 |
| R-02 | 59 is rare | Rounds of 59 or better: 0–2 per 10,000. Three or more = the dispersion is too tight; re-tune. (v3 expectation: the count stays at 0–1 — P(59) ~0.3% per round, down from ~0.5% on v1; see course-design-v3.md §5.3.) |
| R-03 | A 59 is earned, not fluky | Any round ≤ 61 in the harness has: GIR ≥ 15, putts ≤ 26, zero penalty strokes, and no putt holed from > 25 ft. If a low round depends on a 50-footer, the putting model is wrong |
| R-04 | Pace arithmetic correct | The on-screen "59 pace" indicator matches the actual score through the hole being played (score − par through N holes, projected honestly — no rounding that hides a bogey) |

---

## 2. Broadcast soak test — 24/7 unattended run

### 2.1 Setup

Run the full broadcast stack (web build → OBS → NodeCG → Restream → a **private/unlisted** YouTube test stream) unattended for the stated duration. Nobody touches it. The watchdog (broadcast-stack §7) is the only responder. Log everything to `qa/logs/soak-<date>.log`.

### 2.2 Duration gates

| Stage | Duration | Gate to proceed |
|---|---|---|
| Soak A (smoke) | 1 hour | All §2.3 checks pass; zero manual interventions |
| Soak B (overnight) | 12 hours | All §2.3 checks pass; zero manual interventions |
| Soak C (week) | 7 days | All §2.3 checks pass; ≤ 1 watchdog restart, zero manual interventions. **This is the go-live gate.** |

### 2.3 What to monitor (pass/fail per stage)

| # | Metric | How to check | Pass criterion |
|---|---|---|---|
| S-01 | Uptime | OBS/Restream status + stream health API | Stream live for the full stage duration; zero gaps > 30 s |
| S-02 | GPU memory | `renderer.info.memory` sampled every 10 min (geometries, textures) | Flat across rounds: last-round value within ±5% of first-round value. Any steady climb = FAIL (the P0-1 leak from performance-audit) |
| S-03 | JS heap | DevTools `performance.memory` or equivalent, sampled every 10 min | No steady climb; heap at hour 12 within ±10% of hour 1 |
| S-04 | Frame rate | In-app FPS readout, sampled every 10 min | p50 ≥ 55 fps, p5 ≥ 30 fps on the target machine (mid-range laptop, High tier). Zero 10-second stretches below 20 fps |
| S-05 | Rounds completed | `round_complete` events in the event log | ≥ 1 round per ~2.5 hours of wall time at broadcast speed; round counter increments monotonically, never resets |
| S-06 | Event bus health | WebSocket port 4456 heartbeat + `seq` continuity | Zero gaps in `seq` within any round; zero disconnects > 5 s; reconnect (if any) restores within 10 s with no lost events |
| S-07 | Director behaviour | Spot-check 10 random hole transitions from the recording | Camera holds ≥ 2 s on every cut; never cuts mid-flight; falls back to the wide cam (never a black frame) on any error |
| S-08 | Overlay freshness | NodeCG replicant timestamps vs. sim events | Scorebug updates within 1 s of the event; leaderboard updates within 2 s of `hole_end`; no stale data older than 5 s on screen |
| S-09 | Commentary | Log of TTS jobs vs. events | One decision line before every shot; one result line at landing; zero commentary jobs started during a swing (see §4) |
| S-10 | Audio | Recording spot-check, 5 min per hour | Ambient bed audible and never silent; no clipping; no overlapping stingers |
| S-11 | Watchdog | Watchdog log | Every fault (if any) logged with timestamp and action; restart restores the stream without human input |
| S-12 | Disk | `~/mas-golfs/clips/` size | Grows only by the clip-retention policy; no unbounded growth (> 500 MB over 7 days = FAIL unless the policy says otherwise) |

### 2.4 Failure responses (what happens when it breaks)

| Failure | Expected response | Pass criterion |
|---|---|---|
| WebSocket bus drops | Director holds the wide cam; overlays freeze on last good data (never blank); bus reconnects | Stream never goes black; recovery ≤ 10 s; event gap logged |
| OBS crashes | Watchdog restarts OBS; stream resumes | Resume ≤ 60 s; no manual intervention |
| WebGL context lost | Context-lost handler fires; renderer re-initialises; round state restored from the event log | Stream recovers ≤ 30 s; no permanent black screen; the incident is logged |
| NodeCG crashes | Graphics fall back to a static scorebug (last known state) | Stream continues; no blank overlays for > 10 s |
| TTS service down | Commentary silences; ambient bed carries the stream | No error audio, no repeated retry spam in the log (max 1 retry/min) |
| Machine reboot | Autostart brings up the full stack | Full broadcast restored ≤ 5 min after boot with no manual login |

### 2.5 Soak sign-off

A soak stage is signed off only when: the log shows the full duration with no manual interventions, every §2.3 row is PASS, and any §2.4 failure that occurred was handled by the documented response. One manual intervention = the stage restarts from zero.

---

## 3. Web build checklist

### 3.1 Frame rate — locked 60 fps (mid-range laptop)

Reference machine: a mid-range laptop (integrated or entry discrete GPU, 1080p display). Record the exact machine in the test report.

| # | Check | Pass criterion |
|---|---|---|
| F-01 | Steady-state frame rate | p50 ≥ 58 fps, p5 ≥ 50 fps over a 10-minute sample, High tier, 1080p |
| F-02 | Hole-change hitch | No frame over 50 ms during any hole transition in a full 18-hole round (performance-audit P0-2) |
| F-03 | Swing + flight | No frame over 33 ms during any swing or ball flight in a full round |
| F-04 | Tier step-down | Forcing the Balanced tier (simulate a slow machine) keeps p50 ≥ 55 fps; the step-down never triggers on the reference machine |
| F-05 | Recovery | After a forced step-down, the hysteresis controller recovers to High when load drops — it must not be one-way (performance-audit P1-2) |
| F-06 | Shadow tiers | Each tier (2048 PCFSoft / 1024 / off) visibly changes the shadow map; the off tier costs measurably less GPU time than 2048 |

### 3.2 Mobile smoothness

Reference device: a mid-range phone (2–3 years old), 4G/Wi-Fi, battery ≥ 50%.

| # | Check | Pass criterion |
|---|---|---|
| M-01 | Frame rate | p50 ≥ 45 fps, p5 ≥ 30 fps over 10 minutes, Balanced tier |
| M-02 | Load time | First paint ≤ 3 s on Wi-Fi; ≤ 5 s on 4G; no render-blocking external fonts (performance-audit: fonts must be local or the page must not wait on them) |
| M-03 | Touch | All controls (pause, speed, camera, fullscreen, coins) tappable with a finger; no control smaller than 44×44 px; no hover-only feature |
| M-04 | Battery | 30 minutes of viewing drains ≤ 10% battery on the reference device (screensaver mode on when the tab is backgrounded — see M-06) |
| M-05 | Orientation | Works in portrait and landscape; no layout breakage at 360 px wide; scorebug readable at phone width |
| M-06 | Background tab | Hiding the tab pauses the render loop and the AudioContext within 5 s; returning resumes within 2 s (performance-audit P1-3) |

### 3.3 Background-tab behaviour (desktop)

| # | Check | Pass criterion |
|---|---|---|
| B-01 | Pause on hide | `visibilitychange` pauses rendering and audio; CPU usage drops to < 5% of foreground within 10 s |
| B-02 | Screensaver mode | After 5 minutes hidden, the page is in 30 fps screensaver mode (or fully paused) — it never burns a full frame rate in a hidden tab |
| B-03 | Resume | Returning to the tab restores the live state (correct hole, score, and shot) within 2 s; the sim has not fallen behind or raced ahead |

### 3.4 Context-loss recovery

| # | Check | Pass criterion |
|---|---|---|
| C-01 | Forced context loss | Trigger `WEBGL_lose_context.loseContext()` in DevTools; the page shows a "recovering" state, never a permanent black screen |
| C-02 | Recovery time | Full scene restored ≤ 30 s after the forced loss, with the correct hole and score |
| C-03 | No data loss | Scorecard, leaderboard, and handicap state are identical before and after the loss (they live in the event log / localStorage, not in GPU memory) |
| C-04 | Repeat loss | Three consecutive forced losses, 10 s apart — the page recovers every time |

### 3.5 The 3-round soak (from performance-audit.md)

Run the web build alone (no OBS) for 3 full rounds on the reference laptop, DevTools Performance open.

| # | Check | Pass criterion |
|---|---|---|
| K-01 | GPU memory flat | `renderer.info.memory.geometries` and `.textures` at the end of round 3 within ±5% of the end of round 1 (P0-1) |
| K-02 | No context loss | Zero `webglcontextlost` events across 3 rounds |
| K-03 | Frame time stable | Mean frame time in round 3 within ±10% of round 1; no upward drift |
| K-04 | Heap stable | JS heap at end of round 3 within ±10% of end of round 1 |
| K-05 | 5-minute background test | Hide the tab for 5 minutes mid-round; return; the round is intact and the frame rate recovers (performance-audit verification checklist) |

---

## 4. Graphics & commentary checklist

### 4.1 NodeCG graphics — every graphic renders correctly

Check each graphic in OBS at 1080p and on a phone-width preview. Screenshot each one; keep the screenshots in `qa/screenshots/<date>/`.

| # | Graphic | Pass criterion |
|---|---|---|
| G-01 | Scorebug | Readable in 3 seconds by a newcomer: player name (Mas), hole, score to par, handicap pill, and "Road to 59" context all present; no text overflow at 1080p or 360 px wide |
| G-02 | Leaderboard | All-time, last-10, and top-10 tables render with correct numbers (spot-check 5 rows against the event log); updates within 2 s of `hole_end` |
| G-03 | Lower-thirds (3 variants) | Shot-data lower-third fires on every strike with the right club, distance, and shape; decision lower-third fires before every shot; milestone lower-third fires on birdies/eagles/records only |
| G-04 | Ticker | Scrolls without stutter; shows live aggregates (all-time score, last-10, handicap); no stale data older than 5 s |
| G-05 | Player card | Shown between holes with correct season stats; the "Mas — Mason's digital twin" line is present; no placeholder text anywhere |
| G-06 | Hole card | Shown on flyovers with the correct hole name, par, yardage, and stroke index (cross-check against course-design-v3) |
| G-07 | No graphic overlap | No two graphics occupy the same screen region at the same time in a full-round recording |
| G-08 | No placeholder | Zero instances of lorem ipsum, "TBD", "undefined", "NaN", or empty fields in any graphic across a full round |
| G-09 | Phone preview | Every graphic is legible in the phone-width preview; nothing is cut off at the edges |

### 4.2 Commentary — lands on events, never over swings

| # | Check | Pass criterion |
|---|---|---|
| V-01 | Decision line | A decision line (club, target, reasoning) plays before every full shot; it starts ≥ 1 s before the swing begins |
| V-02 | Result line | A result line plays at landing (or within 1 s of it) for every shot; it states the actual outcome, not the predicted one |
| V-03 | No speech over swings | Zero commentary audio overlapping the swing (from address to impact) in a full-round transcript check — the swing is sacred silence |
| V-04 | Two voices distinct | Play-by-play and color voices are audibly different; the color line only appears at apex or on notable outcomes, never on routine shots |
| V-05 | No repeats in a round | No identical commentary line plays twice in the same round (cached lines are allowed across rounds, not within one) |
| V-06 | Numbers correct | Every number spoken (distance, club, score) matches the event data — spot-check 20 lines against the event log, 20/20 correct |
| V-07 | Cost guardrail | TTS spend for a 24-hour test run is $0 (free voice) or within the documented free-tier budget; zero paid TTS calls in the log |
| V-08 | Silence is fine | Gaps between events have ambient bed only — no filler speech, no "and now we wait" lines |

### 4.3 Broadcast feel — the stranger test

| # | Check | Pass criterion |
|---|---|---|
| T-01 | The stranger test | Show 60 seconds of the tee-cam footage to a golfer with no context. PASS if they ask what tournament it is or who the player is. FAIL if they say "that's a video game" unprompted |
| T-02 | No dead air | In a 30-minute recording, no stretch longer than 20 s with no camera movement, no graphic change, and no audio change (excluding the swing itself) |
| T-03 | The show reads | A first-time viewer can answer, after 60 seconds: who is playing, what hole, what score, and what the chase is (Road to 59) |

---

## 5. Coins economy test

Reference: `coins-economy.md` (§5 odds, §6 payouts, §8 anti-abuse).

### 5.1 Odds math

| # | Check | Pass criterion |
|---|---|---|
| O-01 | Odds from real stats | Base probability for a fairway market equals Mas's rolling fairway rate (55–60%) ± 2 points; verify by recomputing from the last 10 rounds in the event log |
| O-02 | Adjustments visible | Form, hole-difficulty, and conditions adjustments are shown on screen with the market; the displayed odds match the computed odds to 2 decimal places |
| O-03 | No overround | The sum of implied probabilities across all outcomes of a market is ≤ 1.00 (no house cut — the economy takes nothing) |
| O-04 | Volume moves odds | A simulated 80/20 volume split moves the odds by no more than ±25% from open, and in the direction of the volume |
| O-05 | Odds never invert | The favourite never becomes the underdog purely from volume; the model/pool blend caps at 50/50 |

### 5.2 Payout splits

| # | Check | Pass criterion |
|---|---|---|
| P-01 | Proportional split | In a simulated 10-viewer market, winners split the pool in exact proportion to stake; total paid out equals total staked (± rounding, max 1 CC) |
| P-02 | No house cut | Total paid out across 100 simulated markets equals total staked (± 1 CC per market rounding). The system never keeps a cut |
| P-03 | Skins carryover | A tied skin carries its pot to the next hole; the pot amount is correct on screen and in the ledger |
| P-04 | Nassau sweep bonus | Winning front + back + overall pays the +25% sweep bonus from the system bonus pool, never from other viewers' stakes |
| P-05 | Rounding rule | All payouts round down; the leftover (max 1 CC per payout) is accounted for in the ledger, never silently kept |
| P-06 | Void/refund | A voided market (e.g. a shot never happens) refunds every stake in full within 2 s of the void |

### 5.3 Leaderboard resets

| # | Check | Pass criterion |
|---|---|---|
| R-01 | Weekly reset | At Monday 00:00 ET the weekly board resets to 1,000 CC for every viewer; the previous week's winner is recorded in the hall of fame |
| R-02 | All-time never resets | The all-time board is unchanged by the weekly reset (spot-check 5 viewers before and after) |
| R-03 | Daily board | The daily net-winnings board resets at midnight ET and shows only that day's results |
| R-04 | Reset is atomic | No viewer can place a prediction during the reset window that lands on the wrong week's board (test with a prediction submitted at 23:59:58 and one at 00:00:02) |

### 5.4 Anti-abuse

| # | Check | Pass criterion |
|---|---|---|
| A-01 | One wallet per identity | Two wallets cannot be created for the same platform identity; a second attempt returns the existing wallet |
| A-02 | No transfers | There is no transfer function in the API; a direct transfer call returns an error |
| A-03 | Rate limit | 61 predictions in one hour from one identity → the 61st is rejected with a clear message |
| A-04 | Stake caps enforced | A stake above the per-market cap (per-shot 100, per-hole 250, round-level 500 CC) is rejected, not silently reduced |
| A-05 | Watch-time cap | Watch-time earnings stop at 360 CC/day; further watch time earns 0 |
| A-06 | No farming vectors | Chat messages, follows, and referrals earn 0 CC (verified in the ledger — no earning entries from those actions) |
| A-07 | Streak bonus from the pool | A streak bonus is paid from the system bonus pool, never from other viewers' stakes; the pool balance decreases by exactly the bonus amount |
| A-08 | No automated wipes | No automated process can zero a balance; bans require human review (verify by code inspection — no `balance = 0` path outside the manual review flow) |

### 5.5 Economy end-to-end

| # | Check | Pass criterion |
|---|---|---|
| E-01 | First-bet flow | A new viewer can arrive, see a market, stake, watch the tracer, and be paid out — all within 30 seconds, with no onboarding flow |
| E-02 | Latency | Stake confirmed in < 1 s; payout settled in < 2 s of the result event |
| E-03 | Ledger integrity | Every prediction, payout, and bonus has an append-only ledger entry; the sum of all ledger entries reconciles to the sum of all wallet balances |
| E-04 | Economy-down failure | With the economy service stopped, the stream continues, markets show "predictions paused", and no viewer loses coins |

---

## 6. Go-live checklist — the first stream

All items must be checked before the first public stream. One unchecked item = no launch.

### 6.1 Gates that must already be green

| # | Item | Evidence |
|---|---|---|
| GL-01 | Sim calibration (§1) | `qa/reports/calibration-<date>.json` shows all rows PASS, run within the last 7 days |
| GL-02 | 7-day soak (§2) | Soak C signed off; log in `qa/logs/soak-<date>.log` |
| GL-03 | Web build (§3) | 3-round soak (§3.5) passed on the reference laptop and phone |
| GL-04 | Graphics & commentary (§4) | Full-round recording reviewed; zero G-08/V-03 failures |
| GL-05 | Coins (§5) | All payout and anti-abuse checks PASS on the test economy |
| GL-06 | Performance audit P0s fixed | P0-1 (dispose) and P0-2 (hole-change hitch) verified fixed by re-running K-01/K-02; the fix is in the live build, not just in a branch |

### 6.2 Launch-day checks (run the morning of)

| # | Item | Pass criterion |
|---|---|---|
| GL-07 | The build is the latest | The live `index.html` matches the repo HEAD commit; branding says "Road to 59" (zero "Road to 62" strings — `grep -c "62" index.html` returns 0 in branding text) |
| GL-08 | Stream keys work | A 5-minute private test stream to YouTube and Twitch both go live and are viewable |
| GL-09 | AI-use disclosure | The YouTube stream description carries the AI-generated content disclosure; the Twitch stream carries the equivalent disclosure |
| GL-10 | Watchdog armed | The watchdog is running and its last health check is < 60 s old; the restart path was tested this week |
| GL-11 | Clip pipeline armed | The replay buffer is saving to `~/mas-golfs/clips/`; one test clip was produced and is viewable |
| GL-12 | Coins seeded | The system bonus pool is seeded at 10,000 CC; the weekly board is live; a test prediction was placed and settled |
| GL-13 | Mason's phone check | Mason opens the stream on his phone, watches 2 minutes, and confirms it looks and sounds right (the only human check in the list) |
| GL-14 | The stranger test (§4.3) | Passed on the live build, not an old recording |

### 6.3 Day-1 monitoring (first 24 hours live)

| # | Item | Pass criterion |
|---|---|---|
| GL-15 | Someone watches the first hour | A human (Mason or a delegate) watches the first 60 minutes live, with the log open, ready to kill the stream if anything in §2.4 fires and is not handled |
| GL-16 | First clip out | The first auto-clip is posted within 24 hours of go-live (launch-playbook cadence) |
| GL-17 | Metrics baseline | The weekly tracking sheet (launch-playbook §4.5) has its first row filled: uptime, clips posted, stream views, returning viewers, predictions placed, Mas's scoring average |
| GL-18 | Incident log | Any incident in the first 24 hours is logged with timestamp, symptom, and resolution; the log is reviewed before day 2 |

---

## Appendix — test artefacts and where they live

| Artefact | Location |
|---|---|
| Calibration reports | `qa/reports/calibration-<date>.json` |
| Soak logs | `qa/logs/soak-<date>.log` |
| Screenshots (graphics) | `qa/screenshots/<date>/` |
| Test recordings | `qa/recordings/<date>/` (keep 7 days, then delete) |
| Incident log | `qa/incidents.md` (append-only, one line per incident: date, time, symptom, cause, fix) |
| This plan | `docs/qa-plan.md` |

**Rule for all artefacts:** if it is not written down, it did not happen. A verbal "it looked fine" is not a pass.
