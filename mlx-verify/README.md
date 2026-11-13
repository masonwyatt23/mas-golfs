# Mas Golfs — on-box MLX verification pack

Proves the local-model stack from `docs/local-models.md` actually works
on the real broadcast box **before the stream depends on it**. Run it on
the 8GB MacBook Pro (Apple Silicon — confirmed by Mason, Nov 12 2026).

## The decision this pack verifies

- **Runtime: plain mlx-lm** (Apple's reference implementation, OpenAI-
  compatible server built in). Decided by Mason, Nov 12 2026 — not oMLX:
  one 4B model, one short line per event, so batching/KV caching buys
  almost nothing and oMLX's overhead cuts against an 8GB box. oMLX stays
  an option only if multi-model serving is ever needed.
- **Default model:** `mlx-community/Qwen3.5-4B-4bit` · **Fallback:**
  `mlx-community/Qwen3-4B-Instruct-2507-4bit` · **Emergency:**
  Qwen3-1.7B. Temperature 0.7, max tokens 120, non-thinking.
- **8B does not fit** alongside the broadcast stack (~10.3–10.8 GB on
  an 8GB box); **27B is GPU-box-only**. Those are settled research
  conclusions (`docs/research/qwen3-family.md`, `qwen-27b-fit.md`) —
  this pack does not re-litigate them.

## How to run it on the box

```bash
cd ~/workspace/mas-golfs-repo/mlx-verify   # or wherever the repo lives
./verify.sh all
```

First run takes a while: it creates a venv at `~/.masgolfs/mlx-venv`,
installs `mlx-lm` (free, `pip install mlx-lm`), downloads the 4B model
(~2.5 GB), and starts the server. The full pack is roughly **45–60
minutes** — 30 of that is the soak, ~5 the A/B (two model loads plus
100 generations), the rest seconds. Nothing here costs money and no
paid API is ever called.

Run one check at a time:

```bash
./verify.sh check      # install + model loads + server answers + smoke line
./verify.sh latency    # 20 real prompts, P99 < 4 s
./verify.sh audition   # 20 lines within the §10 step-4 rules
./verify.sh soak       # 30 minutes, median swap growth after load < 1 GB, max < 4.8 GB
./verify.sh think      # zero-tolerance <think> grep over >= 100 lines
./verify.sh ab         # blind A/B, 50 events, two models
SOAK_MINUTES=5 ./verify.sh soak   # short soak smoke run
MLX_VERIFY_KEEP_SERVER=1 ./verify.sh check   # leave the server running
```

Exit codes: **0** all requested checks passed; **1** a check failed;
**2** wrong hardware (not Apple Silicon macOS) or an unfixable
prerequisite; **3** incomplete (e.g. the think check ran before 100
lines were generated).

## What each check proves

| Check | What it proves | Pass bar | Source |
|---|---|---|---|
| `check` | mlx-lm installs, Qwen3.5-4B loads, the server answers on localhost:8080, one real prompt returns a completion | Server up + smoke line | local-models §10 steps 2–3 |
| `latency` | 20 real commentary prompts (decision/landing/59 Watch/putt/hole-end) through the server, streaming, TTFT + total timed | **P99 total < 4 s** (median + P99 TTFT also reported) | qwen3-family §10 item 2 |
| `audition` | 20 generated lines meet the broadcast rules | Every line ≤ 280 chars, no banned words, no number the event prompt never mentions, no `<think>` | local-models §10 step 4; commentary-prompts §5 |
| `soak` | The model resident for 30 min alongside the stack does not leak swap | **Median swap growth after the model loads stays under 1 GB, and max swap stays under 4.8 GB** for the whole run; server stays alive; warm-up generations keep succeeding | qwen3-family §10 item 1 |
| `think` | No reasoning trace ever reaches the booth | **Zero `<think>`/`</think>` hits across ≥ 100 generated lines** (latency 20 + audition 20 + A/B 100 = 140 lines when the full pack runs) | qwen3-family §10 item 4 |
| `ab` | Which 4B candidate writes better lines, judged blind | Human scores `results/ab-side-by-side.md` on the booth test (commentary-prompts §11); the key stays sealed in `ab-key.json` until scoring is done | qwen3-family §10 item 3 |

Notes on the bars:

- **P99 > 5 s is the operational alert line** (local-models §8): a
  slow generation is a box problem (swap, thermal throttle, runaway
  process), not a model problem. The 4 s bar above is the ship gate;
  5 s is the "something is wrong with the box" line.
- **Soak coverage is reported, not assumed.** The 30-minute soak is
  only fully valid with the real stack running (OBS, browser, NodeCG,
  Kokoro). `verify.sh` prints a `SOAK-COVERAGE: FULL / PARTIAL` line
  listing what was present. A partial-coverage PASS still proves the
  model itself does not swap; repeat with the full stack for the §10
  gate.
- **The 30-minute soak is not the 24-hour soak.** local-models §10
  step 8 requires a separate 24-hour full-round soak (stream live,
  commentary on, all processes running). The 4B decision (§4.4) is
  made from that measurement: peak memory (worst minute) under 6.5 GB
  **and** median swap growth after load under 1 GB (max swap under 4.8 GB)
  for the whole 24 hours, or the 4B stays off the
  box. This pack's soak is the gate that says the 24-hour run is worth
  starting.

## Files in this pack

| File | What it is |
|---|---|
| `verify.sh` | Orchestrator: platform gate, venv + install, server lifecycle, all six checks, exit codes |
| `mlx_verify.py` | The testable logic (stdlib only): prompt loading, OpenAI-compatible HTTP client with streaming TTFT, timing stats, `<think>`/banned-word/invented-number validation, blind A/B writer, soak sampler + verdict |
| `events.json` | 50 real event-shaped prompts (all 17 template/speaker pairs from `commentary/prompts.py`), with the source event fields attached |
| `gen_events.py` | Deterministic generator for `events.json` — re-render the file from `commentary/prompts.py` any time the templates change |
| `tests/test_mlx_verify.py` | 51 unit tests (see below) |
| `results/` | Created on first run: `latency.json`, `audition.json`, `soak.jsonl`, `soak-summary.json`, `ab-results.json`, `ab-side-by-side.md`, `ab-key.json`, `server.log` |

The prompts are the production prompts: `gen_events.py` renders them
through `commentary/prompts.py`, the same templates the commentary
service uses, filled with realistic event values from Wyatt National.
**v3 note:** the checked-in `events.json` was rendered from the v2 hole
yardages (e.g. hole 12 at 164 yards, hole 3 at 187 — v3 is 172 and 196).
Re-run `gen_events.py` from `docs/course-design-v3.md` before the on-box
verification run, so the latency and A/B prompts carry v3 yardages. The
latency and A/B runs measure the prompts the broadcast actually sends,
not toy text. The A/B labels are randomized by one coin flip for the
whole file (not per event), so the judge compares two consistent
voices.

## What was tested here, and what can only run on the real box

Tested on this Linux VM (Nov 12 2026) — **51 unit tests, all passing**
(`python3 -m unittest discover -s tests`):

- Platform gate: fails cleanly on Linux x86_64 (exit 2, "MLX runs on
  macOS only") and on Intel Mac; passes on Darwin/arm64 values.
- Prompt loading and validation (missing keys, duplicate ids, bad
  speaker, empty prompt all rejected); all 50 events load, all 17
  template/speaker pairs covered.
- Timing math (percentiles, median/P99/max), `<think>` detection
  (including `</think>`, `<Think>`, `&lt;think&gt;`; the word
  "thinking" is correctly not a leak), banned words, invented numbers
  (digit and word forms both count as present — "twelve feet" matches
  "12 feet", "fifty-nine" matches "59").
- The HTTP client against a stub OpenAI-compatible server, streaming
  (TTFT measured from the first SSE delta) and non-streaming, healthy/
  unhealthy probes, and failure on a dead server.
- Latency, audition, and blind A/B runs against the stub (50 events,
  sealed key, side-by-side file verified to contain no model names).
- Soak parsing (`vm.swapusage` in K/M/G), verdicts (median growth over 1 GB fails,
  max swap over 4.8 GB fails, dead server fails, failed warm-up fails), and a short live soak run
  against the stub.
- `verify.sh check` on Linux exits 2 with the clear macOS message;
  `verify.sh think` with no results exits 3 (incomplete).
- End-to-end CLI exercise against the stub: latency PASS (P99 0.063 s
  on the stub — stub speed, not a model claim), audition 20/20,
  A/B 50 events, think PASS over 140 lines.

**Not testable here, by construction:** everything that needs the
model or the Mac. `mlx-lm` does not install on Linux x86_64, `sysctl
vm.swapusage` does not exist here, and there is no OBS/browser/NodeCG
stack to soak against. The pack fails cleanly on the wrong hardware
instead of pretending: `./verify.sh` exits 2 before installing or
starting anything. Real latency, real swap behaviour, real line
quality, and the blind A/B judgement can only happen on the 8GB
MacBook Pro — that is what this pack is for.

## If a check fails on the box

- **Latency P99 ≥ 4 s:** check swap first (`vm.swapusage`), then
  Activity Monitor for a runaway process, then thermal state. A slow
  generation is a box problem until proven otherwise. The commentary
  service degrades gracefully (cached standard line), so the stream
  does not die — but do not ship on a failing latency check.
- **Soak median swap growth > 1 GB (or max swap > 4.8 GB):** the 4B does not fit alongside whatever else is
  running. Find the memory hog (usually the browser or a Docker VM),
  re-run, and if it still swaps, the fallback model
  (Qwen3-4B-Instruct-2507, then Qwen3-1.7B) is the call — see
  local-models §4.4. Do not raise the swap tolerance.
- **`<think>` leak:** switch to the fallback model
  (Qwen3-4B-Instruct-2507 is non-thinking by construction) and
  re-run the think check over a fresh 100 lines.
- **A/B is a tie or the fallback wins:** ship the winner. The
  Qwen3.5-4B default is a research conclusion, not a loyalty oath —
  the booth test decides.
- **Server flags moved:** mlx-lm's server flags change between
  releases. **Resolved 2026-11-13 on the box (mlx-lm 0.32.2):**
  `--max-kv-size` does not exist in the 0.32.x server (it is a
  `generate`-only flag), and `-m mlx_lm.server` is deprecated in
  favour of `python -m mlx_lm server`. `verify.sh` now starts the
  server with `--prompt-cache-size 1 --max-tokens 120` — one cached
  prompt prefix instead of ten, plus the 120-token generation cap
  from commentary/config.yaml. The 2K context cap itself is
  non-negotiable — it is the memory budget — and it is enforced by
  the request shape (stateless ~200-token prompts, ≤120 generated)
  plus those two flags; see local-models §3.2 for the working
  command.
