"""Putting model (spec §3.5).

No launch conditions — a make-probability + distance-control model.
"""

from __future__ import annotations

import numpy as np

from . import constants as C
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
    p_make = min(0.995, p_make * form_putt_mult)
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
