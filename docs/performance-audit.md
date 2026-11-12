# Mas Golfs — Performance & Smoothness Audit

**Audited file:** `~/workspace/mas-golfs-repo/index.html` (1,271,041 bytes, self-contained single-file 3D broadcast page)
**Audit date:** 2026-11-12
**Method:** static source analysis of the app code (90 KB, 666 lines) and the inlined Three.js bundle. No live profiling run was available to this audit — frame-time figures below are estimates from code inspection, not measured traces. Verify with Chrome DevTools Performance + `renderer.info` after the fixes (see P2-3).

**Staleness caveat — read first:** this export predates the latest artifact build. The file still says "ROAD TO 62" (current branding is Road to 59) and still uses cone-tier / sphere-lobe trees, not the leaf-card foliage from the most recent fidelity pass. The findings below apply to this snapshot; re-export and re-audit once the current build lands, especially the memory and terrain findings, which may have shifted.

## Verdict

The steady-state frame is in decent shape — instancing is used where it matters, there is no post-processing composer, DOM writes are event-driven, and the adaptive quality step-down exists. **But the build will not hold locked 60 fps on a mid-range laptop, and it will degrade on mobile, for three structural reasons:**

1. **Unbounded GPU memory growth** — every hole rebuild allocates ~20 geometries and ~15 materials and never disposes any of them. Infinite rounds × 18 holes = a guaranteed WebGL context loss on mobile, and slow degradation on desktop.
2. **A main-thread hitch on every hole change** — terrain is rebuilt from scratch (up to 33k vertices, per-vertex trig + `computeVertexNormals`) on the hole-transition frame.
3. **The most expensive GPU settings are on by default** — 2048² PCFSoft shadows, MSAA antialiasing, DPR up to 1.75 — with the only fallback being a one-way, late-triggering step-down.

Fix #1 and #2 first. Everything else is tuning.

---

## 1. What the frame actually costs (steady state)

### Geometry / draw calls

| Item | Cost per frame |
|---|---|
| Terrain | 1 draw call, **32k–66k triangles** (PlaneGeometry 110 × segZ, segZ = min(300, L/2); 171-yd par 3 ≈ 32k tris, 558-yd par 5 ≈ 66k tris) |
| Trees | 7 instanced meshes (trunks 120, 3 pine tiers × ~80, 3 lobes × ~40, bushes 60) |
| Grass tufts | 1 instanced mesh, 420 instances |
| Golfer | ~16 small meshes, **every part casts a shadow** |
| Bunkers, green, fringe, cup, pole, flag, markers, path, water | ~12–16 draw calls |
| Sky, ridges, clouds, sun glow | 1 + 3 + ~36 sprites + 1 |
| Ball, tracer line, particles, rain | 4 draw calls |
| **Total** | **≈ 55–65 draw calls + a shadow pass of ≈ 25–30 draw calls** |

Draw-call count is acceptable. Triangle count is dominated by one object (terrain). The shadow pass re-renders all 7 instanced tree meshes (up to ~840 instances) plus the golfer parts and markers every frame.

### Lighting & shadows

- 3 lights total (hemisphere + 2 directional) — good, no point/spot lights.
- **Shadow map: 2048×2048, PCFSoft, 110×110-unit ortho frustum** (near 10, far 420). PCFSoft is the most expensive shadow filter Three.js offers, and 2048² is a large map to re-render every frame — especially since the sun position and shadow target are moved to follow the action on every frame, so the shadow map can never be cached.
- ACES filmic tone mapping + sRGB output — correct, and cheap (in-shader, no composer).
- Water uses `MeshPhysicalMaterial` with clearcoat — the single most expensive material in the scene. It is one small mesh, so the cost is minor, but it is the obvious first material to downgrade on low tiers.

### Pixel fill

- `antialias: true` (MSAA) + DPR capped at `min(1.75, devicePixelRatio)`. On a phone with a 3x display that is still ~1M shaded pixels × MSAA — a meaningful mobile GPU load for a mostly-static scene.
- Fog (220–1600) hides the far field, which helps.

### Textures

- All textures are tiny canvas-generated maps (grass/sand 256², cloud 256×128, sky 4×256, dot 32²) with `RepeatWrapping`; grass repeats 110×340 with anisotropy 8. Texture memory is negligible. Anisotropy 8 is slightly generous for mobile but not a problem.

### Per-frame CPU work (`render3D` + `loop`)

The per-frame path is lean and mostly well written:

- `poseGolfer()` — pure joint-rotation math. Cheap.
- `updateCamera()` — smooth damped camera, cloud drift, flag wave, water shimmer. Cheap, but it allocates: `V3()` is `new THREE.Vector3`, called ~6–10× per frame, plus ~4 `.clone()` calls. Roughly **10–20 small allocations per frame** — minor GC pressure, trivially fixable with hoisted temp vectors.
- `pushTracer()` — preallocated 900-float buffer, `setDrawRange`, `needsUpdate` during flight only. Good.
- `updateParticles()` — iterates 240 particles, but sets `needsUpdate = true` **every frame even when zero particles are alive**, uploading the buffer pointlessly. Cheap to skip.
- Rain (when raining) — rewrites all 300 points and uploads every frame. Small (3.6 KB/frame), acceptable.
- `updateBug()` / `drawMap()` / scorecard / history renders are **event-driven** (hole transitions, shot resolution), not per-frame. Good — the 69 `textContent` and 18 `innerHTML` write sites look alarming in a grep, but none of them run in the hot loop. `drawMap()` does 280 speckle `fillRect`s per call, which is fine at event frequency.
- One `renderer.render()` per frame. No `EffectComposer`. Good.

### What is already good (keep it)

- Instancing for trees, tufts, bushes.
- DPR capped at 1.75.
- Tiny procedural textures; no external texture downloads.
- No post-processing chain.
- DOM writes event-driven; 2D map redrawn on events, not per frame.
- Preallocated tracer / particle / rain buffers.
- Golfer, ball, tracer, sky, clouds built once at boot.
- Adaptive quality step-down exists (see §3 for why it is not enough).

---

## 2. Finding P0-1 — GPU memory leak on every hole (fix first)

**Severity: critical. This is the finding that will actually break the product.**

`buildHoleScene()` starts with:

```js
while (holeGroup.children.length) {
  const c = holeGroup.children.pop();
  holeGroup.remove(c);
}
```

It removes the old hole's meshes but **never calls `.dispose()` on any geometry or material**. There are **zero `.dispose()` calls in the entire 90 KB app**.

Every hole rebuild allocates, and then orphans:

- Terrain `PlaneGeometry` (up to 33k verts) + a `Float32BufferAttribute` color array
- Fringe / green `irregularDisc` geometries, cup, pole, flag, 2 tee markers
- Per bunker: rim + dished pit geometries (each with its own `computeVertexNormals`)
- Shore + water geometries, cart-path geometry
- Tuft geometry + material; trunk / tier / lobe / bush geometries + **~10 materials**

That is roughly **~20 geometries and ~15 materials per hole, × 18 holes per round, × infinite rounds**. Three.js does not garbage-collect GPU buffers for removed objects — the buffers live until `dispose()` is called. The JavaScript objects become unreachable, but their GPU memory does not.

**Consequence:** GPU memory grows monotonically for as long as the stream runs. On iOS Safari and low-end Android (WebGL contexts commonly limited to a few hundred MB), expect a lost WebGL context — a black screen — after a few rounds. On desktop it degrades slowly and will eventually do the same. This directly contradicts the "runs forever" premise.

**Fix:** in the teardown loop, traverse each removed child and dispose its geometry and material(s) (materials may be shared — dispose per unique material, or track what `buildHoleScene` created). Better still, hoist the geometries/materials that never change (tuft/trunk/tier/lobe/bush geometries, sand materials, marker geometry) out of `buildHoleScene` and reuse them across holes; only rebuild what is genuinely hole-specific (terrain, green/fringe, bunkers, path).

---

## 3. Finding P0-2 — main-thread hitch on every hole change

**Severity: high. Visible stutter 18 times per round.**

`buildHoleScene()` runs synchronously on the hole-transition frame and does:

1. Terrain: `PlaneGeometry(190, L, 110, segZ)` — up to **33,111 vertices** — then a per-vertex loop doing `Math.hypot`, two `seeded()` calls (each a `Math.sin`), and `offsetHSL` per vertex, then `computeVertexNormals()` over up to 66k triangles.
2. ~1,200 instanced-matrix compositions (120 trees × 6 foliage slots + 420 tufts + 60 bushes), each calling `groundH()` (several trig calls).
3. Per-bunker `computeVertexNormals()` on dished pit geometries; cart-path vertex draping (91 vertices × trig).

Estimated cost: **~30–100 ms on a mid-range laptop, ~100–250 ms on a phone** — a dropped-frame spike at every single hole change, 18 times per round, forever. On mobile it will read as a freeze every few minutes.

**Fix (in order of preference):**
- **Cache per hole.** Hole layouts are seeded by `holeIdx`, so the terrain and scenery for hole *n* are identical every round. Build all 18 once (or lazily, one per round) and reuse them forever. Memory cost is 18 × ~33k-vert terrain ≈ 18 × ~1.6 MB of vertex data — acceptable, and it deletes the hitch entirely after round one.
- **If caching is too much memory:** build the *next* hole during the current hole's walk/putt phases (there are seconds of low-intensity time there), or chunk the vertex loop across frames. Never build it on the transition frame.
- **Reduce segments on mobile:** 110×300 is generous. 70×180 on the Lite tier loses almost nothing visually at broadcast distance and cuts the vertex work by ~60%.

---

## 4. Finding P1-1 — shadow cost is the biggest GPU line item

**Severity: high on mobile, medium on desktop.**

- 2048² PCFSoft shadow map, re-rendered every frame (sun follows the action), 110×110 ortho frustum, ~7 instanced caster meshes + ~16 golfer meshes + markers.
- PCFSoft is the most expensive filter; 2048² is large for a scene where the shadow-casting action occupies a small part of the frustum most of the time.

**Fix:**
- Tier it: High 2048² PCFSoft, Balanced 1024² PCFSoft, Lite 1024² PCF (or shadows off, as today).
- Tighten the ortho frustum to the action (it already follows the ball/golfer; ~70 units wide is plenty for the down-the-line view) — smaller frustum = sharper shadows for free.
- Only re-render the shadow map when something that casts has moved meaningfully (the golfer and ball move; the trees do not). Updating the shadow map every 2nd frame halves the cost with no visible difference at broadcast distance.

---

## 5. Finding P1-2 — adaptive quality is too late, one-way, and abrupt

**Severity: medium.**

What exists is a reasonable start: an EMA of frame time, and after 140 frames, if the average exceeds 46 ms, it drops pixel ratio to 0.65 and disables shadows. Problems:

- **Too late:** 46 ms average means the device has already suffered ~2.3 seconds at ~21 fps before anything happens. A weak device (or software renderer) gets a slideshow first.
- **One-way ratchet:** it never recovers. A device that hitches during load stays at 0.65 DPR forever, even if it could hold 60 fps afterwards.
- **Abrupt:** shadows toggle off instantly — a visible pop.
- **It changes nothing else:** terrain density, tuft count, cloud count, and water material stay at full cost.

**Fix:** boot-time capability check (mobile UA, `navigator.hardwareConcurrency`, `deviceMemory`, and the WebGL renderer string to detect SwiftShader/llvmpipe) to pick an initial tier — High / Balanced / Lite — before the first frame. Then a hysteresis controller: step down after ~1 s of bad frames, step back up after ~10 s of good ones. Fade shadows out over ~0.5 s instead of toggling. Add terrain-segment and tuft-count scaling to the tiers.

---

## 6. Finding P1-3 — no background pause (battery)

**Severity: medium for a product designed to run forever.**

There is **no `visibilitychange` handler**. The `requestAnimationFrame` loop keeps running when the tab is hidden (browsers throttle rAF to ~1 Hz in background tabs, but the loop, phase timers, and AudioContext keep going), and there is no frame-rate cap option. For a stream meant to sit on a second screen all day, that is the difference between a quiet background tab and a constant ~10–20 W GPU/CPU load.

**Fix:** on `document.visibilitychange` → hidden, stop the rAF loop and `AC.suspend()` the audio; on visible, resume. Also add a 30 fps "screensaver mode" toggle — halving the frame rate roughly halves GPU work for an ambient display, and nobody can tell at broadcast distance. Respect `prefers-reduced-motion` by defaulting to it.

---

## 7. Finding P1-4 — per-frame allocation churn (easy wins)

**Severity: low, but free to fix.**

- `updateCamera()` allocates ~10–20 `Vector3`s per frame via `V3()` and `.clone()`. Hoist module-scope temp vectors (`_v1`, `_v2`, …) and reuse them. Same for `ballWorldPos()` / `golferWorldPos()` if they allocate.
- `updateParticles()` uploads its buffer every frame even with zero live particles — guard the `needsUpdate` on `anyAlive`.
- `sunGlow.material.opacity` and `waterMesh.material.roughness` are written every frame — harmless, leave them.

Expected impact: less GC pressure, smoother frame pacing, especially on low-end Android where minor GC pauses are visible.

---

## 8. Finding P2-1 — first load: 1.27 MB blocking parse + external fonts

**Severity: medium for first impression, low for steady state.**

- The file is 1,271,041 bytes; ~1.15 MB of it is minified Three.js inlined in a classic `<script>` that blocks parsing. Parse + compile is roughly 150–400 ms on desktop, 500 ms–1.5 s on a mid-range phone, before `boot` even runs.
- Google Fonts (Playfair Display, Archivo, IBM Plex Mono — 3 families, multiple weights) are render-blocking external dependencies. Offline or on a slow network, first paint waits or falls back. The page already preconnects, but there is no `font-display: swap` control beyond what Google serves and no self-hosted fallback.
- No loading indicator before boot; no `renderer.info` instrumentation anywhere, so there is no way to measure real-world fps, draw calls, or triangles in production.

**Fix:** load Three.js as an external module (CDN with import map + SRI, or self-hosted `three.module.min.js`) so it can be cached across visits instead of re-parsed on every load; add a minimal loading state; self-host the fonts (or trim to the weights actually used); add a dev-only FPS/draw-call readout from `renderer.info`.

---

## 9. Finding P2-2 — smaller items

- **Water material:** `MeshPhysicalMaterial` + clearcoat + `transparent: true` is the most expensive material in the scene. Swap to `MeshStandardMaterial` on Balanced/Lite tiers; keep physical only on High.
- **Clouds:** ~36 transparent sprites with `depthWrite: false` are sorted per frame. Fine, but the Lite tier could halve the sprite count with no visible loss.
- **Anisotropy 8** on the grass texture is generous for mobile; 4 is enough at broadcast distance.
- **No WebGL context-lost handler.** Add `webglcontextlost` / `webglcontextrestored` listeners that show a message and rebuild the renderer — otherwise a lost context (see P0-1) is a permanent black screen with no recovery.
- **No `renderer.info` / FPS instrumentation** (see P2-1). You cannot claim 60 fps without measuring it.
- **dt clamp of 0.05 s** is correct; Turbo speed multiplies `dt`, which is fine. No issue found with the phase state machine — it is cheap and event-driven.

---

## 10. Prioritized optimization plan

Target: **locked 60 fps on a mid-range laptop, smooth playback on mobile, visuals as good as possible, all free.**

| # | Change | Effort | Expected impact |
|---|---|---|---|
| **P0-1** | Dispose geometries/materials in hole teardown; hoist shared geometries/materials out of `buildHoleScene` | Small (~30 lines) | **Stops unbounded GPU memory growth; prevents mobile context loss.** The single most important fix. |
| **P0-2** | Cache the 18 hole scenes (seeded by `holeIdx`) and reuse across rounds; or build the next hole during walk/putt phases | Medium | **Removes the 30–250 ms hitch on every hole change.** |
| **P1-1** | Tiered shadows: 2048² PCFSoft / 1024² PCFSoft / 1024² PCF-or-off; tighten frustum to ~70 units; update shadow map every 2nd frame | Small–medium | Biggest single GPU saving on mobile; ~30–50% shadow cost reduction. |
| **P1-2** | Boot-time capability tier (High/Balanced/Lite) + hysteresis controller with recovery + smooth shadow fade; scale terrain segments & tuft count per tier | Medium | No more 2-second slideshow on weak devices; good devices stop being punished for a load hitch. |
| **P1-3** | `visibilitychange` pause (stop rAF, suspend audio); 30 fps screensaver mode; respect `prefers-reduced-motion` | Small | Large battery saving for an always-on product. |
| **P1-4** | Hoist temp `Vector3`s in `updateCamera`/position helpers; skip particle buffer upload when nothing is alive | Small | Less GC pressure; smoother frame pacing on low-end Android. |
| **P2-1** | Externalize Three.js (cached module), loading state, self-host/trim fonts, add `renderer.info` FPS readout | Medium | Faster first paint; offline resilience; measurable performance. |
| **P2-2** | Terrain LOD on mobile (70×180), merge small meshes, share one sand material, water → Standard material below High tier | Medium | Fewer triangles and draw calls; small GPU saving. |
| **P2-3** | `webglcontextlost` / `restored` handlers with rebuild + user message | Small | A lost context becomes recoverable instead of a permanent black screen. |

### Suggested order of work

1. **P0-1 + P0-2 together** — they live in the same function (`buildHoleScene`) and together they fix the two defects that break the "runs forever" premise.
2. **P1-1 + P1-2** — the GPU tier system; do these as one pass since the tier definitions drive both.
3. **P1-3 + P1-4** — small, independent, high battery/ smoothness value.
4. **P2-1 → P2-3** — load time, LOD, and resilience, in that order.

### Verification checklist (after the fixes)

- [ ] Run 3 full rounds (54 hole transitions) with Chrome DevTools Performance + `renderer.info.render` open: confirm draw calls ≈ 55–65, triangles ≈ 40–70k, no long tasks at hole transitions.
- [ ] Confirm GPU memory is flat across rounds (DevTools Memory / `renderer.info.memory.geometries` constant after round 1).
- [ ] Confirm 60 fps on a mid-range laptop at DPR 1.75, and smooth playback on a mid-range Android/iPhone at the Balanced tier.
- [ ] Background the tab for 5 minutes: confirm rAF stops and CPU drops to ~0.
- [ ] Force a WebGL context loss (DevTools → Rendering → lose context): confirm the page recovers with a message instead of a black screen.
- [ ] Re-export from the current artifact build and re-run this audit — this snapshot predates the leaf-card foliage pass.

---

## Appendix — audit evidence (source locations in `index.html`)

- Renderer: `new THREE.WebGLRenderer({antialias:true, powerPreference:"high-performance"})`, DPR `Math.min(1.75, devicePixelRatio)`, ACES tone mapping, sRGB output.
- Shadow: `sunLight.shadow.mapSize.set(2048,2048)`, `PCFSoftShadowMap`, ortho ±55, near 10 / far 420.
- Terrain: `PlaneGeometry(W, L, 110, segZ)`, `segZ = min(300, round(L/2))`, per-vertex color loop + `computeVertexNormals()`, rebuilt in `buildHoleScene()`.
- Instancing: trunks/tiers/lobes NT=120, tufts NT2=420, bushes 60.
- Leak: `buildHoleScene()` teardown removes children with no `.dispose()` anywhere in the app (0 occurrences in 90 KB).
- Loop: `requestAnimationFrame(loop)`, manual `rawDt` clamped to 0.05, `dtEma` adaptive step-down at frame >140 and avg >46 ms → DPR 0.65 + shadows off, one-way.
- Buffers: tracer preallocated `Float32Array(300*3)`; particles `Float32Array(240*3)`; rain `Float32Array(300*3)`.
- Textures: canvas-generated 256² (grass repeat 110×340, anisotropy 8; sand 2×2), cloud 256×128, sky 4×256, dot 32².
- No `visibilitychange` handler, no `renderer.info` usage, no context-lost handler, no `setAnimationLoop`.
- First load: ~1.15 MB inlined Three.js + Google Fonts (3 families), classic blocking script, `boot` via `setTimeout(boot, 0)` on DOMContentLoaded.
