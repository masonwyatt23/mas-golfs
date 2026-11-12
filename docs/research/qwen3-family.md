# Qwen3 Family — Deep Research for Local Use on Apple Silicon

**Date:** November 12, 2026
**Purpose:** Decide which Qwen model runs the real-time commentary LLM on the Mas Golfs broadcast box — an **8GB MacBook Pro** that also runs OBS, a browser (the web build), NodeCG, and Kokoro TTS.
**Related docs:** `docs/local-models.md` (the MLX-first architecture this research feeds), `docs/voice-options.md` (Kokoro TTS), `docs/commentary-prompts.md` (the prompts the LLM runs), `docs/broadcast-stack.md` §5 (the commentary pipeline).

## Verdict up front

**4B is the practical ceiling on the 8GB box. 8B does not fit alongside the full broadcast stack.**

- **Recommended default: `mlx-community/Qwen3.5-4B-4bit`** — the newest small Qwen (March 2026), ~2.5–3 GB at 4-bit, with benchmark quality far above the original Qwen3-4B. Fallback if it misbehaves: `mlx-community/Qwen3-4B-Instruct-2507-4bit` (2.27 GB), the proven, clean non-thinking instruct model.
- **Qwen3-8B 4-bit (~4.6–5.6 GB weights, ~7 GB running) technically loads on an 8GB Mac, but it leaves ~0–1 GB for everything else** once macOS + OBS + browser + NodeCG + Kokoro are counted. It forces swap, risks the macOS GPU memory limit, and generates at roughly 8–17 tok/s on a base M1/M2 — too slow and too fragile for a 24/7 unattended stream.
- **If Mason meant "Qwen 3.8" the generation (not Qwen3-8B the size): the smallest Qwen3.8, the 27B dense model, needs ~16.5–17 GB at 4-bit. It does not fit on 8GB at all.** See §0.

---

## §0 — Naming: "Qwen 3.8" is a generation, "Qwen3-8B" is a size

This confusion matters because the two things have opposite answers on an 8GB Mac.

| Name | What it is | Released | Smallest open model | Fits 8GB? |
|---|---|---|---|---|
| **Qwen3-8B** | One size in the Qwen3 family (April 2025) | Apr 29, 2025 | 8.19B dense | Barely loads; does not fit *alongside the stack* (§6–§8) |
| **Qwen3.8** | A whole generation (successor to Qwen3.5 → Qwen3.6 → Qwen3.7, which stayed closed) | Aug 2026 | **Qwen3.8-27B** dense, 27.8B | **No — ~16.5 GB at Q4** |
| Qwen3.8-2.4T-A95B | The Qwen3.8 flagship MoE (95B active) | Aug 12, 2026 | 2.4T total | No — and it is under a custom Qwen3.8-Max License, not Apache 2.0 |

Qwen3.8-27B is Apache 2.0, native vision-language (text/image/video), 262K context, and — per Artificial Analysis — scores 33.70 on Intelligence Index v4.3.2 (Oct 2026). It is the current default local Qwen on a 24GB+ machine. On this 8GB box it is not a candidate; it belongs to the GPU-box upgrade path in `docs/local-models.md` §7, where it would replace Qwen3-8B as the step-up model.

The rest of this doc covers the Qwen3 family (April 2025) in depth, then the newer generations' small models, because the best model that fits on 8GB turns out to be a newer-generation 4B, not a Qwen3-8B.

---

## §1 — The Qwen3 family (April 2025): all eight sizes

Released April 28–29, 2025, by Alibaba's Qwen team. Pre-trained on 36 trillion tokens, 119 languages. Hybrid thinking / non-thinking modes — the same weights can reason with a `<think>` block or answer directly. All eight models are open weights under **Apache 2.0** (commercial use, modification, redistribution, no royalty, no usage cap).

### Dense models

| Model | Parameters | Layers | Q heads / KV heads | Tied embeddings | Native context | 4-bit weights |
|---|---|---|---|---|---|---|
| Qwen3-0.6B | 0.6B | 28 | 16 / 8 | Yes | 32K | ~0.5 GB |
| Qwen3-1.7B | 1.7B | 28 | 16 / 8 | Yes | 32K | ~1.4 GB |
| Qwen3-4B | 4.0B | 36 | 32 / 8 | Yes | 32K native, 128K w/ YaRN | ~2.5 GB |
| Qwen3-8B | 8.19B | 36 | 32 / 8 | No | 32K native, 128K w/ YaRN | ~5.2 GB |
| Qwen3-14B | 14.8B | 40 | 40 / 8 | No | 32K native, 128K w/ YaRN | ~9.3 GB |
| Qwen3-32B | 32.8B | 64 | 64 / 8 | No | 32K native, 128K w/ YaRN | ~20 GB |

### Mixture-of-Experts models

| Model | Total params | Active params | Experts (total / active) | Layers | Native context | 4-bit weights |
|---|---|---|---|---|---|---|
| Qwen3-30B-A3B | 30.5B | ~3.3B | 128 / 8 | 48 | 32K native, 128K w/ YaRN (256K for the 2507 update) | ~18.6 GB |
| Qwen3-235B-A22B | 235B | 22B | 128 / 8 | 94 | 32K native, 128K w/ YaRN (256K for the 2507 update) | ~142 GB |

MoE models save compute, not memory: all 30B parameters still have to sit in memory even though only ~3B fire per token. The 30B-A3B is therefore not a small-model option — it needs ~19 GB.

**Context-length note:** the "128K" figures for 4B+ are YaRN-extended, not native. Native is 32K for the whole Qwen3 family. The July 2025 "2507" update (see §4) raised native context to **262,144** for the 4B, 30B-A3B, and 235B-A22B. For commentary, context is a non-issue either way: prompts are ~500–1,000 tokens.

---

## §2 — The newer generations (what shipped after Qwen3)

Qwen did not stand still. Three generations followed, and the small models got dramatically better. This is the single most important finding of this research: **the best 4B-class model in November 2026 is not a Qwen3 at all.**

| Generation | Released | Small dense sizes (open, Apache 2.0) | Architecture | Native context |
|---|---|---|---|---|
| Qwen3 | Apr 2025 | 0.6B, 1.7B, 4B, 8B, 14B, 32B; MoE 30B-A3B, 235B-A22B | Standard transformer | 32K |
| Qwen3-Next | Sep 2025 | 80B-A3B MoE only (no small dense) | Hybrid: Gated DeltaNet linear attention + gated attention | 262K |
| Qwen3.5 | Feb–Mar 2026 | **0.8B, 2B, 4B, 9B**, 27B; MoE 35B-A3B, 122B-A10B, 397B-A17B | Hybrid (Next architecture), natively multimodal (text/image/video) | 256K |
| Qwen3.6 | Apr 2026 | 27B; MoE 35B-A3B | Hybrid, natively multimodal | 256K |
| Qwen3.7 | May 2026 | **None open** — API-only Max; generation effectively skipped | — | — |
| Qwen3.8 | Aug 2026 | 27B; MoE 2.4T-A95B (custom license), Flash-Next 176B-A6B | Hybrid, natively multimodal | 262K, extendable to 1M via YaRN |

**Qwen3.5-9B is the newest small dense Qwen** — 3.6 and 3.8 skipped the ~8–9B size entirely. It is 9.7B parameters, 32 layers, 4 KV heads, Apache 2.0, and its MLX repo is `mlx-community/Qwen3.5-9B-4bit` (~5.5–6 GB at Q4). Its benchmarks (§3.3) are far ahead of Qwen3-8B — but its footprint is the same class as Qwen3-8B, so it hits the same 8GB wall.

**Qwen3.5-4B is the most interesting model for this box:** ~2.5–3 GB at Q4, with benchmarks that beat the original Qwen3-8B on several measures (§3.3). MLX repo: `mlx-community/Qwen3.5-4B-4bit` (the 4-bit build is the one RapidMLX benchmarked in Oct 2026).

---

## §3 — Benchmark quality by size

All Qwen3 numbers below are from the **Qwen3 Technical Report** (arXiv:2505.09388, May 2025), the vendor's own evaluations. Qwen3.5 numbers are from Qwen's published model-card/blog benchmarks, also vendor-reported. Treat vendor numbers as directional, not gospel — but the *relative* ordering across sizes is consistent across independent sources.

### §3.1 Qwen3, thinking mode (hybrid reasoning on)

| Benchmark | Qwen3-4B | Qwen3-8B | Qwen3-14B* | Qwen3-30B-A3B* | Qwen3-235B-A22B |
|---|---|---|---|---|---|
| MMLU-Redux (knowledge) | 83.7 | 87.5 | 82.0 | 84.1 | 89.2 |
| GPQA-Diamond (graduate science) | 55.9 | 62.0 | 54.8 | 54.8 | 62.9 |
| LiveBench (live, hard to game) | 63.6 | 67.1 | 59.6 | 59.4 | 62.5 |
| IFEval strict (instruction following) | 81.9 | 85.0 | 84.8 | 83.7 | 83.2 |
| Arena-Hard (open-ended quality) | 76.6 | 85.8 | 86.3 | 88.0 | 96.1 |
| MATH-500 | 97.0 | 97.4 | 90.0 | 89.8 | — |
| AIME'24 (competition math) | 73.8 | 76.0 | 31.7 | 32.8 | 85.7 |
| AIME'25 | 65.6 | 67.3 | 23.3 | 21.6 | 81.5 |

\* 14B and 30B-A3B figures are non-thinking mode from the same report's comparison table; thinking-mode AIME for those two is low because the report's table mixes modes — do not read the 14B AIME'24 of 31.7 as "14B is worse than 8B at math." The clean 4B-vs-8B comparison is the reliable one.

**Reading:** 8B beats 4B everywhere in thinking mode, but by small margins on the metrics that matter for commentary: IFEval +3.1 points, Arena-Hard +9.2, MMLU-Redux +3.8. The 4B already beats DeepSeek-R1-Distill-Qwen-14B on IFEval (81.9 vs 72.6) and Arena-Hard (76.6 vs 48.0) — a 4B model outperforming a 14B distillate on instruction following is the distillation story (§4) working.

### §3.2 Qwen3, non-thinking mode (the mode commentary actually uses)

Commentary lines are short, templated, fact-filled sentences — not chain-of-thought reasoning. Non-thinking mode is the right comparison, and it is also the mode with no `<think>` block to strip before TTS.

| Benchmark | Qwen3-4B | Qwen3-8B | Qwen3-14B | Qwen3-30B-A3B |
|---|---|---|---|---|
| MMLU-Redux | 77.3 | 79.5 | 82.0 | 84.1 |
| GPQA-Diamond | 41.7 | 39.3 | 54.8 | 54.8 |
| IFEval strict | 81.2 | 83.0 | 84.8 | 83.7 |
| Arena-Hard | 66.2 | 79.6 | 86.3 | 88.0 |
| LiveBench | 48.4 | 53.5 | 59.6 | 59.4 |

**Reading:** in non-thinking mode the 4B→8B gap narrows to **+1.8 IFEval points** and +2.2 MMLU-Redux. The big 8B advantage is Arena-Hard (+13.4) — open-ended creative writing quality, which a two-sentence golf line does not need.

### §3.3 The 2507 update — Qwen3-4B-Instruct-2507 (July 2025)

Three models got a mid-cycle update in July 2025: 4B, 30B-A3B, 235B-A22B. The 4B became **Qwen3-4B-Instruct-2507**: non-thinking only, **262,144 native context**, and substantially better instruction following.

| Benchmark | Qwen3-4B (orig, non-thinking) | Qwen3-4B-Instruct-2507 | Qwen3-30B-A3B (non-thinking) |
|---|---|---|---|
| MMLU-Pro | 58.0 | **69.6** | 69.1 |
| MMLU-Redux | 77.3 | **84.2** | 84.1 |
| AIME'25 | 19.1 | **47.4** | 21.6 |
| IFEval | 81.2 | **83.4** | 83.7 |
| Arena-Hard v2 | 9.5 | **43.4** | 24.8 |

**Reading:** the 2507 4B matches the 30B-A3B MoE on MMLU-Pro and MMLU-Redux, and beats the original 4B by +11.6 MMLU-Pro and +28.3 AIME'25. Its IFEval (83.4) is within 0.4 points of the original **8B non-thinking** (83.0) — it has effectively closed the 4B→8B instruction-following gap. This is why `docs/local-models.md` originally shortlisted it, and why it remains the safe fallback.

**No Qwen3-8B-Instruct-2507 exists.** The 2507 treatment was never applied to the 8B. Multiple projects note they are "monitoring for its availability" — as of November 2026 it has not shipped. The MLX 8B repo (`mlx-community/Qwen3-8B-4bit`) is the **base hybrid model**, not a clean instruct model: it emits `<think>` blocks by default, which the commentary pipeline must strip before TTS.

### §3.4 Qwen3.5 small models (vendor-reported, February–March 2026)

| Benchmark | Qwen3.5-4B | Qwen3.5-9B | Qwen3-8B (thinking, for reference) | GPT-OSS-120B |
|---|---|---|---|---|
| MMLU-Pro | 79.1 | **82.5** | — (MMLU-Redux 87.5) | 80.8 |
| GPQA Diamond | 76.2 | **81.7** | 62.0 | 80.1 |
| IFEval | 89.8 | **91.5** | 85.0 | 88.9 |
| MMLU-Redux | 88.8 | 91.1 | 87.5 | 91.0 |
| AIME 2026 | — | 92.5 | — | — |
| LongBench v2 | 50.0 | 55.2 | — | 48.2 |

**Reading, with the caveat:** these are vendor-reported and the GPQA jump (62.0 → 81.7) is large enough to treat with care until independently reproduced. But the direction is corroborated: the 9B beats a 120B model on MMLU-Pro, GPQA, IFEval, and LongBench v2 across multiple independent write-ups, and the 4B's IFEval of 89.8 is +6.4 over the Qwen3-4B-Instruct-2507's 83.4. Even discounting vendor optimism by several points, **Qwen3.5-4B is the strongest ~4B-class model available, and Qwen3.5-9B is the strongest ~8–9B-class model available.**

---

## §4 — Distilled variants: what exists

The short answer: **the small Qwen3 models already are distilled models.** There is no separate "Qwen3-8B-distilled" product to go find.

- **Qwen3's own distillation:** per the technical report, the five smaller dense models (0.6B–14B) and the 30B-A3B MoE were **distilled from Qwen3-32B and Qwen3-235B-A22B in two phases** (off-policy distillation, then on-policy distillation). The 4B and 8B you download are the products of that process — which is why a 4B Qwen3 beats a 14B DeepSeek-R1-Distill-Qwen on instruction following (§3.1).
- **DeepSeek-R1-Distill-Qwen-14B / 32B:** a different lineage — Qwen2.5 bases distilled from DeepSeek-R1. Older generation, larger, and worse than Qwen3-4B on IFEval and Arena-Hard. Not relevant.
- **Qwen3-4B-Instruct-2507:** the July 2025 refresh — a non-thinking instruct variant with improved instruction following, reasoning, and text comprehension. Effectively a second distillation/RL pass on the 4B. The cleanest small instruct model in the family.
- **Qwen3.5-4B / 9B:** a full generation newer, built on the hybrid Next architecture. Not "distilled" in name, but trained with the same distillation-heavy recipe at a newer capability level.
- **Community fine-tunes:** dozens of Qwen3-8B fine-tunes exist on Hugging Face (uncensored variants, role-play, domain-specific). None is a better commentary model than the base/instruct weights, and unlicensed/uncensored variants add risk for a broadcast product. Not recommended.

**Bottom line:** do not go looking for a distilled 8B — the 8B is already a distillate, and the quality lever that actually moves is generation (3.5 > 3), not a further distillation of the same size.

---

## §5 — MLX availability

All of these are downloadable today from Hugging Face and runnable with `mlx-lm`. MLX-native format (safetensors) is 20–30% more memory-efficient than GGUF due to zero-copy unified memory; prefer MLX repos over GGUF for this box. (MLX can read GGUF, but only Q4_0, Q4_1, and Q8_0 — other quants get cast to FP16, defeating the purpose.)

| Model | MLX repo (Hugging Face) | Quant variants available | Download size |
|---|---|---|---|
| Qwen3-0.6B | `mlx-community/Qwen3-0.6B-4bit` | 4-bit | ~0.4 GB |
| Qwen3-1.7B | `mlx-community/Qwen3-1.7B-4bit` | 4-bit | ~1.1 GB |
| Qwen3-4B | `mlx-community/Qwen3-4B-4bit` | 4-bit | ~2.3 GB |
| Qwen3-4B-Instruct-2507 | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 4-bit | **2.27 GB** |
| Qwen3-8B | `mlx-community/Qwen3-8B-4bit` | 4-bit | ~4.3–4.9 GB |
| Qwen3-8B (DWQ) | `mlx-community/Qwen3-8B-4bit-DWQ` | 4-bit DWQ | 4.6 GB |
| Qwen3-14B | `mlx-community/Qwen3-14B-4bit` | 4-bit | ~9 GB |
| Qwen3-30B-A3B | `mlx-community/Qwen3-30B-A3B-4bit`, `...-Instruct-2507-4bit` | 4-bit | ~18.6 GB |
| Qwen3.5-4B | `mlx-community/Qwen3.5-4B-4bit` | 4-bit | ~2.5–3 GB |
| Qwen3.5-9B | `mlx-community/Qwen3.5-9B-4bit` | 4-bit | ~5.5–6 GB |
| Qwen3.6-35B-A3B | `mlx-community/Qwen3.6-35B-A3B-4bit-DWQ` | 4-bit DWQ | ~22 GB |
| Qwen3.8-27B | `mlx-community/Qwen3.8-27B-4bit` (verify at install time) | 4-bit | ~16.5 GB |

Official Qwen-hosted MLX exports also exist: `Qwen/Qwen3-4B-MLX-4bit` and `Qwen/Qwen3-8B-MLX-4bit`. The mlx-community builds are the ones the community benchmarks and most projects use; prefer them.

**Quantization notes:**
- **4-bit is the sweet spot** (~0.6 GB per billion parameters; ~3.3% quality loss vs BF16, ~75% size reduction). 8-bit doubles memory for a small quality gain — not worth it on 8GB. 6-bit exists for some models but is not the MLX default.
- **3-bit exists** for some models (e.g. `Qwen3-VL-4B-Instruct-3bit`). A 3-bit 8B would be ~3.5 GB — small enough to fit — but 3-bit costs noticeably more quality than 4-bit, and no 3-bit Qwen3-8B text build is a standard, well-tested artifact. Treat as an experiment for later, not a default.
- **DWQ (Deep Weight Quantization)** is mlx-community's higher-quality 4-bit variant. Where a `-DWQ` build exists for the chosen model, prefer it.

---

## §6 — Memory footprint on Apple Silicon (the deciding section)

### §6.1 What a model actually costs in memory

Weights are only part of it. Running memory = weights + KV cache + activations + framework overhead.

| Model (4-bit MLX) | Weights | KV cache @ 2K ctx | Activations + overhead | Total running |
|---|---|---|---|---|
| Qwen3-1.7B | ~1.1 GB | ~0.2 GB | ~0.5 GB | ~1.8 GB |
| Qwen3-4B / 4B-Instruct-2507 | ~2.3 GB | ~0.3 GB | ~0.5 GB | **~3.0 GB** |
| Qwen3.5-4B | ~2.5–3 GB | ~0.3 GB | ~0.5 GB | **~3.5 GB** |
| Qwen3-8B | ~4.6–5.6 GB | ~0.7 GB | ~0.8 GB | **~6.5–7.0 GB** |
| Qwen3.5-9B | ~5.5–6 GB | ~0.7 GB | ~0.8 GB | **~7.0 GB** |
| Qwen3-14B | ~9.2 GB | ~1 GB | ~1 GB | ~11 GB |
| Qwen3-30B-A3B | ~18.6 GB | ~1.5 GB | ~1 GB | ~21 GB |
| Qwen3.8-27B | ~16.5 GB | ~1.5 GB | ~1 GB | ~19 GB |

Anchors: Apple's own MLX benchmark (M5 MacBook Pro, 4K prompt) measured Qwen3-8B-MLX-4bit at **5.61 GB** and Qwen3-14B-MLX-4bit at **9.16 GB** — weights plus a 4K-prompt KV cache, before the rest of the system. An independent M3 Pro measurement put Qwen3-8B 4-bit at **~7 GB total running** (4.3 GB weights + 1.5 GB activations at 2K tokens + 1.0 GB KV cache). Simon Willison's hands-on report: Qwen3-8B MLX 4-bit consumes **4–5 GB** in practice. All three agree: 8B-class costs ~5–7 GB running.

### §6.2 The macOS GPU memory limit (the hidden constraint)

On Apple Silicon, MLX allocates from unified memory, but macOS caps how much the GPU can address: on a 24 GB M2 Mac, Ollama, llama.cpp, and MLX all report the same GPU limit of **17.8 GB — about three quarters of total memory**. By the same ratio, an 8GB Mac's GPU-addressable ceiling is **~6 GB by default**. It can be raised on macOS 15+ with `sudo sysctl iogpu.wired_limit_mb=N`, but that is a manual hack on the broadcast box, not a clean default — and raising it just lets the model eat memory the rest of the stack needs.

A 5.6 GB model inside a ~6 GB GPU ceiling leaves nothing for KV cache growth, let alone OBS's encoder. This is a second, independent reason 8B is out — not just total RAM, but the GPU-addressable slice.

### §6.3 The 8GB box budget (from `docs/local-models.md` §4, re-checked)

| Consumer | Memory |
|---|---|
| macOS | ~1.5 GB |
| OBS (1080p60 hardware encode) | ~0.6 GB |
| Browser (web build, Balanced tier) | ~0.9 GB |
| NodeCG | ~0.25 GB |
| Commentary service | ~0.15 GB |
| Kokoro TTS (native) | ~0.4 GB |
| **Subtotal before the LLM** | **~3.8 GB** |
| Free on an 8GB box | ~4.2 GB |

| LLM candidate | Running memory | Total with stack | Headroom | Verdict |
|---|---|---|---|---|
| Qwen3-1.7B 4-bit | ~1.8 GB | ~5.6 GB | ~2.4 GB | Fits easily |
| Qwen3-4B-Instruct-2507 4-bit | ~3.0 GB | ~6.8 GB | ~1.2 GB | **Fits** |
| Qwen3.5-4B 4-bit | ~3.5 GB | ~7.3 GB | ~0.7 GB | **Fits, tighter** |
| Qwen3-8B 4-bit | ~6.5–7.0 GB | ~10.3–10.8 GB | **−2.3 to −2.8 GB** | **Does not fit** |
| Qwen3.5-9B 4-bit | ~7.0 GB | ~10.8 GB | **−2.8 GB** | **Does not fit** |
| Qwen3-14B 4-bit | ~11 GB | ~14.8 GB | −6.8 GB | No |
| Qwen3.8-27B 4-bit | ~19 GB | ~22.8 GB | −14.8 GB | No |

The 8B shortfall is not marginal — it is 2–3 GB over, which on an 8GB box means sustained swap, memory pressure, and the watchdog killing processes. Swap on Apple Silicon is fast but it is not free: it burns SSD write cycles on the broadcast box and adds latency jitter exactly when a commentary line is due.

---

## §7 — Generation speed on an 8GB Mac

LLM generation is **memory-bandwidth-bound**: every token requires reading the whole model from memory once, so the ceiling is `bandwidth ÷ model size in memory`. The 8GB MacBook Pro is a base M1, M2, or M3 (the Pro chips start at 16GB), so its bandwidth is **68 GB/s (M1) or 100 GB/s (M2/M3)**.

### §7.1 The arithmetic ceiling

| Model (4-bit) | Size in memory | M1 ceiling (68 GB/s) | M2/M3 ceiling (100 GB/s) |
|---|---|---|---|
| Qwen3-1.7B | ~1.1 GB | ~62 tok/s | ~91 tok/s |
| Qwen3-4B | ~2.3 GB | ~30 tok/s | ~43 tok/s |
| Qwen3.5-4B | ~2.7 GB | ~25 tok/s | ~37 tok/s |
| Qwen3-8B | ~5 GB | ~14 tok/s | ~20 tok/s |
| Qwen3.5-9B | ~5.7 GB | ~12 tok/s | ~18 tok/s |

Real machines hit **60–80% of the ceiling** (KV cache reads, attention, kernel overhead). Measured anchors:

- **M1 8GB, Llama 3.1 7B Q4 (llama.cpp/Metal): 24.3 tok/s** in one harness, ~14 tok/s in another — harness variance is large; treat both as the same ballpark.
- **M2 Max 32GB (measured, llama.cpp, 2K ctx): Llama 3.1 8B Q4 ~28 tok/s.** Scaled by bandwidth ratio to a base M2 (100 GB/s vs 400 GB/s), that is ~18 tok/s — consistent with the ceiling math.
- **RapidMLX, Oct 30 2026 (M2 Pro 32GB, 200 GB/s): `qwen3-8b-4bit` 38.1 tok/s; `qwen3.5-9b-4bit` 36.8 tok/s; `qwen3.5-4b` 63.3 tok/s.** Halve those for a base M2 (100 GB/s) and divide by ~3 for a base M1 (68 GB/s).
- **MLX vs llama.cpp:** MLX is 20–87% faster than llama.cpp for models under 14B on Apple Silicon; Qwen3-8B 4-bit measured at **93.3 tok/s (MLX) vs 76.9 (llama.cpp), +21%** — but that benchmark ran on a high-bandwidth Mac. The MLX advantage is real and it is why MLX is the runtime; it does not change the bandwidth ceiling.

### §7.2 What that means for a commentary line

A commentary line is 1–2 sentences, ~30–60 tokens. Expected real-world speed on the 8GB box:

| Model | M1 (68 GB/s) | M2/M3 (100 GB/s) | Time for a 40-token line (M1) | Time for a 40-token line (M2) |
|---|---|---|---|---|
| Qwen3-4B-Instruct-2507 | ~18–24 tok/s | ~26–34 tok/s | ~1.7–2.2 s | ~1.2–1.5 s |
| Qwen3.5-4B | ~15–20 tok/s | ~22–30 tok/s | ~2.0–2.7 s | ~1.3–1.8 s |
| Qwen3-8B | ~8–11 tok/s | ~12–16 tok/s | ~3.6–5.0 s | ~2.5–3.3 s |
| Qwen3.5-9B | ~7–10 tok/s | ~11–14 tok/s | ~4.0–5.7 s | ~2.9–3.6 s |

Context that saves the 4B: lines are generated **before** they are needed (the decision line is generated pre-shot; the result line is generated during ball flight), and standard lines are cached verbatim (`docs/commentary-prompts.md` §9). So even 2 seconds per line is workable. But 4–5 seconds per line on an M1 8B — plus the swap risk from §6 — leaves no margin for a slow day, a long prompt, or a cold cache. And time-to-first-token grows with prompt length under MLX (full prefill before the first token), so the 8B's slower prefill compounds the problem.

**Speed verdict:** 4B-class generates roughly **2× as fast** as 8B-class on this hardware, because it moves half the bytes per token. That is a bigger practical difference than the ~2-point IFEval gap.

---

## §8 — Is Qwen3-8B the best model that fits? No — and the real question is different

**Direct answer:** Qwen3-8B is the best *Qwen3-family* model that can technically load on an 8GB Mac in isolation. It is **not** the best model that fits on this box *alongside the broadcast stack* — it does not fit, by 2–3 GB, and it is too slow on base-M1/M2 bandwidth. The practical ceiling for a resident LLM on this box is **4B-class**.

But the more useful finding is that the ceiling does not cost much quality, because the generation moved on:

| Candidate | Fits? | Speed (M1) | IFEval | MMLU-Pro / Redux | Notes |
|---|---|---|---|---|---|
| Qwen3-1.7B 4-bit | Yes, easily | ~40–50 tok/s | 68.2 | — / 64.4 | Too weak for broadcast voice; the old default |
| Qwen3-4B-Instruct-2507 4-bit | **Yes** | ~18–24 tok/s | **83.4** | 69.6 / 84.2 | Proven, clean non-thinking, no `<think>` to strip |
| **Qwen3.5-4B 4-bit** | **Yes** | ~15–20 tok/s | **89.8** | 79.1 / 88.8 | Newest, strongest 4B; vendor-reported, verify on the box |
| Qwen3-8B 4-bit | No (with stack) | ~8–11 tok/s | 83.0–85.0 | — / 79.5–87.5 | Base hybrid model; emits `<think>`; GPU-limit risk |
| Qwen3.5-9B 4-bit | No (with stack) | ~7–10 tok/s | **91.5** | 82.5 / 91.1 | Best 9B-class model; the one to want on the GPU box |
| Qwen3.8-27B 4-bit | No | — | — | — | 16.5 GB; GPU-box upgrade path only |

Two observations:

1. **Qwen3.5-4B beats Qwen3-8B on instruction following** (IFEval 89.8 vs 83.0–85.0) while using half the memory and generating ~2× as fast. The 8B's advantage was real in April 2025; a generation of progress erased it.
2. **The model to want is Qwen3.5-9B, not Qwen3-8B.** If the box ever grows (GPU box, or a 16GB+ Mac), the 9B is the step up — it is the newest small dense Qwen, it beats the 8B on every published benchmark, and it is Apache 2.0. Qwen3-8B is a dead end as a target: it is the best of its generation, but its generation is two behind.

**The 3-bit escape hatch, honestly assessed:** a 3-bit Qwen3-8B would be ~3.5 GB and would fit the memory budget, generating at ~15–20 tok/s on M1. It is a legitimate experiment — but 3-bit costs real quality (more than 4-bit's ~3.3%), no standard well-tested 3-bit Qwen3-8B text build is the community default, and it would still emit `<think>` blocks. Only try it if the 4B options both disappoint on the box, and A/B it against the 4B on real commentary prompts before adopting.

---

## §9 — Recommendation for the real-time commentary LLM

**Default: `mlx-community/Qwen3.5-4B-4bit`, served by mlx-lm, non-thinking, temperature 0.7, max tokens 120** (per `docs/commentary-prompts.md` §11).

**Fallback: `mlx-community/Qwen3-4B-Instruct-2507-4bit`** — same serving setup. Swap to it if Qwen3.5-4B shows any of: `<think>` leakage, infinite chain-of-thought loops (an Ollama-specific Qwen3.5 issue reported March 2026; not expected under mlx-lm, but verify), broken tool/JSON output, or worse lines than the 2507 on the same prompts.

**Do not ship on this box:** Qwen3-8B (any quant), Qwen3.5-9B, Qwen3-14B, Qwen3-30B-A3B, Qwen3.8-27B. All are revisited on the GPU box, where Qwen3.5-9B (not Qwen3-8B) is the next step, then Qwen3.8-27B.

**What changes in `docs/local-models.md`:** the default commentary LLM moves from Qwen3-1.7B-Instruct (with Qwen3-4B as a gated stretch goal) to **Qwen3.5-4B-4bit as the default, Qwen3-4B-Instruct-2507-4bit as the fallback**. The 1.7B drops to emergency-fallback status. The memory budget still closes: ~3.5 GB for the LLM leaves ~0.7 GB headroom on the 8GB box (vs ~2.1 GB with the 1.7B) — acceptable, and the degradation order (batch jobs die first, then cached lines, then silence, then browser tier, never OBS) is unchanged. Qwen3-4B as a "stretch goal" is deleted — it is now the fallback, not the aspiration.

## §10 — What to measure on the real box before locking this in

1. **Memory:** boot the full stack (OBS + browser + NodeCG + Kokoro + mlx-lm with Qwen3.5-4B), run 30 minutes, confirm swap stays at 0 and no process is jetsammed. Then repeat with Qwen3-4B-Instruct-2507 and compare.
2. **Latency:** time 20 commentary generations (decision lines + result lines, real prompts from `docs/commentary-prompts.md`): report median and P99 time-to-first-token and total time. Pass bar: P99 total under 4 seconds.
3. **Line quality:** blind A/B the two 4B candidates on 20 real events; the booth test from `docs/commentary-prompts.md` §12 (60 seconds to a golfer with no context — can they state score, hole, and plan?) decides.
4. **`<think>` check:** grep 100 generated lines for `<think>` / `</think>` leakage. Zero tolerance — a leaked think block read aloud by Kokoro is a broadcast failure.
5. **Qwen3-8B negative control (optional, 10 minutes):** load `mlx-community/Qwen3-8B-4bit` with the stack running and watch Activity Monitor. Expect swap growth and/or the GPU wired-limit warning. This is the evidence that closes the 8B question on this hardware, rather than an argument.

## Sources

- Qwen3 Technical Report, arXiv:2505.09388 (May 2025) — family structure, architecture tables, all Qwen3 benchmark tables, two-phase distillation of the smaller models from Qwen3-32B / Qwen3-235B-A22B. https://arxiv.org/html/2505.09388v1
- Qwen3-4B-Instruct-2507 model card / Unsloth GGUF page — 262,144 native context, non-thinking only, benchmark table vs GPT-4.1-nano and Qwen3-30B-A3B. https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF (via search)
- Qwen3.5 small-model benchmarks (NYU Shanghai RITS write-up, March 2026) — Qwen3.5-9B/4B vs GPT-OSS-120B, Qwen3-30B, Qwen3-80B. https://rits.shanghai.nyu.edu/ai/qwen-3-5-small-models-9b-parameters-that-beat-120b/
- RedHatAI Qwen3.5-9B quantized evaluation (Hugging Face) — BF16 vs INT4 recovery rates on MMLU-Pro, IFEval, AIME 2025, GPQA Diamond. https://huggingface.co/RedHatAI/Qwen3.5-9B-quantized.w4a16
- Apple, "Exploring LLMs with MLX and the Neural Accelerators in the M5 GPU" — Qwen3-8B-MLX-4bit 5.61 GB, Qwen3-14B-MLX-4bit 9.16 GB, Qwen3-8B-MLX-bf16 17.46 GB; MLX memory behavior on Apple Silicon. https://machinelearning.apple.com/research/exploring-llms-mlx-m5
- RapidMLX benchmark, Oct 30 2026 (4 Macs) — `qwen3-8b-4bit` 38.1 tok/s and `qwen3.5-9b-4bit` 36.8 tok/s on M2 Pro; `qwen3.5-4b` 63.3 tok/s; peak memory Qwen3.8-27B 17 GB. https://rapidmlx.com/blog/local-ai-speed-m2-pro-m4-pro-m5-max-m3-ultra
- Starmorph, "Apple Silicon LLM Inference Optimization" — MLX 20–87% faster than llama.cpp under 14B; Qwen3-8B 4-bit MLX 93.3 vs llama.cpp 76.9 tok/s; Ollama MLX backend requires 32GB+. https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide
- Haplo, "How to Run an LLM Locally on a Mac" (Oct 2026) — 8GB Mac guidance (up to ~4B params), GPU limit ~3/4 of total memory, `iogpu.wired_limit_mb`. https://haploapp.com/blog/run-llm-locally-on-mac
- HeyEduardo, "Local LLM Speed on M1–M5 Macs" — bandwidth-bound generation, M1 68 GB/s → ~14 tok/s on 7B Q4, M2 100 GB/s → ~22 tok/s. https://heyeduardo.app/blog/apple-silicon-ai-benchmarks-2026
- ML Journey, "Mac M1 vs M2 vs M3 vs M4 for Running LLMs" — measured 7B Q4 generation: M1 8GB 24.3 tok/s, M2 28.5 tok/s; M1 8GB cannot load Q8 7B. https://mljourney.com/mac-m1-vs-m2-vs-m3-vs-m4-for-running-llms-real-tests/
- ModelPiper, "Local LLM Benchmarks on Apple Silicon" — M2 Max measured 8B Q4 ~28 tok/s; M1 8GB 8B expectation 10–14 tok/s. https://modelpiper.com/blog/local-llm-benchmarks-apple-silicon
- Simon Willison, MLX tag (May 2025) — hands-on Qwen3-8B MLX 4-bit, 4.3 GB download, 4–5 GB memory in use. https://simonwillison.net/tags/mlx/
- DeepWiki, MLX conversion/quantization doc — Qwen3-8B 4-bit on M3 Pro: ~7 GB total running, ~30 tok/s vs ~20 tok/s BF16. https://deepwiki.com/sehgal-vip/jee-finetune/5.2-mlx-conversion-and-quantization
- Qwen version trackers (Nov 2026) — Qwen3.5/3.6/3.8 release dates, sizes, licenses (Qwen3.8-2.4T under custom Qwen3.8-Max License; Qwen3.8-27B Apache 2.0; Qwen3.7 closed). https://mungomash.com/ai/qwen/versions/ and https://vramglass.com/model/qwen
- Local AI model rankings — Qwen3-8B thinking-mode GPQA 62.0 / AIME'24 76.0; Qwen3-14B GPQA 64.0 / AIME'24 79.3. https://local-ai.net/models/rankings/
