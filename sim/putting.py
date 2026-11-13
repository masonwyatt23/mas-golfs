"""Putting model (spec §3.5) + putting v2 solver (putting-model-v2.md).

v1 — No launch conditions: a make-probability + distance-control model
(``make_probability``, ``draw_break``, ``putt``). The table is the
calibrated contract; it does not move.

v2 — The green is real. ``sim.greens.Green`` carries one heightfield per
hole; the solver below integrates every putt over that field, so the path
is a real integration, not a drawn curve, and it is guaranteed consistent
with the outcome the table drew (outcome first, path second — §1.3).
Break is measured from the integrated path, never drawn (§1.4).

INTEGRATION POINTS (how this plugs into the engine — nothing below is
wired in yet; each bullet is a one-spot change in the named file):
1. ``Green`` plugs into the hole: ``engine._play_hole`` builds
   ``green = green_for_hole(hole_no, hole.green_radius_ft)`` once per
   hole (future: a ``green: Green`` field on ``Hole`` in
   ``sim/course.py`` — not added here, course.py is owned by another
   agent right now). ``hole_start`` gains ``"green": green.payload()``
   so the broadcast renders from the same array the ball rolls on.
2. ``putt_read`` (before the stroke): the engine converts the ball and
   pin to green-local feet (``greens.to_green_local``), calls
   ``build_putt_read`` — which runs ``predicted_path`` from the ideal
   line *before* the outcome is drawn, so the preview can never leak
   the result — and emits ``"putt_read"`` alongside the putt decision.
   ``predicted_path`` takes no RNG: it cannot advance the PRNG state
   and cannot change the outcome draw.
3. ``putt()`` (v1, unchanged) still draws the outcome — made/leave/
   pace — from the calibrated table. It is the contract; the solver
   conditions the path on it, it never replaces it.
4. After the outcome, the engine calls ``build_putt_result`` with the
   ``putt()`` result dict. That solves the actual path, measures the
   break from it, classifies the lip, and returns the extended
   ``putt_result`` putt dict (§2.3). The ball is then moved to the
   integrated path's endpoint (converted back with
   ``greens.from_green_local``) instead of the straight-line roll-out
   the engine does today.
5. ``bus/translate.py`` passes ``putt_read`` and the extended
   ``putt_result`` through to the broadcast envelope unchanged.
6. ``ROLL_MU_STIMP11`` below is an ESTIMATE (0.05, from the Stimpmeter
   energy argument in §1.5), not a fitted constant. The fit procedure
   (§1.5) belongs in ``sim/constants.py`` with the fitted value, the
   way the flight-model corrections are recorded in ``sim/README.md``
   — that move happens at integration time, when the harness can run
   the fit. Until then, do not quote 0.05 as measured.
"""

from __future__ import annotations

import math

import numpy as np

from . import constants as C
from .greens import GRID_FT, Green
from .rng import Rng


def make_probability(distance_ft: float, break_ft: float,
                     green_speed: float) -> float:
    """P(make) for Mas, interpolated from the §3.5 table."""
    dist = np.clip(distance_ft, C.PUTT_MAKE_DIST_FT[0], C.PUTT_MAKE_DIST_FT[-1])
    p = float(np.interp(dist, C.PUTT_MAKE_DIST_FT, C.PUTT_MAKE_PCT))
    if distance_ft > 10:
        p *= (11.0 / green_speed) ** 0.5   # faster greens harder from distance
    if break_ft > 2:
        p *= (1.0 - 0.04 * break_ft)        # big break costs makes
    return min(0.995, max(0.001, p))


def draw_break(rng: Rng, distance_ft: float):
    """Break in feet and direction for a putt of this length."""
    break_ft = float(rng.triangular(0.0, max(0.5, distance_ft * 0.15),
                                    distance_ft * 0.05))
    if break_ft < 0.3:
        return 0.0, "straight"
    return break_ft, rng.choice(["left_to_right", "right_to_left"])


def putt(rng: Rng, distance_ft: float, green_speed: float = 11.0,
         form_putt_mult: float = 1.0) -> dict:
    """Simulate one putt. Returns made / leave_ft / speed / break info."""
    break_ft, break_dir = draw_break(rng, distance_ft)
    p_make = make_probability(distance_ft, break_ft, green_speed)
    # Spec §3.6 (design doc §4.5): the form multiplier applies only to
    # putts over 10 ft — a cold putter still makes a 3-footer.
    if distance_ft > 10:
        p_make *= form_putt_mult
    p_make = min(0.995, p_make)
    made = rng.random() < p_make
    if made:
        return dict(made=True, leave_ft=0.0, speed="good",
                    break_ft=break_ft, break_dir=break_dir,
                    distance_ft=distance_ft)
    # Missed: pace draw. 12% of putts over 20 ft run long, 8% come up short.
    roll = rng.random()
    if distance_ft > 20 and roll < 0.12:
        speed = "long"
        leave = distance_ft * rng.gauss(0.18, 0.06)
        leave = min(10.0, max(2.0, leave))
    elif roll < 0.20:
        speed = "short"
        leave = distance_ft * rng.gauss(0.15, 0.05)
        leave = min(6.0, max(0.5, leave))
    else:
        speed = "good"
        leave = distance_ft * rng.gauss(0.08, 0.05)
        leave = min(6.0, max(0.5, leave))
    return dict(made=False, leave_ft=leave, speed=speed,
                break_ft=break_ft, break_dir=break_dir,
                distance_ft=distance_ft)


# --------------------------------------------------------------------------
# Putting v2 — the solver (putting-model-v2.md §§1-2).
#
# The solver is deterministic: no RNG anywhere. The outcome is drawn by
# ``putt()`` (the calibrated table); the solver conditions the path on
# that outcome. The predicted path is computed from the ideal line alone,
# before the outcome draw, so it can never leak the result.
# --------------------------------------------------------------------------

G_FT_S2 = 32.174          # gravity, ft/s^2
HOLE_RADIUS_IN = 2.125    # regulation cup radius (spec §2.4)
BALL_RADIUS_IN = 0.84     # regulation ball radius (spec §2.4)
HOLE_RADIUS_FT = HOLE_RADIUS_IN / 12.0
LIP_IN = 3.0              # closest approach < 3 in: on the lip (§2.4)
BURNED_EDGE_IN = 6.0      # 3-6 in: burned the edge (§2.4)
CAPTURE_SPEED_FT_S = 5.0  # ball drops if it reaches the cup slower than this
STOP_SPEED_FT_S = 0.05    # ball is at rest below this speed
PUTT_DT = 0.05            # integration step, seconds (putt speeds are low)
PUTT_MAX_T = 30.0         # safety cap on roll time
MAX_PATH_POINTS = 60      # event paths: one point per foot, capped (§2.2)

# Rolling-friction coefficient at stimp 11 — ESTIMATE, not fitted (see the
# module docstring). A Stimpmeter releases at 1.83 m/s (6.0 ft/s) and the
# ball rolls ~11 ft on a stimp-11 green: a = v^2 / 2d = 6.0^2 / 22 = 1.64
# ft/s^2, so mu = a / g = 1.64 / 32.174 = 0.051. Faster greens roll
# further on the same pace, so mu scales as 11.0 / green_speed (§1.5).
ROLL_MU_STIMP11 = 0.05

# How much the pin's difficulty moves the putt_read make % (see
# build_putt_read): make_pct *= 1 - PIN_READ_WEIGHT * (difficulty - 0.5).
# ESTIMATE — a display/read judgment, not a calibrated table change.
PIN_READ_WEIGHT = 0.20


def roll_mu(green_speed: float) -> float:
    """Rolling-friction coefficient for a green speed (stimp)."""
    return ROLL_MU_STIMP11 * (11.0 / max(6.0, green_speed))


def nominal_pace_v0(distance_ft: float, green_speed: float,
                    extra_ft: float = 1.5) -> float:
    """Initial speed (ft/s) for a Tour-pace putt: dies ~18 in past the hole.

    Energy to travel ``distance + extra`` on a flat green at this stimp:
    v0 = sqrt(2 * mu * g * d). The solver searches around this pace.
    """
    mu = roll_mu(green_speed)
    return math.sqrt(2.0 * mu * G_FT_S2 * max(1.0, distance_ft + extra_ft))


def _bilinear(H, half_ft: float, x, y):
    """Vectorized bilinear interpolation on a height array (feet).

    ``H`` is indexed [row=y, col=x]; ``x``/``y`` are arrays (or scalars)
    in green-local feet. Points outside the grid clamp to the edge.
    """
    n = H.shape[0]
    gx = np.clip((np.asarray(x, dtype=float) + half_ft) / GRID_FT,
                 0.0, n - 1.001)
    gy = np.clip((np.asarray(y, dtype=float) + half_ft) / GRID_FT,
                 0.0, n - 1.001)
    ix = gx.astype(int)
    iy = gy.astype(int)
    fx = gx - ix
    fy = gy - iy
    ix1 = np.minimum(ix + 1, n - 1)
    iy1 = np.minimum(iy + 1, n - 1)
    return (H[iy, ix] * (1 - fx) * (1 - fy)
            + H[iy, ix1] * fx * (1 - fy)
            + H[iy1, ix] * (1 - fx) * fy
            + H[iy1, ix1] * fx * fy)


def _roll_batch_pin(green: Green, pin_ft, starts, dirs_rad, v0s,
                    green_speed: float):
    """Vectorized roll integration for K putts at one pin.

    ``starts``: (K, 2) ball positions, green-local ft. ``dirs_rad``: (K,)
    start directions (radians, green-local frame). ``v0s``: (K,) initial
    speeds in ft/s. ``pin_ft``: (x, y) cup position, green-local ft.

    Returns a dict with per-candidate results:
    - ``paths``: list of (n_i, 2) arrays, the dense integrated path.
      For a captured putt the path continues past the cup (the
      counterfactual roll — see ``past_hole_ft``); the event path is
      truncated at ``capture_idx`` by the caller.
    - ``captured``: (K,) bool — the ball dropped.
    - ``capture_idx``: (K,) int — step index of the capture (-1 if none).
    - ``capture_vel``: (K,) float — ball speed (ft/s) at the capture.
    - ``closest_in``: (K,) float — closest approach to the cup centre,
      inches, measured point-to-segment (so a 6-inch integration step
      cannot jump over the cup).
    - ``pace_at_closest``: (K,) float — ball speed (ft/s) at the closest
      approach.
    - ``stop_dist_ft``: (K,) float — distance from the final rest point
      to the cup.
    """
    H = green.heightfield().astype(float) / 304.8  # feet
    half_ft = green.half_ft
    # Precompute the gradient arrays once: bilinear interpolation of the
    # gradient is two array lookups per step, not four height lookups.
    gy_arr, gx_arr = np.gradient(H, GRID_FT, GRID_FT)
    mu = roll_mu(green_speed)
    pin = np.asarray(pin_ft, dtype=float)
    starts = np.asarray(starts, dtype=float)
    dirs = np.asarray(dirs_rad, dtype=float)
    v0s = np.asarray(v0s, dtype=float)
    k = starts.shape[0]

    pos = starts.copy()
    vel = np.stack([np.cos(dirs), np.sin(dirs)], axis=1) * v0s[:, None]
    speed = np.linalg.norm(vel, axis=1)
    alive = speed > STOP_SPEED_FT_S
    captured = np.zeros(k, dtype=bool)
    capture_idx = np.full(k, -1, dtype=int)
    capture_vel = np.zeros(k)
    closest = np.full(k, np.inf)
    pace_at_closest = np.zeros(k)
    stop_idx = np.full(k, -1, dtype=int)

    paths = [pos.copy()]
    max_steps = int(PUTT_MAX_T / PUTT_DT)
    for step in range(1, max_steps + 1):
        if not alive.any():
            break
        prev = pos.copy()
        prev_speed = speed.copy()
        prev_vel = vel.copy()
        gx = _bilinear(gx_arr, half_ft, pos[:, 0], pos[:, 1])
        gy = _bilinear(gy_arr, half_ft, pos[:, 0], pos[:, 1])
        # Gravity pulls downhill: a = -g * grad(h). Friction opposes motion.
        ax = -G_FT_S2 * gx
        ay = -G_FT_S2 * gy
        moving = speed > 1e-9
        ax = ax - np.where(moving, mu * G_FT_S2 * vel[:, 0]
                           / np.maximum(speed, 1e-9), 0.0)
        ay = ay - np.where(moving, mu * G_FT_S2 * vel[:, 1]
                           / np.maximum(speed, 1e-9), 0.0)
        vel = vel + np.stack([ax, ay], axis=1) * PUTT_DT
        # A ball at rest stays at rest. There is no static-friction term
        # in the per-step acceleration (friction only opposes motion), so
        # without this a ball that dies on a slope would be re-accelerated
        # downhill by gravity on the next step and roll back 20 ft — a
        # real golf ball does not do that (the grass holds it), and the
        # broadcast ends the putt when the ball stops. Freeze a candidate
        # the moment its speed reaches zero or its velocity reverses
        # (it stopped mid-step), and never integrate it again.
        new_speed = np.linalg.norm(vel, axis=1)
        dot = np.einsum("ij,ij->i", vel, prev_vel)
        stopped = (new_speed <= STOP_SPEED_FT_S) | \
            ((prev_speed > 0) & (dot < 0.0))
        vel = np.where(stopped[:, None], 0.0, vel)
        pos = pos + vel * PUTT_DT
        speed = np.linalg.norm(vel, axis=1)

        # Closest approach to the cup, point-to-segment on this step.
        ab = pos - prev
        ab2 = np.einsum("ij,ij->i", ab, ab)
        t = np.where(ab2 > 1e-12,
                     np.einsum("ij,ij->i", pin - prev, ab)
                     / np.maximum(ab2, 1e-12), 0.0)
        t = np.clip(t, 0.0, 1.0)
        seg_pt = prev + t[:, None] * ab
        d = np.linalg.norm(pin - seg_pt, axis=1)
        better = d < closest
        closest = np.where(better, d, closest)
        pace_at_closest = np.where(better, prev_speed, pace_at_closest)

        # Capture: inside the cup's radius at a droppable pace.
        hit = (d < HOLE_RADIUS_FT) & (prev_speed < CAPTURE_SPEED_FT_S) \
            & (~captured) & alive
        if hit.any():
            captured = captured | hit
            capture_idx = np.where(hit & (capture_idx < 0), step, capture_idx)
            capture_vel = np.where(hit, prev_speed, capture_vel)
        # Freeze at rest, off the field, or after the time cap.
        off = (np.abs(pos[:, 0]) > half_ft + 2.0) | \
              (np.abs(pos[:, 1]) > half_ft + 2.0)
        alive = alive & (speed > STOP_SPEED_FT_S) & (~off)
        paths.append(pos.copy())
        newly_stopped = (~alive) & (stop_idx < 0)
        stop_idx = np.where(newly_stopped, step, stop_idx)
    stop_idx = np.where(stop_idx < 0, len(paths) - 1, stop_idx)

    out_paths = []
    for i in range(k):
        out_paths.append(np.asarray(paths)[:stop_idx[i] + 1, i, :])
    return {
        "paths": out_paths,
        "captured": captured,
        "capture_idx": capture_idx,
        "capture_vel": capture_vel,
        "closest_in": closest * 12.0,
        "pace_at_closest": pace_at_closest,
        "stop_dist_ft": np.linalg.norm(
            np.asarray([p[-1] for p in out_paths]) - pin, axis=1),
    }


def roll_putt(green: Green, ball_ft, pin_ft, start_deg: float,
              v0_ft_s: float, green_speed: float) -> dict:
    """Integrate one putt over the green (single-putt wrapper).

    ``start_deg`` is the start direction in green-local degrees (0 deg
    is +X, toward the fairway). Returns the path and the measurements
    the solver needs: captured, closest approach, pace at the hole, and
    the stop point. The path continues past the cup when captured (the
    counterfactual roll); callers truncate it at ``capture_idx``.
    """
    res = _roll_batch_pin(
        green, pin_ft,
        np.asarray([ball_ft], dtype=float),
        np.asarray([math.radians(start_deg)]),
        np.asarray([v0_ft_s], dtype=float), green_speed)
    path = res["paths"][0]
    return {
        "path": [(float(x), float(y)) for x, y in path],
        "captured": bool(res["captured"][0]),
        "capture_idx": int(res["capture_idx"][0]),
        "closest_in": float(res["closest_in"][0]),
        "pace_at_closest": float(res["pace_at_closest"][0]),
        "stop_dist_ft": float(res["stop_dist_ft"][0]),
    }


def _straight_dir(ball_ft, pin_ft) -> float:
    """Direction (radians, green-local) of the straight ball-to-hole line."""
    return math.atan2(pin_ft[1] - ball_ft[1], pin_ft[0] - ball_ft[0])


def to_putt_frame(path, ball_ft, pin_ft):
    """Dense path -> putt frame: origin at the ball, +x toward the pin.

    +y is the golfer's left (the putt direction rotated +90 deg). A path
    that bows toward +y therefore breaks left-to-right. Returns a list
    of (x, y) in feet.
    """
    phi = _straight_dir(ball_ft, pin_ft)
    c, s = math.cos(-phi), math.sin(-phi)
    out = []
    for x, y in path:
        dx, dy = x - ball_ft[0], y - ball_ft[1]
        out.append((dx * c - dy * s, dx * s + dy * c))
    return out


def _closest_index(path, pin_ft) -> int:
    """Index of the path point closest to the pin."""
    best, best_d = 0, float("inf")
    for i, (x, y) in enumerate(path):
        d = (x - pin_ft[0]) ** 2 + (y - pin_ft[1]) ** 2
        if d < best_d:
            best, best_d = i, d
    return best


def measure_break(path, ball_ft, pin_ft):
    """Break measured from an integrated path (spec §1.4 — never drawn).

    ``break_ft`` is the maximum lateral deviation of the path from the
    straight ball-to-hole line, in feet, measured on the approach — the
    path up to its closest approach to the cup. The roll-out past the
    cup keeps curving and is not part of the break; measuring over the
    whole path would inflate it (on a 3% cross-slope, a 15-footer's
    roll-out adds ~2 ft of phantom break). ``break_dir`` is
    ``"left_to_right"`` when the path bows toward the golfer's left
    (the ball starts left of the line and curves right, toward the
    cup), ``"right_to_left"`` when it bows toward the golfer's right,
    and ``"straight"`` when the deviation stays under 0.3 ft.
    """
    if not path:
        return 0.0, "straight"
    approach = path[:_closest_index(path, pin_ft) + 1]
    framed = to_putt_frame(approach, ball_ft, pin_ft)
    if not framed:
        return 0.0, "straight"
    lat = [y for _, y in framed]
    i = max(range(len(lat)), key=lambda j: abs(lat[j]))
    dev = lat[i]
    if dev > 0.3:
        return abs(dev), "left_to_right"
    if dev < -0.3:
        return abs(dev), "right_to_left"
    return 0.0, "straight"


def classify_miss(closest_in: float):
    """Lip classification from the measured closest approach (§2.4).

    The ball's edge touches the cup's edge when the centres are
    ~3 in apart (hole radius 2.125 in + ball radius 0.84 in). Returns
    ``(lip, edge_class)``: ``lip`` is True only for the < 3 in case;
    ``edge_class`` is ``"lip"``, ``"burned_edge"`` (3-6 in), or
    ``"missed"`` (> 6 in).
    """
    if closest_in < LIP_IN:
        return True, "lip"
    if closest_in < BURNED_EDGE_IN:
        return False, "burned_edge"
    return False, "missed"


def sample_path(path, max_points: int = MAX_PATH_POINTS):
    """Downsample a dense path to one point per foot of arc length.

    Always keeps the first and last points; capped at ``max_points``
    (the event budget, §2.2). Returns a list of [x, y] in feet.
    """
    if len(path) <= 1:
        return [[round(float(x), 2), round(float(y), 2)] for x, y in path]
    pts = [(float(x), float(y)) for x, y in path]
    total = 0.0
    for i in range(1, len(pts)):
        total += math.hypot(pts[i][0] - pts[i - 1][0],
                            pts[i][1] - pts[i - 1][1])
    if total <= 0.0:
        return [[round(pts[0][0], 2), round(pts[0][1], 2)]]
    interval = max(1.0, total / max(1, max_points - 1))
    out = [pts[0]]
    acc = 0.0
    for i in range(1, len(pts)):
        acc += math.hypot(pts[i][0] - pts[i - 1][0],
                          pts[i][1] - pts[i - 1][1])
        if acc >= interval:
            out.append(pts[i])
            acc = 0.0
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return [[round(x, 2), round(y, 2)] for x, y in out]


def _past_hole_ft(path, ball_ft, pin_ft, capture_idx: int) -> float:
    """How far past the hole the ball would have rolled (§2.3).

    For a made putt, the arc length of the counterfactual roll from the
    capture point to the stop. For a miss, the arc length from the first
    step past the cup to the stop — 0.0 when the ball died short.
    """
    if capture_idx >= 0:
        seg = path[capture_idx:]
    else:
        phi = _straight_dir(ball_ft, pin_ft)
        ux, uy = math.cos(phi), math.sin(phi)
        cross = None
        for i, (x, y) in enumerate(path):
            if (x - pin_ft[0]) * ux + (y - pin_ft[1]) * uy > 0:
                cross = i
                break
        if cross is None:
            return 0.0
        seg = path[cross:]
    total = 0.0
    for i in range(1, len(seg)):
        total += math.hypot(seg[i][0] - seg[i - 1][0],
                            seg[i][1] - seg[i - 1][1])
    return total


def ideal_start_line(green: Green, ball_ft, pin_ft,
                     green_speed: float) -> dict:
    """The ideal start line: the line the preview shows (§2.1).

    Searches start lines in a ±10 deg cone around the straight ball-to-hole
    line and paces from 0.9x to 1.4x nominal — the pace has to be searched
    too, because nominal pace is computed on a flat green and an uphill
    putt (or one climbing a tier step) needs more than nominal to reach
    the cup at all. The wide cone matters on cross-slopes: a 15-footer
    on a 3% slope needs ~9 deg of aim, and a ±6 deg cone would force the
    preview onto a firm edge-of-cone line instead of the natural one.
    Picks the line that comes closest to the cup, penalising pace at the
    closest approach. Deterministic — no RNG, so it can run before the
    outcome draw without touching the PRNG state. Returns ``start_deg``
    (green-local degrees), the integrated path, and the closest approach.
    """
    dist_ft = math.hypot(pin_ft[0] - ball_ft[0], pin_ft[1] - ball_ft[1])
    v_nom = nominal_pace_v0(dist_ft, green_speed)
    phi0 = _straight_dir(ball_ft, pin_ft)
    deltas = np.arange(-10.0, 10.01, 0.5)
    fracs = [0.9, 1.0, 1.1, 1.25, 1.4, 1.55]
    dirs, v0s = [], []
    for d in deltas:
        for f in fracs:
            dirs.append(phi0 + math.radians(float(d)))
            v0s.append(v_nom * f)
    res = _roll_batch_pin(
        green, pin_ft,
        np.tile(np.asarray(ball_ft, dtype=float), (len(dirs), 1)),
        np.asarray(dirs), np.asarray(v0s), green_speed)
    score = res["closest_in"] + 2.0 * res["pace_at_closest"]
    best = int(np.argmin(score))
    return {
        "start_deg": math.degrees(dirs[best]),
        "path": [(float(x), float(y)) for x, y in res["paths"][best]],
        "closest_in": float(res["closest_in"][best]),
        "v0_ft_s": float(v0s[best]),
    }


def predicted_path(green: Green, ball_ft, pin_ft,
                   green_speed: float) -> dict:
    """The preview line: the ideal line, integrated before the outcome.

    This is the "should" line (§2.1). It takes the ideal start line and
    nominal pace and integrates it — nothing about the outcome is an
    input, so it can never leak the result. Deterministic, no RNG.
    Returns the path in putt frame (origin at the ball, +x toward the
    pin), the measured break, and the start line.
    """
    ideal = ideal_start_line(green, ball_ft, pin_ft, green_speed)
    path = ideal["path"]
    framed = to_putt_frame(path, ball_ft, pin_ft)
    break_ft, break_dir = measure_break(path, ball_ft, pin_ft)
    return {
        "path": sample_path(framed),
        "break_ft": break_ft,
        "break_dir": break_dir,
        "start_deg": ideal["start_deg"],
        "v0_ft_s": ideal["v0_ft_s"],
    }


def solve_actual_path(green: Green, ball_ft, pin_ft, made: bool,
                      leave_ft: float, pace: str,
                      green_speed: float) -> dict:
    """The outcome-conditioned solver (§1.3): the "did" line.

    Given the outcome the table drew, search start lines and paces around
    the ideal line until the integrated path is consistent with it:
    - made: the path must drop (capture inside the cup at a droppable
      pace). The search prefers the smallest deviation from the ideal
      line, then the pace closest to nominal.
    - missed: the path must stop ``leave_ft`` from the cup, with the
      drawn pace class (``long`` runs past, ``short`` dies early,
      ``good`` stops near the leave). The search minimises
      ``|stop_dist - leave_ft|`` plus a penalty when the geometry
      contradicts the pace class.
    Returns the path in putt frame (sampled, ≤60 points), the measured
    break, the pace at the hole, the past-hole roll, and the lip
    classification. ``solver_fallback`` is True only if no capturing
    line was found for a made putt — the path is still a real
    integration, but it is flagged so the harness can see it.
    """
    dist_ft = math.hypot(pin_ft[0] - ball_ft[0], pin_ft[1] - ball_ft[1])
    v_nom = nominal_pace_v0(dist_ft, green_speed)
    ideal = ideal_start_line(green, ball_ft, pin_ft, green_speed)
    phi_ideal = math.radians(ideal["start_deg"])
    ball = np.asarray(ball_ft, dtype=float)

    if made:
        # Search order: smallest |delta| from the ideal line, then pace
        # closest to nominal. First pass: ±3 deg, v0 0.85-1.15x nominal.
        # Second pass (only if the first finds nothing): ±8 deg, 0.7-1.6x
        # — the wide pace range is for uphill putts and tier climbs,
        # which need far more than nominal (a 14-footer climbing a
        # 12 in step needs ~1.45x nominal).
        for deltas, fracs in (
                (np.arange(-3.0, 3.01, 0.25),
                 [0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15]),
                (np.arange(-8.0, 8.01, 0.5),
                 [0.70, 0.85, 1.00, 1.15, 1.30, 1.45, 1.60])):
            dirs, v0s, meta = [], [], []
            for d in deltas:
                for f in fracs:
                    dirs.append(phi_ideal + math.radians(float(d)))
                    v0s.append(v_nom * f)
                    meta.append((abs(float(d)), abs(f - 1.0)))
            res = _roll_batch_pin(
                green, pin_ft, np.tile(ball, (len(dirs), 1)),
                np.asarray(dirs), np.asarray(v0s), green_speed)
            order = sorted(range(len(dirs)),
                           key=lambda i: (0 if res["captured"][i] else 1,
                                          meta[i][0], meta[i][1]))
            if res["captured"][order[0]]:
                i = order[0]
                return _solved(green, ball_ft, pin_ft, res, i, True,
                               dirs[i], v0s[i], green_speed)
        # No capturing line found: take the closest approach and flag it.
        res = _roll_batch_pin(
            green, pin_ft, np.tile(ball, (1, 1)),
            np.asarray([phi_ideal]), np.asarray([v_nom]), green_speed)
        out = _solved(green, ball_ft, pin_ft, res, 0, True,
                      phi_ideal, v_nom, green_speed)
        out["solver_fallback"] = True
        return out

    # Missed: search start lines and paces for the stop that matches the
    # drawn leave, with the drawn pace class. The pace range runs
    # 0.6-1.3x nominal in 0.05 steps: a "short" miss on a short putt
    # needs well under nominal (nominal pace is defined to roll 18 in
    # past the cup), a "long" miss needs over it, and the fine steps
    # matter — with 0.1 steps the stop distance is quantised in ~1 ft
    # jumps on a 20-footer, so no candidate can match a 3 ft leave.
    deltas = np.arange(-4.0, 4.01, 0.5)
    fracs = np.arange(0.60, 1.301, 0.05)
    dirs, v0s = [], []
    for d in deltas:
        for f in fracs:
            dirs.append(phi_ideal + math.radians(float(d)))
            v0s.append(v_nom * f)
    res = _roll_batch_pin(green, pin_ft, np.tile(ball, (len(dirs), 1)),
                          np.asarray(dirs), np.asarray(v0s), green_speed)
    phi0 = _straight_dir(ball_ft, pin_ft)
    ux, uy = math.cos(phi0), math.sin(phi0)
    best, best_score = None, None
    for i in range(len(dirs)):
        if res["captured"][i]:
            # A dropped ball is a made putt, never a miss: the solver
            # may not present a capturing line as the outcome of a
            # putt the table drew as missed, however close its stop
            # distance is to the drawn leave.
            continue
        stop = res["paths"][i][-1]
        past = (stop[0] - pin_ft[0]) * ux + (stop[1] - pin_ft[1]) * uy
        if pace == "long":
            pace_pen = 0.0 if past > 0 else 2.0
        elif pace == "short":
            pace_pen = 0.0 if past <= 0 else 2.0
        else:  # "good": either side, the leave is what matters
            pace_pen = 0.0
        score = (abs(float(res["stop_dist_ft"][i]) - leave_ft)
                 + pace_pen
                 + 0.1 * abs(math.degrees(dirs[i] - phi_ideal))
                 + 0.5 * abs(v0s[i] / v_nom - 1.0))
        if best_score is None or score < best_score:
            best, best_score = i, score
    if best is None:
        # Pathological (short flat putt): every line in the cone dropped.
        # Widen the cone AND slow the pace until a genuine miss appears —
        # a captured line must never be presented as a miss.
        wide = np.arange(-12.0, 12.01, 1.0)
        wide_fracs = [0.6, 0.8, 1.0]
        dirs2, v0s2 = [], []
        for d in wide:
            for f in wide_fracs:
                dirs2.append(phi_ideal + math.radians(float(d)))
                v0s2.append(v_nom * f)
        res2 = _roll_batch_pin(
            green, pin_ft, np.tile(ball, (len(dirs2), 1)),
            np.asarray(dirs2), np.asarray(v0s2), green_speed)
        for i in range(len(dirs2)):
            if res2["captured"][i]:
                continue
            stop = res2["paths"][i][-1]
            past = (stop[0] - pin_ft[0]) * ux + (stop[1] - pin_ft[1]) * uy
            pace_pen = 0.0
            if pace == "long" and past <= 0:
                pace_pen = 2.0
            elif pace == "short" and past > 0:
                pace_pen = 2.0
            score = (abs(float(res2["stop_dist_ft"][i]) - leave_ft)
                     + pace_pen + 0.1 * abs(float(
                         wide[i // len(wide_fracs)])))
            if best_score is None or score < best_score:
                best, best_score = i, score
                res, dirs, v0s = res2, dirs2, v0s2
        if best is None:
            # Still nothing (a tap-in on a flat green): take the widest
            # line and flag it — a real integration, but the harness
            # needs to see the fallback.
            best = len(dirs2) - 1
            res, dirs, v0s = res2, dirs2, v0s2
            out = _solved(green, ball_ft, pin_ft, res, best, False,
                          dirs[best], v0s[best], green_speed)
            out["solver_fallback"] = True
            return out
    return _solved(green, ball_ft, pin_ft, res, best, False,
                   dirs[best], v0s[best], green_speed)


def _solved(green, ball_ft, pin_ft, res, i, made, start_dir, v0,
            green_speed):
    """Package one solved candidate into the §2.3 result shape."""
    raw_path = [(float(x), float(y)) for x, y in res["paths"][i]]
    capture_idx = int(res["capture_idx"][i])
    if made and capture_idx >= 0:
        # The event path ends in the cup; the counterfactual roll past
        # the cup is measured, not drawn.
        event_path = raw_path[:capture_idx + 1]
        event_path[-1] = (float(pin_ft[0]), float(pin_ft[1]))
        past = _past_hole_ft(raw_path, ball_ft, pin_ft, capture_idx)
    else:
        event_path = raw_path
        past = _past_hole_ft(raw_path, ball_ft, pin_ft, -1)
    framed = to_putt_frame(event_path, ball_ft, pin_ft)
    break_ft, break_dir = measure_break(event_path, ball_ft, pin_ft)
    closest_in = float(res["closest_in"][i])
    lip, edge_class = classify_miss(closest_in)
    if made:
        lip, edge_class, closest_in = False, "made", 0.0
    return {
        "path": sample_path(framed),
        "break_ft": break_ft,
        "break_dir": break_dir,
        "pace_ft_s": float(res["pace_at_closest"][i]),
        "past_hole_ft": round(past, 1),
        "lip": lip,
        "closest_in": round(closest_in, 1),
        "edge_class": edge_class,
        "start_deg": round(math.degrees(start_dir), 2),
        "v0_ft_s": round(float(v0), 2),
        "solver_fallback": False,
    }


def build_putt_read(green: Green, ball_ft, pin_ft, distance_ft: float,
                    green_speed: float, form_putt_mult: float = 1.0,
                    is_comebacker: bool = False,
                    pin_difficulty: float | None = None) -> dict:
    """The ``putt_read`` putt dict (§2.2), emitted before the stroke.

    The predicted path and the measured break come from the ideal line
    alone — no outcome has been drawn yet. ``make_pct`` is the pre-stroke
    probability from ``make_probability()`` with the measured break; the
    form multiplier applies only to putts over 10 ft (spec §3.6 — the
    >10 ft gate lives here, in this one place, so the read and the
    result can never disagree about it). A tucked pin reads harder:
    when ``pin_difficulty`` is given (the rotation's effective pin
    difficulty, ``sim/pins.py``), the read is scaled by
    ``1 - PIN_READ_WEIGHT * (difficulty - 0.5)`` on putts over 6 ft —
    a Sunday corner pin reads ~8% harder than the raw distance, an
    accessible centre pin ~4% easier. ESTIMATE, and a read/display
    effect only: the outcome draw still uses the calibrated table, so
    the read is the caddie's judgment that a tucked pin plays harder
    than the yardage, not a second table. Tap-ins (<= 6 ft) read true.
    """
    pred = predicted_path(green, ball_ft, pin_ft, green_speed)
    p = make_probability(distance_ft, pred["break_ft"], green_speed)
    if distance_ft > 10:
        p *= form_putt_mult
    if pin_difficulty is not None and distance_ft > 6:
        p *= (1.0 - PIN_READ_WEIGHT * (pin_difficulty - 0.5))
    p = min(0.995, max(0.001, p))
    return {
        "distance_ft": round(float(distance_ft), 1),
        "distance_in": int(round(distance_ft * 12)),
        "break_ft": round(pred["break_ft"], 1),
        "break_dir": pred["break_dir"],
        "make_pct": round(p, 3),
        "green_speed": round(float(green_speed), 1),
        "predicted_path": pred["path"],
        "is_comebacker": bool(is_comebacker),
    }


def build_putt_result(green: Green, ball_ft, pin_ft, res: dict,
                      green_speed: float, make_pct: float | None = None
                      ) -> dict:
    """The extended ``putt_result`` putt dict (§2.3).

    ``res`` is the v1 ``putt()`` result (made / leave_ft / speed /
    break_ft / break_dir / distance_ft) — the outcome the table drew.
    The solver conditions the integrated path on it; the break reported
    here is measured from that path, replacing the drawn break in
    ``res``. ``make_pct`` should be the pre-stroke value from the
    ``putt_read`` (it is never recomputed after the outcome); if it is
    not passed, it is computed from the measured break without any form
    multiplier.
    """
    solved = solve_actual_path(green, ball_ft, pin_ft, res["made"],
                               res["leave_ft"], res["speed"], green_speed)
    if make_pct is None:
        make_pct = make_probability(res["distance_ft"],
                                    solved["break_ft"], green_speed)
        make_pct = min(0.995, max(0.001, make_pct))
    return {
        "distance_ft": round(float(res["distance_ft"]), 1),
        "break_ft": round(solved["break_ft"], 1),
        "break_dir": solved["break_dir"],
        "speed": res["speed"],
        "made": bool(res["made"]),
        "leave_ft": round(float(res["leave_ft"]), 1),
        "make_pct": round(float(make_pct), 3),
        "path": solved["path"],
        "pace_ft_s": round(solved["pace_ft_s"], 1),
        "past_hole_ft": solved["past_hole_ft"],
        "lip": solved["lip"],
        "closest_in": solved["closest_in"],
        "edge_class": solved["edge_class"],
    }
