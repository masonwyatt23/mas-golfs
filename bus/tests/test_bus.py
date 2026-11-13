"""Tests for the Mas Golfs event bus (``bus/``).

Covers the live server end to end (real sockets on an ephemeral port)
plus the pure translation/state functions. Stdlib ``unittest`` only.

Run: ``python -m unittest discover -s bus/tests -v``
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest

from bus.client import BusPublisher, BusError
from bus.server import create_server
from bus.translate import RoundState, format_handicap, iso_ts, translate_event

# --- Sample sim-flat events (shapes copied from sim/engine.py output) -----

ROUND_START = {
    "type": "round_start", "v": 1, "event_id": "evt_20261112_0001_0001",
    "ts": 1794441601000, "round_id": "R0001", "round_no": 47, "hole": 0,
    "shot_no": 0, "seq": 1,
    "course": {"name": "Wyatt National", "par": 72, "rating": 76.1,
               "slope": 142, "yardage": 7602},
    "target_score": 59, "handicap_index": 3.1, "last10_avg": 70.4,
    "form": "neutral",
}

HOLE_START = {
    "type": "hole_start", "v": 1, "event_id": "evt_20261112_0001_0002",
    "ts": 1794441602000, "round_id": "R0001", "round_no": 47, "hole": 12,
    "shot_no": 0, "seq": 2, "par": 3, "yardage": 164,
    "name": "The Picture", "tee": "back",
    "pin": {"x_ft": -15, "y_ft": 0, "zone": "mid_left", "difficulty": 0.5},
    "hole_wind": {"mph": 12, "dir_deg": 204, "effect": "down"},
}

SHOT_DECISION = {
    "type": "shot_decision", "v": 1, "event_id": "evt_20261112_0001_0003",
    "ts": 1794441603000, "round_id": "R0001", "round_no": 47, "hole": 12,
    "shot_no": 1, "seq": 3,
    "situation": {"lie": "tee", "distance_yd": 164, "elevation_ft": -8,
                  "wind_mph": 12, "wind_effect": "down", "to_pin_yd": 164},
    "decision": {"shot_type": "full", "club": "7-iron",
                 "target": {"aim_point": "the pin", "aim_offset_ft": 0.0,
                            "intended_shape": "straight",
                            "intended_traj": "normal",
                            "intended_carry_yd": 158},
                 "reasoning": "Full shot at the pin — trust the number.",
                 "alternatives_considered": []},
    "ev_strokes": 2.9, "risk": 0.1, "confidence": 0.98,
}

SHOT_RESULT = {
    "type": "shot_result", "v": 1, "event_id": "evt_20261112_0001_0004",
    "ts": 1794441604000, "round_id": "R0001", "round_no": 47, "hole": 12,
    "shot_no": 1, "seq": 4, "club": "7-iron", "shot_type": "full",
    "contact": {"quality": "pure", "strike_x_mm": 4.6, "strike_y_mm": 1.4,
                "face_deg": -1.69, "path_deg": 0.43,
                "club_speed_mph": 98.0},
    "launch": {"ball_speed_mph": 132.0, "launch_deg": 19.0,
               "spin_rpm": 6800, "spin_axis_deg": 0.6, "apex_ft": 78.0,
               "carry_yd": 158.0, "total_yd": 164.0, "curve_ft": -9.0,
               "offline_ft": -9.0},
    "outcome": {"lie": "green", "distance_to_pin_ft": 12.0,
                "on_green": True, "fairway_hit": False, "gir": True,
                "hazard": None, "penalty": 0, "in_water": False,
                "ob": False},
    "shot_quality": 0.9, "commentary": "Right at it.", "drama": 0.6,
}

HOLE_COMPLETE = {
    "type": "hole_complete", "v": 1, "event_id": "evt_20261112_0001_0010",
    "ts": 1794441610000, "round_id": "R0001", "round_no": 47, "hole": 12,
    "shot_no": 0, "seq": 10, "par": 3, "score": 2, "score_name": "birdie",
    "score_to_par": -1,
    "strokes_gained": {"ott": 0.0, "app": 0.4, "arg": 0.0, "putt": 0.3,
                       "total": 0.7},
    "hole_stats": {"fairway_hit": None, "gir": True, "putts": 1,
                   "up_and_down": None, "sand_save": None, "penalties": 0,
                   "driving_yd": None, "approach_ft": 12.0},
    "fifty_nine_watch": {"hole": 12, "score_so_far": -2,
                         "strokes_vs_pace": -0.4, "strokes_remaining": 3,
                         "prob_break_60": 0.42, "status": "on_pace",
                         "best_pace": -0.4, "best_pace_hole": 12,
                         "alive_on_18": True, "on_pace_at_turn": True},
    "commentary": "Birdie at The Picture. -2 through 12.",
}


def _recv_json(client: BusPublisher, timeout: float = 5.0) -> dict:
    return json.loads(client.recv_text(timeout=timeout))


class BusServerTestCase(unittest.TestCase):
    """Live-server tests on an ephemeral port."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_file = os.path.join(self._tmp.name, "last_event")
        self.server = create_server("127.0.0.1", 0,
                                    state_file=self.state_file)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.05},
                                       daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.url = f"ws://127.0.0.1:{self.port}"
        self.clients: list[BusPublisher] = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def connect(self) -> BusPublisher:
        client = BusPublisher(self.url)
        client.connect()
        self.clients.append(client)
        return client

    def test_handshake_and_snapshot_on_connect(self):
        client = self.connect()
        first = _recv_json(client)
        self.assertEqual(first["event"], "round_state")
        state = first["data"]["round_state"]
        self.assertEqual(state["golfer"], "Mas")
        self.assertEqual(state["target_score"], 59)
        self.assertEqual(state["thru"], 0)

    def test_handshake_rejects_plain_http(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            sock.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
            response = sock.recv(4096)
        finally:
            sock.close()
        self.assertTrue(response.startswith(b"HTTP/1.1 400"),
                        f"expected 400, got {response[:60]!r}")

    def test_broadcast_fanout_and_no_self_echo(self):
        sub1 = self.connect()
        sub2 = self.connect()
        _recv_json(sub1)  # snapshot
        _recv_json(sub2)  # snapshot
        pub = self.connect()
        _recv_json(pub)  # snapshot
        pub.publish(SHOT_DECISION)
        for sub in (sub1, sub2):
            evt = _recv_json(sub)
            self.assertEqual(evt["event"], "decision")
            self.assertEqual(evt["hole"], 12)
            self.assertEqual(evt["data"]["club"], "7-iron")
            self.assertEqual(evt["data"]["risk"], "safe")
        with self.assertRaises(TimeoutError):
            pub.recv_text(timeout=0.5)  # publisher gets no echo

    def test_shot_result_fans_out_to_three_events(self):
        sub = self.connect()
        _recv_json(sub)
        pub = self.connect()
        _recv_json(pub)
        pub.publish(SHOT_RESULT)
        strike = _recv_json(sub)
        apex = _recv_json(sub)
        landing = _recv_json(sub)
        self.assertEqual(
            [strike["event"], apex["event"], landing["event"]],
            ["strike", "apex", "landing"])
        self.assertEqual(strike["data"]["ball_speed_mph"], 132.0)
        self.assertEqual(strike["data"]["smash_factor"], 1.35)
        self.assertEqual(strike["data"]["contact"], "pure")
        self.assertEqual(apex["data"]["apex_ft"], 78.0)
        self.assertEqual(apex["data"]["carry_yds"], 158.0)
        self.assertEqual(apex["data"]["shape"], "draw")
        self.assertEqual(landing["data"]["total_yds"], 164.0)
        self.assertEqual(landing["data"]["lie"], "green")
        self.assertEqual(landing["data"]["result"], "green_hit")
        self.assertEqual(landing["data"]["dist_to_pin_ft"], 12.0)

    def test_snapshot_on_reconnect_reflects_play(self):
        pub = self.connect()
        _recv_json(pub)
        pub.publish(ROUND_START)
        time.sleep(0.1)
        pub.publish(HOLE_START)
        time.sleep(0.1)
        pub.publish(HOLE_COMPLETE)
        time.sleep(0.2)
        late = self.connect()
        snap = _recv_json(late)
        self.assertEqual(snap["event"], "round_state")
        state = snap["data"]["round_state"]
        self.assertEqual(state["round"], 47)
        self.assertEqual(state["hole"], 12)
        self.assertEqual(state["thru"], 1)
        self.assertEqual(state["score_to_par"], -1)
        self.assertEqual(state["current_hole"]["name"], "The Picture")
        self.assertEqual(len(state["scorecard"]), 1)
        self.assertEqual(state["scorecard"][0]["score"], 2)
        self.assertEqual(state["stats"]["gir"], "1/1")
        self.assertEqual(state["stats"]["putts"], 1)
        self.assertEqual(state["streak"]["birdies"], 1)

    def test_request_round_state(self):
        client = self.connect()
        _recv_json(client)  # connect snapshot
        client.request_round_state()
        snap = _recv_json(client)
        self.assertEqual(snap["event"], "round_state")
        self.assertEqual(snap["data"]["round_state"]["golfer"], "Mas")

    def test_subscribe_control_message_is_not_broadcast(self):
        sub = self.connect()
        _recv_json(sub)
        pub = self.connect()
        _recv_json(pub)
        pub.send_text(json.dumps({"type": "subscribe", "events": "*"}))
        with self.assertRaises(TimeoutError):
            sub.recv_text(timeout=0.5)

    def test_last_event_file_updates_on_publish(self):
        self.assertFalse(os.path.exists(self.state_file))
        pub = self.connect()
        _recv_json(pub)
        pub.publish(ROUND_START)
        time.sleep(0.3)
        self.assertTrue(os.path.exists(self.state_file))
        with open(self.state_file, encoding="ascii") as fh:
            written = int(fh.read().strip())
        self.assertLess(abs(int(time.time()) - written), 5)

    def test_malformed_message_ignored_connection_survives(self):
        sub = self.connect()
        _recv_json(sub)
        pub = self.connect()
        _recv_json(pub)
        pub.send_text("this is not json {")
        pub.send_text(json.dumps({"not": "an event at all"}))
        # The connection is still alive: a valid publish still arrives.
        pub.publish(HOLE_START)
        evt = _recv_json(sub)
        self.assertEqual(evt["event"], "hole_start")

    def test_ping_pong_frames(self):
        # Raw socket: send a masked ping, expect an unmasked pong.
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            sock.sendall(
                f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n".encode("ascii"))
            response = b""
            while b"\r\n\r\n" not in response:
                response += sock.recv(4096)
            self.assertIn(b"101", response.split(b"\r\n", 1)[0])
            # Bytes after the header terminator may already include the
            # snapshot frame — keep them, don't drop them.
            _head, _sep, tail = response.partition(b"\r\n\r\n")
            buf = bytearray(tail)
            # Skip the snapshot frame the server sends on connect.
            self._skip_one_frame(sock, buf)
            mask = os.urandom(4)
            payload = b"hello"
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            sock.sendall(bytes([0x89, 0x80 | len(payload)]) + mask + masked)
            header = self._read_exact(sock, buf, 2)
            self.assertEqual(header[0] & 0x0F, 0xA)  # pong opcode
            self.assertEqual(header[1] & 0x7F, len(payload))
            self.assertEqual(self._read_exact(sock, buf, len(payload)),
                             payload)
        finally:
            sock.close()

    @staticmethod
    def _read_exact(sock: socket.socket, buf: bytearray, count: int) -> bytes:
        while len(buf) < count:
            chunk = sock.recv(65536)
            if not chunk:
                raise BusError("connection closed while reading a frame")
            buf.extend(chunk)
        out = bytes(buf[:count])
        del buf[:count]
        return out

    def _skip_one_frame(self, sock: socket.socket, buf: bytearray) -> None:
        header = self._read_exact(sock, buf, 2)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(
                ">H", self._read_exact(sock, buf, 2))[0]
        elif length == 127:
            length = struct.unpack(
                ">Q", self._read_exact(sock, buf, 8))[0]
        self._read_exact(sock, buf, length)


class TranslateTestCase(unittest.TestCase):
    """Pure translation + state tests (no sockets)."""

    def test_control_messages_translate_to_nothing(self):
        for raw in ({"type": "subscribe", "events": "*"},
                    {"type": "request_round_state"},
                    {"type": "ping"}):
            self.assertEqual(translate_event(raw), [])

    def test_envelope_passthrough(self):
        raw = {"event": "landing", "seq": 9, "ts": "2026-11-12T06:00:00.000Z",
               "round": 47, "hole": 12,
               "data": {"total_yds": 164, "lie": "green"}}
        out = translate_event(raw)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["event"], "landing")
        self.assertEqual(out[0]["data"]["total_yds"], 164)

    def test_milestone_maps_kind_to_type(self):
        out = translate_event({
            "type": "milestone", "seq": 5, "round_no": 47, "hole": 12,
            "kind": "birdie_streak", "text": "Three birdies in a row!",
            "value": 3})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["data"]["type"], "birdie_streak")
        self.assertEqual(out[0]["data"]["detail"],
                         "Three birdies in a row!")

    def test_hole_complete_maps_to_hole_end(self):
        out = translate_event(HOLE_COMPLETE)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["event"], "hole_end")
        self.assertEqual(out[0]["data"]["score_to_par"], -1)
        self.assertEqual(out[0]["data"]["putts"], 1)

    def test_format_handicap(self):
        self.assertEqual(format_handicap(3.1), "+3.1")
        self.assertEqual(format_handicap(0), "0.0")
        self.assertEqual(format_handicap(-1.5), "-1.5")
        self.assertEqual(format_handicap("+3.1"), "+3.1")
        self.assertEqual(format_handicap(None), "+3.1")

    def test_iso_ts(self):
        self.assertEqual(iso_ts(1794441601000), "2026-11-12T00:00:01.000Z")

    def test_round_state_stats_and_streaks(self):
        state = RoundState()
        state.apply(translate_event(ROUND_START)[0])
        state.apply(translate_event(HOLE_START)[0])
        state.apply(translate_event(HOLE_COMPLETE)[0])
        snap = state.snapshot()
        self.assertEqual(snap["stats"]["gir"], "1/1")
        self.assertEqual(snap["stats"]["fairways"], "0/0")  # par 3: no FW
        self.assertEqual(snap["streak"]["birdies"], 1)
        self.assertEqual(snap["streak"]["bogey_free"], 1)
        self.assertEqual(snap["fifty_nine_watch"]["status"], "on_pace")

    def test_round_state_resets_on_new_round(self):
        state = RoundState()
        state.apply(translate_event(ROUND_START)[0])
        state.apply(translate_event(HOLE_COMPLETE)[0])
        self.assertEqual(state.snapshot()["thru"], 1)
        state.apply(translate_event(ROUND_START)[0])
        self.assertEqual(state.snapshot()["thru"], 0)
        self.assertEqual(state.snapshot()["scorecard"], [])


if __name__ == "__main__":
    unittest.main()
