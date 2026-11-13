"""Mas Golfs event-bus server (docs/broadcast-stack.md §1).

A stdlib-only local WebSocket server on ``localhost:4456``. The sim
engine is the single publisher; NodeCG, the commentary service, the
director and the ambient engine are subscribers. No third-party
dependencies — the RFC 6455 handshake and framing are hand-rolled here,
mirroring the client in ``commentary/bus.py``.

Protocol (the contract every consumer relies on):

* On connect, the server sends the current ``round_state`` snapshot
  immediately (broadcast-stack §1.1), so a restarted component is never
  stale. A client may also ask for one at any time with
  ``{"type": "request_round_state"}``.
* A connected client publishes an event by sending one JSON object per
  WebSocket text message — either a sim-flat event (``sim/events.py``)
  or an already-enveloped broadcast event. The server translates it
  (``translate.py``), updates the round-state snapshot, writes the
  last-event timestamp file, and broadcasts it to every *other*
  connected client. The publisher never receives its own echo.
* ``{"type": "subscribe", ...}`` is accepted and ignored (NodeCG sends
  it on connect); ``{"type": "ping"}`` gets ``{"type": "pong"}``.
* WebSocket-level ping frames are answered with pong; close frames are
  echoed and the connection is dropped.

Watchdog contract (``ops/watchdog.sh`` check 3): on every published
event the server writes the epoch seconds of that event to the
last-event file (default ``ops/state/last_event`` under the repo home;
see :func:`default_state_file`). The watchdog pages ``event_bus_silent``
if the file is 60 s old — so the file is only ever written for real
events, never faked by a timer. If the sim stalls, the watchdog should
know.

Run it with ``python -m bus`` (see ``bus/__main__.py``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import socket
import socketserver
import struct
import threading
import time

from .translate import RoundState, snapshot_event, translate_event

log = logging.getLogger("mas-golfs.bus")

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4456
HANDSHAKE_TIMEOUT = 5.0
SOCKET_TIMEOUT = 1.0
PING_INTERVAL = 30.0


def default_state_file() -> str | None:
    """Resolve the watchdog's last-event file path.

    Precedence: ``MAS_GOLFS_STATE_FILE`` env (``"none"`` disables the
    file) > ``MAS_GOLFS_HOME/ops/state/last_event`` > the repo checkout
    this package lives in (``<repo>/ops/state/last_event``).
    """
    explicit = os.environ.get("MAS_GOLFS_STATE_FILE")
    if explicit:
        return None if explicit.strip().lower() == "none" else explicit
    home = os.environ.get("MAS_GOLFS_HOME")
    if home:
        return os.path.join(home, "ops", "state", "last_event")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "ops", "state", "last_event")


def _ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _encode_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    """Server-to-client frame: FIN set, never masked."""
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", length))
    return bytes(header) + payload


class BusServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """The event bus: subscriber registry, round state, sequencing."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler_class,
                 state_file: str | None = None):
        super().__init__(server_address, handler_class)
        self.state_file = state_file
        self.round_state = RoundState()
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._subscribers: set[_Connection] = set()
        self._sub_lock = threading.Lock()

    def next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def register(self, conn: "_Connection") -> None:
        with self._sub_lock:
            self._subscribers.add(conn)

    def unregister(self, conn: "_Connection") -> None:
        with self._sub_lock:
            self._subscribers.discard(conn)

    def subscriber_count(self) -> int:
        with self._sub_lock:
            return len(self._subscribers)

    def snapshot_envelope(self) -> dict:
        return snapshot_event(self.round_state.snapshot(), self.next_seq())

    def broadcast(self, envelopes: list[dict],
                  exclude: "_Connection | None" = None) -> None:
        """Send envelopes to every subscriber except ``exclude``."""
        if not envelopes:
            return
        payloads = [json.dumps(e).encode("utf-8") for e in envelopes]
        with self._sub_lock:
            targets = [c for c in self._subscribers if c is not exclude]
        dead: list[_Connection] = []
        for conn in targets:
            try:
                for payload in payloads:
                    conn.send_frame(payload)
            except OSError:
                dead.append(conn)
        for conn in dead:
            self.unregister(conn)

    def touch_last_event(self) -> None:
        """Record the epoch seconds of the latest published event.

        Atomic (temp file + rename) so the watchdog never reads a torn
        value. A failure to write is logged, never fatal — the port
        check still applies without the file.
        """
        if not self.state_file:
            return
        try:
            parent = os.path.dirname(self.state_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            tmp = f"{self.state_file}.tmp-{os.getpid()}"
            with open(tmp, "w", encoding="ascii") as fh:
                fh.write(str(int(time.time())))
            os.replace(tmp, self.state_file)
        except OSError as exc:
            log.warning("could not write last-event file %s: %s",
                        self.state_file, exc)

    def handle_published(self, raw: dict, sender: "_Connection") -> None:
        """Translate one published message, update state, fan it out."""
        try:
            envelopes = translate_event(raw)
        except ValueError as exc:
            log.warning("dropping unusable message from %s: %s",
                        sender.peer, exc)
            return
        if not envelopes:
            return  # control message handled by the connection itself
        for env in envelopes:
            env["seq"] = self.next_seq()
            self.round_state.apply(env)
        self.broadcast(envelopes, exclude=sender)
        self.touch_last_event()
        log.debug("published %s (seq %s) to %d subscriber(s)",
                  envelopes[0]["event"], envelopes[0]["seq"],
                  self.subscriber_count())


class _Connection(socketserver.BaseRequestHandler):
    """One WebSocket connection: handshake, then a frame loop."""

    server: BusServer

    def setup(self) -> None:
        self.request.settimeout(HANDSHAKE_TIMEOUT)
        self._buf = bytearray()
        self._closed = False
        self.peer = self.client_address
        self._last_ping = time.monotonic()

    def handle(self) -> None:
        try:
            if not self._handshake():
                return
        except (OSError, ValueError) as exc:
            log.debug("handshake failed from %s: %s", self.peer, exc)
            return
        self.server.register(self)
        log.info("subscriber connected from %s (%d total)", self.peer,
                 self.server.subscriber_count())
        try:
            self.send_json(self.server.snapshot_envelope())
            self.request.settimeout(SOCKET_TIMEOUT)
            self._frame_loop()
        except OSError as exc:
            log.debug("connection to %s dropped: %s", self.peer, exc)
        finally:
            self.server.unregister(self)
            log.info("subscriber disconnected from %s (%d total)",
                     self.peer, self.server.subscriber_count())
            try:
                self.request.close()
            except OSError:
                pass

    # -- handshake ------------------------------------------------------
    def _handshake(self) -> bool:
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = self.request.recv(4096)
            if not chunk:
                return False
            request += chunk
            if len(request) > 65536:
                raise ValueError("handshake headers too large")
        head, _, _ = request.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, _path, _version = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
        key = headers.get("sec-websocket-key")
        if (method != "GET" or not key
                or "websocket" not in headers.get("upgrade", "").lower()
                or "upgrade" not in headers.get("connection", "").lower()
                or headers.get("sec-websocket-version") != "13"):
            self.request.sendall(
                b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n"
                b"Connection: close\r\n\r\n")
            return False
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {_ws_accept(key)}\r\n\r\n"
        )
        self.request.sendall(response.encode("ascii"))
        return True

    # -- framing --------------------------------------------------------
    def _read_exact(self, count: int) -> bytes:
        while len(self._buf) < count:
            chunk = self.request.recv(65536)
            if not chunk:
                raise ConnectionError("client closed the connection")
            self._buf.extend(chunk)
        out = bytes(self._buf[:count])
        del self._buf[:count]
        return out

    def send_frame(self, payload: bytes, opcode: int = 0x1) -> None:
        self.request.sendall(_encode_frame(payload, opcode))

    def send_json(self, obj: dict) -> None:
        self.send_frame(json.dumps(obj).encode("utf-8"))

    def _read_message(self) -> tuple[int, bytes, bool]:
        """Read one frame; returns (opcode, payload, fin)."""
        header = self._read_exact(2)
        fin = bool(header[0] & 0x80)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else None
        payload = self._read_exact(length)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload, fin

    def _frame_loop(self) -> None:
        fragments: list[bytes] = []
        while not self._closed:
            try:
                opcode, payload, fin = self._read_message()
            except socket.timeout:
                if time.monotonic() - self._last_ping >= PING_INTERVAL:
                    self.send_frame(b"", opcode=0x9)
                    self._last_ping = time.monotonic()
                continue
            self._last_ping = time.monotonic()
            if opcode == 0x9:  # ping -> pong
                self.send_frame(payload, opcode=0xA)
            elif opcode == 0xA:  # pong
                continue
            elif opcode == 0x8:  # close -> echo, then drop
                try:
                    self.send_frame(payload, opcode=0x8)
                except OSError:
                    pass
                self._closed = True
            elif opcode in (0x1, 0x0):  # text / continuation
                if opcode == 0x1 and fragments:
                    # A new text frame while fragments are pending: the
                    # previous message was never finished; drop it.
                    fragments = []
                fragments.append(payload)
                if fin:
                    text = b"".join(fragments).decode("utf-8", "replace")
                    fragments = []
                    self._handle_text(text)
            # Binary frames (0x2) and anything else are ignored.

    def _handle_text(self, text: str) -> None:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            log.warning("dropping unparsable message from %s", self.peer)
            return
        if not isinstance(raw, dict):
            log.warning("dropping non-object message from %s", self.peer)
            return
        msg_type = raw.get("type") or raw.get("event")
        if msg_type == "request_round_state":
            self.send_json(self.server.snapshot_envelope())
            return
        if msg_type == "subscribe":
            return  # every connection receives everything already
        if msg_type == "ping":
            self.send_json({"type": "pong"})
            return
        self.server.handle_published(raw, sender=self)


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  state_file: str | None = None) -> BusServer:
    """Build (but do not start) the bus server.

    ``port=0`` binds an ephemeral port (used by the tests);
    ``state_file=None`` resolves via :func:`default_state_file`.
    Pass ``state_file="none"`` to disable the last-event file.
    """
    if state_file is None:
        state_file = default_state_file()
    elif isinstance(state_file, str) and state_file.strip().lower() == "none":
        state_file = None
    return BusServer((host, port), _Connection, state_file=state_file)


def serve_forever(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  state_file: str | None = None) -> None:
    server = create_server(host, port, state_file)
    log.info("Mas Golfs event bus listening on %s:%d (state file: %s)",
             host, server.server_address[1], server.state_file or "disabled")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log.info("event bus shutting down")
    finally:
        server.shutdown()
        server.server_close()
