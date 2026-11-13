# Mas Golfs — Godot broadcast slice

**Status: scaffold.** Written without running Godot. Nothing here has been
opened in the editor yet. The first Mac session will find the errors; fix
them there and commit. Do not present this as a working build until the
Hole 12 slice passes the phone eye test in `docs/cinematic-direction.md`.

## What this folder is

The native broadcast renderer for the Mac box (Godot 4.7, Forward+ on
native Metal), per `docs/mac-native-broadcast.md`. The sim stays
authoritative: this folder is a **dumb visualizer** — it renders what the
bus tells it, nothing more. The web build stays live as prototype, clip
factory, and OBS fallback.

## Layout

- `project.godot` — project settings (Forward+, 1920×1080).
- `scripts/bus_client.gd` — WebSocket client for the event bus
  (`ws://localhost:4456`). Parses broadcast envelopes and dispatches to
  the director. Mirrors `bus/translate.py` — the envelope is
  `{"event", "seq", "ts", "round", "hole", "data"}`.
- `scripts/director.gd` — shot-state machine: the 7-beat Hole 12 shot
  list from `docs/cinematic-direction.md` as states. Camera moves are
  stubs until the terrain + character land.
- `scenes/` — **empty on purpose.** The Hole 12 scene (`hole_12.tscn`)
  is built on the Mac with the editor: Terrain3D from the LiDAR
  heightmap (`docs/research/terrain-lidar-prep.md`), the Mas character,
  lighting, and fog. Do not hand-write the scene file here.

## First run on the Mac (Step 0 of the slice)

1. Install Godot 4.7 (see `docs/mac-install-weekend.md` for the box
   setup; Godot is not installed yet as of 2026-11-13).
2. Open this folder in Godot. Fix whatever the editor complains about
   and commit the fixes.
3. Start the sim with the bus up (`MAS_GOLFS_BUS_URL=ws://localhost:4456`)
   and confirm `bus_client.gd` connects and prints the `round_state`
   snapshot (the bus sends one on connect — see `bus/client.py`).
4. Build the Hole 12 scene in the editor, then judge it on real
   1080p60 footage watched on a phone — the eye test in
   `docs/cinematic-direction.md` §7 is the deciding gate.

## Memory budget (from docs/mac-native-broadcast.md)

Hard cap **7.0 GB** total on the box (assumes the 8 GB label is right;
re-measure RAM first — Mac15,3 ships 18 GB+, which would loosen this).
Degradation order: render scale → shadows → grass → fog → MLX cached
lines → Kokoro silence. OBS / sim / bus are never shed.

## What is NOT here yet

Terrain, character, swing animation, lighting rig, grass, water,
bunkers, trees, the score bug / 59 Watch graphics, and OBS capture.
Those are the slice build itself, done on the Mac.
