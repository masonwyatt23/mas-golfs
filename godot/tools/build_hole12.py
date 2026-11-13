#!/usr/bin/env python3
"""Build godot/scenes/hole_12.tscn — Hole 12, "The Picture" (par 3, 172 yd).

v1: primitives + real layout from docs/course-design-v3.md §12.
Units are yards (1 unit = 1 yd). Tee at the origin, the hole runs down
-Z; the green is 172 yd out and 22 ft (~7.3 yd) downhill, fronted by
the pond. The scene is generated (not hand-edited) so positions stay
derivable from the course data; re-run to regenerate.

Run:  python3 godot/tools/build_hole12.py   (writes godot/scenes/hole_12.tscn)
"""
from __future__ import annotations

import os

OUT = os.path.join(os.path.dirname(__file__), "..", "scenes", "hole_12.tscn")

# --- Course data (course-design-v3.md §12) ---------------------------------
TEE_Y = 7.3            # tee elevation (22 ft downhill to the green)
GREEN_Z = -172.0       # green centre, yards down the hole
GREEN_R = 14.0         # green 28 yd wide
POND_Z0, POND_Z1 = -148.0, -168.0   # pond fronts the entire green
POND_Y = -0.6
BUNKER_Z = -186.0      # bunker behind the green
PIN = (-6.0, -166.0)  # front-left (Sunday) pin, near the water

# --- Helpers -----------------------------------------------------------------
subs: list[str] = []      # [sub_resource] blocks
nodes_out: list[str] = []  # [node] blocks
sub_id = [0]


def sub(kind: str, props: dict) -> str:
    sub_id[0] += 1
    sid = f"{kind}_{sub_id[0]}"
    subs.append(f'[sub_resource type="{kind}" id="{sid}"]')
    for k, v in props.items():
        subs.append(f"{k} = {v}")
    subs.append("")
    return sid


def mat(color: tuple[float, float, float], roughness: float = 0.9,
        metallic: float = 0.0, unshaded: bool = False) -> str:
    r, g, b = color
    props = {
        "albedo_color": f"Color({r}, {g}, {b}, 1)",
        "roughness": str(roughness),
        "metallic": str(metallic),
    }
    if unshaded:
        props["shading_mode"] = "1"  # SHADING_MODE_UNSHADED: albedo as-is, no lighting
    return sub("StandardMaterial3D", props)


def box(sx: float, sy: float, sz: float) -> str:
    return sub("BoxMesh", {"size": f"Vector3({sx}, {sy}, {sz})"})


def plane(sx: float, sz: float) -> str:
    return sub("PlaneMesh", {"size": f"Vector2({sx}, {sz})"})


def cyl(top_r: float, bot_r: float, height: float, sides: int = 24) -> str:
    return sub("CylinderMesh", {
        "top_radius": str(top_r), "bottom_radius": str(bot_r),
        "height": str(height), "radial_segments": str(sides),
    })


def sphere(r: float) -> str:
    return sub("SphereMesh", {"radius": str(r), "height": str(2 * r)})


def capsule(r: float, h: float) -> str:
    return sub("CapsuleMesh", {"radius": str(r), "height": str(h)})


def node(name: str, ntype: str, parent: str | None, transform: str | None = None,
         extra: list[str] | None = None) -> None:
    if parent is None:
        nodes_out.append(f'[node name="{name}" type="{ntype}"]')
    else:
        nodes_out.append(f'[node name="{name}" type="{ntype}" parent="{parent}"]')
    if transform:
        nodes_out.append(f"transform = {transform}")
    for e in extra or []:
        nodes_out.append(e)
    nodes_out.append("")


def t(x: float, y: float, z: float) -> str:
    return f"Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {x}, {y}, {z})"


def mesh_node(name: str, mesh: str, material: str, x: float, y: float,
              z: float) -> None:
    node(name, "MeshInstance3D", ".", t(x, y, z), [
        f'mesh = SubResource("{mesh}")',
        f'surface_material_override/0 = SubResource("{material}")',
    ])


# --- Materials ----------------------------------------------------------------
# Grass is SHADED again (the v6 unshaded diagnostic proved the mesh
# renders; the tee/green already prove shaded green reads fine).
grass = mat((0.28, 0.58, 0.28))
fairway = mat((0.32, 0.62, 0.30))
green_mat = mat((0.35, 0.70, 0.32))
collar_mat = mat((0.22, 0.55, 0.22))
sand = mat((0.85, 0.75, 0.55), roughness=1.0)
water = mat((0.10, 0.35, 0.55), roughness=0.15, metallic=0.4)
trunk_mat = mat((0.35, 0.22, 0.12))
pine_mat = mat((0.08, 0.25, 0.12))
shirt = mat((0.08, 0.12, 0.30))
pants = mat((0.15, 0.15, 0.15))
skin = mat((0.85, 0.65, 0.50))
white = mat((0.95, 0.95, 0.95))
red = mat((0.80, 0.10, 0.10))
club_mat = mat((0.60, 0.60, 0.65), metallic=0.8, roughness=0.3)

# --- Meshes -------------------------------------------------------------------
# Ground is a thin BOX. v6 PROVED the culling theory: the 400x400 ground
# never rendered (v5 unshaded was pixel-identical to v4) while a 120x120
# box renders fine — the huge mesh is frustum-culled because the camera
# sits inside its footprint. The black trapezoid in v6 is the sky's dark
# ground showing through beyond the 120-box's far edge (z=-140). Fix: a
# ground long enough to reach the horizon (z=-340) but whose near edge
# stays in FRONT of the camera (z=-20), so the camera is outside its
# footprint and it renders. 240 wide x 360 deep, centred z=-160.
ground_mesh = box(240, 0.4, 360)
tee_mesh = box(12, 0.4, 10)
green_mesh = cyl(GREEN_R, GREEN_R, 0.4, 32)
collar_mesh = cyl(GREEN_R + 3, GREEN_R + 3, 0.3, 32)
pond_mesh = plane(64, 20)
bunker_mesh = cyl(7, 7, 0.3, 24)
stick_mesh = cyl(0.06, 0.06, 7, 8)
flag_mesh = plane(2.2, 1.4)
trunk_mesh = cyl(0.5, 0.7, 6, 8)
canopy_mesh = cyl(0.0, 4.5, 12, 12)
body_mesh = capsule(0.55, 2.6)
head_mesh = sphere(0.42)
leg_mesh = cyl(0.22, 0.22, 1.6, 8)
club_mesh = cyl(0.05, 0.05, 3.4, 8)

# --- Sky / environment ---------------------------------------------------------
sky_mat = sub("ProceduralSkyMaterial", {
    "sky_top_color": "Color(0.25, 0.45, 0.75, 1)",
    "sky_horizon_color": "Color(0.95, 0.65, 0.35, 1)",
    "ground_bottom_color": "Color(0.15, 0.20, 0.12, 1)",
    "ground_horizon_color": "Color(0.85, 0.60, 0.35, 1)",
    "sun_angle_max": "30.0",
    "sun_curve": "0.08",
})
sky = sub("Sky", {"sky_material": f'SubResource("{sky_mat}")'})
env = sub("Environment", {
    "background_mode": "2",
    "sky": f'SubResource("{sky}")',
    "ambient_light_source": "2",
    "ambient_light_energy": "1.0",
    "tonemap_mode": "2",
    "tonemap_exposure": "1.0",
    "glow_enabled": "true",
})

# --- Scene ---------------------------------------------------------------------
# (sub_resources and nodes were collected above; the header must lead.)

node("Hole12", "Node3D", None)
node("WorldEnvironment", "WorldEnvironment", ".", None,
     [f'environment = SubResource("{env}")'])
# Golden-hour sun: low, warm, from behind-left so the golfer is rim-lit.
# Shadows OFF for now — the v2 frame rendered the whole ground black and
# the prime suspect is the directional shadow map acne-ing the flat
# ground plane. Re-enable with a tuned bias once the ground reads green.
node("Sun", "DirectionalLight3D", ".",
     "Transform3D(0.866, 0.353, 0.353, 0, 0.707, -0.707, -0.5, 0.612, 0.612, 0, 40, 20)",
     ["light_color = Color(1, 0.85, 0.6, 1)",
      "light_energy = 1.6",
      "shadow_enabled = false"])
node("BusClient", "Node", ".", None, ['script = ExtResource("1")'])
node("Director", "Node", ".", None, ['script = ExtResource("2")'])

# Ground + hole features.
# Ground centred at z=-160 so it spans z=-340..-20 (near edge in front of
# the camera at z=15, far edge past the green at -172 to the horizon).
mesh_node("Ground", ground_mesh, grass, 0, -0.2, -160)
mesh_node("Tee", tee_mesh, fairway, 0, TEE_Y - 0.2, 0)
mesh_node("Collar", collar_mesh, collar_mat, 0, -0.15, GREEN_Z)
mesh_node("Green", green_mesh, green_mat, 0, 0, GREEN_Z)
mesh_node("Pond", pond_mesh, water, 0, POND_Y, (POND_Z0 + POND_Z1) / 2)
mesh_node("Bunker", bunker_mesh, sand, 0, -0.15, BUNKER_Z)
mesh_node("Flagstick", stick_mesh, white, PIN[0], 3.5, PIN[1])
# Flag: a small red plane on the stick, facing the tee (+Z).
node("Flag", "MeshInstance3D", ".",
     f"Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {PIN[0] + 1.1}, 6.2, {PIN[1]})",
     [f'mesh = SubResource("{flag_mesh}")',
      f'surface_material_override/0 = SubResource("{red}")'])

# Pines framing the green (both sides).
for i, (px, pz) in enumerate([(-22, -160), (-26, -172), (-20, -182),
                              (22, -160), (26, -172), (20, -182)]):
    mesh_node(f"PineTrunk{i}", trunk_mesh, trunk_mat, px, 3, pz)
    mesh_node(f"PineCanopy{i}", canopy_mesh, pine_mat, px, 11, pz)

# Mas — a simple standing figure at the tee, facing down the hole (-Z).
# (Placeholder proportions; the swing-video character replaces this.)
node("Mas", "Node3D", ".", t(0, TEE_Y, 2))
mesh_node("MasBody", body_mesh, shirt, 0, TEE_Y + 1.6, 2)
mesh_node("MasHead", head_mesh, skin, 0, TEE_Y + 3.3, 2)
mesh_node("MasLegL", leg_mesh, pants, -0.3, TEE_Y + 0.8, 2)
mesh_node("MasLegR", leg_mesh, pants, 0.3, TEE_Y + 0.8, 2)
# Club held upright beside him (pose is a stub until the swing rig lands).
mesh_node("MasClub", club_mesh, club_mat, 0.9, TEE_Y + 1.7, 1.6)

# Broadcast camera — always behind the golfer, looking down the hole.
# v2 pulled too far (Mas left the frame). This is the middle: back and up
# enough that Mas is a small figure and the hole reads, close enough that
# he is still in the shot. Tilted down 15 deg.
node("BroadcastCam", "Camera3D", ".",
     "Transform3D(1, 0, 0, 0, 0.966, 0.259, 0, -0.259, 0.966, 0, 11, 15)",
     ["fov = 50.0", "current = true"])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
header = ['[gd_scene load_steps=%d format=3]' % (sub_id[0] + 3), "",
          '[ext_resource type="Script" path="res://scripts/bus_client.gd" id="1"]',
          '[ext_resource type="Script" path="res://scripts/director.gd" id="2"]', ""]
out_lines = header + subs + nodes_out
with open(OUT, "w") as f:
    f.write("\n".join(out_lines))
print(f"wrote {OUT} ({len(out_lines)} lines)")
