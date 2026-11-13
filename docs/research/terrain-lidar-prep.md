# Mas Golfs — Terrain / LiDAR Prep for the Unreal Vertical Slice

**Status:** terrain prep complete, $0 spent, no GPU used, no purchases. The 16-bit heightmap for Hole 12 "The Picture" is ready for Unreal Landscape import. Hand-authoring of the golf features (tee/green flattening, pond carving, bunkers) is a later step done in Unreal — see §8.

**Deliverables** (all under `unreal/terrain/`):

| File | What it is | Size |
|------|-----------|------|
| `wyatt-hole12-heightmap-505.png` | 16-bit grayscale PNG heightmap, 505×505 px, 1 m/px — **the Unreal import file** | 367,308 bytes (md5 `37bb377111f3cdda3fd5a8c9bf80a5f5`) |
| `wyatt-hole12-source-clip-1m.tif` | The raw 1 m DEM clip, float32 GeoTIFF, EPSG:26917 — the reproducible source | 981,629 bytes (md5 `312be8cd092f96eba0e6312598f1379b`) |
| `wyatt-hole12-preview-hillshade.png` | 8-bit hillshade preview of the heightmap (orientation check) | 129,163 bytes (md5 `9499a106cfbe3f168c7ce7fb0ea5fd33`) |

---

## 1. The site — what it is and why

Wyatt National is fictional, so there is no LiDAR of it. Per `docs/unreal-vertical-slice.md` §3, the base landform is **real LiDAR of analogous terrain**: Blue Ridge foothill terrain east of Staunton, VA (the course's setting).

**Chosen window — 505 m × 505 m, centered lon −78.99270, lat 38.14465**, ~8 km east of downtown Staunton, VA, in the Shenandoah Valley → Blue Ridge foothill transition:

| Corner | UTM 17N (EPSG:26917) | WGS84 |
|--------|----------------------|-------|
| NW | E 675644.96, N 4224020.47 | lon −78.99552, lat 38.14697 |
| NE | E 676149.96, N 4224020.47 | lon −78.98976, lat 38.14688 |
| SW | E 675644.96, N 4223515.47 | lon −78.99564, lat 38.14242 |
| SE | E 676149.96, N 4223515.47 | lon −78.98988, lat 38.14233 |
| Center | E 675897.46, N 4223767.97 | lon −78.99270, lat 38.14465 |

**Why this window:** scouted first at 10 m resolution over a 6.9 km × 7.8 km area east of Staunton (see §3.2). This window scored the best of ~13,700 candidate 505 m windows on the criteria that matter for Hole 12: a real valley running diagonally NW–SE through the middle (center ~21 m lower than the window edges), 40.8 m of relief, mean slope 0.21, max slope 0.68. The valley floor (~375–377 m) is where the pond basin gets carved; the west rim (~409 m) is the natural tee side; the east rim's lower bench is the natural green side. The shape is a downhill-over-a-valley par 3 in miniature — the same golf idea as Hole 12, found in real ground instead of sculpted from nothing.

**Elevation (1 m data):** min 375.36 m, max 414.94 m, mean 394.94 m, relief 39.58 m. Mean slope 0.213, p95 slope 0.474. Zero nodata pixels in the window.

**Orientation note for the build:** PNG row 0 = north edge (lat 38.14697), row 504 = south edge (lat 38.14242); column 0 = west edge (lon −78.99552), column 504 = east edge (lon −78.98976). The valley runs NW–SE. Verify against the hillshade preview after import — if the valley reads mirrored in-editor, use the import dialog's flip options or rotate the Landscape actor 180°.

---

## 2. Source data — exact sources

### 2.1 The 1 m DEM (the data actually used)

- **Product:** USGS 1 Meter DEM, tile `17 x67y423`, project `VA_NorthernShenandoah_2020_D20`
- **Collection:** 2020 LiDAR, published 2023-05-02
- **Tile download URL (public, no account):** https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/VA_NorthernShenandoah_2020_D20/TIFF/USGS_1M_17_x67y423_VA_NorthernShenandoah_2020_D20.tif
- **Tile extent:** 10,012 × 10,012 px at 1 m, EPSG:26917 (NAD83 / UTM zone 17N), bounds E 669994–680006, N 4219994–4230006; float32, LZW-compressed, 512×512 internal tiles, nodata −999999; ~317 MB for the full tile (only the 505×505 window was fetched — see §3.3)
- **Metadata (ScienceBase):** https://www.sciencebase.gov/catalog/item/646702e5d34ec11ae4a7fadd
- **Discovery query (TNM Download API v1, run 2026-11-13):** `https://tnmaccess.nationalmap.gov/api/v1/products?datasets=Digital%20Elevation%20Model%20(DEM)%201%20meter&bbox=-79.05,38.08,-78.90,38.20&prodFormats=GeoTIFF&outputFormat=JSON` — returned 9 tiles; `x67y423` is the one covering the chosen site.
- **License:** public domain (USGS 3DEP). No account, no key, no cost.

### 2.2 The 10 m scout DEM (site selection only, not used in the heightmap)

- **Service:** USGS 3DEP Elevation ImageServer (seamless 1/3 arc-second, ~10 m)
- **Request:** `https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?bbox=-79.02,38.09,-78.94,38.16&bboxSR=4326&size=690,780&imageSR=4326&format=tiff&pixelType=F32&f=image`
- **Result:** 690×780 px, ~10.2 m/px, elev 358.3–483.5 m, no nodata. Used only to rank candidate windows (§1).

### 2.3 What was NOT downloaded

- **No LAS/LAZ point cloud.** The 1 m DEM GeoTIFF was sufficient; the slice plan's PDAL step (LAS → DEM) is unnecessary when the finished 1 m DEM exists for the tile.
- **No full-tile download.** The window was read over HTTPS with GDAL range requests (see §3.3) — a few MB transferred instead of ~317 MB.

---

## 3. Conversion pipeline — exact commands

### 3.1 Environment

```bash
python3 -m venv /tmp/geo-venv
/tmp/geo-venv/bin/pip install rasterio pyproj pillow
# rasterio 1.5.2, pyproj (PROJ bundled), pillow — all free, all pip-installable
```

Note: `/tmp/geo-venv` is ephemeral (this VM wipes `/tmp` on turnover). The three `pip install` lines above are the full reproducible environment — nothing else is needed. System `pip3` is PEP 668 externally-managed, which is why the venv is used. GDAL itself was **not** installed separately; rasterio's wheel bundles it.

**SSL quirk (sandbox only):** this VM's network path presents a self-signed certificate in the chain, so rasterio/GDAL's HTTPS reads fail certificate verification. The workaround used here is `GDAL_HTTP_UNSAFESSL=YES` in the rasterio environment (see the fetch script). On a normal machine the S3 URL works without it — do not copy the workaround into production scripts without understanding it.

### 3.2 Site scouting (10 m)

Fetched the scout DEM (§2.2) with `curl`, then ranked every 505 m window on relief (15–45 m), mean slope (0.03–0.25), max slope (< 0.8), and "valley score" (window-edge mean minus center mean). Top candidate: center lon −78.99270, lat 38.14465, relief 40.8 m, valley +20.8 m. Verified by ASCII elevation map: high rims west and east, low channel NW–SE, W→E profile 409 → 377 → 410 m.

### 3.3 Windowed 1 m fetch (the real data)

```python
# /tmp/fetch_window.py — run with /tmp/geo-venv/bin/python
import numpy as np, rasterio
from rasterio.env import Env
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from pyproj import Transformer

URL = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/VA_NorthernShenandoah_2020_D20/TIFF/USGS_1M_17_x67y423_VA_NorthernShenandoah_2020_D20.tif"
CENTER_LON, CENTER_LAT = -78.99270, 38.14465
HALF = 252.5  # m -> 505 x 505 m window

tr = Transformer.from_crs("EPSG:4326", "EPSG:26917", always_xy=True)
cx, cy = tr.transform(CENTER_LON, CENTER_LAT)   # E 675897.46, N 4223767.97

with Env(GDAL_HTTP_UNSAFESSL="YES"):              # sandbox SSL quirk, see §3.1
    with rasterio.open(URL) as ds:
        win = from_bounds(cx-HALF, cy-HALF, cx+HALF, cy+HALF, ds.transform)
        a = ds.read(1, window=win, out_shape=(505, 505), resampling=Resampling.bilinear)
        # nodata count: 0. elev min 375.36 max 414.94 mean 394.94
        # saved as wyatt-hole12-source-clip-1m.tif (float32, EPSG:26917, LZW)
```

GDAL range-requests only the 512×512 internal tiles the window touches — no full-tile download. The `out_shape=(505, 505)` bilinear resample absorbs the sub-pixel window offset (the UTM window edges fall between source pixels); the resample shift is < 1 m and immaterial at this scale.

### 3.4 Heightmap export (16-bit PNG)

```python
# /tmp/make_heightmap2.py — run with /tmp/geo-venv/bin/python
import numpy as np, rasterio
a = np.load('/tmp/window_1m.npy').astype(np.float64)
zmin, zmax = a.min(), a.max()                    # 375.36 / 414.94 m
u16 = np.round((a - zmin) / (zmax - zmin) * 65535).astype(np.uint16)
with rasterio.open('unreal/terrain/wyatt-hole12-heightmap-505.png', 'w',
                   driver='PNG', height=505, width=505, count=1, dtype='uint16') as dst:
    dst.write(u16, 1)
```

Linear normalization, min → 0, max → 65535, no smoothing, no vertical exaggeration, no nodata fill needed (zero nodata pixels). PIL could not write uint16 via `fromarray` in this environment, so the PNG was written through rasterio/GDAL — verified round-trip below (§5).

---

## 4. Heightmap specification

| Property | Value |
|----------|-------|
| File | `unreal/terrain/wyatt-hole12-heightmap-505.png` |
| Dimensions | 505 × 505 px |
| Bit depth | 16-bit grayscale (PIL mode `I;16`, rasterio dtype `uint16`) |
| Value range in file | 0–65535 (min → 0, max → 65535) |
| Ground spacing | 1 m/px; window 505 m × 505 m |
| Elevation range | 375.36–414.94 m (relief 39.58 m) |
| Vertical precision in file | 39.58 m / 65535 ≈ 0.6 mm per step (no banding) |
| CRS of source | EPSG:26917 (NAD83 / UTM 17N); PNG itself is not georeferenced (Unreal doesn't read it) |
| Datum note | Source is NAD83; WGS84 lat/lon in §1 differ from NAD83 by ~1–2 m at this location — immaterial for a golf hole |

### 4.1 Unreal Z-scale math (verified against UE docs/forum sources)

Unreal maps a 16-bit PNG linearly: value 0 = lowest, 65535 = highest, 32767 = center, and the full range spans `512 × ZScale` centimeters. So:

```
range_cm  = (zmax - zmin) * 100 = 3958 cm
ZScale    = range_cm / 512       = 7.7314
actor Z   = zmin_cm + 256 * ZScale = 37536 + 1979.01 = 39515.01 cm (395.150 m)
check:    v=0     -> 375.36 m ;  v=65535 -> 414.94 m
```

**Effective in-engine vertical resolution:** Unreal quantizes Landscape heights to 512 steps across the Z range, so one step ≈ 39.58 m / 512 ≈ **7.7 cm**. That is the real precision of the imported terrain — far finer than any golf feature needs (greens are shaped to centimeter tolerances by hand later; the base landform only needs decimeter character).

**XY scale:** 100 (1 m per vertex). Strictly, a 505-vertex landscape at scale 100 spans 504 m, not 505 m (spacing = 504 intervals × 1 m); the 1 m difference is immaterial and scale 100 is the standard for 1 m data.

---

## 5. Verification (all run, all passing)

- **Heightmap round-trip:** re-read with rasterio — 505×505, dtype `uint16`, min 0, max 65535. PIL reports mode `I;16`, size 505×505.
- **Source clip round-trip:** re-read — 505×505, EPSG:26917, float32, bounds E 675644.96–676149.96, N 4223515.47–4224020.47.
- **1 m vs 10 m agreement:** 1 m window elev 375.36–414.94 m vs 10 m scout window 375.4–416.2 m — agrees within ~1 m, as expected across resolutions.
- **Valley shape persists at 1 m:** ASCII map of the 1 m data shows the same diagonal NW–SE low channel and high rims as the 10 m scout.
- **Nodata:** zero nodata pixels in the window; no fill/interpolation was applied anywhere — every value in the PNG is real measured elevation.
- **Z-scale check:** `v=0 → 375.36 m`, `v=65535 → 414.94 m` recomputed from the documented ZScale and actor Z — reproduces the source min/max exactly.

**Not verified here (cannot be, on this VM):** the actual Unreal import — there is no Unreal Engine on this machine. The import steps in §6 are the standard documented procedure; the first builder to run them should confirm the valley orientation and the Z values in-editor and record any correction here.

---

## 6. Unreal import steps (UE 5.8, per `docs/unreal-vertical-slice.md` §3.3)

1. Create the project from the **Blank** template (no starter content).
2. Open **Landscape Mode → Manage → New → Import from File**, select `unreal/terrain/wyatt-hole12-heightmap-505.png`.
3. In the import dialog, confirm/set:
   - **Overall Resolution:** 505 × 505 (auto-detected from the file)
   - **Section Size:** 63 × 63 Quads
   - **Sections per Component:** 2 × 2
   - **Number of Components:** 2 × 2 (505 = 2×2 components × 2 sections × 63 quads + 1)
   - **Location:** X 0, Y 0, **Z 39515.01 cm** (puts v=0 at the true 375.36 m absolute elevation; use Z 0 instead if absolute elevation doesn't matter and the Cesium backdrop is aligned separately)
   - **Scale:** X **100**, Y **100**, Z **7.7314**
4. Import. Check the result against `wyatt-hole12-preview-hillshade.png`: the valley must run NW–SE, high rims west and east, low channel in the middle. If it reads mirrored, flip in the import dialog or rotate the Landscape actor 180°.
5. Spot-check heights in-editor: valley floor ~375–377 m, west rim ~409–415 m, east rim ~405–412 m (absolute, if Z was set per step 3).

---

## 7. Sources

- USGS 3DEP program: https://www.usgs.gov/3d-elevation-program
- TNM Download API v1 (product discovery): https://tnmaccess.nationalmap.gov/api/v1/products
- 1 m DEM tile (S3): https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/VA_NorthernShenandoah_2020_D20/TIFF/USGS_1M_17_x67y423_VA_NorthernShenandoah_2020_D20.tif
- Tile metadata (ScienceBase): https://www.sciencebase.gov/catalog/item/646702e5d34ec11ae4a7fadd
- 3DEP Elevation ImageServer (scout): https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer
- Z-scale formula (`range(cm) / 512`): Cesium for Unreal height-map wiki, https://github-wiki-see.page/m/jgoffeney/Cesium4Unreal/wiki/Height-Maps ; corroborated by the UE forums thread on 16-bit PNG Landscape import, https://forums.unrealengine.com/t/landscape-from-heightmap-problem-with-file-format/1290415
- Related repo docs: `docs/unreal-vertical-slice.md` §3 (terrain pipeline), `docs/course-design-v2.md` §12 (Hole 12 design: 164 yd, 20 ft downhill, pond fronts the green, kidney green 28 yd wide)

---

## 8. What is NOT in this delivery (next steps, not gaps in the data)

- **Hand-authored golf features.** The tee box is not flattened, the green is not flattened, the pond basin is not carved, and there are no bunkers in this heightmap — it is raw real terrain. That authoring happens in Unreal's Landscape sculpt mode (or Gaea) per the slice plan §3.2 step 4, using the design elevations from `course-design-v2.md` §12 (tee ~6 m / 20 ft above the green; pond fronts the entire green; kidney green 28 yd wide). A before/after screenshot pair belongs in the repo when that step is done.
- **Layer masks** (fairway, rough, green, bunker, water table, cart path). Those come from the Gaea step in the slice plan, not from this prep.
- **A real pond in the base terrain.** The window's valley floor is dry ground at ~375–377 m; no water body was confirmed here. The Overpass API query for mapped ponds in the scout area failed with a 406 from the API (tried twice, GET and POST) and was not pursued — it doesn't matter, because the pond is hand-carved into the valley floor in either case. If the builder wants a real water reference, the National Hydrography Dataset for this quad is the authoritative source.
- **Full 18-hole terrain.** This is one 505 m tile for the one-hole slice. The full course will need 18 more tiles from the same region, picked the same way (scout at 10 m, rank windows, fetch 1 m windows). The pipeline in §3 is repeatable per tile.
