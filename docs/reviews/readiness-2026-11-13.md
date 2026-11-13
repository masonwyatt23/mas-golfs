# Mas Golfs — Go-Live Readiness Report

**Date:** 2026-11-13 (audit performed ~05:00–05:30 UTC)
**Auditor:** readiness audit (subagent), against `docs/qa-plan.md` §6 and `docs/deployment-runbook.md`
**Repo state at audit time:** local checkout `~/workspace/mas-golfs-repo`, sync record 39 pushes, latest commit `ba6d268b` (course-design-v3.md)
**Verdict: NOT READY — 0 of 18 go-live gates green.**

## Verdict up front

| §6 section | Green | Red | Blocked |
|---|---|---|---|
| 6.1 Gates that must already be green (GL-01–GL-06) | 0 | 6 | 0 |
| 6.2 Launch-day checks (GL-07–GL-14) | 0 | 4 | 4 |
| 6.3 Day-1 monitoring (GL-15–GL-18) | 0 | 0 | 4 |
| **Total** | **0** | **10** | **8** |

Verdict key used throughout: **green** = verified passing with evidence in hand. **red** = checked and failing, or required and absent/never run. **blocked** = cannot even be attempted until a dependency lands. A gate that was never run is red, not green, and "verified on the VM" is not "verified on the box."

The blunt summary: the code that exists is good and well unit-tested on this Linux VM, but **nothing has ever run on the real 8GB MacBook Pro**; the sim is **uncalibrated** (its own harness reports FAILED on the last sample); the web build is **mid-rebuild** with its repo export a full build stale; the coins economy **does not exist as code**; and **no soak of any duration, no private test stream, and no failover drill has ever happened**. The earliest honest launch shape is: finish the retune + calibration, land and freeze the web build, do an on-box install weekend, then run the 7-day soak. The soak alone is 7 days of calendar time.

Two process notes that affect every verdict below:

1. **The tree was a moving target during this audit.** The flight-model retune agent was actively editing `sim/course.py`, `sim/tests/test_sim.py`, and `sim/verify_carry.py` while I ran tests (mtimes 05:06–05:09 UTC), a `docs/putting-model-v2.md` design doc appeared at 05:08 UTC, and the artifact clean-screen rebuild was running the whole time. Any result in this report is a snapshot of 05:00–05:30 UTC, Nov 13 — re-verify before launch.
2. **This audit ran on a Linux VM, not the broadcast box.** Every "passes" below means "passes on this VM." The 8GB MacBook Pro has run zero minutes of any Mas Golfs component. Apple Silicon on that box was confirmed by Mason on Nov 12, which unblocks the MLX plan — but nothing has been installed or executed there.

## How this audit was done

- Re-ran the unit suites myself on this VM: bus 18/18, commentary 34/34, clip-pipeline 58/58, mlx-verify 51/51 (see component table). Sim suite: re-run in progress at time of writing — see GL-01.
- Read `docs/qa-plan.md` §6, `docs/deployment-runbook.md` end to end, and the READMEs of sim, bus, commentary, nodecg-bundle, clip-pipeline, ops, mlx-verify.
- Checked for QA artefacts: **no `qa/` directory exists anywhere in the repo** — no calibration reports, no soak logs, no screenshots, no incident log. `docs/reviews/` did not exist until this audit created it.
- Checked the repo web export against the live artifact, checked artifact build status, and checked for coins-economy code (none exists).

---

## §6.1 — Gates that must already be green

### GL-01 — Sim calibration (§1) — 🔴 RED

- **No calibration report exists.** `qa/reports/` does not exist; the 10,000-round harness has never been run at any round count that counts as a gate.
- **The last calibration sample fails its own harness.** Per `sim/README.md`, the post-refit 6-round Monte Carlo sample (n=120) passes driving (272.5 yd, band 265–275) and scoring (71.5, band 71–73), but the harness still reports **CALIBRATION FAILED overall**: fairways 43% (target 57%), GIR 68% (target 60%, overshooting in the good direction), scrambling 49% (target 60%), sand saves 100% (tiny sample). The README's own next step is a §3.2 sigma retune, not another physics change — and 6 rounds is a sanity sample, not the gate.
- **The gate as written is infeasible in the current implementation.** `qa-plan.md` §1.1 demands 10,000 rounds in under 5 minutes (<50 ms/round). The Python reference implementation runs a round in ~5–20 s (sim README, honest perf note), so 10,000 Monte Carlo rounds is ~14–55 hours. `sim/calibrate.py` defaults to 1,000 rounds MC (`--rounds` default 1000, `--fast` default False). The fast rule-based path would meet the time budget but is disqualified by its own docs: it is materially worse (12 rounds, mean 81.0, GIR 39.3%) and `calibrate.py` says "Smoke test only… Never use for calibration." **The gate needs a decision before it can pass: sampled MC gate, fast-path rework, lower default, or a compiled implementation.** The retune agent was asked to recommend; that recommendation has not landed.
- **The course just changed underneath the calibration.** The sim now carries v3 yardages (verified by me: 18 holes, 7,602 yd, par 72 — matching `docs/course-design-v3.md` exactly). The v3 spec says the scoring band moves 71–73 → plausibly 72–74 and P(59) ~0.5% → ~0.3%, flagged as an estimate the harness must confirm, not a measurement. No harness run exists on the v3 course at all.
- **The sim is currently broken, not just uncalibrated.** My Nov 13 re-runs: 64 tests in 363.4 s, FAILED (1 failure + 12 errors); a verbose re-run (202.1 s, log at `/tmp/sim-suite-2026-11-13.log`) shows all 12 errors are the same `KeyError: 'semi'`, and 10 of them are in `TestEngine` round-playing tests — **no full round can complete right now**. Cause, self-documented in the code: the retune agent added the v3 semi-rough lie to `sim/course.py:462` (`determine_lie` returns `"semi"`), and left a comment at `course.py:454` — "BLOCKER, DO NOT MISS: 'semi' has no entry yet in sim/constants.py LIE_EFFECTS, and physics.py / decisions.py index that table with a hard lookup… until that entry lands, any shot played from a semi-rough lie raises KeyError." `LIE_EFFECTS` (`constants.py:146`) has 9 entries and no `"semi"`; the spec's suggested factors (dist 0.97, spin 0.95, sig 1.15) are marked TO-BE-CONFIRMED and were never added. The 1 failure is `test_lie_determination` (`'rough_heavy' != 'rough_light'`) — a lie boundary shifted when the semi-rough band went in. The fix is one table entry plus a test re-run, but until it lands the engine cannot play golf, and no calibration run is even possible.
- **Variability is undesigned, let alone implemented.** `docs/variability.md` does not exist yet (the audit/design agent was spawned ~00:00 EST Nov 13 and had not delivered at audit time). Mason's Nov 13 directive — the golfer needs real round-to-round variability, "the journey from scratch to breaking 59" — has no design and no code. The current sim's round-to-round distribution has never been measured against real scratch-golfer distributions.

### GL-02 — 7-day soak (§2) — 🔴 RED

- Never run at any stage. Not Soak C (7 days), not Soak B (12 hours), not Soak A (1 hour smoke).
- There is no private/unlisted test stream, no OBS install, no Restream account evidenced anywhere, and no soak log. The runbook's §2 chain (web build → OBS → NodeCG → Restream → private YouTube) has never existed on any machine.
- Every §2.3 row (S-01–S-12: uptime, GPU memory flat, heap, frame rate, rounds completed, bus health, director behaviour, overlay freshness, commentary, audio, watchdog, disk) is therefore unverified. In particular S-02/S-03 (the P0-1 leak tripwires) have never been measured over any duration.

### GL-03 — Web build (§3) — 🔴 RED

- **The 3-round soak (§3.5, K-01–K-05) has never run.** The verification checklist in `docs/performance-audit.md` is unchecked (`[ ]` items): 3 full rounds with DevTools Performance open, GPU memory flat across rounds, no long tasks at hole transitions. No frame-rate measurement exists on any reference laptop or phone (F-01–F-06, M-01–M-06 all unrun).
- **The build under audit is not stable.** The live artifact is on v11 (graphics/putting pass, saved Nov 13 ~04:51 UTC) with a clean-screen rebuild **running** at audit time (agent `12c7b1c1`, the Nov 12 23:54 "declutter + mobile-first + 7,600-yard course" edit). There is no frozen build to certify.
- **The repo export is a full build stale.** Repo `index.html` is dated Nov 12 11:58 UTC, md5 `cbeaf466…` (the v10 redesign export). It contains **zero** of the v11 additions (grep for "championship plate", "scrolling wire", "Season So Far", "Stream Mode" returns 0). The live artifact and the repo do not match, so GL-07's "live build matches repo HEAD" cannot currently be true.
- **The last full audit passed before the last two changes.** The 06:42 UTC audit (Nov 12) passed with zero console errors and rendered captures — but that was pre-de-blend. Later audit runs timed out at the infrastructure level; the redesign's 07:57/08:12 audits passed on the redesign source. **No fresh full audit exists after the de-blend change or after v11.**
- **The builder's own verdict on v11 is adverse.** The v11 completion attested a serious unresolved finding: "Graphics priority not visibly delivered in the 3D scene" — the desktop capture compared against BEFORE shows the same low-poly faceted tree canopies, same flat striped fairway, same simple cloud sprites, no visible increase in scene density or realism. The visible v11 changes were broadcast chrome (wire, season card, championship plate) plus the putting moments (flag-out, putting camera, putting line, cup ripple). Mason then directed the clean-screen rebuild at 23:54 EST Nov 12, explicitly calling the mobile view bad and the screen overloaded — which is consistent with the builder's attestation, not a contradiction of it.

### GL-04 — Graphics & commentary (§4) — 🔴 RED

- **No full-round recording has ever been reviewed.** G-01–G-09 and V-01–V-08 have never been checked end-to-end against a real round. Zero G-08 (no placeholder/NaN) and zero V-03 (no speech over swings) failures cannot be claimed because the check was never run.
- Partial evidence that exists (all VM-only):
  - NodeCG bundle: `node --check` passes; stub smoke test confirmed strike → shotData + lower-third, landing → lastShot, hole_end → scorebug update. **Never run inside a live NodeCG instance or OBS.** Placeholder data is duplicated between `shared/placeholder.js` and `shared/placeholder-data.json`.
  - Commentary service: 34/34 tests pass (re-run by me); demo plays 12 lines with 12 decisions logged. **Never run against a real bus, MLX server, or Kokoro** — all live paths exercised only through stubs. The bus agent's smoke test did connect the commentary service's own `WebSocketBus` client to the real bus server and it received its snapshot — the handshake works; the LLM/TTS paths remain stub-only.
  - The 06:42 UTC audit captures confirmed 59 Watch, conditions, and booth rendering on the pre-de-blend build.
- **The stranger test (T-01) has never been run.** No 60-second clip has been shown to an unbriefed golfer. The builder's own v11 capture comparison ("still reads as a stylized low-poly diorama") is the closest thing to evidence, and it points the wrong way.

### GL-05 — Coins (§5) — 🔴 RED

- **The coins economy does not exist as code.** A repo-wide search for coin-related code returns nothing outside the docs. `docs/coins-economy.md` is a complete, well-specified design (odds, payouts, resets, anti-abuse) with zero implementation behind it: no wallets, no ledger, no odds engine, no market lifecycle, no weekly-reset logic, no rate limiting.
- Every §5 check (O-01–O-05, P-01–P-06, R-01–R-04, A-01–A-08, E-01–E-04) is therefore un-runnable. This is not a "needs testing" item — it is a "needs building" item, and it is the largest unbuilt component in the project.
- Launch implication: either the economy gets built and tested, or coins are explicitly descoped from launch and the stream launches without predictions. That is a scope decision for Mason, not an engineering detail.

### GL-06 — Performance audit P0s fixed — 🔴 RED

- P0-1 (unbounded GPU memory leak — zero `.dispose()` calls in the audited export) and P0-2 (main-thread hitch on hole change) are **claimed fixed** in the v8/repair/redesign builds (shared asset registry, prebuild, tiered shadows, hysteresis quality controller, context recovery).
- **The fix has never been verified by re-running the check that defines it.** `performance-audit.md`'s verification checklist is unchecked: no DevTools run showing `renderer.info.memory.geometries` flat across rounds, no 60 fps confirmation at DPR cap. The 06:42 audit confirmed rendering with zero console errors, which is not the same check.
- The audit also flagged P1 items (2048² PCFSoft shadow map every frame, MSAA, DPR up to 1.75, no visibilitychange pause, per-frame Vector3 churn, particle buffer uploaded every frame when empty) as claimed-fixed; none have a measured before/after.

---

## §6.2 — Launch-day checks

### GL-07 — The build is the latest — 🔴 RED

- The live artifact (v11 + clean-screen rebuild in flight) does not match the repo export (v10-era, Nov 12 11:58 UTC). There is no `.git` directory in the local checkout (pushes go through the GitHub API), so "matches repo HEAD" cannot even be checked locally — it has to be checked against the GitHub main branch, and the last pushed web export predates v11.
- Branding check on the stale export: `grep -c "Road to 62"` returns 0 and "Road to 59" returns 9 — passes on the old file, meaningless for the live build. Must be re-run on the frozen export.
- Blocked in practice until the clean-screen rebuild lands, is audited, and is exported to the repo.

### GL-08 — Stream keys work — 🟡 BLOCKED

- Never tested. No OBS install, no Restream account, no YouTube/Twitch stream keys evidenced anywhere in the repo or this environment. Cannot be attempted until the box is installed (§2 of the runbook) and the accounts exist. A 5-minute private test stream to both platforms is the check; it has never happened.

### GL-09 — AI-use disclosure — 🔴 RED

- No stream exists, so no stream description exists. The requirement (YouTube AI-generated-content disclosure; Twitch equivalent) is documented in `docs/livestream-plan.md` §11 and the runbook, but the disclosure text itself has not been drafted anywhere. Small job, unstarted.

### GL-10 — Watchdog armed — 🟡 BLOCKED

- The watchdog code is complete and passed a full dry run on this Linux VM (all 9 checks ran, exit 0, heartbeat touched, alert suppression and quiet-hours hold verified; the dry run found and fixed two real bugs). But `ops/install.sh` has never run, the launchd agents have never been loaded, and the macOS-only paths (`open -a OBS`, `osascript`, `launchctl`, `networkQuality`, `sysctl vm.swapusage`) are guarded with `command -v` but **unexercised**. The README's per-check failure tests have never been run on the real box.
- Note a doc drift: `ops/README.md` still describes the bus as "Node.js `ws` on localhost:4456" and says check 3 is port-only "until it [the bus] ships." The Python stdlib bus **has** shipped and **does** write `ops/state/last_event` on every event (verified by its own tests), so the contract is now satisfied — but the README is stale and should be corrected before the install, or the installer will be reading the wrong contract.
- Also note: check 2 is an HTTP + title proxy, not a true frame-advance check; the README flags that a perf-HUD endpoint is needed for the real thing. That endpoint does not exist.

### GL-11 — Clip pipeline armed — 🟡 BLOCKED

- The pipeline code is the most completely verified component in the repo: 58/58 tests pass (re-run by me), and real ffmpeg 8.1.2 verification produced 2/2 clips at 1080×1920, 30 fps, h264 + AAC, exactly 35.000 s each, with sidecars and report. Two real bugs were caught by the real run and fixed.
- Arming is still blocked: OBS replay buffer has never been configured, `~/mas-golfs/clips/` has never existed, and the pipeline has never run on the box against real replay files. Known limitations carried forward: center crop can cut a tracer at the frame edge; no ambient bed mixed in yet.
- The one test clip GL-11 requires has never been produced.

### GL-12 — Coins seeded — 🔴 RED

- Follows from GL-05: there is no economy to seed, no bonus pool, no weekly board, no test prediction. Red, not blocked, because the blocker is a missing build, not a missing prerequisite.

### GL-13 — Mason's phone check — 🟡 BLOCKED

- Never done. Requires a live stream to watch. This is the only human check in the list and it has no substitute — it cannot be done on a recording or a local page with the same meaning.

### GL-14 — The stranger test (§4.3) — 🟡 BLOCKED

- Never done. Requires the frozen live build. Given the builder's own v11 attestation and Mason's Nov 12 assessment of the visuals, the honest expectation is that it would fail today — which is why the clean-screen rebuild exists. Re-run it on the frozen build, not before.

---

## §6.3 — Day-1 monitoring

### GL-15 — Someone watches the first hour — 🟡 BLOCKED
### GL-16 — First clip out within 24 hours — 🟡 BLOCKED
### GL-17 — Metrics baseline (tracking sheet first row) — 🟡 BLOCKED
### GL-18 — Incident log reviewed before day 2 — 🟡 BLOCKED

All four depend on a live stream that has never existed. Supporting artefacts are also absent: the weekly tracking sheet (`docs/launch-playbook.md` §4.5) does not exist as a file, and the incident log (`qa/incidents.md`) does not exist — there is no `qa/` directory at all. GL-16 is the only one with its machinery verified (the clip pipeline); GL-17's metrics (uptime, clips, views, returning viewers, predictions, scoring average) have no collection point yet — the analytics dashboard in `docs/analytics.md` §4 is a spec, and no status-dashboard file exists in the repo.

---

## Runbook checklist status (condensed)

| Runbook item | Verdict | Evidence / blocker |
|---|---|---|
| §1 Machine setup (pmset, auto-login, `masgolfs` user, FileVault off, lid open, thermal) | 🟡 Blocked | Never done; requires hands on the real 8GB MBP. Apple Silicon confirmed Nov 12 (unblocks MLX). Air off-limits, 128GB MBP untouched — both correctly reflected everywhere. |
| §2 Install order, step 1 (web build serves) | 🟡 Blocked | Serves and renders in audit captures on this VM; never served on the box. |
| §2 Steps 2–5 (OBS, NodeCG, Kokoro, Restream) | 🔴 Red | None installed anywhere. NodeCG bundle exists but never ran in NodeCG; Kokoro never pulled; no Restream account evidenced. |
| §2 Step 6 (go-live checklist) | 🔴 Red | This report. |
| §3 Multistream (OBS 1080p60, VideoToolbox, 8,000 Kbps, Ethernet) | 🔴 Red | Settings documented, never configured or tested; no bandwidth test from the box; no Ethernet confirmation. |
| §3.2 8GB memory discipline | 🟡 Blocked | Documented; unenforced until the box runs. Balanced tier default is a doc statement, not a measured state. |
| §3.4 TikTok | — | Correctly deferred. Phase 1 is YouTube + Twitch; TikTok needs 1,000 followers first. Not a launch blocker. |
| §3.5 Recording / clip pipeline | 🟡 Blocked | Pipeline code verified (see GL-11); OBS recording never configured; disk math (~96 GB/day) untested against the real disk. |
| §4.1–4.2 Watchdog + launchd | 🟡 Blocked | Code complete; VM dry run passed; install + failure tests pending on box. |
| §4.3 Restart order | 🟡 Blocked | Documented; never exercised. `start_stack.sh` exists; never run. |
| §4.4 No scheduled restart | 🟢 Green (by design) | The rule is written in the runbook, the watchdog, and the web build (fault-only intermission). Nothing to test until the stack runs. |
| §4.5 Pee-break intermission | 🟡 Blocked | Implemented in the web build (fault-only + manual control, resumes on the exact frozen frame) and confirmed in audit captures; never exercised end-to-end on the box. |
| §5.1 Status dashboard | 🔴 Red | No status-dashboard file exists in the repo. Watching the stream itself works as the primary check; the six-number dashboard is unbuilt. |
| §5.2 Remote access (Screen Sharing, Tailscale, key-only SSH) | 🔴 Red | Not set up. No Tailscale on either Mac evidenced; the Air is correctly excluded from Tailscale everywhere. |
| §5.3 Alerting (5 alerts, one per incident, quiet hours) | 🟡 Blocked | Rules documented; watchdog implements suppression + quiet hours (VM-verified); no alert has ever fired on real hardware. |
| §6.1 Daily checklist | 🟡 Blocked | Nothing to operate yet. |
| §6.2 Weekly review ritual | 🔴 Red | No review file exists. `docs/reviews/` was created by this audit; this report is its first file. The Sunday ritual has never run. |
| §6.3 Monthly (cold-boot drill, disk/thermal, Restream/TikTok review) | 🔴 Red | Never run. The cold-boot drill (unattended recovery < 10 min) is the only proof the no-spare failover works, and it has never been attempted. |
| §6.4 Ops log | 🔴 Red | `ops/ops-log.md` does not exist in the repo; no incident has ever been logged. |
| §7 Unreal upgrade path | — | Correctly deferred. Slice not built, no spend committed, trigger points documented. Not a go-live blocker for the web build. |
| §8 Failure modes (8.1–8.12) | 🔴 Red | All twelve recovery paths are untested on real hardware. No fault has ever been injected on the box. |

---

## Component-by-component evidence

| Component | What I verified myself | What is only ever VM-verified | What has never been verified anywhere |
|---|---|---|---|
| **sim/** | Unit suite: 62/62 on Nov 12 (parent-verified, 171.8 s); **Nov 13 re-run: 64 tests in 363.4 s, FAILED (1 failure + 12 errors), exit 1** — the retune agent was mid-edit during the run. Course data now matches v3 exactly (18 holes, 7,602 yd, par 72). | 6-round MC calibration samples; physics corrections documented with evidence. | 10,000-round harness (never run); calibration PASS (harness reports FAILED); determinism at scale; decision-time budget on real hardware; learning-loop checks L-01–L-06; handicap math vs hand-checked sheet. |
| **bus/** | 18/18 tests, re-run by me. | Live smoke test: full round, 169 events, subscriber received 46 decisions + 46 strike/apex/landing triples + 18 hole_ends + 1 round_end; last-event file 2 s old; commentary client handshake works. | NodeCG's `ws` client against the real server (no Node test env in the task). |
| **commentary/** | 34/34 tests, re-run by me. | Demo: 12 lines, 12 decisions, silence fraction 0.06; three real bugs found and fixed by tests. | Every live path: real bus + MLX + Kokoro. MLX→Ollama failover untested. Full-round V-01–V-08 unrun. |
| **nodecg-bundle/** | File inventory checked; `node --check` per builder. | Stub smoke test (placeholder data, demo loop). | Live NodeCG instance; OBS browser sources; overlay freshness (S-08); any G-01–G-09 check. |
| **clip-pipeline/** | 58/58 tests, re-run by me. | Real ffmpeg 8.1.2: 2/2 clips, 1080×1920, 30 fps, exactly 35.000 s; two real bugs fixed. | Running on the box against real replay files; the daily queue in production. |
| **ops/** | Read all scripts + READMEs; confirmed the bus last-event contract is now satisfied. | Full dry run on this Linux VM: all 9 checks, exit 0, alert suppression + quiet hours verified; two real bugs fixed. | Everything macOS-only (`launchctl`, `networkQuality`, `sysctl vm.swapusage`, `open -a OBS`, `osascript`); install.sh on the real box; per-check failure tests. |
| **mlx-verify/** | 51/51 tests, re-run by me. | Fails cleanly on Linux (exit 2, "MLX runs on macOS only"); stub end-to-end CLI exercise. | Everything that matters: model load, latency P99 < 4 s, 30-min soak with swap 0, `<think>` grep on real output, blind A/B judgement. Pack runs ~45–60 min on the box; never started. |
| **web build (artifact)** | Repo export inspected (v10-era, Nov 12 11:58 UTC, md5 `cbeaf466…`); artifact status checked (v11 live, clean-screen rebuild running). | Audit captures 06:42 / 07:57 / 08:12 UTC Nov 12: renders, zero console errors, zero mobile overflow (redesign). 59 Watch, conditions, booth confirmed rendering. | Fresh full audit after de-blend and after v11; 3-round DevTools soak; frame rates on reference laptop/phone; context-loss recovery; the stranger test. |
| **docs** | Read qa-plan §6, runbook, all component READMEs. | Research docs sourced and pushed (Golf Clash, best golf games, PGA Tour broadcast, game AI). | — |

### Two structural findings the component table hides

1. **Putting has no green.** `docs/putting-model-v2.md` (written Nov 13 05:08 UTC, design only, no sim code changed) documents that putting v1 is a make-probability + distance-control model with **no green geometry at all**: the break is drawn from a triangular distribution, the ball rolls in a straight line toward the pin, and `sim/course.py` `Hole` has a green radius and an elevation but no slope, contour, or pin position. The broadcast renders a green from its own art, not from sim data. The doc names the risk plainly: it is the same structural flaw that made EA Sports PGA Tour's putting beads wrong — overlay and physics computed from different samplings of the green. Any green-read overlay the broadcast draws today would be decoration. Putting v2 (one heightfield per green as the single source of truth) is designed, not built. This does not block a launch by itself — the make-rate table is the calibrated contract and it is what the harness gates — but the "incredible putting" Mason asked for on Nov 12 cannot be honestly shown until v2 lands.
2. **The course is drifting across three places.** The v3 spec (7,602 yd) is written and pushed; the sim yardages match v3 exactly (verified); the artifact is being rebuilt to "~7,600 yards" but its hole data is the builder's own, not the sim's; and the v3 green-slope / semi-rough lie model is specified in the doc but **not yet in the sim** (`semi_rough_yd` field and `semi` lie are spec-only). The two different v1 rating/slope pairs in the record (74.1/141 in the web build vs 74.6/138 in `conditions-system.md`) are still unresolved — the v3 recompute must produce one number used everywhere. Freeze one course version across sim, artifact, and docs before calibration, or the harness will certify a course nobody is broadcasting.

---

## Top 5 risks (priority order)

### 1. The sim is uncalibrated, mid-surgery, and currently broken — unblocks everything downstream
**Risk:** the engine that generates every number on screen (scores, odds, 59 Watch probabilities, commentary facts) has never passed its own calibration harness, it is being edited right now, and **as of this audit it cannot play a round at all**: 12 of 64 unit tests error with `KeyError: 'semi'` because the v3 semi-rough lie was added to the course without its entry in the lie-effects table (the retune agent left a "BLOCKER, DO NOT MISS" comment in `sim/course.py:454` saying exactly this). The last calibration sample fails on fairways, GIR, and scrambling; the 10,000-round gate as written is infeasible in Python; the course just lengthened by 388 yards, which moves the scoring band.
**What unblocks it:** add the `semi` entry to `LIE_EFFECTS` (spec's suggested factors dist 0.97 / spin 0.95 / sig 1.15, to be confirmed) and re-run the suite green → finish the flight-model retune → take the retune agent's recommendation on what the 10,000-round gate becomes (sampled MC / fast-path rework / lower count) and write it into `qa-plan.md` → run the harness on the v3 course → publish `qa/reports/calibration-<date>.json` with all rows PASS. Until that file exists, commentary numbers, coins odds, and 59 Watch probabilities are ungrounded — and until the `semi` entry lands, no round can even be played.

### 2. Nothing has ever run on the real box — the whole broadcast is unproven hardware
**Risk:** the 8GB MacBook Pro is the entire broadcast and it has run zero minutes of any component. Every VM pass in this report could hide a box-only failure: swap pressure under the real OBS + browser + NodeCG + Kokoro load, VideoToolbox encoder behaviour, Docker memory limits, launchd ordering. There is no spare machine, so the first on-box failure happens in front of viewers unless it is found in a rehearsal.
**What unblocks it:** a physical install weekend on the 8GB MBP: `mlx-verify` pack (~45–60 min), `ops/install.sh` + the README's per-check failure tests, commentary README §10 build order (MLX install, Kokoro, Ollama failover drill, 24-hour soak), NodeCG live-mode test, OBS + Restream private test stream. Mason's hands are needed for the box itself; none of this can be done from this VM.

### 3. The web build is mid-rebuild, unaudited, and stale in the repo
**Risk:** the only thing viewers ever see is being rebuilt right now (clean-screen + mobile-first + 7,600-yard course), its last full audit predates the last two changes, the P0 leak fix has never been DevTools-verified, and the repo export is a full build behind the live artifact. Shipping the current artifact would mean launching a build nobody has seen whole.
**What unblocks it:** let the rebuild land → fresh full audit (desktop + phone captures, console errors, mobile overflow) → 3-round DevTools soak (K-01–K-05, flat GPU memory, no context loss) → export the frozen build to the repo → run the stranger test on the frozen build. Do not launch off a moving build.

### 4. No soak, no stream, no failover has ever been exercised — the schedule risk
**Risk:** the 7-day soak gate is 7 days of calendar time that cannot be compressed, and it has not started. Neither has the 1-hour smoke or the 12-hour overnight. No private test stream, no Restream account, no cold-boot recovery drill, no staged cloud fallback. The monthly drill is the only proof the no-spare failover works, and it has never been attempted — if the 8GB MBP dies on day 2, recovery is "hours if unprepared" by the runbook's own estimate.
**What unblocks it:** install → Soak A (1 hr) → Soak B (12 hr overnight) → Soak C (7 days) with the §2.3 rows logged; stage the RunPod template and run the cold-boot drill (unattended recovery < 10 min) before go-live, not after. Earliest honest launch is install weekend + 7 days + calibration time — not this week.

### 5. The coins economy does not exist — a scope decision, not just work
**Risk:** the largest unbuilt component in the project. Every §5 check is un-runnable, GL-05 and GL-12 are red with no code to test, and the launch-playbook's community loop (predictions → clips → returning viewers) assumes predictions exist. Building it is real work (wallets, append-only ledger, odds from rolling stats, weekly reset atomicity, anti-abuse) that has not started.
**What unblocks it:** Mason decides: (a) build the economy service and run §5 end-to-end before launch, or (b) explicitly descope coins from launch and go live without predictions, adding them later. Do not launch with a half-built economy — a ledger that does not reconcile is worse than no predictions at all.

---

## What would have to be true to go live (sequenced)

1. **Retune lands; calibration gate decided and passed** — `qa/reports/calibration-<date>.json`, all rows PASS, on the v3 course, within 7 days of launch (GL-01).
2. **Web build frozen and audited** — clean-screen rebuild lands, fresh audit passes, 3-round DevTools soak passes, frozen export pushed to the repo, stranger test passes (GL-03, GL-04, GL-07, GL-14).
3. **On-box install weekend** — MLX verify pack, ops install + failure tests, commentary build order, NodeCG live test, OBS + Restream private test stream to YouTube and Twitch (GL-08, GL-10, GL-11; runbook §1–§5).
4. **Coins decision** — built and §5-tested, or explicitly descoped (GL-05, GL-12).
5. **Soaks** — A (1 hr) → B (12 hr) → C (7 days), all §2.3 rows PASS, ≤1 watchdog restart, zero manual interventions (GL-02).
6. **Launch-day checks** — AI disclosure drafted and in the stream descriptions, watchdog armed, clip pipeline armed with one test clip, Mason's 2-minute phone check (GL-09–GL-13).
7. **Day-1 monitoring** — first-hour watch, first clip within 24 hours, tracking-sheet baseline, incident log (GL-15–GL-18).

## Honest schedule shape

Calibration work (days, not hours — the gate decision alone is unresolved) + install weekend + 7-day soak = **launch is not this week**. The critical path is the soak's 7 calendar days, and it cannot start until the box is installed and the build is frozen. Any date given before the calibration report exists is a guess.

---

## Addendum — sim suite re-run (to be filled when it lands)

- Nov 12, 2026 (parent-verified): `python3 -m unittest discover -s sim/tests` — **62 tests, ALL PASS, 171.8 s**.
- Nov 13, ~05:10 UTC (this audit): re-run with `timeout 280` — **did not complete within 280 s** (progress dots only, no summary). The suite is slower than Nov 12; the retune agent was editing `sim/tests/test_sim.py` and `sim/course.py` during the run.
- Nov 13, ~05:35 UTC (this audit): second re-run with `timeout 600` — **completed in 363.4 s: Ran 64 tests, FAILED (failures=1, errors=12), exit 1.** Against 62/62 passing in 171.8 s on Nov 12. The test count grew 62 → 64 and the runtime more than doubled.
- Nov 13, ~05:50 UTC (this audit): verbose re-run, 202.1 s, log at `/tmp/sim-suite-2026-11-13.log` — **same result, FAILED (failures=1, errors=12)**. All 12 errors are `KeyError: 'semi'` (10 in `TestEngine` round-playing tests, 1 in `TestConditions`, 1 in `TestRatingSlope`); the 1 failure is `test_lie_determination` (`AssertionError: 'rough_heavy' != 'rough_light'`). Root cause, self-documented at `sim/course.py:454`: the v3 semi-rough lie is returned by `determine_lie` but has no entry in `LIE_EFFECTS` (`sim/constants.py:146`), and `decisions.py` indexes that table with a hard lookup. The spec's suggested factors (dist 0.97, spin 0.95, sig 1.15) are TO-BE-CONFIRMED and were never added. **No full round can complete on the current tree.** Re-run the suite on the settled tree after the `semi` entry lands; do not treat this snapshot as the diagnosis of anything but the missing entry.
