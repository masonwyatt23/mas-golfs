"""The local on-device decision engine (spec §5).

A compact, deterministic procedure — not a neural network, not an API call:
golf rules + a Monte Carlo expected-strokes evaluator over the true physics
(§2). Fully explainable, runs locally, costs nothing.

Performance note (honest): the spec's <5 ms per decision budget assumes a
compiled implementation. In this Python reference implementation a full
Monte Carlo decision (N=120, ~8 candidates) takes ~0.1-0.3 s. The physics
is identical; only the wall-clock differs. ``fast_mode`` skips the Monte
Carlo for the calibration harness (§3.7), where 10,000 rounds must run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import constants as C
from .conditions import green_spin_factor, roll_mu
from .course import Course, Hole
from .physics import (Delivery, Launch, apply_roll, classify_contact,
                      delivery_to_launch, draw_delivery, fly)
from .rng import Rng
from .strokes_gained import baseline_strokes

CLUB_ORDER = ["driver", "3-wood", "5-wood", "hybrid", "4-iron", "5-iron",
              "6-iron", "7-iron", "8-iron", "9-iron", "PW", "GW", "SW", "LW"]


# ----------------------------------------------------------------- situation --
@dataclass
class Situation:
    hole: Hole
    ball_x: float
    ball_y: float
    lie: str
    distance_yd: float          # along-centreline distance to the pin
    distance_straight_yd: float
    elevation_ft: float         # to the target (+ = uphill)
    wind_mph: float             # hole wind speed
    wind_effect: str            # into / down / cross_left / ... / calm
    wind_along_mph: float       # + = helping (downwind), hole frame
    wind_lateral_mph: float     # + = pushes ball to the golfer's right
    hazard: str = ""
    pin_x: float = 0.0
    pin_y: float = 0.0
    blocked_by_trees: bool = False
    hole_no: int = 1
    holes_left: int = 18
    strokes_vs_59_pace: float = 0.0
    temp_f: float = 62.0
    firmness: float = 0.6
    green_speed: float = 11.0


@dataclass
class Candidate:
    shot_type: str
    club: str
    intended_carry_yd: float
    aim_offset_ft: float
    intended_shape: str
    intended_traj: str
    target_x: float
    target_y: float
    speed_fraction: float = 1.0
    power: bool = False
    reasoning: str = ""
    ev_strokes: float = 0.0
    risk: float = 0.0
    confidence: float = 0.7


# -------------------------------------------------------------------- gating --
def allowed_shot_types(lie: str, blocked_by_trees: bool = False) -> list:
    """Shot availability by lie (§4.1). Enforced in code, not suggested."""
    table = {
        "tee": ["full", "knockdown", "draw", "fade", "layup"],
        "fairway": ["full", "knockdown", "draw", "fade", "layup",
                    "pitch", "chip"] + (["punch"] if blocked_by_trees else []),
        "rough_light": ["full", "knockdown", "draw", "fade", "layup",
                        "pitch", "chip"],
        "rough_heavy": ["full", "knockdown", "layup", "punch", "pitch", "chip"],
        "bunker_fairway": ["full", "knockdown", "layup"],
        "bunker_green": ["bunker_splash", "bunker_pick"],
        "trees": ["punch", "layup", "full"],
        "fringe": ["chip", "pitch", "putt"],
        "green": ["putt"],
    }
    return table.get(lie, ["full"])


def wind_effect_string(along_mph: float, lateral_mph: float) -> str:
    """Hole wind effect label (§1.2)."""
    into = along_mph < -3
    down = along_mph > 3
    left = lateral_mph < -5
    right = lateral_mph > 5
    if into and left:
        return "into_and_left"
    if into and right:
        return "into_and_right"
    if down and left:
        return "down_and_left"
    if down and right:
        return "down_and_right"
    if into:
        return "into"
    if down:
        return "down"
    if left:
        return "cross_left"
    if right:
        return "cross_right"
    return "calm"


def resolve_hole_wind(round_wind_mph: float, wind_from_deg: float,
                      hole_azimuth_deg: float, rng: Rng):
    """Round wind + hole azimuth -> (along_mph, lateral_mph, effect) (§1.4)."""
    gust = rng.gauss(1.0, 0.12)
    mph = round_wind_mph * gust
    to_deg = math.radians(wind_from_deg + 180.0 - hole_azimuth_deg)
    along = mph * math.cos(to_deg)     # + = helping
    lateral = mph * math.sin(to_deg)   # + = pushes ball to golfer's right
    return along, lateral, wind_effect_string(along, lateral)


def wind_in_shot_frame(hole: Hole, ball_x: float, ball_y: float,
                       aim_ang: float, wind_along_mph: float,
                       wind_lateral_mph: float):
    """Rotate hole-frame wind into the shot frame (m/s).

    The wind is stored relative to the hole's centreline direction at the
    ball; the shot frame is rotated by the angle between centreline and
    aim line. Returns (wind_along_ms, wind_lateral_ms).
    """
    s_ball, _ = hole.project(ball_x, ball_y)
    pts = hole.centreline_points()
    seg_ang = math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0])
    if len(pts) > 2:
        s1 = math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        if s_ball > s1:
            seg_ang = math.atan2(pts[2][1] - pts[1][1], pts[2][0] - pts[1][0])
    diff = aim_ang - seg_ang
    along_ms = wind_along_mph * C.MPH_TO_MS
    lat_ms = wind_lateral_mph * C.MPH_TO_MS
    w_along = along_ms * math.cos(diff) + lat_ms * math.sin(diff)
    w_lat = -along_ms * math.sin(diff) + lat_ms * math.cos(diff)
    return w_along, w_lat


# --------------------------------------------------------- club selection ----
def effective_distance(sit: Situation) -> float:
    """Distance adjusted for wind, elevation, and lie (§4.3)."""
    d = sit.distance_yd
    into = max(0.0, -sit.wind_along_mph)
    down = max(0.0, sit.wind_along_mph)
    d *= (1.0 + 0.010 * into) * (1.0 - 0.008 * down)
    d += sit.elevation_ft * 0.8
    if sit.lie == "rough_heavy":
        d += 25.0  # club up 2-3 (§4.2)
    elif sit.lie == "rough_light":
        d += 8.0
    return max(5.0, d)


def choose_club(eff_dist_yd: float, prefer_long: bool = True) -> str:
    """Club whose gapping carry is closest to the required carry (§5.6)."""
    best, best_score = None, float("inf")
    for club in CLUB_ORDER:
        carry = C.CLUBS[club]["carry"]
        score = abs(carry - eff_dist_yd)
        if prefer_long and carry < eff_dist_yd:
            score += 4.0     # on approaches, slightly long beats short
        if not prefer_long and carry > eff_dist_yd:
            score += 4.0     # on tee shots into trouble, slightly short
        if score < best_score:
            best, best_score = club, score
    return best


def _club_idx(club: str) -> int:
    return CLUB_ORDER.index(club)


def _neighbour_club(club: str, delta: int) -> str:
    i = min(len(CLUB_ORDER) - 1, max(0, _club_idx(club) + delta))
    return CLUB_ORDER[i]


def _aim_point(sit: Situation, aim_offset_ft: float):
    """Target point: pin shifted laterally by aim_offset_ft (+ = right)."""
    dx = sit.pin_x - sit.ball_x
    dy = sit.pin_y - sit.ball_y
    dist = math.hypot(dx, dy) or 1.0
    # Right of the line of play, in hole coords: (dy, -dx)/dist is one
    # perpendicular; the golfer's right is the normal the course module
    # uses, (-dy, dx)/dist for a line heading (dx, dy). We use that normal.
    nx, ny = -dy / dist, dx / dist
    off_yd = aim_offset_ft / 3.0
    return sit.pin_x + nx * off_yd, sit.pin_y + ny * off_yd


def _reasoning(sit: Situation, cand: Candidate) -> str:
    into = -sit.wind_along_mph
    if sit.lie == "trees":
        return "No line to the green — punch it low back to the fairway and live to fight."
    if sit.lie == "bunker_green":
        return "Open the face, splash the sand, let it float out soft."
    if cand.shot_type == "knockdown" and into >= 8:
        return (f"Uphill into a {into:.0f} mph wind — club up one, knock it "
                "down, and let the wind bring it back.")
    if cand.shot_type == "layup":
        return "The smart play is the lay-up — a full wedge in beats a hero shot from the junk."
    if sit.wind_effect.startswith("down") and sit.wind_along_mph >= 8:
        return "Downwind — take the full ball, ride it, and let it run out."
    if cand.shot_type in ("draw", "fade"):
        return (f"Working a {cand.shot_type} around the trouble — shape it "
                "in and let the wind hold it.")
    if sit.elevation_ft >= 10:
        return "Uphill — take the extra club and swing smooth."
    if sit.distance_yd <= 100:
        return "Wedge in hand — a controlled swing at the fat of the green."
    return "Full shot at the pin — trust the number and commit."


def generate_candidates(sit: Situation, golfer) -> list:
    """All (shot_type, club) pairs the §4 gate allows (§5.2 step 1)."""
    allowed = allowed_shot_types(sit.lie, sit.blocked_by_trees)
    cands = []
    eff = effective_distance(sit)
    into = max(0.0, -sit.wind_along_mph)
    down = max(0.0, sit.wind_along_mph)
    cross = abs(sit.wind_lateral_mph)

    # Aim offset for crosswind (§4.3): wind_mph x carry_yd x 0.011 feet.
    # Aim INTO the wind: a wind pushing the ball right (lateral +) needs an
    # aim to the left (negative offset).
    aim_off = 0.0
    if cross >= 10:
        aim_off = -sit.wind_lateral_mph * sit.distance_yd * 0.011
    # Golfer-model aim bias (§6.4) for the distance bucket.
    aim_off += golfer.aim_bias_for(sit.distance_yd, sit.lie)
    # Firm/fast days: safer targets — aim at the fat of the green, not the
    # pin. Firm greens don't hold, fast greens punish the short side.
    if sit.firmness >= 0.70 or sit.green_speed >= 12.0:
        aim_off *= 0.5

    def add(shot_type, club, carry, shape="straight", traj="normal",
            frac=1.0, power=False, aim=None):
        tx, ty = _aim_point(sit, aim if aim is not None else aim_off)
        c = Candidate(shot_type, club, carry, aim_off, shape, traj,
                      tx, ty, frac, power)
        c.reasoning = _reasoning(sit, c)
        cands.append(c)

    if sit.lie == "green":
        return [Candidate("putt", "putter", 0, 0, "straight", "normal",
                          sit.pin_x, sit.pin_y)]
    if sit.lie == "bunker_green":
        for club in ("SW", "LW"):
            add("bunker_splash", club, sit.distance_yd,
                frac=min(1.0, max(0.3, sit.distance_yd / C.CLUBS[club]["carry"])))
        add("bunker_pick", "SW", sit.distance_yd,
            frac=min(1.0, max(0.3, sit.distance_yd / C.CLUBS["SW"]["carry"])))
        return cands
    if sit.lie == "trees":
        # The hero shot through a gap (§4.4) is deliberately not generated
        # in v1.0: the gate requires a >= 15 ft gap and < 150 yd carry over
        # trouble, and the course data does not model gap widths yet.
        for club in ("7-iron", "8-iron"):
            add("punch", club, min(150.0, sit.distance_yd * 0.65),
                traj="low", frac=0.7)
        add("layup", "8-iron", 120.0, frac=0.8)
        return cands
    if sit.lie == "fringe":
        add("putt", "putter", 0)
        add("chip", "PW", sit.distance_yd,
            frac=min(1.0, max(0.25, sit.distance_yd / C.CLUBS["PW"]["carry"])))
        add("pitch", "SW", sit.distance_yd,
            frac=min(1.0, max(0.25, sit.distance_yd / C.CLUBS["SW"]["carry"])))
        return cands

    # Full swings: tee, fairway, rough, fairway bunker.
    # On approaches (any non-tee shot) prefer slightly long (§5.6).
    club = choose_club(eff, prefer_long=(sit.lie != "tee"))
    # Short game: inside 100 yd the candidates are pitch/chip, not full irons.
    if sit.distance_yd <= 100 and sit.lie != "tee":
        for c in ("GW", "SW", "LW"):
            add("pitch", c, sit.distance_yd,
                frac=min(1.0, max(0.25, sit.distance_yd / C.CLUBS[c]["carry"])))
        add("chip", "8-iron", sit.distance_yd, frac=0.5)
        return cands

    if "full" in allowed:
        # Into a strong wind the full high ball is a decision error (§4.3).
        if not (into >= 15 and sit.distance_yd > 150):
            add("full", club, C.CLUBS[club]["carry"],
                power=(sit.lie == "tee" and sit.hole.par == 5
                       and sit.distance_yd > 500))
            add("full", _neighbour_club(club, -1),
                C.CLUBS[_neighbour_club(club, -1)]["carry"])
    if "knockdown" in allowed and into >= 8:
        kd_club = _neighbour_club(club, 1)  # club up one (§4.3)
        add("knockdown", kd_club, C.CLUBS[kd_club]["carry"] * 0.92,
            traj="low", frac=0.92)
    if "knockdown" in allowed and into < 8 and down < 8:
        add("knockdown", _neighbour_club(club, 1),
            C.CLUBS[_neighbour_club(club, 1)]["carry"] * 0.92,
            traj="low", frac=0.92)
    if "draw" in allowed and "fade" in allowed:
        shape = "fade" if sit.wind_lateral_mph < 0 else "draw"
        add(shape, club, C.CLUBS[club]["carry"], shape=shape)
    if "layup" in allowed and (sit.distance_yd > 240 or sit.hazard):
        layup_carry = 200.0 if sit.hole.par == 5 else 150.0
        layup_club = choose_club(layup_carry)
        add("layup", layup_club, layup_carry,
            frac=min(1.0, layup_carry / C.CLUBS[layup_club]["carry"]))
    return cands


# ------------------------------------------------------- Monte Carlo ( §5.4) --
def _draw_delivery_batch(rng: Rng, club: str, cand: Candidate, n: int,
                         form_sig_mult: float, lie: str):
    """Draw N deliveries as numpy arrays (§3.2)."""
    spec = C.CLUBS[club]
    mod = C.SHOT_TYPE_MODIFIERS[cand.shot_type]
    lie_sig = C.LIE_EFFECTS[lie]["sig"]
    sig_mult = mod["sig"] * form_sig_mult * lie_sig
    if cand.power:
        sig_mult *= 1.25
    speed_mean = spec["speed_mean"] * cand.speed_fraction * (1.04 if cand.power else 1.0)
    speeds = np.array([rng.gauss_clamped(speed_mean, spec["sig_speed"], 60, 135)
                       for _ in range(n)])
    faces = np.array([C.SHAPE_FACE_BIAS[cand.intended_shape] +
                      rng.gauss(0, spec["sig_face"] * sig_mult) for _ in range(n)])
    paths = np.array([rng.gauss(0, spec["sig_path"] * sig_mult) for _ in range(n)])
    shift = {"rough_heavy": -3.0, "rough_light": -1.5,
             "bunker_fairway": -2.0}.get(lie, 0.0)
    sxs = np.array([rng.gauss(0, spec["sig_sx"]) for _ in range(n)])
    sys = np.array([rng.gauss(shift, spec["sig_sy"]) for _ in range(n)])
    if club == "driver":
        aoas = np.array([rng.gauss(3.0, 1.0) for _ in range(n)])
    elif spec["cls"] in ("fairway", "hybrid"):
        aoas = np.array([rng.gauss(1.0, 1.0) for _ in range(n)])
    else:
        aoas = np.array([rng.gauss(-4.0, 1.0) for _ in range(n)])
    return speeds, faces, paths, sxs, sys, aoas


def _classify_batch(sxs, sys, rng: Rng):
    """Vectorized contact classification (§2.4)."""
    n = len(sxs)
    quality = np.full(n, "pure", dtype=object)
    chunk_roll = np.array([rng.random() for _ in range(n)])
    quality = np.where(sxs < -14, "shank", quality)
    quality = np.where((sys <= -12) & (quality == "pure"),
                       np.where(chunk_roll < 0.65, "chunk", "thin"), quality)
    quality = np.where((sxs > 8) & (quality == "pure"), "toe", quality)
    quality = np.where((sxs < -8) & (quality == "pure"), "heel", quality)
    quality = np.where((sys < -8) & (quality == "pure"), "thin", quality)
    return quality


def _launch_batch(speeds, faces, paths, sxs, sys, aoas, qualities, club, lie,
                  wind_into_mph, rng: Rng):
    """Vectorized delivery -> launch (§2.2)."""
    spec = C.CLUBS[club]
    smash_map = C.SMASH_BY_QUALITY[spec["cls"]]
    smash = np.array([smash_map[q] for q in qualities])
    spin_map = C.SPIN_FACTOR_BY_QUALITY
    spin_f = np.array([spin_map[q] for q in qualities])
    ball_speed = speeds * smash * math.sqrt(C.LIE_EFFECTS[lie]["dist"])
    # Launch: per-club base angle plus the drawn AoA's deviation from the
    # club's typical AoA — mirrors physics.delivery_to_launch exactly.
    typical_aoa = {"driver": 3.0, "3-wood": 1.0, "5-wood": 1.0,
                   "hybrid": 0.0}.get(club, -4.0)
    if club == "driver":
        aoa_effect = (aoas - typical_aoa) * 0.5
    else:
        aoa_effect = (aoas - typical_aoa) * 0.25
    strike_effect = np.zeros(len(speeds))
    strike_effect = np.where(qualities == "thin", -2.0, strike_effect)
    strike_effect = np.where(qualities == "chunk", 1.5, strike_effect)
    strike_effect = np.where((sys > 6) & (qualities == "pure"), 1.0, strike_effect)
    launch_deg = C.LAUNCH_DEG[club] + aoa_effect + strike_effect
    spin = spec["base_spin"] * spin_f
    lie_spin = C.LIE_EFFECTS[lie]["spin"]
    if lie_spin is None:
        flyer = np.array([rng.random() < 0.5 for _ in range(len(speeds))])
        spin = np.where(flyer, spin * 0.70, spin * 1.15)
    else:
        spin = spin * lie_spin
    if wind_into_mph >= 8:
        spin = spin * 1.15
    gear = sxs * 0.55
    spin_axis = np.clip((faces - paths) * 0.9 + gear, -15.0, 15.0)
    start_dir = faces * 0.75 + paths * 0.25
    return ball_speed, launch_deg, spin, spin_axis, start_dir


def evaluate_candidate(course: Course, sit: Situation, cand: Candidate,
                       rng: Rng, n: int, form_sig_mult: float,
                       adjustments: dict | None = None):
    """Monte Carlo: N shots through the §2 pipeline -> (EV, risk) (§5.2)."""
    speeds, faces, paths, sxs, sys, aoas = _draw_delivery_batch(
        rng, cand.club, cand, n, form_sig_mult, sit.lie)
    qualities = _classify_batch(sxs, sys, rng)
    wind_into = max(0.0, -sit.wind_along_mph)
    ball_speed, launch_deg, spin, spin_axis, start_dir = _launch_batch(
        speeds, faces, paths, sxs, sys, aoas, qualities, cand.club,
        sit.lie, wind_into, rng)

    # Aim direction in hole coords; wind rotated into the shot frame.
    dx = cand.target_x - sit.ball_x
    dy = cand.target_y - sit.ball_y
    aim_ang = math.atan2(dy, dx)
    w_along, w_lat = wind_in_shot_frame(
        sit.hole, sit.ball_x, sit.ball_y, aim_ang,
        sit.wind_along_mph, sit.wind_lateral_mph)
    ground_elev_m = sit.elevation_ft * C.FT_TO_M
    result = fly(ball_speed, launch_deg, spin, spin_axis, start_dir,
                 w_along, w_lat, ground_elev_m, sit.temp_f, sit.firmness)

    # Bounce-end positions -> hole coords -> surface -> roll.
    bx = sit.ball_x + result.bounce_x_m * C.M_TO_YARD * math.cos(aim_ang) \
        - result.bounce_z_m * C.M_TO_YARD * math.sin(aim_ang)
    by = sit.ball_y + result.bounce_x_m * C.M_TO_YARD * math.sin(aim_ang) \
        + result.bounce_z_m * C.M_TO_YARD * math.cos(aim_ang)
    lies_b, _, _ = course.determine_lie_batch(sit.hole, bx, by)
    mu = np.array([roll_mu(l, sit.firmness, sit.green_speed) for l in lies_b])
    on_green = lies_b == "green"
    fx, fz, _ = apply_roll(result.bounce_x_m, result.bounce_z_m,
                           result.hvel_x_ms, result.hvel_z_ms, mu, spin,
                           on_green=on_green,
                           spin_factor=green_spin_factor(sit.firmness))
    fx_yd = sit.ball_x + fx * C.M_TO_YARD * math.cos(aim_ang) \
        - fz * C.M_TO_YARD * math.sin(aim_ang)
    fy_yd = sit.ball_y + fx * C.M_TO_YARD * math.sin(aim_ang) \
        + fz * C.M_TO_YARD * math.cos(aim_ang)
    lies, in_water, ob = course.determine_lie_batch(sit.hole, fx_yd, fy_yd)

    # Strokes to hole out from each outcome (§5.5).
    dist_pin_yd = np.hypot(sit.pin_x - fx_yd, sit.pin_y - fy_yd)
    dist_pin_ft = dist_pin_yd * 3.0
    ev = np.zeros(n)
    penalty = np.zeros(n)
    for i in range(n):
        if in_water[i]:
            penalty[i] = 1
            dz_x, dz_y = sit.hole.point_at(*sit.hole.drop_zone)
            d_yd = math.hypot(sit.pin_x - dz_x, sit.pin_y - dz_y)
            ev[i] = 1 + 1 + baseline_strokes("fairway", d_yd, 0, adjustments)
        elif ob[i]:
            penalty[i] = 1
            # Stroke and distance: replay from the previous position.
            ev[i] = 1 + 1 + baseline_strokes(sit.lie, sit.distance_yd, 0,
                                            adjustments)
        else:
            ev[i] = 1 + baseline_strokes(lies[i], dist_pin_yd[i],
                                         dist_pin_ft[i], adjustments)
    # Wind carry adjustments (§4.3): full ball into the wind balloons.
    if cand.shot_type == "full" and wind_into >= 8:
        ev = ev + 0.08
    risk = float(np.mean((penalty > 0) | (lies == "trees") |
                         ((lies == "bunker_green") &
                          (cand.shot_type not in ("bunker_splash", "bunker_pick")))))
    return float(np.mean(ev)), risk


def fast_ev(course: Course, sit: Situation, cand: Candidate,
            adjustments: dict | None = None) -> tuple:
    """Rule-based EV without Monte Carlo (calibration fast path).

    Evaluates the candidate at its *intended* outcome with nominal
    proximity error from the §3.3 truth table. Used only by the
    calibration harness; the broadcast always uses the Monte Carlo.
    """
    # Intended landing: the target point, with nominal miss by distance.
    prox_ft = {50: 10.0, 100: 14.0, 150: 22.5, 200: 35.5, 250: 41.5}
    d = sit.distance_yd
    prox = float(np.interp(d, [50, 100, 150, 200, 250],
                           [10.0, 14.0, 22.5, 35.5, 41.5]))
    if sit.lie == "rough_light":
        prox *= 1.25
    elif sit.lie == "rough_heavy":
        prox *= 1.45
    elif sit.lie == "bunker_fairway":
        prox *= 1.35
    if cand.shot_type in ("draw", "fade"):
        prox *= 1.10
    elif cand.shot_type == "knockdown":
        prox *= 0.85
    if sit.lie in ("bunker_green",):
        ev = 1 + baseline_strokes("green", 0, prox, adjustments)
        return ev, 0.05
    if sit.distance_yd <= 100 and cand.shot_type in ("pitch", "chip"):
        ev = 1 + baseline_strokes("green", 0, prox, adjustments)
        return ev, 0.03
    # Intended outcome is on the green at `prox` feet from the pin.
    ev = 1 + baseline_strokes("green", 0, prox, adjustments)
    risk = 0.10 if sit.hazard else 0.05
    if sit.lie == "rough_heavy":
        risk += 0.08
    if sit.lie == "trees":
        risk = 0.05  # punch-out is safe by design
    return ev, risk


# ------------------------------------------------------------- risk rule -----
def risk_threshold(sit: Situation, within_record: bool) -> float:
    """§5.3 risk rule. A hero shot must be worth 0.15 strokes to be taken."""
    if sit.holes_left <= 3 and within_record:
        return 0.08   # record in reach: get aggressive
    if sit.holes_left <= 6 and sit.strokes_vs_59_pace <= -4:
        return 0.25   # pressing for the comeback
    return 0.15


def select_decision(candidates, risk_limit: float):
    """Rank by EV, apply the risk rule (§5.3). Returns (chosen, rejected)."""
    ranked = sorted(candidates, key=lambda c: c.ev_strokes)
    best = ranked[0]
    safe = [c for c in ranked if c.risk <= 0.15]
    chosen = best
    if safe:
        safe_best = min(safe, key=lambda c: c.ev_strokes)
        if safe_best.ev_strokes - best.ev_strokes <= risk_limit:
            chosen = safe_best
    rejected = [c for c in ranked if c is not chosen][:2]
    return chosen, rejected


def decide(course: Course, sit: Situation, golfer, rng: Rng,
           mc_n: int = 120, fast_mode: bool = False):
    """Full decision procedure (§5.2). Returns (chosen, rejected)."""
    cands = generate_candidates(sit, golfer)
    form_mult = C.FORM_SIG_MULT[golfer.form]
    for cand in cands:
        if fast_mode:
            cand.ev_strokes, cand.risk = fast_ev(course, sit, cand,
                                                 golfer.baseline_adjustments)
        else:
            cand.ev_strokes, cand.risk = evaluate_candidate(
                course, sit, cand, rng, mc_n, form_mult,
                golfer.baseline_adjustments)
    within_record = sit.strokes_vs_59_pace >= -2
    limit = risk_threshold(sit, within_record)
    # Conditions move the risk dial: firm/fast days play safer, soft/slow
    # days let him press. (Conditions engine: firm >= 0.70, fast >= 12 ft.)
    if sit.firmness >= 0.70 or sit.green_speed >= 12.0:
        limit -= 0.03
    elif sit.firmness < 0.45 and sit.green_speed < 10.5:
        limit += 0.02
    limit += golfer.risk_threshold_delta
    chosen, rejected = select_decision(cands, limit)
    # Confidence: high when one option dominates on EV (§1.2).
    ranked = sorted(cands, key=lambda c: c.ev_strokes)
    gap = (ranked[1].ev_strokes - ranked[0].ev_strokes) if len(ranked) > 1 else 0.5
    chosen.confidence = min(0.98, max(0.05, 1.0 - gap / 0.5))
    chosen.ev_strokes = chosen.ev_strokes
    return chosen, rejected
