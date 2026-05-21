extends Node2D

var _websocket := WebSocketPeer.new()
var _connected := false

@onready var state_label: Label = $ColorRect/StateLabel
@onready var rect: ColorRect = $ColorRect

func _ready() -> void:
	get_tree().get_root().set_transparent_background(true)
	
	# Make window fully click-through
	DisplayServer.window_set_mouse_passthrough(PackedVector2Array([Vector2(0,0), Vector2(0,0), Vector2(0,0)]))
	
	var err = _websocket.connect_to_url("ws://localhost:5000/avatar-ws")
	if err != OK:
		print("Failed to initiate WebSocket connection")

func _process(_delta: float) -> void:
	_websocket.poll()
	var state = _websocket.get_ready_state()
	
	if state == WebSocketPeer.STATE_OPEN:
		if not _connected:
			_connected = true
			print("WebSocket Connected to /avatar-ws!")
			
		while _websocket.get_available_packet_count() > 0:
			var packet = _websocket.get_packet().get_string_from_utf8()
			_handle_websocket_packet(packet)
			
	elif state == WebSocketPeer.STATE_CLOSED:
		_connected = false

func _handle_websocket_packet(packet: String) -> void:
	var json = JSON.new()
	if json.parse(packet) == OK:
		var data = json.data
		if data is Dictionary:
			_update_avatar(data)

func _update_avatar(payload: Dictionary) -> void:
	var avatar_state = payload.get("state", "idle")
	var focus_window = payload.get("focus_window", "")
	state_label.text = avatar_state
	
	match avatar_state:
		"idle":
			rect.color = Color(0.5, 0.5, 0.5, 0.8)
			# pacing, resting, ambient movement
		"working":
			rect.color = Color(0.2, 0.6, 1.0, 0.8)
			# typing, focused activity
		"thinking":
			rect.color = Color(0.8, 0.8, 0.2, 0.8)
			# meditating, slow movement
		"alert":
			rect.color = Color(1.0, 0.2, 0.2, 0.8)
			# startled snap, look around
		"speaking":
			rect.color = Color(0.2, 0.8, 0.2, 0.8)
			# mouth animation, active gesture
			
	if focus_window != "":
		# Stub: move towards the active window
		print("Focus shifted to: ", focus_window)
