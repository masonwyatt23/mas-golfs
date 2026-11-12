# Mas Golfs — Voice Options for the Commentary Pipeline

**The job:** two distinct broadcast voices (play-by-play host + color commentator) for a 24/7 autonomous golf livestream. Event-only usage — a decision line before the shot, a result line at apex/landing, milestone calls — never continuous talk. Budget: **$0/month**. Everything below was verified against current sources on Nov 12, 2026; links are in §9.

**The latency insight that decides this:** the pipeline is event-driven, not conversational. The sim knows the decision *before* the shot and the result *at* apex, so a line can be synthesized during the walk, the swing, or the ball flight — seconds of headroom, not milliseconds. Any engine that renders a 20-second line in under ~5 seconds is fast enough. That makes CPU engines viable and makes pre-generation + caching the real latency strategy, not raw time-to-first-audio.

---

## 1. The comparison

| | Kokoro-82M | Piper | Chatterbox | Qwen3-TTS | Coqui XTTS v2 | ElevenLabs Flash v2.5 |
|---|---|---|---|---|---|---|
| **License** | Apache 2.0 ✅ | Engine GPL-3.0; voices vary ⚠️ | MIT ✅ | Apache 2.0 ✅ | Weights CPML, non-commercial only ❌ | Proprietary, paid |
| **Cost** | $0 | $0 | $0 | $0 | $0 (but see license) | $0.04 / 1K chars ($40 / 1M) |
| **Size** | 82M params, 88–310 MB | ~63 MB per voice (medium) | 110M–500M | 0.6B / 1.7B | ~2.1 GB | Cloud API |
| **Hardware** | CPU fine; GPU faster | CPU, even Raspberry Pi | GPU preferred; Nano on CPU | GPU (6–12 GB VRAM) | GPU (4–6 GB VRAM) | None (cloud) |
| **Speed** | ~6× RTF on M3 Pro CPU; 35–100× RTF on GPU; TTFA ~300 ms GPU, ~1 s M3 Pro | RTF ~0.15–0.2 CPU; 50–150 ms for short phrases | ~200 ms (Turbo, GPU); Nano ~3× RTF on 8 CPU cores | Published 97 ms first packet; measured 2–3 s first audio in one project | Sub-200 ms streaming on GPU; slow on CPU | ~75 ms model latency (excl. network) |
| **Voices** | 54 preset, 8 languages | 174–175 across 55 languages | Presets + zero-shot clone | Presets + clone + voice design | Any voice from a clip | Library + cloning |
| **Voice cloning** | No — blends only | No | Yes, 5–20 s clip | Yes, ~3 s clip | Yes, ~6 s clip | Yes, ~10 s clip |
| **Two distinct voices** | Yes — pick any two presets, or blend | Yes — pick any two voices | Yes — two clones or presets | Yes — two clones/presets | Yes — two clones | Yes |
| **Quality** | ~90% of ElevenLabs in one head-to-head; 63rd of 103 on the Artificial Analysis Speech Arena | 3–4/5; clearly below Kokoro; fine for prompts, thin for broadcast | Beat ElevenLabs in Resemble's own blind test (63.75% preference); emotion control | Benchmarks beat ElevenLabs on WER/similarity; some report an "anime-like" English quality | Excellent cloning quality | Best-in-class expressiveness |
| **Streaming** | No token-streaming websocket; chunked PCM/MP3 via HTTP | File/pipe output; no streaming server built in | Streaming supported | Streaming (12 Hz path) | Streaming | WebSocket streaming |
| **Setup** | One Docker command | One install command | `pip install chatterbox-tts` + PyTorch | Hard: FlashAttention builds, pinned transformers | `pip install coqui-tts` + PyTorch | API key + SDK |
| **Maintenance risk** | Active (Kokoro-FastAPI maintained) | Active fork (OHF-Voice/piper1-gpl) | **Resemble left the voice business Aug 2026 — no vendor support** | Active (Qwen team) | Company dead Jan 2024; community fork maintained | Vendor-supported |

---

## 2. Kokoro-82M — the recommended default

**Why it wins for this project:** it is the only option that is simultaneously free, commercially clean (Apache 2.0), CPU-capable, good-sounding, trivially deployable, and already served over an OpenAI-compatible API — which makes it a drop-in backend for the commentary pipeline and trivially swappable later.

- **Model:** 82M parameters, StyleTTS2-based, 24 kHz output. Weights ~310 MB (FP32), 169 MB (FP16), 88 MB (INT8). FP16 is the sweet spot: on a decade-old 4-core Xeon it still managed RTF ~1.4×; on an M3 Pro CPU it runs ~6× faster than real time with under a second to first audio; on a mid-range NVIDIA GPU it runs 35–100× real time with ~300 ms to first audio.
- **Voices:** 54 preset voices across 8 languages (US/British English, Spanish, French, Hindi, Italian, Japanese, Brazilian Portuguese, Mandarin). American English voices use the `af_` (female) / `am_` (male) prefix. `af_heart` is widely considered the best all-rounder. **Voice blending** is built in: `af_bella+af_sky` blends two voices equally, `af_bella(2)+af_sky(1)` weights them 67/33 — enough to craft two voices that are unmistakably different even without cloning.
- **Server:** Kokoro-FastAPI wraps the model in an OpenAI-compatible endpoint (`POST /v1/audio/speech`, plus `/v1/audio/voices` to list voices). Docker images exist for CPU, CUDA, Blackwell (`latest-cu128`), and ROCm. Default port 8880. A web player at `http://localhost:8880/web` lets you audition voices in the browser before committing.
- **Latency in this pipeline:** a 20-second commentary line renders in ~1–3 seconds on CPU, ~0.3 seconds on GPU. Because lines are pre-generated during the walk/swing/flight, this is effectively zero perceived latency. Pre-generate + cache (see §7) and latency stops being a question at all.
- **Limits, honestly:** no voice cloning (a real person's voice needs another model); no token-streaming websocket, so it is one-shot synthesis per line, not a live stream — fine for event lines, wrong for a live conversation. Quality is good but not top of the field (63rd of 103 on the Speech Arena); on an 8 kHz phone call some detail is lost, but a livestream is 48 kHz, where Kokoro sounds its best. Date/number verbalization is its weakest spot — the pipeline's text normalizer (see §7) handles that.

**The two voices (audition these first):**

| Role | Voice | Why |
|---|---|---|
| **Host (play-by-play)** | `am_michael` | Male, warm, steady — the CBS/NBC cadence the broadcast wants. Speed 1.0. |
| **Color (commentator)** | `af_sky` | Female, bright, clear — clearly distinct from the host in pitch and timbre. Speed 1.05, slightly quicker and lighter. |

If `am_michael` reads too flat on your test lines, try `am_adam` (host) and `af_nicole` (color). If the two voices still feel too close, blend: host `am_michael+am_echo`, color `af_sky+af_nicole`. Audition on real lines — "He's got 187, uphill, into the wind — this is a full 7-iron" — not on test sentences.

---

## 3. Piper — the fallback if the machine has no headroom

- **Model:** VITS, exported to ONNX, one small model per voice. Medium voices are ~63 MB at 22.05 kHz; low ~28–63 MB at 16 kHz; high up to ~137 MB. RTF ~0.15–0.2 on a 12th-gen i7 CPU — roughly 6× faster than real time — and 50–150 ms for short phrases. It runs on a Raspberry Pi.
- **Voices:** 174–175 voices across 55 languages; 38 English. Two distinct broadcast voices are easy (e.g. `en_US-ryan-medium` host, `en_US-amy-medium` color). Some voices bundle multiple speakers in one model, but quality per speaker can be lower than a dedicated single-speaker voice.
- **Quality:** the weakest of the free options for broadcast — 3–4 stars out of 5 in community ratings, "fine for a UI prompt, not what you'd want for an audiobook." On a golf broadcast it would read as a robot next to Kokoro.
- **License — read this carefully:** the original `rhasspy/piper` repo (MIT) was archived Oct 6, 2025; active development is now `OHF-Voice/piper1-gpl` under **GPL-3.0**. Voice models are licensed separately — each ships a `MODEL_CARD`, and Piper's own docs say the project is intended for personal use and TTS research only and that some individual voices carry more restrictive licenses. **Check the MODEL_CARD of each voice before broadcasting with it.** GPL-3.0 on the engine is not a problem for a self-hosted server (no distribution), but the per-voice terms are.
- **Use it when:** the broadcast box has no GPU and not enough CPU for Kokoro, or as the emergency fallback if Kokoro ever fails. It is the lightest engine here by a wide margin.

---

## 4. Chatterbox — the cloning upgrade path (not the default)

- **Model:** Resemble AI, MIT license — the only zero-shot cloning model here that is fully commercial-friendly. Three variants: **Turbo** (350M, English, low latency, ~200 ms), **Nano** (110M, English, ~3× real time on 8 CPU cores), **Multilingual v3** (0.5B, 23 languages + 4 dialects, released June 10, 2026). Zero-shot cloning from a 5–20 second reference clip; emotion control on a continuous scale; `[laugh]`, `[cough]`, `[chuckle]` tags.
- **Quality:** the strongest free option on paper — Resemble's own blind evaluation had testers prefer Chatterbox over ElevenLabs Flash v2.5 in 63.75% of comparisons. Community benchmarks measured ~4.5 GB VRAM and ~8.8× real time on an RTX 5090.
- **The catches:** (1) **Every clip carries a mandatory PerTh watermark** — embedded, not removable. For a broadcast this is arguably a feature (provenance, AI-use disclosure), but it must be a conscious choice. (2) **Resemble left the voice business on Aug 13, 2026** — there is no vendor support; the models are community-maintained now. (3) Long generations fall apart: the original cuts off around 40 seconds, Turbo wobbles and drops words after 25–30 seconds — commentary lines are short (280-char cap), so this is manageable by splitting, but it is a real constraint. (4) Cloning any real person's voice requires their consent, regardless of license.
- **Use it when:** the show wants two *named, consistent* voices that are not presets — e.g. cloning two consenting broadcast voices, or Mason's own voice as the color commentator. It is the upgrade from Kokoro, not the starting point: Kokoro first, Chatterbox when the show has an audience and a reason to lock in a voice identity.

---

## 5. Qwen3-TTS — the future option, not yet

- **Model:** Alibaba Qwen team, released Jan 22, 2026. Apache 2.0. Two sizes (0.6B / 1.7B), 10 languages. Zero-shot cloning from ~3 seconds of reference, voice design from a text description ("a calm, gravelly Scottish commentator"), emotion control. Benchmarks beat ElevenLabs on word-error rate and speaker similarity.
- **Latency:** the published 97 ms is a per-chunk streaming figure, not time-to-first-audio. One project's own testing measured **2–3 seconds to first audio** in practice, and RTX 5090 owners report generation 10× slower than real time out of the box without community forks (torch.compile + CUDA graphs). Until a proper streaming server (vLLM) is verified, plan around the measured number.
- **Hardware:** 6–8 GB VRAM for 0.6B, 8–12 GB for 1.7B. NVIDIA only in practice; Mac/AMD support is patchy.
- **Setup:** hard for non-specialists — FlashAttention builds, a hard-pinned transformers version.
- **Verdict:** the most capable free engine on paper and the cleanest license, but the setup and latency uncertainty make it a bad first choice. Re-evaluate at the Unreal leap, when the broadcast box has a GPU and someone has an afternoon to stand up the vLLM server. If it delivers on its numbers, it replaces Chatterbox as the cloning upgrade.

---

## 6. Coqui XTTS v2 — ruled out

XTTS v2 clones a voice from a ~6-second clip across 17 languages, with sub-200 ms streaming latency on a GPU and excellent cloning quality. It is ruled out for one reason: **the model weights are under the Coqui Public Model License, which permits non-commercial use only — and Coqui shut down in January 2024, so there is no one left to sell a commercial license.** A monetized YouTube/Twitch broadcast is commercial use. The code (MPL-2.0) is fine; the weights are not. The maintained fork is `idiap/coqui-ai-TTS` (`pip install coqui-tts`, v0.28.0, Oct 2026), but the fork cannot change the weights' license. Use Chatterbox or Qwen3-TTS for cloning instead.

---

## 7. ElevenLabs Flash v2.5 — the paid fallback

- **Price (verified Oct 2026):** $0.04 / 1,000 characters ($40 / 1M) for Flash v2.5 and v4 Turbo; $0.08 / 1,000 for v3, v4, and Multilingual v2. Free tier is 10,000 credits/month, **non-commercial only** (attribution required) — not usable for this broadcast.
- **Latency:** ~75 ms model latency, excluding application and network latency. Independent benchmarks (Coval, Sep 2026) put real-world time-to-first-audio at ~185 ms median. 32 languages, 40,000 characters per request. Voice cloning from ~10 seconds of reference.
- **The cost trap, quantified:** continuous 24/7 commentary at ~45,000 characters/hour would cost ~$1,300/month. Event-only commentary with cached lines is an order of magnitude less — but it is still a bill, and it is still $0 vs. something.
- **The one real gotcha:** Flash v2.5 leaves text normalization off by default to protect latency, so phone numbers, dates, and currency come out awkwardly — and turning it on is an Enterprise-only option. The pipeline's own text normalizer (expand "187" to "one eighty-seven", "7-iron" to "seven iron") is needed either way.
- **Use it when:** the show has revenue and wants the best available expressiveness for a specific moment (e.g. a season-finale special), or if every free engine is down. Never as the default. The switch is a config change (see §8), not a rebuild.

---

## 8. Recommendation and setup

### The default: Kokoro-FastAPI (CPU)

**Stack:** one Docker container on the same machine that runs OBS. No GPU required. $0/month, $0 per line, forever.

**Setup steps:**

```bash
# 1. CPU-only (works everywhere)
docker run -d --name kokoro \
  -p 8880:8880 \
  ghcr.io/remsky/kokoro-fastapi-cpu:latest

# GPU (if the box has one — 35-100x real time, ~300 ms to first audio)
docker run -d --name kokoro \
  --gpus all -p 8880:8880 \
  ghcr.io/remsky/kokoro-fastapi-gpu:latest

# 2. Check it answers
curl http://localhost:8880/v1/audio/voices | head -c 500

# 3. Audition the two voices in the browser
#    open http://localhost:8880/web, paste a real commentary line,
#    try am_michael (host) and af_sky (color), then am_adam / af_nicole.
```

**Pipeline integration:**

1. **One HTTP interface, every engine behind it.** The commentary service talks to an OpenAI-compatible `/v1/audio/speech` endpoint with `{model, voice, input, response_format}`. Kokoro-FastAPI serves that endpoint natively. Every other engine is reached through the same shape (a thin shim for Piper/Chatterbox, the real API for ElevenLabs). Swapping engines is a config change, never a code change.
2. **Voice config (one file, e.g. `voices.yaml`):**
   ```yaml
   engine: kokoro            # kokoro | piper | chatterbox | elevenlabs
   base_url: http://localhost:8880/v1
   host:
     voice: am_michael      # play-by-play
     speed: 1.0
   color:
     voice: af_sky          # commentator
     speed: 1.05
   ```
3. **Pre-generate + cache.** Hash `(voice + normalized text)` → audio file. Decision lines are generated the moment the sim emits a `decision` event (seconds before the shot); result lines are generated at `apex` (seconds before landing). Repeated calls ("He's got 187, uphill, into the wind") hit the cache and cost nothing. Cache lives on disk; a 24-hour round is a few hundred short lines, tens of megabytes at most.
4. **Text normalization before synthesis.** Expand numbers ("187" → "one eighty-seven"), clubs ("7-iron" → "seven iron"), distances ("12 feet" → "twelve feet"), and strip anything the voice would stumble on. This is required for Kokoro and for Flash alike.
5. **Audio chain.** Output MP3 or PCM from Kokoro; normalize to −16 LUFS; duck the ambient bed under commentary; never speak over a swing (the director holds the line until impact).
6. **Watchdog.** If the Kokoro container stops answering, the commentary service falls back to Piper (if installed) or to silence with the ambient bed — never to a paid API without a human flipping the config.

### The switching guide

| From → To | What changes | What does not change |
|---|---|---|
| Kokoro → Piper | `engine: piper`, voice IDs to Piper names (e.g. `en_US-ryan-medium` / `en_US-amy-medium`), add the Piper shim. Check each voice's MODEL_CARD first. | Event schema, caching, normalization, audio chain, OBS routing. |
| Kokoro → Chatterbox | `engine: chatterbox`, add reference clips (5–20 s each, with consent) for the two voices, or use presets. Budget ~4.5 GB VRAM. Accept the PerTh watermark. Split lines over ~25 seconds. | Same interface, same cache keys (voice ID changes, so the cache rebuilds once). |
| Kokoro → Qwen3-TTS | `engine: qwen3`, stand up the vLLM streaming server, verify first-audio latency on the actual box before going live. | Same interface; cloning from 3-second clips if desired. |
| Any free engine → ElevenLabs Flash | `engine: elevenlabs`, API key, `model_id: eleven_flash_v2_5`, voice IDs to ElevenLabs voice IDs. Set a monthly character budget and an alert at 80%. | Same interface; cache becomes even more valuable at $40/1M chars. |
| ElevenLabs → any free engine | Remove the API key, point `base_url` at the local server. | Nothing else. This is why the interface is engine-agnostic. |

**Upgrade ladder:** Kokoro (now) → Chatterbox (when the show wants locked-in voice identities) → Qwen3-TTS (re-evaluate at the Unreal leap) → ElevenLabs Flash (only for paid specials, or if free engines fail and revenue exists). Never the reverse direction by default.

---

## 9. Sources (checked Nov 12, 2026)

- Kokoro benchmarks and CPU numbers: https://blog.nemesisnet.co.za/self-hosted-tts-with-kokoro-onnx-what-cpu-only-inference-actually-gets-you/
- Kokoro review, Speech Arena ranking, no cloning: https://www.dograh.com/hub/blogs/kokoro-tts-review
- Kokoro vs ElevenLabs head-to-head, Apache 2.0, RTF: https://www.remogrid.com/blog/ai-tools/kokoro-tts-vs-elevenlabs-voiceover-comparison
- Kokoro model table, 54 voices, blending: https://rakazo.com/voice-providers/self-hosted/
- Self-hosted TTS model comparison 2026: https://www.sevenlabs.site/blogs/best-self-hosted-tts-models-2026
- Piper CPU shortlist, license change, voice tiers: https://localaimaster.com/blog/best-tts-without-gpu
- Piper license and voice MODEL_CARD warnings: https://www.murmurtts.com/blog/piper-tts-vs-murmur-mac and https://www.cekura.ai/discover/piper-tts
- XTTS v2 status, fork, CPML non-commercial: https://www.murmurtts.com/blog/xtts-coqui-vs-modern-local-tts, https://localaimaster.com/blog/xtts-coqui-commercial-license, https://www.promptquorum.com/power-local-llm/xtts-v2-review
- Chatterbox variants, MIT, watermark, Resemble exit: https://www.promptquorum.com/power-local-llm/best-local-tts-nvidia-gpu, https://www.alterhunt.com/tools/chatterbox, https://awesomeagents.ai/tools/best-open-source-voice-tts-2026/
- Qwen3-TTS release, latency caveat, hardware: https://yurios.org/book/24-voice.html, https://www.snackonai.com/p/qwen3-tts-voice-ai-without-the-cloud, https://localaimaster.com/blog/local-ai-voice-clone
- ElevenLabs Flash pricing and latency (Oct 2026 cut): https://www.beri.net/article/elevenlabs-vs-cartesia-vs-azure-tts-latency-pricing-voice-cloning-2026, https://oxyy.ai/blog/fish-audio-vs-elevenlabs-api-pricing, https://balazscsorba.com/blog/elevenlabs
- Kokoro-FastAPI setup, voices, streaming: https://bishalkshah.com.np/blog/kokoro-tts-local-text-to-speech-setup, https://docs.jambonz.org/guides/features/tts-vendor-settings/kokoro, https://pypi.org/project/fastkokoro/0.7.0/
