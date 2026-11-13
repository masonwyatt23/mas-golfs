# Mas Golfs — Unreal Engine 5.8 One-Hole Vertical Slice

**The goal:** prove the look before building 18 holes. One hero hole in UE 5.8, fully playable by the autonomous golfer, rendered and broadcast end-to-end — and judged against the 2K / Tiger Woods / GTA 6 bar on real footage. If the slice clears the bar, it becomes the template for the full course. If it doesn't, we find out on one hole, not eighteen.

**Status:** plan only. No code, no assets, no purchases made. All prices verified Nov 12, 2026 — re-check before spending anything.

---

## 1. The hero hole

**Hole 12 — "The Picture." Par 3, 172 yards, Wyatt National.**

- Downhill tee shot over a pond to a green framed by pines. Wedge in hand, water in mind.
- **Why this hole:** smallest scope with the maximum visual payoff. One tee shot exercises everything that matters — elevation, water carry, the Niagara tracer arcing over the pond, the green-side camera, the putt, the reaction. It shows off terrain, water, vegetation, sky, and the golfer in a single 90-second loop. A par 5 would prove more shot variety but triples the build (three landing areas, a fairway, a lay-up zone); hole 12 proves the *look*, which is what the slice exists to judge.
- **Stretch candidate if 12 goes fast:** Hole 2, "The Reach" (par 5, 578 yds, dogleg left around a lake) — it adds a drive, a risk-reward second shot, and a lay-up decision. Do not start it until 12 passes go/no-go.

**What the slice must show, in one loop:** Mas walks to the tee → addresses the ball (down-the-line cam) → decision line in commentary → full swing → ball flight with glowing tracer over the water → landing on the green (pin cam) → walk to the green → putt(s) → hole-out reaction → scorebug update → next loop begins (new wind, new pin, new result). The loop must run unattended for at least 1 hour with no crash, no stall, and no repeated identical shot.

---

## 2. Software list — exact versions and costs

| Item | Version / source | Cost |
|------|------------------|------|
| Unreal Engine | **5.8** (June 17, 2026 — latest major release; last planned 5.x before UE6 early access late 2027). Download from Epic Games Launcher. | $0 — free under $1M lifetime gross revenue (games) / $1M annual (non-game commercial). Above that: 5% royalty over $1M, or $1,850/seat/year for non-game commercial use. |
| DLSS 4.5 plugin for UE | **v8.9.0** (Oct 16, 2026), official NVIDIA plugin — Super Resolution, Ray Reconstruction, Multi Frame Generation, DLAA, Reflex. Download from developer.nvidia.com (UE 5.8 build). | $0 |
| Quixel Megascans | Full library (~23,000 assets) on Fab. **Free since Nov 5, 2026, no end date** (listings finished updating Nov 12, 2026). Fab Standard License, commercial use included; AI training now permitted. | $0 |
| Quixel Megaplants | Procedural Nanite-compatible trees, editable in the Procedural Vegetation Editor. Free under Fab Standard License. | $0 |
| Ultra Dynamic Sky | Fab, by Everett Gunther. **$49.99**, 4.9/5 (1,319 reviews). Single Time-of-Day variable drives sun, moon, volumetric clouds, rain, lightning; Lumen-integrated. | **$49.99 — the only purchase in the slice** |
| SkyScape (fallback) | Fab, $19.99, UE 5.0–5.6 compatible — use only if UDS has a 5.8 compatibility problem at build time. | $19.99 if needed |
| MetaHuman | Free, browser-based MetaHuman Creator (60+ presets, 72-bone face rig, hair/cloth). Standard Mannequin skeleton, so all UE5 animation tooling applies. | $0 |
| GASP (Game Animation Sample) | Free Epic sample, updated for 5.8 — 500+ AAA mocap clips, Motion Matching locomotion (walk, turns, idle). ~0.5 ms worker-thread cost per character. | $0 |
| Cesium for Unreal | Free, Apache 2.0 — streams Cesium World Terrain, Bing imagery, Google Photorealistic 3D Tiles. **Backdrop only** (see §3). | $0 |
| NodeCG | Open source — HTML/CSS/JS broadcast graphics as OBS browser sources, replicants over WebSocket. | $0 |
| OBS Studio 33 | Free, with obs-websocket bundled since v28 (JSON-RPC on port 4455). | $0 |
| Sim engine | Python (existing Mas Golfs sim — see `docs/sim-engine.md`). Emits JSON events; no license cost. | $0 |
| Houdini (terrain prep) | Houdini Engine for Unreal / Houdini Indie. **Houdini Indie is $269/year** — budget it only if the team chooses Houdini over the free path (§3). The free path (PDAL/GDAL + QGIS + Gaea free tier or Terrazed) covers the slice. | $0 for the slice (free path) |
| **Total software cost for the slice** | | **$49.99** |

> **Do not buy anything else for the slice.** No other paid assets, no mocap software licenses, no cloud services. If a line item appears that isn't in this table, it needs a reason written down before it's purchased.

---

## 3. Terrain pipeline — USGS 3DEP LiDAR → heightmap → Unreal

Wyatt National is a fictional course, so there is no real-world LiDAR of it. The pipeline uses **real LiDAR of analogous terrain** (Blue Ridge / Shenandoah Valley, Virginia) as the base landform, then hand-authors the golf features on top. That gives real elevation character for free instead of sculpting a mountain from nothing.

### 3.1 Pick the site (Day 1)

1. Open the USGS National Map / 3DEP viewer and pick a 1 km × 1 km tile of rolling Virginia foothill terrain with a natural valley and a water feature — the closest real analogue to hole 12's downhill-over-a-pond shape.
2. Download the **1 m DEM** (GeoTIFF) and, if available, the **LAS/LAZ point cloud** for the same tile. Both are public domain, no account needed.
3. Record the tile coordinates, DEM resolution, and download date in the repo (`docs/unreal-vertical-slice.md` appendix or a `terrain/SOURCE.md`). Reproducibility matters — the full 18-hole build will need 18 more tiles from the same region.

### 3.2 Heightmap prep (Day 1–2) — free path

1. **PDAL + GDAL** (both free, command-line): convert LAS → ground-classified DEM if the point cloud is used; otherwise take the 1 m DEM GeoTIFF directly.
2. **QGIS** (free): clip to the hole-12 footprint (~500 m × 300 m at 1 m resolution), reproject to a local metric CRS, export a **16-bit PNG heightmap** (Unreal's Landscape import format). Verify no nodata holes in the clip — fill any with QGIS interpolation before export.
3. **Gaea 2.0** (free Community tier) *or* **Terrazed** ($26.99 one-time, only if Gaea can't do the job): generate the **layer masks** — fairway, rough, green, bunker, water table, cart path — from slope/height rules plus hand-painted corrections. Export masks as 8-bit PNGs at the same resolution as the heightmap.
4. **Hand-author the golf features.** This is the step that makes it a golf hole instead of a hillside: flatten the tee box and green to their design elevations (tee ~8 m above the green for the downhill par 3), carve the pond basin, shape the front bunker and the green's two tiers, and grade the surrounds so balls feed toward the green, not away from it. Do this in Gaea's sculpt tools or directly in Unreal's Landscape sculpt mode — whichever the builder is faster in. Keep a before/after screenshot pair in the repo.

### 3.3 Import into Unreal (Day 2–3)

1. Create the UE 5.8 project from the **Blank** template (no starter content — everything comes from Fab/Quixel).
2. **Landscape import:** import the 16-bit PNG heightmap as a Landscape (recommended: 505×505 or 1017×1017 vertices for the hole footprint; 1 m per vertex). Apply the layer masks as Landscape layers.
3. **Do not use Cesium for the course surface.** Global terrain tiles are too coarse for greens and bunkers — the LiDAR heightmap plus hand-authoring is the course. Cesium is for the surrounding mountains, skyline, and horizon only (a Cesium World Terrain + Bing imagery backdrop beyond the hole boundary, so the horizon looks infinitely real).
4. **Mesh Terrain (Experimental in 5.8)** is the alternative to Landscape if the team wants denser geometry at points of interest — evaluate it in week 1, but default to Landscape: it is proven, and Mesh Terrain is experimental. Record the decision and why.
5. **Landscape material:** Substrate master material with Megascans layers — bent-grass green, fairway, rough, sand, rock, cart path. Mow stripes via the fairway layer's stripe mask, not geometry. Dew/wetness via Substrate multi-layer blending (morning dew on the green is the showcase detail — verify it reads on camera before calling the material done).

### 3.4 Water

- Pond: a planar water surface with a Substrate water material (translucency + reflections), a sandy shoreline ring (Megascans sand + a darker wet-sand band at the waterline), and a slight normal ripple. The pond must read as water from the tee cam at 172 yards — test from the actual broadcast camera, not the editor viewport.
- Ball-in-water behavior: the sim already emits the outcome; the render needs a splash (Niagara sprite emitter) and the drop/penalty flow in the broadcast. Scope it, don't skip it — water is the hole's identity.

---

## 4. Vegetation and materials

### 4.1 Trees — the hard part (budget real time here)

The web prototype's trees are the weakest visual element (flat low-poly blobs). The slice must prove trees can look real. This is the highest-risk item in the plan — see §10.

1. **Megaplants** (free, Nanite-compatible) as the base: Virginia species — loblolly pine, white oak, red maple. Grow variants in the **Procedural Vegetation Editor (Experimental in 5.8)** — biologically correct branching, Nanite-ready, wind response via Nanite Skinning.
2. **Placement:** PCG (Procedural Content Generation) scatter with hand-placed hero trees framing the green and the tee. Rules: no tree inside the line of play, canopy gaps that frame the green from the tee (the "picture" in "The Picture"), denser tree line on the hole's outer boundary, sparser near the pond so the water reads.
3. **Validation:** screenshot the tree line from the tee cam, the pin cam, and the aerial cam. Trees must show layered branch structure, trunk detail, and natural silhouette variation — not cones, not spheres, not blobs. If PVE output still reads as blobs at broadcast distance, fall back to hand-placed Megascans tree meshes with manual LOD tuning, and record what failed.
4. **Grass:** Nanite Foliage (experimental in 5.7, carried into 5.8) for ground clutter and fairway blade detail — dense where the camera is close (tee, green), sparse at distance. Wind response on, tied to the sim's wind state so the grass moves with the same wind that moves the ball.

### 4.2 Materials (Substrate, production-ready in 5.7)

- **Green:** bent grass with dew layer, mow stripes, ball-mark divots (decals, spawned on landing).
- **Fairway/rough:** Megascans grass surfaces, rough visibly longer and darker than fairway — the fairway/rough boundary must be legible on camera at 100+ yards.
- **Sand:** raked texture with footprint/rake lines, wet band near the pond edge.
- **Rock/cart path:** Megascans rock and path surfaces; the cart path drapes the terrain, it does not float above it.
- **Sky:** Ultra Dynamic Sky — one Time-of-Day variable driving sun, clouds, and atmosphere. Golden-hour default (matches Mason's swing video). Volumetric clouds are expensive — profile early; 2D cloud modes are the fallback if frame time blows out.

---

## 5. MetaHuman Mas — and the swing mocap gap

### 5.1 The character

1. Build Mas in **MetaHuman Creator** (free, browser-based): left-handed golfer, late-20s, athletic build, dark hair, cap. Match the reference: navy polo, khaki shorts, white shoes, black cap — the outfit from Mason's swing video is the *default* outfit; the customization system comes later.
2. MetaHuman rides the standard Mannequin skeleton, so GASP locomotion (walk, turns, idle, address stance) applies directly via Motion Matching — no state-machine snapping between walking and addressing the ball.
3. **Cloth:** polo wrinkle and cap behavior via Chaos Cloth (production-ready in 5.8). Keep cloth simulation scoped to the polo and cap — full-body cloth is a performance trap.

### 5.2 The swing — the honest gap

**There is no off-the-shelf golf-swing mocap pack in GASP or on Fab.** This is a discrete workstream, not a detail. Three options, in order of preference:

| Option | What it is | Cost | Quality | Recommendation |
|--------|-----------|------|---------|----------------|
| **A. Mocap shoot (recommended)** | Half-day **Xsens** (inertial) or **Rokoko** (inertial) session capturing Mason's actual swing: address, waggle, takeaway, backswing, transition, impact, follow-through, held finish — plus walk, ball-mark repair, cap tip, and reaction animations. | Xsens/Rokoko suit rental or studio half-day: budget **$1,500–$4,000** depending on market; get quotes before committing. | Highest — it is literally his swing, and it is the differentiator. | **Do this for the full build. For the slice, it is optional — see below.** |
| **B. Video-derived** | AI pose estimation from Mason's swing video (Sportsbox-style video-to-3D) retargeted to the MetaHuman rig. | Near $0 (software + time). | Medium — good tempo and shape, weaker on joint detail and weight shift. | **Use for the slice.** It proves the pipeline end-to-end with zero spend, and the mocap shoot replaces it for the full build. |
| **C. Hand-keyed** | Animator hand-keys the swing in Sequencer/Control Rig from the video reference. | Time only. | Lowest — readable but never quite human. | Fallback only if B fails. |

**Slice decision:** use **Option B** for the vertical slice. The slice exists to judge the *look* — a video-derived swing is good enough to judge whether the broadcast reads as real golf. The mocap shoot (Option A) is green-lit only at the go/no-go gate, as part of the full-build commitment. Do not spend mocap money before the slice passes.

### 5.3 Swing integration

- Retarget the swing (from B) onto the MetaHuman via Control Rig. Keyframes must hit: quiet address with waggle → wide takeaway → full shoulder turn against resisting hips → lag-loaded transition → **impact at exactly the ball-strike frame** → high balanced finish held on the lead leg.
- The sim emits the `strike` event; the animation and the ball launch must share the same frame. A 2-frame mismatch between club and ball is visible on camera — verify with slow-motion capture during validation.
- **Left-handed by default.** The swing is mirrored from Mason's left-handed video. Right-handed mode is a full-build feature, not a slice feature.

---

## 6. Camera / director setup in Unreal

The broadcast director from `docs/broadcast-stack.md` ports directly — the sim's JSON events drive it, the render engine changes underneath.

### 6.1 Camera positions (CineCameraActor, never standard game cameras)

| Camera | Position | Lens | Job |
|--------|----------|------|-----|
| Tee / down-the-line | Behind Mas, on the target line | 70–200 mm telephoto | Address, swing, impact. Telephoto compression flattens the background pines against the player — the broadcast look. |
| Tracer cam | Tracking the ball | 200–400 mm | Ball flight, tracer ribbon. Holds through the entire flight — never cut mid-flight. |
| Pin cam | Green-side, low | 70–200 mm | Landing, roll-out, green-side drama. |
| Aerial / drone | High, slow orbit | 24–35 mm wide | Between holes: hole flyover + player card. |
| Reaction cam | Green-side, on Mas | 85 mm | Hole-out reaction, cap tip, scorebug lower-third. |

- **Lens simulation:** aperture f/2.8–f/4 for shallow depth of field on the tee and reaction cams; deeper focus on the tracer cam so the ball and the green stay sharp together.
- **Camera movement:** spring-arm damping + micro-shake on tracking cameras to mimic a human operator panning a heavy broadcast lens on a fluid-head tripod. No instant snaps, no game-camera glides.
- **Cuts:** the director state machine from the broadcast-stack doc (phase → camera map, 2–3 s minimum hold, cut on events never on a clock, drama-scored 0.5× slow-motion replays). The director lives in the sim/event bus, not in Unreal — Unreal only receives "cut to camera X" commands. That separation is what lets the same director drive the web build today and the Unreal build tomorrow.

### 6.2 Tracer and effects (Niagara, enabled by default in UE5)

- **Ball flight:** Niagara ribbon renderer — particles along a spline + ribbon = continuous glowing trail, fed by real-time ball telemetry from the sim. Color and glow scale with drama (a birdie-bound tracer reads differently from a ball heading for the pond).
- **Divot / sand / splash:** standard Niagara sprite/mesh emitters, triggered by the `landing` event with the lie as a parameter.
- **Green grid:** projected slope heatmap + putting line on the green for putts (the broadcast's second-screen signature).

---

## 7. Sim-engine JSON integration

The sim engine (Python, see `docs/sim-engine.md`) is unchanged — it already emits typed JSON events. The slice wires those events into Unreal:

```
Sim engine (Python) ──JSON events──▶ Event bus (local WebSocket, port 4456)
   ├─▶ Unreal: camera cuts, MetaHuman animation triggers, Niagara tracer, ball spawn
   ├─▶ NodeCG replicants ──OBS browser sources──▶ scorebug, leaderboard, lower-thirds
   ├─▶ Commentary LLM ──TTS──▶ OBS audio (2 voices, event-only)
   └─▶ Clip pipeline (replay-buffer saves)
OBS ──RTMP──▶ Restream ──▶ YouTube Live + Twitch (+ watchdog auto-restart)
```

- **Event envelope:** the same 11 typed events from the broadcast-stack doc (`round_start`, `hole_start`, `decision`, `shot_start`, `strike`, `apex`, `landing`, `putt_result`, `hole_end`, `milestone`, `round_end`) plus the `round_state` snapshot as the single source of truth.
- **Timing contract:** the `strike` event and the ball launch share a frame; the `apex` event fires the Color commentator's line; the `landing` event fires the pin-cam cut and the tracer fade. Latency budget: sim → Unreal < 50 ms on the local machine. Measure it during validation; if it exceeds 50 ms, the commentary will land late and the broadcast will feel off.
- **Fallback:** if the event bus drops, Unreal holds the wide aerial cam and the sim keeps playing — never cut to black, never freeze the stream.

---

## 8. OBS + NodeCG playout

Same stack as the web build's broadcast plan (`docs/broadcast-stack.md`), running on the same GPU box as Unreal:

- **OBS Studio 33** captures the Unreal output (game capture, not display capture) at 1080p60, 8,000 Kbps.
- **NodeCG** graphics as OBS browser sources: scorebug, leaderboard, lower-thirds, ticker, player card, hole card — driven by replicants from the sim's JSON events.
- **Replays:** OBS replay buffer + Instant Replay plugin, 0.5× slow-motion on dramatic shots, auto-clip saves to `~/mas-golfs/clips/` for the clip pipeline.
- **Audio:** two-voice commentary (event-only, Kokoro self-hosted as the free default, ElevenLabs Flash as paid fallback), layered ambient bed (wind/bird, per-hole variation, impact/applause stingers), sidechain ducking under commentary.
- **Output:** OBS → Restream (free tier, 2 channels) → YouTube Live + Twitch over RTMP. Watchdog auto-restart on crash; stream-health alerts.
- **Compliance:** YouTube AI-use disclosure set from day one; "Mas is Mason's digital twin" visible on screen.

---

## 9. Performance targets and validation

### 9.1 Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Internal render resolution | **1440p** | DLSS Quality/Performance upscales to 4K60 output. Do not target native 4K — only an RTX 5090 exceeds 60 fps at native 4K Ultra in current UE 5.7 titles, and the slice runs on a 4090. |
| Output | **4K60** via DLSS 4.5 (Super Resolution + Ray Reconstruction) | Validate DLSS presets on the slice's own content — Ray Reconstruction v2 has been reported to denoise away normal-map detail in some UE 5.7 titles. DLSS 4 Super Resolution is the safe default if RR misbehaves. |
| Frame time | Locked 60 fps, < 16.6 ms average, no sustained dips below 50 fps | Lumen Lite (Beta, ~2× faster than Lumen High) is the default GI mode for the slice. Full Lumen High is the stretch goal, not the baseline. |
| Lighting | Lumen Lite + hardware ray-traced reflections | Path Tracer is production-ready but **offline only** — never plan a live path-traced pipeline. |
| Latency | Sim → Unreal < 50 ms; pipeline latency to stream < 2 s acceptable (nobody is playing the game) | MFG latency is irrelevant for a broadcast. |
| Uptime | 1-hour unattended soak with zero crashes, zero stalls, zero repeated identical shots | The slice's reliability gate. |

### 9.2 Validation checklist (all must pass before go/no-go)

**Visual — judged on captured footage, not the editor viewport:**
- [ ] Tee-cam frame reads as a golf broadcast, not a game: telephoto compression, shallow depth of field, natural greens (no oversaturated video-game green).
- [ ] Trees show layered branch structure, trunk detail, natural silhouette variation — from tee cam, pin cam, and aerial cam. No cones, no spheres, no blobs.
- [ ] Water reads as water from the tee at 172 yards; splash on a ball in the pond.
- [ ] Grass: fairway/rough boundary legible at 100+ yards; green shows mow stripes and dew.
- [ ] Sky: volumetric clouds (or 2D fallback) with correct sun angle for golden hour; dawn-to-dusk grading works.
- [ ] Mas: human proportions, proper cap, polo, glove on lead hand; swing reads as a human swing in slow motion; impact frame matches ball launch (≤ 1 frame error).
- [ ] Tracer: glowing ribbon, correct arc, fades on landing; shot-data lower-third fires on strike.

**Broadcast:**
- [ ] Director cuts on events only; no mid-flight cuts; minimum holds respected; 0.5× replay triggers on drama and returns to live.
- [ ] Scorebug tells a newcomer the story in 3 seconds (hole, score to par, Road to 59 target).
- [ ] Commentary: decision line before the shot, result line at apex/landing, never speaks over the swing.
- [ ] Ambient bed never goes silent; stingers fire on impact and applause.

**Simulation:**
- [ ] Shot outcomes match +3 calibration (driving, GIR, proximity, putting) over a 20-round sample.
- [ ] No two consecutive rounds identical; wind, pin, and form vary the loop.
- [ ] Learning loop surfaces exactly one fix per round.

**Reliability:**
- [ ] 1-hour unattended soak: zero crashes, zero stalls, stream stays live.
- [ ] Watchdog restarts OBS and re-establishes the stream after a forced kill (test it — don't assume it).
- [ ] AI-use disclosure set on the YouTube test stream.

---

## 10. Hardware options

The slice renders on **one GPU, once, broadcast to everyone**. Unreal cannot run in a browser, and pixel-streaming to every viewer would need a GPU per viewer — ruinous. One render, one RTMP feed, platforms distribute.

| Option | Cost | Notes |
|--------|------|-------|
| **RunPod Community Cloud, RTX 4090** | **$0.34/hr ≈ $248/mo** for 24/7 (730 hrs). Evictable spot — fine for build/test, risky for a live 24/7 stream. | Cheapest way to *build* the slice. |
| **RunPod Secure Cloud, RTX 4090** | **$0.74–$0.89/hr ≈ $540–$650/mo** for 24/7. T3/T4 data center, stable. | The safe cloud option for a live 24/7 stream. (Rates vary by source and date — re-check runpod.io/pricing before committing.) |
| **Own RTX 4090 box** | **~$2,500–$3,000 one-time** + ~$35–52/mo power. | Pays for itself in 3–6 months of 24/7 use vs. Secure Cloud. The recommended option once the slice passes go/no-go. |
| **Vast.ai RTX 4090** | From ~$0.14–$0.59/hr (marketplace, interruptible). | Cheapest raw compute; only for build/test, never for live. |
| **Local dev machine** | Whatever Mason already has — if it has an RTX 4070 or better, the slice can be built and validated locally for $0. | **Build the slice here first.** Cloud spend starts only when the slice needs 24/7 uptime. |

**Slice hardware plan:** build and validate on the local dev machine (or a short RunPod Community rental for heavy profiling). Zero 24/7 spend until the go/no-go gate passes.

---

## 11. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Trees still read as blobs in UE | **High** — this is the known weak point from the web build | Slice fails the visual bar | Budget the most time here; PVE first, hand-placed Megascans fallback; judge on broadcast-camera footage, not editor view; if trees can't be fixed in the slice, the full build's art direction changes (fewer, better trees; more open sightlines) |
| PVE / Mesh Terrain experimental instability | Medium | Crashes, API changes | Default to proven paths (Landscape, PCG scatter); experimental features only where they have a fallback |
| Volumetric clouds blow the frame budget | Medium | Dropped frames on stream | 2D cloud fallback ready from day one; profile clouds in week 1, not week 4 |
| DLSS Ray Reconstruction artifacts on foliage | Medium | Denoised-away detail, flicker | Validate presets on slice content; DLSS 4 SR as safe default; MFG off until the base image is clean |
| Video-derived swing reads as robotic | Medium | Golfer looks like a mannequin | Accept for the slice (it judges the look, not the swing); mocap shoot is the full-build fix, already budgeted |
| Event-bus latency makes commentary land late | Low | Broadcast feels off | 50 ms budget, measured in validation; local WebSocket, no network hops |
| Scope creep: "just add one more hole" | **High** | Slice never finishes | Hard rule: one hole. Hole 2 is a stretch candidate only after 12 passes go/no-go. |
| 24/7 cloud cost surprises | Medium | Budget overrun | Slice has zero 24/7 spend; cloud pricing re-checked before any commitment; own-box payback math in §10 |
| UE6 early access distracts the build | Low | Wasted migration effort | Target 5.8, the last planned 5.x. Do not migrate mid-build. |

---

## 12. Build order (weeks 1–4)

| Week | Work | Exit criteria |
|------|------|---------------|
| **0 — Setup** | Install UE 5.8, DLSS 4.5 plugin, UDS ($49.99). Create project, Git repo, folder structure. Pull Megascans/Megaplants packs. | Project opens, UDS sky renders, one Megascans material applied. |
| **1 — Terrain** | Pick USGS tile, prep heightmap + masks (PDAL/GDAL/QGIS/Gaea), import Landscape, hand-author tee/green/pond/bunker, Cesium backdrop. | Hole 12's landform reads from the aerial cam; pond basin holds water. |
| **2 — Vegetation & materials** | PVE trees, PCG scatter, hero-tree placement, Nanite foliage, Substrate master material, water material. | Tree-line screenshot from tee cam passes the "real trees" test (see §9.2). |
| **3 — Character & cameras** | MetaHuman Mas, video-derived swing retarget, GASP locomotion, 5 CineCameraActors, director wiring to the event bus, Niagara tracer. | One full shot loop plays end-to-end in-engine: address → swing → tracer → landing → putt → hole-out. |
| **4 — Broadcast & validation** | NodeCG graphics, OBS scenes, commentary pipeline, ambient audio, replay triggers, 1-hour soak test, validation checklist (§9.2), go/no-go review. | All checklist boxes ticked or explicitly waived with reasons; go/no-go decision recorded. |

**Total: 4 weeks for the slice** (one builder, with agents assisting on docs, configs, and NodeCG templates — UE editor work is binary assets and cannot be parallelized the way text can). The full 18-hole build is months, even with agents.

---

## 13. Go / no-go criteria

The slice passes — and the full build is green-lit — **only if all of these hold on real captured footage:**

1. **A stranger who plays golf believes it is a broadcast.** Show the tee-cam footage to a golfer with no context. If they ask what tournament it is, it passes. If they say "nice game," it fails.
2. **The trees pass.** Layered branch structure, trunk detail, natural silhouettes from all three broadcast cameras. This is the known weak point; it gets its own explicit vote.
3. **Mas's swing passes in slow motion.** Impact frame matches ball launch; the finish is held and balanced. (Video-derived is acceptable here — the mocap shoot improves it later.)
4. **The loop runs unattended for 1 hour** with no crash, no stall, no repeated identical shot, and the stream stays live.
5. **Performance holds:** locked 60 fps at 1440p internal with DLSS to 4K60 on the target GPU, no sustained dips below 50 fps.
6. **The broadcast layer works:** director cuts, scorebug, commentary timing, replays, and the Road to 59 target all fire correctly.

**If it fails:** the review records exactly which criterion failed and what changes. The options are (a) one more week on the failing item, (b) change the art direction for that item (e.g., fewer trees, different species, different camera framing), or (c) stop the Unreal build and keep improving the web build. **Do not** start hole 2, buy hardware, or book a mocap shoot until the slice passes.

**If it passes:** green-light in this order — (1) own RTX 4090 box or Secure Cloud pod for 24/7, (2) mocap shoot for Mas's swing, (3) holes 1–18 in batches of 3, reusing the slice as the template, (4) full broadcast launch on YouTube Live + Twitch.

---

## 14. What stays live while this is built

The web build is the always-on prototype and clip factory. **Do not take it down to "wait for Unreal."** It keeps streaming, keeps clipping, keeps growing the audience — and the audience it builds is the audience the Unreal broadcast launches to.

---

## Appendix A — Sources (verified Nov 12, 2026)

- Unreal Engine 5.8 release (June 17, 2026; last planned 5.x; Lumen Lite ~2× faster than Lumen High; MegaLights production-ready; Mesh Terrain and PVE experimental; MetaHuman Collections experimental): https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available
- UE 5.8 feature status (Substrate production-ready in 5.7; Lumen Lite Beta; UE6 early access late 2027): https://andrewaltimit.github.io/Documentation/docs/technology/unreal.html
- Quixel Megascans free on Fab (announced Nov 5, 2026; ~23,000 assets; listings free by Nov 12; Fab Standard License; AI training permitted): https://www.cgchannel.com/2026/11/epic-has-made-megascans-free-again-for-good-this-time/ and https://quixel.com/
- Ultra Dynamic Sky, $49.99, 4.9/5 (1,319 reviews): https://www.fab.com/listings/84fda27a-c79f-49c9-8458-82401fb37cfb
- DLSS 4.5 UE plugin v8.9.0 (UE 5.8 build, Oct 16, 2026; Super Resolution, Ray Reconstruction, Multi Frame Generation, DLAA, Reflex): https://developer.nvidia.com/rtx/dlss.md
- RunPod RTX 4090 pricing (Community $0.34/hr, Secure $0.74–$0.89/hr; checked Nov 9–11, 2026 — re-check before committing): https://www.stork.ai/en/runpod and https://gpuwerk.com/private-llm-hosting/vs/runpod/
- Unreal licensing (free under $1M; 5% royalty above; $1,850/seat/year non-game commercial over $1M/year): https://www.unrealengine.com/license — *verify at build time; summarized here from prior research, not re-fetched for this plan.*
- USGS 3DEP (free 1 m DEMs and LAS/LAZ point clouds, public domain): https://www.usgs.gov/3d-elevation-program

## Appendix B — Related repo docs

- `docs/architecture.md` — the four-layer system (world, cinematography, overlays, commentary).
- `docs/broadcast-stack.md` — OBS scenes, director state machine, NodeCG graphics, commentary pipeline.
- `docs/sim-engine.md` — shot physics, decision engine, learning loop, event schema.
- `docs/course-design-v3.md` — Wyatt National, all 18 holes (hole 12 is the slice's hero hole; 172 yards in v3).
- `docs/livestream-plan.md` — platforms, clip machine, growth timeline, free-tier rule.
- `docs/launch-playbook.md` — 90-day launch plan, clip formats, community mechanics.
