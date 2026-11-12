"""Tests for the Mas Golfs commentary service.

Run from the repo root:
    python3 -m unittest discover -s commentary/tests -v

Everything here is offline: the stub LLM and stub TTS stand in for the
model servers, and a fake bus stands in for the sim. No network, no
model downloads, no paid APIs.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from commentary import normalize as norm
from commentary.bus import FakeBus, normalize_event
from commentary.cache import AudioCache, cache_key, standard_line
from commentary.config import ConfigError, load_config, parse_yaml_subset
from commentary.demo import run_demo
from commentary.llm import LLMClient, LLMError, StubLLM
from commentary.prompts import render_user_prompt
from commentary.service import CommentaryService
from commentary.tts import StubTTS


def make_service(**overrides):
    """Build a service against a temp dir, with a controllable clock."""
    tmp = tempfile.mkdtemp(prefix="mas-golfs-commentary-test-")
    cfg = {
        "bus": {"url": "ws://localhost:4456"},
        "llm": {
            "backend": "mlx",
            "mlx": {"model": "mlx-community/Qwen3-1.7B-4bit",
                    "base_url": "http://localhost:8080/v1"},
            "ollama": {"model": "qwen3:1.7b",
                       "base_url": "http://localhost:11434/v1"},
            "generation": {"temperature": 0.7, "max_tokens": 120,
                           "timeout_seconds": 10},
        },
        "tts": {
            "base_url": "http://localhost:8880/v1",
            "host": {"voice": "am_michael", "speed": 1.0},
            "color": {"voice": "af_sky", "speed": 1.05},
            "cache_dir": os.path.join(tmp, "tts-cache"),
        },
        "limits": {"min_seconds_between_lines": 15,
                   "max_lines_per_hole": 4, "max_line_chars": 280},
        "paths": {
            "decision_log": os.path.join(tmp, "decisions.jsonl"),
            "output_log": os.path.join(tmp, "output.jsonl"),
            "audio_dir": os.path.join(tmp, "audio"),
        },
        "dry_run": False,
        "stub_llm": True,
    }
    cfg.update(overrides)
    clock = _ManualClock()
    service = CommentaryService(
        cfg, llm=LLMClient(StubLLM()), tts=StubTTS(), clock=clock.now)
    return service, clock, tmp


class _ManualClock:
    """A clock the test advances by hand."""

    def __init__(self, start: float = 1000.0):
        self.value = start

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class TestConfig(unittest.TestCase):
    def test_repo_config_loads(self):
        cfg = load_config()
        self.assertEqual(cfg["llm"]["backend"], "mlx")
        self.assertEqual(cfg["tts"]["host"]["voice"], "am_michael")
        self.assertEqual(cfg["tts"]["color"]["voice"], "af_sky")
        self.assertEqual(cfg["limits"]["min_seconds_between_lines"], 15)
        self.assertEqual(cfg["limits"]["max_lines_per_hole"], 4)
        self.assertEqual(cfg["limits"]["max_line_chars"], 280)

    def test_yaml_subset_nested_and_lists(self):
        parsed = parse_yaml_subset(
            "a:\n  b: 1\n  c: true\n  d: [x, y]\n  e: 'quoted'\n")
        self.assertEqual(
            parsed, {"a": {"b": 1, "c": True, "d": ["x", "y"], "e": "quoted"}})

    def test_bad_indent_raises(self):
        with self.assertRaises(ConfigError):
            parse_yaml_subset("a:\n   b: 1\n")


class TestNormalize(unittest.TestCase):
    def test_numbers_to_words(self):
        self.assertEqual(norm.words_to_number("twelve"), 12)
        self.assertEqual(norm.words_to_number("fifty-nine"), 59)
        self.assertEqual(norm.words_to_number("one eighty-seven"), 187)
        self.assertEqual(norm.words_to_number("two hundred seventy-eight"), 278)
        self.assertIsNone(norm.words_to_number("fairway"))

    def test_validate_numbers_accepts_event_numbers(self):
        event = {"total_yds": 278, "dist_to_pin_ft": 12, "hole": 12}
        self.assertTrue(norm.validate_numbers(
            "That's in the fairway, 278 yards, twelve feet.", event, None))

    def test_validate_numbers_rejects_invented_number(self):
        event = {"total_yds": 278, "dist_to_pin_ft": 12, "hole": 12}
        self.assertFalse(norm.validate_numbers(
            "That's 310 yards, a career best.", event, None))
        self.assertFalse(norm.validate_numbers(
            "Twelve feet, and the crowd of fifty thousand roars.",
            event, None))

    def test_prose_one_is_not_a_number(self):
        # "the next one" must not be treated as the number 1.
        event = {"total_yds": 278, "hole": 12}
        self.assertTrue(norm.validate_numbers(
            "That is the result, and it leaves him a look at the next one.",
            event, None))
        self.assertTrue(norm.validate_numbers(
            "The one thing to work on is the approach.", event, None))

    def test_number_phrases_still_validated(self):
        event = {"score_to_par": -1, "thru": 11, "hole": 12}
        self.assertTrue(norm.validate_numbers(
            "Mas is one under par through eleven.", event, None))
        self.assertFalse(norm.validate_numbers(
            "Mas is two under par through eleven.", event, None))

    def test_banned_words_stripped(self):
        cleaned = norm.apply_hard_filter(
            "That was an unbelievable shot, amazing!")
        self.assertNotIn("unbelievable", cleaned.lower())
        self.assertNotIn("amazing", cleaned.lower())
        self.assertNotIn("!", cleaned)

    def test_cap_length_truncates_at_sentence(self):
        long_line = ("First sentence here. " * 20).strip()
        capped = norm.cap_length(long_line, 280)
        self.assertIsNotNone(capped)
        self.assertLessEqual(len(capped), 280)
        self.assertTrue(capped.endswith("."))
        # A single unbreakable sentence over the cap is dropped.
        self.assertIsNone(norm.cap_length("word " * 100, 280))

    def test_normalize_for_tts(self):
        spoken = norm.normalize_for_tts(
            "7-iron, 164 yards, -2 through 11, wind 8 mph.")
        self.assertIn("seven iron", spoken)
        self.assertIn("one sixty-four yards", spoken)
        self.assertIn("two under par", spoken)
        self.assertIn("miles per hour", spoken)
        self.assertNotIn("164", spoken)


class TestCache(unittest.TestCase):
    def test_cache_key_is_voice_sensitive(self):
        self.assertNotEqual(
            cache_key("am_michael", "Hello."),
            cache_key("af_sky", "Hello."))
        self.assertEqual(
            cache_key("am_michael", "Hello."),
            cache_key("am_michael", "Hello."))

    def test_standard_hole_intro(self):
        line = standard_line("hole_start", {
            "hole": 12, "hole_name": "The Picture", "par": 3, "yards": 164},
            None)
        self.assertEqual(line, "Hole 12, The Picture. Par 3, 164 yards.")

    def test_standard_score_update(self):
        line = standard_line("hole_end", {}, {"thru": 11, "score_to_par": -2})
        self.assertEqual(line, "Mas is 2 under par through 11.")

    def test_standard_round_opener(self):
        line = standard_line("round_start", {
            "round_no": 47, "course": "Wyatt National", "target_score": 59},
            None)
        self.assertEqual(line, "Round 47 at Wyatt National. Mas is chasing 59.")

    def test_standard_59_off_pace(self):
        line = standard_line("fifty_nine_watch", {"status": "off_pace"}, None)
        self.assertEqual(line, "The 59 is off the table for this round.")
        self.assertIsNone(
            standard_line("fifty_nine_watch", {"status": "on_pace"}, None))

    def test_audio_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AudioCache(tmp)
            self.assertIsNone(cache.get("am_michael", "Hello."))
            path = cache.put("am_michael", "Hello.", b"fake-audio")
            self.assertEqual(cache.get("am_michael", "Hello."), path)
            self.assertGreater(cache.size_bytes(), 0)


class TestPrompts(unittest.TestCase):
    def test_decision_template_fills(self):
        prompt = render_user_prompt("decision", "color", {
            "hole": 12, "par": 3, "score_to_par": "-2", "thru": 11,
            "club": "7-iron", "shot_type": "full", "target_yards": 164,
            "aim": "middle of the green", "lie": "tee",
            "wind_mph": 8, "wind_dir": "into",
            "reason": "pin is back left", "risk": "standard"})
        self.assertIn("7-iron", prompt)
        self.assertIn("164", prompt)
        self.assertIn("pin is back left", prompt)

    def test_missing_field_renders_dash_not_crash(self):
        prompt = render_user_prompt("landing", "host", {"club": "driver"})
        self.assertIn("—", prompt)


class TestBusNormalization(unittest.TestCase):
    def test_flat_sim_envelope(self):
        event = normalize_event(
            {"type": "landing", "seq": 7, "round_no": 47, "hole": 12,
             "total_yds": 164})
        self.assertEqual(event["type"], "landing")
        self.assertEqual(event["total_yds"], 164)

    def test_nested_broadcast_stack_envelope(self):
        event = normalize_event(
            {"event": "landing", "seq": 7, "round": 47, "hole": 12,
             "data": {"total_yds": 164, "lie": "green"}})
        self.assertEqual(event["type"], "landing")
        self.assertEqual(event["total_yds"], 164)
        self.assertEqual(event["lie"], "green")

    def test_nested_milestone_kind_does_not_overwrite_event_type(self):
        # broadcast-stack §1.2: data.type is the milestone KIND.
        event = normalize_event(
            {"event": "milestone", "seq": 11, "round": 47, "hole": 12,
             "data": {"type": "birdie_streak", "detail": "three in a row"}})
        self.assertEqual(event["type"], "milestone")
        self.assertEqual(event["detail"], "three in a row")


class TestServiceDecisions(unittest.TestCase):
    def test_hole_intro_plays_from_cache(self):
        service, clock, tmp = make_service()
        service.handle_event({
            "type": "hole_start", "seq": 1, "round_no": 47, "hole": 12,
            "par": 3, "yards": 164, "hole_name": "The Picture"})
        played = read_jsonl(service.cfg["paths"]["output_log"])
        self.assertEqual(len(played), 1)
        self.assertEqual(played[0]["speaker"], "host")
        self.assertIn("Hole 12", played[0]["text"])
        decisions = read_jsonl(service.cfg["paths"]["decision_log"])
        self.assertTrue(decisions[0]["cache_hit"])
        self.assertTrue(decisions[0]["played"])

    def test_apex_straight_ball_is_silence(self):
        service, clock, tmp = make_service()
        service.handle_event({
            "type": "apex", "seq": 1, "round_no": 47, "hole": 12,
            "apex_ft": 90, "carry_yds": 160, "shape": "straight",
            "curve_yds": 1, "club": "7-iron"})
        self.assertEqual(read_jsonl(service.cfg["paths"]["output_log"]), [])
        decisions = read_jsonl(service.cfg["paths"]["decision_log"])
        self.assertEqual(decisions, [])  # no line planned at all: silence

    def test_apex_draw_is_named(self):
        service, clock, tmp = make_service()
        service.handle_event({
            "type": "apex", "seq": 1, "round_no": 47, "hole": 12,
            "apex_ft": 92, "carry_yds": 158, "shape": "draw",
            "curve_yds": 8, "club": "7-iron"})
        played = read_jsonl(service.cfg["paths"]["output_log"])
        self.assertEqual(len(played), 1)
        self.assertEqual(played[0]["speaker"], "color")

    def test_director_hold_queues_line_until_landing(self):
        service2, clock2, tmp2 = make_service()
        service2.cfg["limits"]["min_seconds_between_lines"] = 0
        # The swing starts: a milestone during the swing must be held,
        # not spoken over it.
        service2.handle_event({"type": "shot_start", "seq": 1,
                               "round_no": 47, "hole": 12})
        service2.handle_event({
            "type": "milestone", "seq": 2, "round_no": 47, "hole": 12,
            "detail": "birdie streak", "score_to_par": -2, "thru": 11})
        self.assertEqual(
            len(read_jsonl(service2.cfg["paths"]["output_log"])), 0)
        service2.handle_event({
            "type": "landing", "seq": 3, "round_no": 47, "hole": 12,
            "total_yds": 164, "lie": "green", "dist_to_pin_ft": 12,
            "result": "green_hit", "club": "7-iron"})
        played = read_jsonl(service2.cfg["paths"]["output_log"])
        # Held milestone lines release first, then the landing line.
        self.assertEqual(len(played), 3)
        self.assertEqual(played[0]["event"], "milestone")

    def test_rate_limit_drops_second_line_within_15s(self):
        service, clock, tmp = make_service()
        service.handle_event({
            "type": "hole_start", "seq": 1, "round_no": 47, "hole": 12,
            "par": 3, "yards": 164, "hole_name": "The Picture"})
        # 5 seconds later: another line is due but the 15s cap blocks it.
        clock.advance(5)
        service.handle_event({
            "type": "landing", "seq": 2, "round_no": 47, "hole": 12,
            "total_yds": 164, "lie": "green", "dist_to_pin_ft": 12,
            "result": "green_hit", "club": "7-iron"})
        played = read_jsonl(service.cfg["paths"]["output_log"])
        self.assertEqual(len(played), 1)
        decisions = read_jsonl(service.cfg["paths"]["decision_log"])
        self.assertEqual(decisions[-1]["drop_reason"], "rate_limited")
        # 20 seconds later the same event plays.
        clock.advance(20)
        service.handle_event({
            "type": "landing", "seq": 3, "round_no": 47, "hole": 12,
            "total_yds": 164, "lie": "green", "dist_to_pin_ft": 12,
            "result": "green_hit", "club": "7-iron"})
        self.assertEqual(len(read_jsonl(service.cfg["paths"]["output_log"])), 2)

    def test_max_four_lines_per_hole(self):
        service, clock, tmp = make_service()
        service.cfg["limits"]["min_seconds_between_lines"] = 0
        for seq in range(1, 7):
            service.handle_event({
                "type": "putt_result", "seq": seq, "round_no": 47,
                "hole": 12, "dist_ft": 12, "made": False,
                "putts_this_hole": seq})
        played = read_jsonl(service.cfg["paths"]["output_log"])
        self.assertEqual(len(played), 4)
        decisions = read_jsonl(service.cfg["paths"]["decision_log"])
        self.assertEqual(decisions[-1]["drop_reason"], "rate_limited")

    def test_59_watch_lines_are_fresh_never_cached(self):
        service, clock, tmp = make_service()
        service.handle_event({
            "type": "fifty_nine_watch", "seq": 1, "round_no": 47, "hole": 12,
            "status": "on_pace", "score_to_par": -3, "thru": 12,
            "strokes_remaining": 1, "probability": 38, "holes_left": 6})
        decisions = read_jsonl(service.cfg["paths"]["decision_log"])
        self.assertTrue(any(d["played"] for d in decisions))
        self.assertTrue(all(not d["cache_hit"] for d in decisions))

    def test_llm_failure_drops_line_never_paid_api(self):
        service, clock, tmp = make_service()

        class FailingLLM:
            name = "failing"

            def generate(self, speaker, user_prompt):
                raise LLMError("connection refused")

        service.llm = LLMClient(FailingLLM(), None)
        service.handle_event({
            "type": "decision", "seq": 1, "round_no": 47, "hole": 12,
            "club": "7-iron", "shot_type": "full", "target_yards": 164,
            "aim": "middle", "reason": "pin back left", "risk": "standard",
            "lie": "tee", "wind_mph": 8, "wind_dir": "into"})
        self.assertEqual(read_jsonl(service.cfg["paths"]["output_log"]), [])
        decisions = read_jsonl(service.cfg["paths"]["decision_log"])
        self.assertEqual(len(decisions), 1)
        self.assertFalse(decisions[0]["played"])
        self.assertIn("llm_failed", decisions[0]["drop_reason"])

    def test_llm_failover_to_ollama(self):
        service, clock, tmp = make_service()

        class FailingLLM:
            name = "mlx"

            def generate(self, speaker, user_prompt):
                raise LLMError("mlx down")

        switches = []
        service.llm = LLMClient(
            FailingLLM(), StubLLM(),
            on_switch=lambda a, b, r: switches.append((a, b)))
        service.handle_event({
            "type": "decision", "seq": 1, "round_no": 47, "hole": 12,
            "club": "7-iron", "shot_type": "full", "target_yards": 164,
            "aim": "middle", "reason": "pin back left", "risk": "standard",
            "lie": "tee", "wind_mph": 8, "wind_dir": "into"})
        self.assertEqual(len(read_jsonl(service.cfg["paths"]["output_log"])), 1)
        self.assertEqual(switches, [("mlx", "stub")])

    def test_silence_budget_tracked(self):
        service, clock, tmp = make_service()
        service.handle_event({
            "type": "hole_start", "seq": 1, "round_no": 47, "hole": 12,
            "par": 3, "yards": 164, "hole_name": "The Picture"})
        clock.advance(120)
        self.assertLess(service.silence_fraction(), 0.5)

    def test_fake_bus_end_to_end(self):
        service, clock, tmp = make_service()
        service.cfg["limits"]["min_seconds_between_lines"] = 0
        events = [
            {"type": "round_start", "seq": 1, "round_no": 47, "hole": 1,
             "course": "Wyatt National", "par": 72, "target_score": 59,
             "last10_avg": 70.4, "handicap": "+3.1"},
            {"type": "hole_start", "seq": 2, "round_no": 47, "hole": 12,
             "par": 3, "yards": 164, "hole_name": "The Picture"},
            {"type": "landing", "seq": 3, "round_no": 47, "hole": 12,
             "total_yds": 164, "lie": "green", "dist_to_pin_ft": 12,
             "result": "green_hit", "club": "7-iron"},
        ]
        bus = FakeBus(events)
        while True:
            try:
                raw = bus.recv_text()
            except Exception:
                break
            service.handle_event(json.loads(raw))
        played = read_jsonl(service.cfg["paths"]["output_log"])
        self.assertEqual(len(played), 3)


class TestDemo(unittest.TestCase):
    def test_demo_runs_offline(self):
        from commentary.config import load_config
        result = run_demo(load_config())
        self.assertGreater(len(result["played"]), 0)
        self.assertLessEqual(result["silence_fraction"], 0.5)
        speakers = {r["speaker"] for r in result["played"]}
        self.assertEqual(speakers, {"host", "color"})


if __name__ == "__main__":
    unittest.main()
