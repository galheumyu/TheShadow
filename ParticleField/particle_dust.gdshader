shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, unshaded, shadows_disabled;

// XY quads + particle_flag_disable_z face the camera — same setup as the working wall.
// hole_mask only fades particles that drift into the hole so the circle stays clear.
uniform sampler2D particle_tex : source_color, filter_linear;
uniform sampler2D hole_mask : source_color, filter_linear, hint_default_white;
uniform vec2 wall_half_extents = vec2(6.0, 3.5);
uniform vec3 particle_tint = vec3(0.35, 0.65, 1.0);
uniform float emission_strength : hint_range(0.0, 8.0) = 2.2;

varying float hole_fade;

void vertex() {
	vec3 pos = MODEL_MATRIX[3].xyz;
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
	vec3 col = particle_tint * tex.rgb;
	ALBEDO = col * alpha;
	ALPHA = max(alpha, 0.001);
	EMISSION = col * emission_strength * alpha;
}
