shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, unshaded, shadows_disabled;

// XY quads + particle_flag_disable_z face the camera — same setup as the working wall.
// hole_mask only fades particles that drift into the hole so the circle stays clear.
uniform sampler2D particle_tex : source_color, filter_linear;
uniform sampler2D hole_mask : source_color, filter_linear, hint_default_white;
uniform vec2 wall_half_extents = vec2(6.0, 3.5);
// Distance drives staggered per-particle colors instead of one shared tint.
uniform float color_progress : hint_range(0.0, 1.0) = 0.0;
uniform float color_saturation : hint_range(0.0, 1.0) = 0.5;
uniform float color_spread : hint_range(0.0, 0.8) = 0.45;
uniform float emission_strength : hint_range(0.0, 8.0) = 2.2;

varying float hole_fade;
varying vec3 local_particle_color;

vec3 hue_to_rgb(float hue) {
	vec3 channels = abs(fract(vec3(hue) + vec3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
	return mix(vec3(1.0), clamp(channels - 1.0, 0.0, 1.0), color_saturation);
}

void vertex() {
	vec3 pos = MODEL_MATRIX[3].xyz;
	// Use a fixed per-particle offset, even while particles move or respawn.
	// Steady distance settles to steady colors instead of continuous hue cycling.
	float patch = INSTANCE_CUSTOM.y;
	float begin = patch * color_spread;
	float finish = 1.0 - (1.0 - patch) * color_spread;
	// All patches are blue at zero and red at one, but transition at different times.
	float local_progress = smoothstep(begin, finish, color_progress);
	// Keep the full hue sweep: one complete turn, then continue from blue to red.
	float hue = fract(mix(2.0 / 3.0, -1.0, local_progress));
	local_particle_color = hue_to_rgb(hue);
	vec2 mask_uv = pos.xy / wall_half_extents * 0.5 + vec2(0.5);
	float mask = 0.0;
	if (mask_uv.x >= 0.0 && mask_uv.x <= 1.0 && mask_uv.y >= 0.0 && mask_uv.y <= 1.0) {
		mask = texture(hole_mask, mask_uv).r;
	}
	// Align with hole_keep_threshold (0.55) for a crisp isocontour read.
	hole_fade = smoothstep(0.45, 0.62, mask);
}

void fragment() {
	vec4 tex = texture(particle_tex, UV);
	float alpha = tex.a * hole_fade;
	vec3 col = local_particle_color * tex.rgb;
	ALBEDO = col * alpha;
	ALPHA = max(alpha, 0.001);
	EMISSION = col * emission_strength * alpha;
}
