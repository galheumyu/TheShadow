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

## Shadow detected by the vision process; particles gather on its outline.
var shadow_mask: Texture2D:
	set(value):
		shadow_mask = value
		if is_node_ready():
			_apply_shadow_mask()

@onready var particles: GPUParticles3D = $GPUParticles3D

var _process_material: ShaderMaterial
var _draw_material: ShaderMaterial

const COLOR_COLD := Color(0.35, 0.65, 1.0, 1.0)
const COLOR_WARM := Color(1.0, 0.82, 0.35, 1.0)


func _ready() -> void:
	_process_material = particles.process_material as ShaderMaterial
	_draw_material = particles.material_override as ShaderMaterial
	particles.emitting = true
	_apply_shared_uniforms()
	_apply_shadow_mask()
	set_match_score(0.0)
	_update_visibility_aabb()


func set_match_score(score: float) -> void:
	# Match score only drives color — not motion / forces.
	var tint := COLOR_COLD.lerp(COLOR_WARM, clampf(score, 0.0, 1.0))
	var tint_v := Vector3(tint.r, tint.g, tint.b)
	if _process_material:
		_process_material.set_shader_parameter("particle_tint", tint_v)
	if _draw_material:
		_draw_material.set_shader_parameter("particle_tint", tint_v)


func set_hole_mask(texture: Texture2D) -> void:
	hole_mask = texture


func set_shadow_mask(texture: Texture2D) -> void:
	shadow_mask = texture


func _apply_shadow_mask() -> void:
	# Only the motion shader reads it; the draw pass just renders the particles.
	if _process_material:
		_process_material.set_shader_parameter("shadow_mask", shadow_mask)


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
