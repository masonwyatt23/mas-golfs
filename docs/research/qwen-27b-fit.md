# Does a "Qwen 27B" exist — and could it run on the 8GB MacBook Pro?

**Research date:** Nov 12, 2026
**Question from Mason:** "maybe consider using Qwen 3.8 and I don't know if the 27B would fit on it but we probably have a distilled model" — i.e. is there a Qwen 27B, would it fit on the 8GB MacBook Pro broadcast box, and is there a distilled route to the best model we can run?

## TL;DR

- **Yes, a Qwen 27B exists — three of them.** Qwen3.5-27B (Feb 2026), Qwen3.6-27B (Apr 2026), and Qwen3.8-27B (Aug 2026). The newest, Qwen3.8-27B, is the current best single-GPU Qwen: dense 27B, vision-language, 262K context, Apache 2.0.
- **No, it cannot run on the 8GB MacBook Pro. Not close.** Its smallest usable build (MLX 4-bit) is ~16 GB of weights alone — twice the machine's entire memory. The broadcast stack already uses ~5.9 GB of the 8 GB, leaving ~2.1 GB free.
- **It cannot run on the 16GB MacBook Air either** (verified by testing: it never loads), and a 24GB Mac is tight. 32GB is the comfortable floor.
- **The "distilled model" idea is real — and it is already how Qwen builds its small models.** Qwen3's 0.6B–14B models were distilled from the 32B/235B teachers. The high-leverage move for this project is the same pattern in miniature: use Qwen3.8-27B as a *teacher* on a rented GPU to distill a small student (Qwen3-1.7B/4B) that runs on the 8GB box.
- **Best model that fits the 8GB box today: Qwen3-4B** (2.5 GB), with Qwen3-1.7B (~2.0 GB) as the safe default. Qwen3-8B (5.2 GB) loads on an 8GB Mac only with nothing else running — not alongside the broadcast stack.

---

## 1. Does a "Qwen 27B" exist?

Yes. Three generations of Qwen have shipped a dense 27B model. Note the naming trap: **"Qwen3-8B"** (an 8-billion-parameter model from the Qwen3 generation) and **"Qwen3.8-27B"** (a 27-billion-parameter model from the Qwen3.8 generation) are different things.

| Model | Released | Parameters | Context | License | Ollama tag |
|---|---|---|---|---|---|
| Qwen3.5-27B | Feb 2026 | 27B dense | 262K | Apache 2.0 | `qwen3.5:27b` |
| Qwen3.6-27B | Apr 2026 | 27B dense | 262K | Apache 2.0 | `qwen3.6:27b` |
| **Qwen3.8-27B** | **Aug 14, 2026** | **27B dense (27.78B measured)** | **262K** | **Apache 2.0** | **`qwen3.8:27b`** |

For comparison, the generations *before* Qwen3.5 had no 27B at all:

- **Qwen3 (Apr 2025):** dense 0.6B, 1.7B, 4B, 8B, 14B, 32B + MoE 30B-A3B, 235B-A22B. No 27B.
- **Qwen2.5 (2024):** 0.5B, 1.5B, 3B, 7B, 14B, 32B, 72B. No 27B — the nearest size is 32B.

Qwen3.8-27B is the one that matters. Per its model card (via the sources below): a dense vision-language model — text, image, and video input — 64 layers, hidden size 5,120, thinking mode on by default, 262,144-token native context, Apache 2.0. It is described as the best single-GPU Qwen available in November 2026, and its Ollama download is 18 GB (Q4_K_M weights plus a 0.9 GB vision projector).

One architecture detail that matters for the memory math: only 16 of its 64 layers are attention layers with a growing KV cache. The other 48 are Gated DeltaNet layers with a fixed-size state (~154 MB per sequence). That makes its KV cache unusually small for a 27B model — but the weights are still the problem.

**Related 27B, not Qwen:** Google's Gemma 3 27B (Mar 2025, 27.4B params, 128K context) is the other well-known ~27B open model. Its memory numbers are nearly identical to Qwen3.8-27B's and are used below as a cross-check. Its licence is the custom Gemma Terms of Use, not Apache 2.0.

---

## 2. The memory math for a ~27B model

Weights dominate. The formula is simple: **weights = parameters × bytes per parameter**, plus KV cache, plus runtime overhead. A 27.78B-parameter model:

### Weights by quantization (Qwen3.8-27B, verified builds)

| Quantization | Weights | What it is |
|---|---|---|
| BF16 (full precision) | ~54.7 GB | Raw checkpoint |
| Official FP8 checkpoint | ~28.75 GiB | Alibaba's own FP8 release |
| MLX 8-bit | 29.5 GB | `mlx-community/Qwen3.8-27B-8bit` |
| **MLX 4-bit** | **~16.05 GB** | **`mlx-community/Qwen3.8-27B-4bit` — the smallest MLX build** |
| GGUF Q4_K_M | ~17.8 GB file | Ollama download 18 GB incl. vision projector |
| MLX 5-bit / 6-bit | 19.4 / 22.8 GB | LM Studio community builds |

Notes:
- 4-bit is not 0.5 bytes/param in practice. Scales, zero-points, and the vision encoder + embeddings (which stay in BF16) push Q4_K_M to ~0.60 bytes/param, and the MLX 4-bit build to ~16 GB rather than the naive ~13.9 GB.
- **There is no 2-bit or 3-bit MLX build of Qwen3.8-27B.** Only 4-bit and 8-bit exist on `mlx-community`. A hypothetical 2-bit build would have to be produced and validated by hand.
- The vision tower is included in the MLX builds (they are built with `mlx-vlm`), which is why the file is bigger than a text-only 27B would be.

### KV cache (Qwen3.8-27B, from config.json)

Only the 16 attention layers grow a cache: 16 layers × 4 KV heads × 256 dims × 2 (K and V) × 2 bytes = **64 KiB per token at FP16**.

| Context | KV cache (FP16) |
|---|---|
| 2K tokens (our commentary prompts) | ~0.13 GB |
| 8K tokens | ~0.5 GB |
| 32K tokens | ~2 GB |
| 262K tokens (full window) | ~16 GB |

The DeltaNet layers add a fixed ~154 MB per sequence regardless of length. Our use case (short commentary prompts, ~2K context) keeps the cache small — this is the one part of the math that works in our favour.

### Total loaded memory (weights + cache + runtime)

| Quantization | Total at 8K context | Total at 32K context | Hardware that fits it |
|---|---|---|---|
| Q4_K_M / MLX 4-bit | **~18–19 GB** | ~20–21 GB | 24 GB GPU/Mac (tight); 32 GB comfortable |
| Q8_0 / MLX 8-bit | ~31–32 GB | ~33–34 GB | 48 GB |
| FP8 | ~30 GB | ~32 GB | 32–48 GB |
| BF16 | ~57 GB | ~59 GB | 80 GB datacentre GPU |

Cross-check with Gemma 3 27B (same size class): Q4_K_M 18.1–18.2 GB at 8K context, Q8 ~31–32 GB, BF16 ~57–59 GB — the same numbers, independently computed.

---

## 3. Could it run on the 8GB MacBook Pro?

**No. The arithmetic is not close.**

The broadcast box is an 8GB MacBook Pro (Apple Silicon, unified memory). The project's own budget in `docs/local-models.md` accounts for the running stack as:

| Process | Memory |
|---|---|
| macOS | ~1.5 GB |
| OBS | ~0.6 GB |
| Browser (web build) | ~0.9 GB |
| NodeCG | ~0.25 GB |
| Commentary service | ~0.15 GB |
| MLX server (Qwen3-1.7B) | ~2.0 GB |
| Kokoro TTS (native) | ~0.4 GB |
| **Total** | **~5.9 GB, leaving ~2.1 GB headroom** |

Against that, Qwen3.8-27B needs:

- **Weights alone at 4-bit: ~16 GB.** That is 2× the machine's entire physical memory, and ~7.6× the ~2.1 GB actually free.
- **Total loaded at 8K context: ~18–19 GB.** More than twice the machine.
- **Even a hypothetical 2-bit build** (~7–8 GB of weights) would exceed the whole machine before macOS, OBS, or a single KV-cache token — and no such build exists.

There is a second, less obvious wall on Apple Silicon: **macOS caps the GPU's wired allocation at roughly 75% of physical RAM by default.** On an 8GB machine that is ~6 GiB. The model has to fit under that ceiling, not under 8 GB. The 4-bit weights (14.97 GiB measured) sit far above it.

**The 16GB MacBook Air cannot run it either.** This was tested, not theorised: on a 16GB MacBook Air the 4-bit MLX build (16.1 GB file = 14.97 GiB) never loads, because the ~12 GiB GPU cap sits below the model size. The file is smaller than the RAM and it still does not work. (The Air is grandpa's computer and off-limits for this project regardless — see `docs/deployment-runbook.md`.)

**What does run it:**

| Machine | Verdict |
|---|---|
| 8GB MacBook Pro (our box) | No — needs ~18 GB, has ~2 GB free |
| 16GB MacBook Air | No — verified: never loads (12 GiB GPU cap) |
| 24GB Mac | Tight — ~19–20 GB free after macOS; workable at Q4 with a short context |
| 32GB Mac | Yes — the comfortable floor for Q4 |
| 48GB+ Mac / RTX 4090 24GB | Yes — 4090 runs it at Q4 at ~60 tok/s ceiling |
| RTX 5090 32GB | Yes — Q4 comfortably, Q8 tight |

---

## 4. What actually fits on the 8GB box

The largest Qwen that can run on an 8GB Mac, and what it costs in the stack:

| Model | Download (Q4) | Loads on 8GB Mac? | Loads alongside the broadcast stack? |
|---|---|---|---|
| Qwen3-0.6B | 0.5 GB | Yes | Yes |
| Qwen3-1.7B | 1.4 GB | Yes | **Yes — current default (~2.0 GB in MLX)** |
| Qwen3-4B | 2.5 GB | Yes | **Yes — the stretch goal, decided by measurement** |
| Qwen3.5-9B | 6.6 GB | Barely, alone | No |
| Qwen3-8B | 5.2 GB | Yes, alone (8–10 GB needed) | **No — 5.2 + ~3.9 GB of stack = ~9.1 GB > 8 GB** |
| Qwen3-14B | 9.3 GB | No | No |
| Qwen3.8-27B | 18 GB | No | No |
| Qwen3-32B | 20 GB | No | No |
| Qwen3-30B-A3B (MoE) | 18.6 GB | No | No — only 3B active per token, but all 30B must be resident |

So the honest ladder on this box is: **Qwen3-1.7B today, Qwen3-4B if the 24-hour soak proves the headroom, and nothing bigger without new hardware.** Qwen3-8B is the largest Qwen that loads on an 8GB Mac at all — but only with nothing else running, which is not our situation.

One nuance worth knowing: Qwen3-8B is not a weak model. Per Qwen's own scaling table, Qwen3-8B performs like a Qwen2.5-14B, and Qwen3-4B like a Qwen2.5-7B. The small models punch above their size (see §5 for why).

---

## 5. Distilled models — the idea is already real

Mason's instinct — "we probably have a distilled model" — is correct, and it is how the Qwen family itself is built.

**Qwen3's small models are distilled from its large ones.** Per the Qwen3 technical report (May 2025): the 0.6B–14B dense models (and the 30B-A3B MoE) were built by **strong-to-weak distillation** from Qwen3-32B and Qwen3-235B-A22B, in two phases — off-policy distillation (the student trains on teacher responses) followed by on-policy distillation (the student generates its own responses, and the teacher's token distribution is the KL-divergence target). Only the 32B and 235B flagships got the full four-stage SFT+RL pipeline. The reported result on Qwen3-8B: distillation reached **74.4 on AIME'24 in 1,800 GPU-hours**, while reinforcement learning from the same starting point reached 67.6 in 17,920 GPU-hours — better score at roughly a tenth of the compute.

The pattern is industry-wide, not Qwen-specific: Gemma 3 distilled every size from a larger teacher; Llama 3.2 1B/3B were pruned from Llama 3.1 8B with 8B/70B logits as targets; DeepSeek published R1 distillations at 1.5B, 7B, 8B, 14B, 32B, and 70B.

**What this means for Mas Golfs:** the best model we can run is not necessarily the biggest model we can *load*. It is the best *distilled* small model — and Qwen's own small models already are that. The next step beyond them is a **custom distillation for our exact job**: use Qwen3.8-27B as a teacher on a rented GPU to generate thousands of golf-commentary lines (Nantz-style host lines, Gruden-style colour lines, 59 Watch moments, decision breakdowns), then fine-tune Qwen3-1.7B or Qwen3-4B on those outputs. That is legal under Apache 2.0 (both teacher and student are open weights) — unlike distilling from a hosted API model, whose terms of service forbid training on outputs. The student stays ~2 GB, runs on the 8GB box, and sounds like it was written by the 27B.

This is exactly the fine-tuning path gated in `docs/local-models.md` §7 (90 days of logs, a demonstrated gap prompts cannot close, a GPU box to train on, an A/B win) — the teacher makes the gap closable.

---

## 6. The realistic paths to a bigger model

| Path | What it gets you | Cost | When |
|---|---|---|---|
| **A. Stay on the 8GB box** | Qwen3-1.7B now, Qwen3-4B if the soak proves it | $0 | Now |
| **B. Custom distillation (teacher → student)** | A 1.7B/4B student that writes like the 27B teacher, on the same box | GPU rental for the teacher run only (~tens of dollars) | After 90 days of event logs (per the local-models gating) |
| **C. Rent a cloud GPU** | Qwen3.8-27B at Q4, live, ~60 tok/s ceiling on an RTX 4090 | RunPod Community RTX 4090 ~$0.34/hr (~$248/mo at 24/7) | When the show needs the big voice live |
| **D. Own an RTX 4090 box** | Qwen3.8-27B at Q4 (and Qwen3-32B) locally, plus the Unreal build | ~$2,500–3,000 one-time + ~$35–52/mo power | The Unreal upgrade (see `docs/unreal-vertical-slice.md`) |
| **E. Bigger Mac** | 32GB Mac runs Qwen3.8-27B at Q4 comfortably | A new machine | Only if the show outgrows the 8GB box before the GPU box |

Note on path C/D and the project's free-tier rule: the 27B does not fit the "completely free" constraint on the 8GB box, and renting a GPU is the first thing in this project that costs real money per month. That is a decision for Mason, not a default. Paths A and B keep the $0/month rule intact.

Also worth knowing for path D: the MoE alternative Qwen3-30B-A3B (18.6 GB at Q4) only activates 3B per token, so it generates faster than its size suggests — but all 30B must still be resident in memory, so it needs the same 24GB-class hardware as the 27B.

---

## 7. Recommendation for Mas Golfs

1. **Now:** keep Qwen3-1.7B as the commentary LLM on the 8GB box, with Qwen3-4B as the measured stretch goal. Both are already distilled from Qwen's biggest teachers — we are already running a distilled model.
2. **Next (no new hardware):** plan the custom distillation — Qwen3.8-27B as teacher, Qwen3-4B as student, trained on our own commentary corpus once 90 days of event logs exist. That is the highest-leverage way to get 27B-quality writing onto an 8GB box.
3. **Later (when the GPU box arrives for Unreal):** run Qwen3.8-27B at Q4 on the RTX 4090 for the live commentary, and keep the distilled student as the fallback. The box is bought for Unreal; the model upgrade rides along for free.
4. **Do not chase the 27B onto the 8GB box.** There is no quantization, runtime flag, or context trick that makes 16 GB of weights fit in ~2 GB of free memory. The 16GB Air proves the point: even double the RAM is not enough.

---

## Sources

- Qwen3.8-27B release and specs: https://localaimaster.com/blog/qwen-3-local-setup-guide?trk=article-ssr-frontend-pulse_little-text-block (updated Nov 2, 2026; Ollama tags and download sizes re-read from the registry)
- Qwen version history incl. Qwen3.8-27B (Aug 14, 2026) and Qwen3.5-27B: https://mungomash.com/ai/qwen/versions/
- Qwen family sizes and hardware (Qwen3 0.6B–32B, 30B-A3B, 235B-A22B): https://llmshed.com/models/qwen/ and https://cache.directory/local-llm/ollama-qwen3/
- Qwen3.8-27B memory envelope, MLX builds, Apple Silicon: https://tryginger.ai/blog/qwen-38-27b-hardware-requirements-and-how-to-deploy-locally
- Qwen3.8-27B config.json memory math (64 KiB/token KV, 154 MB DeltaNet state), MLX 4-bit 16.05 GB: https://rohitghumare.com/guides/qwen3-8-27b/
- Qwen3.8-27B will not run on a 16GB MacBook (GPU cap ~75%, tested on a 16GB Air): https://www.baseload.co.kr/en/blog/2026-08-16-qwen3-8-27b-macbook-16gb-reality-check/
- Qwen3.8-27B on 24GB Mac/GPU, MLX 4-bit ~15 GiB: https://modelfit.io/blog/run-qwen38-27b-locally-2026/
- Qwen2.5-32B memory at Q4_K_M (21 GB loaded at 4K, 28.6 GB at 32K) and KV-cache math: https://agentinfraguide.com/models/qwen25-coder/hardware-requirements and https://llmrun.dev/model/qwen-qwen2-5-coder-32b
- VRAM calculator (weights + KV cache + overhead formulas): https://www.standaard.tech/llm-vram-calculator
- Gemma 3 27B memory (Q4 18.1–18.2 GB, Q8 ~31–34 GB, BF16 ~57–67 GB): https://llmhardware.io/guides/gemma3-hardware-requirements, https://nodegrove.io/models/gemma-3-27b, https://projectcozy.me/blog/gemma-3-27b-it-guide
- Qwen3 strong-to-weak distillation (0.6B–14B distilled from 32B/235B-A22B; 8B AIME'24 74.4 at 1,800 GPU-hours vs RL 67.6 at 17,920): https://loom.chanvichetvong.com/papers/qwen-3 and https://github.com/eb1386/syntheticscaling/blob/HEAD/docs/08_teacher_selection.md
- Distillation background (Gemma, Llama, DeepSeek-R1 distills, on-policy distillation): https://www.howaiworks.dev/distillation/

Related project docs: `docs/local-models.md` (MLX-first architecture, 8GB budget, fine-tuning gates), `docs/deployment-runbook.md` (8GB MacBook Pro broadcast box; 16GB Air off-limits), `docs/unreal-vertical-slice.md` (GPU box costs), `docs/commentary-prompts.md` (the prompts the LLM runs).
