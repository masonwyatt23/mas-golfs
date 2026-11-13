"""Tests for the ffmpeg assembly step (clip_pipeline.assemble).

The ffmpeg binary itself is never invoked here: every subprocess call
goes through an injected fake runner, so these tests assert the command
construction — the filter graph, the 0.5x slow-mo factor, the burned-in
caption text, and the missing-input behaviour. A real end-to-end run
against ffmpeg is verified manually (see README § "Verifying with a
real ffmpeg run").

Run with:

    python -m unittest discover -s tests -v
    (from clip-pipeline/)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clip_pipeline import run_pipeline  # noqa: E402
from clip_pipeline.assemble import (  # noqa: E402
    assemble_clip_file,
    assemble_manifest,
    build_ffmpeg_command,
    build_filter_graph,
    check_ffmpeg,
    escape_drawtext,
    has_audio,
    segment_window,
)
from clip_pipeline.sample_log import build_round  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


class FakeRunner:
    """Stand-in for subprocess.run. Records calls; answers ffprobe
    with an audio stream by default, ffmpeg with success by default."""

    def __init__(self, returncode=0, stderr="", audio=True):
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stderr = stderr
        self.audio = audio

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        if "ffprobe" in str(cmd[0]):
            streams = '[{"index": 1}]' if self.audio else "[]"
            return SimpleNamespace(
                returncode=0, stdout=f'{{"streams": {streams}}}', stderr=""
            )
        return SimpleNamespace(returncode=self.returncode, stdout="", stderr=self.stderr)

    @property
    def ffmpeg_calls(self):
        return [c for c in self.calls if "ffmpeg" in str(c[0])]


def _clips():
    _, clips, _, manifest = run_pipeline(build_round())
    by_type = {c.moment_type: c for c in clips}
    return by_type["hole_out"].to_dict(), by_type["birdie"].to_dict(), manifest


class EscapeTests(unittest.TestCase):
    def test_colon_apostrophe_percent_backslash_escaped(self):
        # The apostrophe becomes a typographic ’ (U+2019): \' breaks
        # ffmpeg's filtergraph parser (verified: exit 234).
        self.assertEqual(
            escape_drawtext("It's 10:30 — 100% \\ done"),
            "It\u2019s 10\\:30 — 100\\% \\\\ done",
        )

    def test_newline_becomes_space(self):
        self.assertEqual(escape_drawtext("one\ntwo"), "one two")


class SegmentWindowTests(unittest.TestCase):
    def test_full_speed_segment_consumes_slot_seconds_of_source(self):
        # The manifest's shot segment declares 28 s of source (29-57) for
        # a 26 s output slot (6-32): the output timeline is authoritative,
        # so only the first 26 s are consumed (29-55). The last 3 s are
        # the slow-mo replay's territory anyway.
        seg = {"start_s": 6, "end_s": 32, "source_start_s": 29,
               "source_end_s": 57, "speed": 1.0}
        self.assertEqual(segment_window(seg), (29.0, 55.0, 1.0))

    def test_slow_mo_segment_consumes_half_its_source_range(self):
        # 3 s output slot at 0.5x -> 1.5 s of source (54-55.5), so the
        # finished clip stays exactly duration_s long.
        seg = {"start_s": 29, "end_s": 32, "source_start_s": 54,
               "source_end_s": 57, "speed": 0.5}
        self.assertEqual(segment_window(seg), (54.0, 55.5, 0.5))


class FilterGraphTests(unittest.TestCase):
    def setUp(self):
        self.ace, self.birdie, _ = _clips()

    def test_slow_mo_clip_has_half_speed_video_and_audio(self):
        graph = build_filter_graph(self.ace, FONT, audio=True)
        self.assertIn("setpts=2.000*PTS", graph)
        self.assertIn("atempo=0.5", graph)

    def test_slow_mo_truncates_preceding_shot_segment(self):
        # The slow-mo segment sits inside the shot segment's span
        # (29-32 inside 6-32). The shot's full-speed portion must end
        # where the replay begins, or the clip runs 3 s over duration_s
        # (verified: 38 s for a 35 s card before this fix).
        graph = build_filter_graph(self.ace, FONT, audio=True)
        self.assertIn("trim=start=29.000:end=52.000", graph)
        self.assertNotIn("trim=start=29.000:end=55.000", graph)

    def test_effective_segment_slots_sum_to_duration(self):
        from clip_pipeline.assemble import effective_segments

        for clip in (self.ace, self.birdie):
            slots = effective_segments(clip["segments"])
            total = sum(s["end_s"] - s["start_s"] for s in slots)
            self.assertEqual(total, clip["duration_s"])

    def test_plain_clip_has_no_slow_motion(self):
        graph = build_filter_graph(self.birdie, FONT, audio=True)
        self.assertNotIn("2.000*PTS", graph)
        self.assertNotIn("atempo=", graph)
        self.assertIn("setpts=PTS-STARTPTS", graph)

    def test_hook_line_and_caption_text_are_burned_in(self):
        graph = build_filter_graph(self.ace, FONT, audio=True)
        self.assertIn("HOLE IN ONE.", graph)
        self.assertIn("REPLAY", graph)
        # The result card (payoff segment text) is burned in too.
        self.assertIn("Result card", graph)
        self.assertIn("drawtext=", graph)

    def test_no_font_means_no_drawtext_but_clip_still_builds(self):
        graph = build_filter_graph(self.ace, None, audio=True)
        self.assertNotIn("drawtext=", graph)
        self.assertIn("concat=", graph)

    def test_graph_crops_to_9x16_and_concats_all_segments(self):
        graph = build_filter_graph(self.ace, FONT, audio=True)
        self.assertIn("scale=1080:1920", graph)
        self.assertIn("crop=1080:1920", graph)
        self.assertIn("fps=30", graph)
        self.assertIn("concat=n=5:v=1:a=1[outv][outa]", graph)

    def test_video_only_graph_when_no_audio(self):
        graph = build_filter_graph(self.ace, FONT, audio=False)
        self.assertNotIn("[outa]", graph)
        self.assertIn("concat=n=5:v=1:a=0[outv]", graph)
        self.assertNotIn("atrim=", graph)

    def test_segments_play_in_manifest_order_hook_first(self):
        graph = build_filter_graph(self.ace, FONT, audio=True)
        self.assertLess(graph.index("HOLE IN ONE."), graph.index("REPLAY"))
        self.assertLess(graph.index("REPLAY"), graph.index("Result card"))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.ace, _, _ = _clips()

    def test_command_shape(self):
        cmd = build_ffmpeg_command(
            self.ace, "/rec/round0042-hole12-hole_out-0086.mp4",
            "/out/round0042-hole12-hole_out-0086.mp4",
            font=FONT, audio=True,
        )
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-i", cmd)
        self.assertEqual(cmd[cmd.index("-i") + 1],
                         "/rec/round0042-hole12-hole_out-0086.mp4")
        self.assertIn("-filter_complex", cmd)
        self.assertIn("[outv]", cmd)
        self.assertIn("[outa]", cmd)
        self.assertIn("libx264", cmd)
        self.assertIn("+faststart", cmd)
        # Output file is the last argument.
        self.assertEqual(cmd[-1], "/out/round0042-hole12-hole_out-0086.mp4")

    def test_video_only_command_has_no_audio_map_or_codec(self):
        cmd = build_ffmpeg_command(
            self.ace, "/rec/x.mp4", "/out/x.mp4", font=FONT, audio=False
        )
        self.assertNotIn("[outa]", cmd)
        self.assertNotIn("aac", cmd)

    def test_slow_mo_factor_appears_in_command_filter_graph(self):
        cmd = build_ffmpeg_command(
            self.ace, "/rec/x.mp4", "/out/x.mp4", font=FONT, audio=True
        )
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("setpts=2.000*PTS", graph)


class HasAudioTests(unittest.TestCase):
    def test_audio_stream_detected(self):
        self.assertTrue(has_audio(Path("/rec/x.mp4"), runner=FakeRunner(audio=True)))

    def test_no_audio_stream(self):
        self.assertFalse(has_audio(Path("/rec/x.mp4"), runner=FakeRunner(audio=False)))

    def test_ffprobe_failure_means_no_audio(self):
        def boom(cmd, **kwargs):
            raise OSError("ffprobe not found")

        self.assertFalse(has_audio(Path("/rec/x.mp4"), runner=boom))


class CheckFfmpegTests(unittest.TestCase):
    def test_ffmpeg_present(self):
        self.assertTrue(check_ffmpeg("ffmpeg"))

    def test_missing_binary_reports_false(self):
        self.assertFalse(check_ffmpeg("ffmpeg-definitely-not-installed"))


class AssembleClipTests(unittest.TestCase):
    def setUp(self):
        self.ace, self.birdie, _ = _clips()

    def _recordings(self, td, names):
        rec = Path(td) / "recordings"
        rec.mkdir()
        for name in names:
            (rec / name).write_bytes(b"fake mp4")
        return rec

    def test_output_filename_matches_replay_filename(self):
        with tempfile.TemporaryDirectory() as td:
            rec = self._recordings(td, [self.ace["source"]["replay_file"]])
            out = Path(td) / "out"
            runner = FakeRunner()
            result = assemble_clip_file(self.ace, rec, out, runner=runner)
            self.assertEqual(result.status, "done")
            self.assertEqual(result.output_path.name,
                             self.ace["source"]["replay_file"])
            self.assertEqual(result.duration_s, self.ace["duration_s"])
            # The ffmpeg call used the replay file as its input.
            self.assertEqual(len(runner.ffmpeg_calls), 1)
            self.assertIn(str(rec / self.ace["source"]["replay_file"]),
                          runner.ffmpeg_calls[0])

    def test_sidecar_carries_post_copy(self):
        with tempfile.TemporaryDirectory() as td:
            rec = self._recordings(td, [self.ace["source"]["replay_file"]])
            out = Path(td) / "out"
            result = assemble_clip_file(self.ace, rec, out, runner=FakeRunner())
            sidecar = result.output_path.with_suffix(".txt")
            self.assertTrue(sidecar.is_file())
            text = sidecar.read_text()
            self.assertIn(self.ace["title"], text)
            self.assertIn("#masgolfs", text)
            self.assertIn("#roadto59", text)

    def test_missing_recording_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            rec = self._recordings(td, [])
            out = Path(td) / "out"
            runner = FakeRunner()
            result = assemble_clip_file(self.ace, rec, out, runner=runner)
            self.assertEqual(result.status, "skipped")
            self.assertIsNone(result.output_path)
            self.assertEqual(runner.ffmpeg_calls, [])

    def test_ffmpeg_failure_is_reported_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as td:
            rec = self._recordings(td, [self.ace["source"]["replay_file"]])
            out = Path(td) / "out"
            runner = FakeRunner(returncode=1, stderr="Invalid data found")
            result = assemble_clip_file(self.ace, rec, out, runner=runner)
            self.assertEqual(result.status, "failed")
            self.assertIn("Invalid data found", result.message)


class AssembleManifestTests(unittest.TestCase):
    def setUp(self):
        self.ace, self.birdie, self.manifest = _clips()

    def test_queue_assembles_and_report_is_written(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td) / "recordings"
            rec.mkdir()
            for clip in self.manifest["queue"]:
                (rec / clip["source"]["replay_file"]).write_bytes(b"fake mp4")
            out = Path(td) / "out"
            results = assemble_manifest(
                self.manifest, rec, out, runner=FakeRunner()
            )
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r.status == "done" for r in results))
            report = json.loads((out / "assembly_report.json").read_text())
            self.assertEqual(report["summary"], {
                "attempted": 2, "done": 2, "skipped": 0, "failed": 0,
            })

    def test_missing_recording_skips_one_clip_and_queue_continues(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td) / "recordings"
            rec.mkdir()
            # Only the first queued clip has a recording.
            first = self.manifest["queue"][0]
            (rec / first["source"]["replay_file"]).write_bytes(b"fake mp4")
            out = Path(td) / "out"
            results = assemble_manifest(
                self.manifest, rec, out, runner=FakeRunner()
            )
            self.assertEqual(
                [r.status for r in results], ["done", "skipped"]
            )
            report = json.loads((out / "assembly_report.json").read_text())
            self.assertEqual(report["summary"]["skipped"], 1)
            self.assertEqual(report["summary"]["done"], 1)

    def test_dry_run_builds_commands_without_calling_ffmpeg(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td) / "recordings"
            rec.mkdir()
            for clip in self.manifest["queue"]:
                (rec / clip["source"]["replay_file"]).write_bytes(b"fake mp4")
            out = Path(td) / "out"
            runner = FakeRunner()
            results = assemble_manifest(
                self.manifest, rec, out, runner=runner, dry_run=True
            )
            self.assertEqual(runner.ffmpeg_calls, [])
            self.assertTrue(all(r.status == "done" for r in results))
            self.assertIn("dry run", results[0].message)


if __name__ == "__main__":
    unittest.main()
