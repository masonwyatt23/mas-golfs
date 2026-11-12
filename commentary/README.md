# Mas Golfs — Commentary Service

The autonomous commentary pipeline: sim events in, broadcast voice out.

```
sim JSON event (bus, ws://localhost:4456)
  -> decide: is a line due? (event-only, director hold, rate limits)
  -> cached standard line first (commentary-prompts.md §6.1)
  -> else local MLX LLM (Qwen3, docs/local-models.md), Ollama fallback
  -> validation: ≤280 chars, no banned words, numbers only from the event
  -> text normalization -> Kokoro TTS (localhost:8880) -> audio cache
  -> emit text + audio to the broadcast pipeline (output log + WAV files)
  -> log every decision to the JSONL decision log
```

**Free, local-only, no paid APIs.** The fallback hierarchy is: fresh
generation → cached line → silence. A paid API is never an option in
this code.

## Files

| File | What it is |
|---|---|
| `service.py` | The orchestrator: event routing, director hold, rate limits, silence budget, emission, logging |
| `config.yaml` | The single source of truth: bus, LLM, TTS, voices, rate limits, paths |
| `config.py` | Config loader (stdlib-only YAML-subset parser — no PyYAML on the box) |
| `prompts.py` | System prompts verbatim + user-prompt templates (commentary-prompts.md §2, §4) |
| `normalize.py` | Banned-word filter, 280-char cap, number validation, TTS text normalization (§5, §9, §10) |
| `cache.py` | Pre-seeded standard lines + disk-backed audio cache (§6) |
| `llm.py` | MLX / Ollama HTTP backends with automatic failover + deterministic stub |
| `tts.py` | Kokoro-FastAPI client + deterministic stub |
| `bus.py` | Minimal RFC 6455 WebSocket client (stdlib) + fake bus for demo/tests |
| `demo.py` | Scripted fake-event demo (round start → hole 12 → 59 Watch) |
| `tests/test_commentary.py` | 30 tests, all offline |

## Run it

```bash
# 1. The model servers it talks to (separate processes, on the box):
python -m mlx_lm.server --model mlx-community/Qwen3.5-4B-4bit \
  --port 8080 --max-kv-size 2048          # MLX LLM (docs/local-models.md §3.2)
ollama pull qwen3:1.7b                    # fallback LLM (docs/local-models.md §3.3)
docker run -d -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest  # TTS

# 2. The sim must be publishing events on ws://localhost:4456
#    (docs/broadcast-stack.md §1).

# 3. Run the service (from the repo root):
python3 -m commentary

# Dry run (no LLM/TTS calls — cached lines only, everything logged):
#   set dry_run: true in commentary/config.yaml
```

The service writes three things:

* `~/.masgolfs/commentary-output.jsonl` — one record per line played
  (voice, text, audio path, event). This is the handoff to the
  broadcast pipeline: OBS/NodeCG watch this file and the audio dir.
* `~/.masgolfs/commentary-audio/` — the rendered WAV for each played line.
* `~/.masgolfs/commentary-decisions.jsonl` — one record per decision
  (event, line, voice, backend, latency, cache hit, drop reason, and
  the running silence fraction). This is the log the weekly
  self-improvement review reads (docs/local-models.md §6).

## Test it (no servers needed)

```bash
# Demo: scripted fake event stream, stub LLM + stub TTS, offline.
python3 -m commentary --demo

# Full test suite (30 tests, all offline):
python3 -m unittest discover -s commentary/tests -v
```

## The acceptance test (commentary-prompts.md §11)

Play 60 seconds of the broadcast to a golfer with no context. It passes if:

1. They can tell you the score, the hole, and what Mas is trying to do — from the commentary alone.
2. Nothing the voices said was wrong about the numbers.
3. Nothing felt like hype, and nothing felt like a robot.
4. They ask what tournament it is.

If any of those four fails, the fix is in the prompts, not the voices.
Change the prompt, re-audition on the §8 lines, and try again. The
audition lines live in `docs/commentary-prompts.md` §8; run them through
the live MLX + Kokoro stack per the checklist in
`docs/local-models.md` §10 step 4 (every line ≤280 chars, no invented
numbers, no banned words).

## How the decisions work

* **Event-only.** A line is due only when an event says so. No timers,
  no filler. Roughly half the round is silence — that is the broadcast
  working correctly.
* **Director hold (rule 1).** A line queued when `shot_start` arrives
  is held until `landing`. Silence during the swing is always safe.
* **Rate limits (rule 11).** Max 1 line / 15 s, max 4 lines / hole.
  When events arrive faster, the lowest-priority line is dropped:
  result > 59 Watch > color > apex read.
* **Apex is selective.** A straight, on-line ball needs no call. A
  draw/fade working toward the flag (curve ≥ 5 yd) or a ball clearly
  offline (curve ≥ 10 yd) gets one short sentence.
* **59 Watch is always fresh.** Pace, strokes remaining, and
  probability change every hole — those lines are never cached.
* **Numbers are validated.** Every number in a generated line (digits
  or golf number words like "one eighty-seven") must appear in the
  event JSON or the `round_state` snapshot. An invented number drops
  the line and the cached standard call plays instead.
* **Two envelopes accepted.** The bus spec (broadcast-stack.md §1.2)
  says `{"event": ..., "data": {...}}`; the sim (sim/events.py)
  actually emits flat events (`{"type": ..., ...fields}`). The service
  normalizes both to the flat form.

## Failure modes (commentary-prompts.md §10)

| Failure | Response |
|---|---|
| LLM returns a line over 280 chars | Truncate at the last sentence boundary under 280; if none fits, drop it |
| LLM invents a number | Validation rejects it; cached standard call plays instead |
| LLM returns a banned word | Hard filter strips it; if unreadable after filtering, drop it |
| Line still queued at `shot_start` | Held until `landing` |
| MLX down | Automatic fallback to Ollama, logged; if both down, cached lines only |
| TTS down | Line dropped, logged; ambient bed carries the silence |
| Events faster than the rate limit | Lowest-priority line dropped, logged |
| `SILENCE` returned | Nothing plays. The bed carries the moment. |
