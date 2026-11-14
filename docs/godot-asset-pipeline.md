# Mas Golfs Godot visual pipeline — asset setup (Nov 13, 2026)

The primitives-only scene hit its ceiling (v27 is the best it gets). The
leap to a real golf-course look comes from free assets + addons, all $0.
This doc records what is installed, where it came from, and how to
reproduce it. The addons/textures are BINARY and are NOT in git (the
push tool is text-only) — they live on the broadcast Mac in
`~/mas-golfs/godot/` and are installed by direct transfer. The
`project.godot` change (enabling the plugins) IS in git.

## Installed on the Mac (verified Nov 13, ~11:15pm)

| What | Version | Source (free, $0) | Location on the Mac |
|---|---|---|---|
| Terrain3D | 1.1.0-stable | https://github.com/TokisanGames/Terrain3D/releases (release zip, has the prebuilt macOS .framework; the main-branch zip has NO binaries) | `godot/addons/terrain_3d/` (macOS binaries only; other platforms stripped to fit the 50 MB transfer limit) |
| Sky3D | 2.1.0 | https://github.com/TokisanGames/Sky3D/releases | `godot/addons/sky_3d/` |
| Grass004 (fairway) | 2K JPG | https://ambientcg.com/view?id=Grass004 (CC0) | `godot/textures/Grass004_Color.jpg`, `Grass004_NormalGL.jpg` |
| Grass006 (rough) | 2K JPG | https://ambientcg.com/view?id=Grass006 (CC0) | `godot/textures/Grass006_Color.jpg`, `Grass006_NormalGL.jpg` |
| Sand (bunker) | 512 PNG | Generated locally (`make_grass_texture.py` pattern) — a real ambientCG sand texture was not found by ID; replace when one is confirmed | `godot/textures/sand-detail.png` |

Verified: Godot 4.7.2 headless `--import` on the Mac registers the
Terrain3D + Sky3D global classes, verifies the GDExtension, and imports
all five textures with no errors. Plugins are enabled in `project.godot`
(`[editor_plugins]`).

## Next steps (not yet done)

1. **Terrain3D terrain:** create a Terrain3D node, import the existing
   16-bit heightmap (`unreal/terrain/wyatt-hole12-heightmap-505.png`),
   set up 4 texture layers (fairway Grass004, rough Grass006, green
   Grass004 tinted lighter, sand), paint the fairway corridor + green +
   bunker. This replaces the OBJ terrain mesh in `hole_12.tscn` — the
   generator (`build_hole12.py`) will skip the Terrain mesh once
   Terrain3D owns it. This is editor work; verify with the frame
   capture loop.
2. **Sky3D:** add the Sky3D node, set golden-hour time, replace the
   gradient sky. Keep the DirectionalLight3D sun; retune shadows with
   Terrain3D's real normals + PBR (the fix for the black-terrain
   shadow failure — see below).
3. **Mixamo golfer:** needs Mason's free Adobe ID. Download a Mixamo
   character (with skin, T-pose) + Golf Drive / Golf Putt / Golf Tee Up
   / Idle animations (without skin); import as Animation Libraries in
   Godot 4.7 (built-in ufbx); parent a club to the hand bone. This
   replaces the capsule Mas. Left-handed: mirror by scaling root X -1.
4. **Trees:** Quaternius Stylized Nature MegaKit (CC0, itch.io $0) +
   ProtonScatter, to replace the cone pines. Not yet downloaded.

## Known dead ends (do not retry)

- Custom terrain shader + shadows (v28): the directional shadow map
  self-shadows the whole terrain black at the low golden-hour sun, and
  shaded terrain goes black (v21). Terrain3D + PBR + proper shadow
  bias + SDFGI/LightmapGI is the fix, not another material swap.
- Poly Haven direct downloads: the `dl.polyhaven.org` URL pattern and
  the `api.polyhaven.org` endpoint did not return the files in Nov 2026
  (404 / non-JSON). Use ambientCG (the `get?file=` pattern works) or
  the Poly Haven site directly in a browser.
- AI 3D for the hero golfer: Meshy/Tripo generate props, not a reliable
  rigged human. The golfer comes from Mixamo (or MediaPipe/Mocai from
  Mason's swing video). Tripo free outputs are non-commercial — do not
  ship them.
