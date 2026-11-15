shader_type particles;

// Priority: early-algorithm isocontour lock (strong fa, slow fv) for a compass-round hole.
// Secondary: far-field multi-octave curl (div≈0) for gentler density — never near the rim.
// match_score is color-only via particle_tint.

uniform sampler2D hole_mask : filter_linear, repeat_disable;
// Shadow from the vision process (alpha = shadow). Empty until the first frame arrives.
uniform sampler2D shadow_mask : filter_linear, repeat_disable, hint_default_transparent;
uniform float shadow_pull_strength : hint_range(0.0, 40.0) = 14.0;
uniform vec2 wall_half_extents = vec2(6.0, 3.5);
uniform vec3 particle_tint = vec3(0.35, 0.65, 1.0);

uniform float base_speed_min : hint_range(0.0, 2.0) = 0.12;
uniform float base_speed_max : hint_range(0.0, 2.0) = 0.35;
uniform float turb_strength : hint_range(0.0, 5.0) = 0.42;
uniform float turb_scale : hint_range(0.1, 8.0) = 1.35;
uniform float turb_time_scale : hint_range(0.0, 2.0) = 0.2;
uniform float flow_blend : hint_range(0.0, 10.0) = 1.2;

// Early-style radial lock + slow tangential.
uniform float fa_strength : hint_range(0.0, 20.0) = 6.0;
uniform float fv_strength : hint_range(0.0, 20.0) = 1.0;
uniform float tangent_speed : hint_range(0.0, 5.0) = 0.28;
uniform float hole_push_strength : hint_range(0.0, 30.0) = 10.0;
uniform float hole_keep_threshold : hint_range(0.0, 1.0) = 0.55;
uniform float hole_project_strength : hint_range(0.0, 4.0) = 1.05;
uniform float grad_weight_start : hint_range(0.0, 20.0) = 0.6;
uniform float grad_weight_end : hint_range(0.0, 40.0) = 5.5;
uniform float damping : hint_range(0.0, 5.0) = 0.3;
uniform float max_speed : hint_range(0.1, 5.0) = 0.85;
uniform float scale_min : hint_range(0.05, 2.0) = 0.4;
uniform float scale_max : hint_range(0.05, 2.0) = 1.0;

float next_rand(inout uint seed) {
	seed = seed * 1103515245u + 12345u;
	return float(seed >> 16u) / 65535.0;
}

float mask_at(vec2 uv) {
	if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
		return 0.0;
	}
	return texture(hole_mask, uv).r;
}

vec2 world_to_uv(vec2 pos) {
	return pos / wall_half_extents * 0.5 + vec2(0.5);
}

float shadow_at(vec2 uv) {
	if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
		return 0.0;
	}
	return texture(shadow_mask, uv).a;
}

vec2 shadow_gradient(vec2 uv) {
	ivec2 sz = textureSize(shadow_mask, 0);
	vec2 texel = 1.0 / max(vec2(sz), vec2(1.0));
	float dx = shadow_at(uv + vec2(texel.x, 0.0)) - shadow_at(uv - vec2(texel.x, 0.0));
	float dy = shadow_at(uv + vec2(0.0, texel.y)) - shadow_at(uv - vec2(0.0, texel.y));
	return vec2(dx, dy) / (2.0 * texel);
}

vec2 mask_gradient(vec2 uv) {
	ivec2 sz = textureSize(hole_mask, 0);
	vec2 texel = 1.0 / max(vec2(sz), vec2(1.0));
	float dx = mask_at(uv + vec2(texel.x, 0.0)) - mask_at(uv - vec2(texel.x, 0.0));
	float dy = mask_at(uv + vec2(0.0, texel.y)) - mask_at(uv - vec2(0.0, texel.y));
	return vec2(dx, dy) / (2.0 * texel);
}

float stream_psi(vec2 p, float t, float s) {
	float a = sin(p.x * s * 0.7 + t * 0.85) * cos(p.y * s * 0.65 - t * 0.65);
	float b = 0.5 * sin(p.x * s * 1.35 - t * 0.95) * cos(p.y * s * 1.25 + t * 0.5);
	float c = 0.25 * sin(p.x * s * 2.1 + t * 0.4) * cos(p.y * s * 1.9 - t * 0.7);
	return a + b + c;
}

vec2 curl_flow(vec2 p, float t) {
	// Multi-scale curl: broad mixing (large s) + gentle detail — fewer sharp filaments.
	float e = 0.1;
	float s0 = turb_scale * 0.55;
	float s1 = turb_scale;
	float ddx = (
		(stream_psi(p + vec2(e, 0.0), t, s0) - stream_psi(p - vec2(e, 0.0), t, s0)) * 0.55
		+ (stream_psi(p + vec2(e, 0.0), t, s1) - stream_psi(p - vec2(e, 0.0), t, s1)) * 0.45
	) / (2.0 * e);
	float ddy = (
		(stream_psi(p + vec2(0.0, e), t, s0) - stream_psi(p - vec2(0.0, e), t, s0)) * 0.55
		+ (stream_psi(p + vec2(0.0, e), t, s1) - stream_psi(p - vec2(0.0, e), t, s1)) * 0.45
	) / (2.0 * e);
	return vec2(ddy, -ddx) * turb_strength;
}

void make_birth(
	uint seed_in,
	out vec3 out_pos,
	out vec3 out_vel,
	out float out_scale,
	out vec4 out_color
) {
	uint seed = seed_in;
	out_pos = vec3(0.0);
	bool found = false;
	for (int i = 0; i < 20; i++) {
		out_pos.x = (next_rand(seed) * 2.0 - 1.0) * wall_half_extents.x;
		out_pos.y = (next_rand(seed) * 2.0 - 1.0) * wall_half_extents.y;
		out_pos.z = 0.0;
		if (mask_at(world_to_uv(out_pos.xy)) > hole_keep_threshold) {
			found = true;
			break;
		}
	}
	if (!found) {
		float ang = next_rand(seed) * TAU;
		float rad = min(wall_half_extents.x, wall_half_extents.y) * 0.8;
		out_pos = vec3(cos(ang) * rad, sin(ang) * rad, 0.0);
	}

	float speed = mix(base_speed_min, base_speed_max, next_rand(seed));
	float ang0 = next_rand(seed) * TAU;
	out_vel = vec3(cos(ang0) * speed, sin(ang0) * speed, 0.0);
	out_scale = mix(scale_min, scale_max, next_rand(seed));
	out_color = vec4(particle_tint, 1.0);
}

void start() {
	vec3 pos;
	vec3 vel;
	float sc;
	vec4 col;
	make_birth(uint(INDEX) * 747796405u + RANDOM_SEED + 2891336453u, pos, vel, sc, col);

	VELOCITY = vel;
	CUSTOM = vec4(sc, 0.0, 0.0, 0.0);
	TRANSFORM = mat4(
		vec4(sc, 0.0, 0.0, 0.0),
		vec4(0.0, sc, 0.0, 0.0),
		vec4(0.0, 0.0, sc, 0.0),
		vec4(pos, 1.0)
	);
	COLOR = col;
}

void process() {
	if (RESTART) {
		vec3 pos;
		vec3 vel;
		float sc;
		vec4 col;
		make_birth(
			uint(INDEX) * 747796405u + RANDOM_SEED + 2891336453u + uint(TIME * 1000.0),
			pos, vel, sc, col
		);
		VELOCITY = vel;
		CUSTOM = vec4(sc, 0.0, 0.0, 0.0);
		TRANSFORM = mat4(
			vec4(sc, 0.0, 0.0, 0.0),
			vec4(0.0, sc, 0.0, 0.0),
			vec4(0.0, 0.0, sc, 0.0),
			vec4(pos, 1.0)
		);
		COLOR = col;
	} else {
		float sc = CUSTOM.x;
		vec3 pos = TRANSFORM[3].xyz;
		vec2 vel = VELOCITY.xy;

		vec2 uv = world_to_uv(pos.xy);
		float m = mask_at(uv);
		vec2 grad = mask_gradient(uv);
		float g = length(grad);
		vec2 n = g > 1e-4 ? grad / g : (length(pos.xy) > 1e-4 ? normalize(pos.xy) : vec2(1.0, 0.0));
		vec2 t = vec2(-n.y, n.x);
		float W = smoothstep(grad_weight_start, grad_weight_end, g);

		// Hard isolation: curl only in the solid wall body, never on/inside the rim.
		float far_field = smoothstep(0.62, 0.88, m);

		vec2 flow = curl_flow(pos.xy, TIME * turb_time_scale);
		float blend = 1.0 - exp(-flow_blend * DELTA);
		vel = mix(vel, flow, blend * far_field);

		// --- Early algorithm boundary lock (shape first) ---
		vec2 fa = n * fa_strength * W;
		if (m < hole_keep_threshold) {
			fa += n * hole_push_strength * (hole_keep_threshold - m);
		}

		// Slow tangential — particles sit on the isocontour and crawl, not race.
		vec2 v_target = t * tangent_speed;
		vec2 fv = (v_target - vel) * fv_strength * W;
		vel += (fa + fv) * DELTA;

		// Kill any remaining inward component near the hole.
		float near_hole = 1.0 - far_field;
		float into_hole = min(dot(vel, n), 0.0);
		vel -= into_hole * n * max(near_hole, W);

		// --- Shadow contour: pull particles onto the 0.5 level set of the shadow ---
		// Inside the shadow the pull points out, outside it points in, so particles
		// gather on the outline instead of filling or avoiding it. The gradient weight
		// keeps the force local: particles far from the shadow are left alone.
		vec2 s_grad = shadow_gradient(uv);
		float s_mag = length(s_grad);
		if (s_mag > 1e-3) {
			vec2 s_n = s_grad / s_mag;
			float s_val = shadow_at(uv);
			float edge = smoothstep(1.0, 4.0, s_mag);
			vel += s_n * (0.5 - s_val) * shadow_pull_strength * edge * DELTA;
		}

		vel *= exp(-damping * DELTA);

		float spd = length(vel);
		if (spd > max_speed && spd > 1e-5) {
			vel *= max_speed / spd;
		}

		pos.xy += vel * DELTA;
		pos.z = 0.0;

		// Project back onto / outside the keep isocontour (compass circle).
		vec2 uv2 = world_to_uv(pos.xy);
		float m2 = mask_at(uv2);
		vec2 grad2 = mask_gradient(uv2);
		float g2 = length(grad2);
		vec2 n2 = g2 > 1e-4 ? grad2 / g2 : (length(pos.xy) > 1e-4 ? normalize(pos.xy) : vec2(1.0, 0.0));
		if (m2 < hole_keep_threshold) {
			pos.xy += n2 * (hole_keep_threshold - m2) * hole_project_strength;
			float into2 = min(dot(vel, n2), 0.0);
			vel -= into2 * n2;
		}

		if (abs(pos.x) > wall_half_extents.x) {
			pos.x = clamp(pos.x, -wall_half_extents.x, wall_half_extents.x);
			vel.x = 0.0;
		}
		if (abs(pos.y) > wall_half_extents.y) {
			pos.y = clamp(pos.y, -wall_half_extents.y, wall_half_extents.y);
			vel.y = 0.0;
		}

		VELOCITY = vec3(vel, 0.0);
		TRANSFORM = mat4(
			vec4(sc, 0.0, 0.0, 0.0),
			vec4(0.0, sc, 0.0, 0.0),
			vec4(0.0, 0.0, sc, 0.0),
			vec4(pos, 1.0)
		);
		COLOR = vec4(particle_tint, 1.0);
	}
}
