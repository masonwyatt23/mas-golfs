# import_terrain_editor.gd — Run the Terrain3D importer in headless EDITOR mode.
#
# The Terrain3D data is initialised by the editor plugin. A SceneTree
# script (-s res://tools/setup_terrain3d.gd) cannot initialise it: the
# Terrain3DData stays uninitialised and import_images / add_region fail
# with "Data not initialized" (and add_region_blankp segfaults). The
# supported path is the importer scene (addons/terrain_3d/tools/importer.tscn)
# driven from the editor, which is what this EditorScript does.
#
# RUN (on the Mac, from the repo root ~/mas-golfs):
#   /Applications/Godot.app/Contents/MacOS/Godot --headless --editor \
#       --path ~/mas-golfs/godot --script res://tools/import_terrain_editor.gd
#
# PREREQUISITES (on the Mac):
#   - godot/tools/wyatt-hole12-terrain.r16 + wyatt-hole12-terrain-r16.json
#     (transferred already).
#   - Terrain3D + Sky3D addons enabled (already done).
#
# WHAT IT DOES:
#   1. Loads addons/terrain_3d/tools/importer.tscn, adds it to the edited
#      scene root so the editor plugin manages the Terrain3D node.
#   2. Sets the importer properties from the R16 manifest (height file,
#      r16_range, r16_size, import_position, destination_directory).
#   3. Calls start_import() then save_data().
#   4. Prints SUCCESS/FAILED and quits the editor.
@tool
extends EditorScript

const MANIFEST_PATH := "res://tools/wyatt-hole12-terrain-r16.json"
const R16_PATH := "res://tools/wyatt-hole12-terrain.r16"
const IMPORTER_SCENE := "res://addons/terrain_3d/tools/importer.tscn"
const DATA_DIR := "res://terrain_data/hole12"


func _run() -> void:
	print("=== import_terrain_editor: start ===")
	var manifest := _load_manifest()
	if manifest.is_empty():
		_fail("manifest not found or invalid: " + MANIFEST_PATH)
		return
	var y_min: float = float(manifest["y_min_yd"])
	var y_max: float = float(manifest["y_max_yd"])
	var r16_w: int = int(manifest["r16_size_w_h"][0])
	var r16_h: int = int(manifest["r16_size_w_h"][1])
	var vs: float = float(manifest["vertex_spacing_yd"])
	var region_size: int = int(manifest["region_size_px"])
	var imp: Array = manifest["import_world_x_z"]
	# import_position is in region units (descaled): world / vertex_spacing,
	# rounded to the nearest region_size (per the Terrain3D docs).
	var import_x := int(round(float(imp[0]) / vs / region_size)) * region_size
	var import_y := int(round(float(imp[1]) / vs / region_size)) * region_size
	print("manifest: r16 %dx%d, y %.3f..%.3f, vs %.4f, region %d, import world (%s, %s) -> region (%d, %d)"
		% [r16_w, r16_h, y_min, y_max, vs, region_size, imp[0], imp[1], import_x, import_y])

	var packed := load(IMPORTER_SCENE) as PackedScene
	if packed == null:
		_fail("cannot load importer scene: " + IMPORTER_SCENE)
		return
	var importer := packed.instantiate()
	if importer == null:
		_fail("cannot instantiate importer scene")
		return
	# Add to the edited scene root so the editor plugin manages it.
	var editor_root := get_editor_interface().get_edited_scene_root()
	if editor_root == null:
		# No scene open; create a fresh root and add the importer under it.
		editor_root = Node3D.new()
		editor_root.name = "TerrainImport"
		get_editor_interface().get_edited_scene_root()
		# Fall back: add to the editor's scene tree via the interface.
		get_editor_interface().get_base_control().add_child(editor_root)
	editor_root.add_child(importer)
	importer.owner = editor_root

	# Configure the importer from the manifest.
	importer.height_file_name = R16_PATH
	importer.r16_range = Vector2(y_min, y_max)
	importer.r16_size = Vector2i(r16_w, r16_h)
	importer.import_position = Vector2i(import_x, import_y)
	importer.destination_directory = DATA_DIR
	# The importer needs a data directory to write to; ensure it exists.
	var dir := DirAccess.open("res://")
	if dir != null:
		if not dir.dir_exists("terrain_data"):
			dir.make_dir("terrain_data")
		if not dir.dir_exists("terrain_data/hole12"):
			dir.make_dir("terrain_data/hole12")
	print("importer configured: height=%s r16_range=(%.3f, %.3f) r16_size=(%d, %d) import_position=(%d, %d) dest=%s"
		% [R16_PATH, y_min, y_max, r16_w, r16_h, import_x, import_y, DATA_DIR])

	importer.start_import()
	print("import finished; regions: %d" % importer.data.get_region_count())
	importer.save_data()
	print("saved terrain data -> " + DATA_DIR)
	var saved := DirAccess.open(DATA_DIR)
	if saved != null:
		print("data dir files: %s" % ", ".join(saved.get_files()))
	print("=== import_terrain_editor: SUCCESS ===")


func _load_manifest() -> Dictionary:
	if not FileAccess.file_exists(MANIFEST_PATH):
		return {}
	var file := FileAccess.open(MANIFEST_PATH, FileAccess.READ)
	if file == null:
		return {}
	var text := file.get_as_text()
	file.close()
	var json := JSON.new()
	if json.parse(text) != OK:
		return {}
	return json.data


func _fail(msg: String) -> void:
	printerr("ERROR: " + msg)
	printerr("=== import_terrain_editor: FAILED ===")
