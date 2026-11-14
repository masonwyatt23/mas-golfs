"""Tests for guest twins Path C (sim/twins.py, guest-twins.md §2-§3).

Pure-calibration tests are fast. The Monte Carlo validation tests play
real headless rounds (~35 s each at mc_n=60) and are marked slow by
comment; the whole file runs in ~3-4 minutes.
"""

import unittest

from sim import constants as C
from sim import putting
from sim.tests._markers import slow
from sim.twins import (
    BAND_DRIVING_YD, BAND_PCT_POINTS, BAND_SCORING_STROKES,
    StatProfile, TwinAlreadyExists, TwinProfile, TwinRegistry,
    approve_twin, benchmark_for_handicap, build_twin, calibrate_twin,
    can_air, play_validation_round, render_twin_card, request_fix,
    retire_twin, sigma_mult_for_handicap, speed_factor_for_driving,
    twin_clubs, twin_model, twin_overrides,
)


def _profile_12hcp(**over):
    kw = dict(name="Jordan Lee", handicap=-12, miss="slice",
              best_part="putting", worst_part="driving",
              between_clubs="extra",
              proud_number="I average 28 putts")
    kw.update(over)
    return StatProfile(**kw)


class TestBenchmarkTables(unittest.TestCase):
    def test_anchors(self):
        self.assertEqual(benchmark_for_handicap(-3)["driving_yd"], 270.0)
        self.assertEqual(benchmark_for_handicap(0)["driving_yd"], 251.5)
        self.assertEqual(benchmark_for_handicap(10)["driving_yd"], 235.0)
        self.assertEqual(benchmark_for_handicap(20)["driving_yd"], 215.0)
        self.assertEqual(benchmark_for_handicap(20)["scoring_avg"], 92.0)
        self.assertAlmostEqual(benchmark_for_handicap(0)["gir_pct"], 0.56)

    def test_interpolation(self):
        # Halfway between the 10 and 15 anchors.
        row = benchmark_for_handicap(12.5)
        self.assertAlmostEqual(row["driving_yd"], 230.0)
        self.assertAlmostEqual(row["scoring_avg"], 84.5)

    def test_clamped(self):
        # Better than Mas clamps to Mas's row; worse than 20 clamps to 20.
        self.assertEqual(benchmark_for_handicap(-5)["driving_yd"], 270.0)
        self.assertEqual(benchmark_for_handicap(25)["driving_yd"], 215.0)

    def test_sigma_anchors(self):
        self.assertEqual(sigma_mult_for_handicap(-3), 1.00)
        self.assertEqual(sigma_mult_for_handicap(0), 1.10)
        self.assertEqual(sigma_mult_for_handicap(20), 2.40)
        self.assertGreater(sigma_mult_for_handicap(12),
                           sigma_mult_for_handicap(5))

    def test_speed_factor(self):
        # Anchored to Mas's measured driver-only mean (284 yd), so a
        # 270-yd target is slightly below Mas, not equal to him.
        self.assertAlmostEqual(speed_factor_for_driving(270.0), 0.98, places=2)
        self.assertLess(speed_factor_for_driving(215.0), 0.92)
        self.assertGreater(speed_factor_for_driving(215.0), 0.85)


class TestBuildTwin(unittest.TestCase):
    def test_12hcp_profile(self):
        t = build_twin(_profile_12hcp())
        self.assertEqual(t.guest_name, "Jordan Lee")
        self.assertEqual(t.strokes_over_scratch, 12)
        self.assertAlmostEqual(t.benchmark["driving_yd"], 231.0)
        self.assertAlmostEqual(t.benchmark["scoring_avg"], 84.0)
        self.assertLess(t.speed_factor, 1.0)
        self.assertGreater(t.sigma_mult, 1.0)
        self.assertEqual(t.putt_mult, 1.10)          # best part: putting
        self.assertEqual(t.strength, "great putter")
        self.assertEqual(t.weakness, "wild off the tee")
        self.assertEqual(t.risk_threshold_delta, 0.03)  # extra club = conservative
        self.assertEqual(t.usual_miss, "right")
        self.assertEqual(t.shot_shape, "fade")

    def test_face_bias_sign_right_handed(self):
        # Right-handed guest whose miss is right: engine frame is the
        # left-handed convention, so the bias sign flips (see twins.py).
        t = build_twin(_profile_12hcp(miss="slice", handedness="right"))
        self.assertEqual(t.face_bias_deg, -1.0)
        t = build_twin(_profile_12hcp(miss="slice", handedness="left"))
        self.assertEqual(t.face_bias_deg, 1.0)
        t = build_twin(_profile_12hcp(miss="hook", handedness="right"))
        self.assertEqual(t.face_bias_deg, 1.0)
        t = build_twin(_profile_12hcp(miss="straight"))
        self.assertEqual(t.face_bias_deg, 0.0)
        self.assertEqual(t.shot_shape, "straight")

    def test_aggression_mapping(self):
        t = build_twin(_profile_12hcp(between_clubs="smooth"))
        self.assertEqual(t.risk_threshold_delta, -0.03)
        t = build_twin(_profile_12hcp(between_clubs="neutral"))
        self.assertEqual(t.risk_threshold_delta, 0.0)

    def test_scratch_twin_is_close_to_mas(self):
        p = StatProfile(name="Scratch Sam", handicap=0, miss="straight",
                        best_part="irons", worst_part="putting",
                        between_clubs="neutral")
        t = build_twin(p)
        self.assertAlmostEqual(t.speed_factor, 0.94, places=2)
        self.assertAlmostEqual(t.sigma_mult, 1.10)

    def test_profile_validation(self):
        with self.assertRaises(ValueError):
            StatProfile(name="X", handicap=-12, miss="slice",
                        best_part="putting", worst_part="putting",
                        between_clubs="extra")
        with self.assertRaises(ValueError):
            StatProfile(name="X", handicap=-40, miss="slice",
                        best_part="putting", worst_part="driving",
                        between_clubs="extra")
        with self.assertRaises(ValueError):
            StatProfile(name="X", handicap=-12, miss="slice",
                        best_part="putting", worst_part="driving",
                        between_clubs="???")
        with self.assertRaises(ValueError):
            StatProfile(name=" ", handicap=-12, miss="slice",
                        best_part="putting", worst_part="driving",
                        between_clubs="extra")


class TestClaimClamping(unittest.TestCase):
    """Honesty rule: a twin is only better than the guest if the guest's
    numbers say so (guest-twins.md §3.2). Vanity claims calibrate down."""

    def test_driving_claim_clamped(self):
        p = _profile_12hcp(driving_distance_yd=300.0)
        t = build_twin(p)
        self.assertAlmostEqual(t.benchmark["driving_yd"], 231.0)
        self.assertAlmostEqual(t.speed_factor,
                               speed_factor_for_driving(231.0))
        self.assertTrue(any("300" in n and "benchmark" in n
                            for n in t.calibration_notes))

    def test_plausible_claim_accepted(self):
        p = _profile_12hcp(driving_distance_yd=240.0)
        t = build_twin(p)
        self.assertAlmostEqual(t.speed_factor,
                               speed_factor_for_driving(240.0))

    def test_fairway_claim_clamped(self):
        p = _profile_12hcp(fairway_pct=0.75)
        t = build_twin(p)
        self.assertTrue(any("fairway" in n.lower()
                            for n in t.calibration_notes))

    def test_proud_number_checked(self):
        # "28 putts" from a 12-handicapper is >2 better than benchmark.
        t = build_twin(_profile_12hcp())
        self.assertTrue(any("28 putts" in n for n in t.calibration_notes))
        # A plausible proud number draws no note.
        t2 = build_twin(_profile_12hcp(proud_number="I hit 45% of fairways"))
        self.assertEqual(t2.calibration_notes, [])


class TestStrengthWeaknessBounds(unittest.TestCase):
    def test_putting_strength(self):
        t = build_twin(_profile_12hcp(best_part="putting"))
        self.assertEqual(t.putt_mult, 1.10)
        t = build_twin(_profile_12hcp(best_part="driving",
                                      worst_part="putting"))
        self.assertEqual(t.putt_mult, 0.90)

    def test_driver_weakness_in_clubs(self):
        t = build_twin(_profile_12hcp(worst_part="driving"))
        clubs = twin_clubs(t)
        # Driver direction sigma x1.20 (weakness) on top of the handicap sigma.
        self.assertAlmostEqual(
            clubs["driver"]["sig_face"],
            C.CLUBS["driver"]["sig_face"] * t.sigma_mult * 1.20)
        self.assertAlmostEqual(
            clubs["driver"]["speed_mean"],
            C.CLUBS["driver"]["speed_mean"] * t.speed_factor * 0.98)
        # Strike sigmas are handicap-driven only (see twin_clubs): a
        # 12-handicapper's strike multiplier is 1.25 whatever the class
        # adjustment is — a wild driver misses fairways, it does not
        # shank more.
        self.assertAlmostEqual(
            clubs["driver"]["sig_sx"],
            C.CLUBS["driver"]["sig_sx"] * 1.25)

    def test_strike_scaling_is_damped(self):
        # Strike dispersion grows gently: a 20-handicapper's strike
        # multiplier caps well below the 2.40x direction multiplier.
        from sim.twins import strike_mult_for_sigma
        self.assertAlmostEqual(strike_mult_for_sigma(1.00), 1.00)
        self.assertAlmostEqual(strike_mult_for_sigma(1.79), 1.25)
        self.assertAlmostEqual(strike_mult_for_sigma(2.40), 1.25)

    def test_iron_strength_in_clubs(self):
        p = StatProfile(name="Irons Ida", handicap=-5, miss="straight",
                        best_part="irons", worst_part="putting",
                        between_clubs="neutral")
        t = build_twin(p)
        clubs = twin_clubs(t)
        self.assertAlmostEqual(
            clubs["7-iron"]["sig_face"],
            C.CLUBS["7-iron"]["sig_face"] * t.sigma_mult * 0.90)
        # Wedges are untouched by the iron strength.
        self.assertAlmostEqual(
            clubs["SW"]["sig_face"],
            C.CLUBS["SW"]["sig_face"] * t.sigma_mult)

    def test_twin_clubs_does_not_mutate_constants(self):
        before = {k: dict(v) for k, v in C.CLUBS.items()}
        t = build_twin(_profile_12hcp())
        twin_clubs(t)
        self.assertEqual(C.CLUBS, before)

    def test_twin_model(self):
        t = build_twin(_profile_12hcp())
        m = twin_model(t)
        self.assertEqual(m.risk_threshold_delta, 0.03)
        self.assertEqual(m.form, "neutral")
        self.assertTrue(all(v == 0.0 for v in m.aim_biases.values()))


class TestOverrides(unittest.TestCase):
    def test_restore_on_exit(self):
        before_clubs = {k: dict(v) for k, v in C.CLUBS.items()}
        before_bias = dict(C.SHAPE_FACE_BIAS)
        before_make = putting.make_probability
        t = build_twin(_profile_12hcp())
        with twin_overrides(t):
            self.assertNotEqual(C.CLUBS["driver"]["speed_mean"],
                                before_clubs["driver"]["speed_mean"])
            self.assertEqual(C.SHAPE_FACE_BIAS["straight"], -1.0)
            self.assertIsNot(putting.make_probability, before_make)
        self.assertEqual(C.CLUBS, before_clubs)
        self.assertEqual(C.SHAPE_FACE_BIAS, before_bias)
        self.assertIs(putting.make_probability, before_make)

    def test_restore_on_error(self):
        before_clubs = {k: dict(v) for k, v in C.CLUBS.items()}
        t = build_twin(_profile_12hcp())
        with self.assertRaises(RuntimeError):
            with twin_overrides(t):
                raise RuntimeError("boom")
        self.assertEqual(C.CLUBS, before_clubs)

    def test_putt_multiplier_scales_makes(self):
        t = build_twin(_profile_12hcp())  # putt_mult 1.10
        # Direct check against the unscaled table value.
        base = putting.make_probability(10.0, 0.0, 11.0)
        with twin_overrides(t):
            scaled = putting.make_probability(10.0, 0.0, 11.0)
        self.assertAlmostEqual(scaled, min(0.995, base * 1.10))


class TestCardAndApproval(unittest.TestCase):
    def test_card_shows_calibrated_numbers(self):
        # No invented results: the card's numbers are the
        # benchmark-calibrated ones, never the guest's clamped claim —
        # and the claim-down is shown honestly as a note, not hidden.
        t = build_twin(_profile_12hcp(driving_distance_yd=300.0))
        card = render_twin_card(t)
        self.assertIn("DRIVING   231 yd avg", card)
        self.assertIn("Claimed 300 yd driving — calibrated to the "
                      "12-handicap benchmark of 231 yd", card)
        self.assertIn("This is how your twin plays.", card)
        self.assertIn("AWAITING GUEST APPROVAL", card)

    def test_approval_gate(self):
        t = build_twin(_profile_12hcp())
        ok, reason = can_air(t)
        self.assertFalse(ok)
        self.assertIn("validation", reason)
        with self.assertRaises(ValueError):
            approve_twin(t)
        # Fake a passed validation to test the approval half of the gate.
        t.validation = dict(passed=True)
        ok, reason = can_air(t)
        self.assertFalse(ok)
        self.assertIn("approved", reason)
        approve_twin(t)
        self.assertTrue(t.approved)
        ok, _ = can_air(t)
        self.assertTrue(ok)

    def test_request_fix_resets_approval(self):
        t = build_twin(_profile_12hcp())
        t.validation = dict(passed=True)
        approve_twin(t)
        request_fix(t, "my miss is a hook, not a slice")
        self.assertFalse(t.approved)
        self.assertTrue(any("hook" in n for n in t.calibration_notes))
        ok, _ = can_air(t)
        self.assertFalse(ok)

    def test_retire(self):
        t = build_twin(_profile_12hcp())
        t.validation = dict(passed=True)
        approve_twin(t)
        retire_twin(t, "guest asked to be removed")
        self.assertTrue(t.retired)
        self.assertFalse(t.approved)
        ok, reason = can_air(t)
        self.assertFalse(ok)
        self.assertIn("retired", reason)

    def test_serialisation_round_trip(self):
        t = build_twin(_profile_12hcp())
        t2 = TwinProfile.from_dict(t.to_dict())
        self.assertEqual(t2.guest_name, t.guest_name)
        self.assertEqual(t2.speed_factor, t.speed_factor)
        self.assertEqual(t2.sigma_mult, t.sigma_mult)
        self.assertEqual(t2.calibration_notes, t.calibration_notes)


class TestRegistry(unittest.TestCase):
    def test_one_twin_per_guest(self):
        reg = TwinRegistry()
        reg.add(build_twin(_profile_12hcp()))
        with self.assertRaises(TwinAlreadyExists):
            reg.add(build_twin(_profile_12hcp()))
        # Case/whitespace-insensitive: same guest.
        with self.assertRaises(TwinAlreadyExists):
            reg.add(build_twin(_profile_12hcp(name="  jordan lee ")))

    def test_recalibrate_keeps_record_resets_approval(self):
        reg = TwinRegistry()
        t = build_twin(_profile_12hcp())
        t.validation = dict(passed=True)
        approve_twin(t)
        reg.add(t)
        reg.record_match("Jordan Lee", won=True, score=82)
        t2 = reg.recalibrate(_profile_12hcp(handicap=-10))
        self.assertEqual(t2.record["matches"], 1)
        self.assertEqual(t2.record["wins"], 1)
        self.assertEqual(t2.record["best_score"], 82)
        self.assertFalse(t2.approved)
        self.assertIsNone(t2.validation)
        self.assertEqual(t2.handicap, -10)

    def test_retire_and_record(self):
        reg = TwinRegistry()
        reg.add(build_twin(_profile_12hcp()))
        self.assertIsNone(reg.record_match("Nobody", won=True, score=80))
        reg.record_match("Jordan Lee", won=False, score=88)
        reg.record_match("Jordan Lee", won=True, score=84)
        t = reg.get("Jordan Lee")
        self.assertEqual(t.record["matches"], 2)
        self.assertEqual(t.record["best_score"], 84)
        reg.retire("Jordan Lee", "guest request")
        self.assertTrue(reg.get("Jordan Lee").retired)

    def test_registry_serialisation(self):
        reg = TwinRegistry()
        reg.add(build_twin(_profile_12hcp()))
        reg2 = TwinRegistry.from_dict(reg.to_dict())
        self.assertIsNotNone(reg2.get("Jordan Lee"))
        self.assertEqual(reg2.get("Jordan Lee").handicap, -12)


class TestValidationBands(unittest.TestCase):
    """The band logic itself, on synthetic results (deterministic)."""

    def _result(self, twin, **kw):
        from sim.twins import ValidationResult
        d = dict(score=84, driving_avg_yd=231.0, driving_longest_yd=260.0,
                 fairway_pct=0.47, gir_pct=0.42, putts=32,
                 long_putts_made=0, seed=0, mc_n=60, round_no=9001)
        d.update(kw)
        return ValidationResult(twin, **d)

    def test_all_bands_pass(self):
        t = build_twin(_profile_12hcp())
        v = self._result(t)
        self.assertTrue(v.passed)
        self.assertTrue(all(v.checks.values()))

    def test_each_band_fails_independently(self):
        t = build_twin(_profile_12hcp())
        cases = [
            (dict(score=90), "scoring"),
            (dict(driving_avg_yd=250.0), "driving"),
            (dict(fairway_pct=0.20), "fairway"),
            (dict(gir_pct=0.20), "gir"),
            (dict(driving_longest_yd=320.0), "no_impossible_drive"),
            (dict(long_putts_made=2), "no_impossible_putts"),
        ]
        for kw, key in cases:
            v = self._result(t, **kw)
            self.assertFalse(v.passed, kw)
            self.assertFalse(v.checks[key], kw)
            self.assertEqual(sum(v.checks.values()), 5, kw)

    def test_band_edges(self):
        t = build_twin(_profile_12hcp())
        v = self._result(t, score=84 + BAND_SCORING_STROKES,
                         driving_avg_yd=231.0 + BAND_DRIVING_YD)
        self.assertTrue(v.checks["scoring"])
        self.assertTrue(v.checks["driving"])


class TestMeasuredOverrides(unittest.TestCase):
    """Path B plug-in: measured values replace benchmark estimates."""

    def test_carry_overrides_speed(self):
        t = build_twin(_profile_12hcp(),
                       measured={"source": "path_b", "carry_yd": 240.0})
        # Carry 240 yd -> equivalent total 240 + 20.6 roll -> same anchor
        # as speed_factor_for_driving.
        self.assertAlmostEqual(t.speed_factor,
                               speed_factor_for_driving(260.6), places=3)
        self.assertEqual(t.source, "path_b")
        self.assertTrue(any("measured" in n.lower()
                            for n in t.calibration_notes))

    def test_dispersion_override(self):
        t = build_twin(_profile_12hcp(),
                       measured={"source": "path_b", "sig_face_deg": 2.30})
        self.assertAlmostEqual(t.sigma_mult, 2.30 / 1.15)

    def test_club_speed_override(self):
        t = build_twin(_profile_12hcp(),
                       measured={"source": "path_b", "club_speed_mph": 99.0})
        self.assertAlmostEqual(t.speed_factor, 99.0 / 110.0)


class TestValidationRoundMC(unittest.TestCase):
    """Real headless rounds (slow: ~2 min each at mc_n=60; the pure
    suite above runs in <1 s). A single round is far too noisy for the
    tight bands — Mas himself scores 71-89 and drives 271-306 yd across
    seeds — so the single-round test asserts wide sanity bands only.
    The tight gate lives in the calibration loop, on the running mean.
    """

    @slow
    def test_scratch_validation_round(self):
        p = StatProfile(name="Scratch Sam", handicap=0, miss="straight",
                        best_part="irons", worst_part="putting",
                        between_clubs="neutral")
        t = build_twin(p)
        v = play_validation_round(t, seed=0, mc_n=60)
        # Wide sanity bands for one noisy round: the round plays, the
        # driver-only stat is sane, nothing impossible happened.
        self.assertLessEqual(abs(v.driving_avg_yd - 251.5), 30, v.detail)
        self.assertLessEqual(v.driving_longest_yd, 251.5 + 75)
        self.assertLessEqual(v.long_putts_made, 1)
        self.assertLessEqual(abs(v.score - 73), 10, v.detail)
        self.assertIn("score", v.detail)
        self.assertEqual(v.seed, 0)
        self.assertEqual(v.mc_n, 60)

    @slow
    def test_calibrate_12hcp_and_approve(self):
        """The loop gates on the running mean; a validated twin can air
        once the guest approves the card."""
        t = build_twin(_profile_12hcp())
        calibrate_twin(t, max_rounds=3, mc_n=60)
        self.assertIsNotNone(t.validation)
        self.assertGreaterEqual(len(t.validation_history), 1)
        # The loop either passes on the mean or records why it adjusted
        # — never silently claims a pass it did not earn.
        if t.validation["passed"]:
            mean = t.validation["mean"]
            self.assertLessEqual(abs(mean["score"] - 84),
                                 BAND_SCORING_STROKES)
            self.assertLessEqual(
                abs(mean["driving_avg_yd"] - 231.0), BAND_DRIVING_YD)
            approve_twin(t)
            ok, reason = can_air(t)
            self.assertTrue(ok, reason)
        else:
            self.assertEqual(len(t.validation_history), 3)
            self.assertTrue(any("running mean" in n
                                for n in t.calibration_notes))


if __name__ == "__main__":
    unittest.main()
