// Terrain shader for the Mas Golfs Godot Hole 12 — the "far better" pass.
//
// The flat unshaded green read as a diorama. This shader gives the course
// real grass: a tiled detail texture (grass-detail.png), mowing stripes
// on the fairway, a lighter smoother green, and real Lambert lighting so
// the LiDAR elevation reads through light and shadow (and the sun's
// shadows actually land on it).
//
// Zones are computed from world XZ (the terrain is in Godot scene units,
// yards, tee at origin, hole runs down -Z, green centre (0,-172) r=14):
//   green   — within 14 yd of (0,-172): lighter, smoother, no stripes.
//   fairway — |x| < 14, z in [-180, +8]: mowing stripes every 6 yd.
//   rough   — everything else: darker, coarser.
// The base colors are multiplied by the grass detail texture, so the
// micro-grain shows through everywhere.
shader_type spatial;
render_mode diffuse_lambert, specular_disabled;

uniform sampler2D grass_tex : repeat_enable;
uniform vec3 rough_color : source_color = vec3(0.16, 0.38, 0.16);
uniform vec3 fairway_color : source_color = vec3(0.24, 0.52, 0.22);
uniform vec3 green_color : source_color = vec3(0.32, 0.62, 0.28);

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	// Grass detail: tile the texture by world XZ, 1 tile per 4 yd.
	vec3 detail = texture(grass_tex, world_pos.xz / 4.0).rgb;

	// Green: within 14 yd of the green centre (0,-172).
	float green_d = distance(world_pos.xz, vec2(0.0, -172.0));
	float is_green = 1.0 - smoothstep(12.0, 16.0, green_d);

	// Fairway: corridor |x| < 14, z from +8 to -180.
	float fairway_x = 1.0 - smoothstep(11.0, 15.0, abs(world_pos.x));
	float fairway_z = smoothstep(10.0, 4.0, world_pos.z)
		* (1.0 - smoothstep(-176.0, -182.0, world_pos.z));
	float is_fairway = fairway_x * fairway_z * (1.0 - is_green);

	// Mowing stripes on the fairway: bands every 6 yd along z,
	// alternating 1.0 / 0.86 brightness.
	float stripe = mod(floor(world_pos.z / 6.0), 2.0);
	float stripe_bright = mix(1.0, 0.86, stripe);

	// Base color: rough, then fairway (with stripes), then green on top.
	vec3 base = rough_color;
	base = mix(base, fairway_color * stripe_bright, is_fairway);
	base = mix(base, green_color, is_green);

	ALBEDO = base * detail;
	// A touch of roughness variation so the light doesn't read flat.
	ROUGHNESS = 0.95;
}
