extends Node
## Add beside the teammate's 2D particles, assign both paths in Inspector.
@export var receiver_path: NodePath
@export var particles_path: NodePath
@export var far_color := Color(0.25, 0.4, 1.0)
@export var near_color := Color(1.0, 0.35, 0.2)
var _particles: CanvasItem

func _ready() -> void:
	# Assign these paths in the Inspector to reuse the teammate's particles.
	var receiver := get_node(receiver_path) as HandDistanceReceiver
	_particles = get_node(particles_path) as CanvasItem
	if receiver == null or _particles == null:
		push_error("Assign receiver and 2D particles paths on the color adapter")
		return
	receiver.distance_updated.connect(_on_distance_updated)

func _on_distance_updated(value: float, _valid: bool, _distance: float) -> void:
	# Tint the existing particles without changing positions or shape generation.
	# modulate multiplies their original color, so white particles tint best.
	_particles.modulate = far_color.lerp(near_color, value)
