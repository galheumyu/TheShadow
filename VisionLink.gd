extends Node
class_name VisionLink

## UDP link to the Python vision process (see vision/).
## Sends the target shape, receives the score and the detected shadow shape.

## Where vision listens for set_target (config.py: listen_addr).
@export var vision_host := "127.0.0.1"
@export var vision_port := 9001
## Where vision sends results (config.py: godot_addr).
@export var listen_port := 9002
## Size of the target mask sent to vision: keep the work_size aspect, small enough
## to stay in one datagram.
@export var mask_size := Vector2i(320, 180)
## Draw the detected shadow over the screen (debug). The particle wall already
## shows the shadow outline, so this is off by default.
@export var show_overlay := false

signal score_received(iou: float, matched: bool)

var iou := 0.0
var matched := false
var valid := false
var shadow_texture: Texture2D

var _socket := PacketPeerUDP.new()
var _target_id := 0
var _target_packet := PackedByteArray()
var _acked := true
var _resend_in := 0.0
var _overlay: TextureRect
var _label: Label


func _ready() -> void:
	var err := _socket.bind(listen_port)
	if err != OK:
		push_error("VisionLink: cannot listen on port %d" % listen_port)
	if show_overlay:
		_build_overlay()


func _process(delta: float) -> void:
	_receive()
	_resend(delta)
	if show_overlay:
		_update_overlay()


## Send the current target shape. Call it at the start of every round.
func set_target(mask: Texture2D, id: int) -> void:
	var source := mask.get_image()
	if source == null:
		return
	var image := source.duplicate() as Image
	# The wall fills the screen: stretching the square wall texture to the screen
	# aspect gives the shape as the camera sees it.
	image.resize(mask_size.x, mask_size.y, Image.INTERPOLATE_BILINEAR)
	_target_id = id
	_target_packet = JSON.stringify({
		"type": "set_target",
		"target_id": id,
		"w": image.get_width(),
		"h": image.get_height(),
		"mask_png_b64": Marshalls.raw_to_base64(image.save_png_to_buffer()),
	}).to_utf8_buffer()
	_acked = false
	_resend_in = 0.0


func _receive() -> void:
	while _socket.get_available_packet_count() > 0:
		var msg = JSON.parse_string(_socket.get_packet().get_string_from_utf8())
		if typeof(msg) != TYPE_DICTIONARY:
			continue
		if msg.get("type") == "target_ack":
			if int(msg.get("target_id", -1)) == _target_id:
				_acked = true
		elif msg.get("type") == "match":
			_apply_match(msg)


func _apply_match(msg: Dictionary) -> void:
	valid = bool(msg.get("valid", false))
	matched = valid and bool(msg.get("matched", false))
	iou = float(msg.get("iou", 0.0))
	score_received.emit(iou, matched)

	var b64: String = msg.get("shadow_png_b64", "")
	if b64.is_empty():
		return
	var image := Image.new()
	if image.load_png_from_buffer(Marshalls.base64_to_raw(b64)) != OK:
		return
	var texture := shadow_texture as ImageTexture
	if texture != null and texture.get_width() == image.get_width() \
			and texture.get_height() == image.get_height():
		texture.update(image)
	else:
		shadow_texture = ImageTexture.create_from_image(image)


func _resend(delta: float) -> void:
	if _acked or _target_packet.is_empty():
		return
	_resend_in -= delta
	if _resend_in <= 0.0:
		_resend_in = 1.0     # UDP drops packets: repeat until vision acknowledges
		_socket.set_dest_address(vision_host, vision_port)
		_socket.put_packet(_target_packet)


func _build_overlay() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 5
	add_child(layer)

	_overlay = TextureRect.new()
	_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_overlay.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_overlay.stretch_mode = TextureRect.STRETCH_SCALE
	_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_overlay.modulate = Color(1.0, 1.0, 1.0)
	layer.add_child(_overlay)

	_label = Label.new()
	_label.position = Vector2(24, 120)
	_label.add_theme_font_size_override("font_size", 18)
	_label.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0))
	_label.add_theme_color_override("font_shadow_color", Color(0.0, 0.0, 0.0, 0.9))
	layer.add_child(_label)


func _update_overlay() -> void:
	_overlay.texture = shadow_texture
	var state := "-" if valid else "no signal"
	_label.text = "vision  iou %.2f  %s" % [iou, "MATCHED" if matched else state]
