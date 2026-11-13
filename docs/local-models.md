# Mas Golfs — Local-Model Architecture

**The rule that governs this document:** everything runs locally, on the broadcast box, for $0 — no paid APIs, no cloud inference, no per-call cost. If a job cannot run on the box, the job is redesigned until it can, or it is dropped. There is no "just call an API" escape hatch.

**The box:** one 8GB MacBook Pro (Apple Silicon, unified memory, no discrete GPU). It is the only machine. The 128GB MacBook Pro is Mason's workhorse and is never the stream box. The 16GB MacBook Air is off-limits entirely — it was Mason's grandpa's computer, it holds all of his poems and writing, and his grandma wants to publish that material. It is never touched, repurposed, powered on for this project, or used as a failover. The local-model stack is therefore designed for exactly 8GB of unified memory, and every number in this document is budgeted against that.

**The runtime decision (Mason, Nov 12, 2026): MLX is the chosen runtime** — Apple's ML framework for Apple Silicon. llama.cpp (via Ollama) is the fallback. The whole stack below is built around MLX on the 8GB box: which models run well under MLX, what they cost in memory, and how the commentary LLM + TTS pipeline uses it.

**Why MLX wins here (verified, Nov 12, 2026):** on Apple Silicon, MLX is 20–87% faster than llama.cpp for generation on models under ~14B parameters (Groundy benchmarks, via the Starmorph Apple Silicon optimization guide). On a Mac Studio M3 Ultra, plain mlx-lm generated Qwen3.5 9B at 107.5 tok/s against Ollama's GGUF path at 77.7 tok/s — and, more importantly for an 8GB box, mlx-lm peaked at 5.24 GB of memory where Ollama's GGUF path took 15 GB for the same model and weights (TerminalBytes, measured). Memory efficiency is the deciding factor on this box, not raw speed: MLX's lower resident footprint is what makes a commentary LLM fit alongside OBS, a browser, NodeCG, and TTS.

**The one honest MLX caveat:** Ollama's MLX backend — the easy path — auto-activates only on Macs with 32GB+ RAM. It will not activate on the 8GB box. The MLX path here is therefore **mlx-lm directly** (Apple's reference implementation, with its built-in OpenAI-compatible server), not Ollama. That is a little more setup than `ollama pull`, and it is the right call: it is the fastest runtime *and* the lightest on memory, which is exactly what an 8GB box needs. llama.cpp stays as the fallback because it is the most battle-tested engine and Ollama makes it a one-command install.

**oMLX considered and set aside (Mason, Nov 12, 2026):** oMLX (github.com/jundot/omlx) is a local inference server built on MLX — OpenAI/Anthropic-compatible API, menu-bar app, continuous batching, tiered SSD KV cache. Mason has used it before for other work. Decision: plain mlx-lm. Our workload is one 4B model writing one short line per event — batching and long-context KV caching buy almost nothing here, and oMLX's extra server overhead and 16GB documented minimum cut against an 8GB box. oMLX stays an option if multi-model serving is ever needed; switching would be a `base_url` change in `commentary/config.yaml`, since the commentary service is already an OpenAI-compatible client.

**Related docs:** `docs/commentary-prompts.md` (the prompts the LLM runs), `docs/voice-options.md` (Kokoro TTS, the voices), `docs/broadcast-stack.md` §5 (the commentary pipeline), `docs/sim-engine.md` (the decision engine), `docs/deployment-runbook.md` (the box, the watchdog, no scheduled restart), `docs/self-improvement.md` (the learning loop this stack serves), `docs/qa-plan.md` (the verification gates).

---

## 0. Decisions up front (do not relitigate without new evidence)

| Decision | Choice | Why |
|---|---|---|
| LLM runtime | **MLX (mlx-lm)** | Fastest on Apple Silicon (20–87% over llama.cpp under 14B) and lightest on memory (5.24 GB vs 15 GB for the same 9B model under Ollama) |
| LLM runtime fallback | **llama.cpp via Ollama** | Most battle-tested; one-command install; the fallback is a config change, not a rebuild |
| Commentary LLM (default) | **Qwen3.5-4B-4bit MLX** (`mlx-community/Qwen3.5-4B-4bit`) | Best quality-per-GB measured in research (IFEval 89.8 vendor-reported); fits the 8GB budget; Apache 2.0 |
| Commentary LLM (fallback) | **Qwen3-4B-Instruct-2507, 4-bit MLX** | If Qwen3.5-4B misbehaves on the box; IFEval 83.4, Apache 2.0 |
| Commentary LLM (emergency) | **Qwen3-1.7B-Instruct, 4-bit MLX** | Only if neither 4B fits; weak as a live voice |
| Commentary LLM (does NOT fit) | **Qwen3-8B, Qwen3.5-9B, Qwen3.8-27B** | 8B needs ~10.3–10.8 GB total with the stack on an 8GB box; 27B needs ~16–19 GB. Both belong on the GPU box only |
| TTS engine | **Kokoro-82M, FP16** | Free, Apache 2.0, CPU-capable, ~6× real time on Apple Silicon; see `voice-options.md` §2 |
| Decision engine | **No model at all** | Monte Carlo over real physics (see §1.2) — a model would be slower, costlier, and worse |
| Clip selection | **Deterministic drama scoring, no model** | Rules + thresholds (see §1.4) — a model adds nothing a table cannot do |
| Thumbnail text / captions | **Templates + the commentary LLM** | No separate model; reuse the one already loaded |
| Cloud inference | **Never** | $0 is a design constraint, not a budget target |
| The 16GB MacBook Air | **Never used** | Grandpa's writing archive. Not a spare, not a failover, not a test box. |

---

## 1. The full inventory of local-model jobs

Every job the broadcast needs, what runs it, and whether it needs a model at all. The guiding principle: **a model is the last resort, not the first.** Most of the show is deterministic code, and that is a feature — deterministic code is free, instant, and never hallucinates a number.

### 1.1 Commentary LLM — the one real LLM job

- **What:** one LLM call per commentary event, using the prompt templates in `docs/commentary-prompts.md` §2 and §4. Two system prompts (Nantz-inspired host, Gruden-inspired color), one call per event, no conversation history, temperature 0.7, max 120 tokens, output 1–2 sentences / 280 characters maximum.
- **Load:** rate-limited to 1 line per 15 seconds, max 4 lines per hole (commentary-prompts §5, rule 11). A round is ~18 holes × ~6–8 events ≈ 120–150 LLM calls, each generating ~70 tokens. That is roughly one 70-token generation every 60–90 seconds of broadcast time — a trivial load for any small model, and the reason a 1.7B model is more than enough.
- **Latency budget:** lines are pre-generated during the walk, the swing, and the ball flight (commentary-prompts §6.3), so the LLM has seconds of headroom, not milliseconds. At an estimated 30–60 tok/s for a 1.7B 4-bit model under MLX on a base Apple Silicon chip (see §2.4), a 70-token line takes ~1.5–2.5 seconds. That is effectively zero perceived latency. The pipeline never waits on the model.
- **Model:** Qwen3.5-4B-4bit MLX (default). See §2. Verdict from the Nov 12 research (`docs/research/qwen3-family.md`, `docs/research/small-llm-broadcast.md`, `docs/research/qwen-27b-fit.md`): 4B is the practical ceiling on the 8GB box; 8B does not fit alongside the stack; 27B needs 24 GB+. The naming trap: Qwen3-8B is an 8B model from the Qwen3 generation; Qwen3.8-27B is a 27B model from the Qwen3.8 generation (Aug 2026).

### 1.2 The decision engine — no model, by design

- **What:** the sim's decision engine picks the club, trajectory, and target for every shot (see `docs/sim-engine.md` §5).
- **How it actually works:** candidate generation from the lie/wind gate, then a 200-sample Monte Carlo per candidate through the real ball-flight physics, ranked by expected strokes. No neural network, no API call, no model weights anywhere.
- **Why no model:** a model would be slower (a forward pass per candidate vs. a few hundred floating-point physics steps), costlier (memory the box does not have), and worse (a model can hallucinate a club choice; Monte Carlo over physics cannot — it can only rank real outcomes). The decision engine's "intelligence" is the physics plus the strokes-gained baseline table, and the learning loop changes only aim biases, risk threshold, and the baseline table — never a model's weights. **Do not "upgrade" the decision engine to an LLM.** That would be a downgrade in every dimension that matters: speed, cost, correctness, and auditability.
- **Cost on the box:** negligible — a few milliseconds of CPU per shot decision, no memory beyond the sim process itself.

### 1.3 Kokoro TTS — the voice

- **What:** renders each commentary line to audio in one of two voices (host `am_michael`, color `af_sky`), per `docs/voice-options.md` §2.
- **Model:** Kokoro-82M, 82M parameters, FP16 weights 169 MB. ~6× faster than real time on an M3 Pro CPU; a 20-second line renders in ~1–3 seconds on CPU. Pre-generate + cache by hash of `(voice + normalized text)` — repeated lines cost nothing.
- **Cost on the box:** ~0.3–0.5 GB resident for the model (native) plus the server process. See §4 for the Docker-vs-native decision, which matters on 8GB.
- **Not a job for the LLM:** TTS and text generation are separate engines with separate budgets. Never let the LLM "also do" TTS, and never let TTS load the LLM's memory.

### 1.4 Clip selection and drama scoring — no model

- **What:** the clip pipeline (`clip-pipeline/`) scores every moment with a drama model (hole-out 100, Road to 59 moment 100, eagle 95, near-miss 85, recovery 80, best decision 75, worst miss 75, streak 70, birdie 60) and picks the daily queue. See `docs/launch-playbook.md` §1.
- **How:** deterministic rules + thresholds over the event log. No ML, no embeddings, no classifier.
- **Why no model:** the drama model is a table, and a table is exactly right — every score is explainable ("this clip is in the queue because it is a hole-out, which scores 100"), every threshold is tunable in one line, and the whole pipeline runs in milliseconds on a CSV of events. A model would add latency, memory, and unexplainable picks for zero gain.

### 1.5 Future jobs — reuse the loaded model, never load a second one

| Future job | How it runs | New model? |
|---|---|---|
| Thumbnail text | 5–8 word title from the clip manifest, generated by the commentary LLM in a batch job after the round (same model, same process, off-peak) | No |
| Social captions | Caption + hashtags from the clip manifest, same batch job as thumbnails | No |
| Clip descriptions | One sentence per clip, same batch job | No |
| Weekly review summary | The Sunday review ritual's four questions answered from the event log, same batch job | No |
| Guest-twin calibration notes | Plain-language summary of a twin's profile, same batch job | No |
| Video-derived swing work | Pose estimation from Mason's swing video — **not on the 8GB box.** This is a GPU-box job (§7). Do not attempt it here. | Later, on the GPU box |

The rule: **one LLM resident on the box, ever.** Every future text job queues behind the commentary LLM or runs as a batch job when the LLM is idle (between rounds, or during an intermission — see §9). A second resident model is a memory decision, not a feature decision, and on 8GB it is a no.

---

## 2. Model selection per job

### 2.1 The commentary LLM — the decision table

All sizes are the Ollama/GGUF download size at Q4_K_M unless noted; MLX 4-bit weights are within ~10% of the same numbers. "Memory at 2K ctx" is weights + KV cache + runtime buffers at a 2,048-token context — the context this pipeline actually uses (prompts are ~300–500 tokens; 2K is generous headroom). Speeds are measured on an Apple M3 Pro (18GB) under Ollama/llama.cpp unless noted, from community benchmarks published Nov 2026 — treat them as order-of-magnitude, not promises; §10 verifies them on the real box.

| Model | Params | License | Download (Q4_K_M) | Memory at 2K ctx | Speed (M3 Pro) | Verdict for this box |
|---|---|---|---|---|---|---|
| **Qwen3-0.6B-Instruct** | 0.6B | Apache 2.0 | ~0.5 GB | ~1.0 GB | ~150+ tok/s (est.) | The emergency fallback. Runs anywhere, but its instruction-following is thin — lines get generic. Only if the 1.7B will not fit. |
| **Qwen3-1.7B-Instruct** | 1.7B | Apache 2.0 | ~1.4 GB | ~2.0 GB | ~80–100 tok/s (est.) | **The emergency fallback.** Fits with headroom, but weak as a live voice — superseded by the 4B picks (Nov 12 research). |
| **Llama 3.2 3B Instruct** | 3B | Llama 3.2 Community | ~2.0 GB | ~3.5 GB | 55.6 tok/s (measured) | The alternative default. Best instruction-following in the 3B class, most-downloaded small model. Costs ~1.5 GB more than the 1.7B for a quality gain the prompts mostly do not need — the prompts do the work, not the model size (commentary-prompts §2.3). |
| **Phi-4-mini-instruct** | 3.8B | MIT | ~2.5 GB | ~4.0 GB at 2K (4.5 GB at 8K) | 43.7 tok/s (measured) | The reasoning pick. Leads its class on reasoning benchmarks, MIT license. But its KV cache is heavy (128 KB per token — a 32K context would add 4.3 GB alone), so it lives or dies on the 2K context cap. A credible second choice if the 1.7B disappoints on decision lines. |
| **Gemma 3 4B IT** | 4B | Gemma (Google) | ~3.4 GB | ~4.5 GB (est.) | ~40 tok/s (est.) | The quality pick at 4B. Good instruction-following, but the largest file of the candidates and no clear edge over Qwen3-4B for 280-character lines. |
| **Qwen3-4B-Instruct-2507** | 4B | Apache 2.0 | ~2.5 GB | ~3.5–4.0 GB | ~50–60 tok/s (est.) | **The fallback.** IFEval 83.4, MMLU-Pro 69.6 — effectively closes the 4B→8B gap. Used if Qwen3.5-4B misbehaves on the box. |
| Qwen3-8B / Llama 3.1 8B | 8B | Apache 2.0 / Llama | ~5.2 GB / ~4.7 GB | ~6.5 GB+ | ~30–50 tok/s | **Do not run on the 8GB box.** Weights alone leave nothing for OBS, the browser, and TTS. These are GPU-box models (§7). |

**Why Qwen3.5-4B is the default, in one paragraph (updated Nov 12, 2026):** the commentary job is 120–150 short generations per round, each ~70 tokens, from a tight prompt with all the numbers supplied. The model is not reasoning from scratch — it is turning structured event data into one or two warm sentences. The Nov 12 research measured the gap: in non-thinking mode (the mode commentary uses), Qwen3-4B is only +1.8 IFEval points behind Qwen3-8B, and Qwen3.5-4B (IFEval 89.8 vendor-reported) beats Qwen3-8B outright at half the size. The 4B generates ~2× as fast as the 8B on this box and is the largest model that fits alongside the stack. Pick the model that fits, not the model that impresses.

**Licenses, read once:** Qwen3 (all sizes) is Apache 2.0 — commercially clean, no restrictions. Phi-4-mini is MIT. Gemma 3 is under Google's Gemma license (permissive, but read it before commercial use). Llama 3.2 is under Meta's Llama 3.2 Community License — commercial use allowed, with a separate license required only above 700M monthly active users. None of these is a problem for this broadcast; all are noted here so nobody has to re-check them later.

**Quantization — Q4 is the sweet spot, Q8 only for the smallest models:**
- **Q4_K_M (GGUF) / 4-bit (MLX):** the default. ~0.5 bytes per parameter, ~95% of full-precision quality on short-form generation, 75% size reduction against FP16. Every model above is run at 4-bit.
- **Q8_0:** use only on models ≤1B (Qwen3-0.6B), where the absolute size is small enough that the extra precision is nearly free. On 1.7B+, Q8 doubles the memory for a quality gain no viewer can hear in a 280-character line.
- **Q5_K_M / Q6_K:** only if memory headroom appears after the audit and a specific quality gap is demonstrated on real lines. Never pre-emptively.
- **Q2_K / Q3_K_M:** never. The quality loss shows up exactly where it hurts — numbers drifting, sentences truncating.
- **MLX quantization note:** mlx-community 4-bit quants are the MLX equivalent of Q4_K_M. They are not bit-identical to GGUF, but they are the same trade-off (4 bits per weight, mixed precision on sensitive tensors) and the same size class.

### 2.2 TTS — Kokoro-82M (already decided, restated for the budget)

- **Model:** Kokoro-82M, 82M parameters, StyleTTS2-based, 24 kHz output. FP16 weights 169 MB, INT8 88 MB. FP16 is the sweet spot.
- **Voices:** host `am_michael` (speed 1.0), color `af_sky` (speed 1.05). See `voice-options.md` §2.
- **Speed:** ~6× real time on an M3 Pro CPU; a 20-second line renders in ~1–3 seconds on CPU. Pre-generate + cache (commentary-prompts §6) makes this effectively free at broadcast time.
- **License:** Apache 2.0. Commercially clean.

### 2.3 What is deliberately NOT on the box

| Candidate | Why not |
|---|---|
| Qwen3-8B / Llama 3.1 8B (commentary) | ~5 GB weights. Does not fit alongside OBS + browser + TTS on 8GB. GPU-box job (§7). |
| Qwen3-TTS 0.6B/1.7B | 6–12 GB VRAM, GPU-only in practice, hard setup. Re-evaluate at the Unreal leap (voice-options §5). Kokoro is the voice now. |
| Chatterbox (cloning) | ~4.5 GB VRAM, GPU-preferred. The upgrade path for locked-in voice identities, on the GPU box (voice-options §4). |
| Any vision / pose-estimation model | Video-derived swing work is a GPU-box job (§7). Not attempted on 8GB. |
| Any embedding / reranking model | Nothing in the pipeline needs retrieval. The event log is structured data, not a corpus. |
| A second LLM "for captions" | One resident LLM, ever (§1.5). Batch jobs reuse it. |

---

## 3. The runtime stack — MLX first, llama.cpp as fallback

### 3.1 The stack, in one picture

```
sim JSON event
  → commentary service (Python, one process)
      → prompt templates (docs/commentary-prompts.md §2/§4)
      → LLM backend: mlx-lm server  ←── MLX (default)
      │                 (OpenAI-compatible HTTP, localhost:8080)
      │   fallback: Ollama (llama.cpp Metal) on localhost:11434
      → text normalizer (numbers → words, banned-word filter)
      → TTS backend: Kokoro-FastAPI (OpenAI-compatible HTTP, localhost:8880)
      → audio cache (hash of voice + normalized text) → OBS audio, bed ducked
```

**One interface, every engine behind it.** The commentary service talks to an OpenAI-compatible HTTP endpoint for both text and speech. Swapping the LLM runtime is a config change (`llm.backend: mlx | ollama`), never a code change. Swapping the TTS engine is the same (see `voice-options.md` §8). This is what makes the fallback real instead of theoretical.

### 3.2 MLX — the default (mlx-lm)

**What it is:** Apple's ML framework for Apple Silicon, built on Metal. `mlx-lm` is the reference LLM library on top of it, with an OpenAI-compatible server built in.

**Why it is the default on this box:**
- Fastest generation on Apple Silicon for models under ~14B (20–87% over llama.cpp).
- Lightest memory footprint of any runtime (5.24 GB peak vs 15 GB for the same 9B model under Ollama's GGUF path — the difference is KV-cache and context handling, and on an 8GB box that difference is the whole game).
- Native Metal, no translation layer, no Docker, no VM — it runs as a plain Python process on macOS.
- MLX quants for every model in §2.1 are published by `mlx-community` on Hugging Face, ready to pull.

**Setup (on the 8GB MBP):**

```bash
# 1. Python 3.12+ (python.org or Homebrew; never the system Python)
python3 -m venv ~/.venvs/masgolfs
source ~/.venvs/masgolfs/bin/activate

# 2. Install mlx-lm
pip install mlx-lm

# 3. Pull the default model (4-bit MLX quant from mlx-community)
#    First run downloads the weights (~1.4 GB) and caches them locally.
python -m mlx_lm.server --model mlx-community/Qwen3.5-4B-4bit --port 8080
#    Verify it answers:
curl http://localhost:8080/v1/models

# 4. Pin the context: the server must run with a small context window.
#    The commentary prompts are ~300-500 tokens; 2,048 is generous.
#    Set it explicitly — never rely on a runtime default, which can be
#    32K or larger and will eat the KV cache (and the box) alive.
#    Verified on the box 2026-11-13 (mlx-lm 0.32.2): --max-kv-size
#    does NOT exist in the 0.32.x server (generate-only). The bound is
#    --prompt-cache-size 1 (one cached prefix, not ten) plus
#    --max-tokens 120 (matches commentary/config.yaml). Requests are
#    stateless single prompts, so the active KV is ~320 tokens max.
python -m mlx_lm server --model mlx-community/Qwen3.5-4B-4bit \
  --port 8080 --prompt-cache-size 1 --max-tokens 120
```

**MLX quirks to know before they bite:**
- **Prefill is full before the first token.** MLX computes the entire prompt before emitting anything, so time-to-first-token rises linearly with prompt length. Our prompts are short (~300–500 tokens), so this is a non-issue here — but it is why the 2K context cap matters twice over: long context would cost both memory *and* first-token latency.
- **First load is slow, then it is fast.** Model load takes a few seconds (weights read from disk into unified memory). The server stays resident, so this happens once per boot — never per call. The watchdog (§8) restarts the server if it dies; it does not restart it per round.
- **MLX is Apple Silicon only.** The stack is Mac-native by design. On the future GPU box (NVIDIA), the runtime switches to vLLM or Ollama — see §7. That is a planned migration, not a surprise.
- **Verify the server command on the real box.** mlx-lm's server flags move between releases. The commands above are the shape, not gospel — run them once on the 8GB MBP, confirm the port answers, and write the exact working command into the runbook.

### 3.3 llama.cpp via Ollama — the fallback

**What it is:** Ollama bundles llama.cpp's Metal backend behind a one-command install and an OpenAI-compatible API on `localhost:11434`.

**When it runs:** only if the MLX server fails to start, crashes repeatedly, or a model has no MLX quant. The commentary service tries MLX first, falls back to Ollama, and logs the switch. A fallback that has never been tested is not a fallback — §10 tests it.

**Setup:**

```bash
# 1. Install Ollama (ollama.com, macOS installer)
# 2. Pull the fallback model (GGUF Q4_K_M, same model as the MLX default)
ollama pull qwen3:1.7b
# 3. Run with an explicit small context — Ollama's defaults can be
#    enormous (one measured run loaded a 262K context and took 15 GB
#    for a 6.6 GB model). Never rely on the default.
ollama run qwen3:1.7b --help   # confirm the context flag on the installed version
#    then serve with num_ctx 2048, e.g. via a Modelfile:
#    FROM qwen3:1.7b
#    PARAMETER num_ctx 2048
#    PARAMETER temperature 0.7
#    PARAMETER num_predict 120
```

**Why Ollama's MLX backend is NOT the plan:** Ollama 0.19+ ships an MLX backend that is 57–93% faster than its llama.cpp backend — but it auto-activates only on Macs with 32GB+ RAM. It will not activate on the 8GB box. Do not spend an afternoon trying to force it. mlx-lm directly is the MLX path here; Ollama is the llama.cpp path.

### 3.4 Kokoro — the TTS server, and the Docker question

Kokoro-FastAPI runs in Docker in the voice-options doc — and on a Mac, Docker runs inside a Linux VM with its own memory overhead (~0.5–1 GB for Docker Desktop itself, before the model). On an 8GB box, that overhead is real money. Two options, in order:

1. **Native install (preferred on this box).** Install Kokoro via pip (`kokoro` package / FastKokoro) and run it as a plain Python process, no Docker, no VM. Same OpenAI-compatible endpoint shape, same voices, ~0.3–0.5 GB total instead of ~1–1.5 GB through Docker. Verify on the real box; if the native install fights (dependency conflicts with the mlx-lm venv — keep them in separate virtualenvs), fall back to option 2.
2. **Docker with a hard memory limit (the fallback).** `docker run --memory=1g --memory-swap=1g` on the Kokoro container, so a TTS memory spike can never take the encoder down with it. The voice-options doc's Docker commands still apply, with the limit added.

Either way, Kokoro is memory-capped, and the watchdog (§8) restarts it if it stops answering. TTS down never takes the broadcast down — it takes the commentary down, and the ambient bed carries the silence (commentary-prompts §10).

### 3.5 Configuration — one file, everything in it

```yaml
# models.yaml — the single source of truth for the local-model stack.
# The commentary service reads this at boot. Nothing about models
# lives in code.
llm:
  backend: mlx                 # mlx | ollama (fallback, automatic on MLX failure)
  mlx:
    model: mlx-community/Qwen3.5-4B-4bit
    base_url: http://localhost:8080/v1
    max_kv_size: 2048
  ollama:
    model: qwen3:1.7b
    base_url: http://localhost:11434/v1
    num_ctx: 2048
  generation:
    temperature: 0.7
    max_tokens: 120
    timeout_seconds: 10        # a call slower than this is dropped, not awaited
tts:
  engine: kokoro               # kokoro | piper (emergency fallback)
  base_url: http://localhost:8880/v1
  host: { voice: am_michael, speed: 1.0 }
  color: { voice: af_sky, speed: 1.05 }
  cache_dir: ~/.masgolfs/tts-cache
budgets:
  llm_memory_mb: 2200          # hard cap: if the LLM process exceeds this, restart it
  tts_memory_mb: 1024          # hard cap (Docker limit or cgroup equivalent)
```

---

## 4. The resource budget — 8GB, accounted for

This is the table the whole architecture stands or falls on. Numbers are budgets (ceilings), not measurements — §10 measures them on the real box and this table is corrected from those measurements. "Resident" is steady-state memory while the stream is live.

### 4.1 The budget table

| Process | What it is | Resident budget | Notes |
|---|---|---|---|
| macOS + system | The OS, WindowServer, background daemons | ~1,500 MB | Non-negotiable. Measure it on the real box at idle before anything else starts. |
| OBS Studio | 1080p60, hardware encode (VideoToolbox), 2 scenes + browser sources | ~600 MB | Hardware encoding keeps this low; x264 software encoding would double it and is forbidden on this box. |
| Browser (web build) | One Chromium tab, the 3D broadcast, Balanced tier | ~900 MB | One tab only. No other tabs, no extensions. Balanced tier (not High) on 8GB — see deployment-runbook §3.2. |
| NodeCG | Graphics server + bundle | ~250 MB | Node.js; small and steady. |
| Commentary service | Python: event bus client, prompt templates, cache, audio chain | ~150 MB | The orchestrator. Small by design — it holds no model weights. |
| **MLX server (Qwen3.5-4B 4-bit)** | **The commentary LLM** | **~2,500 MB** | Weights ~2.3 GB + KV cache at 2K ctx ~0.3 GB + runtime/buffers ~0.3 GB. The single largest line. |
| **Kokoro (native)** | **TTS** | **~400 MB** | FP16 weights 169 MB + server + buffers. Native install (preferred, §3.4). |
| Kokoro (Docker) | TTS, if native fails | ~1,000 MB | Model + Docker Desktop VM overhead. Only if native is impossible. |
| Watchdog + misc | launchd agents, logging, ops tools | ~100 MB | |
| **Total (native Kokoro)** | | **~5,900 MB** | **Leaves ~2,100 MB headroom on an 8GB box.** |
| **Total (Docker Kokoro)** | | **~6,500 MB** | **Leaves ~1,500 MB headroom. Workable, tighter.** |

**The headroom is the point.** ~2 GB of free memory is what lets the box absorb a spike — a big browser frame, a TTS burst, a model reload — without swapping. Swap is the failure mode on this box (deployment-runbook §0): a swap-thrashed encoder drops frames first. The watchdog watches swap, not just RAM (§8).

### 4.2 What runs concurrently, what queues

| Concurrency rule | Why |
|---|---|
| The LLM and TTS run concurrently | They are a pipeline (text → audio), not alternatives. The LLM generates while TTS renders the previous line. |
| Only one LLM call in flight at a time | Rate limits (1 line / 15 s) guarantee this. No batching, no parallel calls. A second call queues behind the first and is dropped if it ages past its event. |
| Batch jobs (thumbnails, captions, weekly summary) run only when the LLM is idle | Between rounds, or during an intermission (§9). Never during a live round. A batch job that collides with a live commentary call loses — it is killed, not queued. |
| The sim, the decision engine, and the clip pipeline are CPU-only and run concurrently with everything | They use milliseconds of CPU and megabytes of RAM. They never wait on a model. |
| Nothing else runs on the box | No browser with Mason's sessions, no Slack, no code editor, no second LLM. See deployment-runbook §1.5. |

### 4.3 What degrades first under pressure

In order, when memory or CPU runs short:

1. **Batch jobs die first.** Thumbnails and captions are killed silently. The broadcast never notices.
2. **The LLM drops to cached lines.** If a generation is slow or the LLM is down, the pipeline plays the cached standard call for that event (commentary-prompts §6.1) instead of generating fresh. The viewer hears a correct, if less specific, line.
3. **Commentary goes silent.** If TTS is down or the LLM is down and the cache misses, the ambient bed carries the moment. Silence is always the safe choice (commentary-prompts §5, rule 12).
4. **The browser drops a quality tier.** Balanced → Lite (shadows off, lower DPR). The broadcast gets plainer, not broken.
5. **The stream never degrades.** OBS is the last thing to lose resources. If the box is in genuine trouble, everything else is killed before the encoder is touched. A silent, plain-looking live stream beats a dead stream.

### 4.4 The Qwen3-4B question — settled by research (Nov 12, 2026)

Qwen3-4B 4-bit MLX costs ~3.5–4.0 GB resident (weights ~2.5 GB + KV + buffers) against the 1.7B's ~2.0 GB. Swapping it in would take the native-Kokoro total from ~5.9 GB to ~7.4–7.9 GB — leaving ~100–600 MB of headroom, which is not headroom at all. **The rule:** the 4B runs on the box only if, after a full 24-hour soak on the real box with the 1.7B, measured peak memory (all processes, worst minute) stays under 6.5 GB *and* swap stays at zero for the whole soak. If either condition fails, the 4B stays off the box and the 1.7B is the model. This is a measurement decision, not a preference decision, and it is made once, in §10, not debated weekly.

---

## 5. The commentary LLM + TTS pipeline on MLX

How the pieces in §3 actually run a round. This is the pipeline from `docs/broadcast-stack.md` §5, specified for the MLX stack.

### 5.1 The call flow, event by event

```
sim emits `decision` event
  → commentary service builds the user prompt from the template
    (commentary-prompts §4.1, placeholders filled from the event JSON)
  → POST to the MLX server (OpenAI-compatible /v1/chat/completions)
      model: mlx-community/Qwen3.5-4B-4bit
      messages: [system prompt (host or color, verbatim), user prompt]
      temperature 0.7, max_tokens 120, no history
  → line returned (~70 tokens, ~1.5-2.5 s at 30-60 tok/s)
  → validation: ≤280 chars, no banned words, every number present
    in the event JSON or round_state (else drop the line)
  → text normalizer (187 → "one eighty-seven", 7-iron → "seven iron")
  → cache lookup: hash(voice + normalized text)
      hit  → play the cached audio file (cost: $0, latency: 0)
      miss → POST to Kokoro /v1/audio/speech → audio → store in cache
  → OBS audio, bed ducked, never over a swing (director hold)
```

**Timing, worked:** a decision line is generated the moment the sim emits `decision` — seconds before the swing. At ~30–60 tok/s, a 70-token line takes ~1.5–2.5 seconds, and TTS takes ~1–3 seconds on CPU. Both finish inside the walk and the waggle. A result line is generated at `apex` — seconds before landing. The model is never on the critical path of anything the viewer sees. That is the whole latency strategy: pre-generation, not speed.

### 5.2 Why the prompts, not the model, do the work

The system prompts in commentary-prompts §2 are doing the heavy lifting: the voice, the cadence, the banned words, the number discipline, the silence rule. The model is a sentence-turner, not a thinker. That is why a 1.7B model is enough, and why swapping models (1.7B → 3B → 4B) changes the lines less than changing one sentence of the prompt. **When a line is wrong, fix the prompt first.** The model is the last suspect, never the first.

### 5.3 The cache is the cost control

- **What is cached:** every line, keyed by hash of `(voice + normalized text)` (commentary-prompts §6). Hole intros, standard score updates, routine result calls, round openers/closers, and the off-pace notice are templated and synthesized once.
- **What is never cached:** decision lines, 59 Watch moments, milestones, the learning fix, recoveries, apex reads (commentary-prompts §6.2). A stale pace line is a wrong line.
- **Cache size:** a 24-hour round is a few hundred short lines, tens of megabytes on disk. The cache lives on the broadcast box, survives restarts, and is invalidated when any number inside a line changes (score-update lines are keyed by `(thru, score_to_par)`).
- **The economic point:** the cache is what makes the LLM load trivial. Most of what the viewer hears in a round is a cached line; the LLM only generates the lines that are genuinely new. On a typical round, the LLM generates ~40–60 fresh lines and the cache serves the rest.

### 5.4 Two voices, one pipeline

The host and color are not two models — they are two system prompts and two Kokoro voices behind one pipeline. The LLM generates both voices' lines from the same server, one call at a time. The handoff order (commentary-prompts §3.3) is enforced by the director, not the model: color before the shot, silence during the swing, host as the ball lands.

---

## 6. The self-improvement loop for the models themselves

The show's learning loop (`docs/self-improvement.md`) improves Mas. This section is the loop that improves the *models* — the commentary and the pipeline — from the same event log. It is deliberately the cheapest form of improvement: **prompt iteration and cache learning, not retraining.** Retraining is never needed for this job, and light fine-tuning is a later, optional step with its own gate.

### 6.1 What is logged (the raw material)

Every LLM call writes one log row: the event type, the prompt (template + filled placeholders), the model + runtime, the raw output, the validated output (or the drop reason), generation time, tokens, and whether the line played, was held, or was dropped. Every TTS call writes: voice, text hash, cache hit/miss, render time. The event log already exists (`docs/analytics.md` §4: event log retained 90 days hot); the model log is a view over it, not a second system.

### 6.2 The weekly improvement cycle (part of the Sunday review)

Once a week, in the Sunday 30-minute review (`docs/analytics.md` §5), the model log is read for four questions:

1. **What got dropped, and why?** Lines dropped for invented numbers, banned words, or over-length point at prompt wording, not model quality. Fix the template sentence that invited the failure.
2. **What sounded wrong?** Mason (or a listener) flags lines that felt robotic, hyped, or off-cadence. Each flagged line is traced to its template and its system prompt. One sentence changes at a time.
3. **What is the cache hit rate?** If the hit rate is falling, the lines are varying more than they need to — usually because a template includes a number that changes every time (a timestamp, a running total). Move the varying number out of the cached part.
4. **What is the generation latency?** P50 and P99 per event type. If P99 creeps past 5 seconds, something is wrong with the runtime (swap, thermal throttle, a runaway process) — not the model. Fix the box, not the prompt.

**The rule for every change:** one change at a time, then a full round to observe it. Prompt changes are versioned in git (the prompts file is the config), and a bad change is reverted by checking out the previous version. There is no "try five things at once" — that is how you learn nothing.

### 6.3 Cached-line learning (the cheap win)

The cache is not just a cost saver — it is a learning mechanism. Over weeks, the cache accumulates the lines that actually played well: the standard calls that never got flagged, the hole intros that sounded right, the score updates that landed. When a template is revised, its cached lines are regenerated once and the new versions become the new standard. The show's voice converges on its best lines without anyone retraining anything. This is the highest-leverage improvement in the whole system, and it costs nothing.

### 6.4 Prompt A/B, the honest way

When two prompt wordings are genuinely in contention, run them on alternate rounds (round N uses wording A, round N+1 uses wording B) and compare the drop rate and the flagged-line count over at least 10 rounds each. Do not judge on one round. Do not judge by feel alone — the log is the judge. The winner becomes the template; the loser is deleted, not kept "just in case."

### 6.5 Fine-tuning — the later, optional step (gated, not assumed)

Light fine-tuning (LoRA on the commentary LLM, trained on the log of lines that played well) is a real option *later*, and it is gated on all four of these being true:

1. The show has at least 90 days of logged lines (thousands of accepted examples).
2. A specific, demonstrated gap exists that prompt changes cannot close (e.g. the model consistently mangles one construction).
3. There is a machine to train on — fine-tuning does not happen on the 8GB broadcast box. It happens on the GPU box (§7) or a rented GPU, once, and the resulting adapter (a few hundred MB) is copied to the broadcast box.
4. The fine-tuned model is A/B'd against the base model on real rounds (§6.4) and wins on drop rate + flagged lines before it ships.

**Until all four are true, there is no fine-tuning.** The base model plus good prompts plus the cache is the system. Anyone proposing fine-tuning before the gates are met is solving a problem the log has not demonstrated.

### 6.6 What never changes

- The decision engine never becomes a model (§1.2).
- Dispersion σ never changes (self-improvement.md §1) — the golfer improves by aim and judgment, not by tighter physics.
- The hard rules never relax (commentary-prompts §5): no invented numbers, no hype words, no speaking over a swing, no mentioning the machine. A model that cannot follow the rules is replaced, not accommodated.

---

## 7. The upgrade path — what changes when the GPU box arrives

The GPU box (own RTX 4090 box ~$2,500–3,000 + ~$35–52/mo power, or a rented spot GPU ~$248–650/mo — see `docs/deployment-runbook.md` §7 and `docs/unreal-vertical-slice.md`) is bought for Unreal, not for models. But it changes the local-model stack in useful ways, and the plan for that day is written now so it is a migration, not a redesign.

| What changes | On the 8GB MBP (now) | On the GPU box (later) |
|---|---|---|
| LLM runtime | MLX (mlx-lm), Apple Silicon only | **vLLM or Ollama** (CUDA). MLX does not run on NVIDIA. The OpenAI-compatible interface (§3.1) means the commentary service does not change — only `llm.backend` and `base_url` change. |
| Commentary LLM | Qwen3.5-4B 4-bit (default), Qwen3-4B-Instruct-2507 fallback, 1.7B emergency | **Qwen3.5-9B Q4_K_M** (~5.5–6 GB) on the GPU box, then **Qwen3.8-27B Q4_K_M** (~16–19 GB). Qwen3-8B is a dead end as a target (best of its generation, two generations behind). The 1.7B stays as the emergency fallback. |
| TTS | Kokoro-82M on CPU | Kokoro on GPU (35–100× real time, ~300 ms to first audio) — same engine, same voices, same cache. Optionally Chatterbox for locked-in cloned voices (voice-options §4). |
| Qwen3-TTS | Not on the box | Re-evaluate: 0.6B/1.7B with a vLLM streaming server, cloning from 3-second clips. Only if it beats Kokoro on a real audition. |
| Video-derived swing work | Not attempted | **This is the GPU-box job.** Pose estimation from Mason's swing video for the MetaHuman swing (unreal-vertical-slice.md). It needs a GPU and it gets one. |
| Fine-tuning | Gated, not done (§6.5) | The GPU box is where LoRA fine-tuning happens, once, if the gates are met. The adapter ships back to the broadcast box. |
| What stays on the 8GB MBP | — | **The broadcast itself.** The 8GB MBP remains the OBS/stream box. The GPU box renders Unreal and serves models; it does not become the encoder. Separation is the point. |

**Migration order (when the box arrives):** (1) Unreal slice first — the box is bought for Unreal. (2) Move the LLM to the GPU box and A/B it against the 1.7B on real rounds; ship the bigger model only if it wins on drop rate + flagged lines. (3) Move TTS to the GPU box; keep Kokoro on the MBP as the fallback. (4) Video-derived swing work. (5) Fine-tuning, only if the §6.5 gates are met. Each step is independently reversible — the 8GB stack stays installed and working throughout, so any step can be rolled back by flipping `models.yaml` back.

---

## 8. Failure modes and fallbacks

| Failure | Detection | Response | Viewer sees |
|---|---|---|---|
| MLX server slow (P99 > 5 s) | Generation-time log + watchdog | Drop the slow call; play the cached standard line for that event. Log it. If it repeats 3× in a round, restart the MLX server at the next hole. | A correct, slightly less specific line. Nothing. |
| MLX server down | Health check fails (port 8080 silent) | Automatic fallback to Ollama/llama.cpp on localhost:11434 (same model, GGUF). Log the switch. If Ollama is also down, go to cached lines only. | Nothing, or cached lines. |
| Ollama also down | Health check fails | Cached lines only (commentary-prompts §6.1). Fresh generation is suspended until a runtime recovers. | Cached lines, then silence. |
| LLM invents a number | Output validation (every number must be in the event JSON or `round_state`) | Line dropped; cached standard call plays instead (commentary-prompts §10). | The standard call. |
| LLM returns a banned word | Hard filter | Word stripped; if the line is unreadable after filtering, drop it. | Nothing, or the standard call. |
| TTS (Kokoro) down | Health check fails (port 8880 silent) | Fallback to Piper if installed (voice-options §3); else silence + ambient bed. Never a paid API without a human flipping the config. | Silence + the bed. The golf carries it. |
| Memory pressure / swap > 0 | Watchdog watches swap (deployment-runbook §4.1) | Kill batch jobs first; restart the LLM server (frees the KV cache); drop the browser a quality tier (Balanced → Lite). OBS is never touched. | Possibly plainer visuals for a while. |
| Model file corrupt / missing | Server fails to start | Fall back to the other runtime; if both fail, cached lines + silence. Alert Mason (one alert, §8 in analytics.md). | Cached lines, then silence. |
| A line is still queued at `shot_start` | Director hold (broadcast-stack §3) | Hold the line until `landing`. Silence is always safe. | Silence during the swing — correct behavior. |
| Events arrive faster than the rate limit | Rate limiter (1 line / 15 s, 4 per hole) | Drop the lowest-priority line (result > 59 Watch > color > apex read). | Fewer lines, never overlapping lines. |

**The fallback hierarchy, in one line:** fresh generation → cached line → silence → (never) a paid API. Every step down is automatic, logged, and reversible. A human flips the config back up; the system never spends money on its own.

---

## 9. Operations concept — the "pee break" intermission

Planned maintenance is the one place a 24/7 autonomous stream has to stop being autonomous for a few minutes. The rule for this show: **maintenance never looks like downtime.** It looks like a break in the broadcast — because that is what it is.

### 9.1 What it is

When a planned maintenance window arrives, the director cuts to a branded intermission card instead of the golf. The card says, in the show's voice:

> **Mas is taking a quick break — back in a moment.**
> *Updating the broadcast · back shortly*

Under the headline, the card shows the things a viewer actually wants while they wait: the current score and hole, the 59 Watch status, the leaderboard top 3, and a countdown ("Back in about 4 minutes"). The ambient bed keeps playing under it — birds, breeze, the course breathing — so the stream never goes silent and never goes black. Then the stream auto-resumes: the director cuts back to the golf, the host says one line ("And we're back — Mas is on the 13th, two under"), and the round continues exactly where it left off.

### 9.2 What it is for

| Maintenance job | Why it needs a window | Typical length |
|---|---|---|
| A fault-driven restart (watchdog-detected drift) | Memory climbing, event bus silent, encoder failing (deployment-runbook §4.4) | ~2–3 minutes |
| macOS updates (Sunday, by hand) | An unattended update rebooting the box mid-round is the most avoidable outage in the runbook | ~10–15 minutes |
| Model pulls (new LLM or TTS version) | The server restarts to load new weights; a restart mid-round would drop a line | ~3–5 minutes |
| Cache rebuild (after a prompt change) | Regenerating cached lines after a template revision | ~2–3 minutes |
| OBS scene / graphics changes | New NodeCG graphics or OBS scenes need a reload | ~2–5 minutes |
| The Sunday review's action items | Anything the review decided that needs the box touched | Varies, capped at 15 minutes |

**The hard cap: 15 minutes.** Any maintenance that would take longer is split across windows or deferred. A 15-minute intermission is a break; a 45-minute intermission is an outage with a nice card on it.

### 9.3 How it works (the mechanics)

1. **The sim state is persisted, always.** The round state (hole, score, strokes, 59 Watch pace, conditions) is written to disk on every event — not just at maintenance time. The intermission does not "pause" the sim; the sim's state is safe on disk, and the broadcast resumes from exactly that state. This is the same persistence the crash-recovery path uses (deployment-runbook §4), so the intermission is just the planned version of a recovery.
2. **The director schedules it, never the clock alone.** A maintenance window is scheduled (Sunday for updates; fault-driven restarts whenever the watchdog calls one), but the director defers it if the moment is wrong: never during a 59 Watch `on_the_line` moment, never mid-hole-out, never during an eagle putt. The window waits for the next hole boundary or the end of the round — whichever comes first, up to 30 minutes of deferral. If the deferral expires, the intermission runs anyway and the card says why ("Quick break while Mas walks to the next tee").
3. **The card is a NodeCG graphic, not a video file.** It is built from the same design system as the scorebug (brand-identity.md: Fairway #0B3D2E, Gold #C9A227, Cream #F5F1E6), driven by the same replicants (`roundState`, `shotData`) — so the score, the 59 Watch status, and the leaderboard on the card are always live numbers, never a stale image. The countdown is real (time until the scheduled resume).
4. **The update runs, the watchdog watches.** During the intermission, the watchdog's checks keep running (deployment-runbook §4.1). The update is a script with a checklist, not a human clicking around: stop the service, apply the change, start the service, health-check it, log the result. If any health check fails, the watchdog rolls back to the previous version and the intermission extends by the rollback time — the card updates its countdown and its message ("Taking a little longer — back shortly").
5. **Auto-resume is verified, not assumed.** The stream does not cut back to golf because a timer expired. It cuts back because the watchdog confirms: OBS is streaming, the web build is rendering, the event bus is alive, NodeCG is serving graphics, and the sim state on disk matches the state before the break. Only then does the director cut back, with the host's "we're back" line. If verification fails, the intermission continues and Mason is alerted (one alert — the only maintenance alert in the system).
6. **The log records it.** Every intermission writes one line to the ops log: start, end, reason, what changed, verification result. If it isn't written down, it didn't happen (deployment-runbook §6.4).

### 9.4 The tone (why it is a "pee break" and not "maintenance")

The card's language is the show's language, not IT language. "Mas is taking a quick break" — not "scheduled maintenance window." "Updating the broadcast" — not "applying macOS 15.4.1." The countdown is honest ("Back in about 4 minutes"), the leaderboard is real, and the bed keeps playing. The viewer experience is: the golfer walked to the next tee and the broadcast took a breath. That is the truth, told in the show's voice — and it is also the most honest possible framing, because the sim really is just waiting on the next tee while the box does its chores.

**What the intermission never does:** it never shows an error, never shows a terminal, never shows "stream offline," never plays a generic "we'll be right back" stock card, and never runs during a moment a viewer would pay to see. If the moment is too good to interrupt, the maintenance waits. The golf outranks the chores, every time.

### 9.5 Scheduling

| Window | When | What happens | Intermission? |
|---|---|---|---|
| Fault-driven restart | Whenever the watchdog calls it | OBS + services restart (deployment-runbook §4.4) | Yes — the card, ~2–3 minutes |
| Sunday maintenance | Sunday, low-viewership hour | macOS updates, model pulls, cache rebuilds, review action items | Yes — the card, capped at 15 minutes |
| Ad-hoc (rare) | Only when something must change now | Whatever it is | Yes — the card, with the reason in plain language |
| Emergency (crash, power cut) | Unplanned | Auto-recovery (deployment-runbook §4) | No — recovery is not maintenance; the stream resumes as fast as possible, no card |

---

## 10. Build order and verification (the ship gate)

Build in this order. Each step is independently testable, and a step that fails stops the line — do not stack untested steps.

| # | Step | Pass criteria |
|---|---|---|
| 1 | Measure the box at idle | macOS + system resident memory recorded. If it is over 2 GB, find out why before anything else starts. |
| 2 | Install mlx-lm, pull Qwen3.5-4B-4bit | `mlx_lm.server` answers on localhost:8080; a test prompt returns a completion. |
| 3 | Verify the 2K context cap | The server runs with `--prompt-cache-size 1 --max-tokens 120` (verified on the box 2026-11-13, mlx-lm 0.32.2 — `--max-kv-size` does not exist in the 0.32.x server). Memory with the model loaded is recorded. |
| 4 | Run the 20 audition lines | The 10 host + 10 color lines from commentary-prompts §8, through the MLX server, temperature 0.7, max 120 tokens. Every line ≤280 chars, no invented numbers, no banned words. |
| 5 | Wire the commentary service to MLX | One full round, headless, events → prompts → MLX → validation → normalizer → cache. Drop rate < 5%, P99 generation < 5 s. |
| 6 | Install Kokoro (native first) | Kokoro answers on localhost:8880; the two voices render the audition lines; cache hit/miss works. If native fails, Docker with `--memory=1g`, and the budget table (§4) is corrected to the Docker numbers. |
| 7 | Install Ollama + the fallback model | `ollama pull qwen3:1.7b`, served with `num_ctx 2048`. Kill the MLX server mid-round: the commentary service must fall back to Ollama automatically and log the switch. |
| 8 | Full-round soak, 24 hours | Stream live, commentary on, all processes running. Peak memory (worst minute) recorded; swap must stay at zero; dropped frames < 1%. This is the measurement the 4B decision (§4.4) is made from. |
| 9 | Failure drills | MLX down, Kokoro down, both down, swap pressure simulated, a line queued at `shot_start`. Each must produce the §8 response, and each must be logged. |
| 10 | Intermission drill | Trigger a planned intermission: card shows, countdown runs, a trivial update applies, watchdog verifies, stream auto-resumes with the "we're back" line. Then deferral: schedule an intermission during a 59 Watch `on_the_line` moment and confirm it waits for the hole boundary. |
| 11 | 7-day soak (the go-live gate) | The QA plan's soak criteria (qa-plan.md §2) with the model stack included: flat GPU memory, flat heap, event-bus sequence continuity, overlay freshness ≤1–2 s, commentary drop rate < 5%, zero unplanned silences longer than one hole. |

**The 4B decision** is made from step 8's measurements, per §4.4, and written into `models.yaml` with a comment recording the measured peak. It is not revisited until the GPU box arrives.

---

## 11. Sources (checked Nov 12, 2026)

- MLX vs llama.cpp speed and memory, Ollama MLX backend 32GB requirement, Q4_K_M as the sweet spot: https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide
- mlx-lm vs Ollama vs llama.cpp measured on Mac Studio (Qwen3.5 9B: mlx-lm 107.5 tok/s at 5.24 GB peak, Ollama GGUF 77.7 tok/s at 15 GB, Ollama MLX 90.5 tok/s at 9 GB): https://terminalbytes.com/ollama-vs-llama-cpp-vs-mlx-mac-2026/
- Apple Silicon runtime comparison, MLX 20–55% faster than llama.cpp under 30B: https://localmodel.run/tools
- Qwen3 sizes and memory (0.6B ~0.5 GB, 1.7B ~1.4 GB, 4B ~2.5 GB at Q4_K_M; 8GB unified memory fits 0.6B Q8_0 at 4K or 1.7B Q4 at short context; 4B Q4 exceeds an 8GB budget under a 20% safety allowance): https://localllmguide.com/guides/local-llm-ram-vram-requirements
- Qwen3 family, Ollama tags, Apache 2.0: https://www.spheron.network/blog/run-qwen3-locally-gpu-requirements-2026/ and https://microaione.com/en/tutorials/qwen-local-deployment-en/
- Llama 3.2 3B measured (Q4_K_M 2.02 GB, ~3.5 GB at 4K ctx, 55.6 tok/s on M3 Pro 18GB) and 1B tags: https://localaimaster.com/models/llama-3-2-3b
- Phi-4-mini measured (Q4_K_M 2.5 GB file, 4.5 GB at 8K, 7.7 GB at 32K, 43.7 tok/s on M3 Pro; 128 KB KV cache per token): https://www.thinkfacility.com/run-locally/more/
- Gemma 3 sizes (1B 806 MB, 4B 3.4 GB) and the half-RAM rule of thumb: http://dev.to/veloxadev/which-ollama-model-fits-a-cpu-only-server-a-ram-sizing-cheat-sheet-3060
- 8GB machines fit 3B-class models; Q4_K_M the 2026 default: https://www.misar.blog/@synor/articles/run-local-llm-on-laptop
- Kokoro benchmarks, CPU speed, FP16/INT8 sizes, and voice table: see `docs/voice-options.md` §9 (sources checked Nov 12, 2026).
- Ollama's 262K default context loading 15 GB for a 6.6 GB model: https://terminalbytes.com/ollama-vs-llama-cpp-vs-mlx-mac-2026/
