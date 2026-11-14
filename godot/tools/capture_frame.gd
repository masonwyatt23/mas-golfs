# Capture a real rendered frame of the Hole 12 scene and quit.
# Run: Godot --path godot -s res://tools/capture_frame.gd --resolution 1920x1080
# Renders the scene in a window, waits ~2s for the frame to settle, saves
# the viewport to ~/godot-hole12-frame.png on the Mac, and quits.
# Uses Godot's own viewport capture (not macOS screencapture), so it works
# even when the Mac display is locked or the runner has no WindowServer access.
extends SceneTree

var frames := 0
var inst: Node = null

func _initialize() -> void:
	# v37: the scene is instantiated on the FIRST _process frame, not
	# in _initialize. In -s mode, _initialize runs before the engine
	# has populated the ClassDB with the global script classes
	# (class_name) from addons, so instantiating there makes Sky3D /
	# PhantomCamera nodes fail ("Cannot get class") and become
	# placeholders — the real cause of the v34/v35 black frame.
	# Deferring to _process (after full init) lets the ClassDB resolve
	# them. The explicit addon loads are kept as a belt-and-braces.
	load("res://addons/sky_3d/src/Sky3D.gd")
	load("res://addons/phantom_camera/scripts/phantom_camera/phantom_camera_3d.gd")
	load("res://addons/phantom_camera/scripts/phantom_camera_host/phantom_camera_host.gd")

func _process(_delta: float) -> bool:
	frames += 1
	if frames == 1:
		var scene: PackedScene = load("res://scenes/hole_12.tscn")
		inst = scene.instantiate()
		root.add_child(inst)
	if frames == 120:
		var img: Image = root.get_texture().get_image()
		var err: Error = img.save_png("/Users/masonwyatt/godot-hole12-frame.png")
		if err == OK:
			print("FRAME-SAVED /Users/masonwyatt/godot-hole12-frame.png")
		else:
			print("FRAME-FAILED err=", err)
		return true
	return false
