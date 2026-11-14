# setup_terrain3d.gd — Build the Mas Golfs Hole 12 Terrain3D terrain, headless.
#
# Replaces the OBJ terrain mesh (godot/tools/wyatt-hole12-terrain.obj) in
# godot/scenes/hole_12.tscn with a real Terrain3D node: LiDAR heightmap
# imported at full 16-bit precision, PBR grass/sand texture layers, and
# painted fairway/green/bunker zones. No editor GUI needed.
#
# RUN (on the Mac, from the repo root ~/mas-golfs):
#   /Applications/Godot.app/Contents/MacOS/Godot --headless \
#       --path ~/mas-golfs/godot -s res://tools/setup_terrain3d.gd
# See docs/terrain3d-setup-runbook.md for the full runner commands.
#
# PREREQUISITES (on the Mac, before running):
#   - godot/tools/wyatt-hole12-terrain.r16 + wyatt-hole12-terrain-r16.json
#     (built on the VM by godot/tools/heightmap_to_r16.py, transferred
#     via device files.write vm_path — same as the heightmap PNG).
#   - godot/textures/ Grass004/Grass006 Color + NormalGL JPGs and
#     sand-detail.png (already on the Mac).
#   - Terrain3D + Sky3D addons enabled in project.godot (already done).
#
# WHAT IT DOES (in order):
#   1. Reads the R16 manifest (y_min/y_max, image size, import position).
#   2. Loads the R16 heightmap via Terrain3DUtil.load_image (full 16-bit
#      precision — the 16-bit PNG cannot be imported directly because
#      Godot reads PNGs as 8-bit and the terrain would terrace).
#   3. Builds a Terrain3DMaterial (autoshader OFF, manual painting) and
#      a Terrain3DAssets with 4 texture layers, saves both as .tres.
#   4. Creates a Terrain3D node (region_size 256, vertex_spacing 0.6336
#      yd/px), imports the heightmap, paints the control map.
#   5. Saves the terrain data (region .res files) to res://terrain_data/hole12.
#   6. Loads hole_12.tscn, removes the OBJ "Terrain" node and the flat
#      "Tee"/"Green"/"Collar"/"Bunker" discs (replaced by Terrain3D
#      painting), adds the Terrain3D node, saves the scene.
#      A backup is written to hole_12.tscn.bak first, and the saved
#      scene is re-loaded and verified before the script exits.
#   7. Prints verification: get_height at tee/green/pin/pond/bunker and
#      get_control_base_id at sample points. Exits 0 on success, 1 on
#      any failure.
#
# IDEMPOTENT: safe to re-run. It deletes the terrain data directory and
# re-imports from scratch, and it reuses an existing Terrain3D node in
# the scene if one is already there (instead of adding a duplicate).
#
# HEADLESS LIMITS (see the runbook):
#   - Shadows stay OFF (as in v29). Terrain3D's PBR + real normals are
#     the fix for the black-terrain shadow failure, but turning shadows
#     on is a separate look-dev step after this frame lands.
#   - The normal-map JPGs are loaded as-is. If the terrain normals look
#     wrong (too bumpy / inverted), set the NormalGL JPGs' import to
#     "Normal Map" in the editor and re-run.
#   - The green is flat 0.0 (the real green heightfield from
#     sim/greens.py is a later step, as in the OBJ converter).
extends SceneTree

const MANIFEST_PATH := "res://tools/wyatt-hole12-terrain-r16.json"
const R16_PATH := "res://tools/wyatt-hole12-terrain.r16"
const SCENE_PATH := "res://scenes/hole_12.tscn"
const DATA_DIR := "res://terrain_data/hole12"
const MATERIAL_PATH := "res://terrain_data/hole12/material.tres"
const ASSETS_PATH := "res://terrain_data/hole12/assets.tres"

const TEX_ROUGH_ALBEDO := "res://textures/Grass006_Color.jpg"
const TEX_ROUGH_NORMAL := "res://textures/Grass006_NormalGL.jpg"
const TEX_FAIRWAY_ALBEDO := "res://textures/Grass004_Color.jpg"
const TEX_FAIRWAY_NORMAL := "res://textures/Grass004_NormalGL.jpg"
const TEX_SAND_ALBEDO := "res://textures/sand-detail.png"

# Texture asset IDs. 0 is the default: fresh regions render texture 0
# wherever nothing is painted, so 0 must be the rough.
const TEX_ROUGH := 0
const TEX_FAIRWAY := 1
const TEX_GREEN := 2
const TEX_SAND := 3

# Painting zones (world yards). Hole 12 is a par 3: no fairway corridor,
# just a mown tee box, the green + a mown apron ring, and the bunker.
# Everything else stays rough (texture 0, the default).
# Paint order matters: apron ring first, then green over its centre,
# then tee and bunker (they do not overlap anything else).
const ZONES := [
	# [centre_x, centre_z, r_inner, r_outer, texture_id, label]
	[0.0, -172.0, 14.0, 22.0, TEX_FAIRWAY, "apron"],
	[0.0, -172.0, 0.0, 14.0, TEX_GREEN, "green"],
	[0.0, 0.0, 0.0, 10.0, TEX_FAIRWAY, "tee"],
	[0.0, -186.0, 0.0, 7.0, TEX_SAND, "bunker"],
]

var _errors: Array[String] = []


func _initialize() -> void:
	var ok := _run()
	if ok:
		print("=== setup_terrain3d: SUCCESS ===")
	else:
		printerr("=== setup_terrain3d: FAILED ===")
		for e in _errors:
			printerr("  ERROR: " + e)
	quit(0 if ok else 1)


func _fail(msg: String) -> void:
	_errors.append(msg)
	printerr("ERROR: " + msg)


func _load_manifest() -> Dictionary:
	if not FileAccess.file_exists(MANIFEST_PATH):
		_fail("manifest not found: " + MANIFEST_PATH
			+ " (run godot/tools/heightmap_to_r16.py on the VM and transfer it)")
		return {}
	var file := FileAccess.open(MANIFEST_PATH, FileAccess.READ)
	if file == null:
		_fail("cannot open manifest: " + MANIFEST_PATH)
		return {}
	var text := file.get_as_text()
	file.close()
	var json := JSON.new()
	if json.parse(text) != OK:
		_fail("manifest is not valid JSON: " + MANIFEST_PATH)
		return {}
	return json.data


func _make_material() -> Terrain3DMaterial:
	var mat := Terrain3DMaterial.new()
	# Manual painting. The autoshader is off globally, so the control
	# map we paint is what renders. (Fresh regions default to
	# autoshader per-pixel, but the material-level switch overrides it.)
	mat.auto_shader_enabled = false
	# No background mesh beyond the terrain: the sky's ground colour
	# already covers the far field (as in the v27 scene).
	mat.world_background = Terrain3DMaterial.NONE
	return mat


func _make_texture_asset(asset_name: String, tex_id: int,
		albedo_path: String, normal_path: String,
		uv_scale: float, albedo_color: Color) -> Terrain3DTextureAsset:
	var ta := Terrain3DTextureAsset.new()
	ta.name = asset_name
	ta.id = tex_id
	ta.albedo_texture = load(albedo_path) as Texture2D
	if ta.albedo_texture == null:
		_fail("cannot load albedo texture: " + albedo_path)
	if normal_path != "":
		ta.normal_texture = load(normal_path) as Texture2D
		if ta.normal_texture == null:
			_fail("cannot load normal texture: " + normal_path)
	ta.uv_scale = uv_scale
	ta.albedo_color = albedo_color
	return ta


func _make_assets() -> Terrain3DAssets:
	var assets := Terrain3DAssets.new()
	var rough := _make_texture_asset("Rough", TEX_ROUGH,
		TEX_ROUGH_ALBEDO, TEX_ROUGH_NORMAL, 0.1, Color(1, 1, 1, 1))
	var fairway := _make_texture_asset("Fairway", TEX_FAIRWAY,
		TEX_FAIRWAY_ALBEDO, TEX_FAIRWAY_NORMAL, 0.1, Color(1, 1, 1, 1))
	# Same Grass004 as the fairway, tinted brighter so the green reads
	# as a distinct putting surface.
	var green := _make_texture_asset("Green", TEX_GREEN,
		TEX_FAIRWAY_ALBEDO, TEX_FAIRWAY_NORMAL, 0.1, Color(1.15, 1.2, 1.15, 1))
	# Sand has no normal map (flat grains at this scale); the albedo
	# alone is enough for the small bunker.
	var sand := _make_texture_asset("Sand", TEX_SAND,
		TEX_SAND_ALBEDO, "", 0.2, Color(1, 1, 1, 1))
	assets.set_texture_asset(TEX_ROUGH, rough)
	assets.set_texture_asset(TEX_FAIRWAY, fairway)
	assets.set_texture_asset(TEX_GREEN, green)
	assets.set_texture_asset(TEX_SAND, sand)
	return assets


func _paint_zone(data: Terrain3DData, vertex_spacing: float,
		zone: Array) -> int:
	var cx: float = zone[0]
	var cz: float = zone[1]
	var r_in: float = zone[2]
	var r_out: float = zone[3]
	var tex_id: int = int(zone[4])
	var label: String = zone[5]
	var painted := 0
	# Step across the zone's bounding box on the vertex grid.
	var x0 := cx - r_out
	var x1 := cx + r_out
	var z0 := cz - r_out
	var z1 := cz + r_out
	var x := x0
	while x <= x1:
		var z := z0
		while z <= z1:
			var dx := x - cx
			var dz := z - cz
			var d := sqrt(dx * dx + dz * dz)
			if d >= r_in and d <= r_out:
				var pos := Vector3(x, 0.0, z)
				# Match the Paint tool: blend 0, base == overlay == tex.
				data.set_control_base_id(pos, tex_id)
				data.set_control_overlay_id(pos, tex_id)
				data.set_control_blend(pos, 0.0)
				data.set_control_auto(pos, false)
				painted += 1
			z += vertex_spacing
		x += vertex_spacing
	print("  painted %s tex %d: %d px" % [label, tex_id, painted])
	return painted


func _verify_heights(data: Terrain3DData) -> bool:
	# (x, z, expected_y, label, tolerance)
	var checks := [
		[0.0, 0.0, 7.3, "tee", 0.15],
		[0.0, -172.0, 0.0, "green centre", 0.15],
		[-6.0, -166.0, 0.0, "Sunday pin", 0.15],
		[0.0, -153.0, -1.6, "pond (below water -0.6)", 0.6],
		[0.0, -186.0, -0.15, "bunker", 0.15],
	]
	var ok := true
	for c in checks:
		var pos := Vector3(c[0], 0.0, c[1])
		var h: float = data.get_height(pos)
		var want: float = c[2]
		var tol: float = c[4]
		var good := absf(h - want) <= tol
		print("  height %s at (%.1f, %.1f): %.2f (want %.2f) %s"
			% [c[3], c[0], c[1], h, want, "OK" if good else "MISMATCH"])
		if not good:
			_fail("height mismatch at %s: got %.2f want %.2f"
				% [c[3], h, want])
			ok = false
	return ok


func _verify_paint(data: Terrain3DData) -> bool:
	# (x, z, expected_base_id, label)
	var checks := [
		[0.0, 0.0, TEX_FAIRWAY, "tee box"],
		[0.0, -172.0, TEX_GREEN, "green centre"],
		[-6.0, -166.0, TEX_GREEN, "Sunday pin"],
		[0.0, -180.0, TEX_FAIRWAY, "apron (behind green)"],
		[0.0, -186.0, TEX_SAND, "bunker"],
		[40.0, -100.0, TEX_ROUGH, "rough (valley side)"],
		[-60.0, -250.0, TEX_ROUGH, "rough (behind green)"],
	]
	var ok := true
	for c in checks:
		var pos := Vector3(c[0], 0.0, c[1])
		var got: int = data.get_control_base_id(pos)
		var want: int = c[2]
		var good := got == want
		print("  paint %s at (%.1f, %.1f): base %d (want %d) %s"
			% [c[3], c[0], c[1], got, want, "OK" if good else "MISMATCH"])
		if not good:
			_fail("paint mismatch at %s: base %d want %d" % [c[3], got, want])
			ok = false
	return ok


func _run() -> bool:
	print("=== setup_terrain3d: start ===")

	# 1. Manifest + R16 ------------------------------------------------------
	var manifest := _load_manifest()
	if manifest.is_empty():
		return false
	var y_min: float = float(manifest["y_min_yd"])
	var y_max: float = float(manifest["y_max_yd"])
	var r16_w: int = int(manifest["r16_size_w_h"][0])
	var r16_h: int = int(manifest["r16_size_w_h"][1])
	var vs: float = float(manifest["vertex_spacing_yd"])
	var region_size: int = int(manifest["region_size_px"])
	var imp: Array = manifest["import_world_x_z"]
	var import_pos := Vector3(float(imp[0]), 0.0, float(imp[1]))
	print("manifest: r16 %dx%d, y %.3f..%.3f yd, vs %.4f, region %d, import (%s, %s)"
		% [r16_w, r16_h, y_min, y_max, vs, region_size, imp[0], imp[1]])
	if not FileAccess.file_exists(R16_PATH):
		_fail("R16 file not found: " + R16_PATH + " (transfer it from the VM)")
		return false

	# 2. Load the R16 heightmap (full 16-bit precision) ----------------------
	var height_img: Image = Terrain3DUtil.load_image(R16_PATH,
		ResourceLoader.CACHE_MODE_IGNORE,
		Vector2(y_min, y_max), Vector2i(r16_w, r16_h))
	if height_img == null or height_img.is_empty():
		_fail("Terrain3DUtil.load_image failed for " + R16_PATH)
		return false
	print("R16 loaded: %dx%d format %s" % [height_img.get_width(),
		height_img.get_height(), height_img.get_format()])
	var mm := Terrain3DUtil.get_min_max(height_img)
	print("R16 height range in image: %.3f..%.3f yd (want %.3f..%.3f)"
		% [mm.x, mm.y, y_min, y_max])

	# 3. Material + assets (.tres) -------------------------------------------
	var dir := DirAccess.open("res://")
	if dir == null:
		_fail("cannot open res://")
		return false
	if not dir.dir_exists("terrain_data"):
		dir.make_dir("terrain_data")
	if not dir.dir_exists("terrain_data/hole12"):
		dir.make_dir("terrain_data/hole12")
	# Fresh import: wipe any previous region files so a re-run does not
	# merge with stale regions. Do this BEFORE the Terrain3D node is
	# created / data_directory is set, so it cannot have loaded them.
	var data_dir := DirAccess.open(DATA_DIR)
	if data_dir != null:
		for f in data_dir.get_files():
			data_dir.remove(f)
	var mat := _make_material()
	if ResourceSaver.save(mat, MATERIAL_PATH) != OK:
		_fail("cannot save material to " + MATERIAL_PATH)
		return false
	var assets := _make_assets()
	if _errors.size() > 0:
		return false
	if ResourceSaver.save(assets, ASSETS_PATH) != OK:
		_fail("cannot save assets to " + ASSETS_PATH)
		return false
	print("saved material -> " + MATERIAL_PATH)
	print("saved assets   -> " + ASSETS_PATH)

	# 4. Terrain3D node + import ---------------------------------------------
	# Set ALL properties BEFORE add_child. The Terrain3D native data is
	# initialised when the node enters the tree, from the data_directory
	# (and region/vertex/material/assets) as they stand at entry. Setting
	# data_directory after add_child leaves data uninitialised and
	# import_images fails with "Data not initialized" (seen Nov 14).
	var terrain := Terrain3D.new()
	terrain.name = "Terrain3D"
	terrain.free_editor_textures = false
	terrain.region_size = region_size
	terrain.vertex_spacing = vs
	terrain.data_directory = DATA_DIR
	terrain.material = mat
	terrain.assets = assets
	root.add_child(terrain)
	print("importing heightmap at %s (offset 0, scale 1) ..." % import_pos)
	# import_images writes INTO existing regions; it does not create
	# them. A fresh Terrain3D has no regions, so import fails with
	# "Data not initialized". Create blank regions covering the whole
	# heightmap first (corners + centre), then import into them.
	var span_x := float(r16_w) * vs
	var span_z := float(r16_h) * vs
	var corners := [
		Vector3(import_pos.x, 0.0, import_pos.z),
		Vector3(import_pos.x + span_x, 0.0, import_pos.z),
		Vector3(import_pos.x, 0.0, import_pos.z + span_z),
		Vector3(import_pos.x + span_x, 0.0, import_pos.z + span_z),
		Vector3(import_pos.x + span_x * 0.5, 0.0, import_pos.z + span_z * 0.5),
	]
	for c in corners:
		terrain.data.add_region_blankp(c, false)
	terrain.data.update_maps(Terrain3DRegion.TYPE_MAX, true, false)
	print("regions after blank creation: %d" % terrain.data.get_region_count())
	terrain.data.import_images([height_img, null, null], import_pos, 0.0, 1.0)
	var regions: Array = terrain.data.get_regions_active()
	print("regions after import: %d" % regions.size())
	if regions.size() == 0:
		_fail("import produced no regions")
		return false
	terrain.data.calc_height_range(true)
	var hr := terrain.data.get_height_range()
	print("terrain height range: %.2f..%.2f yd" % [hr.x, hr.y])

	# 5. Paint the control map ----------------------------------------------
	print("painting zones (base=overlay=tex, blend 0, manual) ...")
	var total := 0
	for zone in ZONES:
		total += _paint_zone(terrain.data, vs, zone)
	print("painted %d px total" % total)
	terrain.data.update_maps(Terrain3DRegion.TYPE_MAX, true, false)

	# 6. Verify before saving -------------------------------------------------
	print("verifying heights ...")
	var ok_h := _verify_heights(terrain.data)
	print("verifying paint ...")
	var ok_p := _verify_paint(terrain.data)
	if not (ok_h and ok_p):
		return false

	# 7. Save the terrain data ------------------------------------------------
	terrain.data.save_directory(DATA_DIR)
	print("saved terrain data -> " + DATA_DIR)
	var saved := DirAccess.open(DATA_DIR)
	if saved != null:
		print("data dir files: %s" % ", ".join(saved.get_files()))

	# 8. Swap the terrain into hole_12.tscn -----------------------------------
	print("updating scene " + SCENE_PATH + " ...")
	var scene_dir := DirAccess.open("res://scenes")
	if scene_dir != null and scene_dir.file_exists("hole_12.tscn.bak"):
		scene_dir.remove("hole_12.tscn.bak")
	var scene_text := FileAccess.get_file_as_string(SCENE_PATH)
	if scene_text.is_empty():
		_fail("cannot read scene: " + SCENE_PATH)
		return false
	var fa := FileAccess.open(SCENE_PATH + ".bak", FileAccess.WRITE)
	fa.store_string(scene_text)
	fa.close()
	print("backup written: " + SCENE_PATH + ".bak")
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		_fail("cannot load scene as PackedScene: " + SCENE_PATH)
		return false
	var scene_root := packed.instantiate()
	if scene_root == null:
		_fail("cannot instantiate scene: " + SCENE_PATH)
		return false
	# Remove the OBJ terrain + the flat feature discs. They are replaced
	# by the Terrain3D height + paint. Keep Pond (water plane),
	# Flagstick, Flag, the pines, Mas, camera, lights, environment.
	for node_name in ["Terrain", "Tee", "Green", "Collar", "Bunker"]:
		var old := scene_root.get_node_or_null(node_name)
		if old != null:
			scene_root.remove_child(old)
			old.free()
			print("  removed node: " + node_name)
		else:
			print("  (node already gone: " + node_name + ")")
	# Reuse the scene's existing Terrain3D node on a re-run.
	var existing := scene_root.get_node_or_null("Terrain3D")
	if existing != null:
		scene_root.remove_child(existing)
		existing.free()
		print("  removed stale Terrain3D node (re-run)")
	# Move our configured node into the scene.
	root.remove_child(terrain)
	scene_root.add_child(terrain)
	terrain.owner = scene_root
	# The old ArrayMesh ext_resource (id 3, the OBJ) is now unreferenced;
	# PackedScene.pack drops unreferenced ext_resources on save.
	var out := PackedScene.new()
	if out.pack(scene_root) != OK:
		_fail("PackedScene.pack failed")
		return false
	if ResourceSaver.save(out, SCENE_PATH) != OK:
		_fail("cannot save scene: " + SCENE_PATH)
		return false
	print("saved scene -> " + SCENE_PATH)

	# 9. Re-load the saved scene and confirm the Terrain3D node is there -----
	var check := load(SCENE_PATH) as PackedScene
	if check == null:
		_fail("saved scene does not load: " + SCENE_PATH)
		return false
	var check_root := check.instantiate()
	var check_t := check_root.get_node_or_null("Terrain3D")
	if check_t == null:
		_fail("saved scene has no Terrain3D node")
		return false
	print("verified: saved scene loads, Terrain3D node present, "
		+ "data_directory = " + str(check_t.data_directory))
	check_root.free()
	scene_root.free()
	return _errors.size() == 0
