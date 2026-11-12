"""Tests for the Mas Golfs auto-clip pipeline. Run with:

    python -m unittest discover -s tests -v
    (from clip-pipeline/)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clip_pipeline import (  # noqa: E402
    assemble_clip,
    load_events,
    run_pipeline,
    score_round,
    select_daily_queue,
)
from clip_pipeline.assembly import PLATFORM_SPECS  # noqa: E402
from clip_pipeline.sample_log import build_round  # noqa: E402

HERE = Path(__file__).resolve().parent.parent


class SampleLogTests(unittest.TestCase):
    def setUp(self):
        self.events = build_round()

    def test_sample_round_is_one_round_of_18_holes(self):
        holes = {e["hole"] for e in self.events if e["type"] == "hole_complete"}
        self.assertEqual(holes, set(range(1, 19)))
        self.assertEqual({e["round_no"] for e in self.events}, {42})

    def test_sample_round_scores_59(self):
        rc = [e for e in self.events if e["type"] == "round_complete"][0]
        self.assertEqual(rc["score"], 59)
        self.assertEqual(rc["score_to_par"], -13)

    def test_sample_log_is_deterministic(self):
        self.assertEqual(build_round(), self.events)

    def test_sample_log_validates_and_loads(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "round.jsonl"
            path.write_text("\n".join(json.dumps(e) for e in self.events))
            loaded = load_events(path)
        self.assertEqual(len(loaded), len(self.events))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.moments = score_round(build_round())
        self.by_hole_type = {(m.hole, m.moment_type): m for m in self.moments}

    def test_ace_scores_100(self):
        m = self.by_hole_type[(12, "hole_out")]
        self.assertEqual(m.drama, 100)

    def test_road_to_59_scores_100(self):
        m = self.by_hole_type[(18, "road_to_59")]
        self.assertEqual(m.drama, 100)

    def test_eagle_scores_95(self):
        m = self.by_hole_type[(2, "eagle")]
        self.assertEqual(m.drama, 95)

    def test_near_miss_scores_85(self):
        m = self.by_hole_type[(3, "near_miss")]
        self.assertEqual(m.drama, 85)

    def test_worst_miss_and_recovery_both_fire_on_hole_5(self):
        self.assertEqual(self.by_hole_type[(5, "worst_miss")].drama, 75)
        self.assertEqual(self.by_hole_type[(5, "recovery")].drama, 80)

    def test_best_decision_scores_75(self):
        m = self.by_hole_type[(7, "best_decision")]
        self.assertEqual(m.drama, 75)
        self.assertIn("knock", m.context["decision_reasoning"].lower())

    def test_streak_scores_70(self):
        m = self.by_hole_type[(11, "streak")]
        self.assertEqual(m.drama, 70)

    def test_birdie_drought_rule_h6_birdie_scores_nothing(self):
        self.assertNotIn((6, "birdie"), self.by_hole_type)

    def test_first_birdie_scores_60(self):
        m = self.by_hole_type[(1, "birdie")]
        self.assertEqual(m.drama, 60)

    def test_record_chase_moments_fire_deep_in_the_round(self):
        for hole in (13, 16, 17):
            self.assertIn((hole, "record_chase"), self.by_hole_type)

    def test_record_chase_boost_applies(self):
        # H17 record-chase is on pace and deep: 70 + 10 boost = 80.
        self.assertEqual(self.by_hole_type[(17, "record_chase")].drama, 80)

    def test_bogey_hole_scores_nothing(self):
        # H14 ends in bogey: the bunker splash is not a recovery.
        self.assertFalse(any(m.hole == 14 for m in self.moments))

    def test_h11_pitch_is_gir_not_a_recovery(self):
        # The H11 pitch reaches the green in regulation on the par 5,
        # so there is no up-and-down recovery moment — only the streak.
        self.assertNotIn((11, "recovery"), self.by_hole_type)
        self.assertIn((11, "streak"), self.by_hole_type)

    def test_worst_miss_hook_names_the_mishit(self):
        _, clips, _, _ = run_pipeline(build_round())
        miss = next(c for c in clips if c.moment_type == "worst_miss")
        self.assertIn("Chunked", miss.title)

    def test_shot_moment_caption_uses_score_after_the_hole(self):
        _, clips, _, _ = run_pipeline(build_round())
        ace = next(c for c in clips if c.moment_type == "hole_out")
        self.assertIn("10 under par through 12", ace.caption)

    def test_all_moments_meet_replay_threshold(self):
        self.assertTrue(all(m.save_replay for m in self.moments))

    def test_moments_sorted_by_drama_desc(self):
        dramas = [m.drama for m in self.moments]
        self.assertEqual(dramas, sorted(dramas, reverse=True))


class SelectionTests(unittest.TestCase):
    def test_queue_is_top_two_and_both_90_plus(self):
        _, clips, queue, _ = run_pipeline(build_round())
        self.assertEqual(len(queue), 2)
        self.assertTrue(all(c.drama >= 90 for c in queue))
        self.assertEqual({c.hole for c in queue}, {18, 12})

    def test_one_clip_per_hole_unless_90_plus(self):
        _, clips, _, _ = run_pipeline(build_round())
        queue = select_daily_queue(clips)
        holes = [c.hole for c in queue]
        self.assertEqual(len(holes), len(set(holes)))

    def test_second_clip_needs_90_plus(self):
        # A round with only sub-90 moments yields a one-clip queue.
        moments = score_round(build_round())
        low = [m for m in moments if m.drama < 90]
        clips = [assemble_clip(m) for m in low]
        queue = select_daily_queue(clips)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0].drama, max(c.drama for c in clips))


class AssemblyTests(unittest.TestCase):
    def test_clip_card_has_in_out_points_within_60s_buffer(self):
        _, clips, _, _ = run_pipeline(build_round())
        for clip in clips:
            self.assertGreaterEqual(clip.source_in_s, 0)
            self.assertEqual(clip.source_out_s, 60)
            self.assertEqual(clip.source_out_s - clip.source_in_s, clip.duration_s)
            self.assertTrue(20 <= clip.duration_s <= 35)

    def test_hook_is_first_and_segments_cover_duration(self):
        _, clips, _, _ = run_pipeline(build_round())
        clip = clips[0]
        self.assertEqual(clip.segments[0]["name"], "hook")
        self.assertEqual(clip.segments[0]["start_s"], 0)
        self.assertEqual(clip.segments[-1]["end_s"], clip.duration_s)
        self.assertEqual(clip.segments[-1]["name"], "payoff")

    def test_big_moments_get_slow_motion(self):
        _, clips, _, _ = run_pipeline(build_round())
        ace = next(c for c in clips if c.moment_type == "hole_out")
        self.assertTrue(ace.slow_motion)
        self.assertTrue(any(s["name"] == "shot_slow_motion" for s in ace.segments))

    def test_platform_variants_differ(self):
        _, clips, _, _ = run_pipeline(build_round())
        clip = clips[0]
        self.assertEqual(set(clip.platforms), set(PLATFORM_SPECS))
        self.assertNotEqual(clip.platforms["shorts"]["hashtags"],
                            clip.platforms["reels"]["hashtags"])
        for variant in clip.platforms.values():
            self.assertIn("#masgolfs", variant["hashtags"])
            self.assertIn("#roadto59", variant["hashtags"])

    def test_source_filename_encodes_moment(self):
        _, clips, _, _ = run_pipeline(build_round())
        ace = next(c for c in clips if c.moment_type == "hole_out")
        self.assertTrue(ace.source_file.startswith("round0042-hole12-hole_out-"))


class ManifestTests(unittest.TestCase):
    def test_manifest_schema(self):
        _, _, _, manifest = run_pipeline(build_round())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["round"]["score"], 59)
        self.assertEqual(manifest["round"]["score_to_par"], -13)
        self.assertEqual(manifest["summary"]["queue_size"], 2)
        self.assertEqual(len(manifest["queue"]), 2)
        self.assertEqual(len(manifest["library"]), manifest["summary"]["clips_saved"])
        queue_ids = {c["clip_id"] for c in manifest["queue"]}
        self.assertEqual(queue_ids, set(manifest["_queue_ids"]))


if __name__ == "__main__":
    unittest.main()
