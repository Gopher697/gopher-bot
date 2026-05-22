extends Node2D

var _websocket := WebSocketPeer.new()
var _connected := false

# Dynamic sprite for hot-swappable textures (created at runtime, T73)
var _sprite: Sprite2D = null

@onready var state_label: Label = $ColorRect/StateLabel
@onready var rect: ColorRect = $ColorRect

func _ready() -> void:
	get_tree().get_root().set_transparent_background(true)

	# Make window fully click-through
	DisplayServer.window_set_mouse_passthrough(PackedVector2Array([Vector2(0,0), Vector2(0,0), Vector2(0,0)]))

	# Create the sprite node for texture-swappable avatar art.
	# Sits above the ColorRect status indicator; hidden until a texture is installed.
	_sprite = Sprite2D.new()
	_sprite.position = Vector2(64, 64)   # centred in the default 128x128 window
	_sprite.visible = false
	add_child(_sprite)

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
			var msg_type = data.get("type", "")
			if msg_type == "swap_texture":
				_swap_texture(data.get("path", ""))
			else:
				_update_avatar(data)

func _swap_texture(abs_path: String) -> void:
	# Load an image from an absolute filesystem path and apply it to the sprite.
	# Godot 4 loads images from the local filesystem via Image.load() at runtime.
	if abs_path == "":
		print("swap_texture: empty path, ignoring")
		return

	var img = Image.new()
	var err = img.load(abs_path)
	if err != OK:
		print("swap_texture: failed to load image from ", abs_path, " (err ", err, ")")
		return

	var tex = ImageTexture.create_from_image(img)
	_sprite.texture = tex
	_sprite.visible = true

	# Hide the placeholder ColorRect once a real texture is loaded.
	rect.visible = false
	state_label.visible = false

	print("swap_texture: loaded ", abs_path.get_file())

func _update_avatar(payload: Dictionary) -> void:
	var avatar_state = payload.get("state", "idle")
	var focus_window = payload.get("focus_window", "")

	# Only drive the label/rect fallback when no texture is installed yet.
	if not _sprite.visible:
		state_label.text = avatar_state
		match avatar_state:
			"idle":
				rect.color = Color(0.5, 0.5, 0.5, 0.8)
			"working":
				rect.color = Color(0.2, 0.6, 1.0, 0.8)
			"thinking":
				rect.color = Color(0.8, 0.8, 0.2, 0.8)
			"alert":
				rect.color = Color(1.0, 0.2, 0.2, 0.8)
			"speaking":
				rect.color = Color(0.2, 0.8, 0.2, 0.8)

	if focus_window != "":
		print("Focus shifted to: ", focus_window)
