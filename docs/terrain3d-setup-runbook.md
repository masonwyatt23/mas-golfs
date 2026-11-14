# Terrain3D setup — runbook

Build the Hole 12 Terrain3D terrain headless on the Mac and capture a frame
to verify it. The script (`godot/tools/setup_terrain3d.gd`) replaces the OBJ
terrain mesh with a real Terrain3D node: LiDAR heightmap at full 16-bit
precision, PBR grass/sand texture layers, painted fairway/green/bunker.

## Prerequisites (on the VM, done)

- `godot/tools/heightmap_to_r16.py` — converts the 16-bit PNG to a raw R16
  file + JSON manifest. Already run on the VM; outputs:
  - `godot/tools/wyatt-hole12-terrain.r16` (535,468 bytes, 509x526 uint16 LE)
  - `godot/tools/wyatt-hole12-terrain-r16.json`
- `godot/tools/setup_terrain3d.gd` — the headless setup script (this runbook's
  subject). Not yet pushed (see §4).

## 1. Transfer the R16 + manifest to the Mac

The R16 is binary and the GitHub push tool is text-only, so transfer it the
same way the heightmap PNG was transferred: device `files.write` with
`vm_path` (paths relative to VM home, no absolute paths).

- VM source: `workspace/mas-golfs-repo/godot/tools/wyatt-hole12-terrain.r16`
  -> Mac dest: `~/mas-golfs/godot/tools/wyatt-hole12-terrain.r16`
- VM source: `workspace/mas-golfs-repo/godot/tools/wyatt-hole12-terrain-r16.json`
  -> Mac dest: `~/mas-golfs/godot/tools/wyatt-hole12-terrain-r16.json`

After transfer, de-quarantine both (files arriving via files.write are
quarantined):
```bash
xattr -d com.apple.quarantine ~/mas-golfs/godot/tools/wyatt-hole12-terrain.r16
xattr -d com.apple.quarantine ~/mas-golfs/godot/tools/wyatt-hole12-terrain-r16.json
```

## 2. Runner command (one script, the Mac executes it)

Write this to `~/.masgolfs/runner/command.sh` via the device files API
(device "Mason's MacBook Pro"). The runner polls every 20s; output appends
to `~/.masgolfs/runner/output.log`.

```bash
#!/bin/bash
export PATH=/opt/homebrew/bin:/opt/homebrew/sbin:$PATH
set -x
cd ~/mas-golfs

# The Mac's git pulls abort if mlx-verify/verify.sh has local changes.
git checkout -- mlx-verify/verify.sh
git pull --ff-only

# Sanity: the new script + R16 + manifest are present.
ls -la godot/tools/setup_terrain3d.gd godot/tools/wyatt-hole12-terrain.r16 \
  godot/tools/wyatt-hole12-terrain-r16.json godot/textures/
md5 godot/tools/wyatt-hole12-terrain.r16

# Import any new resources (the .r16, the .json, the new .gd) so Godot
# sees them, then run the setup script headless.
# NOTE: use --import first; a failed import can leave an empty resource.
# NOTE: the setup script is a SceneTree script (-s), NOT --editor --script.
/Applications/Godot.app/Contents/MacOS/Godot --headless --path ~/mas-golfs/godot --import
/Applications/Godot.app/Contents/MacOS/Godot --headless \
  --path ~/mas-golfs/godot -s res://tools/setup_terrain3d.gd
echo "SETUP_EXIT=$?"

# Capture a frame to verify (writes ~/godot-hole12-frame.png).
/Applications/Godot.app/Contents/MacOS/Godot --path ~/mas-golfs/godot \
  -s res://tools/capture_frame.gd --resolution 1920x1080
ls -la ~/godot-hole12-frame.png
```

The setup script prints `=== setup_terrain3d: SUCCESS ===` and exits 0, or
`=== setup_terrain3d: FAILED ===` with `ERROR:` lines and exits 1.
`SETUP_EXIT` in the log tells you which. If it fails, read the ERROR lines
in `output.log` before re-running.

## 3. Verify the frame

Download `~/godot-hole12-frame.png` via device files.read and look at it.

Pass criteria (the script also prints numeric checks — see §5):
- The ground reads as real grass: visible texture grain / mowing variation,
  not a flat green slab.
- The fairway apron (around the green) and the tee box read slightly
  different/lighter than the surrounding rough; the green reads as a
  distinct lighter putting surface; the bunker reads sandy/tan.
- The LiDAR hills still hold their shape (the rise behind-right of the
  green, undulations left) — the terrain is not flattened or mirrored.
- The tee still sits at 7.3 yd and the green at 0.0 (the script prints
  `get_height` at tee/green/pin/pond/bunker; pond must be below the water
  plane at y=-0.6).
- Mas, the flagstick, the pines, and the pond are still in the scene.

## 4. If the frame is good

Commit the new files. The Terrain3D data files are **generated** (region
`.res` files under `godot/terrain_data/hole12/`) — they are small and the
scene references them by path, so commit them like the rest of the project.
Do NOT commit the R16 or the heightmap PNG (binary build inputs, same as
the PNG already is).

Push (text files only; keep it small for the approval card):
```
godot/tools/setup_terrain3d.gd
godot/tools/heightmap_to_r16.py
godot/scenes/hole_12.tscn
godot/terrain_data/hole12/material.tres
godot/terrain_data/hole12/assets.tres
godot/terrain_data/hole12/terrain3d_*.res   (whatever regions were written)
docs/terrain3d-setup-runbook.md
```

Then update `build_hole12.py` BEFORE anyone re-runs it: it currently
regenerates the whole `hole_12.tscn` with the OBJ terrain + flat discs, and
re-running it would wipe the Terrain3D node the script just installed.
Until it is updated, `hole_12.tscn` is the source of truth for the terrain.

## 5. What the script prints (so you can read the log)

```
manifest: r16 509x526, y -5.213..9.921 yd, vs 0.6336, region 256, import (-162.2016, -324.4032)
R16 loaded: 509x526 format ...
R16 height range in image: -5.213..9.921 yd (want -5.213..9.921)
saved material -> res://terrain_data/hole12/material.tres
saved assets   -> res://terrain_data/hole12/assets.tres
regions after import: N
terrain height range: -5.21..9.92 yd
painted apron tex 1: ~2250 px
painted green tex 2: ~1530 px
painted tee   tex 1: ~780 px
painted bunker tex 3: ~380 px
height tee at (0.0, 0.0): 7.30 (want 7.30) OK
height green centre at (0.0, -172.0): 0.00 (want 0.00) OK
height Sunday pin at (-6.0, -166.0): 0.00 (want 0.00) OK
height pond (below water -0.6) at (0.0, -153.0): -1.60 (want -1.60) OK
height bunker at (0.0, -186.0): -0.15 (want -0.15) OK
paint tee box at (0.0, 0.0): base 1 (want 1) OK
paint green centre at (0.0, -172.0): base 2 (want 2) OK
paint Sunday pin at (-6.0, -166.0): base 2 (want 2) OK
paint apron (behind green) at (0.0, -180.0): base 1 (want 1) OK
paint bunker at (0.0, -186.0): base 3 (want 3) OK
paint rough (valley side) at (40.0, -100.0): base 0 (want 0) OK
paint rough (behind green) at (-60.0, -250.0): base 0 (want 0) OK
saved terrain data -> res://terrain_data/hole12
data dir files: terrain3d_00-01.res, ...
removed node: Terrain / Tee / Green / Collar / Bunker
saved scene -> res://scenes/hole_12.tscn
verified: saved scene loads, Terrain3D node present, data_directory = res://terrain_data/hole12
=== setup_terrain3d: SUCCESS ===
```

## 6. If the orientation is mirrored (hill on the wrong side)

The R16 orientation is the one untested assumption. The script's anchor
checks (tee/green/pond/bunker heights) pass even if the terrain is mirrored
left-right, because the golf features are painted analytically in world
coordinates — only the *LiDAR hills* would be mirrored. Compare the frame
to `unreal/terrain/wyatt-hole12-preview-hillshade.png` (the hillshade
preview): in the v19 frame the big rise sat behind-right of the green.
If the new frame shows it behind-LEFT instead, the R16 is mirrored.

Fix (on the VM, then re-transfer the R16 and re-run the script):
in `godot/tools/heightmap_to_r16.py`, change the R16 build line
`R16[r, c] = PNG[504 - c, 504 - r]` to the transposed variant
`R16[r, c] = PNG[504 - r, 504 - c]` (or flip the sign of one index —
see the comment in the script). Re-run the Python script, re-transfer
the R16, re-run the GDScript. The GDScript is idempotent: it wipes the
data directory and re-imports from scratch, and reuses an existing
Terrain3D node in the scene instead of duplicating it.

## 7. Troubleshooting

- `R16 file not found` / `manifest not found`: the transfer (§1) did not
  happen or landed in the wrong directory. Check `ls godot/tools/`.
- `cannot load albedo texture` / `cannot load normal texture`: the
  textures are not at `godot/textures/` or were not imported. Run the
  `--import` step first (it is in the runner command, §2).
- `import produced no regions`: the R16 failed to load as a height image
  (wrong size in the manifest, or the file is corrupt). Re-run
  `heightmap_to_r16.py` on the VM and re-transfer.
- `height mismatch` on a check: the R16 y-range or the import position
  is off. Compare the printed `R16 height range` and `import` values
  against the manifest JSON; the manifest is the single source of truth
  and both scripts read it.
- `paint mismatch`: a zone is painted in the wrong place. Check the
  `painted ... px` counts — a count of 0 means the zone's bounding box
  fell outside the terrain (import position wrong).
- The scene loads but the terrain is invisible / the frame is black:
  the Terrain3D node may have failed to load its data (check the capture
  log for Terrain3D errors) or the data directory path in the saved
  scene is wrong (the script prints `data_directory` on verification).
  Restore the backup `godot/scenes/hole_12.tscn.bak` if needed and
  report the log.
- `PackedScene.pack failed`: the scene has a node the packer cannot
  serialise. Report the error; the backup is intact.

## 8. What still needs the editor GUI (honest limits)

- **Nothing in this setup needs the editor.** The heightmap import,
  texture layers, painting, data save, and scene edit are all scripted.
- The two things that *might* need a GUI touch later, only if the frame
  shows it: (a) if the normal maps look wrong (too bumpy / inverted),
  set the Grass004/Grass006 NormalGL JPGs' import to "Normal Map" in
  the editor and re-run the script; (b) shadows are deliberately OFF
  for this first frame — turning them on with Terrain3D's real normals
  (plus the SDFGI fix from the second research pass) is a separate
  look-dev step, done in the editor or in `build_hole12.py`.
- Do NOT re-run `build_hole12.py` until it is updated to emit the
  Terrain3D node (§4) — it would overwrite this work.
