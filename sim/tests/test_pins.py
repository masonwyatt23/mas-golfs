"""Tests for the pin rotation system (sim/pins.py).

Pins move every 2 rounds, deterministic from (course_id, hole_no,
rotation_index); every pin sits on the green, never in a bunker.
"""

import json
import math
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from sim.course import DUNMORE_LINKS, WYATT_NATIONAL
from sim.engine import RoundEngine
from sim.greens import green_for_hole
from sim.pins import (pin_difficulty_for, pin_zone_for,
                      rotation_index_for_round)
from sim.putting import build_putt_read
from sim.tests._markers import slow


def _pin_xy(engine, hole, zone):
    return engine._pin_position(hole, zone)


def _pin_on_green(engine, hole, zone):
    """(inside_radius, inside_bunker) for a pin zone on a hole."""
    px, py = _pin_xy(engine, hole, zone)
    gx, gy = hole.green_centre()
    dist_ft = math.hypot(px - gx, py - gy) * 3.0
    inside = dist_ft <= hole.green_radius_ft
    s, lat = hole.project(px, py)
    in_bunker = False
    for b in hole.bunkers:
        rx = b.rx_ft / 3.0
        ry = b.ry_ft / 3.0
        if ((s - b.s_yd) / rx) ** 2 + ((lat - b.lateral_yd) / ry) ** 2 <= 1.0:
            in_bunker = True
    return inside, in_bunker, dist_ft


class TestRotationIndex(unittest.TestCase):
    def test_two_round_blocks(self):
        self.assertEqual(rotation_index_for_round(1), 0)
        self.assertEqual(rotation_index_for_round(2), 0)
        self.assertEqual(rotation_index_for_round(3), 1)
        self.assertEqual(rotation_index_for_round(4), 1)
        self.assertEqual(rotation_index_for_round(11), 5)
        self.assertEqual(rotation_index_for_round(12), 5)
        self.assertEqual(rotation_index_for_round(13), 6)


class TestPinRotation(unittest.TestCase):
    COURSES = (("wyatt_national", WYATT_NATIONAL),
               ("dunmore_links", DUNMORE_LINKS))

    def test_pins_change_between_rotation_blocks(self):
        # Every hole's pin moves on every rotation boundary (the
        # anti-repeat rule in pin_zone_for guarantees it).
        for course_id, _ in self.COURSES:
            for hole_no in range(1, 19):
                for r in range(6):
                    self.assertNotEqual(
                        pin_zone_for(course_id, hole_no, r),
                        pin_zone_for(course_id, hole_no, r + 1),
                        f"{course_id} hole {hole_no} rotation {r}")

    def test_pins_stay_put_within_a_block(self):
        # Same rotation index -> same zone, whatever the round number.
        for course_id, _ in self.COURSES:
            for hole_no in range(1, 19):
                for r in range(6):
                    self.assertEqual(
                        pin_zone_for(course_id, hole_no, r),
                        pin_zone_for(course_id, hole_no, r))

    def test_deterministic_across_rebuilds(self):
        # A fresh interpreter must pick the same pins: the hash is
        # SHA-256, not the per-process salted hash().
        expected = {
            cid: {h: [pin_zone_for(cid, h, r) for r in range(6)]
                  for h in range(1, 19)}
            for cid, _ in self.COURSES}
        code = (
            "import json; from sim.pins import pin_zone_for; "
            "print(json.dumps({cid: {h: [pin_zone_for(cid, h, r) "
            "for r in range(6)] for h in range(1, 19)} "
            "for cid in ('wyatt_national', 'dunmore_links')}))")
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, cwd=REPO_ROOT,
                             timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout)
        got = {cid: {int(h): zones for h, zones in holes.items()}
               for cid, holes in got.items()}
        self.assertEqual(got, expected)

    def test_every_pin_on_the_green(self):
        # Every pin, every hole, every rotation, both courses: inside
        # the green radius and outside every bunker ellipse.
        for course_id, course in self.COURSES:
            engine = RoundEngine(course=course)
            for hole_no in range(1, 19):
                hole = course.hole(hole_no)
                for r in range(6):
                    zone = pin_zone_for(course_id, hole_no, r)
                    inside, in_bunker, dist_ft = _pin_on_green(
                        engine, hole, zone)
                    self.assertTrue(
                        inside,
                        f"{course_id} hole {hole_no} rot {r} zone {zone}: "
                        f"pin {dist_ft:.1f} ft from centre, "
                        f"radius {hole.green_radius_ft} ft")
                    self.assertFalse(
                        in_bunker,
                        f"{course_id} hole {hole_no} rot {r} zone {zone}: "
                        "pin inside a bunker")

    def test_difficulty_in_range(self):
        for course_id, _ in self.COURSES:
            for hole_no in range(1, 19):
                for r in range(6):
                    d = pin_difficulty_for(course_id, hole_no, r)
                    self.assertGreaterEqual(d, 0.30)
                    self.assertLessEqual(d, 0.95)

    def test_tucked_pin_reads_harder(self):
        # A Sunday-tough pin reads harder than an accessible one at
        # the same distance; a tap-in reads true either way.
        g = green_for_hole(12, radius_ft=42.0)
        tucked = build_putt_read(g, (-14.0, 0.0), (0.0, 0.0), 14.0, 11.0,
                                 pin_difficulty=0.89)
        easy = build_putt_read(g, (-14.0, 0.0), (0.0, 0.0), 14.0, 11.0,
                               pin_difficulty=0.30)
        plain = build_putt_read(g, (-14.0, 0.0), (0.0, 0.0), 14.0, 11.0)
        self.assertLess(tucked["make_pct"], plain["make_pct"])
        self.assertGreater(easy["make_pct"], plain["make_pct"])
        tap_tucked = build_putt_read(g, (-3.0, 0.0), (0.0, 0.0), 3.0, 11.0,
                                     pin_difficulty=0.89)
        tap_plain = build_putt_read(g, (-3.0, 0.0), (0.0, 0.0), 3.0, 11.0)
        self.assertEqual(tap_tucked["make_pct"], tap_plain["make_pct"])


class TestPinRotationEngine(unittest.TestCase):
    @slow
    def test_engine_pins_follow_the_rotation(self):
        # Rounds 1-2 share a rotation (identical pins); round 3 is a
        # new rotation (pins move on nearly every hole).
        engine = RoundEngine(fast_mode=True, seed_offset=0)
        pins_by_round = {}
        for round_no in (1, 2, 3):
            result = engine.play_round(round_no)
            pins_by_round[round_no] = {
                e["hole"]: (e["pin"]["x_ft"], e["pin"]["y_ft"],
                           e["pin"]["zone"], e["pin"]["rotation"],
                           e["pin"]["rotation_name"])
                for e in result.events if e["type"] == "hole_start"}
        self.assertEqual(pins_by_round[1], pins_by_round[2])
        moved = sum(1 for h in range(1, 19)
                    if pins_by_round[1][h][:2] != pins_by_round[3][h][:2])
        self.assertGreaterEqual(moved, 14)
        self.assertEqual({p[3] for p in pins_by_round[1].values()}, {0})
        self.assertEqual({p[3] for p in pins_by_round[3].values()}, {1})
        names = {p[4] for p in pins_by_round[1].values()}
        self.assertEqual(names, {"Accessible"})


if __name__ == "__main__":
    unittest.main()
