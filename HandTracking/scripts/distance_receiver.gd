class_name HandDistanceReceiver
extends Node
## Connect this signal to a particle system without changing its shape logic.
## proximity: 0 = far, 1 = near; distance_norm: distance / image width.
signal distance_updated(proximity: float, valid: bool, distance_norm: float)

@export var port: int = 4242
@export var timeout_seconds: float = 0.5
@export var smoothing_speed: float = 8.0
var proximity: float = 0.0
var valid: bool = false
var distance_norm: float = -1.0
var _target: float = 0.0
var _last_packet_ms: int = -1
var _udp := PacketPeerUDP.new()

func _ready() -> void:
	# Listen only on this computer. Python sends JSON packets to this port.
	var error := _udp.bind(port, "127.0.0.1")
	if error != OK:
		push_error("Cannot bind UDP port %d: %s" % [port, error_string(error)])
		set_process(false)

func _process(delta: float) -> void:
	# Drain queued packets so the latest measurement becomes the target.
	while _udp.get_available_packet_count() > 0:
		var data = JSON.parse_string(_udp.get_packet().get_string_from_utf8())
		# JSON parsing returns null if the packet is not valid JSON.
		if not data is Dictionary:
			continue
		# The local Python sender defines the fields and their types.
		var incoming_valid: bool = data["valid"]
		if incoming_valid:
			_target = data["proximity"]
			distance_norm = data["distance_norm"]
		else:
			# Missing hands are invalid measurements, not zero distance.
			_target = 0.0
			distance_norm = -1.0
		valid = incoming_valid
		_last_packet_ms = Time.get_ticks_msec()
	# Also reset if Python stops without sending a final packet.
	if _last_packet_ms < 0 or Time.get_ticks_msec() - _last_packet_ms > timeout_seconds * 1000.0:
		valid = false
		_target = 0.0
		distance_norm = -1.0
	# Frame-rate-independent smoothing prevents abrupt color changes.
	proximity = lerpf(proximity, _target, 1.0 - exp(-smoothing_speed * delta))
	# Consumers receive the smoothed value every frame, even between packets.
	distance_updated.emit(proximity, valid, distance_norm)

func _exit_tree() -> void:
	# Release the port when this node leaves the scene.
	_udp.close()
