extends Node3D

## 0 = cold blue (low match), 1 = warm gold (high match). Hole shape is independent.
@export_range(0.0, 1.0, 0.001) var match_score: float = 0.0:
	set(value):
		match_score = clampf(value, 0.0, 1.0)
		if _field:
			_field.set_match_score(match_score)

@onready var _field: ParticleField = $ParticleField


func _ready() -> void:
	_field.set_match_score(match_score)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_1:
				match_score = 0.0
			KEY_2:
				match_score = 0.5
			KEY_3:
				match_score = 1.0
