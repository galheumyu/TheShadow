extends SceneTree
## Run headless with --path godot --script res://verify_receiver.gd
func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var receiver := HandDistanceReceiver.new()
	receiver.port = 44242
	receiver.timeout_seconds = 0.12
	root.add_child(receiver)
	var sender := PacketPeerUDP.new()
	sender.set_dest_address("127.0.0.1", receiver.port)
	sender.put_packet(JSON.stringify({"version": 1, "valid": true, "proximity": 1.0, "distance_norm": 0.12}).to_utf8_buffer())
	await create_timer(0.06).timeout
	if not receiver.valid or receiver.proximity <= 0.0 or receiver.distance_norm != 0.12:
		push_error("UDP valid data / smoothing failed")
		quit(1)
		return
	await create_timer(0.2).timeout
	if receiver.valid or receiver.distance_norm != -1.0:
		push_error("Tracker timeout failed")
		quit(1)
		return
	sender.put_packet(JSON.stringify({"version": 1, "valid": false}).to_utf8_buffer())
	await create_timer(0.04).timeout
	if receiver.valid:
		quit(1)
		return
	print("PASS: UDP reception, smoothing, tracking loss, timeout")
	sender.close()
	receiver.queue_free()
	quit(0)
