# Mas Golfs — end-to-end integration harness

Proves the whole chain works on this VM, one test per link plus one
full-chain test:

| Test | Link | What it proves |
|---|---|---|
| `test_01_sim_link` | sim | A real fast-mode round emits a complete event stream |
| `test_02_bus_link` | bus | Snapshot-on-connect, `shot_result` → strike/apex/landing fan-out, every sim `seq` arrives, watchdog last-event file written |
| `test_03_commentary_link` | commentary | The real service (stub LLM/TTS) receives the stream and logs decisions, at least one line played |
| `test_04_nodecg_link` | NodeCG | The real extension updates roundState/shotData/lastShot/lowerThird from the stream |
| `test_05_clip_link` | clips | The scorer finds birdie/eagle/near-miss, the manifest queue is built, ffmpeg assembly skips cleanly with no recordings |
| `test_06_full_chain` | all | One 3-hole publish feeds bus, commentary, NodeCG and clips together |

## Run

From the repo root:

```bash
python3 tests/integration/run.py
# or
python3 -m unittest tests.integration.test_chain -v
```

Expect ~2–4 minutes (fast sim rounds dominate). Python stdlib only, plus
Node 24's built-in WebSocket client via the `ws` shim in
`node_modules/ws` (the extension requires the `ws` package, which is not
installed here and must not be npm-installed by the harness).

## Fixture

The chain tests publish a deterministic 3-hole demo round: `round_start`
plus holes 1–3 of the sample round R0042 (H1 birdie, H2 eagle, H3
near-miss lip-out). Using a fixed fixture keeps the bus / commentary /
NodeCG / clip links testable even while the sim is broken. The sim-link
test is the only one that plays a real round.

## Known failure: the commentary service crashes on the first made putt

Found by this harness (Nov 13, 2026 — `test_03` FAILs, `test_06` fails
with it). This is a **production bug, not a harness bug**; the harness
must not be "fixed" to hide it.

* Trigger: the first made putt of a round, before any `hole_end` event.
* Crash: `ValueError: invalid literal for int() with base 10: '—'`,
  raised in `commentary/cache.py::standard_line` (`int(score)`) when it
  renders `"The putt drops. Mas is … through {thru}."`.
* Root cause, two halves:
  1. `commentary/service.py::_template_fields` formats `score_to_par`
     into a display string (`'—'`, `'E'`, `'−1'`, …) before the fields
     reach `standard_line`, which expects a number-or-`None` score.
  2. `commentary/service.py::_update_round_state` stores the raw
     `round_state` snapshot *envelope* as `self.round_state` instead of
     the nested `round_state` dict, so `state.get("score_to_par")` is
     `None` until the first `hole_end` sets it — and `format_score(None)`
     is `'—'`.
* Effect: the service thread dies on hole 1's made putt and processes
  nothing further for the round. A missed putt on hole 1 does not
  trigger it (the miss branch never touches the score), which is why
  the service's own 34 unit tests and its demo never caught it.
* Suggested fix (for the commentary owner, not this harness):
  unwrap the snapshot in `_update_round_state`
  (`self.round_state = dict(event.get("round_state") or {})`), and/or
  make `standard_line` treat a non-numeric score as unknown instead of
  calling `int()` on it.
* Re-run after the fix: `python3 tests/integration/run.py` — the
  commentary link and the full chain should both go green.

## The sim link, honestly

At the time of writing the sim was flaky: the v3 semi-rough lie was added
to `sim/course.py` without an entry in `sim/constants.py::LIE_EFFECTS`,
so any round whose shots land in semi-rough died with
`KeyError: 'semi'` (readiness audit, Nov 13: 12 errors, no round could
complete). The fix landed **during this harness run** — the v3 agent
added the `semi` entry (`dist 0.97, spin 0.95, sig 1.15`) and the
sim-link test now passes on all three seeds (scores 87/89/81, fast
mode). The test still tries seeds 1–3 and reports per-seed outcomes, so
any regression shows up as a skip (all seeds failing) or a printed
warning (some seeds failing) rather than a silent pass.

The sim-link test is the gate: until it passes, no calibration run is
possible either, because calibration needs rounds the sim can finish.

## What this harness does NOT prove

* The Monte Carlo decision path (fast mode only — a full MC round is too
  slow for a test suite; `sim/calibrate.py` owns that gate).
* Anything on the real 8GB MacBook Pro (MLX server, Kokoro, OBS,
  Restream, NodeCG inside a live NodeCG instance). The NodeCG link runs
  the real extension code against a stubbed `nodecg` object, not inside
  NodeCG itself.
* ffmpeg assembly of a real clip (no OBS recordings exist on this VM;
  the harness proves the missing-input path skips cleanly instead).
* The coins economy (doc-only — no code exists to integrate yet).
