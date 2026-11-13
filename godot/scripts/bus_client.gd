extends Node
## Bus client — connects the Godot renderer to the sim event bus.
##
## SCAFFOLD: written without running Godot. The wire format is real
## (mirrors bus/translate.py); the handlers are stubs until the scene
## exists. Connects to ws://localhost:4456, the bus port from
## docs/mac-native-broadcast.md. The sim is authoritative; this node
## only receives and dispatches — it never sends game state.
##
## Envelope (from bus/translate.py _base_envelope):
##   {"event": <str>, "seq": <int>, "ts": <iso str>,
##    "round": <int>, "hole": <int>, "data": {...}}
## Wire events: decision, strike, apex, landing, putt_read,
## putt_result, hole_start, round_start, hole_complete,
## round_complete, fifty_nine_watch, milestone.
## shot_result fans out to strike/apex/landing on the bus.
## The bus also sends a "round_state" snapshot on connect.

class_name MasBusClient

signal event_received(event_name: String, data: Dictionary, hole: int, round_no: int)
signal connected
signal disconnected

const BUS_URL := "ws://localhost:4456"
const RECONNECT_DELAY_SEC := 2.0

var _socket := WebSocketPeer.new()
var _reconnect_timer := 0.0
var _want_connection := false


func _ready() -> void:
	_want_connection = true
	_connect()


func _process(delta: float) -> void:
	_socket.poll()
	var state := _socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		while _socket.get_available_packet_count() > 0:
			_handle_packet(_socket.get_packet())
	elif state == WebSocketPeer.STATE_CLOSED:
		if _want_connection:
			_reconnect_timer += delta
			if _reconnect_timer >= RECONNECT_DELAY_SEC:
				_reconnect_timer = 0.0
				_connect()


func _connect() -> void:
	var err := _socket.connect_to_url(BUS_URL)
	if err != OK:
		push_warning("bus: connect to %s failed: %s" % [BUS_URL, err])
	else:
		print("bus: connecting to ", BUS_URL)


func _handle_packet(packet: PackedByteArray) -> void:
	var text := packet.get_string_from_utf8()
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_warning("bus: non-dict packet: " + text.left(200))
		return
	var event_name := String(parsed.get("event", ""))
	var data: Dictionary = parsed.get("data", {})
	var hole := int(parsed.get("hole", 0))
	var round_no := int(parsed.get("round", 0))
	if event_name == "round_state":
		# Snapshot the bus sends every connection (see bus/client.py):
		# current round/hole/score state. The director consumes it to
		# place the camera before the first live event arrives.
		print("bus: round_state snapshot received")
		event_received.emit(event_name, data, hole, round_no)
		return
	if event_name == "":
		push_warning("bus: envelope with no event field")
		return
	# TODO (slice build): route to the director instead of just emitting.
	event_received.emit(event_name, data, hole, round_no)


func disconnect_bus() -> void:
	_want_connection = false
	_socket.close()
	disconnected.emit()
