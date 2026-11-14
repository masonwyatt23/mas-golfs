# Capture a real rendered frame of the Hole 12 scene and quit.
# Run: Godot --path godot -s res://tools/capture_frame.gd --resolution 1920x1080
# Renders the scene in a window, waits ~2s for the frame to settle, saves
# the viewport to ~/godot-hole12-frame.png on the Mac, and quits.
# Uses Godot's own viewport capture (not macOS screencapture), so it works
# even when the Mac display is locked or the runner has no WindowServer access.
extends SceneTree

var frames := 0

func _initialize() -> void:
	# v36: when Godot runs a SceneTree script with -s, the global
	# script classes (class_name) from addons are NOT registered in
	# the ClassDB, so the scene's Sky3D / PhantomCamera nodes fail
	# to instantiate ("Cannot get class") and become placeholders —
	# which is why v34/v35 rendered black (no Sky3D sun/sky, no
	# Phantom Camera). Explicitly loading the addon scripts first
	# registers their class_names, so the scene instantiates fully.
	# (The .godot global class cache is correct — the -s runner just
	# doesn't populate ClassDB from it.)
	load("res://addons/sky_3d/src/Sky3D.gd")
	load("res://addons/phantom_camera/scripts/phantom_camera/phantom_camera_3d.gd")
	load("res://addons/phantom_camera/scripts/phantom_camera_host/phantom_camera_host.gd")
	var scene: PackedScene = load("res://scenes/hole_12.tscn")
	var inst: Node = scene.instantiate()
	root.add_child(inst)

func _process(_delta: float) -> bool:
	frames += 1
	if frames == 120:
		var img: Image = root.get_texture().get_image()
		var err: Error = img.save_png("/Users/masonwyatt/godot-hole12-frame.png")
		if err == OK:
			print("FRAME-SAVED /Users/masonwyatt/godot-hole12-frame.png")
		else:
			print("FRAME-FAILED err=", err)
		return true
	return false
