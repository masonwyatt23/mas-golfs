"""Event-bus client (docs/broadcast-stack.md §1).

The bus is a local WebSocket server on ``localhost:4456``. The sim is
the single publisher; this service is a subscriber. Messages are JSON
objects, one event per message.

The box has no ``websockets`` package installed and the service is
stdlib-only, so :class:`WebSocketBus` is a minimal RFC 6455 client
built on ``socket``: handshake, text frames (including fragmented and
>64KB frames), ping/pong, and close. It is deliberately small — this is
a local trusted socket, not a public-facing client.

Two envelopes are accepted, because the spec and the sim disagree:

* The broadcast-stack envelope: ``{"event": <type>, "seq": ..., "data": {...}}``
* The sim's flat envelope (sim/events.py): ``{"type": <type>, "seq": ...,
  "round_no": ..., "hole": ..., ...fields}``

Both are normalized to the flat form before the service sees them.

On reconnect the server re-sends the latest ``round_state`` snapshot
(broadcast-stack §1.1); the service also requests one explicitly.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.parse

from .config import load_config


class BusError(RuntimeError):
    """Raised when the event bus cannot be reached or a frame is corrupt."""


def normalize_event(raw: dict) -> dict:
    """Normalize either bus envelope to the flat form the service uses.

    Returns a dict with ``type``, ``seq``, ``hole``, ``round_no`` and
    all type-specific fields at the top level.
    """
    event = dict(raw)
    if "data" in event and isinstance(event["data"], dict):
        data = event.pop("data")
        event.update(data)
    if "event" in event and "type" not in event:
        event["type"] = event.pop("event")
    event.setdefault("seq", 0)
    event.setdefault("hole", 0)
    event.setdefault("round_no", 0)
    return event


class WebSocketBus:
    """Minimal RFC 6455 WebSocket client (text frames only)."""

    def __init__(self, url: str, connect_timeout: float = 5.0):
        self.url = url
        self.connect_timeout = connect_timeout
        self.sock: socket.socket | None = None
        self._buf = bytearray()

    def connect(self) -> None:
        parsed = urllib.parse.urlparse(self.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80
        path = parsed.path or "/"
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock = socket.create_connection((host, port), timeout=self.connect_timeout)
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                sock.close()
                raise BusError("bus closed the connection during handshake")
            response += chunk
        if b"101" not in response.split(b"\r\n", 1)[0]:
            sock.close()
            raise BusError(f"bus handshake failed: {response[:200]!r}")
        self.sock = sock
        self._buf = bytearray()

    def _read_exact(self, count: int) -> bytes:
        while len(self._buf) < count:
            if self.sock is None:
                raise BusError("not connected")
            chunk = self.sock.recv(65536)
            if not chunk:
                raise BusError("bus closed the connection")
            self._buf.extend(chunk)
        out = bytes(self._buf[:count])
        del self._buf[:count]
        return out

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.sock is None:
            raise BusError("not connected")
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", length))
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def recv_text(self, timeout: float | None = None) -> str:
        """Read one complete text message, answering pings on the way."""
        if self.sock is None:
            raise BusError("not connected")
        self.sock.settimeout(timeout)
        fragments: list[bytes] = []
        while True:
            header = self._read_exact(2)
            opcode = header[0] & 0x0F
            masked = header[1] & 0x80
            length = header[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else None
            payload = self._read_exact(length)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x9:  # ping -> pong
                self._send_frame(0xA, payload)
                continue
            if opcode == 0x8:  # close
                raise BusError("bus closed the connection")
            if opcode in (0x1, 0x0):  # text / continuation
                fragments.append(payload)
                if header[0] & 0x80:  # FIN
                    return b"".join(fragments).decode("utf-8")
            # Other opcodes are ignored.

    def request_round_state(self) -> None:
        self.send_text(json.dumps({"type": "request_round_state"}))

    def close(self) -> None:
        if self.sock is not None:
            try:
                self._send_frame(0x8, b"")
                self.sock.close()
            except OSError:
                pass
            self.sock = None


class FakeBus:
    """An in-process event source for the demo and the tests.

    Yields pre-built event dicts (normalized the same way as the real
    bus) instead of opening a socket.
    """

    def __init__(self, events: list[dict]):
        self.events = [normalize_event(e) for e in events]
        self.index = 0

    def recv_text(self, timeout: float | None = None) -> str:
        if self.index >= len(self.events):
            raise BusError("fake bus exhausted")
        event = self.events[self.index]
        self.index += 1
        return json.dumps(event)

    def request_round_state(self) -> None:
        return None

    def close(self) -> None:
        return None


def build_bus(cfg: dict | None = None) -> WebSocketBus:
    cfg = cfg or load_config()
    return WebSocketBus(cfg["bus"]["url"])


def connect_with_backoff(bus: WebSocketBus, cfg: dict,
                         sleep=time.sleep) -> None:
    """Connect, retrying with exponential backoff up to the configured max."""
    delay = cfg["bus"].get("reconnect_initial_seconds", 1)
    max_delay = cfg["bus"].get("reconnect_max_seconds", 30)
    while True:
        try:
            bus.connect()
            bus.request_round_state()
            return
        except (BusError, OSError, socket.timeout):
            sleep(delay)
            delay = min(delay * 2, max_delay)
