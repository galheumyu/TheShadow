extends Node2D

var receiver: HandDistanceReceiver
var particles: CPUParticles2D
var status: Label
var meter: ProgressBar
var far_color := Color(0.25, 0.4, 1.0)
var near_color := Color(1.0, 0.35, 0.2)

func _ready() -> void:
	# Keep input reception separate from the demonstration visuals.
	receiver = HandDistanceReceiver.new()
	receiver.name = "HandDistance"
	add_child(receiver)
	# A simple rectangular particle field demonstrates the distance input.
	# The teammate's shape system can replace this field later.
	particles = CPUParticles2D.new()
	particles.position = Vector2(500, 355)
	particles.amount = 650
	particles.lifetime = 3.0
	particles.preprocess = 3.0
	particles.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
	particles.emission_rect_extents = Vector2(420, 170)
	particles.direction = Vector2(0, -1)
	particles.spread = 35.0
	particles.gravity = Vector2.ZERO
	particles.initial_velocity_min = 8.0
	particles.initial_velocity_max = 24.0
	particles.scale_amount_min = 2.0
	particles.scale_amount_max = 4.0
	# Fade particles in and out over their lifetime; RGB stays white for tinting.
	var gradient := Gradient.new()
	gradient.set_color(0, Color(1, 1, 1, 0))
	gradient.add_point(0.15, Color.WHITE)
	gradient.add_point(0.8, Color.WHITE)
	gradient.set_color(gradient.get_point_count() - 1, Color(1, 1, 1, 0))
	particles.color_ramp = gradient
	add_child(particles)
	# Show connection status and proximity to make testing easier.
	var title := Label.new()
	title.text = "TWO HANDS / DISTANCE TO COLOR"
	title.position = Vector2(45, 30)
	title.add_theme_font_size_override("font_size", 28)
	add_child(title)
	status = Label.new()
	status.position = Vector2(45, 85)
	add_child(status)
	meter = ProgressBar.new()
	meter.position = Vector2(45, 560)
	meter.size = Vector2(910, 24)
	meter.show_percentage = false
	add_child(meter)
	var hint := Label.new()
	hint.text = "Far = blue   |   Near = orange   |   Run Python tracker or --simulate"
	hint.position = Vector2(45, 605)
	add_child(hint)
	receiver.distance_updated.connect(_on_distance_updated)

func _on_distance_updated(value: float, tracking: bool, distance: float) -> void:
	# Interpolate between the endpoint colors using the smoothed proximity.
	particles.modulate = far_color.lerp(near_color, value)
	meter.value = value * 100.0
	status.text = ("Tracking two hands | distance %.3f | proximity %.2f" % [distance, value]) if tracking else "Waiting for two hands / tracker disconnected"
