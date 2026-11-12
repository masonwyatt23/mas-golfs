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
                  power: bool = False, lie: str = "fairway") -> Delivery:
    """Draw club delivery from the per-club normal distributions (§3.2)."""
    spec = C.CLUBS[club]
    mod = C.SHOT_TYPE_MODIFIERS[shot_type]
    lie_sig = C.LIE_EFFECTS[lie]["sig"]
    sig_mult = mod["sig"] * form_sig_mult * lie_sig
    if power:
        sig_mult *= 1.25
    speed_mean = spec["speed_mean"] * (1.04 if power else 1.0)
    speed = rng.gauss_clamped(speed_mean, spec["sig_speed"], 60.0, 135.0)
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

    if club == "driver":
        aoa_effect = d.aoa_deg * 0.5
    else:
        aoa_effect = d.aoa_deg * 0.25
    if quality == "thin":
        strike_effect = -2.0
    elif quality == "chunk":
        strike_effect = 1.5
    elif d.strike_y_mm > 6:
        strike_effect = 1.0
    else:
        strike_effect = 0.0
    launch_deg = spec["loft"] * 0.72 + aoa_effect + strike_effect

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
    v0 = np.atleast_1d(v0)
    launch = np.atleast_1d(launch)
    start = np.atleast_1d(start)
    spin = np.atleast_1d(spin)

    rho = air_density(temp_f)
    cd = 0.24 + 0.000012 * spin
    cl = np.clip(spin / 145000.0, 0.02, 0.35)
    omega = _spin_vector(spin, spin_axis_deg)
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
        magnus = (0.5 * rho * cl * C.BALL_AREA_M2 * speed_rel ** 2)[:, None] * magnus_dir
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
                    retain = 0.72 if bounce_count[i] == 0 else 0.85
                    v[i, 1] = -v[i, 1] * restitution
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
               spin_rpm=None, on_green=False):
    """Analytic roll after the bounce phase (§2.5).

    ``mu`` is the roll friction of the surface the ball actually landed on.
    Backspin > 5,000 rpm on a green checks the ball (roll < 3 yd);
    backspin < 3,000 rpm releases (roll 5-12 yd).
    Returns (final_x_m, final_z_m, roll_yd) — scalars or arrays.
    """
    vh = np.hypot(hvel_x_ms, hvel_z_ms)
    roll_m = np.where(vh > 0.3, vh ** 2 / (2.0 * C.GRAVITY * mu), 0.0)
    if on_green and spin_rpm is not None:
        spin = np.asarray(spin_rpm, dtype=float)
        roll_m = np.where(spin > 5000, np.minimum(roll_m, 3.0 / C.M_TO_YARD), roll_m)
        roll_m = np.where(spin < 3000,
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
