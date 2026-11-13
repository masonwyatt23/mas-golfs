"""Tests for the sim -> event-bus live publish hook (sim/events.py).

Run:  python -m unittest discover -s sim/tests -v -k live
"""

import json
import os
import socket
import threading
import time
import unittest
from unittest import mock

from bus.client import BusPublisher
from bus.server import create_server
from sim.events import DEFAULT_BUS_URL, EventEmitter, resolve_bus_url
from sim import live_demo


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _BusFixture:
    """A real bus server on an ephemeral port, in a thread."""

    def __init__(self):
        self.port = _free_port()
        self.server = create_server("127.0.0.1", self.port,
                                    state_file="none")
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.1}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"ws://127.0.0.1:{self.port}"

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5.0)


class TestResolveBusUrl(unittest.TestCase):
    def test_unset_is_off(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve_bus_url())

    def test_env_url_wins(self):
        with mock.patch.dict(os.environ,
                             {"MAS_GOLFS_BUS_URL": "ws://example:4456"}):
            self.assertEqual(resolve_bus_url(), "ws://example:4456")

    def test_env_empty_means_default(self):
        with mock.patch.dict(os.environ, {"MAS_GOLFS_BUS_URL": ""}):
            self.assertEqual(resolve_bus_url(), DEFAULT_BUS_URL)

    def test_explicit_arg_wins_over_env(self):
        with mock.patch.dict(os.environ,
                             {"MAS_GOLFS_BUS_URL": "ws://example:4456"}):
            self.assertEqual(resolve_bus_url("ws://other:1"),
                             "ws://other:1")
            self.assertEqual(resolve_bus_url(""), DEFAULT_BUS_URL)


class TestLivePublish(unittest.TestCase):
    def test_emitter_publishes_to_live_bus(self):
        with _BusFixture() as url:
            sub = BusPublisher(url, connect_timeout=5.0)
            sub.connect()
            snapshot = json.loads(sub.recv_text(timeout=5.0))
            self.assertEqual(snapshot.get("event"), "round_state")

            emitter = EventEmitter(1, bus_url=url)
            emitter.emit("round_start", course={"name": "Wyatt National"})
            emitter.emit("hole_start", hole=1)
            emitter.emit("milestone", detail="birdie")

            seen = [json.loads(sub.recv_text(timeout=5.0)).get("event")
                    for _ in range(3)]
            self.assertEqual(seen, ["round_start", "hole_start",
                                    "milestone"])
            self.assertEqual(emitter.live_dropped, 0)
            self.assertTrue(emitter.live_connected)
            emitter.close()
            sub.close()

    def test_emitter_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            emitter = EventEmitter(1)
            self.assertFalse(emitter.live_enabled)
            self.assertIsNone(emitter.bus_url)
            event = emitter.emit("round_start")
            self.assertEqual(len(emitter.events), 1)
            self.assertEqual(event["type"], "round_start")

    def test_emitter_survives_dead_bus(self):
        # A port nothing listens on: connection refused immediately.
        url = f"ws://127.0.0.1:{_free_port()}"
        emitter = EventEmitter(2, bus_url=url)
        t0 = time.monotonic()
        for _ in range(50):
            emitter.emit("hole_start", hole=1)
        dt = time.monotonic() - t0
        # One short connect attempt, then backoff-gated skips: fast.
        self.assertLess(dt, 5.0, f"dead bus stalled emits for {dt:.2f}s")
        self.assertEqual(len(emitter.events), 50)
        self.assertEqual(emitter.live_dropped, 50)
        self.assertFalse(emitter.live_connected)
        # After the backoff window a retry is attempted, still harmless.
        time.sleep(0.6)
        emitter.emit("hole_start", hole=2)
        self.assertEqual(len(emitter.events), 51)
        emitter.close()

    def test_dead_bus_does_not_change_events(self):
        url = f"ws://127.0.0.1:{_free_port()}"
        emitter = EventEmitter(3, bus_url=url)
        a = emitter.emit("round_start", course={"name": "Wyatt National"})
        b = emitter.emit("hole_start", hole=1)
        self.assertEqual(a["seq"], 1)
        self.assertEqual(b["seq"], 2)
        self.assertEqual(a["round_id"], "R0003")
        self.assertEqual([e["type"] for e in emitter.events],
                         ["round_start", "hole_start"])
        emitter.close()


class TestLiveDemo(unittest.TestCase):
    def test_demo_round_completes(self):
        port = _free_port()
        summary = live_demo.run(port=port, rounds=1, fast=True)
        self.assertEqual(summary["rounds_played"], 1)
        self.assertEqual(len(summary["scores"]), 1)
        self.assertGreater(summary["events_emitted"], 100)
        self.assertTrue(summary["round_end_received"],
                        f"subscriber error: {summary['subscriber_error']}")
        self.assertIsNone(summary["subscriber_error"])
        # shot_result fans out to strike/apex/landing, so the subscriber
        # sees at least as many envelopes as the sim emitted events.
        self.assertGreaterEqual(summary["events_received"],
                                summary["events_emitted"])
        self.assertIn("round_start", summary["types_seen"])
        self.assertIn("round_end", summary["types_seen"])


if __name__ == "__main__":
    unittest.main()
