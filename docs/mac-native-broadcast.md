# Mas Golfs — Mac-Native Broadcast Design

**Status:** design only, no code. Written Nov 13, 2026.
**Direction:** Mason, Nov 13 ~1:55am EST — build the golf world to run natively on the 8GB MacBook Pro (the broadcast box) and stream *that* via OBS, instead of running the world as a web page in a browser.
**Constraint:** $0. No purchases, no subscriptions, no GPU box. The 16GB MacBook Air (grandpa's writing archive) is never touched.
**Related docs:** `docs/unreal-vertical-slice.md` (the graphics bar and the terrain work), `docs/deployment-runbook.md` (the 8GB box and its stack), `docs/local-models.md` (8GB memory accounting), `docs/broadcast-stack.md` (event bus, NodeCG, OBS scenes), `docs/research/terrain-lidar-prep.md` (Hole 12 LiDAR — note: it lives under `docs/research/`, not `docs/`).

---

## 0. The decision, up front

**Recommendation: Godot 4.7 (current stable at build time), Forward+ renderer on its native Metal driver, GDScript, Terrain3D plugin for terrain, Mixamo/MakeHuman character with a MediaPipe-derived swing from Mason's swing video.**

Godot is the only free engine that (a) runs natively on Apple Silicon Metal, (b) fits in the 8GB budget alongside OBS + MLX + Kokoro + NodeCG, and (c) is a large, honest step up from the browser Three.js scene — real PBR materials, real shadows, baked global illumination, volumetric fog, proper terrain with texture layers, and a real character rig. It does not reach the Unreal + Lumen + Nanite ceiling. Nothing on this box does. What it does is close most of the gap for $0, on hardware we already own.

**What this design does not do:** it does not green-light Unreal on this box (see §1.4 — it does not fit), it does not replace the sim (Python stays authoritative), and it does not replace the web build (the web build stays live as prototype, clip factory, and fallback until the Mac build passes its soak — see §7).

---

## 1. Engine options, ranked for a FREE build on this box

Scored against Mason's bar: "beautiful to watch and cutting edge — 2K, Tiger Woods, GTA 6 level," mobile-first, camera always behind the golfer, clean screen. The bar is the *direction*; the honest statement is that no engine on an 8GB Apple Silicon box hits GTA 6 at 2K. The ranking below is about how close each gets, for $0, on this hardware.

### 1.1 Ranked

| Rank | Engine | Cost | Verdict |
|------|--------|------|---------|
| 1 | **Godot 4.7 — Forward+ / native Metal** | $0, MIT open source | **Recommended.** Native Metal on Apple Silicon since 4.4 (Metal 4 on macOS 26, Metal 3 fallback on older macOS), Forward+ and Mobile renderers both Metal-capable. Fits the memory budget. Biggest graphics step available on this box. |
| 2 | **Unity 6 — URP** | $0 under Unity Personal (free while revenue + funding < $200K in the last 12 months; Pro is $210/mo/seat above that) | Credible alternative. Native Metal, mature tooling, huge free-asset ecosystem, URP is light enough for the box. Loses to Godot on: editor memory footprint (Unity lists 16GB minimum / 32GB recommended on Mac — the editor would not live on this box during development, though a built player would), license terms that expire if the company grows, and a heavier runtime. Keep as the fallback if the Godot slice fails its frame-rate gate. |
| 3 | **Local Electron / Three.js app** | $0 | Fastest route to "runs on the Mac" — the existing web build source runs nearly verbatim inside an Electron shell, OBS window-captures it, no browser chrome, stable dedicated process, direct file access. **But the graphics ceiling is identical to the web build**: same geometry, same materials, same stylized diorama. It answers the deployment question, not Mason's graphics complaint. Use only as a stopgap if the web build becomes unstable, or as the fallback scene if Godot fails. |
| 4 | **Unreal Engine 5.8 on Mac** | $0 license for this use (free under $1M gross revenue; 5% royalty only above $1M — this is a broadcast, not a shipped game product) | **Not viable on this box.** Epic recommends 16GB minimum / 32GB recommended on Mac, M3 minimum for full features. The editor alone wants 2–4GB; a packaged Lumen build at 1080p wants 4GB+; alongside OBS + MLX + Kokoro it does not fit 8GB. Lumen on macOS is software ray tracing only (no hardware RT on Apple Silicon in UE), and there is no DLSS on Mac (NVIDIA-only) — TSR is the upscaler. UE is still the graphics ceiling *in the abstract* and the Hole 12 slice design in `docs/unreal-vertical-slice.md` stays the long-term GPU-box path. It is not the 8GB-box path. Do not attempt it here. |
| — | Bevy, O3DE, Stride, raw Metal custom engine | $0 | Ruled out. Bevy has no mature editor or terrain tooling and a small asset ecosystem; O3DE is heavy and immature; Stride is Windows-centric; a raw Metal engine is months of work for a worse result than Godot. |

### 1.2 Honest graphics ceilings (1080p60 on the 8GB box)

| Engine | What it can look like | What it cannot do | Gap vs the GTA/2K bar |
|--------|----------------------|-------------------|----------------------|
| Godot Forward+ | Real PBR materials, baked LightmapGI or SDFGI, soft shadows, volumetric fog, terrain texture layers, instanced wind-swayed grass and trees, procedural sky + clouds, reflective pond water, a rigged character with a real swing. At broadcast distance (camera behind the golfer, hole in frame) this reads as a good modern game — a large step from the web build. | No Nanite-equivalent (no virtualized geometry — polygon budgets are manual), no Lumen-equivalent real-time GI (GI is baked or SDFGI, both coarser), no Megascans-grade photoreal assets for free, no MetaHuman. Close-ups of trees and the golfer will still read as "game," not footage. | ~60–70% of the bar. The visible jump is real; the last 30% needs the GPU box and UE. |
| Unity URP | Roughly Godot's ceiling, slightly better asset ecosystem, slightly worse out-of-the-box look without paid post-processing. | Same class of limits as Godot (no Nanite/Lumen), plus the editor won't live on this box. | ~60–70% of the bar. |
| Electron/Three.js | Exactly the current web build, minus browser overhead. | Everything the web build can't do — geometry is the limit, not the shell. | ~30% of the bar. No improvement. |
| UE 5.8 (GPU box, for reference) | Lumen + Nanite + MetaHuman + Ultra Dynamic Sky: the only path that genuinely approaches the bar. | Needs a GPU box and ~$50 for the sky asset (not approved). Not this box. | ~90% of the bar. |

**The honest sentence for Mason:** Godot on this Mac will look *much* better than the web page — real light, real terrain, a real golfer — but it will not look like GTA 6. The remaining gap is a hardware gap (GPU box + UE), not an effort gap, and this design does not pretend otherwise.

### 1.3 Why Godot wins the ranking (not just "it's free")

- **Native Metal, not a translation layer.** Godot 4.4 introduced a native Metal driver for Apple Silicon; 4.7 uses Metal 4 on macOS 26. Earlier Godot ran Vulkan through MoltenVK. Native Metal matters here because the box is GPU-constrained and every frame of translation overhead is a frame of grass or shadow we don't get.
- **Forward+ has the features that close the visible gap**: clustered lighting, volumetric fog, SDFGI, LightmapGI, SSAO/SSIL, soft shadows, 32-bit reverse-Z depth (matters for long-view terrain — a golf course is all long views).
- **The exported player is light.** The editor is heavy; the *player* (what actually runs during broadcast) is a small native binary. Development happens on this VM or Mason's dev machine; only the player runs on the broadcast box. This is the opposite of UE, where the editor is the thing that eats the box.
- **MetalFX upscaling is available** if the render-resolution fallback is ever needed (render at 0.85×, upscale to 1080p).
- **GDScript + WebSocketClient are built in.** The renderer can talk to the bus with no plugins (see §3).
- **Terrain3D plugin is free and MIT** — heightmap import, texture-layer painting, LOD. Purpose-built for exactly the terrain step in §5.

### 1.4 What Godot cannot do (stated plainly)

- No virtualized geometry: the course must be built with deliberate polygon budgets (terrain mesh resolution, instanced trees/grass with distance culling). A careless scene will chug; a disciplined one will hold 60fps.
- No hardware ray tracing on Apple Silicon, no DLSS. Reflections are probes + screen-space, not ray-traced.
- No MetaHuman. The golfer will be a Mixamo/MakeHuman-quality character — good, not photoreal.
- No asset store as deep as Unity's or Quixel's. Free assets exist (Quaternius CC0 packs, Poly Haven HDRIs/textures) but photoreal golf-course assets for free are scarce; most of the course's look must be built from the LiDAR terrain + procedural materials + shader work, not bought assets.

---

## 2. What runs on the 8GB box — memory and GPU budget

### 2.1 The box (measure first — see §6 Step 0)

The broadcast box is an **8GB MacBook Pro, Apple Silicon — confirmed by Mason Nov 12**. The exact chip (M1/M2/M3/M4) and macOS version are **not recorded** and they matter: a base M1 has an 8-core GPU (~2.6 TFLOPS) and Metal 3; a base M4 has a 10-core GPU and Metal 4. **Step 0 of the build measures the chip, macOS version, and idle memory pressure before any renderer settings are chosen.** All budgets below are sized for the worst case (base M1) so a newer chip is headroom, not a requirement.

### 2.2 Memory budget (estimates to be measured on the box, not measurements)

The web build's stack is ~5.9GB with a native Kokoro build (`docs/local-models.md`). The Mac build **removes the browser (~900MB)** and adds the Godot player (~1.0GB) — roughly a wash on RAM, with a large GPU-efficiency win (native Metal vs WebGL + JS).

| Process | Est. RAM | Notes |
|---------|----------|-------|
| macOS + WindowServer | ~1.4GB | With one display attached, Godot window + OBS open. |
| OBS Studio (1080p60, hardware H.264/HEVC via VideoToolbox) | ~0.6GB | One scene, Godot window capture + NodeCG browser source + replay buffer. |
| **Godot exported player (Hole 12 scene, 1080p, Forward+)** | **~1.0GB** | Asset-dependent; textures are the driver. Working set cap: ≤1.5GB of textures, 2K max per texture, mipmapped, compressed. |
| NodeCG server + OBS browser source (overlays) | ~0.6GB | NodeCG server ~0.15GB; the Chromium browser source inside OBS ~0.3–0.5GB. The overlays stay web — only the *world* moves to Godot. |
| MLX — Qwen3.5-4B-4bit (commentary) | ~2.5GB | Per `docs/local-models.md`. Unchanged. |
| Kokoro TTS (native build) | ~0.4GB | Per `docs/local-models.md`. Unchanged. |
| Sim + bus server + commentary service + watchdog | ~0.25GB | Python, light. Unchanged. |
| **Total** | **~6.75GB** | **Leaves ~1.25GB headroom on an 8GB box.** Tight but workable. macOS will compress under pressure; the degradation order (§2.3) exists so pressure never reaches a kill. |

**Hard rule:** total committed memory must stay under **7.0GB** at all times during a broadcast. The watchdog (`ops/`, per the deployment runbook) gains a memory check: if total exceeds 7.0GB for 60 seconds, it sheds load per §2.3 and logs it; it never kills OBS or the sim.

### 2.3 GPU budget and degradation order

Apple Silicon has no dedicated VRAM — the GPU shares the same 8GB. The binding constraint is **texture working set + render targets**, not framebuffers (a 1920×1080 RGBA16F buffer is ~16MB; trivial).

- **Render target:** 1920×1080 native, render scale 1.0. No upscaling at baseline.
- **Texture budget:** ≤1.5GB total, 2K max per texture, BC-compressed, mipmapped. Terrain splat maps at 1K. One 2K sky/cloud texture. Character textures at 1K.
- **Geometry budget:** terrain via Terrain3D LOD; trees/grass as MultiMeshInstance3D with distance culling (grass only within ~40m of camera, trees full hole but instanced, ~300–500 instances max for the slice).
- **Lighting:** one directional sun with shadow mapping, shadow distance ~150m; LightmapGI baked for the static course (preferred — free at runtime) with SDFGI as fallback if bake times are impractical.

**Degradation order (shed in this order, never touch OBS or the sim):**
1. Godot render scale 1.0 → 0.85 (MetalFX upscale to 1080p) — invisible on stream, saves GPU time.
2. Shadows: distance 150m → 80m, then soft shadows off.
3. Grass density halved, then grass off beyond 20m.
4. Volumetric fog quality down, then off (keep standard fog).
5. MLX: drop to cached-line commentary (no live generation) — picture is sacred, commentary degrades first.
6. Kokoro: silence non-essential lines (keep hole intros and milestones).
7. **Never shed:** OBS, the sim, the bus, NodeCG overlays, watchdog.

### 2.4 What the box does NOT run

- **No Godot editor during broadcast.** Only the exported player binary. The editor lives on the dev machine.
- **No Unreal editor or UE game.** See §1.1.
- **No browser tab rendering the world.** The browser is gone from the render path; Chromium survives only as OBS's browser source for NodeCG overlays.
- **Nothing on the 16GB Air.** Ever.

---

## 3. How the sim feeds the renderer

### 3.1 The bus is unchanged

The sim already publishes live to a local WebSocket bus on **port 4456** (`bus/server.py`, stdlib-only; `MAS_GOLFS_BUS_URL` env var, `sim/events.py` `EventEmitter`). The Godot renderer is **a new client of that bus, nothing more**. No changes to `bus/server.py` or `sim/` are needed for the renderer to consume events — Step 1 verifies the server accepts multiple simultaneous clients (Godot + NodeCG + any tooling) and that reconnects are clean.

- **Transport:** `ws://localhost:4456`, Godot's built-in `WebSocketClient` (GDScript, no plugin).
- **Envelope:** the broadcast-stack envelope from `docs/broadcast-stack.md` §1.2 (11 inbound event types; `shot_result` fans out to `strike` / `apex` / `landing`, so 12 envelope types arrive on the wire), plus the `round_state` snapshot for state the renderer needs at startup and after a reconnect.
- **Step 1 check:** confirm the exact field list of each payload against `sim/engine.py` and `bus/translate.py` before writing renderer code — the field names below are the *contract the renderer needs*; if a field is missing from the payload, that is a sim-side addition, not a renderer workaround.

### 3.2 Latency budget

| Hop | Budget | Notes |
|-----|--------|-------|
| Sim decision → bus emit | <10ms | Already the case (in-process publish). |
| Bus → renderer (localhost WebSocket) | <5ms | Same machine, no network. |
| Renderer event → frame | ≤1 frame (16.7ms at 60fps) | Event applied on the next `_process` tick. |
| **Event → photon (shot starts)** | **<50ms total** | The swing starts on screen within ~3 frames of the sim emitting it. |
| Commentary (MLX → Kokoro → OBS) | seconds-scale, buffered | Unchanged from the web build; not latency-critical and never blocks the picture. |

### 3.3 What the renderer does with each event family

**The renderer is a dumb visualizer. The sim is authoritative.** The renderer never computes scores, handicaps, physics outcomes, or commentary. It draws what the sim says happened, and interpolates between the sim's sparse events so motion is smooth at 60fps.

| Event(s) | Renderer behavior |
|----------|-------------------|
| `round_start` | Load the course scene (Wyatt National / Dunmore), apply `conditions` (wind speed/direction → flag + tree sway + grass shader; firmness → ball-roll visuals; green speed → putt visuals; weather → sky/fog/light). Set the season/59 Watch initial state. |
| `hole_start` | Move camera to the tee (always behind the golfer), place the golfer at the tee, place the pin from the event's pin position (`sim/pins.py` — pins rotate every 2 rounds; renderer reads the pin from the event, never computes it), set the hole par/yardage in the scene state for the overlay (overlay itself is NodeCG's job). |
| `decision` | Show the golfer's setup: club selection, aim line (subtle, broadcast-style), stance. No numbers on screen — numbers live in the NodeCG overlay and pinned description. |
| `strike` (from `shot_result`) | Start the swing animation (video-derived, §5.4) and the ball flight. **Ball flight is interpolated, not simulated:** the renderer integrates a ballistic arc from the strike payload's launch parameters (ball speed, launch angle, azimuth, backspin) per frame, and corrects the arc at `apex` and `landing`. Required strike fields: ball speed, launch angle, azimuth, backspin, carry, apex height, landing position. If any field is absent from the payload, add it on the sim side in Step 1 — do not guess it in the renderer. |
| `apex` | Correct the in-flight ball position to the sim's apex (kills integration drift). Tracer peaks here. |
| `landing` | Correct the ball to the sim's landing position, then play rollout (roll distance/direction from the payload; the sim's lie determines the visual: fairway/rough/semi/bunker/green). Tracer fades. |
| `putt_read` (before the stroke) | Draw the solver's predicted path on the green (from the event's path points, `sim/putting.py` `build_putt_read`), tinted by make probability. Show the break. This is the broadcast's signature putting visual. |
| `putt_result` (after the stroke) | Draw the actual path (from the event), animate the ball along it at real putt speed, show make/miss. The predicted path fades as the actual path draws — the viewer sees the read vs the reality. |
| `fifty_nine_watch` | Read the 59 Watch state from the event / `round_state`: pace vs the 59 line, glow state. The renderer shows the state on the course (e.g., a subtle gold tint on the flag / score bug area is NodeCG's job; the renderer's job is the 3D state — flag color, ambient cue). Never invents a 59 Watch state — only renders what the event says. |
| `milestone` | Brief 3D cue (e.g., a subtle camera push-in or light lift) — restrained, never over the swing. The overlay text is NodeCG's. |
| `hole_end` / `round_end` | Camera to the next tee / the clubhouse wide shot; score-state reset per the event. |
| `round_state` snapshot | Consumed at renderer startup and after any reconnect, so a restarted renderer re-syncs to the current hole, score, 59 Watch state, and conditions without waiting for the next event. |

### 3.4 What the renderer must NOT do

- No sim logic (no strokes-gained, no handicap, no learning loop, no decisions).
- No commentary text generation, no TTS.
- No Coins logic, no chat, no leaderboard rendering (NodeCG owns all 2D UI).
- No inventing data: if an event lacks a field the renderer needs, the renderer renders without it and logs the gap — it never estimates a ball position, a score, or a 59 Watch state.

---

## 4. OBS capture path

### 4.1 Capture method — ranked

| Method | How it works | Latency | Verdict |
|--------|-------------|---------|---------|
| **macOS Screen Capture (window capture)** | OBS's built-in ScreenCaptureKit source, capturing the Godot player window. GPU-accelerated, no custom code. | ~1–2 frames | **Primary.** Works today with any app. The Godot player runs in a borderless 1920×1080 window; OBS captures that window. |
| **Syphon (via a small GDExtension)** | Zero-copy GPU texture share between apps on macOS (IOSurface). OBS has a Syphon client source. | ~0 frames | **Stretch goal.** Godot does not ship Syphon support — it would need a small GDExtension that publishes the viewport texture via the Syphon framework, or a community extension if one is verified. Only pursued after the slice is green on window capture. Do not block the slice on this. |
| **NDI (via community extension / NDI Tools)** | Network-based video transport over localhost; free NDI Tools + OBS-NDI (DistroAV) plugin. | ~1–3 frames | **Fallback.** More moving parts than window capture for a same-machine hop; useful only if ScreenCaptureKit misbehaves with the Godot window. |

### 4.2 Resolution and frame rate

- **Stream:** 1080p60 (unchanged from the web build's target).
- **Internal render:** 1920×1080 native, render scale 1.0. Degradation to 0.85 with MetalFX upscale if the frame-time gate fails (see §2.3).
- **Godot window:** borderless, exactly 1920×1080, on the broadcast box's display. No fullscreen-exclusive mode (macOS window capture needs a window; exclusive fullscreen complicates capture and recovery).
- **OBS:** window capture source (Godot) + browser source (NodeCG overlays, per `docs/broadcast-stack.md`) + replay buffer for clips (unchanged). Overlays composite in OBS exactly as they do today — the NodeCG bundle does not change; only the bottom video layer changes from "browser tab" to "Godot window."

### 4.3 Failure behavior

- If the Godot player crashes or freezes, OBS keeps streaming the last frame — the watchdog detects the freeze (no frame change / process gone) and OBS's scene switches to the **web-build fallback scene** (the browser tab, still running warm) while the watchdog restarts the Godot player. The stream never goes black. This is the same fallback posture as the web build's own crash handling, and it is why the web build stays running until cutover (§7).
- If the bus drops, the renderer freezes the last known state and shows nothing new — it never invents motion. Reconnect is automatic with `round_state` re-sync.

---

## 5. The vertical slice: Hole 12 "The Picture" first

### 5.1 Why Hole 12

Hole 12 is the prettiest hole on the course (164 yd, 20 ft downhill, pond fronts the entire kidney green, 28 yd wide — `docs/course-design-v2.md` §12) and it is the only hole with real terrain already prepped. It is also the hardest test of the look: water, elevation, a green that must read as a green. If Hole 12 doesn't look good, 18 holes won't either. **Judge the slice on real footage before committing to 18 holes.**

### 5.2 Terrain import (Godot path)

The heightmap is ready: `unreal/terrain/wyatt-hole12-heightmap-505.png` — **16-bit grayscale PNG, 505×505 px, 1 m/px, 505 m × 505 m**, elevation 375.36–414.94 m (relief 39.58 m), USGS 1 m LiDAR of Blue Ridge foothill terrain east of Staunton, VA. Full provenance and import numbers in `docs/research/terrain-lidar-prep.md`. Verified on disk: 505×505, 16-bit, md5 `37bb377111f3cdda3fd5a8c9bf80a5f5`. The source GeoTIFF (`wyatt-hole12-source-clip-1m.tif`, float32, EPSG:26917) is the reproducible source.

Godot differences from the UE import math in the terrain doc (the UE Z-scale of 7.7314 and the 512-step / 7.7 cm quantization are **UE-specific and do not apply**):

- **Godot units are meters, Y-up, float32 height.** No quantization: the heightmap's 0.6 mm vertical precision survives import (the terrain doc's 7.7 cm UE step does not exist in Godot).
- **Import:** Terrain3D plugin (free, MIT) — import the 16-bit PNG as the heightmap, normalized 0→1 mapping to the 39.58 m relief, with the valley floor offset so the scene origin sits near 0. Terrain3D's import path must be verified against a 16-bit PNG in Step 2; the fallback is a small script that converts the PNG to a mesh (numpy → OBJ/glTF) and imports it as a static mesh with a splat shader.
- **Orientation:** PNG row 0 = north edge, column 0 = west edge; valley runs NW–SE. In Godot, -Z is north by convention — flip/rotate on import as needed and **verify against `wyatt-hole12-preview-hillshade.png`** (high rims west and east, low channel in the middle) before doing any golf-feature work.
- **Golf features (hand-authored after import, same as the UE plan):** flatten the tee box on the west rim (~6 m / 20 ft above the green), flatten the kidney green on the east-rim bench, carve the pond basin into the valley floor in front of the green, cut the two bunkers. Design elevations from `course-design-v2.md` §12. A before/after screenshot pair goes in the repo when this step is done.

### 5.3 Look-dev for the slice (the parts that decide whether it looks good)

- **Sky:** Godot `ProceduralSkyMaterial` + sun + a custom cloud shader + volumetric fog (Forward+). No paid sky asset exists for Godot and none is needed — the UE-only $49.99 Ultra Dynamic Sky is not part of this build.
- **Lighting:** one directional sun, baked LightmapGI for the static course (free at runtime), soft shadows, 150 m shadow distance. Golden-hour default to match the swing video's light.
- **Water:** pond shader — normal-scrolled surface, fresnel, reflection probe, subtle ripple from the wind value in `conditions`. Cheap, and water is the single most visible "is this real" cue on Hole 12.
- **Grass/terrain:** Terrain3D texture layers (fairway / rough / green / bunker sand / cart path) painted from the course spec; instanced grass blades (MultiMeshInstance3D, wind shader) within ~40 m of the camera; trees as instanced meshes with a wind-sway shader. **Trees are the known weakest element** (they were the weakest in the web build too): use Quaternius CC0 tree packs or Blender sapling/MTree-generated trees, keep the camera at broadcast distance where they read well, and do not judge the slice on a tree close-up.
- **Greens:** the green is the putting surface — it must carry the solver's slope. The green mesh comes from `sim/greens.py` heightfields (the putting solver already builds 18 green heightfields); the slice imports Hole 12's green heightfield so the rendered green *is* the solver's green, not a lookalike. Putt-read paths drawn on it must match the solver's numbers exactly.

### 5.4 The golfer and the swing

MetaHuman is UE-only and is not available here. The free path, in order:

1. **Character:** Mixamo (free, Adobe account) — a rigged character with idle/walk animations; or MakeHuman (free, open source) for a custom Mason-like build. Either imports to Godot as glTF. Honest ceiling: a good game character, not a photoreal twin. The character is left-handed, matching Mas.
2. **Swing:** video-derived from Mason's swing video (`workspace/user/media_library/video/9b/9b8ed9d56187ed07bd183c48f09d8c9b5f75a9cd61bfe786a1bec4ec6438038e.mp4` — down-the-line driver, golden hour; swing anchor only, outfit customizable). MediaPipe Pose (free, Apache 2.0) extracts 3D joint angles; retarget in Blender (free) onto the rigged character; export glTF; import to Godot. The swing must be judged on a phone, the way Mason judges the web build.
3. **Timing:** the swing animation is 1.6 s (matching the web rebuild's timing), ball flight ~6.8 s + ~4 s rollout for a driver — the renderer plays the animation on `strike` and the ball arc per §3.3. The ball is the thing the viewer watches after the swing; the tracer + live distance counter stay (they are NodeCG overlay, unchanged).

### 5.5 Slice exit criteria (judged on real footage, not in-editor)

The slice is green only when **all** of these hold, judged from a recorded 1080p60 clip watched on a phone:

1. Hole 12 reads as a real golf hole at broadcast distance: terrain, pond, green, bunkers all present and correctly placed vs the hillshade.
2. A full hole plays end-to-end from sim events: tee shot, approach, putt_read path, putt_result, hole_end — no desync, no invented motion.
3. Frame rate locked at 60fps on the actual 8GB box for the full hole, memory total under 7.0GB.
4. The swing reads as a real swing on a phone screen; the ball flight matches the sim's carry within 5 yd.
5. **Mason's eye test.** He has rejected the web build's graphics three times; the slice is not green until he says it looks good. His call, not the builder's.

If the slice fails (1), (3), or (5), the fallback is Unity URP (§1.1 rank 2) — not more effort on a failing Godot scene, and not UE on this box.

---

## 6. Build order with exit criteria

| Step | Work | Exit criteria |
|------|------|---------------|
| **0. Measure the box** | Record the 8GB MacBook Pro's exact chip (M1/M2/M3/M4), macOS version, free disk, idle memory pressure. Confirm Godot 4.7 runs and which Metal version it picks (Metal 4 on macOS 26, Metal 3 otherwise). | Chip + macOS + Metal version recorded in this doc. If M1 + older macOS, the Mobile renderer is the baseline expectation, Forward+ is the stretch. |
| **1. Skeleton + bus client** | Godot project, GDScript WebSocketClient → `ws://localhost:4456`, envelope parsing, `round_state` snapshot consumption, auto-reconnect. Confirm the exact payload field list against `sim/engine.py` + `bus/translate.py`; add any missing strike fields (ball speed, launch angle, azimuth, backspin, carry, apex, landing) on the sim side. Verify the bus server accepts multiple simultaneous clients. | Connects, receives all 12 envelope types, reconnects cleanly, re-syncs from `round_state`. A log line per event type, no rendering yet. |
| **2. Terrain** | Terrain3D import of the Hole 12 heightmap (or scripted-mesh fallback), orientation verified vs the hillshade, tee/green flatten, pond carve, bunkers. | Side-by-side vs hillshade matches; tee 6 m above green; pond basin in front of the green; before/after screenshots in the repo. |
| **3. Look-dev** | Sky, sun, LightmapGI bake, fog, water shader, terrain texture layers, grass, trees. | A 10-second still + clip of the hole from the tee camera that survives Mason's eye test on a phone. |
| **4. Golfer + ball flight** | Character import, idle, video-derived swing, ball arc interpolation from `strike`/`apex`/`landing`, tracer handoff to NodeCG. | Swing reads real on a phone; ball carry within 5 yd of sim; 60fps held. |
| **5. Putting** | Green heightfield import from `sim/greens.py`, `putt_read` path draw, `putt_result` actual path + ball animation. | Putt paths match solver numbers; read-vs-reality visible on screen. |
| **6. Conditions, 59 Watch, pins** | Wind flag + sway, firmness/green-speed visuals, 59 Watch state, pin from `hole_start`. | Every state renders from events only; no invented state. |
| **7. OBS integration** | Borderless 1920×1080 Godot window, ScreenCaptureKit window capture, NodeCG overlays composited as today, replay buffer, watchdog memory check (7.0GB) + freeze detection + web-fallback scene. | Full round at locked 60fps, zero dropped frames, total memory <7.0GB, fallback switch tested by killing the Godot player mid-round. |
| **8. Soak** | 7-day autonomous run **alongside** the web build (web stays live; Mac build records to disk). | Zero crashes, zero sim/renderer desyncs, memory stable across the week, no watchdog sheds beyond level 2. |
| **9. Cutover** | Mac build becomes the stream; web build becomes fallback + clip factory. | Mason's call, after watching the soak footage. Not automatic. |

**No step starts before the previous step's exit criteria are met.** In particular, no 18-hole work starts before the Hole 12 slice passes §5.5.

---

## 7. What stays on the web build vs what moves to the Mac

| Piece | Stays web | Moves to Mac (Godot) | Notes |
|-------|-----------|----------------------|-------|
| The golf world (terrain, golfer, ball, sky, water) | — | **Yes** | The whole point of this design. |
| Sim engine (`sim/`) | — | — | **Neither.** The sim stays Python on the box, feeding both renderers through the bus. It is engine-agnostic by design. |
| Event bus (`bus/`, port 4456) | — | — | **Neither.** Unchanged; Godot is a new client. |
| Commentary (MLX + Kokoro) | — | — | **Neither.** Unchanged. |
| NodeCG overlays (score bug, 59 Watch, leaderboard, coins) | **Yes — but they composite in OBS over the Godot picture** | — | The overlay bundle does not change; only the video layer underneath it changes. |
| Clip pipeline + ffmpeg assembler | **Yes** | — | Clips come from OBS's replay buffer either way; the pipeline is capture-source-agnostic. |
| Prototype / fast iteration | **Yes** | — | New features land in the web build first (hours, not days), get proven there, then port to Godot. The web build is the sketchbook. |
| Fallback stream | **Yes** | — | The web build keeps running warm until cutover, and stays as the OBS fallback scene after cutover. If Godot dies, the stream falls back to the web build, not to black. |
| Landing page (`mas-golfs` artifact) | **Yes** | — | Unchanged. |

**The web build is not deleted, deprecated, or frozen.** It is the prototype, the clip factory, and the fallback. The Mac build is the live picture. Both run off the same sim and the same bus.

---

## 8. Risks and open questions

1. **Exact chip and macOS version unknown.** Everything in §2 is sized for a base M1. If the box is an M1, Forward+ at 1080p60 with full look-dev is a stretch target and the Mobile renderer may be the real baseline. Step 0 resolves this before any look-dev work.
2. **Terrain3D 16-bit PNG import unverified.** The plugin is the standard path, but the 16-bit import must be verified in Step 2; the scripted-mesh fallback is documented and cheap.
3. **Syphon is a stretch, not a promise.** Godot has no built-in Syphon output. Window capture is the primary path and is sufficient; Syphon is only a latency polish item.
4. **The swing is the highest-risk asset.** MediaPipe → Blender retarget → glTF is a real pipeline with real failure modes (foot slide, joint flips, timing). Budget the most iteration time here, and judge it on a phone.
5. **Trees will still be the weakest element.** Godot improves them (instancing, wind, real shadows) but does not solve them. The camera stays at broadcast distance for a reason.
6. **Godot 4.7 is the current stable line; 4.8 is in beta.** Pin the exact Godot version at Step 1 and do not upgrade mid-build.
7. **The 18-hole course is a second project.** Each additional hole needs its own 505 m LiDAR tile (same pipeline as `docs/research/terrain-lidar-prep.md` §8), its own green heightfield, and its own look-dev pass. The slice deliberately proves the pipeline once, on one hole, before any of that is committed.
8. **UE vertical-slice design is not discarded.** `docs/unreal-vertical-slice.md` stays the GPU-box path. If a GPU box ever enters the picture, the Hole 12 terrain work (same heightmap, same provenance) transfers directly — the LiDAR prep was engine-agnostic by design.

---

## 9. What this design does not decide

- **Whether to cut over.** That is Mason's call after the soak (§6 Step 9), based on footage he has watched.
- **Whether to buy anything.** Nothing in this design costs money. If a paid asset ever looks necessary, that is a separate ask.
- **The GPU-box / UE question.** Unchanged: UE on a GPU box is the long-term ceiling, still unapproved, still $0 spent.
- **Anything about the sim's numbers.** Course rating, variability, the fat left tail, the 10,000-round QA gate — those belong to the sim workstream and are unaffected by the renderer choice.

---

*Design only. No code was written for this document. No files were pushed. The 16GB MacBook Air was not touched.*
