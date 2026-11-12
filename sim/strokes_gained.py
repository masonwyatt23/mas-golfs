"""Strokes-gained baseline table and computation (spec §§5.5, 6.2).

The baseline is the engine's "value of every position". It is used by the
decision engine's Monte Carlo (expected strokes to hole out) and by the
learning loop (strokes gained per shot).
"""

from __future__ import annotations

import numpy as np

from . import constants as C


def baseline_strokes(lie: str, distance_yd: float = 0.0,
                     distance_ft: float = 0.0,
                     adjustments: dict | None = None) -> float:
    """Expected strokes to hole out from a position (§5.5).

    ``distance_yd`` is used for off-green lies, ``distance_ft`` for putts.
    ``adjustments`` (from the learning loop, §6.4) shifts a bucket by
    +/-0.05 strokes per bucket based on observed performance.
    """
    adj = 0.0
    if adjustments:
        adj = adjustments.get(_bucket_key(lie, distance_yd), 0.0)
    if lie == "green":
        d = np.clip(distance_ft, 1.0, 60.0)
        base = float(np.interp(d, C.BASELINE_GREEN_FT, C.BASELINE_GREEN_SG))
    elif lie in ("fairway", "tee"):
        d = np.clip(distance_yd, 1.0, 320.0)
        base = float(np.interp(d, C.BASELINE_FAIRWAY_YD, C.BASELINE_FAIRWAY_SG))
        if d > 250:  # extrapolate the last slope for long par-5 lay-ups
            base = 3.45 + (d - 250.0) * 0.004
    elif lie == "rough_light":
        d = np.clip(distance_yd, 20.0, 220.0)
        base = float(np.interp(d, C.BASELINE_ROUGH_LIGHT_YD,
                               C.BASELINE_ROUGH_LIGHT_SG))
        if d < 100:
            base = 2.95 - (100.0 - d) * 0.004
    elif lie == "rough_heavy":
        d = np.clip(distance_yd, 20.0, 220.0)
        base = float(np.interp(d, C.BASELINE_ROUGH_HEAVY_YD,
                               C.BASELINE_ROUGH_HEAVY_SG))
        if d < 100:
            base = 3.25 - (100.0 - d) * 0.004
    elif lie == "bunker_green":
        base = C.BASELINE_BUNKER_GREEN
    elif lie == "bunker_fairway":
        d = np.clip(distance_yd, 20.0, 250.0)
        base = 3.30 if d >= 150 else 3.30 - (150.0 - d) * 0.002
    elif lie == "trees":
        base = C.BASELINE_TREES
    elif lie in ("water", "ob"):
        base = C.BASELINE_WATER_OB
    elif lie == "fringe":
        base = float(np.interp(np.clip(distance_ft, 1.0, 60.0),
                               C.BASELINE_GREEN_FT, C.BASELINE_GREEN_SG)) + 0.15
    else:
        base = 3.0
    return max(1.0, base + adj)


def _bucket_key(lie: str, distance_yd: float) -> str:
    if lie in ("fairway", "tee", "rough_light", "rough_heavy"):
        for lo, hi in ((0, 100), (100, 125), (125, 150), (150, 175),
                       (175, 200), (200, 9999)):
            if lo <= distance_yd < hi:
                return f"app_{lo}_{hi}"
    return lie


def categorize_shot(shot_no: int, par: int, lie: str, distance_yd: float,
                    is_putt: bool, is_tee_shot: bool) -> str:
    """SG category for a shot (§6.2)."""
    if is_putt:
        return "putt"
    if is_tee_shot and par in (4, 5):
        return "ott"
    if distance_yd > 100 or (is_tee_shot and par == 3):
        return "app"
    return "arg"


def strokes_gained(start_lie: str, start_dist_yd: float, start_dist_ft: float,
                   end_lie: str, end_dist_yd: float, end_dist_ft: float,
                   penalty: int = 0, adjustments: dict | None = None) -> float:
    """SG for one shot (§6.2): baseline(start) - (1 + baseline(end)) - pen."""
    before = baseline_strokes(start_lie, start_dist_yd, start_dist_ft,
                              adjustments)
    after = baseline_strokes(end_lie, end_dist_yd, end_dist_ft, adjustments)
    return before - (1.0 + after) - penalty
