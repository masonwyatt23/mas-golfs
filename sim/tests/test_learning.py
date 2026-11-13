"""Tests for sim.learning — the self-improvement loop (docs/self-improvement.md).

These tests check the SPEC behaviour (multi-round evidence, verdict
windows, caps, season reset, monitoring), not the old skeleton's
single-round behaviour. One legacy test in test_sim.py
(test_one_fix_produced_and_applied) expects a fix from a single round
of records; the spec explicitly forbids that (§4.1/§4.4), so that
legacy test is expected to fail until it is updated to feed 3+ rounds.
See the module docstring for the integration points.
"""

import unittest

from sim import constants as C
from sim.learning import (
    AIM_BIAS_CAP_FT,
    AIM_FIX_FIRST_FT,
    AIM_FIX_MAX_FT,
    BASELINE_CAP,
    BASELINE_DEADBAND,
    Fix,
    GolferModel,
    LearningLoop,
    RoundRecord,
    RoundStore,
    ShotRecord,
    display_handicap_for_rung,
    ladder_rung_for_avg,
    season_improvement,
)

BUCKET = "app_150_175"


def losing_round(bucket=BUCKET, n=5, sg=-0.3, miss=-8.0, dist=160.0):
    """A round of 5 shots in one bucket, all losing, all missing left."""
    return [ShotRecord("app", bucket, sg, miss, dist) for _ in range(n)]


def winning_round(bucket=BUCKET, n=5, sg=0.1, miss=2.0, dist=160.0):
    return [ShotRecord("app", bucket, sg, miss, dist) for _ in range(n)]


def neutral_round(bucket=BUCKET, n=5, sg=0.05):
    """Within the noise floors — no weakness to fix."""
    return [ShotRecord("app", bucket, sg, 1.0, 160.0) for _ in range(n)]


def run_rounds(loop, model, rounds, scores=None):
    """Drive the loop through a list of record lists; return the fixes."""
    fixes = []
    for i, records in enumerate(rounds):
        info = {"score": scores[i]} if scores is not None else None
        fix = loop.after_round(model, records, info)
        fixes.append(fix)
    return fixes


class TestOneFixSelection(unittest.TestCase):
    def test_no_fix_in_first_three_rounds(self):
        loop, model = LearningLoop(), GolferModel()
        for _ in range(3):
            fix = loop.after_round(model, losing_round())
            self.assertIsNone(fix)
        self.assertEqual(loop.last_outcome["kind"], "no_fix")
        self.assertEqual(loop.last_outcome["reason"], "establishing")

    def test_one_fix_from_worst_bucket_after_round_four(self):
        loop, model = LearningLoop(), GolferModel()
        fixes = run_rounds(loop, model, [losing_round()] * 5)
        self.assertIsNone(fixes[0])
        self.assertIsNone(fixes[2])
        fix = fixes[3]
        self.assertIsNotNone(fix)
        self.assertEqual(fix.area, BUCKET)
        self.assertEqual(fix.mechanism, "aim_offset_ft")
        self.assertEqual(fix.magnitude, AIM_FIX_FIRST_FT)
        # Miss left -> aim right (positive offset).
        self.assertEqual(model.aim_biases[BUCKET], AIM_FIX_FIRST_FT)
        # Only one active fix at a time.
        self.assertIs(model.active_fix, fix)

    def test_no_fix_when_within_noise_floor(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [neutral_round()] * 6)
        self.assertIsNone(model.active_fix)
        self.assertEqual(loop.last_outcome["kind"], "no_fix")

    def test_no_fix_on_too_few_samples(self):
        loop, model = LearningLoop(), GolferModel()
        # Only 2 shots in the bucket in the whole 5-round window —
        # below the §4.1 minimum of 3.
        rounds = [losing_round(n=2)] + [neutral_round("app_100_125")] * 4
        run_rounds(loop, model, rounds)
        self.assertIsNone(model.active_fix)

    def test_worst_bucket_wins(self):
        loop, model = LearningLoop(), GolferModel()
        both = losing_round("app_100_125", sg=-0.1) + losing_round(sg=-0.4)
        run_rounds(loop, model, [both] * 5)
        self.assertIsNotNone(model.active_fix)
        self.assertEqual(model.active_fix.area, BUCKET)

    def test_fix_line_is_plain_language(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [losing_round()] * 4)
        line = loop.one_fix_line(model)
        self.assertTrue(line.startswith("ONE FIX: Aim 4 ft right on "
                                        "150–175 yd approaches"))
        self.assertNotIn("aim_offset_ft", line)

    def test_determinism(self):
        def one_run():
            loop, model = LearningLoop(), GolferModel()
            run_rounds(loop, model, [losing_round()] * 6)
            return dict(model.active_fix.__dict__)
        self.assertEqual(one_run(), one_run())

    def test_one_fix_line_establishing(self):
        loop, model = LearningLoop(), GolferModel()
        loop.after_round(model, losing_round())
        self.assertIn("Learning the game again",
                      loop.one_fix_line(model))


class TestVerdictAndEscalation(unittest.TestCase):
    def _loop_to_fix(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [losing_round()] * 4)
        self.assertIsNotNone(model.active_fix)
        return loop, model

    def test_working_fix_resolves_and_bias_stays(self):
        loop, model = self._loop_to_fix()
        # Rounds 5-7: the bucket now gains strokes.
        run_rounds(loop, model, [winning_round()] * 3)
        self.assertIsNone(model.active_fix)
        self.assertEqual(model.aim_biases[BUCKET], AIM_FIX_FIRST_FT)
        resolved = [f for f in model.fix_history
                    if f["status"] == "resolved"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(loop.last_outcome["kind"], "fix_resolved")

    def test_no_effect_escalates_to_7ft(self):
        loop, model = self._loop_to_fix()
        # Rounds 5-7: same losses as before the fix.
        run_rounds(loop, model, [losing_round()] * 3)
        fix = model.active_fix
        self.assertIsNotNone(fix)
        self.assertEqual(fix.escalation_level, 1)
        self.assertEqual(fix.magnitude, AIM_FIX_MAX_FT)
        self.assertEqual(model.aim_biases[BUCKET], AIM_FIX_MAX_FT)
        self.assertEqual(loop.last_outcome["kind"], "fix_escalated")

    def test_harmful_fix_reverts(self):
        loop, model = self._loop_to_fix()
        # Rounds 5-7: the bucket gets WORSE after the fix.
        run_rounds(loop, model, [losing_round(sg=-0.5)] * 3)
        self.assertIsNone(model.active_fix)
        # Bias reverts to the Season 1 starting value (-2.0).
        self.assertEqual(model.aim_biases[BUCKET], -2.0)
        reverted = [f for f in model.fix_history
                    if f["status"] == "reverted"]
        self.assertEqual(len(reverted), 1)

    def test_pending_fix_not_judged_before_window(self):
        loop, model = self._loop_to_fix()
        # Only 1 round after the fix: still pending.
        loop.after_round(model, winning_round())
        self.assertIsNotNone(model.active_fix)
        self.assertEqual(model.active_fix.verdict, None)
        self.assertEqual(loop.last_outcome["reason"], "fix_pending")

    def test_pending_when_bucket_does_not_recur(self):
        loop, model = self._loop_to_fix()
        # 3 rounds with no shots in the fixed bucket: not enough data
        # to judge — the fix stays active, never misjudged as harmful.
        run_rounds(loop, model, [neutral_round("app_100_125")] * 3)
        self.assertIsNotNone(model.active_fix)
        self.assertEqual(model.active_fix.verdict, "pending")

    def test_second_escalation_switches_mechanism(self):
        loop, model = self._loop_to_fix()
        run_rounds(loop, model, [losing_round()] * 3)   # escalate to 7 ft
        self.assertEqual(model.active_fix.mechanism, "aim_offset_ft")
        run_rounds(loop, model, [losing_round()] * 3)   # escalate again
        fix = model.active_fix
        self.assertIsNotNone(fix)
        self.assertEqual(fix.escalation_level, 2)
        self.assertEqual(fix.mechanism, "club_up")
        self.assertIn(BUCKET, model.club_up_buckets)
        # The aim bias from the first mechanism is gone (reverted).
        self.assertEqual(model.aim_biases[BUCKET], -2.0)

    def test_third_no_effect_marks_resistant(self):
        loop, model = self._loop_to_fix()
        run_rounds(loop, model, [losing_round()] * 3)   # -> level 1
        run_rounds(loop, model, [losing_round()] * 3)   # -> level 2
        run_rounds(loop, model, [losing_round()] * 3)   # -> resistant
        self.assertIsNone(model.active_fix)
        self.assertIn(BUCKET, model.resistant)
        resistant = [f for f in model.fix_history
                     if f["status"] == "resistant"]
        self.assertEqual(len(resistant), 1)
        self.assertEqual(loop.last_outcome["kind"], "fix_resistant")


class TestCaps(unittest.TestCase):
    def test_aim_bias_cap_rejected_never_clamped(self):
        loop, model = LearningLoop(), GolferModel()
        model.aim_biases[BUCKET] = 11.0
        fix = Fix(area=BUCKET, mechanism="aim_offset_ft", magnitude=4.0,
                  evidence={"direction": "right"})
        # Aiming further left would need -4.0: a 15 ft move — rejected.
        self.assertFalse(loop._apply_fix(model, fix))
        self.assertEqual(model.aim_biases[BUCKET], 11.0)
        self.assertTrue(any(e["event"] == "fix_rejected_cap"
                            for e in model.change_log))

    def test_single_fix_move_cap_7ft(self):
        loop, model = LearningLoop(), GolferModel()
        model.aim_biases[BUCKET] = -2.0
        fix = Fix(area=BUCKET, mechanism="aim_offset_ft", magnitude=4.0,
                  evidence={"direction": "right"})
        # -2.0 -> -4.0 is a 2 ft move: allowed.
        self.assertTrue(loop._apply_fix(model, fix))
        # But a fresh fix wanting +7.0 from -4.0 is an 11 ft move.
        model.aim_biases[BUCKET] = -4.0
        fix2 = Fix(area=BUCKET, mechanism="aim_offset_ft", magnitude=7.0,
                   evidence={"direction": "left"})
        self.assertFalse(loop._apply_fix(model, fix2))
        self.assertEqual(model.aim_biases[BUCKET], -4.0)

    def test_aim_bias_cap_constant(self):
        self.assertEqual(AIM_BIAS_CAP_FT, 12.0)
        self.assertEqual(AIM_FIX_MAX_FT, 7.0)

    def test_risk_threshold_cap(self):
        loop, model = LearningLoop(), GolferModel()
        for _ in range(3):
            fix = Fix(area="putt_6_15", mechanism="aggression",
                      magnitude=-0.03)
            self.assertTrue(loop._apply_fix(model, fix))
        self.assertEqual(model.risk_threshold_delta, -0.09)
        fix = Fix(area="putt_6_15", mechanism="aggression",
                  magnitude=-0.03)
        self.assertFalse(loop._apply_fix(model, fix))
        self.assertEqual(model.risk_threshold_delta, -0.09)

    def test_baseline_adjustment_cap(self):
        loop, model = LearningLoop(), GolferModel()
        # 20 rounds with the bucket losing 0.5 strokes/shot: observed
        # deviation +0.5, deadband 0.10 cleared, move capped at 0.05.
        rounds = [losing_round(sg=-0.5, n=10)] * 20
        run_rounds(loop, model, rounds)
        self.assertEqual(model.baseline_adjustments[BUCKET], BASELINE_CAP)
        # Next 20 rounds: already at the cap, no further move.
        run_rounds(loop, model, rounds)
        self.assertEqual(model.baseline_adjustments[BUCKET], BASELINE_CAP)

    def test_baseline_deadband(self):
        loop, model = LearningLoop(), GolferModel()
        # Losing 0.05 strokes/shot: observed 0.05 < deadband 0.10.
        rounds = [losing_round(sg=-0.05, n=10)] * 20
        run_rounds(loop, model, rounds)
        self.assertNotIn(BUCKET, model.baseline_adjustments)


class TestFrozenForever(unittest.TestCase):
    def test_sigma_and_constants_never_change(self):
        snapshot = {k: (tuple(v) if isinstance(v, list) else v)
                    for k, v in vars(C).items()
                    if not k.startswith("__")}
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model,
                   [losing_round()] * 30 + [winning_round()] * 30)
        after = {k: (tuple(v) if isinstance(v, list) else v)
                 for k, v in vars(C).items()
                 if not k.startswith("__")}
        self.assertEqual(snapshot, after)

    def test_no_sigma_fields_on_model(self):
        model = GolferModel()
        self.assertFalse(hasattr(model, "sigma"))
        self.assertFalse(hasattr(model, "dispersion"))
        self.assertFalse(hasattr(model, "practice_rounds"))


class TestSeasonReset(unittest.TestCase):
    def test_200_round_reset_preserves_records(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [losing_round()] * 4)
        self.assertIsNotNone(model.active_fix)
        run_rounds(loop, model, [neutral_round()] * 196,
                   scores=[73] * 196)
        self.assertEqual(loop.season_no, 2)
        self.assertEqual(model.season_no, 2)
        self.assertEqual(loop.rounds_seen, 0)
        archive = loop.last_archive
        self.assertIsNotNone(archive)
        self.assertEqual(archive["rounds"], 200)
        self.assertEqual(archive["best_score"], 73)
        # The first 4 rounds carried no score; the other 196 did.
        self.assertEqual(archive["scores"], [73] * 196)
        self.assertTrue(archive["fix_history"])
        # Model reset to +3 baselines.
        self.assertEqual(model.aim_biases, {"app_150_175": -2.0})
        self.assertEqual(model.risk_threshold_delta, 0.0)
        self.assertEqual(model.baseline_adjustments, {})
        self.assertEqual(model.forced_trajectory, {})
        self.assertEqual(model.club_up_buckets, set())
        self.assertIsNone(model.active_fix)
        self.assertFalse(model.halted)
        self.assertEqual(loop.last_outcome["kind"], "season_reset")

    def test_59_ends_season_early(self):
        loop, model = LearningLoop(), GolferModel()
        scores = [73] * 49 + [59]
        run_rounds(loop, model, [neutral_round()] * 50, scores=scores)
        self.assertEqual(loop.season_no, 2)
        self.assertEqual(loop.last_archive["rounds"], 50)
        self.assertEqual(loop.last_archive["best_score"], 59)
        # The halt is a human-review gate, not a season-scoped flag: it
        # survives the reset (the model itself resets to baselines).
        self.assertTrue(model.halted)
        self.assertIn("59_in_first_50", model.halt_reason)

    def test_one_fix_line_after_reset(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [neutral_round()] * 200, scores=[73] * 200)
        self.assertIn("Learning the game again",
                      loop.one_fix_line(model))


class TestMonitoring(unittest.TestCase):
    def test_59_in_first_50_halts(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [neutral_round()] * 10, scores=[73] * 9 + [59])
        self.assertTrue(model.halted)
        self.assertIn("59_in_first_50", model.halt_reason)
        # While halted, the model freezes: no new fixes.
        run_rounds(loop, model, [losing_round()] * 6)
        self.assertIsNone(model.active_fix)
        self.assertEqual(loop.last_outcome["kind"], "halted")

    def test_improvement_cap_projection_halts(self):
        loop, model = LearningLoop(), GolferModel()
        scores = [76] * 20 + [70] * 80
        run_rounds(loop, model, [neutral_round()] * 100, scores=scores)
        self.assertTrue(model.halted)
        self.assertIn("improvement_cap", model.halt_reason)

    def test_healthy_arc_does_not_halt(self):
        loop, model = LearningLoop(), GolferModel()
        # Linear arc 73.1 -> 71.8 over 200 rounds (spec §2.1): projected
        # improvement ~1.3 strokes, under the 1.5 cap.
        scores = [round(73.1 - 0.0065 * i) for i in range(200)]
        run_rounds(loop, model, [neutral_round()] * 200, scores=scores)
        self.assertFalse(model.halted)

    def test_fix_churn_halts(self):
        loop, model = LearningLoop(), GolferModel()
        model.new_fix_rounds = list(range(1, 12))  # 11 new fixes, 20 rounds
        loop.rounds_seen = 20
        loop._monitoring(model, None)
        self.assertTrue(model.halted)
        self.assertIn("fix_churn", model.halt_reason)

    def test_category_drift_halts(self):
        loop, model = LearningLoop(), GolferModel()
        early = [losing_round(sg=-0.1)] * 20
        late = [losing_round(sg=-0.5)] * 20
        run_rounds(loop, model, early + late, scores=[73] * 40)
        self.assertTrue(model.halted)
        self.assertIn("category_drift", model.halt_reason)

    def test_resume_after_halt(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [neutral_round()] * 10, scores=[73] * 9 + [59])
        self.assertTrue(model.halted)
        loop.resume(model, "reviewed: calibration error, not a real 59")
        self.assertFalse(model.halted)
        self.assertIsNone(model.halt_reason)


class TestLadder(unittest.TestCase):
    def test_rung_thresholds(self):
        self.assertEqual(ladder_rung_for_avg(73.5), 0)
        self.assertEqual(ladder_rung_for_avg(72.5), 1)
        self.assertEqual(ladder_rung_for_avg(72.0), 2)
        self.assertEqual(ladder_rung_for_avg(71.5), 3)
        self.assertEqual(ladder_rung_for_avg(71.0), 4)
        self.assertEqual(ladder_rung_for_avg(70.5), 4)

    def test_display_handicaps(self):
        self.assertEqual(display_handicap_for_rung(0), 3.1)
        self.assertEqual(display_handicap_for_rung(4), 5.0)

    def test_season_improvement(self):
        scores = [74] * 20 + [72] * 20
        self.assertAlmostEqual(season_improvement(scores), 2.0)
        self.assertIsNone(season_improvement([74] * 30))

    def test_ladder_state_framing(self):
        loop = LearningLoop()
        state = loop.ladder_state(71.0)
        self.assertEqual(state["rung"], 4)
        self.assertEqual(state["handicap"], 5.0)
        self.assertIn("+5", state["framing"])


class TestRoundStoreAndModel(unittest.TestCase):
    def test_round_store_append_only(self):
        store = RoundStore()
        store.add_round(RoundRecord(round_no=1, shots=losing_round()))
        store.add_round(RoundRecord(round_no=2, shots=losing_round()))
        self.assertEqual(len(store.rounds), 2)
        bucket = store.bucket_round_sg(BUCKET, 5)
        self.assertEqual(len(bucket), 2)
        self.assertEqual(bucket[0][2], 5)  # 5 shots in the bucket

    def test_model_serialisation_round_trip(self):
        loop, model = LearningLoop(), GolferModel()
        run_rounds(loop, model, [losing_round()] * 4)
        data = model.to_dict()
        restored = GolferModel.from_dict(data)
        self.assertEqual(restored.aim_biases, model.aim_biases)
        self.assertEqual(restored.active_fix.area, BUCKET)
        self.assertEqual(restored.version, model.version)
        self.assertEqual(restored.fix_history, model.fix_history)

    def test_old_save_still_loads(self):
        old = dict(aim_biases={"app_150_175": -2.0},
                   risk_threshold_delta=0.0,
                   baseline_adjustments={},
                   forced_trajectory={},
                   club_up_buckets=[],
                   form="neutral",
                   active_fix=None)
        model = GolferModel.from_dict(old)
        self.assertEqual(model.version, 1)
        self.assertEqual(model.season_no, 1)
        self.assertFalse(model.halted)

    def test_change_log_bumps_version(self):
        model = GolferModel()
        v0 = model.version
        model.log_change("test", "detail", 1)
        self.assertEqual(model.version, v0 + 1)
        self.assertEqual(model.change_log[-1]["event"], "test")

    def test_focus_fix_dict(self):
        loop, model = LearningLoop(), GolferModel()
        self.assertIsNone(loop.focus_fix_dict(model))
        run_rounds(loop, model, [losing_round()] * 4)
        focus = loop.focus_fix_dict(model)
        self.assertIsNotNone(focus)
        self.assertEqual(focus["area"], BUCKET)
        self.assertEqual(focus["mechanism"], "aim_offset_ft")


if __name__ == "__main__":
    unittest.main()
