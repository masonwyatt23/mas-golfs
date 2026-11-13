# Best small LLMs for real-time broadcast commentary on Apple Silicon

**Research date:** Nov 12, 2026
**Use case:** Mas Golfs — autonomous golf broadcast. One commentary LLM, resident on the broadcast box (an 8GB MacBook Pro, Apple Silicon), generating one-line commentary from tight prompts: a decision line before the shot, a result line at landing, 59 Watch moments, milestones. Typical output: 20–40 tokens, event-driven, a few calls per minute at most. MLX-first runtime (see `docs/local-models.md`).
**Companion research:** `docs/research/qwen-27b-fit.md` answers the 27B question in depth (does a Qwen 27B exist, does it fit, and the distillation route). This document covers the full field and the ranked recommendation; it does not repeat the 27B memory math.

---

## 0. The job, precisely

Commentary generation for this broadcast is not a general chatbot workload. The constraints are narrow, and they decide the ranking:

- **Short outputs only.** 20–40 tokens per line, hard-capped at 40–60 tokens. A model that is slow at 500 tokens is irrelevant; what matters is time-to-first-token (TTFT) plus ~30 tokens of decode.
- **Strict instruction following.** Every line must obey a format (one idea, no hype words, numbers only from the event data, never mention the machine). IFEval is the closest public proxy, and it matters more than MMLU here.
- **No thinking traces.** The model must answer directly. Any model that emits a chain-of-thought first is disqualified for the live path, whatever its benchmark scores.
- **One resident model, ever.** The 8GB budget in `docs/local-models.md` allows one LLM (~2.0 GB). A second resident model is a memory decision, not a feature decision.
- **Commercial use.** The broadcast is a commercial product. Licences matter: Apache 2.0 / MIT are clean; custom terms (Gemma, Llama) are usable but carry strings.

## 1. The box and the physics

### 1.1 Decode is bandwidth-bound

LLM token generation at batch size 1 reads every weight from memory once per token. The ceiling is a simple formula:

**max tok/s ≈ memory bandwidth ÷ model size in memory** (real-world 60–80% of theoretical)

| Chip | Bandwidth | 4B Q4 (~2.5 GB) | 8B Q4 (~4.6 GB) | 14B Q4 (~8 GB) | 32B Q4 (~18 GB) |
|---|---|---|---|---|---|
| M1 base | 68 GB/s | ~16–22 tok/s | ~9–12 tok/s | ~5–7 tok/s | ~2–3 tok/s |
| M2 / M3 base | 100 GB/s | ~24–32 tok/s | ~13–17 tok/s | ~7–10 tok/s | ~3–4 tok/s |
| M4 base | 120 GB/s | ~29–38 tok/s | ~16–21 tok/s | ~9–12 tok/s | ~4–5 tok/s |
| M4 Pro | 273 GB/s | ~65–87 tok/s | ~36–47 tok/s | ~20–27 tok/s | ~9–12 tok/s |
| M4 Max | 546 GB/s | ~130–175 tok/s | ~71–95 tok/s | ~41–55 tok/s | ~18–24 tok/s |

Sources: https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide ; https://specpicks.com/reviews/run-llama-3-1-8b-on-m4

Practical reading: on a base M4, a 4B model gives a 30-token line in ~1 s; an 8B model in ~1.5–2 s. Both are fast enough for commentary (the ball is in the air longer than that). The binding constraint on 8GB is **memory, not speed**.

### 1.2 The 8GB memory budget

From `docs/local-models.md`: macOS ~1.5 GB, OBS ~0.6 GB, browser ~0.9 GB, NodeCG ~0.25 GB, commentary service ~0.15 GB, Kokoro TTS (native) ~0.4 GB — **~3.9 GB before the LLM, leaving ~2.1 GB free, ~4.1 GB if the stack is squeezed**. That makes the comfortable ceiling a ~2–2.5 GB model, with ~3 GB possible only if the soak proves the headroom.

### 1.3 MLX is the runtime — and it requires Apple Silicon

MLX is 15–30% faster than llama.cpp on dense models under ~30B, widening to ~2× on MoE models; the advantage collapses above ~27–30B where both hit the bandwidth ceiling. Measured head-to-head (decode, 4-bit): M4 Max Qwen3-8B — MLX 93.3 vs llama.cpp 76.9 tok/s (+21%); Qwen3-4B — 159.0 vs 118.2 (+35%); Qwen3-0.6B — 525.5 vs 281.5 (+87%). Ollama's MLX backend (v0.19+, auto-activates only on 32GB+ Macs) reaches ~85% of pure-MLX throughput — so on this 8GB box the MLX path is `mlx-lm` directly, not Ollama.

Two MLX caveats: it does full prefill before emitting any token, so TTFT grows with prompt length (keep prompts short — ours are); and it has no layer-splitting equivalent to llama.cpp's CPU offload — if a model does not fit in unified memory, it does not run.

**First verification step before anything else: confirm the 8GB MacBook Pro is Apple Silicon.** MLX does not run on Intel Macs. If the box is Intel, the entire MLX plan fails and the fallback is llama.cpp on CPU at a fraction of the speed. Check `About This Mac → Chip`. **CONFIRMED Nov 12, 2026 (Mason): the 8GB MacBook Pro is Apple Silicon. The MLX plan stands; the Intel fallback is not needed.**

Sources: https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide ; https://localmodel.run/tools ; https://llmcheck.net/guides/mlx-framework-apple-silicon/

---

## 2. The comparison

| Model | Params | 4-bit size | MLX repo | Fits 8GB + stack? | Decode, base chip (est.) | IFEval | Licence |
|---|---|---|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507** | 4B | ~2.3 GB | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | ✅ Yes | ~30–60 tok/s | 81.9 (non-thinking, tech report) | Apache 2.0 |
| **Gemma 3 4B IT QAT** | 4.3B | ~3.0–3.2 GB | `mlx-community/gemma-3-4b-it-qat-4bit` | ✅ Yes, tight | ~40–85 tok/s | 90.2 (Google) / ~65–80 (independent) | Gemma Terms (custom) |
| **Qwen3-8B** | 8.2B | ~4.6 GB | `mlx-community/Qwen3-8B-4bit` | ⚠️ Alone only | ~16–24 tok/s | 85.0 (non-thinking) | Apache 2.0 |
| **Llama 3.2 3B Instruct** | 3B | ~1.8–2.0 GB | `mlx-community/Llama-3.2-3B-Instruct-4bit` | ✅ Yes | ~25–55 tok/s | 77.4 | Llama Community Licence |
| **Phi-4-mini-instruct** | 3.8B | ~2.2 GB | `mlx-community/Phi-4-mini-instruct-4bit` | ✅ Yes | ~15–20 tok/s (M1) / ~68 (M3 Max) | 0.50 measured on 4-bit artifact | MIT |
| Qwen3-1.7B | 1.7B | ~1.0–1.4 GB | `mlx-community/Qwen3-1.7B-4bit` | ✅ Yes, easily | ~60–120 tok/s | Weak | Apache 2.0 |
| Gemma 3 1B / Llama 3.2 1B | 1B | ~0.7–0.8 GB | `mlx-community/gemma-3-1b-it-4bit` / `mlx-community/Llama-3.2-1B-Instruct-4bit` | ✅ Yes | ~60–150+ tok/s | 59.5 (Llama 1B) / 80.2 (Gemma 1B, Google) | Gemma Terms / Llama Licence |
| Gemma 3 12B | 12B | ~7–8.5 GB | `mlx-community/gemma-3-12b-it-4bit` | ❌ No | — | 88.9 (Google) / 0.82 measured | Gemma Terms |
| Qwen3-14B | 14B | ~8.0 GB | `mlx-community/Qwen3-14B-4bit` | ❌ No | — | — | Apache 2.0 |
| Qwen3-32B | 32.8B | ~17.4–18.5 GB | `mlx-community/Qwen3-32B-4bit` | ❌ No | — | — | Apache 2.0 |
| Qwen3.8-27B | 27.8B | ~16.0 GB | `mlx-community/Qwen3.8-27B-4bit` | ❌ No | — | — | Apache 2.0 |
| Mistral Small 3.2 24B | 24B | ~13.9–14.3 GB | `mlx-community/Mistral-Small-3.2-24B-Instruct-2506-4bit` | ❌ No | ~6 tok/s measured MLX (M3 Max) | 0.65 measured | Apache 2.0 |
| Llama 4 Scout | 109B total | ~61–66 GB | `mlx-community/Llama-4-Scout-17B-16E-Instruct-4bit` | ❌ No | — | — | Llama 4 Licence + EU exclusion |
| Llama 4 Maverick | 400B total | ~224–243 GB | `mlx-community/Llama-4-Maverick-17B-128E-Instruct-4bit` | ❌ No | — | — | Llama 4 Licence + EU exclusion |
| DeepSeek-R1-Distill-Qwen-7B/14B/32B | 7B/14B/32B | ~4.7 / ~9 / ~20 GB | `mlx-community/DeepSeek-R1-Distill-Qwen-*-4bit` | 7B only, but ❌ wrong tool | — | — | MIT + Apache 2.0 |

Speeds are single-stream decode estimates for base M1/M2/M3/M4 chips unless stated; high-end-chip figures are much higher and are given in the per-family sections. Benchmark scores are full precision unless stated; 4-bit costs a few points, QAT less than plain post-training quantisation. IFEval methodology differs between vendors — do not treat Google's 90.2 vs Meta's 77.4 as a like-for-like 13-point lead.

---

## 3. Qwen3 — the family to bet on

### 3.1 Sizes, memory, MLX

Qwen3 dense models: 0.6B, 1.7B, 4B, 8B, 14B, 32B, plus 30B-A3B / 235B-A22B MoE. Context 32K native (128K with YaRN) for 4B and up. All Apache 2.0, commercial use allowed.

| Model | 4-bit footprint | MLX repo |
|---|---|---|
| Qwen3-0.6B | ~0.5 GB | `mlx-community/Qwen3-0.6B-4bit` |
| Qwen3-1.7B | ~1.0–1.4 GB | `mlx-community/Qwen3-1.7B-4bit`; official `Qwen/Qwen3-1.7B-MLX-4bit` |
| Qwen3-4B | ~2.3–2.5 GB file; peak memory measured 2.89–3.24 GB | `mlx-community/Qwen3-4B-4bit`; `mlx-community/Qwen3-4B-Instruct-2507-4bit` (~2.27 GB); official `Qwen/Qwen3-4B-MLX-4bit` |
| Qwen3-8B | ~4.6 GB | `mlx-community/Qwen3-8B-4bit`; official `Qwen/Qwen3-8B-MLX-4bit` |
| Qwen3-32B | ~17.4–18.5 GB | `mlx-community/Qwen3-32B-4bit` |

Sources: https://huggingface.co/Qwen/Qwen3-8B ; https://huggingface.co/Qwen/Qwen3-32B ; https://arxiv.org/pdf/arXiv:2505.09388 ; https://github.com/travis-ml/mlx-benchmark/blob/HEAD/README.md

**Variant warning — the most important detail in this document.** The original `Qwen/Qwen3-*` checkpoints are hybrid thinking/non-thinking in one model, and thinking is **on by default**. The later `Qwen3-*-Instruct-2507` / `Thinking-2507` splits are separate: Instruct-2507 is non-thinking only and does not emit `<think>` blocks. For broadcast, use an Instruct-2507 model, or set `enable_thinking=False` / append `/no_think`. Recommended sampling for non-thinking mode (from the HF card): Temperature 0.7, TopP 0.8, TopK 20, never greedy.

### 3.2 Quality

Qwen3 Technical Report, non-thinking mode (Table 18): **IFEval (strict prompt): Qwen3-4B 81.9, Qwen3-8B 85.0** — vs DeepSeek-R1-Distill-Qwen-14B 72.6 / 32B 72.5 on the same table. Creative Writing v3: 4B 61.1, 8B 75.0. MMLU-Redux (non-thinking): 4B 83.7, 8B 87.5. The report states the 0.6B/1.7B/4B/8B models "outperform baselines even with more parameters, including our previous Qwen2.5 models, in either the thinking or the non-thinking mode."

Practical reading: **0.6B/1.7B** — only for templated, very short lines; weak, error-prone, not a credible live voice. **4B** — the minimum credible live model on 8GB; good instruction-following for its size. **8B** — the sweet spot for quality/speed on 16GB+; on 8GB it loads alone but not alongside the broadcast stack. **32B** — best creative writing in the family, irrelevant on 8GB hardware.

Source: https://arxiv.org/pdf/arXiv:2505.09388

### 3.3 Speed on Apple Silicon

Measured (MLX, Groundy benchmarks, M4 Max 128 GB): Qwen3-0.6B 525.5 tok/s; Qwen3-4B 159.0 tok/s; Qwen3-8B 93.3 tok/s. On a base M4 (~¼ the bandwidth), expect roughly 30–60 tok/s at 4B and ~16–24 tok/s at 8B. A 30-token line: ~0.5–1 s at 4B, ~1.5–2 s at 8B. Both are fast enough — the ball is in the air longer than that.

### 3.4 The newer generations — Qwen3.5 / Qwen3.6 / Qwen3.8

Qwen has since shipped Qwen3.5 (Feb 2026), Qwen3.6 (Apr 2026), and Qwen3.8 (Aug 2026), all Apache 2.0. The 27B sizes live in these generations (Qwen3.5-27B, Qwen3.6-27B, Qwen3.8-27B) — the original Qwen3 has no 27B; its dense sizes jump 14B → 32B. See `docs/research/qwen-27b-fit.md` for the full 27B analysis. For the small sizes, Qwen3.5-4B/8B-class models exist and may supersede Qwen3 for a new build — worth a verification pass before finalising the model pick, but Qwen3-4B-Instruct-2507 is the verified, available-now choice.

---

## 4. Gemma 3 — the strongest instruction-follower per byte

Gemma 3 4B is **4.3B parameters** including its vision encoder; 1B is text-only, 32K context; 4B/12B/27B are multimodal, 128K context.

| Model | MLX 4-bit file | Runtime at Q4 | Fits 8GB? |
|---|---|---|---|
| 1B | 0.77 GB | ~1–2 GB | ✅ Yes, easily |
| 4B | ~3.0 GB (QAT 4-bit) | ~3.2 GB | ✅ Yes (short/medium context) |
| 12B | ~7–8.5 GB | ~8.5 GB | ❌ No |
| 27B | ~17 GB | ~18 GB | ❌ No |

MLX: `mlx-community/gemma-3-1b-it-4bit`, `gemma-3-4b-it-4bit`, `gemma-3-12b-it-4bit`, plus `-8bit` and `-qat-4bit` variants. Prefer **QAT 4-bit** — quantisation-aware training measurably preserves quality at 4-bit vs plain post-training quantisation. Note: the 4B/12B MLX builds are vision-language models — use `mlx-vlm` for image input; text-only use without loading the vision encoder is supported, which saves memory.

Speed (MLX, M3 Max 36 GB, 4-bit): Gemma 3 4B QAT **63.0 tok/s**; 12B QAT 25.9 tok/s. On an 8GB base chip, expect roughly 40–80 tok/s for the 4B.

Quality (Google model card, full precision): MMLU 1B 38.8 / 4B 58.1 / 12B 71.9; GSM8K 1B 62.8 / 4B 89.2 / 12B 94.4; **IFEval 1B 80.2 / 4B 90.2 / 12B 88.9**. Measured on the actual 4-bit MLX artifacts (M3 Max, 40-item samples): Gemma 3 4B QAT GSM8K 0.72, IFEval 0.65, schema-following 1.00; 12B QAT GSM8K 0.88, IFEval 0.82. The 1B is weak on knowledge (MMLU 38.8, MMLU-Pro 14.7) — templated lines only.

**Licence — the catch.** Gemma 3 is under Google's custom **Gemma Terms of Use** + Prohibited Use Policy, not Apache 2.0/MIT. Commercial use is permitted (including self-hosting, fine-tuning, redistribution, charging), but: prohibited-use categories apply; **downstream flow-down** (distribute Gemma or a derivative and you must pass the use restrictions on as enforceable provisions); Google can restrict/terminate usage it reasonably believes violates the agreement. No revenue or MAU threshold. Note: **Gemma 4 (Apr 2026) is Apache 2.0** — clean commercial use with no custom clauses — but that does not retroactively apply to Gemma 3 checkpoints.

Sources: https://ai.google.dev/gemma/docs/core/model_card_3 ; https://huggingface.co/collections/mlx-community/gemma-3 ; https://github.com/nicoloboschi/localmaxxing ; https://wcr.legal/google-gemma-license-risks/

**Verdict:** Gemma 3 4B QAT is the strongest 4B-class instruction-follower on MLX and punches above its size. It is the challenger to Qwen3-4B, held back only by its custom licence and its slightly larger footprint (~3.2 GB vs ~2.3 GB).

---

## 5. Llama 3.2 — the safe fallback

| Model | MLX 4-bit file | Runtime | Fits 8GB? |
|---|---|---|---|
| 1B Instruct | ~0.69–0.77 GB | ~1.1–2.2 GB | ✅ Yes |
| 3B Instruct | ~1.79–1.8 GB | ~2.14–3.3 GB | ✅ Yes |

MLX: `mlx-community/Llama-3.2-1B-Instruct-4bit`, `mlx-community/Llama-3.2-3B-Instruct-4bit`. Speed: 3B ~72.3 tok/s on M4 Max (mlx-benchmark), 55.6 on M3 Pro 18 GB (Ollama), 25–35 on M2 Air 24 GB (mlx-lm) — expect roughly 25–55 tok/s on a base 8GB chip. A 40–80-token line takes ~1–3 s at 3B speed on a base chip.

Quality (Meta model card, bf16): MMLU 1B 49.3 / 3B **63.4**; GSM8K 1B 44.4 / 3B 77.7; **IFEval 1B 59.5 / 3B 77.4**. The 3B is a large step up from the 1B and has the best MMLU at 3B; the 1B is "fine for classification, short extraction, autocomplete… for anything that needs reasoning or reliable tool calls, use the 3B."

**Licence — Llama Community License.** Commercial use allowed, royalty-free, but it is Meta's own licence, not Apache/MIT: attribution ("Built with Meta Llama 3" / "Built with Llama") on products using it; derivatives distributed must keep the licence and be named starting with "Llama"; **>700M monthly active users** triggers a separate-licence requirement (irrelevant at this scale, but a hard clause); **no training other LLMs on its outputs** (Llama 3 §1.b.v — you will not use Llama materials or outputs to improve any other large language model, excluding Meta Llama 3 or derivatives — note this clause is **absent from the Llama 4 licence**); Acceptable Use Policy incorporated by reference.

Sources: https://huggingface.co/mlx-community/Llama-3.2-1B-Instruct-4bit ; https://github.com/travis-ml/mlx-benchmark/blob/HEAD/README.md ; https://openweightlicenses.com/commercial-use/llama

**Verdict:** Llama 3.2 3B is the safe fallback — strong general knowledge, cleanest small-model licence story after Apache/MIT, and the smallest footprint of the credible options. It loses to Qwen3-4B and Gemma 3 4B on instruction following.

---

## 6. Phi-4-mini — fast, but the instruction following is weak

3.8B params, dense, 128K context, trained on 5T tokens. **Licence: MIT — confirmed** on the model card. MLX: `mlx-community/Phi-4-mini-instruct-4bit`, ~2.18–2.5 GB download, measured peak RAM 2.37 GB on an M1 MacBook Air 16 GB. Speed (MLX, 4-bit): M3 Max 67.8 tok/s single-stream decode; M1 MacBook Air ~15–20 tok/s (TTFT 0.358 s, end-to-end 1.670 s for a ~32-token reply); M4 Max 167.4 tok/s.

Quality (Microsoft, full precision): MMLU 67.3, GSM8K 88.6, MATH 64.0, MMLU-Pro 52.8 — beats 7–8B models on math. **But measured on the actual 4-bit MLX artifact (M3 Max, 40-item samples): GSM8K 0.65, IFEval 0.50, JSON-schema following 1.00.** The IFEval 0.50 is weak vs peers (Qwen3.5-4B scored 0.80 / GSM8K 0.78 on the same rig) — a real caveat for strict instruction following. Microsoft also warns of limited factual-knowledge capacity at 3.8B.

Sources: https://huggingface.co/microsoft/Phi-4-mini-instruct ; https://arxiv.org/html/2503.01743 ; https://github.com/nicoloboschi/localmaxxing ; https://dev.to/gde/measuring-real-world-response-latency-on-16gb-apple-silicon-for-agent-workflows-24e5

**Verdict:** the fastest credible option on base chips and the only one with a genuinely MIT licence at this size — but the weakest instruction-follower of the credible options. A fast fallback, not the voice.

---

## 7. Ruled out

### 7.1 DeepSeek-R1-Distill — wrong tool for live commentary

R1-Distill-Qwen-7B/14B/32B (Qwen2.5 bases, not Qwen3) are reasoning specialists: they always emit a long `<think>` trace first. A 30-token line can cost hundreds–thousands of hidden tokens — **5–15× more tokens per query** than a non-reasoning model of the same size. They cannot be told to stop thinking (unlike Qwen3's `enable_thinking=False`), they leak `<think>` content unless stripped, and DeepSeek's own usage recommendation is to avoid a system prompt and force `<think>\n` at the start of every output — the opposite of what a tight live-commentary prompt wants. Official scores are strong on reasoning (R1-Distill-Qwen-14B: AIME 2024 69.7%, MATH-500 93.9%), but reasoning is not the job. Licence is MIT + Apache 2.0 (clean), and the 7B fits (~4.7 GB at 4-bit) — none of that matters, because the tool is wrong. Reserve R1-Distill for offline reasoning (e.g. pre-game analysis), never the live path.

Sources: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B ; https://www.canihost.com/models/deepseek-r1-distill-qwen-14b ; https://canitrun.dev/models/deepseek-r1-distill-qwen-32b/

### 7.2 Anything 14B and up — does not fit

- **Qwen3-14B** (~8.0 GB at Q4): weights alone equal the whole machine.
- **Mistral Small 3.2 24B** (~13.9–14.3 GB at 4-bit, ~16.3 GB loaded at 8K context): needs a 24GB Mac minimum, comfortable on 32GB+. And its MLX speed is suspect — measured **5.7 tok/s single-stream decode on M3 Max** via `mlx_lm.server`, far below bandwidth-based estimates (~13–17 tok/s on M4 Pro). Re-benchmark before ever committing. Apache 2.0, strong quality (MMLU 81.0, IFEval 0.65 measured), but irrelevant on this box.
- **Gemma 3 12B** (~7–8.5 GB at Q4): exceeds 8GB before OS/KV cache.
- **Qwen3-32B** (~17.4–18.5 GB), **Qwen3.8-27B** (~16.0 GB): ~2× the whole machine. Full analysis in `docs/research/qwen-27b-fit.md`.
- **Llama 4 Scout** (17B active / 109B total, ~61–66 GB at 4-bit) and **Maverick** (17B active / 400B total, ~224–243 GB): the MoE trap — only 17B are active per token, but all experts must be resident. Scout needs a 96GB Mac; Maverick a 512GB Mac Studio or cluster. Plus the Llama 4 licence's EU multimodal exclusion. Not remotely realistic here.

### 7.3 1B models as the voice — too weak

Llama 3.2 1B (IFEval 59.5, MMLU 49.3) and Gemma 3 1B (MMLU 38.8, MMLU-Pro 14.7) are fast (~60–150+ tok/s) but will hallucinate and over-edit under the tight format constraints. Keep a 1B only as a draft/fallback tier, never as the commentary voice.

---

## 8. Distillation — the high-leverage path (no new hardware)

The best model we can run is not necessarily the biggest model we can *load*. It is the best *distilled* small model — and Qwen's own small models already are that: Qwen3's 0.6B–14B models were built by strong-to-weak distillation from Qwen3-32B and Qwen3-235B-A22B (off-policy, then on-policy with the teacher's token distribution as the KL target). The reported result on Qwen3-8B: distillation reached 74.4 on AIME'24 in 1,800 GPU-hours, vs reinforcement learning reaching 67.6 in 17,920 GPU-hours — better score at roughly a tenth of the compute.

The next step beyond them is a **custom distillation for our exact job**: use Qwen3.8-27B as a teacher on a rented GPU to generate thousands of golf-commentary lines (Nantz-style host lines, Gruden-style colour lines, 59 Watch moments, decision breakdowns), then fine-tune Qwen3-1.7B or Qwen3-4B on those outputs. That is legal under Apache 2.0 (both teacher and student are open weights) — unlike distilling from a hosted API model, whose terms of service forbid training on outputs. The student stays ~2 GB, runs on the 8GB box, and sounds like it was written by the 27B.

This is exactly the fine-tuning path gated in `docs/local-models.md` §7 (90 days of logs, a demonstrated gap prompts cannot close, a GPU box to train on, an A/B win) — the teacher makes the gap closable. Cost is a GPU rental for the teacher run only (tens of dollars), and the $0/month rule stays intact.

Sources: https://loom.chanvichetvong.com/papers/qwen-3 ; `docs/research/qwen-27b-fit.md` §5–§7

---

## 9. What changes with a GPU box later

When the RTX 4090 box arrives for Unreal (see `docs/unreal-vertical-slice.md`), the model ceiling lifts completely — and the box is bought for Unreal, so the model upgrade rides along for free:

| Model | 4-bit size | On RTX 4090 (24GB) | Why |
|---|---|---|---|
| Qwen3.8-27B | ~16 GB | ✅ ~60 tok/s ceiling | Best single-GPU Qwen; the live voice |
| Qwen3-32B | ~18 GB | ✅ | Best creative writing in the Qwen3 family |
| Qwen3-30B-A3B (MoE) | ~18.6 GB | ✅ | Only 3B active per token — faster than its size suggests |
| Mistral Small 3.2 24B | ~14 GB | ✅ | Quality + function calling, if MLX/vLLM speed verifies |
| Gemma 3 12B / 27B | ~8.5 / ~18 GB | ✅ | 12B measured IFEval 0.82 on MLX artifact |
| DeepSeek-R1-Distill-14B | ~9 GB | ✅ | Offline reasoning only, still not the live voice |

Runtime also changes: vLLM/Ollama on CUDA replaces mlx-lm, speculative decoding becomes viable (a small draft model + large verifier nearly doubled throughput in one independent benchmark: 64 → 206 tok/s on a 26B model), and fine-tuning becomes possible on-box. The distilled student stays as the fallback — if the GPU box dies, the 8GB MacBook Pro keeps the show running on the student.

---

## 10. Ranked recommendation

### For the 8GB MacBook Pro, now

1. **Qwen3-4B-Instruct-2507, 4-bit MLX** — `mlx-community/Qwen3-4B-Instruct-2507-4bit` (~2.27 GB). **The pick.** Best balance of quality (IFEval 81.9), size, speed (~30–60 tok/s on a base M4 → a 30-token line in ~0.5–1 s), and licence (Apache 2.0, clean). Non-thinking by construction, so no `<think>` risk. *Caveat:* peak memory measured 2.89–3.24 GB — the 24-hour soak in the QA plan decides whether it holds headroom alongside the full stack; if it does not, drop to #4.
2. **Gemma 3 4B IT QAT, 4-bit MLX** — `mlx-community/gemma-3-4b-it-qat-4bit` (~3.0 GB). **The A/B challenger.** Strongest instruction-following per byte (IFEval 90.2 Google / ~65–80 independent; GSM8K 89.2) and fastest of the capable options. Held back only by its larger footprint and its custom Gemma Terms (commercial OK, but flow-down clauses). Run it head-to-head against #1 on real commentary prompts; if it wins clearly, it is worth the licence strings.
3. **Qwen3-8B, 4-bit MLX** — `mlx-community/Qwen3-8B-4bit` (~4.6 GB). **The stretch goal, only by measurement.** Best quality that loads on an 8GB Mac at all (IFEval 85.0, Creative Writing 75.0) — but only with nothing else running. It does not fit alongside the broadcast stack (~5.2 + ~3.9 GB = ~9.1 GB > 8 GB). Revisit only if #1/#2 prove too weak *and* a memory diet (smaller browser footprint, Kokoro native, shorter context) frees the room.
4. **Qwen3-1.7B, 4-bit MLX** — `mlx-community/Qwen3-1.7B-4bit` (~1.0–1.4 GB). **The safe default.** Already in `docs/local-models.md` as the default. Weak for a live voice on its own — use it only if #1 fails the soak, or as the fast fallback tier.
5. **Llama 3.2 3B Instruct, 4-bit MLX** — `mlx-community/Llama-3.2-3B-Instruct-4bit` (~1.8 GB). **The legal fallback.** Strong general knowledge (MMLU 63.4, best at 3B), IFEval 77.4, smallest footprint of the credible options. Pick it if legal prefers Meta's licence over Google's custom terms, or if the commentary needs Llama's stronger general knowledge.
6. **Phi-4-mini-instruct, 4-bit MLX** — `mlx-community/Phi-4-mini-instruct-4bit` (~2.2 GB). **The fast fallback.** MIT licence, fastest on base chips, but the weakest instruction-follower measured (IFEval 0.50 on the 4-bit artifact).

**Ruled out for the live path:** DeepSeek-R1-Distill (any size — think traces), Mistral Small 3.2 24B (doesn't fit, slow MLX), Gemma 3 12B (doesn't fit), Qwen3-14B/32B and Qwen3.8-27B (don't fit — see `docs/research/qwen-27b-fit.md`), Llama 4 Scout/Maverick (absurd on this box), all 1B models as the voice.

### Later, on the GPU box

**Qwen3.8-27B at Q4** as the live voice, with the distilled student as the fallback. If the 27B is ever unavailable, Qwen3-32B or Qwen3-30B-A3B (MoE) are the alternates. DeepSeek-R1-Distill-14B joins only for offline reasoning, never live.

### Verification steps (on the actual 8GB box, in order)

1. Confirm the box is Apple Silicon (`About This Mac → Chip`). If Intel, the MLX plan fails — fall back to llama.cpp on CPU. **DONE Nov 12, 2026: confirmed Apple Silicon by Mason.**
2. `mlx_lm.benchmark --model mlx-community/Qwen3-4B-Instruct-2507-4bit -p 512 -g 128 -n 5` — record TTFT, decode tok/s, peak memory.
3. Run the 24-hour soak from the QA plan with the full stack (OBS + browser + NodeCG + Kokoro + MLX) and watch swap. If swap stays at zero, #1 is confirmed; if it grows, drop to #4.
4. A/B #1 vs #2 on 50 real commentary events, scored by a human on format compliance, factual grounding, and voice. Pick the winner on evidence, not benchmarks.
5. Re-check Qwen3.5/Qwen3.6/Qwen3.8 small sizes before finalising — the family moves fast, and a newer 4B may supersede Qwen3-4B.

---

## Sources

- Qwen3 technical report (IFEval, Creative Writing, MMLU-Redux, distillation): https://arxiv.org/pdf/arXiv:2505.09388
- Qwen3-8B / Qwen3-32B model cards: https://huggingface.co/Qwen/Qwen3-8B ; https://huggingface.co/Qwen/Qwen3-32B
- MLX benchmarks (Groundy, via Starmorph): https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide
- MLX vs llama.cpp / Ollama: https://localmodel.run/tools ; https://llmcheck.net/guides/mlx-framework-apple-silicon/ ; https://specpicks.com/reviews/run-llama-3-1-8b-on-m4
- mlx-benchmark suite (peak memory, TTFT): https://github.com/travis-ml/mlx-benchmark/blob/HEAD/README.md
- Llama 3.2 model card figures: https://localaimaster.com/models/llama-3-2-3b
- Gemma 3 model card: https://ai.google.dev/gemma/docs/core/model_card_3
- Gemma 3 MLX collection: https://huggingface.co/collections/mlx-community/gemma-3
- Gemma licence risks: https://wcr.legal/google-gemma-license-risks/
- Llama licence: https://openweightlicenses.com/commercial-use/llama
- Phi-4-mini model card: https://huggingface.co/microsoft/Phi-4-mini-instruct
- Phi-4-mini technical report: https://arxiv.org/html/2503.01743
- Localmaxxing 4-bit MLX artifact measurements (IFEval/GSM8K, decode speeds): https://github.com/nicoloboschi/localmaxxing
- DeepSeek-R1-Distill model card: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B
- Mistral Small 3.2: https://www.llamabuilds.ai/models/mistral-small-3-2-24b ; https://nodegrove.io/models/mistral-small-3.1-24b
- NordicSilicon Gemma Apple Silicon benchmarks: https://nordicsilicon.io/blog/gemma-apple-silicon-benchmarks
- Qwen 27B fit analysis (companion): `docs/research/qwen-27b-fit.md`
- Related project docs: `docs/local-models.md` (MLX-first architecture, 8GB budget, fine-tuning gates), `docs/commentary-prompts.md` (the prompts the LLM runs), `docs/qa-plan.md` (soak and calibration gates), `docs/deployment-runbook.md` (8GB MacBook Pro broadcast box), `docs/unreal-vertical-slice.md` (GPU box costs)
