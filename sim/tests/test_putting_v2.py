"""Putting v2 tests (putting-model-v2.md §§1-2, 2.5).

Run:  python -m unittest sim.tests.test_putting_v2 -v

The solver is deterministic (no RNG): every solve here takes the outcome
as an input, so the tests pin the solver's conditioning on the outcome,
not the outcome draw. The one v1 behaviour under test is the tap-in
form-multiplier drift flagged in the design doc — that test is marked
expectedFailure until ``putt()`` is fixed (see the test).
"""

import math
import unittest

import numpy as np

from sim.course import WYATT_NATIONAL
from sim.greens import Green, from_green_local, green_for_hole, to_green_local
from sim.putting import (
    build_putt_read,
    build_putt_result,
    classify_miss,
    ideal_start_line,
    measure_break,
    nominal_pace_v0,
    predicted_path,
    putt as putt_model,
    roll_putt,
    sample_path,
    solve_actual_path,
)
from sim.rng import Rng


def _stop_dist_framed(path, ball_ft, pin_ft):
    """Stop distance from the pin, from a putt-frame path.

    In putt frame the pin sits at (distance, 0); the last path point is
    the rest point, so the stop distance is its distance from (dist, 0).
    """
    dist = math.hypot(pin_ft[0] - ball_ft[0], pin_ft[1] - ball_ft[1])
    x, y = path[-1]
    return math.hypot(x - dist, y)


class TestGreens(unittest.TestCase):
    def test_deterministic(self):
        a = green_for_hole(12).heightfield()
        b = green_for_hole(12).heightfield()
        np.testing.assert_array_equal(a, b)

    def test_all_18_build(self):
        for n in range(1, 19):
            g = green_for_hole(n)
            h = g.heightfield()
            self.assertEqual(h.dtype, np.int16)
            self.assertEqual(h.min(), 0)
            self.assertEqual(h.shape, g.grid_shape)
            self.assertGreater(h.max(), 0)

    def test_height_falls_along_fall_line(self):
        # Two points 10 and 25 ft from the centre along the fall line,
        # on the same tier side: the further (more downhill) point must
        # be lower. This holds even on the stepped greens, where a naive
        # centre-vs-edge check would be fooled by the tier step.
        for n in range(1, 19):
            g = green_for_hole(n)
            fx, fy = g.fall_unit
            near = g.height_at(10 * fx, 10 * fy)
            far = g.height_at(25 * fx, 25 * fy)
            self.assertLess(far, near, f"hole {n}")

    def test_gradient_points_uphill(self):
        # On the flattest green (12, fall 0 deg = toward +X) the gradient
        # at the centre points uphill, i.e. against the fall direction.
        g = green_for_hole(12)
        gx, gy = g.gradient_at(0.0, 0.0)
        fx, fy = g.fall_unit
        self.assertLess(gx * fx + gy * fy, 0.0)
        # Hole 2 falls toward +Y: the y-gradient at the centre is negative.
        g2 = green_for_hole(2)
        _, gy2 = g2.gradient_at(0.0, 0.0)
        self.assertLess(gy2, 0.0)

    def test_payload_roundtrip(self):
        g = green_for_hole(12)
        p = g.payload()
        g2, h = Green.from_payload(p)
        np.testing.assert_array_equal(h, g.heightfield())
        self.assertEqual(g2.hole_no, 12)
        self.assertEqual(g2.slope_pct, g.slope_pct)
        self.assertEqual(g2.fall_dir_deg, g.fall_dir_deg)

    def test_coordinate_conversion_inverts(self):
        hole = WYATT_NATIONAL.hole(12)
        for x, y in [(hole.yardage, 0.0), (hole.yardage - 10, 5.0),
                     (0.0, 0.0)]:
            gx, gy = to_green_local(hole, x, y)
            bx, by = from_green_local(hole, gx, gy)
            self.assertAlmostEqual(bx, x, places=9)
            self.assertAlmostEqual(by, y, places=9)

    def test_green_radius_from_hole(self):
        # Holes 4 and 11 are the 45 ft greens; the default is 42 ft.
        self.assertEqual(WYATT_NATIONAL.hole(4).green_radius_ft, 45.0)
        self.assertEqual(WYATT_NATIONAL.hole(12).green_radius_ft, 42.0)


class TestRollPhysics(unittest.TestCase):
    def test_flat_green_nominal_pace_captures(self):
        flat = Green(course_id="test", hole_no=99, slope_pct=0.0,
                     fall_dir_deg=0.0, radius_ft=42.0, tiers=())
        v0 = nominal_pace_v0(14.0, 11.0)
        r = roll_putt(flat, (-14.0, 0.0), (0.0, 0.0), 0.0, v0, 11.0)
        self.assertTrue(r["captured"])
        self.assertLess(r["closest_in"], 2.125)

    def test_flat_green_short_putt_dies_short(self):
        # Energy check: v0 = 3.5 ft/s on a stimp-11 flat green rolls
        # v^2 / (2 mu g) = 3.81 ft — so a 14-footer stops ~10.3 ft short.
        flat = Green(course_id="test", hole_no=99, slope_pct=0.0,
                     fall_dir_deg=0.0, radius_ft=42.0, tiers=())
        r = roll_putt(flat, (-14.0, 0.0), (0.0, 0.0), 0.0, 3.5, 11.0)
        self.assertFalse(r["captured"])
        self.assertAlmostEqual(r["stop_dist_ft"], 10.28, delta=0.5)

    def test_ball_never_rolls_back(self):
        # Regression: a ball that dies on a steep uphill slope (hole 16,
        # pin on the 14 in tier step) used to be re-accelerated downhill
        # by gravity and roll back 23 ft. A ball at rest stays at rest.
        g16 = green_for_hole(16, radius_ft=42.0)
        r = roll_putt(g16, (-10.0, -10.0), (0.0, 0.0), 45.0, 10.29, 11.0)
        self.assertTrue(r["captured"])
        self.assertLess(r["stop_dist_ft"], 1.0)
        self.assertLess(len(r["path"]), 100)


class TestPredictedPath(unittest.TestCase):
    def test_deterministic_and_outcome_free(self):
        # The preview is computed from the ideal line alone. Two
        # different drawn outcomes (one made, one missed) must not
        # change it, and calling it twice must give the same path.
        g = green_for_hole(12, radius_ft=42.0)
        ball, pin = (-14.0, 0.0), (0.0, 0.0)
        p1 = predicted_path(g, ball, pin, 11.0)
        p2 = predicted_path(g, ball, pin, 11.0)
        self.assertEqual(p1, p2)
        made = putt_model(Rng(7), 14.0, 11.0)
        missed = putt_model(Rng(1), 14.0, 11.0)
        self.assertTrue(made["made"] or missed["made"])
        self.assertTrue(made["made"] != missed["made"])
        r1 = build_putt_read(g, ball, pin, 14.0, 11.0)
        r2 = build_putt_read(g, ball, pin, 14.0, 11.0)
        self.assertEqual(r1["predicted_path"], r2["predicted_path"])
        self.assertEqual(r1["make_pct"], r2["make_pct"])

    def test_flat_green_preview_is_straight(self):
        flat = Green(course_id="test", hole_no=99, slope_pct=0.0,
                     fall_dir_deg=0.0, radius_ft=42.0, tiers=())
        p = predicted_path(flat, (-14.0, 0.0), (0.0, 0.0), 11.0)
        self.assertEqual(p["break_ft"], 0.0)
        self.assertEqual(p["break_dir"], "straight")

    def test_cross_slope_preview_breaks(self):
        # Hole 3 falls toward +X (the golfer's right, putting from -Y):
        # the preview line aims left and the path breaks left-to-right.
        g3 = green_for_hole(3, radius_ft=42.0)
        p = predicted_path(g3, (0.0, -15.0), (0.0, 0.0), 11.0)
        self.assertGreater(p["break_ft"], 0.3)
        self.assertEqual(p["break_dir"], "left_to_right")
        self.assertGreater(p["start_deg"], 90.0)  # aimed left of straight

    def test_ideal_line_reaches_the_cup(self):
        # The ideal line is the line that would hole the putt: it must
        # come within the cup's radius, not die short (the old nominal-
        # pace-only search died 2 ft short on steep uphill putts).
        g16 = green_for_hole(16, radius_ft=42.0)
        ideal = ideal_start_line(g16, (-10.0, -10.0), (0.0, 0.0), 11.0)
        self.assertLess(ideal["closest_in"], 2.125)


class TestActualPath(unittest.TestCase):
    def test_made_path_ends_at_the_pin(self):
        g = green_for_hole(12, radius_ft=42.0)
        ball, pin = (-14.0, 0.0), (0.0, 0.0)
        s = solve_actual_path(g, ball, pin, True, 0.0, "good", 11.0)
        self.assertFalse(s["solver_fallback"])
        self.assertEqual(s["edge_class"], "made")
        self.assertFalse(s["lip"])
        self.assertEqual(s["closest_in"], 0.0)
        self.assertLess(_stop_dist_framed(s["path"], ball, pin), 0.25)

    def test_missed_path_matches_the_leave(self):
        g = green_for_hole(12, radius_ft=42.0)
        ball, pin = (-14.0, 0.0), (0.0, 0.0)
        s = solve_actual_path(g, ball, pin, False, 1.1, "good", 11.0)
        self.assertFalse(s["solver_fallback"])
        stop = _stop_dist_framed(s["path"], ball, pin)
        self.assertAlmostEqual(stop, 1.1, delta=0.75)
        self.assertGreater(stop, 0.25)  # it did not drop

    def test_missed_long_runs_past(self):
        g3 = green_for_hole(3, radius_ft=42.0)
        ball, pin = (0.0, -15.0), (0.0, 0.0)
        s = solve_actual_path(g3, ball, pin, False, 2.5, "long", 11.0)
        self.assertFalse(s["solver_fallback"])
        self.assertGreater(s["past_hole_ft"], 0.0)
        stop = _stop_dist_framed(s["path"], ball, pin)
        self.assertAlmostEqual(stop, 2.5, delta=0.75)

    def test_missed_short_dies_early(self):
        flat = Green(course_id="test", hole_no=99, slope_pct=0.0,
                     fall_dir_deg=0.0, radius_ft=42.0, tiers=())
        ball, pin = (-2.0, 0.0), (0.0, 0.0)
        s = solve_actual_path(flat, ball, pin, False, 1.0, "short", 11.0)
        self.assertFalse(s["solver_fallback"])
        self.assertEqual(s["past_hole_ft"], 0.0)
        stop = _stop_dist_framed(s["path"], ball, pin)
        self.assertAlmostEqual(stop, 1.0, delta=0.75)

    def test_made_on_stepped_green(self):
        # Hole 16's pin sits on the 14 in tier step: the solver must
        # find a firm line that climbs it instead of falling back.
        g16 = green_for_hole(16, radius_ft=42.0)
        ball, pin = (-10.0, -10.0), (0.0, 0.0)
        s = solve_actual_path(g16, ball, pin, True, 0.0, "good", 11.0)
        self.assertFalse(s["solver_fallback"])
        self.assertEqual(s["edge_class"], "made")
        self.assertLess(_stop_dist_framed(s["path"], ball, pin), 0.25)

    def test_downhill_long_miss_matches_leave(self):
        g = green_for_hole(12, radius_ft=42.0)
        ball, pin = (-20.0, 0.0), (0.0, 0.0)
        s = solve_actual_path(g, ball, pin, False, 3.0, "long", 11.0)
        self.assertFalse(s["solver_fallback"])
        self.assertGreater(s["past_hole_ft"], 0.0)
        stop = _stop_dist_framed(s["path"], ball, pin)
        self.assertAlmostEqual(stop, 3.0, delta=0.75)


class TestBreakMeasured(unittest.TestCase):
    def test_break_is_measured_not_drawn(self):
        # The v1 draw for this seed/distance draws 1.05 ft of break —
        # but the same putt on a flat green, integrated, breaks 0.0.
        # The solver's break comes from the path, never from the draw.
        flat = Green(course_id="test", hole_no=99, slope_pct=0.0,
                     fall_dir_deg=0.0, radius_ft=42.0, tiers=())
        res = putt_model(Rng(1), 14.0, 11.0)
        self.assertGreater(res["break_ft"], 0.3)
        s = solve_actual_path(flat, (-14.0, 0.0), (0.0, 0.0),
                              res["made"], res["leave_ft"], res["speed"],
                              11.0)
        self.assertEqual(s["break_ft"], 0.0)
        self.assertEqual(s["break_dir"], "straight")

    def test_solved_break_is_deterministic(self):
        g3 = green_for_hole(3, radius_ft=42.0)
        ball, pin = (0.0, -15.0), (0.0, 0.0)
        a = solve_actual_path(g3, ball, pin, True, 0.0, "good", 11.0)
        b = solve_actual_path(g3, ball, pin, True, 0.0, "good", 11.0)
        self.assertEqual(a["break_ft"], b["break_ft"])
        self.assertEqual(a["break_dir"], b["break_dir"])
        self.assertEqual(a["path"], b["path"])

    def test_measure_break_ignores_rollout(self):
        # A straight putt on a flat green has zero break even though
        # the raw integrated path continues past the cup; the break is
        # measured on the approach only.
        flat = Green(course_id="test", hole_no=99, slope_pct=0.0,
                     fall_dir_deg=0.0, radius_ft=42.0, tiers=())
        r = roll_putt(flat, (-14.0, 0.0), (0.0, 0.0), 0.0,
                      nominal_pace_v0(14.0, 11.0), 11.0)
        b, d = measure_break(r["path"], (-14.0, 0.0), (0.0, 0.0))
        self.assertEqual(b, 0.0)
        self.assertEqual(d, "straight")


class TestLipClasses(unittest.TestCase):
    def test_classify_miss_bands(self):
        self.assertEqual(classify_miss(2.5), (True, "lip"))
        self.assertEqual(classify_miss(2.9), (True, "lip"))
        self.assertEqual(classify_miss(3.0), (False, "burned_edge"))
        self.assertEqual(classify_miss(4.5), (False, "burned_edge"))
        self.assertEqual(classify_miss(6.0), (False, "missed"))
        self.assertEqual(classify_miss(9.0), (False, "missed"))

    def test_solved_lip_matches_closest_approach(self):
        # The lip flag and edge class must agree with the measured
        # closest approach on every solved miss.
        cases = [
            (green_for_hole(12, radius_ft=42.0), (-14.0, 0.0),
             (0.0, 0.0), False, 1.1, "good"),
            (green_for_hole(3, radius_ft=42.0), (0.0, -15.0),
             (0.0, 0.0), False, 2.5, "long"),
            (green_for_hole(12, radius_ft=42.0), (-20.0, 0.0),
             (0.0, 0.0), False, 3.0, "long"),
        ]
        for g, ball, pin, made, leave, pace in cases:
            s = solve_actual_path(g, ball, pin, made, leave, pace, 11.0)
            self.assertEqual(s["lip"], s["closest_in"] < 3.0)
            if s["closest_in"] < 3.0:
                self.assertEqual(s["edge_class"], "lip")
            elif s["closest_in"] < 6.0:
                self.assertEqual(s["edge_class"], "burned_edge")
            else:
                self.assertEqual(s["edge_class"], "missed")


class TestFormMultiplier(unittest.TestCase):
    def test_putt_read_gates_form_by_distance(self):
        # Spec §3.6: the form multiplier applies only to putts over
        # 10 ft. The v2 read implements the gate in the one place.
        g = green_for_hole(12, radius_ft=42.0)
        short_a = build_putt_read(g, (-5.0, 0.0), (0.0, 0.0), 5.0, 11.0,
                                  form_putt_mult=0.5)
        short_b = build_putt_read(g, (-5.0, 0.0), (0.0, 0.0), 5.0, 11.0,
                                  form_putt_mult=1.0)
        self.assertEqual(short_a["make_pct"], short_b["make_pct"])
        long_a = build_putt_read(g, (-20.0, 0.0), (0.0, 0.0), 20.0, 11.0,
                                 form_putt_mult=0.5)
        long_b = build_putt_read(g, (-20.0, 0.0), (0.0, 0.0), 20.0, 11.0,
                                 form_putt_mult=1.0)
        self.assertLess(long_a["make_pct"], long_b["make_pct"])

    @unittest.expectedFailure
    def test_v1_putt_still_applies_form_to_tap_ins(self):
        # DRIFT (design doc §2.5): v1 ``putt()`` applies
        # ``form_putt_mult`` to ALL putts, including tap-ins — spec §3.6
        # says it applies only over 10 ft. This test asserts the spec
        # behaviour (a cold tap-in makes at the same rate as a neutral
        # one); it is expected to FAIL until ``putt()`` is fixed. The
        # fix is one line in ``putt()`` — NOT applied here, because
        # ``putt()`` is the frozen v1 contract owned by the calibration
        # work. When the fix lands, remove this decorator.
        n = 2000
        cold = sum(putt_model(Rng(1000 + i), 5.0, 11.0,
                              form_putt_mult=0.5)["made"]
                   for i in range(n))
        neutral = sum(putt_model(Rng(1000 + i), 5.0, 11.0,
                                 form_putt_mult=1.0)["made"]
                      for i in range(n))
        self.assertEqual(cold, neutral)


class TestEventShapes(unittest.TestCase):
    def test_putt_read_shape(self):
        g = green_for_hole(12, radius_ft=42.0)
        r = build_putt_read(g, (-14.0, 0.0), (0.0, 0.0), 14.0, 11.0)
        self.assertEqual(r["distance_ft"], 14.0)
        self.assertEqual(r["distance_in"], 168)
        self.assertIn(r["break_dir"],
                      ("straight", "left_to_right", "right_to_left"))
        self.assertGreater(r["make_pct"], 0.0)
        self.assertLess(r["make_pct"], 1.0)
        self.assertLessEqual(len(r["predicted_path"]), 60)
        self.assertFalse(r["is_comebacker"])

    def test_putt_result_shape_and_passthrough(self):
        g = green_for_hole(12, radius_ft=42.0)
        ball, pin = (-14.0, 0.0), (0.0, 0.0)
        read = build_putt_read(g, ball, pin, 14.0, 11.0)
        res = putt_model(Rng(1), 14.0, 11.0)
        ext = build_putt_result(g, ball, pin, res, 11.0,
                                make_pct=read["make_pct"])
        # The pre-stroke make % is passed through, never recomputed
        # after the outcome.
        self.assertEqual(ext["make_pct"], read["make_pct"])
        self.assertEqual(ext["made"], res["made"])
        self.assertEqual(ext["speed"], res["speed"])
        self.assertLessEqual(len(ext["path"]), 60)
        for key in ("distance_ft", "break_ft", "break_dir", "leave_ft",
                    "pace_ft_s", "past_hole_ft", "lip", "closest_in",
                    "edge_class"):
            self.assertIn(key, ext)

    def test_sample_path_caps_at_60(self):
        # A 200-point dense path over 30 ft downsamples to <= 60 points
        # and keeps the first and last points.
        dense = [(float(i) * 0.15, 0.0) for i in range(200)]
        out = sample_path(dense)
        self.assertLessEqual(len(out), 60)
        self.assertEqual(out[0], [0.0, 0.0])
        self.assertEqual(out[-1], [round(199 * 0.15, 2), 0.0])


if __name__ == "__main__":
    unittest.main()
