#!/usr/bin/env python3
"""Godot terrain fallback for Mas Golfs Hole 12 — LiDAR heightmap to mesh.

Fallback for docs/mac-native-broadcast.md §6 Step 2: if the Terrain3D
16-bit PNG import fails or is unavailable on the Mac, this script converts
the ready LiDAR heightmap into a Godot-importable OBJ mesh instead.

Source: unreal/terrain/wyatt-hole12-heightmap-505.png — 505x505, 16-bit,
USGS 1 m LiDAR, Blue Ridge foothill terrain east of Staunton, VA.
Elevation 375.36-414.94 m (relief 39.58 m). Provenance + md5 in
docs/research/terrain-lidar-prep.md. This script re-verifies the md5.

Units: Godot scene units are YARDS (godot/tools/build_hole12.py).
Tee at (0, 7.3, 0), green centre (0, 0, -172), pond z -148..-168,
bunker (0, -0.15, -186), pin (-6, -166). Y-up.

MAPPING (uniform scale, no distortion — measured from the data, not assumed)
---------------------------------------------------------------------------
Measured Nov 13 from the heightmap itself (row 252 cross-section):
  west rim col 0   = 409.8 m | valley floor col ~250-275 = 377.7 m
  east rise col 325 = 393.2 m, col 400 = 408.8 m, east rim col 500 = 411.3 m
The valley runs diagonally NW-SE: valley col 327 (north rows) -> 3 (south).

Two feature anchors, one linear map, same scale on both axes:
  terrain col 0   (west rim)   -> Godot z = +8 yd   (just behind the tee)
  terrain col 262 (valley floor) -> Godot z = -158 yd (pond centre)
  => dz/dcol = -166/262 = -0.6336 yd per terrain metre-column.
  Same 0.6336 yd/row on the x axis, centred: x = (252 - row) * 0.6336.
Result: terrain spans z +8..-311.6 yd (283 yd deep, 140 yd of backdrop
hill behind the green) and x +/-160 yd (320 yd wide — fills the frame;
the v17 flat ground tile was only 120 yd wide and left sky-ground at
the sides). Green lands at col ~284, on the valley's east edge — it is
built UP as a pad to 0.0 (raw there is ~-3.8 yd), which is a real golf
look (pad-built green), with the east rise as the backdrop hill behind
it. Bunker at col ~306 on the lower east slope. The pond sits in the
natural valley low (raw ~-4.3 yd); the basin is carved only where it
rises above -1.2 yd, still below the scene's water plane at -0.6 yd,
and masked out under the green disc (the pond's far half hides under
the green in plan, as in build_hole12.py).

Vertical: y = (elev_m - 389.0) * 1.09361 * 0.35. The 0.35 vertical
scale compresses the 39.58 m (43.3 yd) raw relief to ~15 yd of rolling
ground — the hole's own drop is only 22 ft (7.3 yd) tee-to-green, so
full relief would read mountainous. 389.0 m is the valley-floor datum.

Orientation: PNG row 0 = north edge, col 0 = west edge; Godot -Z is
north by convention. Row -> +x here (north edge on screen-right from
the tee camera). If the Mac import reads mirrored vs
unreal/terrain/wyatt-hole12-preview-hillshade.png, set FLIP_X = True
(one line) and re-run — do NOT hand-edit the OBJ.

Golf features (hand-authored after import, per the design doc):
  tee disc    r 8 (blend to 14)  ->  7.3 yd
  green disc  r 16 (blend to 24) ->  0.0 yd   (flat for now — Step 5
              imports the real green heightfield from sim/greens.py
              over this disc; the putt solver's slopes replace the flat)
  pond basin  ellipse rx 34, rz 12, centre (0,-158), blend 6, carve-only
              to at most -1.2 yd (valley floor stays at its natural ~-4.3)
  bunker disc r 7 (blend to 12)  -> -0.15 yd

Run:  python3 godot/tools/heightmap_to_mesh.py
      (reads ../unreal/terrain/wyatt-hole12-heightmap-505.png relative
       to the repo root, or --heightmap <path>)
Outputs (next to the script unless --outdir given):
  wyatt-hole12-terrain.obj          Godot-importable mesh (Y-up)
  wyatt-hole12-terrain-preview.png  grayscale height preview (orientation check)
  wyatt-hole12-terrain-manifest.json  all parameters, stats and checks

Mac use (install weekend, Step 2): import the OBJ into the Godot
project, add as MeshInstance3D, REMOVE the flat Ground tile from
hole_12.tscn (it would z-fight / poke through), keep Tee/Green/Collar/
Pond/Bunker/Flagstick nodes — their heights already match the flattened
discs. Capture a frame and judge on a phone per docs/cinematic-direction.md §7.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
from PIL import Image

EXPECTED_MD5 = "37bb377111f3cdda3fd5a8c9bf80a5f5"
ZMIN_M, ZMAX_M = 375.36, 414.94
DATUM_M = 389.0          # valley-floor datum for the vertical map
VERT_SCALE = 0.35        # vertical compression (see header)
M_TO_YD = 1.09361
STEP = 2                 # downsample: every 2nd pixel -> 253 x 253 verts
FLIP_X = False           # set True if the Mac import reads mirrored

# Feature anchors: terrain col -> Godot z (yards)
TEE_COL, TEE_Z = 0, 8.0
POND_COL, POND_Z = 262, -158.0
SCALE_YD = (POND_Z - TEE_Z) / (POND_COL - TEE_COL)  # -0.6336 yd/col (negative: east -> -Z)
SCALE_YD = abs(SCALE_YD)

# Golf features: (kind, centre_x, centre_z, r_in, r_out, target_y)
# pond uses an ellipse (rx, rz) instead of a disc; handled separately.
FEATURES = [
    ("tee", 0.0, 0.0, 8.0, 14.0, 7.3),
    ("green", 0.0, -172.0, 16.0, 24.0, 0.0),
    ("bunker", 0.0, -186.0, 7.0, 12.0, -0.15),
]
POND = dict(cx=0.0, cz=-158.0, rx=34.0, rz=12.0, blend=6.0, y=-1.2)


def smoothstep(a: float, b: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


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

    # Downsampled grid: rows/cols 0, 2, ..., 504 -> 253 x 253.
    idx = np.arange(0, 505, STEP)
    n = len(idx)
    sub = elev[np.ix_(idx, idx)]  # sub[row, col]
    rows = idx[:, None]
    cols = idx[None, :]
    xs = (252.0 - rows) * SCALE_YD * (-1.0 if FLIP_X else 1.0)  # (n, 1)
    zs = TEE_Z - cols * SCALE_YD                                # (1, n)
    X = np.broadcast_to(xs, (n, n))
    Z = np.broadcast_to(zs, (n, n))
    Y = (sub - DATUM_M) * M_TO_YD * VERT_SCALE

    # --- Golf features ------------------------------------------------------
    # Pond ellipse: CARVE-ONLY (never fill) to -1.2 yd, masked out under the
    # green disc. The valley floor under the pond is raw ~-4.3 yd — already
    # below the scene water plane (-0.6) — so only the lip rising toward
    # the green gets cut. The pond's far half (z -158..-170) lies under the
    # green disc in plan (green r=14 at z=-172 covers z -158..-186), exactly
    # as in build_hole12.py where the pond plane passes under the green;
    # the visible water is z -148..-158. Green is applied after the pond.
    dx = (X - POND["cx"]) / POND["rx"]
    dz = (Z - POND["cz"]) / POND["rz"]
    r_pond = np.sqrt(dx * dx + dz * dz)
    w_pond = 1.0 - np.clip((r_pond - 1.0) * POND["rz"] / POND["blend"], 0.0, 1.0)
    w_pond = np.where(r_pond <= 1.0, 1.0, w_pond)
    w_pond = w_pond * w_pond * (3 - 2 * w_pond)
    d_green = np.sqrt((X - 0.0) ** 2 + (Z - (-172.0)) ** 2)
    w_pond = np.where(d_green < 26.0, 0.0, w_pond)  # keep green disc intact
    Y = Y * (1 - w_pond) + np.minimum(Y, POND["y"]) * w_pond
    for _name, cx, cz, r_in, r_out, target in FEATURES:
        d = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
        # smoothstep blend: 1 inside r_in, 0 outside r_out
        t = np.clip((d - r_in) / (r_out - r_in), 0.0, 1.0)
        w = 1.0 - (t * t * (3 - 2 * t))
        w = np.where(d <= r_in, 1.0, np.where(d >= r_out, 0.0, w))
        Y = Y * (1 - w) + target * w

    # --- Normals (central differences on the yard grid) ----------------------
    spacing = STEP * SCALE_YD  # yards between adjacent verts
    gy, gx = np.gradient(Y, spacing, spacing)  # dY/dz, dY/dx
    N = np.stack([-gx, np.ones_like(Y), -gy], axis=-1)
    N /= np.linalg.norm(N, axis=-1, keepdims=True)

    # --- Material (.mtl): grass green diffuse. Godot's OBJ importer turns
    # Kd into a StandardMaterial3D albedo (shaded). The terrain is sloped,
    # not flat, so it shades like the pines' canopies (which read fine) —
    # unlike the flat ground tile, whose horizontal top face went black.
    # Minimal .mtl (Kd only): extra Ka/Ks/Ns lines tripped the importer's
    # parser on the Mac (ERR_INVALID_DATA, Nov 13). If the terrain still
    # reads too dark on the Mac frame, the fallback is to override the
    # material unshaded in the .tscn (see build_hole12.py).
    mtl_path = os.path.join(outdir, "wyatt-hole12-terrain.mtl")
    with open(mtl_path, "w") as f:
        f.write("# Wyatt National Hole 12 terrain material\n")
        f.write("newmtl terrain_grass\n")
        f.write("Kd 0.28 0.58 0.28\n")

    # --- Write OBJ (Y-up, matches Godot) ------------------------------------
    obj_path = os.path.join(outdir, "wyatt-hole12-terrain.obj")
    with open(obj_path, "w") as f:
        f.write("# Wyatt National Hole 12 terrain — LiDAR fallback mesh\n")
        f.write(f"# source md5 {md5}; grid {n}x{n}; step {STEP}; "
                f"scale {SCALE_YD:.4f} yd/px; vert_scale {VERT_SCALE}\n")
        f.write("mtllib wyatt-hole12-terrain.mtl\n")
        f.write("usemtl terrain_grass\n")
        for r in range(n):
            for c in range(n):
                f.write(f"v {X[r, c]:.3f} {Y[r, c]:.3f} {Z[r, c]:.3f}\n")
        for r in range(n):
            for c in range(n):
                f.write(f"vn {N[r, c, 0]:.4f} {N[r, c, 1]:.4f} {N[r, c, 2]:.4f}\n")
        # faces: two triangles per quad, CCW seen from above (+Y)
        for r in range(n - 1):
            for c in range(n - 1):
                a = r * n + c + 1
                b = a + 1
                d0 = a + n
                e = d0 + 1
                # faces: two triangles per quad, CCW seen from above (+Y).
                # Grid: +row -> -x, +col -> -z, so (a, e, d0) / (a, b, e)
                # wind upward; (a, d0, e) winds downward (verified Nov 13).
                f.write(f"f {a}//{a} {e}//{e} {d0}//{d0}\n")
                f.write(f"f {a}//{a} {b}//{b} {e}//{e}\n")

    # --- Preview (grayscale heights, orientation check) -----------------------
    prev = ((Y - Y.min()) / (Y.max() - Y.min()) * 255).astype(np.uint8)
    Image.fromarray(prev, mode="L").save(
        os.path.join(outdir, "wyatt-hole12-terrain-preview.png"))

    # --- Verification ---------------------------------------------------------
    def sample(x: float, z: float) -> float:
        # Grid indices: x = (252 - 2*r) * S (or flipped), z = 8 - 2*c * S.
        # Centre of the grid (x=0) is r=126; z=0 is c~=6 (tee col is z=+8).
        if FLIP_X:
            r = int(round(126.0 + x / (2 * SCALE_YD)))
        else:
            r = int(round(126.0 - x / (2 * SCALE_YD)))
        c = int(round((TEE_Z - z) / (2 * SCALE_YD)))
        r = min(max(r, 0), n - 1)
        c = min(max(c, 0), n - 1)
        # nearest grid vertex (grid spacing ~1.27 yd, so within ~0.9 yd)
        return float(Y[r, c])

    checks = {
        "source_md5_ok": md5 == EXPECTED_MD5,
        "grid": f"{n}x{n}",
        "verts": int(n * n),
        "tris": int((n - 1) * (n - 1) * 2),
        "x_range_yd": [round(float(X.min()), 1), round(float(X.max()), 1)],
        "z_range_yd": [round(float(Z.min()), 1), round(float(Z.max()), 1)],
        "y_range_yd": [round(float(Y.min()), 2), round(float(Y.max()), 2)],
        "tee_centre_y": round(sample(0, 0), 2),
        "green_centre_y": round(sample(0, -172), 2),
        "pin_y": round(sample(-6, -166), 2),
        # visible pond is z -148..-158 (far half hides under the green disc);
        # its floor must sit below the scene water plane at -0.6 yd.
        "pond_visible_y": round(sample(0, -153), 2),
        "pond_below_water_plane": bool(sample(0, -153) < -0.6
                                       and sample(0, -150) < -0.6),
        "bunker_centre_y": round(sample(0, -186), 2),
    }
    # centreline profile (x=0) every ~21 yd
    profile = []
    for z in range(8, -312, -21):
        profile.append([z, round(sample(0, z), 2)])
    checks["centreline_profile_z_y"] = profile
    # shape preservation outside feature discs: processed vs raw-scaled
    Y_raw_scaled = (sub - DATUM_M) * M_TO_YD * VERT_SCALE
    far = np.ones_like(Y, dtype=bool)
    for _name, cx, cz, r_in, r_out, _t in FEATURES:
        far &= np.sqrt((X - cx) ** 2 + (Z - cz) ** 2) > (r_out + 10)
    far &= np.sqrt(((X - POND["cx"]) / POND["rx"]) ** 2
                   + ((Z - POND["cz"]) / POND["rz"]) ** 2) > 1.5
    corr = float(np.corrcoef(Y[far], Y_raw_scaled[far])[0, 1])
    checks["shape_corr_outside_features"] = round(corr, 4)
    # winding: sample triangle normal Y must be positive (upward faces).
    # OBJ triangles are (a, e, d0): a=(r,c), e=(r+1,c+1), d0=(r+1,c).
    p0 = np.array([X[100, 100], Y[100, 100], Z[100, 100]])
    p1 = np.array([X[101, 101], Y[101, 101], Z[101, 101]])
    p2 = np.array([X[101, 100], Y[101, 100], Z[101, 100]])
    fn = np.cross(p1 - p0, p2 - p0)
    checks["sample_face_normal_y_positive"] = bool(fn[1] > 0)

    assert checks["tee_centre_y"] == 7.3, checks
    assert checks["green_centre_y"] == 0.0, checks
    assert checks["pond_below_water_plane"], checks
    assert checks["shape_corr_outside_features"] > 0.99, checks
    assert checks["sample_face_normal_y_positive"], "winding is downward"

    manifest = {
        "source": "unreal/terrain/wyatt-hole12-heightmap-505.png",
        "source_md5": md5,
        "elev_m": [ZMIN_M, ZMAX_M],
        "datum_m": DATUM_M,
        "vert_scale": VERT_SCALE,
        "step": STEP,
        "scale_yd_per_px": round(SCALE_YD, 4),
        "flip_x": FLIP_X,
        "anchors": {"tee_col_to_z": [TEE_COL, TEE_Z],
                    "pond_col_to_z": [POND_COL, POND_Z]},
        "features": [{"name": nm, "x": cx, "z": cz, "r_in": ri, "r_out": ro,
                      "y": t} for nm, cx, cz, ri, ro, t in FEATURES],
        "pond": POND,
        "known_limits": [
            "Green is flat 0.0 — Step 5 imports the real green heightfield "
            "from sim/greens.py over this disc.",
            "Orientation (FLIP_X) must be verified against "
            "wyatt-hole12-preview-hillshade.png on the Mac.",
            "Trees/grass/water shader are separate look-dev steps, not in this mesh.",
        ],
        "checks": checks,
    }
    with open(os.path.join(outdir, "wyatt-hole12-terrain-manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(checks, indent=2))
    print(f"wrote {obj_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
