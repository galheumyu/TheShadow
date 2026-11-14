extends Node3D

enum GameState { INTRO, PLAYING, ROUND_SUCCESS, ROUND_FAILED, COMPLETE }

const SHAPES := ["CIRCLE", "TRIANGLE", "SQUARE"]
const ROUND_DURATION := 25.0
const MATCH_HOLD_DURATION := 2.0
const SUCCESS_PAUSE := 1.5
const MASK_SIZE := 256
const WALL_ASPECT_RATIO := 12.0 / 7.0

@export_category("Shape Matching")
## Optional image-mask rounds appended after the built-in rounds. Use an opaque 12:7 image with the shape in black and the background in white.
@export var image_mask_rounds: Array[Texture2D] = []

@onready var _field: ParticleField = $ParticleField
@onready var _hand_receiver = $HandDistanceReceiver

# 开启：用双手距离控制颜色；关闭：恢复原来的匹配进度颜色。
# Enable: Use the distance between your hands to control the color; Disable: Restore the original color used for the matching progress.
@export var use_hand_color: bool = true
var _state: GameState = GameState.INTRO
var _shape_index := 0
var _time_remaining := ROUND_DURATION
var _match_elapsed := 0.0
var _transition_elapsed := 0.0
var _match_held := false
var _valid_image_masks: Array[Texture2D] = []

var _header_label: Label
var _timer_label: Label
var _message_label: Label
var _progress_bar: ProgressBar
var _prompt_label: Label


func _ready() -> void:
	_collect_image_masks()
	_build_hud()
	_apply_target_shape()
	_update_hud()


func _process(delta: float) -> void:
	if use_hand_color:
		_update_particle_color(0.0)
	if _state == GameState.PLAYING:
		_time_remaining = maxf(_time_remaining - delta, 0.0)
		if _match_held:
			_match_elapsed += delta
			_update_particle_color(_match_elapsed / MATCH_HOLD_DURATION)
			if _match_elapsed >= MATCH_HOLD_DURATION:
				_finish_round(true)
		else:
			_match_elapsed = 0.0
			_update_particle_color(0.0)

		if _state == GameState.PLAYING and _time_remaining <= 0.0:
			_finish_round(false)
	elif _state == GameState.ROUND_SUCCESS:
		_transition_elapsed += delta
		if _transition_elapsed >= SUCCESS_PAUSE:
			if _shape_index == _round_count() - 1:
				_state = GameState.COMPLETE
			else:
				_shape_index += 1
				_start_round()

	_update_hud()


func _unhandled_input(event: InputEvent) -> void:
	if event is not InputEventKey:
		return

	if event.keycode == KEY_SPACE:
		if event.pressed and not event.echo and _state == GameState.PLAYING:
			_match_held = true
		elif not event.pressed:
			_match_held = false
		return

	if not event.pressed or event.echo:
		return

	match event.keycode:
		KEY_ENTER, KEY_KP_ENTER:
			match _state:
				GameState.INTRO:
					_start_round()
				GameState.ROUND_FAILED:
					_start_round()
				GameState.COMPLETE:
					_start_game()
		KEY_R:
			_start_game()


func _start_game() -> void:
	_shape_index = 0
	_start_round()


func _start_round() -> void:
	_state = GameState.PLAYING
	_time_remaining = ROUND_DURATION
	_match_elapsed = 0.0
	_transition_elapsed = 0.0
	_match_held = false
	_update_particle_color(0.0)
	_apply_target_shape()


func _finish_round(success: bool) -> void:
	_match_held = false
	_transition_elapsed = 0.0
	if success:
		_state = GameState.ROUND_SUCCESS
		_update_particle_color(1.0)
	else:
		_state = GameState.ROUND_FAILED
		_match_elapsed = 0.0
		_update_particle_color(0.0)


func _apply_target_shape() -> void:
	if _shape_index < SHAPES.size():
		_field.set_hole_mask(_create_hole_mask(SHAPES[_shape_index]))
	else:
		_field.set_hole_mask(_valid_image_masks[_shape_index - SHAPES.size()])


func _collect_image_masks() -> void:
	for index in range(image_mask_rounds.size()):
		var mask := image_mask_rounds[index]
		if mask == null:
			push_error("Image-mask round %d has no texture assigned." % (index + 1))
			continue
		_valid_image_masks.append(mask)


func _round_count() -> int:
	return SHAPES.size() + _valid_image_masks.size()


func _round_name(index: int) -> String:
	if index < SHAPES.size():
		return SHAPES[index]

	var mask := _valid_image_masks[index - SHAPES.size()]
	var mask_name := mask.resource_name
	if mask_name.is_empty():
		mask_name = mask.resource_path.get_file().get_basename()
	if mask_name.is_empty():
		mask_name = "IMAGE %d" % (index - SHAPES.size() + 1)
	return mask_name.replace("_", " ").to_upper()


func _create_hole_mask(shape_name: String) -> Texture2D:
	var image := Image.create(MASK_SIZE, MASK_SIZE, false, Image.FORMAT_RGBA8)
	for pixel_y in range(MASK_SIZE):
		for pixel_x in range(MASK_SIZE):
			var covered_samples := 0
			for sample_y in range(2):
				for sample_x in range(2):
					var x := ((pixel_x + (float(sample_x) + 0.5) * 0.5) / MASK_SIZE) * 2.0 - 1.0
					var y := ((pixel_y + (float(sample_y) + 0.5) * 0.5) / MASK_SIZE) * 2.0 - 1.0
					if _point_is_inside_shape(shape_name, x, y):
						covered_samples += 1

			var outside_value := 1.0 - float(covered_samples) / 4.0
			image.set_pixel(pixel_x, pixel_y, Color(outside_value, outside_value, outside_value, 1.0))

	return ImageTexture.create_from_image(image)


func _point_is_inside_shape(shape_name: String, x: float, y: float) -> bool:
	var shape_x := x * WALL_ASPECT_RATIO
	match shape_name:
		"CIRCLE":
			return Vector2(shape_x, y).length_squared() <= 0.34 * 0.34
		"TRIANGLE":
			return y >= -0.34 and y <= 0.34 and absf(shape_x) <= (y + 0.34) * 0.5
		"SQUARE":
			return absf(shape_x) <= 0.31 and absf(y) <= 0.31
	return false


func _build_hud() -> void:
	var canvas := CanvasLayer.new()
	canvas.layer = 10
	add_child(canvas)

	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.add_child(root)

	_header_label = _make_label(root, Control.PRESET_TOP_WIDE, 24.0, 76.0, 30)
	_header_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

	_timer_label = _make_label(root, Control.PRESET_TOP_WIDE, 80.0, 116.0, 24)
	_timer_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

	_message_label = _make_label(root, Control.PRESET_BOTTOM_WIDE, -174.0, -120.0, 28)
	_message_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_message_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_message_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	_progress_bar = ProgressBar.new()
	_progress_bar.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	_progress_bar.offset_left = 280.0
	_progress_bar.offset_top = -106.0
	_progress_bar.offset_right = -280.0
	_progress_bar.offset_bottom = -82.0
	_progress_bar.min_value = 0.0
	_progress_bar.max_value = MATCH_HOLD_DURATION
	_progress_bar.show_percentage = false
	_progress_bar.modulate = Color(1.0, 0.82, 0.35, 1.0)
	root.add_child(_progress_bar)

	_prompt_label = _make_label(root, Control.PRESET_BOTTOM_WIDE, -70.0, -20.0, 18)
	_prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_prompt_label.add_theme_color_override("font_color", Color(0.78, 0.86, 1.0))


func _make_label(parent: Control, preset: Control.LayoutPreset, top: float, bottom: float, font_size: int) -> Label:
	var label := Label.new()
	label.set_anchors_and_offsets_preset(preset)
	label.offset_top = top
	label.offset_bottom = bottom
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0))
	label.add_theme_color_override("font_shadow_color", Color(0.0, 0.0, 0.0, 0.9))
	label.add_theme_constant_override("shadow_offset_x", 2)
	label.add_theme_constant_override("shadow_offset_y", 2)
	parent.add_child(label)
	return label


func _update_hud() -> void:
	_header_label.text = "SHAPE MATCH  |  ROUND %d/%d  |  TARGET: %s" % [
		_shape_index + 1,
		_round_count(),
		_round_name(_shape_index),
	]
	_timer_label.text = "TIME  %02d" % ceili(_time_remaining)
	_progress_bar.value = minf(_match_elapsed, MATCH_HOLD_DURATION)

	match _state:
		GameState.INTRO:
			_message_label.text = "Match your shadow to the glowing shape"
			_prompt_label.text = "Press ENTER to begin  |  Prototype: hold SPACE to simulate a match"
			_timer_label.text = ""
		GameState.PLAYING:
			_message_label.text = "Hold your shadow in the shape" if _match_held else "Move your shadow into the shape"
			_prompt_label.text = "Hold SPACE to simulate a shadow match  |  R restart"
		GameState.ROUND_SUCCESS:
			_message_label.text = "Shape matched!"
			_prompt_label.text = "Next shape..."
			_progress_bar.value = MATCH_HOLD_DURATION
		GameState.ROUND_FAILED:
			_message_label.text = "Time's up - try that shape again"
			_prompt_label.text = "Press ENTER to retry  |  R restart"
			_timer_label.text = ""
		GameState.COMPLETE:
			_message_label.text = "All shapes matched!"
			_prompt_label.text = "Press ENTER to play again"
			_timer_label.text = ""

func _update_particle_color(match_score: float) -> void:
	if use_hand_color:
		_field.set_match_score(_hand_receiver.proximity)
	else:
		_field.set_match_score(match_score)
