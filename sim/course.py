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
    # v3 (course-design-v3.md §5.1): first cut of semi-rough blending the
    # fairway into the deep rough — the sim's version of the rounded
    # fairway edge. Default 7 yd; per-hole overrides average the two
    # sides (5th/6th 10 left / 5 right -> 7.5; 13th 5.0; 17th 5.0 — the
    # OB side has no semi-rough, the edge is absolute).
    semi_rough_yd: float = 7.0
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


def build_wyatt_national_v2():
    """Wyatt National v2, par 72, 7,214 yd (course-design-v2.md).

    Kept for calibration comparison: v3 is the live course, v2 stays
    available so the harness can measure exactly what the extra 388
    yards did to scoring.
    """
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


def build_wyatt_national():
    """Wyatt National v3, par 72, 7,602 yd (course-design-v3.md).

    The live course. Same routing, pars, names, azimuths, doglegs, and
    templates as v2; what changes is length (+388 yd), land shaping, and
    green complexes. Front 3,808 / back 3,794.

    How §5.1 was applied here:
    - Yardages and green elevations per the v3 hole tables.
    - Bunkers: driving-distance bunkers stay at their v2 ``s_yd``
      (270–300); greenside bunkers move out by the hole's yardage gain;
      the 7th cross-bunker moves to 496 (90 yd short of the green); the
      14th creek stays at 280; one new bunker on the 11th, fairway left
      at 340. Where the design prose states a bunker distance a few
      yards off the gain rule (e.g. 15th complex, 17th Road Hole
      bunker), the §5.1 gain rule wins — the prose numbers are the
      design intent, the rule is the implementation.
    - Green radii +2–3 ft on the long-approach holes (4, 11, 13, 15).
    - 13th fairway narrowed to 28 yd. Semi-rough overrides: 5th/6th
      7.5, 10th 7.0, 13th 5.0, 17th 5.0 (see the ``semi_rough_yd``
      field comment on ``Hole``).
    - Water, trees, doglegs, azimuths, hazard labels, and drop zones
      are unchanged from v2 — §5.1 is silent on them, so no water or
      tree was moved even though the greens moved out (the pond on 8
      and 12 now sits a few yards further from the green than in v2).
    """
    return [
        _h(1, 4, 432, "The Handshake", 40, 0, -10,
           bunkers=[Bunker(290, -14, 24, 14), Bunker(405, 16, 20, 12)],
           hazard_label="front_right_bunker"),
        _h(2, 5, 612, "The Reach", 10, 0, 5,
           dogleg_at_yd=280, dogleg_angle_deg=-28,
           water=[Water(300, -30, 120, 45)],
           bunkers=[Bunker(310, 18, 26, 14)],
           hazard_label="water_left", drop_zone=(260, 10)),
        _h(3, 3, 196, "The Postage Stamp", 130, 0, 2,
           bunkers=[Bunker(174, 0, 26, 14), Bunker(187, -18, 16, 10)],
           hazard_label="front_bunker"),
        _h(4, 4, 476, "The Examination", 310, 0, 34,
           bunkers=[Bunker(270, -16, 26, 14), Bunker(270, 16, 26, 14),
                    Bunker(448, -14, 20, 12)],
           hazard_label="fairway_bunkers", green_radius_ft=45.0),
        _h(5, 4, 392, "The Temptation", 60, 0, -4,
           bunkers=[Bunker(290, 0, 22, 12), Bunker(366, -16, 18, 10)],
           hazard_label="centerline_bunker_290", semi_rough_yd=7.5),
        _h(6, 4, 452, "The Dogleg", 160, 0, 12,
           dogleg_at_yd=240, dogleg_angle_deg=32,
           trees=[TreeCluster(250, 26, 30), TreeCluster(300, 30, 24)],
           bunkers=[Bunker(421, 14, 20, 12)],
           hazard_label="pines_right", semi_rough_yd=7.5),
        _h(7, 5, 586, "The Valley", 200, 0, 22,
           bunkers=[Bunker(496, 0, 30, 14), Bunker(554, -16, 22, 12)],
           hazard_label="cross_bunker_90"),
        _h(8, 3, 238, "The Long One", 300, 0, 6,
           water=[Water(195, 0, 90, 40)],
           bunkers=[Bunker(227, -16, 18, 10)],
           hazard_label="water_front", drop_zone=(150, 0)),
        _h(9, 4, 424, "The Return", 220, 0, -14,
           bunkers=[Bunker(397, 16, 22, 12), Bunker(407, -14, 18, 10)],
           hazard_label="front_right_bunker"),
        _h(10, 4, 440, "The Turn", 140, 0, -8,
            dogleg_at_yd=230, dogleg_angle_deg=-18,
            bunkers=[Bunker(280, -14, 24, 14), Bunker(411, 14, 20, 12)],
            hazard_label="fairway_bunker_left", semi_rough_yd=7.0),
        _h(11, 5, 624, "The Monster", 320, 0, 34,
            bunkers=[Bunker(300, -16, 28, 14), Bunker(300, 16, 28, 14),
                     Bunker(340, -16, 26, 14), Bunker(593, -14, 22, 12)],
            hazard_label="fairway_bunkers_300", green_radius_ft=45.0),
        _h(12, 3, 172, "The Picture", 90, 0, -17,
            water=[Water(135, 0, 70, 36)],
            trees=[TreeCluster(150, -30, 26), TreeCluster(150, 30, 26)],
            bunkers=[Bunker(166, 16, 18, 10)],
            hazard_label="pond_front", drop_zone=(110, 0)),
        _h(13, 4, 482, "The Grind", 300, 0, 28,
            bunkers=[Bunker(275, -15, 26, 14), Bunker(275, 15, 26, 14),
                     Bunker(457, -14, 20, 12)],
            hazard_label="fairway_bunkers", fairway_width_yd=28.0,
            green_radius_ft=44.0, semi_rough_yd=5.0),
        _h(14, 4, 406, "The Gambler", 180, 0, 4,
            water=[Water(280, 0, 60, 90)],
            bunkers=[Bunker(378, 14, 20, 12)],
            hazard_label="creek_280", drop_zone=(240, 0)),
        _h(15, 5, 578, "The Eagle Chance", 40, 0, -8,
            bunkers=[Bunker(533, -12, 26, 14), Bunker(543, 14, 24, 12),
                     Bunker(558, 0, 20, 12)],
            hazard_label="greenside_bunker_complex", green_radius_ft=44.0),
        _h(16, 3, 214, "The Test", 250, 0, 10,
            bunkers=[Bunker(196, 0, 24, 14), Bunker(206, 18, 16, 10)],
            hazard_label="deep_front_bunker"),
        _h(17, 4, 448, "The Penultimate", 100, 0, 6,
            dogleg_at_yd=250, dogleg_angle_deg=30,
            bunkers=[Bunker(290, -14, 24, 14), Bunker(421, 14, 20, 12)],
            hazard_label="ob_right", ob_right_yd=45.0, semi_rough_yd=5.0),
        _h(18, 4, 430, "The Closer", 20, 0, 19,
            bunkers=[Bunker(300, -14, 24, 14), Bunker(405, 16, 20, 12)],
            hazard_label="fairway_bunker_300"),
    ]


def build_dunmore_links():
    """Dunmore Links, par 72, 7,195 yd (course-two.md).

    The second course: a seaside links on the Outer Banks, NC — Wyatt
    National's opposite on purpose. Parkland vs links, aerial game vs
    ground game, pines and water vs wind, firm ground, and pot bunkers.
    Front 3,591 / back 3,604, two par 3s and two par 5s per nine.

    How the spec was applied here:
    - Yardages, pars, names, and templates per the doc's hole briefs.
      Par 3s: 3 (Biarritz), 7, 12 (Punchbowl), 16 (Double Plateau).
      Par 5s: 2, 6 (Sahara), 11, 15. Par 4s: 1, 4, 5 (Principal's
      Nose), 8, 9, 10, 13, 14, 17 (Alps, signature), 18.
    - Azimuths from the doc's wind rotation: the morning sea breeze
      (NE) helps 1, 5, 9, 15, 18 (azimuth ~210-240, playing SW),
      hurts 4, 6, 11, 13 (azimuth ~30-50, playing NE), crosses
      3, 8, 10, 16, 17 (azimuth ~125-140 or ~310-320). No two
      consecutive holes share an azimuth.
    - Elevations per the hole briefs (tee -> green, ft): 4th +25,
      11th +40, 13th +35, 18th +20 uphill; 8th -15, 9th -20, 10th
      -25, 12th -20 downhill; 17th -10 net (the 45 ft crest is
      mid-hole — the linear elevation model cannot represent it, so
      the tee sits high and the green low; the crest itself is a
      broadcast feature, not a sim number).
    - Fairways are wide on a links (38 yd default; 13th narrowed to
      30, 4th 34, 17th 34) — width is the welcome, the wind is the
      punishment.
    - Pot bunkers: 115 revetted pots, all small (rx 12-16 ft,
      ry 10-12 ft) — one shot in, one shot out. Every greenside pot
      is placed outside the green circle (its centre more than the
      green radius + 3 yd from the green centre), because
      determine_lie() tests the green first; a pot inside the circle
      would never register. No bunker has s > yardage: project()
      clamps s to the green, so a "long" pot behind the green is
      undetectable — long pots sit beside the green instead.
    - The burn crosses 2 (at 170 and 300) and 14 (at 280, diagonal),
      modelled as narrow Water ellipses (20 ft along s, 90-100 ft
      across). The 2nd's second crossing at 300 is the decision the
      hole is built around: carry it or lay up short of it.
    - The sea is OB on the right of 8, 10, and 18 for the whole hole,
      and on the right of 17 (over the dune and right): ob_right_yd
      55.0 on those four holes (default 90 elsewhere).
    - No trees anywhere — a links has nothing to stop the wind.
    - Double green: holes 1 and 18 share one physical double green
      (left lobe = 1st pin, right lobe = 18th pin, spine between),
      each modelled with green_radius_ft 52 — the engine assumes one
      green per hole, so each hole gets its own centre on its own
      lobe. DOC INCONSISTENCY, flagged not fixed: hole 9's brief and
      the "Green complexes" section say the double green is shared by
      9 and 18 (and 9's brief says 9 and 1), while the "name and
      place" section and the 1st/18th briefs agree on 1 and 18 (the
      St. Andrews touch: 1st tee and 18th green in front of the
      clubhouse). This build follows 1 and 18; hole 9 gets its own
      wide, shallow green.
    - The Biarritz 3rd has a 60 yd deep green; the engine models
      greens as circles, so its green_radius_ft is 85 (~28 yd radius)
      to cover the depth — the front plateau must read as green, not
      fairway. The Punchbowl 12th (28 yd wide) and the Double
      Plateau 16th keep normal radii; the Alps 17th green is narrow
      (36 ft).
    - Rating: compute_rating_slope() is calibrated for Wyatt National
      (see its docstring) — the Dunmore number it returns is an
      estimate, not a USGA-method recompute like course-rating-v3.md.
      A proper Dunmore rating recompute is still owed.
    """
    return [
        _h(1, 4, 398, "The First Light", 210, 0, 0,
           bunkers=[Bunker(260, -12, 14, 10), Bunker(280, 14, 14, 10),
                    Bunker(300, -18, 12, 10), Bunker(320, 18, 12, 10),
                    Bunker(385, 18, 14, 10), Bunker(388, -20, 14, 10)],
           hazard_label="double_green", green_radius_ft=52.0),
        _h(2, 5, 562, "The Burn", 175, 0, -6,
           dogleg_at_yd=280, dogleg_angle_deg=25,
           water=[Water(170, 0, 20, 90), Water(300, 0, 20, 100)],
           bunkers=[Bunker(322, -16, 14, 10), Bunker(325, 16, 14, 10),
                    Bunker(340, -18, 12, 10), Bunker(380, 18, 12, 10),
                    Bunker(540, 0, 16, 12), Bunker(545, -18, 14, 10),
                    Bunker(548, 18, 14, 10)],
           hazard_label="burn_twice", drop_zone=(270, 10),
           green_radius_ft=51.0),
        _h(3, 3, 178, "The Biarritz", 130, 0, 0,
           bunkers=[Bunker(172, 33, 14, 10), Bunker(150, 30, 14, 10),
                    Bunker(148, -20, 12, 10), Bunker(158, 24, 12, 10)],
           hazard_label="biarritz", green_radius_ft=85.0),
        _h(4, 4, 445, "The Gauntlet", 40, 0, 25,
           bunkers=[Bunker(250, -8, 14, 10), Bunker(240, 18, 14, 10),
                    Bunker(300, -18, 12, 10), Bunker(320, 18, 12, 10),
                    Bunker(425, -18, 14, 10), Bunker(430, 18, 14, 10),
                    Bunker(438, -20, 14, 10)],
           hazard_label="into_the_wind", fairway_width_yd=34.0,
           green_radius_ft=49.0),
        _h(5, 4, 372, "The Nose", 240, 0, 0,
           bunkers=[Bunker(280, -8, 12, 10), Bunker(280, 0, 12, 10),
                    Bunker(280, 8, 12, 10), Bunker(300, -16, 12, 10),
                    Bunker(330, 16, 12, 10), Bunker(355, -18, 12, 10),
                    Bunker(358, 18, 12, 10), Bunker(366, -18, 12, 10)],
           hazard_label="principals_nose", green_radius_ft=40.0),
        _h(6, 5, 585, "The Gales", 30, 0, 0,
           bunkers=[Bunker(270, -16, 14, 10), Bunker(290, 16, 14, 10),
                    Bunker(310, -14, 14, 10), Bunker(330, 16, 14, 10),
                    Bunker(360, -18, 12, 10), Bunker(400, 18, 12, 10),
                    Bunker(560, -18, 14, 10), Bunker(565, 18, 14, 10),
                    Bunker(578, -18, 14, 10)],
           hazard_label="sahara", green_radius_ft=42.0),
        _h(7, 3, 214, "The Hollow", 60, 0, 0,
           bunkers=[Bunker(200, 14, 14, 10), Bunker(208, -20, 14, 10),
                    Bunker(195, -14, 12, 10), Bunker(205, 20, 12, 10)],
           hazard_label="dune_hollow", green_radius_ft=42.0),
        _h(8, 4, 431, "The Shore", 320, 0, -15,
           dogleg_at_yd=280, dogleg_angle_deg=-25,
           bunkers=[Bunker(260, 16, 14, 10), Bunker(290, -16, 14, 10),
                    Bunker(310, 16, 14, 10), Bunker(330, -16, 12, 10),
                    Bunker(350, 16, 12, 10), Bunker(415, 18, 14, 10),
                    Bunker(420, -18, 12, 10)],
           hazard_label="sea_right", ob_right_yd=55.0,
           green_radius_ft=42.0),
        _h(9, 4, 406, "The Return", 220, 0, -20,
           bunkers=[Bunker(270, -14, 14, 10), Bunker(290, 14, 14, 10),
                    Bunker(320, -18, 12, 10), Bunker(340, 18, 12, 10),
                    Bunker(385, 18, 14, 10), Bunker(395, -18, 12, 10)],
           hazard_label="front_right_pot", green_radius_ft=46.0),
        _h(10, 4, 424, "The Dunes", 140, 0, -25,
           dogleg_at_yd=260, dogleg_angle_deg=-20,
           bunkers=[Bunker(250, 16, 14, 10), Bunker(280, -14, 14, 10),
                    Bunker(300, 16, 14, 10), Bunker(320, -16, 12, 10),
                    Bunker(350, 18, 12, 10), Bunker(405, 18, 14, 10),
                    Bunker(410, -18, 12, 10)],
           hazard_label="sea_right", ob_right_yd=55.0,
           green_radius_ft=40.0),
        _h(11, 5, 578, "The Second Wind", 50, 0, 40,
           bunkers=[Bunker(270, -14, 14, 10), Bunker(290, 14, 14, 10),
                    Bunker(300, -16, 14, 10), Bunker(300, 16, 14, 10),
                    Bunker(340, -18, 12, 10), Bunker(380, 18, 12, 10),
                    Bunker(555, -18, 14, 10), Bunker(560, 18, 14, 10),
                    Bunker(570, -18, 14, 10)],
           hazard_label="wind_uphill", green_radius_ft=45.0),
        _h(12, 3, 165, "The Punchbowl", 185, 0, -20,
           bunkers=[Bunker(160, -24, 14, 10), Bunker(150, -12, 12, 10),
                    Bunker(152, 12, 12, 10), Bunker(158, 20, 12, 10)],
           hazard_label="punchbowl", green_radius_ft=42.0),
        _h(13, 4, 452, "The Anvil", 35, 0, 35,
           bunkers=[Bunker(240, -16, 14, 10), Bunker(240, 16, 14, 10),
                    Bunker(300, -18, 12, 10), Bunker(320, 18, 12, 10),
                    Bunker(432, -18, 14, 10), Bunker(438, 18, 14, 10),
                    Bunker(445, -18, 14, 10)],
           hazard_label="hardest_par4", fairway_width_yd=30.0,
           semi_rough_yd=5.0, green_radius_ft=42.0),
        _h(14, 4, 384, "The Dare", 95, 0, 0,
           water=[Water(280, 0, 20, 100)],
           bunkers=[Bunker(250, -16, 12, 10), Bunker(300, -16, 12, 10),
                    Bunker(330, 16, 12, 10), Bunker(368, -16, 12, 10),
                    Bunker(370, 16, 12, 10)],
           hazard_label="burn_280", drop_zone=(240, 10),
           green_radius_ft=38.0),
        _h(15, 5, 548, "The Downwinder", 230, 0, -8,
           bunkers=[Bunker(270, 16, 14, 10), Bunker(300, -14, 14, 10),
                    Bunker(320, 16, 14, 10), Bunker(340, -18, 12, 10),
                    Bunker(380, 18, 12, 10), Bunker(520, -16, 14, 10),
                    Bunker(525, 0, 14, 10), Bunker(530, 16, 14, 10)],
           hazard_label="downwind_eagle", green_radius_ft=48.0),
        _h(16, 3, 196, "The Plateau", 125, 0, 0,
           bunkers=[Bunker(176, 0, 16, 12), Bunker(190, -18, 12, 10),
                    Bunker(192, 18, 12, 10), Bunker(188, 24, 12, 10),
                    Bunker(170, -20, 12, 10)],
           hazard_label="double_plateau", green_radius_ft=42.0),
        _h(17, 4, 439, "The Alps", 310, 0, -10,
           bunkers=[Bunker(300, -12, 14, 10), Bunker(320, 14, 14, 10),
                    Bunker(340, -16, 12, 10), Bunker(380, 16, 12, 10),
                    Bunker(420, -16, 14, 10), Bunker(432, 14, 12, 10)],
           hazard_label="alps", ob_right_yd=55.0,
           fairway_width_yd=34.0, semi_rough_yd=5.0,
           green_radius_ft=36.0),
        _h(18, 4, 418, "The Homecoming", 215, 0, 20,
           bunkers=[Bunker(280, 16, 14, 10), Bunker(300, -14, 14, 10),
                    Bunker(320, -18, 12, 10), Bunker(340, 18, 12, 10),
                    Bunker(400, -18, 12, 10), Bunker(405, 18, 12, 10)],
           hazard_label="sea_right_home", ob_right_yd=55.0,
           green_radius_ft=52.0),
    ]


def compute_rating_slope(holes, par):
    """USGA-style course rating and slope, computed from the design.

    A transparent, simplified model — not the USGA's proprietary tables —
    with components an architect would recognise:

    - **Effective length**: yardage, plus 1.5 yd per foot of net uphill
      (uphill holes play longer, downhill shorter), plus 40 yd for a
      prevailing wind.
    - **Obstacle strokes**: bunkers 0.02 each, water hazards 0.15 each,
      tree clusters 0.05 each, tight out-of-bounds 0.10, narrow fairways
      (< 30 yd) 0.10, small greens (< 40 ft radius) 0.05.
    - **Rating** = 47.72 + effective_length * 0.00355 + obstacle * 0.35.
    - **Slope** = 129.0 + (rating - par) * 2.54 + obstacle * 1.55.

    The constants are calibrated to the three anchor points in
    `docs/course-rating-v3.md`: Wyatt National v2 computes **74.6 / 138**
    (the back-check — the rating doc §9 reproduces the same pair from
    the USGA method), v3 computes **76.1 / 142** (the single v3 number,
    used everywhere), and the tournament variant computes **77.1 / 149**.
    The variant's slope matches the Major week tier (149); its rating
    sits 0.6 below the tier's 77.7 because the variant prices only the
    geometric setup changes (narrowed fairways, smaller greens, extra
    bunkers), not the stimp / wind / pin / rough levers, which the
    rating function does not model. The previous constants (68.0 / 0.0008 / 0.4
    and 113 / 7.2 / 4.0) computed v3 as 74.9 / 141 — superseded by the
    rating recompute; 74.9 / 141 is retired, as is the web build's
    74.1 / 141, which no derivation reproduces.

    Why these constants, and what they are not:
    - The obstacle weight 0.35 is the rating doc's scratch weight
      (course-rating-v3.md §1/§6): obstacles hurt the scratch golfer
      at 0.35 of their bogey cost.
    - The per-yard coefficient 0.00355 is fitted to the v2→v3 length
      delta, not the USGA 1/220 — the sim's effective-length
      definition (yardage + 1.5 yd per foot of net elevation + 40 yd
      wind) is not the USGA effective playing length, so the
      coefficient that lands the rating delta on the derivation is
      smaller than 1/220.
    - The slope intercept 129.0 is fitted to all three anchors, not
      the USGA 113 standard-slope anchor: the model's obstacle term
      is a per-hole sum that jumps on the narrowed tournament setup
      (1.72 → 4.60), so a two-point fit through v2/v3 alone would
      price the tournament slope past the 155 maximum. The
      three-point fit keeps it at 149.
    - Calibration domain: Wyatt National v2, v3, and its tournament
      setup only. Do not trust these constants for a wildly different
      course — re-derive from that course's rating the same way.
    Harder designs — longer, narrower, more hazards — rate higher
    automatically, so difficulty becomes a variable the engine can
    play with.
    """
    yardage = sum(h.yardage for h in holes)
    uphill = sum(max(0.0, h.elev_green_ft - h.elev_tee_ft) for h in holes)
    downhill = sum(max(0.0, h.elev_tee_ft - h.elev_green_ft) for h in holes)
    effective_length = yardage + 1.5 * (uphill - downhill) + 40.0
    obstacle = 0.0
    for h in holes:
        obstacle += 0.02 * len(h.bunkers)
        obstacle += 0.15 * len(h.water)
        obstacle += 0.05 * len(h.trees)
        if h.ob_right_yd < 60:
            obstacle += 0.10
        if h.fairway_width_yd < 30:
            obstacle += 0.10
        if h.green_radius_ft < 40:
            obstacle += 0.05
    rating = 47.72 + effective_length * 0.00355 + obstacle * 0.35
    slope = 129.0 + (rating - par) * 2.54 + obstacle * 1.55
    return round(rating, 1), int(round(slope)), dict(
        effective_length_yd=round(effective_length),
        obstacle_strokes=round(obstacle, 2),
        uphill_ft=round(uphill), downhill_ft=round(downhill))


class Course:
    """A course: holes, par, rating/slope, and lie determination."""

    def __init__(self, course_id="wyatt_national", name="Wyatt National",
                 rating=None, slope=None, holes=None):
        self.id = course_id
        self.name = name
        self.holes = holes if holes is not None else build_wyatt_national()
        self.par = sum(h.par for h in self.holes)
        self.yardage = sum(h.yardage for h in self.holes)
        rating_c, slope_c, self.rating_detail = compute_rating_slope(
            self.holes, self.par)
        self.rating = rating if rating is not None else rating_c
        self.slope = slope if slope is not None else slope_c

    def hole(self, n: int) -> Hole:
        return self.holes[n - 1]

    def par_through(self, n: int) -> int:
        return sum(h.par for h in self.holes[:n])

    # -- lie determination (§2.5) -----------------------------------------
    def determine_lie(self, hole: Hole, x: float, y: float):
        """Final resting position -> (lie, in_water, ob).

        Tests, in order: green, bunkers, water, trees, fairway,
        semi-rough, rough.
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

        # Semi-rough (v3, course-design-v3.md §5.1): the rounded fairway
        # edge. A ball just off the fairway — inside the semi-rough band
        # — is in first cut, not rough. The s bound mirrors the fairway
        # test; in practice project() clamps s to the green, so a ball
        # past the green is classified by its distance from the green
        # centre, not by this bound.
        #
        # "semi" lives in sim/constants.py LIE_EFFECTS (dist 0.97,
        # spin 0.95, sig 1.15) — the spec's suggested factors, still
        # TO-BE-CONFIRMED against the lie table. physics.py and
        # decisions.py index that table with a hard lookup, so the entry
        # must stay in sync with this lie.
        if abs(lateral) <= hole.fairway_width_yd / 2.0 + hole.semi_rough_yd \
                and s <= hole.yardage + 10:
            return "semi", False, False

        # Rough: close to the fairway edge is light, deep is heavy.
        if abs(lateral) <= hole.fairway_width_yd / 2.0 + 8:
            return "rough_light", False, False
        return "rough_heavy", False, False


    def determine_lie_batch(self, hole: Hole, xs, ys):
        """Vectorized ``determine_lie`` for Monte Carlo arrays (§5.4).

        Returns (lies, in_water, ob) as numpy arrays. Same test order as
        the scalar version: OB -> water -> green -> bunkers -> trees ->
        fairway -> semi-rough -> rough.
        """
        import numpy as np

        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        n = xs.size
        lies = np.full(n, "rough_heavy", dtype=object)
        in_water = np.zeros(n, dtype=bool)
        ob = np.zeros(n, dtype=bool)

        # Project onto the centreline (vectorized, per segment).
        pts = hole.centreline_points()
        best_s = np.zeros(n)
        best_lat = np.zeros(n)
        best_d = np.full(n, np.inf)
        s_acc = 0.0
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            dx, dy = bx - ax, by - ay
            seg_len = math.hypot(dx, dy)
            t = ((xs - ax) * dx + (ys - ay) * dy) / (seg_len * seg_len)
            t = np.clip(t, 0.0, 1.0)
            px, py = ax + t * dx, ay + t * dy
            dist = np.hypot(xs - px, ys - py)
            cross = (xs - px) * dy - (ys - py) * dx
            lateral = np.where(cross <= 0, dist, -dist)
            s_here = s_acc + t * seg_len
            take = dist < best_d
            best_d = np.where(take, dist, best_d)
            best_s = np.where(take, s_here, best_s)
            best_lat = np.where(take, lateral, best_lat)
            s_acc += seg_len
        s, lateral = best_s, best_lat

        gx, gy = hole.green_centre()
        dist_green = np.hypot(xs - gx, ys - gy)
        green_r = hole.green_radius_ft / 3.0

        ob_mask = (lateral > hole.ob_right_yd) | (lateral < -90) | \
                  (s < -15) | (s > hole.yardage + 80)
        ob |= ob_mask

        water_mask = np.zeros(n, dtype=bool)
        for w in hole.water:
            water_mask |= ((s - w.s_yd) / (w.rx_ft / 3.0)) ** 2 + \
                          ((lateral - w.lateral_yd) / (w.ry_ft / 3.0)) ** 2 <= 1.0
        in_water |= water_mask & ~ob_mask

        green_mask = (dist_green <= green_r) & ~ob_mask & ~water_mask
        bunker_mask = np.zeros(n, dtype=bool)
        bunker_green_mask = np.zeros(n, dtype=bool)
        for b in hole.bunkers:
            rx = (b.rx_ft + 2.0) / 3.0
            ry = (b.ry_ft + 2.0) / 3.0
            hit = ((s - b.s_yd) / rx) ** 2 + ((lateral - b.lateral_yd) / ry) ** 2 <= 1.0
            bunker_mask |= hit
            if b.is_greenside:
                bunker_green_mask |= hit
        tree_mask = np.zeros(n, dtype=bool)
        for t in hole.trees:
            tree_mask |= np.hypot(s - t.s_yd, lateral - t.lateral_yd) <= t.r_ft / 3.0
        fairway_mask = (np.abs(lateral) <= hole.fairway_width_yd / 2.0) & \
                       (s <= hole.yardage + 10)
        # Semi-rough (v3): same s bound as the fairway test (vacuous in
        # practice — project() clamps s to the green — see determine_lie).
        # "semi" is in LIE_EFFECTS (spec factors, to-be-confirmed).
        semi_mask = (np.abs(lateral) <= hole.fairway_width_yd / 2.0
                     + hole.semi_rough_yd) & (s <= hole.yardage + 10)
        light_mask = np.abs(lateral) <= hole.fairway_width_yd / 2.0 + 8

        lies = np.where(ob_mask, "ob", lies)
        lies = np.where(water_mask & ~ob_mask, "water", lies)
        lies = np.where(green_mask, "green", lies)
        lies = np.where(bunker_mask & ~green_mask & ~water_mask & ~ob_mask,
                        np.where(bunker_green_mask, "bunker_green",
                                 "bunker_fairway"), lies)
        lies = np.where(tree_mask & ~bunker_mask & ~green_mask & ~water_mask
                        & ~ob_mask, "trees", lies)
        lies = np.where(fairway_mask & ~tree_mask & ~bunker_mask & ~green_mask
                        & ~water_mask & ~ob_mask, "fairway", lies)
        lies = np.where((lies == "rough_heavy") & semi_mask & ~tree_mask
                        & ~bunker_mask & ~green_mask & ~water_mask & ~ob_mask,
                        "semi", lies)
        lies = np.where((lies == "rough_heavy") & light_mask & ~tree_mask
                        & ~bunker_mask & ~green_mask & ~water_mask & ~ob_mask,
                        "rough_light", lies)
        return lies, in_water, ob

    def distance_to_pin(self, hole: Hole, x: float, y: float):
        """(along_yd, straight_yd) from a position to the green centre.

        ``along`` is the centreline arc remaining plus a lateral penalty —
        the right measure for a tee shot, which must follow the hole's
        routing (a dogleg's laser distance cuts the corner through trees).
        It is NOT a distance to the pin for a ball past the green (it
        collapses to ~0 there), so the engine clubs approaches and short
        game off ``straight``, the laser distance. ``straight`` is also
        used for events and stats.
        """
        s, lateral = hole.project(x, y)
        gx, gy = hole.green_centre()
        straight = math.hypot(gx - x, gy - y)
        along = max(0.0, hole.yardage - s) + abs(lateral) * 0.3
        return along, straight


def championship_variant():
    """Wyatt National (Tournament Setup) — the v3 course, set up harder.

    Option (b) from course-design-v3.md §5.2. The Black Tees variant is
    retired: v3 *is* the championship length, so +350 yards on top
    would be 7,952 yards. Instead this is the same yardages with
    26-yard fairways, 36-foot greens, and an extra fairway bunker at
    300 yards on every par 4 and par 5 — the "Major week" setup tier
    from docs/conditions-system.md, without inventing a longer course.
    The rating/slope are computed from the design, so the difficulty
    is real, not a label.
    """
    import copy
    holes = []
    for h in build_wyatt_national():
        h2 = copy.deepcopy(h)
        h2.fairway_width_yd = 26.0
        h2.green_radius_ft = 36.0
        if h.par in (4, 5):
            h2.bunkers = list(h2.bunkers) + [
                Bunker(300, -18 if h.hole % 2 else 18, 24, 14)]
        holes.append(h2)
    return Course(course_id="wyatt_national_tournament",
                  name="Wyatt National (Tournament Setup)", holes=holes)


WYATT_NATIONAL = Course()
DUNMORE_LINKS = Course(course_id="dunmore_links", name="Dunmore Links",
                       holes=build_dunmore_links())
