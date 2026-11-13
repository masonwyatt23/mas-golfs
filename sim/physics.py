"""Shot generation: delivery -> launch -> flight -> landing (spec §2).

One integrator code path, vectorized with numpy: a single real shot is
N=1, the decision engine's Monte Carlo is N=120+ — same math either way.

Sign conventions (§1.2): all lateral signs are from the golfer's
perspective facing the target, + = the golfer's right. Mas is left-handed;
the physics is handedness-agnostic once start direction and spin axis are
computed, and the renderer mirrors lateral geometry for a left-hander.

Flight frame: x = along the target line (horizontal), y = up,
z = lateral (+ = golfer's right).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import constants as C
from .rng import Rng

# Lift-coefficient model (Smits & Smith spin-ratio quadratic):
#   Cl = CL_C2 * S^2 + CL_C1 * S,  S = omega * R / |v|
# Fitted against the §3.2 gapping table and the mishit behaviour
# (a chunk must lose carry, a thin must lose spin/launch). The spec's
# linear Cl = spin / 145000 is documented as wrong in fly() below.
# CORRECTION 3 (Nov 12, 2026 — see README "Flight-model corrections"):
# the first fitted curve (CL_C1 = 1.8, CL_C2 = -3.25) under-lifted at
# low spin ratio: a pure driver at 161 mph / 12 deg / 2,900 rpm carried
# only 248.5 yd against the 268 yd gapping target, while the irons
# (higher S) were already on target — so no global lift/drag change
# could fix the driver without overshooting the irons (a +10% lift
# slope alone pushes the 7-iron +4.7%). The refit steepens the low-S
# rise and rolls off earlier (peak Cl ~0.32 at S ~ 0.27, same peak as
# the published curve): driver pure carry 248.5 -> 269.1 yd, drawn
# 300-shot mean 240.4 -> 262.1 yd, ball speed unchanged (160.8 mph),
# and the 14-club gapping mean error improves 2.14% -> 1.80% (worst
# club besides the LW is the 5-wood at +4.3%).
# Drag spin coefficient: Cd = 0.24 + CD_SPIN_K * spin (spec §2.3 says
# 0.000012; fitted lower — see calibrate.py — because the spec's value
# makes pure iron shots sit at a drag maximum where any mishit that
# reduces spin flies further, which is backwards).
CL_C1 = 2.4
CL_C2 = -4.5
CD_SPIN_K = 0.000012


# ------------------------------------------------------------------ delivery --
@dataclass
class Delivery:
    club_speed_mph: float
    face_deg: float
    path_deg: float
    strike_x_mm: float
    strike_y_mm: float
    aoa_deg: float


def draw_delivery(rng: Rng, club: str, shot_type: str = "full",
                  form_sig_mult: float = 1.0, shape: str = "straight",
                  power: bool = False, lie: str = "fairway",
                  speed_fraction: float = 1.0) -> Delivery:
    """Draw club delivery from the per-club normal distributions (§3.2).

    ``speed_fraction`` scales the swing for partial shots (chip/pitch/
    knockdown/punch) — the club speed mean is multiplied by it.
    """
    spec = C.CLUBS[club]
    mod = C.SHOT_TYPE_MODIFIERS[shot_type]
    lie_sig = C.LIE_EFFECTS[lie]["sig"]
    sig_mult = mod["sig"] * form_sig_mult * lie_sig
    if power:
        sig_mult *= 1.25
    speed_mean = spec["speed_mean"] * speed_fraction * (1.04 if power else 1.0)
    # The clamp bounds scale with the intended speed: a fixed 60 mph floor
    # destroys partial shots (a 44-yd pitch wants a ~28 mph swing and was
    # being clamped up to 60, carrying 80 yd instead of 44).
    lo = max(10.0, speed_mean * 0.75)
    hi = min(135.0, speed_mean * 1.25)
    speed = rng.gauss_clamped(speed_mean, spec["sig_speed"], lo, hi)
    face = C.SHAPE_FACE_BIAS[shape] + rng.gauss(0.0, spec["sig_face"] * sig_mult)
    path = rng.gauss(0.0, spec["sig_path"] * sig_mult)
    # Lie shifts the strike low on the face: heavy rough chunks it, light
    # rough and fairway bunkers thin it (§2.4 rate multipliers).
    strike_y_shift = {"rough_heavy": -3.0, "rough_light": -1.5,
                      "bunker_fairway": -2.0}.get(lie, 0.0)
    sx = rng.gauss(0.0, spec["sig_sx"])
    sy = rng.gauss(strike_y_shift, spec["sig_sy"])
    if club == "driver":
        aoa = rng.gauss(3.0, 1.0)
    elif spec["cls"] in ("fairway", "hybrid"):
        aoa = rng.gauss(1.0, 1.0)
    else:
        aoa = rng.gauss(-4.0, 1.0)
    return Delivery(speed, face, path, sx, sy, aoa)


def classify_contact(d: Delivery, rng: Rng) -> str:
    """Contact quality from strike location (§2.4).

    Order: shank > chunk > toe/heel > thin > pure. A strike below -12 mm
    is a chunk 65% of the time (heavy contact) and a thin the rest.
    """
    if d.strike_x_mm < -14:
        return "shank"
    if d.strike_y_mm <= -12:
        return "chunk" if rng.random() < 0.65 else "thin"
    if d.strike_x_mm > 8:
        return "toe"
    if d.strike_x_mm < -8:
        return "heel"
    if d.strike_y_mm < -8:
        return "thin"
    return "pure"


# -------------------------------------------------------------------- launch --
@dataclass
class Launch:
    ball_speed_mph: float
    launch_deg: float
    spin_rpm: float
    spin_axis_deg: float
    start_dir_deg: float
    club_speed_mph: float
    quality: str


def delivery_to_launch(d: Delivery, club: str, quality: str, lie: str,
                       wind_into_mph: float = 0.0, rng: Rng | None = None) -> Launch:
    """Convert delivery to launch conditions (§2.2)."""
    spec = C.CLUBS[club]
    smash = C.SMASH_BY_QUALITY[spec["cls"]][quality]
    ball_speed = d.club_speed_mph * smash
    # Lie distance factor: distance ~ v^2, so scale speed by sqrt(factor).
    ball_speed *= math.sqrt(C.LIE_EFFECTS[lie]["dist"])

    # Launch: per-club base angle (C.LAUNCH_DEG) plus the drawn AoA's
    # deviation from the club's typical AoA. See constants.py for why the
    # spec's loft x 0.72 formula was replaced (it cannot fit driver and
    # wedges simultaneously).
    typical_aoa = {"driver": 3.0, "3-wood": 1.0, "5-wood": 1.0,
                   "hybrid": 0.0}.get(club, -4.0)
    if club == "driver":
        aoa_effect = (d.aoa_deg - typical_aoa) * 0.5
    else:
        aoa_effect = (d.aoa_deg - typical_aoa) * 0.25
    if quality == "thin":
        strike_effect = -2.0
    elif quality == "chunk":
        strike_effect = 1.5
    elif d.strike_y_mm > 6:
        strike_effect = 1.0
    else:
        strike_effect = 0.0
    launch_deg = C.LAUNCH_DEG[club] + aoa_effect + strike_effect

    spin = spec["base_spin"] * C.SPIN_FACTOR_BY_QUALITY[quality]
    lie_spin = C.LIE_EFFECTS[lie]["spin"]
    if lie_spin is None:  # rough_light: flyer or grabber, 50/50 (§2.2)
        flyer = rng.random() < 0.5 if rng is not None else \
            (abs(d.strike_x_mm * 7.13 + d.strike_y_mm * 3.71) % 1.0) < 0.5
        spin *= 0.70 if flyer else 1.15
    else:
        spin *= lie_spin
    if wind_into_mph >= 8:  # ballooning into the wind (§4.3)
        spin *= 1.15

    gear_deg = d.strike_x_mm * 0.55  # gear effect (§2.4)
    spin_axis = (d.face_deg - d.path_deg) * 0.9 + gear_deg
    spin_axis = max(-15.0, min(15.0, spin_axis))
    start_dir = d.face_deg * 0.75 + d.path_deg * 0.25
    return Launch(ball_speed, launch_deg, spin, spin_axis, start_dir,
                  d.club_speed_mph, quality)


def air_density(temp_f: float) -> float:
    """kg/m^3, adjusted for temperature and Wyatt National's altitude (§2.3)."""
    t_kelvin = (temp_f - 32.0) * 5.0 / 9.0 + 273.15
    return C.RHO_SEA_LEVEL * (288.15 / t_kelvin) * C.ALTITUDE_FACTOR


# -------------------------------------------------------------------- flight --
@dataclass
class FlightResult:
    """Outputs of one (or a batch of) ball flight(s)."""
    carry_yd: np.ndarray        # along-target distance at first ground contact
    total_yd: np.ndarray        # carry + bounce + roll, along target line
    curve_ft: np.ndarray        # lateral displacement during flight (+ = right)
    offline_ft: np.ndarray      # final lateral error from the target line
    apex_ft: np.ndarray         # max height above the landing elevation
    flight_time_s: np.ndarray
    # Bounce-end state (shot frame, metres) — the engine applies roll with
    # the correct surface after determining where the ball actually landed.
    bounce_x_m: np.ndarray
    bounce_z_m: np.ndarray
    hvel_x_ms: np.ndarray
    hvel_z_ms: np.ndarray
    trajectory: list = field(default_factory=list)  # sampled (x,y,z) m, N=1 only


def _spin_vector(spin_rpm: np.ndarray, spin_axis_deg: np.ndarray):
    """Spin vector in the flight frame.

    Pure backspin (axis 0) points along +z (lateral); omega x v then points
    up (lift). A positive axis tilts omega toward -y, which puts the
    Magnus force toward +z — a fade, curving to the golfer's right (§2.3).
    """
    omega_mag = np.asarray(spin_rpm, dtype=float) * 2.0 * math.pi / 60.0
    phi = np.radians(np.asarray(spin_axis_deg, dtype=float))
    wx = np.zeros_like(omega_mag)
    wy = -omega_mag * np.sin(phi)
    wz = omega_mag * np.cos(phi)
    return np.stack([wx, wy, wz], axis=-1)


def _fly_scalar(ball_speed_mph, launch_deg, spin_rpm, spin_axis_deg,
                start_dir_deg, wind_along_ms=0.0, wind_lateral_ms=0.0,
                ground_elev_m=0.0, temp_f=62.0, firmness=0.6,
                record_trajectory=False) -> "FlightResult":
    """Single-ball flight integration with plain floats (speed).

    Identical formulas and step order to the vector path in :func:`fly`
    — same semi-implicit Euler at 100 Hz, same drag/Magnus/bounce
    model — but scalar ``math`` instead of numpy. The vector path costs
    ~25 numpy calls per step; for one ball that overhead dwarfs the
    arithmetic (~130 ms per flight vs ~3 ms here), and the engine's
    per-shot path is always n == 1. Results agree with the vector path
    to within float rounding; the carry bands in the tests are yards
    wide, so this is far inside tolerance.
    """
    v0 = float(ball_speed_mph) * C.MPH_TO_MS
    launch = math.radians(float(launch_deg))
    start = math.radians(float(start_dir_deg))
    spin = float(spin_rpm)
    phi = math.radians(float(spin_axis_deg))
    rho = air_density(temp_f)
    cd = 0.24 + CD_SPIN_K * spin
    omega_mag = spin * 2.0 * math.pi / 60.0
    # Spin vector: pure backspin (axis 0) points along +z; a positive
    # axis tilts it toward -y. (Same as _spin_vector for one ball.)
    ox, oy, oz = 0.0, -omega_mag * math.sin(phi), omega_mag * math.cos(phi)
    om_norm = math.sqrt(oy * oy + oz * oz)
    ohx, ohy, ohz = 0.0, oy / max(om_norm, 1e-9), oz / max(om_norm, 1e-9)
    radius_m = C.BALL_DIAMETER_M / 2.0
    wx, wz = float(wind_along_ms), float(wind_lateral_ms)
    px, py, pz = 0.0, 0.0, 0.0
    vx = v0 * math.cos(launch) * math.cos(start)
    vy = v0 * math.sin(launch)
    vz = v0 * math.cos(launch) * math.sin(start)
    apex = 0.0
    carry = math.nan
    first_contact_done = False
    done = False
    bounce_count = 0
    restitution = 0.35 * firmness + 0.15
    dt = C.DT
    traj: list = []
    t = 0.0
    max_steps = int(C.MAX_FLIGHT_TIME_S / dt)
    for step in range(max_steps):
        vrx, vry, vrz = vx - wx, vy, vz - wz
        speed_rel = math.sqrt(vrx * vrx + vry * vry + vrz * vrz)
        speed_rel = max(speed_rel, 1e-9)
        hx, hy, hz = vrx / speed_rel, vry / speed_rel, vrz / speed_rel
        drag_k = -0.5 * rho * cd * C.BALL_AREA_M2 * speed_rel
        # Magnus direction: omega_hat x v_rel_hat.
        mx = ohy * hz - ohz * hy
        my = ohz * hx - ohx * hz
        mz = ohx * hy - ohy * hx
        spin_ratio = omega_mag * radius_m / speed_rel
        cl = min(0.35, max(0.02, CL_C2 * spin_ratio ** 2
                           + CL_C1 * spin_ratio))
        mag_k = 0.5 * rho * cl * C.BALL_AREA_M2 * speed_rel ** 2
        ax = (drag_k * vrx + mag_k * mx) / C.BALL_MASS_KG
        ay = (drag_k * vry + mag_k * my) / C.BALL_MASS_KG - C.GRAVITY
        az = (drag_k * vrz + mag_k * mz) / C.BALL_MASS_KG
        if done:
            ax = ay = az = 0.0
            vx = vy = vz = 0.0
        vx += ax * dt
        vy += ay * dt
        vz += az * dt
        px += vx * dt
        py += vy * dt
        pz += vz * dt
        t += dt
        apex = max(apex, py - ground_elev_m)
        if record_trajectory and step % 5 == 0:
            traj.append((px, py, pz))
        if (not first_contact_done) and py <= ground_elev_m and vy < 0:
            carry = px
            first_contact_done = True
        if (not done) and py <= ground_elev_m and vy < 0:
            if abs(vy) < 1.0:
                vx = vy = vz = 0.0
                done = True
                py = ground_elev_m
            else:
                spin_f = min(1.0, spin / 9000.0)
                e_i = restitution * (1.0 - 0.35 * spin_f)
                retain = (0.72 if bounce_count == 0 else 0.85) \
                    * (1.0 - 0.55 * spin_f)
                vy = -vy * e_i
                vx *= retain
                vz *= retain
                bounce_count += 1
                py = ground_elev_m
        if done:
            break
    if math.isnan(carry):
        carry = px
    return FlightResult(
        carry_yd=np.array([carry * C.M_TO_YARD]),
        total_yd=np.array([px * C.M_TO_YARD]),
        curve_ft=np.array([pz / C.FT_TO_M]),
        offline_ft=np.array([pz / C.FT_TO_M]),
        apex_ft=np.array([apex / C.FT_TO_M]),
        flight_time_s=np.array([t]),
        bounce_x_m=np.array([px]),
        bounce_z_m=np.array([pz]),
        hvel_x_ms=np.array([vx]),
        hvel_z_ms=np.array([vz]),
        trajectory=traj,
    )


def fly(ball_speed_mph, launch_deg, spin_rpm, spin_axis_deg, start_dir_deg,
        wind_along_ms=0.0, wind_lateral_ms=0.0, ground_elev_m=0.0,
        temp_f=62.0, firmness=0.6, record_trajectory=False):
    """Integrate ball flight at 100 Hz, semi-implicit Euler (§2.3).

    All launch arguments may be scalars or numpy arrays of the same length
    (the Monte Carlo path passes arrays). Returns a FlightResult.
    """
    v0 = np.asarray(ball_speed_mph, dtype=float) * C.MPH_TO_MS
    launch = np.radians(np.asarray(launch_deg, dtype=float))
    start = np.radians(np.asarray(start_dir_deg, dtype=float))
    spin = np.asarray(spin_rpm, dtype=float)
    n = v0.size if v0.ndim else 1
    if n == 1:
        # Single ball: the scalar path (same formulas, plain floats).
        return _fly_scalar(ball_speed_mph, launch_deg, spin_rpm,
                           spin_axis_deg, start_dir_deg, wind_along_ms,
                           wind_lateral_ms, ground_elev_m, temp_f,
                           firmness, record_trajectory)
    v0 = np.atleast_1d(v0)
    launch = np.atleast_1d(launch)
    start = np.atleast_1d(start)
    spin = np.atleast_1d(spin)

    rho = air_density(temp_f)
    # Drag coefficient, per the spec (§2.3). Column vector so it broadcasts
    # correctly against the (n, 3) velocity arrays in the Monte Carlo path.
    cd = (0.24 + CD_SPIN_K * spin)[:, None]
    # Lift coefficient: CORRECTION to §2.3. The spec's linear formula
    # (Cl = spin / 145000, clamped 0.02-0.35) gives Cl = 0.02 at driver spin
    # — about one tenth of the lift a real ball produces — and simulation
    # shows no launch angle can then reach the spec's own §3.1 carry
    # targets (driver maxes out at ~228 yd). The replacement is the
    # published spin-ratio model (Smits & Smith): Cl is a quadratic in the
    # dimensionless spin ratio S = omega * R / |v|, peaking near S = 0.3
    # and falling off at very high spin, which is also what keeps wedge
    # shots from floating forever. S is recomputed every step because the
    # ball slows in flight. The coefficients are module constants so the
    # calibration harness can refit them (see sim/calibrate.py).
    omega = _spin_vector(spin, spin_axis_deg)
    omega_mag = np.linalg.norm(omega, axis=1, keepdims=True)
    ball_radius_m = C.BALL_DIAMETER_M / 2.0
    wind = np.array([float(wind_along_ms), 0.0, float(wind_lateral_ms)])

    p = np.zeros((n, 3))
    v = np.column_stack([
        v0 * np.cos(launch) * np.cos(start),
        v0 * np.sin(launch),
        v0 * np.cos(launch) * np.sin(start),
    ])
    apex = np.zeros(n)
    carry = np.full(n, np.nan)
    first_contact_done = np.zeros(n, dtype=bool)
    done = np.zeros(n, dtype=bool)   # balls that have transitioned to roll
    bounce_count = np.zeros(n, dtype=int)
    restitution = 0.35 * firmness + 0.15
    dt = C.DT
    traj = []
    t = 0.0
    max_steps = int(C.MAX_FLIGHT_TIME_S / dt)
    for step in range(max_steps):
        v_rel = v - wind
        speed_rel = np.linalg.norm(v_rel, axis=1, keepdims=True)
        speed_rel = np.maximum(speed_rel, 1e-9)
        v_rel_hat = v_rel / speed_rel
        omega_hat = omega / np.maximum(
            np.linalg.norm(omega, axis=1, keepdims=True), 1e-9)
        drag = (-0.5 * rho * cd * C.BALL_AREA_M2 * speed_rel * v_rel)
        magnus_dir = np.cross(omega_hat, v_rel_hat)
        # Lift from the spin ratio at the current speed (see note above).
        # speed_rel is already (n, 1); it broadcasts against (n, 3) directly.
        spin_ratio = omega_mag * ball_radius_m / speed_rel
        cl = np.clip(CL_C2 * spin_ratio ** 2 + CL_C1 * spin_ratio,
                     0.02, 0.35)
        magnus = (0.5 * rho * cl * C.BALL_AREA_M2 * speed_rel ** 2) * magnus_dir
        a = (drag + magnus) / C.BALL_MASS_KG
        a[:, 1] -= C.GRAVITY
        a[done] = 0.0               # finished balls stay frozen
        v[done] = 0.0
        v = v + a * dt
        p = p + v * dt
        t += dt
        apex = np.maximum(apex, p[:, 1] - ground_elev_m)
        if record_trajectory and n == 1 and step % 5 == 0:
            traj.append(tuple(p[0]))
        # Ground contact.
        hit = (~first_contact_done) & (p[:, 1] <= ground_elev_m) & (v[:, 1] < 0)
        if np.any(hit):
            carry[hit] = p[hit, 0]
            first_contact_done[hit] = True
        contact = (~done) & (p[:, 1] <= ground_elev_m) & (v[:, 1] < 0)
        if np.any(contact):
            idx = np.where(contact)[0]
            for i in idx:
                if abs(v[i, 1]) < 1.0:
                    # Roll transition: stop integrating this ball.
                    v[i, :] = 0.0
                    done[i] = True
                    p[i, 1] = ground_elev_m
                else:
                    # Backspin grips the turf: a high-spin wedge checks up
                    # instead of bounding 25+ yd forward. The spec's flat
                    # 0.72/0.85 horizontal retain let a wedge bounce clean
                    # off the back of the green (GIR 0/18 in testing).
                    # Both the restitution and the horizontal retain fall
                    # as spin rises; a driver (2,900 rpm) is barely
                    # affected, a wedge (8,500+ rpm) checks hard.
                    spin_f = min(1.0, spin[i] / 9000.0)
                    e_i = restitution * (1.0 - 0.35 * spin_f)
                    retain = (0.72 if bounce_count[i] == 0 else 0.85) \
                        * (1.0 - 0.55 * spin_f)
                    v[i, 1] = -v[i, 1] * e_i
                    v[i, 0] *= retain
                    v[i, 2] *= retain
                    bounce_count[i] += 1
                    p[i, 1] = ground_elev_m
        if np.all(done):
            break
    # Any ball still airborne at the time cap: treat its current position
    # as the landing point (should not happen for golf shots).
    carry = np.where(np.isnan(carry), p[:, 0], carry)
    curve_ft = p[:, 2] / C.FT_TO_M
    return FlightResult(
        carry_yd=carry * C.M_TO_YARD,
        total_yd=p[:, 0] * C.M_TO_YARD,  # roll is added by the engine
        curve_ft=curve_ft,
        offline_ft=p[:, 2] / C.FT_TO_M,
        apex_ft=apex / C.FT_TO_M,
        flight_time_s=np.full(n, t),
        bounce_x_m=p[:, 0].copy(),
        bounce_z_m=p[:, 2].copy(),
        hvel_x_ms=v[:, 0].copy(),
        hvel_z_ms=v[:, 2].copy(),
        trajectory=traj,
    )


def apply_roll(bounce_x_m, bounce_z_m, hvel_x_ms, hvel_z_ms, mu,
               spin_rpm=None, on_green=False, spin_factor=1.0):
    """Analytic roll after the bounce phase (§2.5).

    ``mu`` is the roll friction of the surface the ball actually landed on.
    Backspin > 5,000 rpm on a green checks the ball (roll < 3 yd);
    backspin < 3,000 rpm releases (roll 5-12 yd). ``spin_factor`` scales
    the effective spin on the green — firm greens hold less, so the ball
    releases further (conditions.py).
    Returns (final_x_m, final_z_m, roll_yd) — scalars or arrays.
    """
    vh = np.hypot(hvel_x_ms, hvel_z_ms)
    roll_m = np.where(vh > 0.3, vh ** 2 / (2.0 * C.GRAVITY * mu), 0.0)
    if spin_rpm is not None:
        spin = np.asarray(spin_rpm, dtype=float) * spin_factor
        # on_green may be a scalar (single shot) or an array (MC batch).
        on_g = np.broadcast_to(np.asarray(on_green, dtype=bool),
                               np.shape(roll_m))
        roll_m = np.where(on_g & (spin > 5000),
                          np.minimum(roll_m, 3.0 / C.M_TO_YARD), roll_m)
        roll_m = np.where(on_g & (spin < 3000),
                          np.clip(roll_m, 5.0 / C.M_TO_YARD, 12.0 / C.M_TO_YARD),
                          roll_m)
    direction = np.where(vh > 1e-9, 1.0, 0.0)
    ux = np.where(vh > 1e-9, hvel_x_ms / np.maximum(vh, 1e-9), 0.0)
    uz = np.where(vh > 1e-9, hvel_z_ms / np.maximum(vh, 1e-9), 0.0)
    final_x = np.asarray(bounce_x_m, dtype=float) + roll_m * ux * direction
    final_z = np.asarray(bounce_z_m, dtype=float) + roll_m * uz * direction
    return final_x, final_z, roll_m * C.M_TO_YARD


def fly_shot(launch: Launch, wind_along_ms=0.0, wind_lateral_ms=0.0,
             ground_elev_m=0.0, temp_f=62.0, firmness=0.6,
             record_trajectory=False) -> FlightResult:
    """Scalar convenience wrapper around :func:`fly` for a single shot."""
    return fly(launch.ball_speed_mph, launch.launch_deg, launch.spin_rpm,
               launch.spin_axis_deg, launch.start_dir_deg,
               wind_along_ms, wind_lateral_ms, ground_elev_m,
               temp_f, firmness, record_trajectory)
