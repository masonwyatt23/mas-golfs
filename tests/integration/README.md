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

## Known failure (FIXED Nov 13, 2026): the commentary service crashed on the first made putt

Found by this harness (`test_03` FAILed, `test_06` failed with it).
Fixed in `commentary/service.py` + `commentary/cache.py`; regression
tests in `commentary/tests/test_commentary.py`. The harness now passes
all six links (verified Nov 13, 2026 — full run all green).

* Trigger: the first made putt of a round, before any `hole_end` event.
* Crash: `ValueError: invalid literal for int() with base 10: '—'`,
  raised in `commentary/cache.py::standard_line` (`int(score)`) when it
  renders `"The putt drops. Mas is … through {thru}."`.
* Root cause, two halves:
  1. `commentary/service.py::_template_fields` formats `score_to_par`
     into a display string (`'—'`, `'E'`, `'−1'`, …) before the fields
     reach `standard_line`, which expects a number-or-`None` score.
  2. `commentary/service.py::_update_round_state` stored the raw
     `round_state` snapshot *envelope* as `self.round_state` instead of
     the nested `round_state` dict, so `state.get("score_to_par")` is
     `None` until the first `hole_end` sets it — and `format_score(None)`
     is `'—'`.
* Effect: the service thread dies on hole 1's made putt and processes
  nothing further for the round. A missed putt on hole 1 does not
  trigger it (the miss branch never touches the score), which is why
  the service's own 34 unit tests and its demo never caught it.
* Fix: `_update_round_state` unwraps the snapshot
  (`self.round_state = dict(event.get("round_state") or {})` when the
  nested dict is present; the flat form the demo sends is kept as-is),
  and `standard_line` coerces the score with `_score_as_int` — a
  non-numeric score is unknown (falls back to `"The putt drops."`),
  never `int()`ed. Display forms that carry a value still read right
  (`'E'` → even par, `'−1'` → one under par).
* Regression tests: `test_made_putt_on_hole_1_before_any_hole_end`
  (feeds the real bus snapshot envelope, then a made putt on hole 1,
  then the rest of the round — the line plays and the service keeps
  running) and `test_standard_line_tolerates_display_string_score`.
  Commentary suite is 36/36 with them.
* Note for the reader: the same fix exposed a second, masked failure —
  see "Teardown race" below. And `thru` counts completed holes, so the
  hole-1 made-putt line reads "even par through 0" until the first
  `hole_end` — pre-existing semantics, not part of this fix.

## Teardown race (FIXED Nov 13, 2026)

Once the service survived the fixture, `test_03`/`test_06` failed
with a different error instead: `BusError: bus closed the connection`
(or `OSError: [Errno 9] Bad file descriptor`). That was the harness's
own shutdown, not a crash: `CommentaryRunner.stop()` closes the bus
socket while the service thread is blocked in `recv_text`, and the
service correctly logs `__service_stop__` and exits — but the runner
recorded any thread exception as `runner.error`. The runner now sets
a `_stopping` flag before closing the bus, and only records exceptions
raised before shutdown began. A real mid-run crash (e.g. the putt
`ValueError`) still fails the test, because it is raised before
`stop()` is called.

## Flaky: test_04 (NodeCG link) sometimes stalls mid-burst

`test_04` passes roughly half the time (observed: 2/3 full-harness
runs, 1/3 isolated runs, 3/4 instrumented runs, 5/5 once — the rate
moves with VM load). Failure mode: `roundState.hole` stuck at 1 or 2
— the extension stops receiving envelopes partway through the 21-event
burst. Evidence gathered Nov 13, 2026: a logging `ws` shim captured a
failing run receiving 22 of 32 envelopes (stall after `landing`
seq 23, the last 10 never arrived); the bus server log shows no error,
no warning, no traceback; a bare Node probe with the same shim
receives all 32 every time; the stall point varies run to run. Not
root-caused yet, and independent of the commentary fix (it reproduces
with no commentary code running). Suspects, unproven: the server's
`broadcast` blocking in `sendall`, or the Node event loop starving
under VM load. Do not "fix" it by weakening the hole assertion.

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
