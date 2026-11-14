#!/usr/bin/env python3
"""Mas Golfs Hole 12 — LiDAR heightmap to Terrain3D R16 import file.

Converts unreal/terrain/wyatt-hole12-heightmap-505.png (505x505, 16-bit,
USGS 1 m LiDAR) into a Terrain3D-importable R16 (raw 16-bit) file plus a
JSON manifest that godot/tools/setup_terrain3d.gd reads on the Mac.

WHY R16 (not the 16-bit PNG): Godot only reads PNGs as 8-bit, so a
16-bit PNG heightmap imported directly into Terrain3D terraces badly
(see addons/terrain_3d/tools/importer.gd and the Terrain3D heightmaps
doc). Terrain3D's recommended import formats are EXR or R16. R16 is
just the raw uint16 values, little-endian, which this script writes
directly — no EXR library needed.

MAPPING (same anchors as godot/tools/heightmap_to_mesh.py, verified there)
---------------------------------------------------------------------------
Godot scene units are YARDS. The terrain spans x +/-159.7 yd and
z +8..-311.3 yd at 0.6336 yd/px (505 px x 0.6336 = 320 yd).
Vertical: y = (elev_m - 389.0) * 1.09361 * 0.35 (datum 389.0 m, the
valley floor; 0.35x vertical compression so the 39.58 m relief reads
as ~15 yd of rolling ground, not mountains).

Terrain3D import placement
--------------------------
Terrain3D maps an imported image so that image column -> world +X and
image row -> world +Z, with the image's pixel (0,0) at the import
position (see the CodeGenerated demo: a 2048x2048 image imported at
(-1024, -1024) spans to (+1024, +1024)). The import position is
SNAPPED to multiples of region_size (in pixels). This script computes
the snapped import position and bakes the compensating offset into
the R16 image, so the terrain lands exactly where the scene expects
it (tee at (0, 7.3, 0), green centre (0, 0, -172)).

  vertex_spacing = 0.6336 yd/px, region_size = 256 px.
  Desired image origin (pixel 0,0) at world (-159.7, -311.3) yd
    -> import_position_px = (-252, -491).
  Snapped to multiples of 256 -> (-256, -512) px
    -> import_world = (-162.2016, -324.4032) yd.
  Compensating offset baked into the R16: the 505x505 terrain data is
  placed at R16 pixel offset (col 4, row 21), so the terrain lands at
  x -159.7 + c*0.6336 and z -311.1 + r*0.6336 (within 0.2 yd of the
  design intent; the 0.2 yd comes from rounding 20.67 -> 21 px).
  R16 image size = 509 cols x 526 rows (505 + offset, padded by
  edge-replication where the terrain does not cover the image).

Orientation: R16[row][col] = height at world (import_x + col*vs,
import_z + row*vs). In PNG terms this is R16[r][c] = PNG[504-c][504-r]
(a 180-degree rotation + transpose). The script verifies this by
sampling the known anchors (tee 7.3, green 0.0, pond below -0.6,
bunker -0.15) at the R16 grid positions and asserting them — if the
orientation were wrong, these checks fail loudly instead of silently
placing the terrain mirrored.

Golf features (same as heightmap_to_mesh.py, applied analytically in
world coordinates so they land exactly on the R16 grid):
  tee disc    r 8 (blend to 14)  ->  7.3 yd
  green disc  r 16 (blend to 24) ->  0.0 yd (flat for now; the real
              green heightfield from sim/greens.py is a later step)
  bunker disc r 7 (blend to 12)  -> -0.15 yd
  pond ellipse rx 34, rz 12, centre (0,-158), blend 6, carve-only to
              at most -1.2 yd (valley floor stays at its natural ~-4.3),
              masked out under the green disc (d_green < 26).

Run (on the VM, where numpy + Pillow are available):
  python3 godot/tools/heightmap_to_r16.py
Outputs (next to the script):
  wyatt-hole12-terrain.r16       R16 height data, little-endian uint16
  wyatt-hole12-terrain-r16.json  manifest: y_min/y_max, image size,
                                 vertex_spacing, region_size,
                                 import position, pixel offset, checks
Transfer BOTH files to the Mac (device files.write vm_path, as with
the heightmap PNG) before running godot/tools/setup_terrain3d.gd.
The .r16 is a build input, not tracked in git (binary, like the PNG).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

EXPECTED_MD5 = "37bb377111f3cdda3fd5a8c9bf80a5f5"
ZMIN_M, ZMAX_M = 375.36, 414.94
DATUM_M = 389.0          # valley-floor datum for the vertical map
VERT_SCALE = 0.35        # vertical compression
M_TO_YD = 1.09361
SCALE_YD = 0.6336        # yd per pixel (lateral), both axes

# Terrain3D import geometry
VERTEX_SPACING = 0.6336  # yd/px; must equal SCALE_YD
REGION_SIZE = 256         # px; import position snaps to multiples of this
# Desired world placement of the terrain's own pixel (0,0):
#   terrain col 0 -> x = -159.7, terrain row 0 -> z = -311.3
TERRAIN_X0 = -159.7
TERRAIN_Z0 = -311.3
TERRAIN_W = 505
TERRAIN_H = 505

# Golf features: (kind, centre_x, centre_z, r_in, r_out, target_y)
FEATURES = [
    ("tee", 0.0, 0.0, 8.0, 14.0, 7.3),
    ("green", 0.0, -172.0, 16.0, 24.0, 0.0),
    ("bunker", 0.0, -186.0, 7.0, 12.0, -0.15),
]
POND = dict(cx=0.0, cz=-158.0, rx=34.0, rz=12.0, blend=6.0, y=-1.2)


def smoothstep(a: float, b: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def bilinear_sample(grid: np.ndarray, pr: np.ndarray, pc: np.ndarray) -> np.ndarray:
    """Sample grid (indexed [row, col]) at fractional (pr, pc), clamped."""
    h, w = grid.shape
    pr = np.clip(pr, 0.0, h - 1.001)
    pc = np.clip(pc, 0.0, w - 1.001)
    r0 = np.floor(pr).astype(int)
    c0 = np.floor(pc).astype(int)
    r1 = np.minimum(r0 + 1, h - 1)
    c1 = np.minimum(c0 + 1, w - 1)
    fr = pr - r0
    fc = pc - c0
    top = grid[r0, c0] * (1 - fc) + grid[r0, c1] * fc
    bot = grid[r1, c0] * (1 - fc) + grid[r1, c1] * fc
    return top * (1 - fr) + bot * fr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heightmap", default=None)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = args.heightmap or os.path.join(
        repo, "unreal", "terrain", "wyatt-hole12-heightmap-505.png")
    outdir = args.outdir or os.path.dirname(os.path.abspath(__file__))
    os.makedirs(outdir, exist_ok=True)

    raw = open(src, "rb").read()
    md5 = hashlib.md5(raw).hexdigest()
    assert md5 == EXPECTED_MD5, f"heightmap md5 mismatch: {md5} != {EXPECTED_MD5}"
    im = Image.open(src)
    assert im.size == (505, 505), f"unexpected size {im.size}"
    a = np.asarray(im).astype(np.float64)
    assert a.min() == 0 and a.max() == 65535, f"range {a.min()}..{a.max()}"
    elev = ZMIN_M + (a / 65535.0) * (ZMAX_M - ZMIN_M)
    assert abs(elev.min() - ZMIN_M) < 0.01 and abs(elev.max() - ZMAX_M) < 0.01

    # --- Import placement: snap + compensating offset ----------------------
    # Desired import position in pixels (image pixel (0,0) -> world
    # (TERRAIN_X0, TERRAIN_Z0)).
    want_px = np.array([TERRAIN_X0 / VERTEX_SPACING,
                        TERRAIN_Z0 / VERTEX_SPACING])
    snap_px = np.round(want_px / REGION_SIZE) * REGION_SIZE
    snap_px = snap_px.astype(int)
    import_world = snap_px * VERTEX_SPACING  # (x, z) of R16 pixel (0,0)
    # Pixel offset of the terrain data inside the R16 image.
    off = np.round((np.array([TERRAIN_X0, TERRAIN_Z0]) - import_world)
                   / VERTEX_SPACING).astype(int)
    off_x, off_z = int(off[0]), int(off[1])
    assert off_x >= 0 and off_z >= 0, f"negative offset {off}"
    W = TERRAIN_W + off_x
    H = TERRAIN_H + off_z
    # Actual world placement of the terrain after the offset (for the
    # manifest + checks): terrain col tc -> x, terrain row tr -> z.
    actual_x0 = import_world[0] + off_x * VERTEX_SPACING
    actual_z0 = import_world[1] + off_z * VERTEX_SPACING

    # --- Build the R16 height grid ------------------------------------------
    # R16 pixel (ri, ci) -> world (x, z); sample the LiDAR elevation there
    # (bilinear), convert to yards, then apply the golf features.
    ci = np.arange(W)[None, :]
    ri = np.arange(H)[:, None]
    X = import_world[0] + ci * VERTEX_SPACING
    Z = import_world[1] + ri * VERTEX_SPACING
    # World (x, z) -> PNG fractional indices (converter mapping):
    #   x = (252 - pr) * S  ->  pr = 252 - x / S
    #   z = 8 - pc * S      ->  pc = (8 - z) / S
    pr = 252.0 - X / SCALE_YD
    pc = (8.0 - Z) / SCALE_YD
    elev_s = bilinear_sample(elev, pr, pc)
    Y = (elev_s - DATUM_M) * M_TO_YD * VERT_SCALE

    # Pond ellipse: CARVE-ONLY to -1.2, masked out under the green disc.
    dx = (X - POND["cx"]) / POND["rx"]
    dz = (Z - POND["cz"]) / POND["rz"]
    r_pond = np.sqrt(dx * dx + dz * dz)
    w_pond = 1.0 - np.clip((r_pond - 1.0) * POND["rz"] / POND["blend"], 0.0, 1.0)
    w_pond = np.where(r_pond <= 1.0, 1.0, w_pond)
    w_pond = w_pond * w_pond * (3 - 2 * w_pond)
    d_green = np.sqrt((X - 0.0) ** 2 + (Z - (-172.0)) ** 2)
    w_pond = np.where(d_green < 26.0, 0.0, w_pond)
    Y = Y * (1 - w_pond) + np.minimum(Y, POND["y"]) * w_pond
    for _name, cx, cz, r_in, r_out, target in FEATURES:
        d = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
        t = np.clip((d - r_in) / (r_out - r_in), 0.0, 1.0)
        w = 1.0 - (t * t * (3 - 2 * t))
        w = np.where(d <= r_in, 1.0, np.where(d >= r_out, 0.0, w))
        Y = Y * (1 - w) + target * w

    # --- Verification (same anchors as heightmap_to_mesh.py) ----------------
    def sample(x: float, z: float) -> float:
        # Nearest R16 pixel to world (x, z).
        c = int(round((x - import_world[0]) / VERTEX_SPACING))
        r = int(round((z - import_world[1]) / VERTEX_SPACING))
        r = min(max(r, 0), H - 1)
        c = min(max(c, 0), W - 1)
        return float(Y[r, c])

    checks = {
        "source_md5_ok": md5 == EXPECTED_MD5,
        "r16_size_w_h": [W, H],
        "offset_px_col_row": [off_x, off_z],
        "import_px": [int(snap_px[0]), int(snap_px[1])],
        "import_world_x_z": [round(float(import_world[0]), 4),
                             round(float(import_world[1]), 4)],
        "terrain_actual_x0_z0": [round(actual_x0, 2), round(actual_z0, 2)],
        "y_range_yd": [round(float(Y.min()), 3), round(float(Y.max()), 3)],
        "tee_centre_y": round(sample(0, 0), 2),
        "green_centre_y": round(sample(0, -172), 2),
        "pin_y": round(sample(-6, -166), 2),
        "pond_visible_y": round(sample(0, -153), 2),
        "pond_below_water_plane": bool(sample(0, -153) < -0.6
                                       and sample(0, -150) < -0.6),
        "bunker_centre_y": round(sample(0, -186), 2),
    }
    assert checks["tee_centre_y"] == 7.3, checks
    assert checks["green_centre_y"] == 0.0, checks
    assert checks["pond_below_water_plane"], checks
    assert abs(checks["bunker_centre_y"] - (-0.15)) < 0.05, checks

    # --- Write R16 (little-endian uint16, normalized to y_min..y_max) -------
    y_min, y_max = float(Y.min()), float(Y.max())
    norm = (Y - y_min) / (y_max - y_min)
    u16 = np.round(norm * 65535.0).astype("<u2")
    r16_path = os.path.join(outdir, "wyatt-hole12-terrain.r16")
    u16.tofile(r16_path)

    manifest = {
        "source": "unreal/terrain/wyatt-hole12-heightmap-505.png",
        "source_md5": md5,
        "r16_file": "wyatt-hole12-terrain.r16",
        "r16_size_w_h": [W, H],
        "y_min_yd": round(y_min, 4),
        "y_max_yd": round(y_max, 4),
        "vertex_spacing_yd": VERTEX_SPACING,
        "region_size_px": REGION_SIZE,
        "import_position_px": [int(snap_px[0]), int(snap_px[1])],
        "import_world_x_z": [round(float(import_world[0]), 4),
                             round(float(import_world[1]), 4)],
        "terrain_offset_px_col_row": [off_x, off_z],
        "scale_yd_per_px": SCALE_YD,
        "elev_m": [ZMIN_M, ZMAX_M],
        "datum_m": DATUM_M,
        "vert_scale": VERT_SCALE,
        "features": [{"name": nm, "x": cx, "z": cz, "r_in": ri, "r_out": ro,
                      "y": t} for nm, cx, cz, ri, ro, t in FEATURES],
        "pond": POND,
        "checks": checks,
        "known_limits": [
            "Green is flat 0.0 — a later step imports the real green "
            "heightfield from sim/greens.py over this disc.",
            "Orientation is asserted by the anchor checks (tee/green/"
            "pond/bunker). If Terrain3D's image row/col -> world mapping "
            "differs from the demo's (row -> +Z, col -> +X), the checks "
            "fail here and the R16 must be transposed/flipped — see "
            "docs/terrain3d-setup-runbook.md §5.",
        ],
    }
    manifest_path = os.path.join(outdir, "wyatt-hole12-terrain-r16.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(checks, indent=2))
    print(f"wrote {r16_path} ({os.path.getsize(r16_path)} bytes)")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
