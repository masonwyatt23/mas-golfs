"""Unit tests for the MLX verification pack.

Stdlib only. The MLX parts cannot run on this Linux VM (MLX is Apple
Silicon only), so the tests drive everything testable here — prompt
loading, timing math, <think>/banned-word/number validation, the HTTP
client against a stub OpenAI-compatible server, the blind A/B writer,
soak sampling and verdicts, and the platform gate — with a stub server
standing in for mlx-lm. What the tests cannot prove (real model load,
real swap behaviour, real latency on the box) is labelled as such in
the README and must be run on the 8GB MacBook Pro.

Run:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mlx_verify as mv  # noqa: E402

PACK_DIR = os.path.join(os.path.dirname(__file__), "..")
EVENTS_PATH = os.path.join(PACK_DIR, "events.json")

# The stub's fixed line: no numbers, no banned words, under 280 chars,
# so it passes the audition validation by construction.
STUB_LINE = "That is the result, and it leaves him a look at the next one."
LEAKY_LINE = "<think>Let me think about the wind.</think> That is the result."


class StubHandler(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible server. Behaviour via class attributes."""

    mode = "normal"  # normal | leaky | slow

    def log_message(self, *args):  # silence the server
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json(200, {"data": [{"id": "stub-model"}]})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "not found"})
            return
        text = LEAKY_LINE if self.mode == "leaky" else STUB_LINE
        if body.get("stream"):
            self._send_sse(text)
        else:
            self._send_json(200, {
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 12},
            })

    def _send_json(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, text):
        # One SSE data frame per word, then [DONE].
        frames = []
        for word in text.split(" "):
            chunk = {"choices": [{"delta": {"content": word + " "}}]}
            frames.append(f"data: {json.dumps(chunk)}\n\n")
        frames.append("data: [DONE]\n\n")
        payload = "".join(frames).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_stub(mode="normal"):
    StubHandler.mode = mode
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


class TestPlatformGate(unittest.TestCase):
    def test_apple_silicon_ok(self):
        gate = mv.platform_gate("Darwin", "arm64")
        self.assertTrue(gate["ok"])

    def test_linux_rejected(self):
        gate = mv.platform_gate("Linux", "x86_64")
        self.assertFalse(gate["ok"])
        self.assertIn("macOS", gate["reason"])

    def test_intel_mac_rejected(self):
        gate = mv.platform_gate("Darwin", "x86_64")
        self.assertFalse(gate["ok"])
        self.assertIn("Apple Silicon", gate["reason"])

    def test_real_platform_on_this_vm(self):
        # This VM is Linux x86_64: the gate must fail here, cleanly.
        gate = mv.platform_gate()
        self.assertFalse(gate["ok"])


class TestEvents(unittest.TestCase):
    def test_real_events_file_loads(self):
        events = mv.load_events(EVENTS_PATH)
        self.assertEqual(len(events), 50)

    def test_all_template_pairs_covered(self):
        events = mv.load_events(EVENTS_PATH)
        pairs = {(e["event_type"], e["speaker"]) for e in events}
        self.assertEqual(len(pairs), 17)

    def test_prompts_are_rendered(self):
        events = mv.load_events(EVENTS_PATH)
        for ev in events:
            self.assertNotIn("{{", ev["user_prompt"])
            self.assertNotIn("{", ev["user_prompt"].replace("—", ""))

    def test_missing_key_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump([{"id": "x", "event_type": "landing"}], fh)
            path = fh.name
        with self.assertRaises(ValueError):
            mv.load_events(path)

    def test_duplicate_id_rejected(self):
        events = mv.load_events(EVENTS_PATH)[:2]
        events[1] = dict(events[1], id=events[0]["id"])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(events, fh)
            path = fh.name
        with self.assertRaises(ValueError):
            mv.load_events(path)

    def test_bad_speaker_rejected(self):
        events = [dict(mv.load_events(EVENTS_PATH)[0], speaker="referee")]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(events, fh)
            path = fh.name
        with self.assertRaises(ValueError):
            mv.load_events(path)


class TestStats(unittest.TestCase):
    def test_percentile(self):
        values = sorted([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(mv.percentile(values, 50), 2.0)
        self.assertEqual(mv.percentile(values, 99), 4.0)
        self.assertEqual(mv.percentile(values, 100), 4.0)

    def test_percentile_empty_raises(self):
        with self.assertRaises(ValueError):
            mv.percentile([], 99)

    def test_latency_stats(self):
        stats = mv.latency_stats([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(stats["n"], 4)
        self.assertEqual(stats["median_s"], 2.5)
        self.assertEqual(stats["p99_s"], 4.0)
        self.assertEqual(stats["max_s"], 4.0)


class TestThinkLeaks(unittest.TestCase):
    def test_clean_line(self):
        self.assertEqual(mv.find_think_leaks(STUB_LINE), [])

    def test_opening_tag(self):
        self.assertTrue(mv.find_think_leaks("<think>hmm</think>"))

    def test_closing_tag_only(self):
        self.assertTrue(mv.find_think_leaks("words</think>"))

    def test_case_insensitive(self):
        self.assertTrue(mv.find_think_leaks("<Think>hmm</Think>"))

    def test_escaped_form(self):
        self.assertTrue(mv.find_think_leaks("&lt;think&gt;hmm"))

    def test_word_thinking_is_not_a_leak(self):
        self.assertEqual(mv.find_think_leaks("He is thinking about the putt."), [])


class TestAuditionValidation(unittest.TestCase):
    PROMPT = ("Mas is on hole 3 (par 3), 1 under par through 2.\n"
              "He has chosen 7-iron, full, target 187 yards.")

    def test_clean_line_passes(self):
        # Every number in the line (seven -> 7, 187) appears in the prompt.
        result = mv.validate_line("Seven iron, 187, into a light wind. "
                                  "That is the shot he wanted.",
                                  self.PROMPT)
        self.assertTrue(result["ok"])

    def test_word_form_numbers_count_as_present(self):
        # "twelve" in the line matches "12" in the prompt.
        result = mv.validate_line("That is twelve feet.",
                                  "Putt from 12 feet: made.")
        self.assertTrue(result["ok"])

    def test_hyphenated_fifty_nine_matches_59(self):
        result = mv.validate_line("The fifty-nine is still in play.",
                                  "59 Watch, status on_pace.")
        self.assertTrue(result["ok"])

    def test_invented_number_flagged(self):
        result = mv.validate_line("That is fifteen feet.",
                                  "Putt from 12 feet: made.")
        self.assertFalse(result["ok"])
        self.assertIn("invented numbers", result["failures"][0])

    def test_banned_word_flagged(self):
        result = mv.validate_line("An unbelievable shot from 187 yards.",
                                  self.PROMPT)
        self.assertFalse(result["ok"])
        self.assertIn("unbelievable", result["failures"][0])

    def test_over_280_chars_flagged(self):
        result = mv.validate_line("x" * 281, self.PROMPT)
        self.assertFalse(result["ok"])

    def test_think_leak_flagged(self):
        result = mv.validate_line(LEAKY_LINE, self.PROMPT)
        self.assertFalse(result["ok"])


class TestChatClient(unittest.TestCase):
    def setUp(self):
        self.server, self.base_url = start_stub("normal")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_healthy(self):
        client = mv.ChatClient(self.base_url, "stub-model")
        self.assertTrue(client.healthy())

    def test_unhealthy_when_down(self):
        self.server.shutdown()
        client = mv.ChatClient(self.base_url, "stub-model")
        self.assertFalse(client.healthy())

    def test_generate_streaming(self):
        client = mv.ChatClient(self.base_url, "stub-model")
        result = client.generate("host", "Putt from 12 feet: made.")
        self.assertEqual(result["text"], STUB_LINE)
        self.assertTrue(result["streamed"])
        self.assertLessEqual(result["ttft_s"], result["total_s"])

    def test_generate_against_dead_server_raises(self):
        self.server.shutdown()
        client = mv.ChatClient(self.base_url, "stub-model", timeout_seconds=2.0)
        with self.assertRaises(mv.LLMError):
            client.generate("host", "Putt from 12 feet: made.")


class TestChecksAgainstStub(unittest.TestCase):
    def setUp(self):
        self.server, self.base_url = start_stub("normal")
        self.events = mv.load_events(EVENTS_PATH)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_latency_runs_and_passes_on_stub(self):
        client = mv.ChatClient(self.base_url, "stub-model")
        result = mv.run_latency(client, self.events, n=20)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(len(result["rows"]), 20)
        self.assertLess(result["stats"]["total"]["p99_s"], mv.LATENCY_P99_MAX_S)
        for row in result["rows"]:
            self.assertEqual(row["text"], STUB_LINE)

    def test_audition_passes_on_stub(self):
        client = mv.ChatClient(self.base_url, "stub-model")
        result = mv.run_audition(client, self.events, n=20)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["failed"], 0)

    def test_audition_fails_on_leaky_stub(self):
        self.server.shutdown()
        self.server.server_close()
        self.server, self.base_url = start_stub("leaky")
        client = mv.ChatClient(self.base_url, "stub-model")
        result = mv.run_audition(client, self.events, n=5)
        self.assertEqual(result["verdict"], "FAIL")

    def test_ab_writes_blinded_files(self):
        client_a = mv.ChatClient(self.base_url, mv.DEFAULT_MODEL)
        client_b = mv.ChatClient(self.base_url, mv.FALLBACK_MODEL)
        results, key = mv.run_ab(client_a, client_b, self.events, n=50, seed=7)
        self.assertEqual(len(results["rows"]), 50)
        self.assertEqual(set(key), {"A", "B", "flipped", "n"})
        self.assertEqual({key["A"], key["B"]},
                         {mv.DEFAULT_MODEL, mv.FALLBACK_MODEL})
        with tempfile.TemporaryDirectory() as tmp:
            md_path = os.path.join(tmp, "ab-side-by-side.md")
            mv.write_ab_side_by_side(results, md_path)
            text = open(md_path, encoding="utf-8").read()
            self.assertNotIn(mv.DEFAULT_MODEL, text)
            self.assertNotIn(mv.FALLBACK_MODEL, text)
            self.assertIn("**A**", text)
            self.assertIn("**B**", text)


class TestThinkScan(unittest.TestCase):
    def _write_json(self, texts):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"rows": [{"text": t} for t in texts]}, fh)
        fh.close()
        return fh.name

    def test_clean_100_lines_passes(self):
        path = self._write_json([STUB_LINE] * 100)
        result = mv.scan_think([path])
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["lines_scanned"], 100)

    def test_one_leak_fails(self):
        path = self._write_json([STUB_LINE] * 99 + [LEAKY_LINE])
        result = mv.scan_think([path])
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(len(result["hits"]), 1)

    def test_under_100_lines_incomplete(self):
        path = self._write_json([STUB_LINE] * 20)
        result = mv.scan_think([path])
        self.assertEqual(result["verdict"], "INCOMPLETE")

    def test_plain_text_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("\n".join([STUB_LINE] * 100) + "\n")
            path = fh.name
        result = mv.scan_think([path])
        self.assertEqual(result["verdict"], "PASS")


class TestSoakParsing(unittest.TestCase):
    def test_swap_zero(self):
        out = ("vm.swapusage: total = 64.00M  used =  0.00M  free = 64.00M  "
               "(encrypted)")
        self.assertEqual(mv.parse_swapusage(out), 0.0)

    def test_swap_megabytes(self):
        self.assertEqual(mv.parse_swapusage("vm.swapusage: used = 512.00M"), 512.0)

    def test_swap_gigabytes(self):
        self.assertEqual(mv.parse_swapusage("vm.swapusage: used =  1.50G"), 1536.0)

    def test_swap_unparseable(self):
        with self.assertRaises(ValueError):
            mv.parse_swapusage("no swap here")

    def test_ps_rss(self):
        self.assertEqual(mv.parse_ps_rss("  123456\n"), 123456)


class TestSoakVerdict(unittest.TestCase):
    def _samples(self, swap=0.0, rss=3000000, warmup=True):
        return [{"swap_used_mb": swap, "server_rss_kb": rss,
                 "warmup_ok": warmup}]

    def test_all_zero_passes(self):
        self.assertEqual(mv.soak_verdict(self._samples())["verdict"], "PASS")

    def test_any_swap_fails(self):
        samples = self._samples() + self._samples(swap=128.0)
        verdict = mv.soak_verdict(samples)
        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertEqual(verdict["max_swap_mb"], 128.0)

    def test_dead_server_fails(self):
        samples = [{"swap_used_mb": 0.0, "server_rss_kb": None}]
        self.assertEqual(mv.soak_verdict(samples)["verdict"], "FAIL")

    def test_failed_warmup_fails(self):
        self.assertEqual(mv.soak_verdict(self._samples(warmup=False))["verdict"],
                         "FAIL")

    def test_no_samples_incomplete(self):
        self.assertEqual(mv.soak_verdict([])["verdict"], "INCOMPLETE")


class TestSoakRunAgainstStub(unittest.TestCase):
    def test_short_soak_passes(self):
        server, base_url = start_stub("normal")
        try:
            client = mv.ChatClient(base_url, "stub-model")
            events = mv.load_events(EVENTS_PATH)
            sampler_calls = {"n": 0}

            def fake_sampler():
                sampler_calls["n"] += 1
                return (0.0, 3000000)

            summary = mv.run_soak(client, events, server_pid=None,
                                  minutes=0.01, sample_interval_s=0.2,
                                  warmup_every_s=0.2, sampler=fake_sampler)
            self.assertEqual(summary["verdict"], "PASS")
            self.assertGreaterEqual(sampler_calls["n"], 1)
            self.assertEqual(summary["max_swap_mb"], 0.0)
        finally:
            server.shutdown()
            server.server_close()


class TestVerifyShGateOnLinux(unittest.TestCase):
    def test_verify_sh_fails_cleanly_off_mac(self):
        # This VM is Linux: the pack must refuse with exit 2 and a clear
        # message, not attempt an install or a server start.
        proc = subprocess.run(
            ["bash", os.path.join(PACK_DIR, "verify.sh"), "check"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("macOS", proc.stdout + proc.stderr)

    def test_verify_sh_think_without_results_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, MLX_VERIFY_RESULTS_DIR=tmp)
            proc = subprocess.run(
                ["bash", os.path.join(PACK_DIR, "verify.sh"), "think"],
                capture_output=True, text=True, timeout=30, env=env)
            self.assertEqual(proc.returncode, 3)


if __name__ == "__main__":
    unittest.main()
