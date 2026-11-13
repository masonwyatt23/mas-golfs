"""Tests for Dunmore Links, the second course (course-two.md).

Run:  python -m unittest sim.tests.test_dunmore -v
"""

import unittest

from sim.course import DUNMORE_LINKS, build_dunmore_links
from sim.engine import RoundEngine


def _lie(course, hole_no, s_yd, lateral_yd):
    """Lie at a (s, lateral) position on a hole."""
    hole = course.hole(hole_no)
    x, y = hole.point_at(s_yd, lateral_yd)
    return course.determine_lie(hole, x, y)


class TestDunmoreCard(unittest.TestCase):
    def test_yardages(self):
        holes = build_dunmore_links()
        self.assertEqual(len(holes), 18)
        self.assertEqual(sum(h.yardage for h in holes[:9]), 3591)
        self.assertEqual(sum(h.yardage for h in holes[9:]), 3604)
        self.assertEqual(sum(h.yardage for h in holes), 7195)

    def test_par(self):
        holes = build_dunmore_links()
        self.assertEqual(sum(h.par for h in holes[:9]), 36)
        self.assertEqual(sum(h.par for h in holes[9:]), 36)
        self.assertEqual(sum(h.par for h in holes), 72)
        self.assertEqual([h.hole for h in holes if h.par == 3],
                         [3, 7, 12, 16])
        self.assertEqual([h.hole for h in holes if h.par == 5],
                         [2, 6, 11, 15])

    def test_names(self):
        holes = build_dunmore_links()
        self.assertEqual(
            [h.name for h in holes],
            ["The First Light", "The Burn", "The Biarritz", "The Gauntlet",
             "The Nose", "The Gales", "The Hollow", "The Shore",
             "The Return", "The Dunes", "The Second Wind",
             "The Punchbowl", "The Anvil", "The Dare", "The Downwinder",
             "The Plateau", "The Alps", "The Homecoming"])

    def test_pot_bunkers(self):
        holes = build_dunmore_links()
        total = sum(len(h.bunkers) for h in holes)
        # The doc says 110+ revetted pot bunkers; this build places 115.
        self.assertGreaterEqual(total, 110)
        self.assertEqual(total, 115)
        # All pots are small and deep: no fairway-sized bunker anywhere.
        for h in holes:
            for b in h.bunkers:
                self.assertLessEqual(b.rx_ft, 16)
                self.assertLessEqual(b.ry_ft, 12)
                self.assertLessEqual(b.s_yd, h.yardage)

    def test_no_trees(self):
        holes = build_dunmore_links()
        self.assertEqual(sum(len(h.trees) for h in holes), 0)

    def test_burn_and_sea(self):
        holes = build_dunmore_links()
        water_holes = {h.hole: len(h.water) for h in holes if h.water}
        self.assertEqual(water_holes, {2: 2, 14: 1})
        sea_holes = [h.hole for h in holes if h.ob_right_yd < 60]
        self.assertEqual(sea_holes, [8, 10, 17, 18])

    def test_double_green(self):
        holes = build_dunmore_links()
        # Holes 1 and 18 share one physical double green; the engine
        # models each lobe as its own green centre (see build docstring).
        self.assertEqual(holes[0].green_radius_ft, 52.0)
        self.assertEqual(holes[17].green_radius_ft, 52.0)

    def test_biarritz_green_depth(self):
        holes = build_dunmore_links()
        # The Biarritz green is 60 yd deep; the engine's circular green
        # needs a ~28 yd radius so the front plateau reads as green.
        self.assertEqual(holes[2].green_radius_ft, 85.0)

    def test_wind_rotation(self):
        holes = build_dunmore_links()
        azimuths = [h.azimuth_deg for h in holes]
        for a, b in zip(azimuths, azimuths[1:]):
            self.assertNotEqual(a, b)
        self.assertGreater(len(set(azimuths)), 10)

    def test_rating(self):
        # compute_rating_slope() is calibrated for Wyatt National; the
        # Dunmore number it returns is an estimate pending a proper
        # recompute like course-rating-v3.md. Pin the current output so
        # a recalibration is a deliberate change, not silent drift.
        # 74.6 - 3 = 71.6, inside the doc's ~71-73 scoring band for a +3.
        self.assertEqual(DUNMORE_LINKS.rating, 74.6)
        self.assertEqual(DUNMORE_LINKS.slope, 141)
        self.assertEqual(DUNMORE_LINKS.id, "dunmore_links")
        self.assertEqual(DUNMORE_LINKS.name, "Dunmore Links")


class TestDunmoreLies(unittest.TestCase):
    def test_burn_is_water_hole_2(self):
        self.assertEqual(_lie(DUNMORE_LINKS, 2, 300, 0)[0], "water")
        self.assertEqual(_lie(DUNMORE_LINKS, 2, 170, 0)[0], "water")
        self.assertTrue(_lie(DUNMORE_LINKS, 2, 300, 0)[1])
        # Between the two crossings is fairway, not water.
        self.assertEqual(_lie(DUNMORE_LINKS, 2, 250, 0)[0], "fairway")

    def test_burn_is_water_hole_14(self):
        self.assertEqual(_lie(DUNMORE_LINKS, 14, 280, 0)[0], "water")
        self.assertTrue(_lie(DUNMORE_LINKS, 14, 280, 0)[1])
        self.assertEqual(_lie(DUNMORE_LINKS, 14, 240, 0)[0], "fairway")

    def test_sea_is_ob(self):
        for hole_no in (8, 10, 17, 18):
            lie, _, ob = _lie(DUNMORE_LINKS, hole_no, 300, 60)
            self.assertEqual(lie, "ob")
            self.assertTrue(ob)
        # 40 yd right is deep rough, not OB — the sea is at 55.
        lie, _, ob = _lie(DUNMORE_LINKS, 8, 300, 40)
        self.assertEqual(lie, "rough_heavy")
        self.assertFalse(ob)

    def test_double_green_reads_as_green(self):
        self.assertEqual(_lie(DUNMORE_LINKS, 1, 398, 0)[0], "green")
        self.assertEqual(_lie(DUNMORE_LINKS, 18, 418, 0)[0], "green")

    def test_biarritz_plateaus_read_as_green(self):
        # Front plateau (18 yd short of the centre) and back plateau
        # are both putting surface on a 60 yd deep Biarritz green.
        self.assertEqual(_lie(DUNMORE_LINKS, 3, 160, 0)[0], "green")
        self.assertEqual(_lie(DUNMORE_LINKS, 3, 195, 0)[0], "green")

    def test_principals_nose_pot(self):
        # The centre pot of the Nose cluster at 280 is a fairway bunker.
        self.assertEqual(_lie(DUNMORE_LINKS, 5, 280, 0)[0],
                         "bunker_fairway")

    def test_front_pot_is_greenside(self):
        # The deep front pot on the 16th is within 45 yd of the green.
        self.assertEqual(_lie(DUNMORE_LINKS, 16, 176, 0)[0],
                         "bunker_green")
        # The front pot on the 2nd is greenside too.
        self.assertEqual(_lie(DUNMORE_LINKS, 2, 540, 0)[0],
                         "bunker_green")


class TestDunmoreRound(unittest.TestCase):
    def test_fast_mode_round_completes(self):
        eng = RoundEngine(course=DUNMORE_LINKS, fast_mode=True)
        self.assertEqual(eng.course.name, "Dunmore Links")
        res = eng.play_round()
        self.assertEqual(len(res.hole_scores), 18)
        self.assertEqual(sum(res.hole_scores), res.score)
        self.assertTrue(all(1 <= s <= 12 for s in res.hole_scores))
        self.assertGreater(len(res.events), 100)
        # The round was played at Dunmore, not Wyatt.
        round_starts = [e for e in res.events
                        if isinstance(e, dict) and e.get("type") == "round_start"]
        self.assertEqual(len(round_starts), 1)
        self.assertEqual(round_starts[0]["course"]["name"], "Dunmore Links")
        self.assertEqual(round_starts[0]["course"]["yardage"], 7195)


if __name__ == "__main__":
    unittest.main()
