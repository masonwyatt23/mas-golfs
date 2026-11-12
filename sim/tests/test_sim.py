"""Tests for the Mas Golfs simulation engine (spec §10 ship gates).

Run:  python -m unittest discover -s sim/tests -v
"""

import math
import unittest

import numpy as np

from sim import constants as C
from sim.conditions import (ConditionsEngine, firmness_label,
                           green_spin_factor, roll_mu)
from sim.course import (WYATT_NATIONAL, Course, championship_variant,
                        compute_rating_slope)
from sim.decisions import (allowed_shot_types, decide, generate_candidates,
                           risk_threshold, Situation)
from sim.engine import RoundEngine
from sim.fifty_nine_watch import (FiftyNineWatch, probability_break_60,
                                  STATUS_GONE, STATUS_OFF_PACE,
                                  STATUS_ON_PACE, STATUS_ON_THE_LINE,
                                  STATUS_SECURED)
from sim.handicap import differential, form_from_scores, whs_index
from sim.learning import GolferModel, LearningLoop, ShotRecord
from sim.physics import (apply_roll, classify_contact, delivery_to_launch,
                         draw_delivery, fly_shot)
from sim.putting import make_probability, putt as putt_model
from sim.rng import Rng, seed_for_round
from sim.strokes_gained import baseline_strokes, strokes_gained


def make_situation(**over):
    hole = WYATT_NATIONAL.hole(over.pop("hole_no", 7))
    sit = Situation(
        hole=hole, ball_x=0.0, ball_y=0.0, lie="fairway", distance_yd=150.0,
        distance_straight_yd=150.0, elevation_ft=0.0, wind_mph=5.0,
        wind_effect="calm", wind_along_mph=0.0, wind_lateral_mph=0.0,
        hazard="", pin_x=hole.yardage, pin_y=0.0, hole_no=7, holes_left=12,
        strokes_vs_59_pace=0.0, temp_f=62.0, firmness=0.6, green_speed=11.0)
    for k, v in over.items():
        setattr(sit, k, v)
    return sit


class TestRng(unittest.TestCase):
    def test_deterministic(self):
        a, b = Rng(42), Rng(42)
        self.assertEqual([a.random() for _ in range(100)],
                         [b.random() for _ in range(100)])

    def test_seed_for_round_stable(self):
        self.assertEqual(seed_for_round(7), seed_for_round(7))
        self.assertNotEqual(seed_for_round(7), seed_for_round(8))

    def test_gauss_mean(self):
        rng = Rng(1)
        xs = [rng.gauss(10, 2) for _ in range(5000)]
        self.assertAlmostEqual(sum(xs) / len(xs), 10, delta=0.15)


class TestPhysics(unittest.TestCase):
    def test_driver_carry_in_range(self):
        rng = Rng(7)
        carries = []
        for _ in range(50):
            d = draw_delivery(rng, "driver", "full", 1.0, "straight", False, "tee")
            q = classify_contact(d, rng)
            launch = delivery_to_launch(d, "driver", q, "tee", 0.0, rng)
            fl = fly_shot(launch)
            carries.append(float(fl.carry_yd[0]))
        mean_carry = sum(carries) / len(carries)
        # Gapping carry is 268; physics should land within ~10%.
        self.assertGreater(mean_carry, 240)
        self.assertLess(mean_carry, 295)

    def test_driver_ball_speed(self):
        rng = Rng(7)
        speeds = []
        for _ in range(200):
            d = draw_delivery(rng, "driver", "full", 1.0, "straight", False, "tee")
            q = classify_contact(d, rng)
            speeds.append(delivery_to_launch(d, "driver", q, "tee", 0.0, rng)
                          .ball_speed_mph)
        self.assertAlmostEqual(sum(speeds) / len(speeds), 161, delta=6)

    def test_wedge_carry(self):
        rng = Rng(7)
        carries = []
        for _ in range(30):
            d = draw_delivery(rng, "PW", "full", 1.0, "straight", False, "fairway")
            q = classify_contact(d, rng)
            launch = delivery_to_launch(d, "PW", q, "fairway", 0.0, rng)
            fl = fly_shot(launch)
            carries.append(float(fl.carry_yd[0]))
        mean_carry = sum(carries) / len(carries)
        self.assertGreater(mean_carry, 115)
        self.assertLess(mean_carry, 155)

    def test_thin_lowers_spin(self):
        rng = Rng(3)
        d = draw_delivery(rng, "7-iron", "full", 1.0, "straight", False, "fairway")
        pure = delivery_to_launch(d, "7-iron", "pure", "fairway", 0.0, rng)
        thin = delivery_to_launch(d, "7-iron", "thin", "fairway", 0.0, rng)
        self.assertLess(thin.spin_rpm, pure.spin_rpm * 0.8)
        self.assertLess(thin.launch_deg, pure.launch_deg)

    def test_chunk_loses_carry(self):
        rng = Rng(3)
        d = draw_delivery(rng, "7-iron", "full", 1.0, "straight", False, "fairway")
        pure = delivery_to_launch(d, "7-iron", "pure", "fairway", 0.0, rng)
        chunk = delivery_to_launch(d, "7-iron", "chunk", "fairway", 0.0, rng)
        fl_pure = fly_shot(pure)
        fl_chunk = fly_shot(chunk)
        self.assertLess(float(fl_chunk.carry_yd[0]),
                        float(fl_pure.carry_yd[0]) * 0.92)

    def test_gear_effect_toe_fades(self):
        # Toe strike (+x) opens the face -> fade -> curve to the golfer's
        # right (+z) for a left-hander (§2.4).
        rng = Rng(3)
        d = draw_delivery(rng, "7-iron", "full", 1.0, "straight", False, "fairway")
        d.strike_x_mm = 12.0
        launch = delivery_to_launch(d, "7-iron", "toe", "fairway", 0.0, rng)
        self.assertGreater(launch.spin_axis_deg, 3.0)
        fl = fly_shot(launch)
        self.assertGreater(float(fl.curve_ft[0]), 0.0)

    def test_headwind_costs_distance(self):
        rng = Rng(3)
        d = draw_delivery(rng, "driver", "full", 1.0, "straight", False, "tee")
        launch = delivery_to_launch(d, "driver", "pure", "tee", 0.0, rng)
        calm = fly_shot(launch)
        head = fly_shot(launch, wind_along_ms=-10 * C.MPH_TO_MS)
        self.assertLess(float(head.carry_yd[0]), float(calm.carry_yd[0]))

    def test_contact_classification(self):
        from sim.physics import Delivery
        rng = Rng(1)
        self.assertEqual(classify_contact(
            Delivery(100, 0, 0, -15, 0, 0), rng), "shank")
        self.assertEqual(classify_contact(
            Delivery(100, 0, 0, 0, -13, 0), rng), "chunk")
        self.assertEqual(classify_contact(
            Delivery(100, 0, 0, 10, 0, 0), rng), "toe")
        self.assertEqual(classify_contact(
            Delivery(100, 0, 0, -10, 0, 0), rng), "heel")
        self.assertEqual(classify_contact(
            Delivery(100, 0, 0, 0, -9, 0), rng), "thin")
        self.assertEqual(classify_contact(
            Delivery(100, 0, 0, 0, 0, 0), rng), "pure")

    def test_roll_on_green_checks_with_spin(self):
        fx, fz, roll = apply_roll(100.0, 0.0, 8.0, 0.0, 0.05,
                                  spin_rpm=6000, on_green=True)
        self.assertLess(float(roll[0]) if hasattr(roll, "__len__") else roll,
                        3.5)


class TestCourse(unittest.TestCase):
    def test_par_72(self):
        self.assertEqual(WYATT_NATIONAL.par, 72)
        self.assertEqual(WYATT_NATIONAL.yardage, 7214)
        self.assertEqual(len(WYATT_NATIONAL.holes), 18)

    def test_par_breakdown(self):
        pars = [h.par for h in WYATT_NATIONAL.holes]
        self.assertEqual(pars.count(3), 4)
        self.assertEqual(pars.count(5), 4)
        self.assertEqual(pars.count(4), 10)

    def test_project_point_at_roundtrip(self):
        hole = WYATT_NATIONAL.hole(6)  # dogleg
        for s, lat in ((100, 5), (250, -10), (400, 0), (0, 0)):
            x, y = hole.point_at(s, lat)
            s2, lat2 = hole.project(x, y)
            self.assertAlmostEqual(s, s2, delta=1.0)
            self.assertAlmostEqual(lat, lat2, delta=1.0)

    def test_lie_determination(self):
        hole = WYATT_NATIONAL.hole(1)
        self.assertEqual(WYATT_NATIONAL.determine_lie(hole, 0, 0)[0], "fairway")
        gx, gy = hole.green_centre()
        self.assertEqual(WYATT_NATIONAL.determine_lie(hole, gx, gy)[0], "green")
        self.assertEqual(WYATT_NATIONAL.determine_lie(hole, 200, 60)[0],
                         "rough_heavy")

    def test_lie_batch_matches_scalar(self):
        hole = WYATT_NATIONAL.hole(2)
        pts = [(0, 0), (200, 10), (300, -30), (578, 0), (100, 80), (250, 0)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        lies, _, _ = WYATT_NATIONAL.determine_lie_batch(hole, xs, ys)
        for (x, y), lie in zip(pts, lies):
            self.assertEqual(WYATT_NATIONAL.determine_lie(hole, x, y)[0], lie)


class TestPutting(unittest.TestCase):
    def test_make_probability_monotonic(self):
        ps = [make_probability(d, 0.5, 11.0) for d in (3, 5, 10, 20, 40)]
        self.assertEqual(ps, sorted(ps, reverse=True))
        self.assertAlmostEqual(make_probability(3, 0, 11.0), 0.99, delta=0.01)

    def test_make_rates_roughly_right(self):
        rng = Rng(5)
        for dist, lo, hi in ((5, 0.80, 0.98), (10, 0.28, 0.50), (20, 0.06, 0.22)):
            made = sum(1 for _ in range(2000)
                       if putt_model(rng, dist, 11.0)["made"])
            self.assertGreater(made / 2000, lo)
            self.assertLess(made / 2000, hi)

    def test_leave_distance_bounded(self):
        rng = Rng(5)
        for _ in range(500):
            res = putt_model(rng, 30, 11.0)
            if not res["made"]:
                self.assertGreaterEqual(res["leave_ft"], 0.5)
                self.assertLessEqual(res["leave_ft"], 10.0)


class TestBaseline(unittest.TestCase):
    def test_monotonic_in_distance(self):
        for lie in ("fairway", "rough_light", "rough_heavy"):
            vals = [baseline_strokes(lie, d) for d in (50, 100, 150, 200)]
            self.assertEqual(vals, sorted(vals))
        putts = [baseline_strokes("green", 0, f) for f in (5, 10, 20, 30, 50)]
        self.assertEqual(putts, sorted(putts))

    def test_sg_arithmetic(self):
        # A great approach: 150 yd fairway (2.95) to 10 ft (1.62).
        sg = strokes_gained("fairway", 150, 0, "green", 0, 10)
        self.assertAlmostEqual(sg, 2.95 - (1 + 1.62), delta=0.01)


class TestDecisions(unittest.TestCase):
    def test_gating_no_flop_from_heavy_rough(self):
        self.assertNotIn("flop", allowed_shot_types("rough_heavy"))
        self.assertNotIn("draw", allowed_shot_types("rough_heavy"))
        self.assertIn("punch", allowed_shot_types("rough_heavy"))

    def test_gating_bunker_green(self):
        self.assertEqual(allowed_shot_types("bunker_green"),
                         ["bunker_splash", "bunker_pick"])

    def test_knockdown_mandatory_into_strong_wind(self):
        sit = make_situation(wind_along_mph=-16.0, wind_effect="into",
                             wind_mph=16.0, distance_yd=180.0)
        cands = generate_candidates(sit, GolferModel())
        types = {c.shot_type for c in cands}
        self.assertIn("knockdown", types)
        self.assertNotIn("full", types)

    def test_decide_returns_ev_ranked_choice(self):
        rng = Rng(11)
        sit = make_situation()
        chosen, rejected = decide(WYATT_NATIONAL, sit, GolferModel(), rng,
                                  mc_n=24)
        self.assertIsNotNone(chosen.club)
        self.assertLessEqual(len(rejected), 2)
        for r in rejected:
            self.assertGreaterEqual(r.ev_strokes, chosen.ev_strokes - 1e-9)

    def test_risk_thresholds(self):
        sit = make_situation(holes_left=2, strokes_vs_59_pace=-1)
        self.assertAlmostEqual(risk_threshold(sit, True), 0.08)
        sit2 = make_situation(holes_left=5, strokes_vs_59_pace=-5)
        self.assertAlmostEqual(risk_threshold(sit2, False), 0.25)
        sit3 = make_situation(holes_left=12, strokes_vs_59_pace=0)
        self.assertAlmostEqual(risk_threshold(sit3, False), 0.15)


class TestHandicap(unittest.TestCase):
    def test_differential(self):
        # 69 at Wyatt National: (69-74.6)*113/138 = -4.59
        self.assertAlmostEqual(differential(69), -4.59, delta=0.05)
        self.assertAlmostEqual(differential(74), -0.49, delta=0.05)

    def test_whs_index_needs_3_rounds(self):
        self.assertIsNone(whs_index([-2.0, -3.0]))
        idx = whs_index([-4.6, -3.0, -2.0])
        self.assertIsNotNone(idx)
        self.assertGreater(idx, 0)  # better than scratch displays positive

    def test_form(self):
        # Lists are chronological: the last 3 are the most recent rounds.
        self.assertEqual(form_from_scores([73] * 7 + [70, 70, 70]), "hot")
        self.assertEqual(form_from_scores([72] * 7 + [76, 76, 76]), "cold")
        self.assertEqual(form_from_scores([72] * 10), "neutral")


class TestLearning(unittest.TestCase):
    def _records(self, n=5, sg=-0.3, miss=-8.0):
        return [ShotRecord("app", "app_150_175", sg, miss, 160.0)
                for _ in range(n)]

    def test_no_fix_on_too_few_samples(self):
        loop = LearningLoop()
        model = GolferModel()
        fix = loop.after_round(model, self._records(n=2))
        self.assertIsNone(fix)

    def test_one_fix_produced_and_applied(self):
        loop = LearningLoop()
        model = GolferModel()
        fix = loop.after_round(model, self._records(n=5))
        self.assertIsNotNone(fix)
        self.assertEqual(fix.mechanism, "aim_offset_ft")
        # Miss left -> aim right (positive offset).
        self.assertGreater(model.aim_biases.get("app_150_175", 0), 0)

    def test_exactly_one_active_fix(self):
        loop = LearningLoop()
        model = GolferModel()
        for _ in range(3):
            loop.after_round(model, self._records(n=5))
        self.assertIsNotNone(model.active_fix)


class TestFiftyNineWatch(unittest.TestCase):
    def test_pace_arithmetic(self):
        pars = [4] * 18
        w = FiftyNineWatch(pars, last10_avg=72.0)
        st, changed = w.update(9, 32)  # 4 under through 9
        # Expected at pace after 9: 36 - 6.5 = 29.5; 32 is 2.5 behind.
        self.assertAlmostEqual(st.strokes_vs_pace, 2.5, delta=0.01)
        self.assertEqual(st.strokes_remaining, 59 - (32 + 36))
        self.assertEqual(st.status, STATUS_OFF_PACE)

    def test_on_pace_ahead(self):
        pars = [4] * 18
        w = FiftyNineWatch(pars, last10_avg=72.0)
        st, _ = w.update(9, 28)
        self.assertEqual(st.status, STATUS_ON_PACE)

    def test_probability_bounds_and_monotonic(self):
        pars = [4] * 18
        p_good = probability_break_60(28, 9, pars, 71.0, "hot")
        p_bad = probability_break_60(38, 9, pars, 74.0, "cold")
        self.assertGreater(p_good, p_bad)
        self.assertTrue(0.001 <= p_good <= 0.999)
        self.assertTrue(0.001 <= p_bad <= 0.999)

    def test_on_the_line_on_18(self):
        pars = [4] * 18
        w = FiftyNineWatch(pars, last10_avg=72.0)
        st, _ = w.update(18, 57)  # needs a 2 on the par 4 — an eagle
        self.assertEqual(st.status, STATUS_ON_THE_LINE)
        st2, _ = w.update(18, 55)  # par on 18 still shoots 59
        self.assertEqual(st2.status, STATUS_SECURED)
        st3, _ = w.update(18, 60)
        self.assertEqual(st3.status, STATUS_GONE)

    def test_status_change_detection(self):
        pars = [4] * 18
        w = FiftyNineWatch(pars, last10_avg=72.0)
        _, c1 = w.update(1, 3)    # birdie: ahead of pace
        _, c2 = w.update(2, 8)    # bogey: behind pace
        _, c3 = w.update(3, 11)   # par: still behind
        self.assertTrue(c1)
        self.assertTrue(c2)
        self.assertFalse(c3)


class TestConditions(unittest.TestCase):
    def test_opening_draw_in_ranges(self):
        rng = Rng(9)
        eng = ConditionsEngine(rng)
        c = eng.conditions
        self.assertGreaterEqual(c.wind_mph, 0)
        self.assertLessEqual(c.wind_mph, 18)
        self.assertIn(c.sky, ("clear", "partly_cloudy", "overcast", "light_rain"))
        self.assertGreaterEqual(c.firmness, 0.25)
        self.assertLessEqual(c.firmness, 0.9)
        self.assertGreaterEqual(c.green_speed, 9.5)
        self.assertLessEqual(c.green_speed, 12.5)

    def test_update_deterministic(self):
        a = ConditionsEngine(Rng(4))
        b = ConditionsEngine(Rng(4))
        rng_a, rng_b = Rng(99), Rng(99)
        for hole in range(2, 19):
            self.assertEqual(a.update(hole, rng_a), b.update(hole, rng_b))
            self.assertEqual(a.conditions.to_dict(), b.conditions.to_dict())

    def test_firmness_labels(self):
        self.assertEqual(firmness_label(0.3), "soft")
        self.assertEqual(firmness_label(0.6), "normal")
        self.assertEqual(firmness_label(0.8), "firm")

    def test_roll_mu_ordering(self):
        # Firm fairways roll further (lower mu); fast greens roll further.
        self.assertLess(roll_mu("fairway", 0.85, 11.0),
                        roll_mu("fairway", 0.30, 11.0))
        self.assertLess(roll_mu("green", 0.6, 12.5),
                        roll_mu("green", 0.6, 9.5))

    def test_green_spin_factor_ordering(self):
        self.assertLess(green_spin_factor(0.85), green_spin_factor(0.30))

    def test_conditions_change_events_occur(self):
        eng = RoundEngine(fast_mode=True)
        seen = 0
        for _ in range(5):
            res = eng.play_round()
            seen += sum(1 for e in res.events
                        if e["type"] == "conditions_change")
        self.assertGreater(seen, 0)


class TestRatingSlope(unittest.TestCase):
    def test_wyatt_rating_slope_match_spec(self):
        rating, slope, detail = compute_rating_slope(
            WYATT_NATIONAL.holes, WYATT_NATIONAL.par)
        self.assertAlmostEqual(rating, 74.6, delta=0.3)
        self.assertAlmostEqual(slope, 138, delta=3)
        self.assertEqual(WYATT_NATIONAL.rating, rating)
        self.assertEqual(WYATT_NATIONAL.slope, slope)

    def test_championship_variant_is_harder(self):
        black = championship_variant()
        self.assertEqual(black.par, 72)
        self.assertGreater(black.yardage, WYATT_NATIONAL.yardage)
        self.assertGreater(black.rating, WYATT_NATIONAL.rating)
        self.assertGreater(black.slope, WYATT_NATIONAL.slope)

    def test_differential_uses_course_rating(self):
        # Same score, harder course -> more negative (better) differential.
        d_easy = differential(72, WYATT_NATIONAL.rating, WYATT_NATIONAL.slope)
        black = championship_variant()
        d_hard = differential(72, black.rating, black.slope)
        self.assertLess(d_hard, d_easy)

    def test_black_tees_round_plays(self):
        eng = RoundEngine(course=championship_variant(), fast_mode=True)
        res = eng.play_round()
        self.assertEqual(sum(res.hole_scores), res.score)
        self.assertEqual(res.events[0]["course"]["rating"],
                         championship_variant().rating)


class TestConditionsEffects(unittest.TestCase):
    def test_fast_greens_harder_from_distance(self):
        p_slow = make_probability(20, 0.5, 9.5)
        p_fast = make_probability(20, 0.5, 12.5)
        self.assertLess(p_fast, p_slow)
        # No adjustment inside 10 ft.
        self.assertAlmostEqual(make_probability(5, 0.5, 9.5),
                               make_probability(5, 0.5, 12.5), delta=0.01)

    def test_firm_fast_day_aims_safer(self):
        rng = Rng(2)
        sit_soft = make_situation(wind_lateral_mph=12.0,
                                  wind_effect="cross_right",
                                  wind_mph=12.0, firmness=0.3,
                                  green_speed=10.0)
        sit_firm = make_situation(wind_lateral_mph=12.0,
                                  wind_effect="cross_right",
                                  wind_mph=12.0, firmness=0.85,
                                  green_speed=12.4)
        c_soft = generate_candidates(sit_soft, GolferModel())
        c_firm = generate_candidates(sit_firm, GolferModel())
        full_soft = [c for c in c_soft if c.shot_type == "full"]
        full_firm = [c for c in c_firm if c.shot_type == "full"]
        self.assertTrue(full_soft and full_firm)
        # The firm/fast aim offset is pulled halfway toward the pin.
        self.assertLess(abs(full_firm[0].aim_offset_ft),
                        abs(full_soft[0].aim_offset_ft) + 1e-9)


class TestEngine(unittest.TestCase):
    def test_one_round_completes_and_adds_up(self):
        eng = RoundEngine(mc_n=8)
        res = eng.play_round()
        self.assertEqual(len(res.hole_scores), 18)
        self.assertEqual(sum(res.hole_scores), res.score)
        self.assertGreaterEqual(res.score, 55)
        self.assertLessEqual(res.score, 95)

    def test_events_in_order(self):
        eng = RoundEngine(mc_n=8)
        res = eng.play_round()
        types = [e["type"] for e in res.events]
        self.assertEqual(types[0], "round_start")
        self.assertEqual(types[-1], "round_complete")
        seqs = [e["seq"] for e in res.events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        # Every shot_decision precedes its shot_result.
        for i, e in enumerate(res.events):
            if e["type"] == "shot_result":
                prev = [x for x in res.events[:i]
                        if x["type"] == "shot_decision"
                        and x["hole"] == e["hole"]
                        and x["shot_no"] == e["shot_no"]]
                self.assertTrue(prev)

    def test_all_event_types_present(self):
        eng = RoundEngine(mc_n=8)
        res = eng.play_round()
        types = {e["type"] for e in res.events}
        for t in ("round_start", "hole_start", "shot_decision",
                  "shot_result", "hole_complete", "round_complete"):
            self.assertIn(t, types)
        self.assertIn("putt_result", types)
        self.assertIn("fifty_nine_watch", types)

    def test_determinism_byte_identical(self):
        a = RoundEngine(mc_n=8)
        b = RoundEngine(mc_n=8)
        ra = a.play_round()
        rb = b.play_round()
        self.assertEqual(ra.events, rb.events)
        self.assertEqual(ra.score, rb.score)

    def test_no_nan_positions(self):
        eng = RoundEngine(mc_n=8)
        res = eng.play_round()
        for e in res.events:
            if e["type"] == "shot_result":
                for v in (e["launch"]["carry_yd"], e["launch"]["total_yd"],
                          e["launch"]["apex_ft"], e["outcome"]["distance_to_pin_ft"]):
                    self.assertFalse(math.isnan(v))

    def test_handicap_moves_at_most_half_point(self):
        eng = RoundEngine(mc_n=8, fast_mode=True)
        prev = eng.handicap_index
        for _ in range(10):
            res = eng.play_round()
            self.assertLessEqual(abs(res.handicap_after - prev), 0.5 + 1e-9)
            prev = res.handicap_after

    def test_fast_mode_rounds(self):
        eng = RoundEngine(fast_mode=True)
        res = eng.play_round()
        self.assertEqual(sum(res.hole_scores), res.score)

    def test_multiple_rounds_loop_never_ends(self):
        eng = RoundEngine(fast_mode=True)
        results = eng.play_rounds(5)
        self.assertEqual(len(results), 5)
        self.assertEqual([r.round_no for r in results], [1, 2, 3, 4, 5])

    def test_learning_loop_produces_fix_over_rounds(self):
        eng = RoundEngine(fast_mode=True)
        fixes = set()
        for _ in range(6):
            res = eng.play_round()
            if res.focus_fix:
                fixes.add(res.focus_fix["area"])
        self.assertTrue(len(fixes) >= 1)

    def test_fifty_nine_watch_in_round(self):
        eng = RoundEngine(fast_mode=True)
        res = eng.play_round()
        self.assertIn("final_status", res.fifty_nine_watch)
        self.assertIn("on_pace_at_turn", res.fifty_nine_watch)
        self.assertIn("closest_call", res.fifty_nine_watch)


if __name__ == "__main__":
    unittest.main()
