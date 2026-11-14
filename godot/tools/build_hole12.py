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
        # SHADING_MODE_UNSHADED = 0 (NOT 1 — 1 is PER_PIXEL). The v5-v15
        # "unshaded" diagnostic used 1, so the ground was per-pixel shaded
        # all along and its top face rendered black under the low sun.
        # 0 = unshaded: albedo output directly, no lighting.
        props["shading_mode"] = "0"  # SHADING_MODE_UNSHADED
        props["cull_mode"] = "2"  # CULL_DISABLED (top face was backface-culled)
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


def rx(deg: float) -> tuple[float, float, float, float, float, float,
                           float, float, float]:
    """Basis for a rotation about the X axis (pitch). Positive deg tips
    the +Y axis toward +Z; negative tips it toward -Z (forward, down the
    hole). Returns the 9 basis numbers for a Transform3D."""
    import math
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (1, 0, 0, 0, c, s, 0, -s, c)


def tr_basis(basis, x: float, y: float, z: float) -> str:
    b = basis
    return (f"Transform3D({b[0]:.3f}, {b[1]:.3f}, {b[2]:.3f}, "
            f"{b[3]:.3f}, {b[4]:.3f}, {b[5]:.3f}, "
            f"{b[6]:.3f}, {b[7]:.3f}, {b[8]:.3f}, {x}, {y}, {z})")


def cyl_between(a, b):
    """Transform3D + length for a Y-axis cylinder spanning point a to
    point b (a 3-tuple each). The cylinder is centred at the midpoint
    with its Y axis along (b-a). Caller creates the cylinder mesh with
    height == the returned length."""
    import math
    ax, ay, az = a
    bx, by, bz = b
    d = (bx - ax, by - ay, bz - az)
    length = math.sqrt(sum(v * v for v in d))
    y = tuple(v / length for v in d)
    ref = (1, 0, 0) if abs(y[1]) < 0.9 else (0, 0, 1)
    x = (y[1] * ref[2] - y[2] * ref[1],
         y[2] * ref[0] - y[0] * ref[2],
         y[0] * ref[1] - y[1] * ref[0])
    xl = math.sqrt(sum(v * v for v in x))
    x = tuple(v / xl for v in x)
    z = (y[1] * x[2] - y[2] * x[1],
         y[2] * x[0] - y[0] * x[2],
         y[0] * x[1] - y[1] * x[0])
    mx, my, mz = (ax + bx) / 2, (ay + by) / 2, (az + bz) / 2
    tf = (f"Transform3D({x[0]:.3f}, {x[1]:.3f}, {x[2]:.3f}, "
          f"{y[0]:.3f}, {y[1]:.3f}, {y[2]:.3f}, "
          f"{z[0]:.3f}, {z[1]:.3f}, {z[2]:.3f}, "
          f"{mx:.3f}, {my:.3f}, {mz:.3f})")
    return tf, length


def look_at(eye, target, up=(0, 1, 0)):
    """Transform3D for a camera at eye looking at target. The camera
    looks along its -Z axis. Used for the broadcast camera so it can sit
    offset from the target line (down-the-line view) and still frame the
    green — a dead-behind camera hides the address pose's arms/club/ball
    behind the torso (v23)."""
    import math
    ex, ey, ez = eye
    tx, ty, tz = target
    fx, fy, fz = tx - ex, ty - ey, tz - ez
    fl = math.sqrt(fx * fx + fy * fy + fz * fz)
    fx, fy, fz = fx / fl, fy / fl, fz / fl
    zx, zy, zz = -fx, -fy, -fz  # camera +Z points back from the target
    ux, uy, uz = up
    xx = uy * zz - uz * zy
    xy = uz * zx - ux * zz
    xz = ux * zy - uy * zx
    xl = math.sqrt(xx * xx + xy * xy + xz * xz)
    xx, xy, xz = xx / xl, xy / xl, xz / xl
    yx = zy * xz - zz * xy
    yy = zz * xx - zx * xz
    yz = zx * xy - zy * xx
    return (f"Transform3D({xx:.3f}, {xy:.3f}, {xz:.3f}, "
            f"{yx:.3f}, {yy:.3f}, {yz:.3f}, "
            f"{zx:.3f}, {zy:.3f}, {zz:.3f}, {ex}, {ey}, {ez})")


def mesh_node(name: str, mesh: str, material: str, x: float, y: float,
              z: float) -> None:
    node(name, "MeshInstance3D", ".", t(x, y, z), [
        f'mesh = SubResource("{mesh}")',
        f'surface_material_override/0 = SubResource("{material}")',
    ])


# --- Materials ----------------------------------------------------------------
# Grass is UNSHADED again (diagnostic): v8's SHADED tiled ground rendered
# black while v6's UNSHADED single tile rendered dark green. If the tiled
# ground renders green unshaded, the problem is shading/lighting on the
# ground tiles specifically (not culling); if still black, the tiles are
# not rendering at all. The tee/green prove shaded green CAN read.
grass = mat((0.28, 0.58, 0.28), unshaded=True)  # green again (v14 magenta was the diagnostic; shading_mode is now truly 0=unshaded, so this renders flat green)
# v31: PBR terrain material — the OBJ now has planar UVs (heightmap_to_mesh
# v31, texture tiles every 4 yd), so a real grass texture maps. Grass004
# (ambientCG, CC0, 2K) albedo + normal, roughness high (grass is matte).
# SHADED (not unshaded): SDFGI (v30) is the fix for the v28 black-shadow
# failure — bounced light in shadowed areas. If this still renders black,
# SDFGI alone does not fix it and the sun angle/bias is next.
terrain_pbr = sub("StandardMaterial3D", {
    "albedo_color": "Color(1, 1, 1, 1)",
    "albedo_texture": 'ExtResource("4")',
    "normal_enabled": "true",
    "normal_texture": 'ExtResource("5")',
    "normal_scale": "1.0",
    "roughness": "0.95",
    "metallic": "0.0",
    "texture_filter": "2",
})
fairway = mat((0.32, 0.62, 0.30), unshaded=True)
green_mat = mat((0.35, 0.70, 0.32), unshaded=True)
collar_mat = mat((0.22, 0.55, 0.22), unshaded=True)
sand = mat((0.85, 0.75, 0.55), roughness=1.0, unshaded=True)
water = mat((0.10, 0.35, 0.55), roughness=0.15, metallic=0.4, unshaded=True)
trunk_mat = mat((0.35, 0.22, 0.12))
pine_mat = mat((0.08, 0.25, 0.12))
shirt = mat((0.08, 0.12, 0.30))
pants = mat((0.15, 0.15, 0.15))
skin = mat((0.85, 0.65, 0.50))
white = mat((0.95, 0.95, 0.95))
red = mat((0.80, 0.10, 0.10))
club_mat = mat((0.60, 0.60, 0.65), metallic=0.8, roughness=0.3)

# --- Meshes -------------------------------------------------------------------
# Ground: ONE tile, 120 wide x 300 deep, centred z=-170 (spans z=-320..-20).
# v11 proved side-by-side tiles do NOT render — only the single centre
# tile renders (the x=±120 tiles contribute nothing; v11 is identical to
# v10). So the ground stays one 120-wide tile. It is too narrow to fill
# the frame at the green (~287 yd wide there), so the sides beyond x=±60
# show the sky's dark ground as a black trapezoid. That is fixed with
# depth FOG (below), not with more ground: the far field fades to warm
# golden-hour haze, which is the cinematic look anyway.
ground_mesh = box(120, 0.4, 300)
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
# v32: Sky3D replaces the ProceduralSkyMaterial + hand-placed Sun. Sky3D
# (class_name Sky3D extends WorldEnvironment) auto-creates $SunLight
# (DirectionalLight3D, shadow_enabled = true), $MoonLight, $SkyDome and
# $TimeOfDay. It replaces the environment's sky with its own shader sky
# when environment.sky is null (Sky3D.gd:479-485) — so the Environment
# below has NO sky property; Sky3D creates it at runtime. The v30
# v35: current_time 17.5 was BLACK — Sky3D's TimeOfDay defaults to
# lat 16, lon 108, and at 17.5h the sun is at/below the horizon there:
# dark sky, weak light, and every shaded surface (PBR terrain, Mas,
# pines) rendered black (the v28 self-shadow failure, live for the
# first time — v31/v32/v33 were never actually pulled by the Mac, so
# their "no visible change" captures were v30). current_time 15.0 =
# mid-afternoon, sun high, bright sky, short shadows. Ambient 1.25 ->
# 2.0 as a safety net so shaded surfaces are never pitch black.
# game_time_enabled = false freezes the sun at 15.0 (no drift during
# the broadcast). The old Sun node is REMOVED — Sky3D brings its own.
env = sub("Environment", {
    "background_mode": "2",
    "ambient_light_source": "2",
    # v2: ambient 1.0 -> 1.25 and exposure 1.0 -> 1.1 to lift the dark
    # ground read in the v1 frame; small, reversible, re-check on capture.
    "ambient_light_energy": "2.0",
    # v30 (post-processing pass): ACES tonemap (3) instead of Filmic (2) —
    # better highlight rolloff for the golden-hour sun. SSAO + SSIL add
    # contact shadows and bounced light. SDFGI is the specific fix for
    # the black-terrain shadow failure (v2/v21/v28): it gives shadowed
    # areas bounced light instead of black. These are all built into
    # Godot 4.7 Forward+ — no addon needed. Glow was already on.
    "tonemap_mode": "3",
    "tonemap_exposure": "1.1",
    "glow_enabled": "true",
    "ssao_enabled": "true",
    "ssil_enabled": "true",
    "sdfgi_enabled": "true",
    # Fog OFF: v12's depth fog washed the whole frame to tan, including
    # the near field — the begin/end distances did not behave as expected.
    "fog_enabled": "false",
    "fog_mode": "1",
    "fog_light_color": "Color(0.9, 0.65, 0.4, 1)",
    "fog_light_energy": "1.0",
    "fog_sun_scatter": "0.3",
    "fog_density": "0.007",
    "fog_depth_begin": "60.0",
    "fog_depth_end": "300.0",
})

# --- Scene ---------------------------------------------------------------------
# (sub_resources and nodes were collected above; the header must lead.)
# The terrain OBJ is an external PackedScene (id 3) — Godot imports the
# .obj + .mtl on first open. It is instanced below as "Terrain".

node("Hole12", "Node3D", None)
# v39: attach the addon scripts to BASE-type nodes instead of using
# the class names. The diag proved load() returns valid GDScript but
# ClassDB NEVER gets the addon class_names (not in -s mode, not in a
# main-scene run, not after a .godot rebuild) — so type="Sky3D" /
# type="PhantomCamera3D" can never instantiate headless. A
# WorldEnvironment + Sky3D.gd IS a Sky3D; a Camera3D +
# phantom_camera_3d.gd IS a PhantomCamera3D; a Node +
# phantom_camera_host.gd IS a PhantomCameraHost. Script attachment
# needs only the script resource, not the ClassDB.
node("Sky3D", "WorldEnvironment", ".", None,
     [f'environment = SubResource("{env}")',
      'script = ExtResource("10")',
      "current_time = 15.0",
      "game_time_enabled = false"])
node("BusClient", "Node", ".", None, ['script = ExtResource("1")'])
node("Director", "Node", ".", None, ['script = ExtResource("2")'])
# v38: Capture node — captures a frame when run with --capture, does
# nothing otherwise (so the broadcast runs normally). Running the scene
# directly as the main scene is the ONLY way the addon global classes
# (Sky3D, PhantomCamera) resolve; the -s script path never populates
# the ClassDB with them.
node("Capture", "Node", ".", None, ['script = ExtResource("9")'])

# Ground + hole features.
# TERRAIN (v18): the LiDAR heightfield mesh replaces the flat ground tile.
# The terrain OBJ (godot/tools/wyatt-hole12-terrain.obj, regenerated by
# godot/tools/heightmap_to_mesh.py) is 320 yd wide with real elevation —
# the flat 120-wide tile left sky-ground at the frame sides and read as
# a diorama. The flat Ground tile is REMOVED (it would z-fight the
# terrain). Feature nodes are raised +0.05 yd so their tops sit clearly
# above the terrain's flattened feature discs (tee 7.3, green 0.0),
# which are coplanar with the old node tops.
mesh_node("Tee", tee_mesh, fairway, 0, TEE_Y - 0.2 + 0.05, 0)
# Terrain mesh (LiDAR heightfield) — a MeshInstance3D using the imported
# OBJ mesh. ResourceImporterOBJ imports an .obj as a single Mesh
# (ArrayMesh), NOT a PackedScene — so the .tscn references it as
# type="ArrayMesh" and assigns it to a MeshInstance3D's mesh property.
# (v18 used PackedScene + instance=, which failed: "No loader found for
# resource (expected type: PackedScene)" and a black frame.) Identity
# transform: the OBJ is already in Godot scene units (yards, Y-up, tee
# at origin).
# v31: PBR grass on the terrain (terrain_pbr, Grass004 albedo + normal,
# planar UVs from heightmap_to_mesh v31) + shadows ON. SDFGI (v30) is
# the fix for the v28 black-shadow failure — this is the test of it.
# If the terrain renders black again, SDFGI alone does not fix it.
node("Terrain", "MeshInstance3D", ".", t(0, 0, 0),
     ['mesh = ExtResource("3")',
      f'surface_material_override/0 = SubResource("{terrain_pbr}")'])
mesh_node("Collar", collar_mesh, collar_mat, 0, -0.15 + 0.05, GREEN_Z)
mesh_node("Green", green_mesh, green_mat, 0, 0 + 0.05, GREEN_Z)
mesh_node("Pond", pond_mesh, water, 0, POND_Y, (POND_Z0 + POND_Z1) / 2)
mesh_node("Bunker", bunker_mesh, sand, 0, -0.15 + 0.05, BUNKER_Z)
mesh_node("Flagstick", stick_mesh, white, PIN[0], 3.5, PIN[1])
# Flag: a small red plane on the stick, facing the tee (+Z).
node("Flag", "MeshInstance3D", ".",
     f"Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {PIN[0] + 1.1}, 6.2, {PIN[1]})",
     [f'mesh = SubResource("{flag_mesh}")',
      f'surface_material_override/0 = SubResource("{red}")'])

# Pines framing the green (both sides).
# v34: Quaternius Stylized Nature MegaKit pines (CC0, glTF) replace the
# cone pines. Pine_1/2/3 cycle across the 6 positions. The glTF trees
# are ~7.3m tall (Y -0.24..7.1); at scale 2.0 they stand ~14.7 yd,
# matching the old cone pines (~17 yd). Base sits at y=0.5 so the
# trunk bottom (-0.24 * 2 = -0.48) lands at ~0.02, just above the
# terrain (green is flat y=0). The glTFs are PackedScene ext_resources
# (ids 6-8); their textures (Bark_NormalTree, Leaf_Pine_C) sit beside
# them in res://models/pines/ so the relative URIs resolve.
for i, (px, pz) in enumerate([(-22, -160), (-26, -172), (-20, -182),
                              (22, -160), (26, -172), (20, -182)]):
    _pine_id = ["6", "7", "8"][i % 3]
    node(f"Pine{i}", "Node3D", ".",
         f"Transform3D(2, 0, 0, 0, 2, 0, 0, 0, 2, {px}, 0.5, {pz})",
         [f'instance = ExtResource("{_pine_id}")'])

# Mas — at address over the ball (v23). A golfer bent over a ball reads
# instantly; the old upright capsule did not. Left-handed, facing -Z
# (down the hole), feet at z=2 on the tee. All units yards; Mas ~6 ft.
#   hips (0, 8.9, 2.0); torso tilted 20 deg forward; shoulders (0, 10.22, 1.52)
#   ball on a tee at (0.25, 7.45, 0.7); grip at (0.25, 8.55, 1.05)
# Arms and club are cylinders oriented between two points (cyl_between);
# the torso is a capsule pitched forward with rx(-20). The swing-video
# character still replaces this eventually, but address is the right
# silhouette to judge the camera and the hole against.
node("Mas", "Node3D", ".", t(0, TEE_Y, 2))
# Legs — planted, vertical.
mesh_node("MasLegL", leg_mesh, pants, -0.3, TEE_Y + 0.8, 2)
mesh_node("MasLegR", leg_mesh, pants, 0.3, TEE_Y + 0.8, 2)
# Torso — capsule pitched 20 deg forward, centred between hips and shoulders.
_torso_tf = tr_basis(rx(-20), 0, 9.558, 1.762)
node("MasBody", "MeshInstance3D", ".", _torso_tf,
     [f'mesh = SubResource("{body_mesh}")',
      f'surface_material_override/0 = SubResource("{shirt}")'])
# Head + cap at the top of the tilted torso.
# v27: head raised and moved back (+Z) so it peeks above the torso from
# behind; the v23 head sat forward of the shoulders and hid behind them.
mesh_node("MasHead", head_mesh, skin, 0, 10.6, 1.55)
_cap_mesh = cyl(0.45, 0.45, 0.18, 16)
_cap_tf = tr_basis(rx(-20), 0, 10.9, 1.5)
node("MasCap", "MeshInstance3D", ".", _cap_tf,
     [f'mesh = SubResource("{_cap_mesh}")',
      f'surface_material_override/0 = SubResource("{shirt}")'])
# Arms — from shoulders to the grip (grip follows the ball to x=0.9).
for _name, _a, _b in [
        ("MasArmL", (-0.35, 10.15, 1.55), (0.9, 8.55, 1.05)),
        ("MasArmR", (0.35, 10.15, 1.55), (0.9, 8.55, 1.05))]:
    _tf, _ln = cyl_between(_a, _b)
    _m = cyl(0.14, 0.14, _ln, 8)
    node(_name, "MeshInstance3D", ".", _tf,
         [f'mesh = SubResource("{_m}")',
          f'surface_material_override/0 = SubResource("{shirt}")'])
# Club — from the grip down to the ball.
_club_tf, _club_len = cyl_between((0.9, 8.55, 1.05), (0.9, 7.45, 0.7))
_club_m = cyl(0.05, 0.05, _club_len, 8)
node("MasClub", "MeshInstance3D", ".", _club_tf,
     [f'mesh = SubResource("{_club_m}")',
      f'surface_material_override/0 = SubResource("{club_mat}")'])
# Ball on a tee peg, in front of Mas.
# v27: ball moved to x=0.9 (outside the torso's right edge) so the club
# sticks out beyond the torso silhouette and reads from behind.
_tee_m = cyl(0.03, 0.03, 0.15, 8)
node("MasTeePeg", "MeshInstance3D", ".", t(0.9, TEE_Y + 0.075, 0.7),
     [f'mesh = SubResource("{_tee_m}")',
      f'surface_material_override/0 = SubResource("{white}")'])
_ball_m = sphere(0.07)
node("MasBall", "MeshInstance3D", ".", t(0.9, TEE_Y + 0.15, 0.7),
     [f'mesh = SubResource("{_ball_m}")',
      f'surface_material_override/0 = SubResource("{white}")'])

# Broadcast camera — always behind the golfer, looking down the hole.
# v27: REVERT to the v22 dead-behind camera (0,12,25), 15 deg pitch.
# The offset cameras (v24-v26) kept breaking the framing — Mas at the
# frame edge, too much blue sky, the green tiny. The v22 framing (Mas
# centred, green in the upper third, warm horizon) is the right one;
# the address pose now reads from behind instead, because the ball and
# club sit at x=0.9, outside the torso silhouette. FOV 50.
node("BroadcastCam", "Camera3D", ".",
     "Transform3D(1, 0, 0, 0, 0.966, 0.259, 0, -0.259, 0.966, 0, 12, 25)",
     ["fov = 50.0", "current = true"])
# v33: Phantom Camera (Cinemachine-style broadcast camera). The host is
# a child of the Camera3D; it drives the Camera3D from the highest-
# priority PhantomCamera3D in the scene. TeeCam follows Mas (the
# golfer) with the dead-behind offset and looks at the Green — the same
# framing as the hand-written camera above, but now the camera FOLLOWS
# Mas when he moves (swing, ball flight) and can tween tee->green.
# follow_offset is relative to Mas at (0, 7.3, 2): (0, 4.7, 23) puts
# the camera at (0, 12, 25). tween_on_load = false so the first frame
# is already at the follow position (no opening tween in the capture).
node("PhantomCameraHost", "Node", "BroadcastCam",
     None, ['script = ExtResource("12")'])
node("TeeCam", "Camera3D", ".", t(0, 12, 25),
     ['script = ExtResource("11")',
      "priority = 1",
      "follow_mode = 2",
      'follow_target = NodePath("../Mas")',
      "follow_offset = Vector3(0, 4.7, 23)",
      "look_at_mode = 2",
      'look_at_target = NodePath("../Green")',
      "tween_on_load = false"])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
header = ['[gd_scene load_steps=%d format=3]' % (sub_id[0] + 13), "",
          '[ext_resource type="Script" path="res://scripts/bus_client.gd" id="1"]',
          '[ext_resource type="Script" path="res://scripts/director.gd" id="2"]',
          '[ext_resource type="ArrayMesh" path="res://tools/wyatt-hole12-terrain.obj" id="3"]',
          '[ext_resource type="Texture2D" path="res://textures/Grass004_Color.jpg" id="4"]',
          '[ext_resource type="Texture2D" path="res://textures/Grass004_NormalGL.jpg" id="5"]',
          '[ext_resource type="PackedScene" path="res://models/pines/Pine_1.gltf" id="6"]',
          '[ext_resource type="PackedScene" path="res://models/pines/Pine_2.gltf" id="7"]',
          '[ext_resource type="PackedScene" path="res://models/pines/Pine_3.gltf" id="8"]',
          '[ext_resource type="Script" path="res://tools/capture_node.gd" id="9"]',
          '[ext_resource type="Script" path="res://addons/sky_3d/src/Sky3D.gd" id="10"]',
          '[ext_resource type="Script" path="res://addons/phantom_camera/scripts/phantom_camera/phantom_camera_3d.gd" id="11"]',
          '[ext_resource type="Script" path="res://addons/phantom_camera/scripts/phantom_camera_host/phantom_camera_host.gd" id="12"]', ""]
out_lines = header + subs + nodes_out
with open(OUT, "w") as f:
    f.write("\n".join(out_lines))
print(f"wrote {OUT} ({len(out_lines)} lines)")
