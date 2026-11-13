"""Green heightfields — one source of truth for the ball, the overlay,
and the putt-path trace (putting-model-v2.md §1).

A ``Green`` is the putting surface of one hole: overall slope, fall-line
direction, tier structure, and a 0.5 m heightfield grid covering the green
plus a 2 m collar into the fringe. The field is deterministic from
``(course_id, hole_no)`` — the per-hole table below is fully specified,
so no RNG is involved in generating a field: the same hole always yields
the same field, and the broadcast can trust that the field it rendered
on round 12 is the field the sim integrated on round 47.

Coordinate frame (green-local feet, used everywhere in this module and
in ``sim.putting``):
- Origin: the green centre.
- +X: toward the fairway, i.e. back along the hole's playing direction
  (the opposite of the centreline's last-segment direction).
- +Y: the golfer's right when facing the green (the lateral normal from
  ``course.py`` — the same convention as ``Hole.project``).
- ``fall_dir_deg`` is the downhill direction as an angle in this frame:
  0 deg falls toward the fairway (back-to-front), 180 deg falls toward
  the back (front-to-back), 90 deg falls to the golfer's right,
  270 deg falls to the golfer's left. The downhill unit vector is
  ``(cos fall_dir, sin fall_dir)``.

Per-hole data comes from ``docs/course-design-v3.md`` (green slope,
tier structure, contour character per hole). Where the v3 doc states a
slope as an adjective rather than a number ("tilted hard", "gently"),
the value in the table is marked ESTIMATED in its comment — it is a
design choice, not a measurement, and the v3 doc is the place to correct
it, not this code.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field

import numpy as np

GRID_M = 0.5                 # grid spacing, metres (spec §1.2 — fixed)
COLLAR_M = 2.0               # fringe/apron collar around the green (spec §1.2)
FT_PER_M = 1.0 / 0.3048
M_PER_FT = 0.3048
GRID_FT = GRID_M * FT_PER_M  # 1.64042 ft between grid points


@dataclass
class Tier:
    """One contour feature on a green.

    ``kind`` selects the shape; the remaining fields are the geometry
    that kind reads (unused fields are ignored):

    - ``"step"`` — a smooth step across a line. The raised side is the
      side of the line in the ``normal_deg`` direction; the step sits
      ``offset_ft`` from the centre along that normal and rises
      ``height_in`` over ``width_m`` of run. (A back tier 18 in higher
      is ``normal_deg=180, offset_ft=0, height_in=18``.)
    - ``"spine"`` — a raised ridge along a line. The line runs at
      ``angle_deg`` through the point ``offset_ft`` from the centre along
      its normal; the ridge is ``height_in`` high and ``sigma_m`` wide.
    - ``"bump"`` — a gaussian mound (positive ``height_in``) or hollow
      (negative ``height_in``, a bowl / thumbprint) centred at
      ``(cx_ft, cy_ft)`` with width ``sigma_m``.
    - ``"false_front"`` — the front portion of the green falls away
      toward the fairway: a ``height_in`` drop (given positive, applied
      as a fall) starting ``offset_ft`` inside the front edge.
    """
    kind: str
    height_in: float
    normal_deg: float = 0.0
    offset_ft: float = 0.0
    sigma_m: float = 1.0
    cx_ft: float = 0.0
    cy_ft: float = 0.0
    angle_deg: float = 0.0
    width_m: float = 0.5


@dataclass
class Green:
    """One hole's putting surface (putting-model-v2.md §1.2)."""
    hole_no: int
    course_id: str = "wyatt_national"
    slope_pct: float = 2.0       # overall slope, back-to-front, percent
    fall_dir_deg: float = 0.0    # downhill direction, green-local degrees
    tiers: list = field(default_factory=list)
    radius_ft: float = 42.0      # putting-surface radius (from Hole)
    grid_m: float = GRID_M

    # -- geometry -------------------------------------------------------
    @property
    def half_ft(self) -> float:
        """Half-extent of the field: green radius + 2 m collar, feet."""
        return self.radius_ft + COLLAR_M * FT_PER_M

    @property
    def grid_shape(self) -> tuple[int, int]:
        """(n_rows, n_cols) of the heightfield at 0.5 m spacing."""
        n = int(math.floor(2.0 * self.half_ft / GRID_FT)) + 1
        return (n, n)

    @property
    def fall_unit(self) -> tuple[float, float]:
        a = math.radians(self.fall_dir_deg)
        return (math.cos(a), math.sin(a))

    # -- heightfield ----------------------------------------------------
    # The field is cached on first build: the integrator calls height_at
    # thousands of times per putt, and rebuilding the array each time
    # would dominate the solver. Greens are immutable after construction
    # (the table is fixed), so the cache can never go stale.
    _field: np.ndarray | None = field(default=None, repr=False)

    def heightfield(self) -> np.ndarray:
        """2D array of heights in mm above the green's low corner, int16.

        Base plane at ``slope_pct`` along the fall line, plus the tier
        features, shifted so the minimum is exactly 0. Deterministic:
        no RNG anywhere in this method.
        """
        if self._field is not None:
            return self._field
        n, _ = self.grid_shape
        xs = -self.half_ft + np.arange(n) * GRID_FT
        ys = -self.half_ft + np.arange(n) * GRID_FT
        X, Y = np.meshgrid(xs, ys)  # X: columns (green-local +X), Y: rows
        fx, fy = self.fall_unit
        # Base plane: height DECREASES along the fall direction — the
        # high corner (most uphill point of the grid) is the datum from
        # which the plane falls, so the ball rolls toward +fall_dir.
        proj = X * fx + Y * fy
        h_ft = (self.slope_pct / 100.0) * (proj.max() - proj)
        h_mm = h_ft * 304.8
        for tier in self.tiers:
            h_mm = h_mm + self._tier_mm(tier, X, Y)
        h_mm = h_mm - h_mm.min()
        self._field = np.round(h_mm).astype(np.int16)
        return self._field

    def _tier_mm(self, tier: Tier, X, Y) -> np.ndarray:
        """Height contribution of one tier feature, in mm."""
        if tier.kind == "step":
            a = math.radians(tier.normal_deg)
            d = X * math.cos(a) + Y * math.sin(a) - tier.offset_ft
            w = max(0.2, tier.width_m * FT_PER_M)
            return tier.height_in * 25.4 / (1.0 + np.exp(-d / w))
        if tier.kind == "spine":
            a = math.radians(tier.angle_deg)
            # Line direction (cos a, sin a); perpendicular distance from
            # the line through offset_ft along the line's normal.
            nx, ny = -math.sin(a), math.cos(a)
            d = X * nx + Y * ny - tier.offset_ft
            sig = max(0.3, tier.sigma_m * FT_PER_M)
            return tier.height_in * 25.4 * np.exp(-(d * d) / (2.0 * sig * sig))
        if tier.kind == "bump":
            sig = max(0.3, tier.sigma_m * FT_PER_M)
            r2 = (X - tier.cx_ft) ** 2 + (Y - tier.cy_ft) ** 2
            return tier.height_in * 25.4 * np.exp(-r2 / (2.0 * sig * sig))
        if tier.kind == "false_front":
            # The front edge is at +X = radius_ft; the false front is the
            # band inside it that falls away toward the fairway.
            front = self.radius_ft - tier.offset_ft
            w = max(0.5, 2.0)
            return -tier.height_in * 25.4 / (1.0 + np.exp(-(X - front) / w))
        raise ValueError(f"unknown tier kind: {tier.kind!r}")

    def height_at(self, x_ft: float, y_ft: float) -> float:
        """Surface height (ft above the low corner) at a green-local point.

        Bilinear interpolation on the field; points outside the grid
        clamp to the edge (a putt that runs off the field is already in
        the collar, and the collar is the field's edge).
        """
        h = self.heightfield()
        n, _ = self.grid_shape
        gx = (x_ft + self.half_ft) / GRID_FT
        gy = (y_ft + self.half_ft) / GRID_FT
        gx = min(max(gx, 0.0), n - 1.001)
        gy = min(max(gy, 0.0), n - 1.001)
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        ix1, iy1 = min(ix + 1, n - 1), min(iy + 1, n - 1)
        v = (h[iy, ix] * (1 - fx) * (1 - fy)
             + h[iy, ix1] * fx * (1 - fy)
             + h[iy1, ix] * (1 - fx) * fy
             + h[iy1, ix1] * fx * fy)
        return float(v) / 304.8

    def gradient_at(self, x_ft: float, y_ft: float) -> tuple[float, float]:
        """Surface gradient (dh/dx, dh/dy), dimensionless, at a point.

        Central differences on the field, 0.25 ft step — fine enough for
        a ball whose break is a feature of the surface at the scale of
        a foot or two.
        """
        e = 0.25
        dhdx = (self.height_at(x_ft + e, y_ft)
                - self.height_at(x_ft - e, y_ft)) / (2.0 * e)
        dhdy = (self.height_at(x_ft, y_ft + e)
                - self.height_at(x_ft, y_ft - e)) / (2.0 * e)
        return dhdx, dhdy

    # -- event payload (§1.6, option 1: ship it in hole_start) ----------
    def payload(self) -> dict:
        """JSON-safe payload for the ``hole_start`` event.

        The quantized heightfield as base64 (int16 little-endian), plus
        the grid spacing, the green radius, and the fall-line direction
        — everything the broadcast needs to render slope arrows and the
        grid from the same array the ball rolls on.
        """
        h = self.heightfield()
        return {
            "course_id": self.course_id,
            "hole": self.hole_no,
            "grid_m": self.grid_m,
            "radius_ft": self.radius_ft,
            "slope_pct": self.slope_pct,
            "fall_dir_deg": self.fall_dir_deg,
            "n_rows": h.shape[0],
            "n_cols": h.shape[1],
            "half_ft": round(self.half_ft, 2),
            "heightfield_b64": base64.b64encode(
                h.astype("<i2").tobytes()).decode("ascii"),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> tuple["Green", np.ndarray]:
        """Decode a ``payload()`` dict back to (Green, heightfield).

        The decoded array is the field the ball rolled on — the
        broadcast-side check that the overlay and the ball read the
        same array (spec §1.1).
        """
        raw = base64.b64decode(payload["heightfield_b64"])
        h = np.frombuffer(raw, dtype="<i2").reshape(
            payload["n_rows"], payload["n_cols"]).astype(np.int16)
        green = cls(hole_no=payload["hole"],
                    course_id=payload.get("course_id", "wyatt_national"),
                    slope_pct=payload["slope_pct"],
                    fall_dir_deg=payload["fall_dir_deg"],
                    radius_ft=payload["radius_ft"],
                    grid_m=payload["grid_m"])
        return green, h


# --------------------------------------------------------------------------
# Wyatt National v3 greens (docs/course-design-v3.md, per-hole green specs).
#
# Slope percentages are the v3 numbers where the doc states one. Where the
# doc states the slope as an adjective ("tilted hard", "gently"), the value
# is marked ESTIMATED — a design choice in this table, to be corrected in
# the v3 doc, not improvised elsewhere. Tier heights the doc does not state
# (13th step, 17th shelf, 18th back tier) are likewise ESTIMATED.
# --------------------------------------------------------------------------

def _step(normal_deg, height_in, offset_ft=0.0, width_m=1.5):
    # width_m is the logistic transition: a real tier rises over several
    # feet, not a cliff. 1.5 m makes a 12 in step a ~20% grade a firm
    # putt can climb; the 0.5 m default would make it a ~60% wall.
    return Tier("step", height_in, normal_deg=normal_deg,
                offset_ft=offset_ft, width_m=width_m)


def _spine(angle_deg, height_in, offset_ft=0.0, sigma_m=1.2):
    return Tier("spine", height_in, angle_deg=angle_deg,
                offset_ft=offset_ft, sigma_m=sigma_m)


def _bump(cx_ft, cy_ft, height_in, sigma_m=4.0):
    return Tier("bump", height_in, cx_ft=cx_ft, cy_ft=cy_ft, sigma_m=sigma_m)


def _false_front(height_in=6.0, offset_ft=10.0):
    return Tier("false_front", height_in, offset_ft=offset_ft)


WYATT_GREENS: dict[int, dict] = {
    # hole: slope_pct, fall_dir_deg, tiers
    # 1: two-tier, back tier 18 in higher, B->F 2%.
    1: dict(slope_pct=2.0, fall_dir_deg=0.0,
            tiers=[_step(180.0, 18.0)]),
    # 2: tilted hard L->R toward the water. No % in the doc — ESTIMATED 2.0.
    # The lake the fade runs toward sits on the green's right (the hole
    # doglegs left, so the water that was left of the fairway is right of
    # the green); fall is to the golfer's right.
    2: dict(slope_pct=2.0, fall_dir_deg=90.0, tiers=[]),
    # 3: crowned Short hole, B->F 3%, thumbprint hollow on the left.
    3: dict(slope_pct=3.0, fall_dir_deg=0.0,
            tiers=[_bump(0.0, 0.0, 4.0, sigma_m=6.0),
                   _bump(0.0, -12.0, -2.0, sigma_m=3.0)]),
    # 4: largest green, three sections separated by a spine, up to the
    # back at 1.5% (falls toward the front).
    4: dict(slope_pct=1.5, fall_dir_deg=0.0,
            tiers=[_spine(0.0, 6.0, sigma_m=1.5)]),
    # 5: small, firm, sloping hard front-to-back. No % in the doc —
    # ESTIMATED 2.0. Plateau green; the fall-offs are outside the field.
    5: dict(slope_pct=2.0, fall_dir_deg=180.0, tiers=[]),
    # 6: B->F 1.5%, back-left bowl.
    6: dict(slope_pct=1.5, fall_dir_deg=0.0,
            tiers=[_bump(-12.0, -10.0, -3.0)]),
    # 7: two-tier, 2-ft step, back tier sloping away. No overall % in
    # the doc — ESTIMATED 1.5.
    7: dict(slope_pct=1.5, fall_dir_deg=0.0,
            tiers=[_step(180.0, 24.0)]),
    # 8: Eden, sloping gently toward the water (the pond fronts the
    # green). No % in the doc — ESTIMATED 1.2.
    8: dict(slope_pct=1.2, fall_dir_deg=0.0, tiers=[]),
    # 9: wide/shallow, B->F 2.5%, false front.
    9: dict(slope_pct=2.5, fall_dir_deg=0.0,
            tiers=[_false_front()]),
    # 10: spine down the middle, B->F 1.8%.
    10: dict(slope_pct=1.8, fall_dir_deg=0.0,
             tiers=[_spine(0.0, 5.0)]),
    # 11: up to the back at 1.3%, back-left bowl.
    11: dict(slope_pct=1.3, fall_dir_deg=0.0,
             tiers=[_bump(-12.0, -10.0, -3.0)]),
    # 12: flattest on the course, 0.8%, gently toward the water (front).
    12: dict(slope_pct=0.8, fall_dir_deg=0.0, tiers=[]),
    # 13: most severe, two-tier sloping away from the fairway at 2%,
    # false front, run-off long. Step height not stated — ESTIMATED 12 in.
    13: dict(slope_pct=2.0, fall_dir_deg=180.0,
             tiers=[_step(180.0, 12.0), _false_front()]),
    # 14: small/firm, front-to-back 1.5%, shaved run-off left.
    14: dict(slope_pct=1.5, fall_dir_deg=180.0, tiers=[]),
    # 15: large, back-left bowl, B->F 1.6%.
    15: dict(slope_pct=1.6, fall_dir_deg=0.0,
             tiers=[_bump(-12.0, -10.0, -3.0)]),
    # 16: Redan, tilted front-right to back-left, 2.5% — the steepest
    # putting surface on the course. Two tiers, 14-in step; the raised
    # side is the front-right (high side).
    16: dict(slope_pct=2.5, fall_dir_deg=225.0,
             tiers=[_step(45.0, 14.0)]),
    # 17: narrow, B->F 2%, back-right shelf. Shelf height not stated —
    # ESTIMATED 8 in.
    17: dict(slope_pct=2.0, fall_dir_deg=0.0,
             tiers=[_step(135.0, 8.0, offset_ft=6.0)]),
    # 18: wide, B->F 2%, false front and a back tier. Back-tier height
    # not stated — ESTIMATED 12 in.
    18: dict(slope_pct=2.0, fall_dir_deg=0.0,
             tiers=[_false_front(), _step(180.0, 12.0, offset_ft=8.0)]),
}


def green_for_hole(hole_no: int, radius_ft: float = 42.0,
                   course_id: str = "wyatt_national") -> Green:
    """The ``Green`` for a hole, from the v3 table.

    ``radius_ft`` comes from the hole's ``green_radius_ft`` (42 ft
    default; 45 ft on 4 and 11, 44 ft on 13 and 15). The heightfield is
    deterministic from ``(course_id, hole_no)`` — the table is fully
    specified, so no seed is needed.
    """
    spec = WYATT_GREENS[hole_no]
    return Green(hole_no=hole_no, course_id=course_id,
                 slope_pct=spec["slope_pct"],
                 fall_dir_deg=spec["fall_dir_deg"],
                 tiers=list(spec["tiers"]), radius_ft=radius_ft)


# --------------------------------------------------------------------------
# Coordinate conversion: hole frame (yards) <-> green-local feet.
# --------------------------------------------------------------------------

def to_green_local(hole, x_yd: float, y_yd: float) -> tuple[float, float]:
    """Hole-frame yards -> green-local feet.

    Mirrors ``RoundEngine._pin_position``: the playing direction is the
    centreline's last segment, the lateral normal is ``(-uy, ux)``.
    +X is toward the fairway (opposite the playing direction), +Y is the
    golfer's right facing the green. A pin placed from ``PIN_OFFSETS``
    (x_ft lateral, y_ft front/back) lands at green-local
    ``(-y_ft, x_ft)``: front is toward the fairway, i.e. +X.
    """
    gx, gy = hole.green_centre()
    pts = hole.centreline_points()
    dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
    seg = math.hypot(dx, dy) or 1.0
    ux, uy = dx / seg, dy / seg
    nx, ny = -uy, ux
    rx, ry = x_yd - gx, y_yd - gy
    along = rx * ux + ry * uy   # + = past the green, along play
    lat = rx * nx + ry * ny     # + = golfer's right
    return (-along * 3.0, lat * 3.0)


def from_green_local(hole, x_ft: float, y_ft: float) -> tuple[float, float]:
    """Green-local feet -> hole-frame yards (inverse of to_green_local)."""
    gx, gy = hole.green_centre()
    pts = hole.centreline_points()
    dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
    seg = math.hypot(dx, dy) or 1.0
    ux, uy = dx / seg, dy / seg
    nx, ny = -uy, ux
    # +X (green-local) is -u, +Y is +n.
    rx = (-x_ft / 3.0) * ux + (y_ft / 3.0) * nx
    ry = (-x_ft / 3.0) * uy + (y_ft / 3.0) * ny
    return (gx + rx, gy + ry)
