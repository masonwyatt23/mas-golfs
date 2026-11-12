"""Wyatt National course data and geometry (spec §9.1, course-design.md).

Coordinates: every hole lives in its own local frame. ``s`` is distance along
the hole's centreline in yards (0 at the tee, ``yardage`` at the green
centre); ``lateral`` is yards off the centreline (+ = the golfer's right,
facing the target — the §1.2 left-handed sign convention). Hazards are
ellipses in (s, lateral) space, which makes lie determination a few cheap
tests instead of polygon math. Elevation is linear from tee to green.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Bunker:
    s_yd: float
    lateral_yd: float
    rx_ft: float
    ry_ft: float

    @property
    def is_greenside(self) -> bool:
        # Filled in by Course when the hole is built (needs green s).
        return self._greenside

    _greenside: bool = field(default=False, repr=False)


@dataclass
class Water:
    s_yd: float
    lateral_yd: float
    rx_ft: float
    ry_ft: float


@dataclass
class TreeCluster:
    s_yd: float
    lateral_yd: float
    r_ft: float


@dataclass
class Hole:
    hole: int
    par: int
    yardage: int
    name: str
    azimuth_deg: float      # playing direction, for wind resolution (§1.4)
    elev_tee_ft: float
    elev_green_ft: float
    fairway_width_yd: float = 32.0
    green_radius_ft: float = 42.0
    dogleg_at_yd: float = 0.0
    dogleg_angle_deg: float = 0.0   # + = bends right (golfer's perspective)
    bunkers: list = field(default_factory=list)
    water: list = field(default_factory=list)
    trees: list = field(default_factory=list)
    hazard_label: str = ""
    drop_zone: tuple = (0.0, 0.0)  # (s_yd, lateral_yd) for water drops
    ob_right_yd: float = 90.0      # lateral beyond which the ball is OB

    def __post_init__(self):
        for b in self.bunkers:
            b._greenside = abs(self.yardage - b.s_yd) <= 45

    # -- centreline -------------------------------------------------------
    def centreline_points(self):
        """Polyline of the hole centreline in local (x, y) yards."""
        if self.dogleg_at_yd <= 0:
            return [(0.0, 0.0), (float(self.yardage), 0.0)]
        a = math.radians(self.dogleg_angle_deg)
        x1, y1 = self.dogleg_at_yd, 0.0
        remaining = self.yardage - self.dogleg_at_yd
        x2 = x1 + remaining * math.cos(a)
        y2 = y1 + remaining * math.sin(a)
        return [(0.0, 0.0), (x1, y1), (x2, y2)]

    def green_centre(self):
        return self.centreline_points()[-1]

    def elevation_at(self, s_yd: float) -> float:
        """Ground elevation (ft) at distance s along the centreline."""
        t = min(1.0, max(0.0, s_yd / self.yardage))
        return self.elev_tee_ft + (self.elev_green_ft - self.elev_tee_ft) * t

    # -- (x, y) <-> (s, lateral) ------------------------------------------
    def project(self, x: float, y: float):
        """Nearest point on the centreline -> (s_yd, lateral_yd)."""
        pts = self.centreline_points()
        best = None
        s_acc = 0.0
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            dx, dy = bx - ax, by - ay
            seg_len = math.hypot(dx, dy)
            if seg_len == 0:
                continue
            t = ((x - ax) * dx + (y - ay) * dy) / (seg_len * seg_len)
            t = min(1.0, max(0.0, t))
            px, py = ax + t * dx, ay + t * dy
            dist = math.hypot(x - px, y - py)
            # Lateral sign: + = golfer's right. For a segment heading (dx, dy),
            # right of the direction of travel is (dy, -dx) normalised.
            cross = (x - px) * dy - (y - py) * dx
            lateral = dist if cross <= 0 else -dist
            # NOTE: the cross-product sign above is in world coords; the
            # centreline is built so +y is the golfer's right on the first
            # segment, and the bend preserves it for our small dogleg angles.
            s_here = s_acc + t * seg_len
            if best is None or dist < best[2]:
                best = (s_here, lateral, dist)
            s_acc += seg_len
        return best[0], best[1]

    def point_at(self, s_yd: float, lateral_yd: float):
        """(s, lateral) -> local (x, y) yards."""
        pts = self.centreline_points()
        s_remaining = s_yd
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            dx, dy = bx - ax, by - ay
            seg_len = math.hypot(dx, dy)
            if s_remaining <= seg_len or i == len(pts) - 2:
                t = min(1.0, max(0.0, s_remaining / seg_len))
                px, py = ax + t * dx, ay + t * dy
                # Lateral normal n = (-dy, dx)/len — the same normal
                # `project` uses, so point_at inverts project exactly.
                nx, ny = -dy / seg_len, dx / seg_len
                return (px + lateral_yd * nx, py + lateral_yd * ny)
            s_remaining -= seg_len
        return pts[-1]


def _h(hole, par, yardage, name, azimuth, elev_tee, elev_green, **kw):
    return Hole(hole=hole, par=par, yardage=yardage, name=name,
                azimuth_deg=azimuth, elev_tee_ft=elev_tee,
                elev_green_ft=elev_green, **kw)


def build_wyatt_national():
    """Wyatt National, par 72, 7,214 yd (course-design.md)."""
    return [
        _h(1, 4, 412, "The Handshake", 40, 0, -8,
           bunkers=[Bunker(290, -14, 24, 14), Bunker(385, 16, 20, 12)],
           hazard_label="front_right_bunker"),
        _h(2, 5, 578, "The Reach", 10, 0, 5,
           dogleg_at_yd=280, dogleg_angle_deg=-28,
           water=[Water(300, -30, 120, 45)],
           bunkers=[Bunker(310, 18, 26, 14)],
           hazard_label="water_left", drop_zone=(260, 10)),
        _h(3, 3, 187, "The Postage Stamp", 130, 0, 2,
           bunkers=[Bunker(165, 0, 26, 14), Bunker(178, -18, 16, 10)],
           hazard_label="front_bunker"),
        _h(4, 4, 448, "The Examination", 310, 0, 28,
           bunkers=[Bunker(270, -16, 26, 14), Bunker(270, 16, 26, 14),
                    Bunker(420, -14, 20, 12)],
           hazard_label="fairway_bunkers"),
        _h(5, 4, 376, "The Temptation", 60, 0, -4,
           bunkers=[Bunker(290, 0, 22, 12), Bunker(350, -16, 18, 10)],
           hazard_label="centerline_bunker_290"),
        _h(6, 4, 431, "The Dogleg", 160, 0, 12,
           dogleg_at_yd=240, dogleg_angle_deg=32,
           trees=[TreeCluster(250, 26, 30), TreeCluster(300, 30, 24)],
           bunkers=[Bunker(400, 14, 20, 12)],
           hazard_label="pines_right"),
        _h(7, 5, 552, "The Valley", 200, 0, 18,
           bunkers=[Bunker(462, 0, 30, 14), Bunker(520, -16, 22, 12)],
           hazard_label="cross_bunker_90"),
        _h(8, 3, 226, "The Long One", 300, 0, 6,
           water=[Water(195, 0, 90, 40)],
           bunkers=[Bunker(215, -16, 18, 10)],
           hazard_label="water_front", drop_zone=(150, 0)),
        _h(9, 4, 402, "The Return", 220, 0, -12,
           bunkers=[Bunker(375, 16, 22, 12), Bunker(385, -14, 18, 10)],
           hazard_label="front_right_bunker"),
        _h(10, 4, 419, "The Turn", 140, 0, -6,
            dogleg_at_yd=230, dogleg_angle_deg=-18,
            bunkers=[Bunker(280, -14, 24, 14), Bunker(390, 14, 20, 12)],
            hazard_label="fairway_bunker_left"),
        _h(11, 5, 591, "The Monster", 320, 0, 30,
            bunkers=[Bunker(300, -16, 28, 14), Bunker(300, 16, 28, 14),
                     Bunker(560, -14, 22, 12)],
            hazard_label="fairway_bunkers_300"),
        _h(12, 3, 164, "The Picture", 90, 0, -15,
            water=[Water(135, 0, 70, 36)],
            trees=[TreeCluster(150, -30, 26), TreeCluster(150, 30, 26)],
            bunkers=[Bunker(158, 16, 18, 10)],
            hazard_label="pond_front", drop_zone=(110, 0)),
        _h(13, 4, 455, "The Grind", 300, 0, 22,
            bunkers=[Bunker(275, -15, 26, 14), Bunker(275, 15, 26, 14),
                     Bunker(430, -14, 20, 12)],
            hazard_label="fairway_bunkers"),
        _h(14, 4, 388, "The Gambler", 180, 0, 4,
            water=[Water(280, 0, 60, 90)],
            bunkers=[Bunker(360, 14, 20, 12)],
            hazard_label="creek_280", drop_zone=(240, 0)),
        _h(15, 5, 545, "The Eagle Chance", 40, 0, -8,
            bunkers=[Bunker(500, -12, 26, 14), Bunker(510, 14, 24, 12),
                     Bunker(525, 0, 20, 12)],
            hazard_label="greenside_bunker_complex"),
        _h(16, 3, 203, "The Test", 250, 0, 10,
            bunkers=[Bunker(185, 0, 24, 14), Bunker(195, 18, 16, 10)],
            hazard_label="deep_front_bunker"),
        _h(17, 4, 427, "The Penultimate", 100, 0, 6,
            dogleg_at_yd=250, dogleg_angle_deg=30,
            bunkers=[Bunker(290, -14, 24, 14), Bunker(400, 14, 20, 12)],
            hazard_label="ob_right", ob_right_yd=45.0),
        _h(18, 4, 410, "The Closer", 20, 0, 16,
            bunkers=[Bunker(300, -14, 24, 14), Bunker(385, 16, 20, 12)],
            hazard_label="fairway_bunker_300"),
    ]


class Course:
    """A course: holes, par, rating/slope, and lie determination."""

    def __init__(self, course_id="wyatt_national", name="Wyatt National",
                 rating=74.6, slope=138, holes=None):
        self.id = course_id
        self.name = name
        self.rating = rating
        self.slope = slope
        self.holes = holes if holes is not None else build_wyatt_national()
        self.par = sum(h.par for h in self.holes)
        self.yardage = sum(h.yardage for h in self.holes)

    def hole(self, n: int) -> Hole:
        return self.holes[n - 1]

    def par_through(self, n: int) -> int:
        return sum(h.par for h in self.holes[:n])

    # -- lie determination (§2.5) -----------------------------------------
    def determine_lie(self, hole: Hole, x: float, y: float):
        """Final resting position -> (lie, in_water, ob).

        Tests, in order: green, bunkers, water, trees, fairway, rough.
        A ball within 2 ft of a bunker edge is in the bunker (§2.5).
        """
        s, lateral = hole.project(x, y)
        gx, gy = hole.green_centre()
        dist_to_green_yd = math.hypot(x - gx, y - gy)
        green_r_yd = hole.green_radius_ft / 3.0

        # Out of bounds: far right on 17 (tight OB), or way off the hole.
        if lateral > hole.ob_right_yd or lateral < -90 or s < -15 \
                or s > hole.yardage + 80:
            return "ob", False, True

        # Water.
        for w in hole.water:
            if ((s - w.s_yd) / (w.rx_ft / 3.0)) ** 2 + \
               ((lateral - w.lateral_yd) / (w.ry_ft / 3.0)) ** 2 <= 1.0:
                return "water", True, False

        # Green.
        if dist_to_green_yd <= green_r_yd:
            return "green", False, False

        # Bunkers (2 ft grace at the edge, §2.5).
        for b in hole.bunkers:
            rx = (b.rx_ft + 2.0) / 3.0
            ry = (b.ry_ft + 2.0) / 3.0
            if ((s - b.s_yd) / rx) ** 2 + ((lateral - b.lateral_yd) / ry) ** 2 <= 1.0:
                return ("bunker_green" if b.is_greenside else "bunker_fairway",
                        False, False)

        # Trees.
        for t in hole.trees:
            if math.hypot(s - t.s_yd, lateral - t.lateral_yd) <= t.r_ft / 3.0:
                return "trees", False, False

        # Fairway (past the green is rough, not fairway).
        if abs(lateral) <= hole.fairway_width_yd / 2.0 and s <= hole.yardage + 10:
            return "fairway", False, False

        # Rough: close to the fairway edge is light, deep is heavy.
        if abs(lateral) <= hole.fairway_width_yd / 2.0 + 8:
            return "rough_light", False, False
        return "rough_heavy", False, False


WYATT_NATIONAL = Course()
