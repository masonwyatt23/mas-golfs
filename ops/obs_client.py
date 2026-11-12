#!/usr/bin/env python3
"""Minimal obs-websocket client (stdlib only) for the Mas Golfs watchdog.

Talks to OBS Studio's bundled obs-websocket on localhost:4455.
The broadcast box runs with no obs-websocket authentication (locked-down
local box, see docs/broadcast-stack.md §1), so this client does not
implement the auth handshake — if the server ever demands authentication
it exits 2 and says so instead of failing silently.

Usage:
    obs_client.py GetStreamStatus
    obs_client.py StartStream
    obs_client.py StopStream
    obs_client.py GetVersion
    obs_client.py SetCurrentProgramScene '{"sceneName": "INTERMISSION"}'

Exit codes: 0 = request succeeded, 1 = connection/protocol failure,
2 = server requires authentication (not supported by this client).
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import sys
import uuid

HOST = os.environ.get("MAS_GOLFS_OBS_HOST", "127.0.0.1")
PORT = int(os.environ.get("MAS_GOLFS_OBS_PORT", "4455"))
TIMEOUT = float(os.environ.get("MAS_GOLFS_OBS_TIMEOUT", "5"))


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("obs-websocket closed the connection")
        data += chunk
    return data


def _recv_frame(sock: socket.socket) -> str:
    """Read one WebSocket frame and return its text payload."""
    header = _recv_exact(sock, 2)
    fin = header[0] & 0x80
    opcode = header[0] & 0x0F
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    # Server-to-client frames are never masked.
    payload = _recv_exact(sock, length) if length else b""
    if opcode == 9:  # ping -> pong, then read the real frame
        _send_frame(sock, b"", opcode=10)
        return _recv_frame(sock)
    if opcode == 8:  # close
        raise ConnectionError("obs-websocket closed the connection")
    if not fin:
        raise ValueError("fragmented frames are not supported")
    return payload.decode("utf-8")


def _send_frame(sock: socket.socket, payload: bytes, opcode: int = 1) -> None:
    """Send one masked client frame (masking is mandatory for clients)."""
    mask = os.urandom(4)
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", length)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + mask + masked)


def _connect() -> socket.socket:
    sock = socket.create_connection((HOST, PORT), timeout=TIMEOUT)
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {HOST}:{PORT}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "Sec-WebSocket-Protocol: obswebsocket.json\r\n"
        "\r\n"
    ).encode()
    sock.sendall(handshake)
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("obs-websocket closed during handshake")
        response += chunk
    if b"101" not in response.split(b"\r\n", 1)[0]:
        raise ConnectionError(f"obs-websocket handshake failed: {response!r}")
    return sock


def request(request_type: str, request_data: dict | None = None) -> dict:
    """Send one obs-websocket request and return its response data."""
    sock = _connect()
    try:
        hello = json.loads(_recv_frame(sock))
        if hello.get("op") != 0:
            raise ValueError(f"unexpected first message: {hello}")
        auth = hello.get("d", {}).get("authentication")
        if auth:
            raise PermissionError(
                "obs-websocket requires authentication; "
                "this client does not support it"
            )
        request_id = str(uuid.uuid4())
        _send_frame(
            sock,
            json.dumps(
                {
                    "op": 6,
                    "d": {
                        "requestType": request_type,
                        "requestId": request_id,
                        "requestData": request_data or {},
                    },
                }
            ).encode(),
        )
        while True:
            msg = json.loads(_recv_frame(sock))
            if msg.get("op") == 7 and msg.get("d", {}).get("requestId") == request_id:
                result = msg["d"]
                if result.get("requestStatus", {}).get("result") is not True:
                    raise RuntimeError(
                        f"{request_type} failed: "
                        f"{result.get('requestStatus', {})}"
                    )
                return result.get("responseData", {})
            # Ignore events (op 5) and anything else while waiting.
    finally:
        sock.close()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    request_type = argv[1]
    request_data = json.loads(argv[2]) if len(argv) > 2 else None
    try:
        result = request(request_type, request_data)
    except PermissionError as exc:
        print(f"obs_client: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - report and exit nonzero
        print(f"obs_client: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
