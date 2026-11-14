extends Node3D
class_name ParticleField

## Half-size of the wall in local X/Y.
@export var wall_half_extents: Vector2 = Vector2(6.0, 3.5):
	set(value):
		wall_half_extents = value
		if is_node_ready():
			_apply_shared_uniforms()

@export var hole_mask: Texture2D:
	set(value):
		hole_mask = value
		if is_node_ready():
			_apply_shared_uniforms()

@onready var particles: GPUParticles3D = $GPUParticles3D

var _process_material: ShaderMaterial
var _draw_material: ShaderMaterial

## Lower saturation produces softer colors instead of vivid neon hues.
@export_range(0.0, 1.0) var color_saturation: float = 0.5
## Larger spread makes neighboring patches change at more different distances.
@export_range(0.0, 0.8) var color_spread: float = 0.45
## Smaller values make color changes slower; units are inverse seconds.
@export_range(0.1, 10.0) var color_response_speed: float = 2.0
var _color_target: float = 0.0
var _color_progress: float = 0.0



func _ready() -> void:
	_process_material = particles.process_material as ShaderMaterial
	_draw_material = particles.material_override as ShaderMaterial
	particles.emitting = true
	_apply_shared_uniforms()
	set_match_score(0.0)
	_update_visibility_aabb()


# Receive a target only; smooth it once per frame, independent of call count.
func set_match_score(score: float) -> void:
	_color_target = clampf(score, 0.0, 1.0)


func _process(delta: float) -> void:
	# A slower response prevents camera noise from rapidly sweeping the hue wheel.
	_color_progress = lerpf(_color_progress, _color_target, 1.0 - exp(-color_response_speed * delta))
	if _draw_material:
		_draw_material.set_shader_parameter("color_progress", _color_progress)
		_draw_material.set_shader_parameter("color_saturation", color_saturation)
		_draw_material.set_shader_parameter("color_spread", color_spread)


func set_hole_mask(texture: Texture2D) -> void:
	hole_mask = texture


func _apply_shared_uniforms() -> void:
	if _process_material:
		_process_material.set_shader_parameter("wall_half_extents", wall_half_extents)
		if hole_mask:
			_process_material.set_shader_parameter("hole_mask", hole_mask)
	if _draw_material:
		_draw_material.set_shader_parameter("wall_half_extents", wall_half_extents)
		if hole_mask:
			_draw_material.set_shader_parameter("hole_mask", hole_mask)
	_update_visibility_aabb()


func _update_visibility_aabb() -> void:
	if particles == null:
		return
	particles.visibility_aabb = AABB(
		Vector3(-wall_half_extents.x - 1.0, -wall_half_extents.y - 1.0, -1.0),
		Vector3(wall_half_extents.x * 2.0 + 2.0, wall_half_extents.y * 2.0 + 2.0, 2.0)
	)
