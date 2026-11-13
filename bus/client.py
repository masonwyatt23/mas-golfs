"""Event-bus publisher client (docs/broadcast-stack.md §1).

The sim engine publishes events by opening a WebSocket connection to
the bus and sending one JSON object per text message — the same socket
the subscribers read from. This module is the small stdlib-only client
for that side of the connection (handshake, masked text frames,
ping/pong), mirroring ``commentary/bus.py``'s ``WebSocketBus`` without
depending on the commentary package.

Usage::

    from bus.client import BusPublisher

    with BusPublisher("ws://localhost:4456") as pub:
        pub.publish({"type": "round_start", "round_no": 47, ...})
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.parse


class BusError(RuntimeError):
    """Raised when the event bus cannot be reached or a frame is corrupt."""


class BusPublisher:
    """Minimal RFC 6455 WebSocket client (text frames)."""

    def __init__(self, url: str = "ws://localhost:4456",
                 connect_timeout: float = 5.0):
        self.url = url
        self.connect_timeout = connect_timeout
        self.sock: socket.socket | None = None
        self._buf = bytearray()

    def __enter__(self) -> "BusPublisher":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

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
        sock = socket.create_connection((host, port),
                                        timeout=self.connect_timeout)
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
        # Any bytes after the header terminator belong to the next frame
        # (the server sends the round_state snapshot immediately) — keep
        # them in the read buffer instead of dropping them.
        _head, _sep, tail = response.partition(b"\r\n\r\n")
        self._buf = bytearray(tail)

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

    def publish(self, event: dict) -> None:
        """Send one event (a dict) to the bus for fan-out."""
        self._send_frame(0x1, json.dumps(event).encode("utf-8"))

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def recv_text(self, timeout: float | None = None) -> str:
        """Read one complete text message, answering pings on the way.

        Raises ``TimeoutError`` if ``timeout`` elapses first.
        """
        if self.sock is None:
            raise BusError("not connected")
        self.sock.settimeout(timeout)
        fragments: list[bytes] = []
        while True:
            try:
                header = self._read_exact(2)
            except socket.timeout as exc:
                raise TimeoutError("timed out waiting for a bus message") \
                    from exc
            opcode = header[0] & 0x0F
            fin = bool(header[0] & 0x80)
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
                if fin:
                    return b"".join(fragments).decode("utf-8")
            # Other opcodes are ignored.

    def request_round_state(self) -> None:
        self.send_text(json.dumps({"type": "request_round_state"}))

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            # Drain anything already in the receive buffer first: the bus
            # sends a round_state snapshot to every connection on connect,
            # and a publish-only client never reads it. Closing a socket
            # with unread data in its buffer makes the kernel send RST
            # instead of FIN, which kills the server-side handler while
            # our queued publishes are still unread — a burst publisher
            # loses its tail (harness test_02: only the first 3 of 21
            # events arrived).
            self._drain()
            self._send_frame(0x8, b"")
            # Wait briefly for the server's close echo: the server
            # answers it only after reading every frame we sent, so the
            # echo is the flush barrier for our publishes. Best effort —
            # time out and close anyway.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    self.recv_text(
                        timeout=max(0.1, deadline - time.monotonic()))
                except BusError:
                    break  # close echo (or the server closed) — flushed
                except (TimeoutError, OSError):
                    break
            self.sock.close()
        except OSError:
            pass
        self.sock = None

    def _drain(self) -> None:
        """Discard whatever is already in the receive buffer, non-blocking."""
        if self.sock is None:
            return
        self.sock.settimeout(0)
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
        except (BlockingIOError, OSError):
            pass


def publish_events(url: str, events, delay: float = 0.0) -> int:
    """Publish an iterable of event dicts; returns the count sent."""
    count = 0
    with BusPublisher(url) as pub:
        for event in events:
            pub.publish(event)
            count += 1
            if delay:
                time.sleep(delay)
    return count
