# Capture node for the Hole 12 scene. Attach to a Node in hole_12.tscn.
# When Godot is run with --capture on the command line, waits ~2s for the
# frame to settle, saves the viewport to ~/godot-hole12-frame.png on the
# Mac, and quits. Without --capture it does nothing, so the broadcast
# runs normally. This exists because running the scene directly (as the
# main scene) is the ONLY way the addon global classes (Sky3D,
# PhantomCamera) resolve — the -s SceneTree-script path never populates
# the ClassDB with them, so Sky3D/PhantomCamera became placeholders and
# the frame rendered black (v34/v35/v36/v37).
extends Node

var frames := 0
var do_capture := false

func _ready() -> void:
	do_capture = "--capture" in OS.get_cmdline_args()

func _process(_delta: float) -> void:
	if not do_capture:
		return
	frames += 1
	if frames == 120:
		var img: Image = get_viewport().get_texture().get_image()
		var err: Error = img.save_png("/Users/masonwyatt/godot-hole12-frame.png")
		if err == OK:
			print("FRAME-SAVED /Users/masonwyatt/godot-hole12-frame.png")
		else:
			print("FRAME-FAILED err=", err)
		get_tree().quit()
