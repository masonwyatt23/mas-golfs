# Mas Golfs — Architecture

The project is a real-time virtual television network, not a video game. Four layers:

## 1. Photorealistic world generation

- **Now (web prototype):** a self-contained browser build (`index.html`) — 3D down-the-line broadcast view, procedural terrain, textured grass, bunkers, water, trees, dawn-to-dusk sky. Open it and it plays.
- **Next (Unreal Engine 5.8):** Lumen Lite for locked 60 fps, Nanite Foliage for millions of grass blades and pine needles, Substrate multi-layer materials (dew on bent grass), Quixel Megascans + Megaplants (free on Fab since Nov 2026), LiDAR terrain from USGS 3DEP via Houdini/Gaea, Cesium for Unreal for the surrounding mountains and horizon. MetaHuman Mas + a mocap shoot of Mason's actual swing (no off-the-shelf golf-swing mocap exists). Niagara ribbons for the shot tracer.
- **First step:** a one-hole vertical slice in UE 5.8 — LiDAR terrain, Megascans grass, MetaHuman, one full shot loop with tracer and NodeCG scorebug — judged against the 2K/GTA 6 bar on real footage before committing to 18 holes.

## 2. Broadcast cinematography & optics

- An autonomous director as a **state machine over phases of play**, not a timer: address → down-the-line tee cam; swing → hold through impact; flight → tracer cam; landing → pin cam; walk → wide follow cam; putt → low green-side cam; hole-out → reaction cam.
- Rules: minimum 2–3 s hold per shot, never cut mid-flight, cut on events never on a clock. A drama score per shot (birdie/eagle, hole-out, near-miss, great recovery, bad mishit) triggers a 0.5× slow-motion instant replay.
- Telephoto feel, camera inertia and micro-shake like a human operator on a fluid-head tripod, atmospheric haze, ACES-filmic color grading with highlight roll-off — no oversaturated video-game greens.

## 3. Autonomous broadcast graphics

- Overlays as a separate layer: PGA-style scorebug, player cards, hole flyovers, shot-data lower-thirds (ball speed, apex, carry, curve), leaderboard, ticker.
- **NodeCG** is the recommended stack for the Unreal build (HTML/CSS/JS graphics as OBS browser sources, replicants as shared state). **SPX Graphics** is the simpler fallback; CasparCG only if frame-accurate playout is needed later.
- **OBS Studio + obs-websocket** is the switcher: a Python/Node "AI Director" cuts scenes, triggers replays, and pushes RTMP to YouTube Live + Twitch (via Restream for multistream). Render once, broadcast to everyone — one GPU renders the show; the platforms distribute to unlimited viewers.

## 4. AI commentary & simulation data

- **Shot engine:** generates club delivery first (path, face, strike location, speed), then computes flight from launch conditions through gravity, drag, and Magnus lift. Emits structured JSON events per shot.
- **Decision engine:** a compact local model that runs on-device — club selection, trajectory, risk, lay-up vs. aggression — learning from every round. No server round-trips.
- **Learning loop:** strokes-gained review after each round; approach and driving first (the long game decides ~⅔ of scoring). Surfaces exactly one fix per round: the single biggest leak and the single adjustment.
- **Commentary booth:** event-driven, two voices (calm play-by-play host + analytical color commentator), low-latency TTS (ElevenLabs Flash). Event-only — real golf is mostly quiet — with an ambient bed (wind, birds, impact stingers) carrying the silence. Cost guardrail: caching repeated lines, no continuous narration.
- **Calibration truth tables:** +3 benchmarks (~265–275 yd driving, ~55–60% fairways, ~55–57% GIR, scoring ~72–74); approach proximity (150 yd ≈ 25–30 ft); putting make rates (10 ft ≈ 40%, 20 ft ≈ 14%). (GIR and scoring are v3 estimates for the 7,602-yard course — pending the 10,000-round harness; see course-design-v3.md §5.3.)

## The economy

Clubhouse Coins are closed-loop play money: free, earned by watching and predicting, never purchasable, never convertible to anything of value. No cash-out path, no crypto — that stays off the roadmap until counsel reviews it.

## Build order

1. Sim event bus + JSON event schema
2. OBS scene collection + director
3. NodeCG graphics (scorebug, leaderboard, lower-thirds, ticker)
4. Replay system (0.5× on dramatic shots, auto-clip save)
5. Commentary pipeline (event → LLM → TTS, two voices, cost guardrails)
6. Ambient audio (layered bed, event stingers, ducking)
7. Multistream + 24/7 reliability (watchdog auto-restart, AI-use disclosure set)
8. Clip pipeline (auto-cut highlights into vertical clips for Shorts/Reels/TikTok)

## Compliance

YouTube requires disclosure of realistic AI-generated content on livestreams. Set the AI-use disclosure from day one and keep the "Mas is Mason's digital twin" identity visible on screen.
