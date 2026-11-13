extends Node
## Director — the shot-state machine for the Hole 12 slice.
##
## SCAFFOLD: states and transitions are real (from
## docs/cinematic-direction.md §2, the 7-beat shot list); the camera
## moves are stubs until the terrain + character exist. The director
## never decides golf — it only stages what the bus already decided.
## Hard rules (cinematic-direction.md): always behind the golfer,
## never so zoomed on mobile you lose the hole, eased moves, NO cuts
## mid-swing / mid-flight / mid-putt.
##
## Beats: ADDRESS -> SWING -> TRACER -> LANDING -> GREEN_SIDE ->
## PUTT -> FLYOVER. The tracer cut happens on `strike` only.

class_name MasDirector

enum Beat { IDLE, ADDRESS, SWING, TRACER, LANDING, GREEN_SIDE, PUTT, FLYOVER }

var beat: Beat = Beat.IDLE
var current_hole := 0
var current_round := 0

@onready var bus: MasBusClient = $"../BusClient"


func _ready() -> void:
	bus.event_received.connect(_on_bus_event)


func _on_bus_event(event_name: String, data: Dictionary, hole: int, round_no: int) -> void:
	current_hole = hole
	current_round = round_no
	match event_name:
		"hole_start":
			_set_beat(Beat.ADDRESS)
			# TODO: place camera behind the golfer at the tee; show the
			# tee sign (hole name / par / yardage) as course furniture.
		"decision":
			_set_beat(Beat.ADDRESS)
			# TODO: frame the address. data has club, target_yards,
			# aim, risk — show the club + target in the slim bar only.
		"strike":
			_set_beat(Beat.TRACER)
			# TODO: tracer cut on strike ONLY (never before). data has
			# club_speed_mph, ball_speed_mph, launch_deg, spin_rpm,
			# smash_factor, contact. Start the ball tracer here.
		"apex":
			# TODO: keep the tracer on the ball; live distance counter.
			# data has apex_ft, carry_yds, shape, curve_yds.
			pass
		"landing":
			_set_beat(Beat.LANDING)
			# TODO: follow the roll-out to a stop; realistic roll time.
			# data has total_yds, lie, dist_to_pin_ft, on_green,
			# fairway_hit, penalty.
		"putt_read":
			_set_beat(Beat.PUTT)
			# TODO: green-side frame; show the measured break + live
			# make %, NOT a drawn line. data has the predicted path.
		"putt_result":
			# TODO: hold the frame on the ball until it stops or drops.
			pass
		"hole_complete":
			_set_beat(Beat.FLYOVER)
			# TODO: drone-banked flyover to the next tee.
		"round_complete":
			_set_beat(Beat.IDLE)
		"fifty_nine_watch":
			# TODO: pulse the gold 59 Watch bug; do not cut the camera.
			pass
		"round_state":
			# Snapshot on connect: place the camera at the current
			# hole's tee before live events arrive.
			_set_beat(Beat.ADDRESS)
		_:
			pass


func _set_beat(next: Beat) -> void:
	if next == beat:
		return
	# No cuts mid-swing / mid-flight / mid-putt: the beat only changes
	# on a bus event, and the bus never emits one mid-swing.
	beat = next
	print("director: beat -> ", Beat.keys()[beat], " hole ", current_hole)
