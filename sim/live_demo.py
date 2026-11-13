"""Demo: play a round live on the event bus.

Starts a bus server on ``--port`` (unless one is already listening
there), subscribes, plays one round with live publishing on, and
reports what the subscriber received — proving the sim -> bus ->
subscriber path end to end.

Usage:
    python -m sim.live_demo [--port N] [--rounds N] [--fast] [--mc N]

The bus URL is ``MAS_GOLFS_BUS_URL`` (default ``ws://localhost:4456``);
``--port`` overrides the port for both the server and the URL. With
``--fast`` the rule-based decision path is used (seconds per round);
without it a full Monte Carlo round takes noticeably longer.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time

from bus.client import BusPublisher
from bus.server import create_server

from .engine import RoundEngine
from .events import DEFAULT_BUS_URL


def _bus_url(port: int) -> str:
    env = os.environ.get("MAS_GOLFS_BUS_URL")
    if env:
        return env
    if port != 4456:
        return f"ws://127.0.0.1:{port}"
    return DEFAULT_BUS_URL


class _Subscriber(threading.Thread):
    """Reads translated envelopes from the bus until round_end arrives."""

    def __init__(self, url: str):
        super().__init__(daemon=True)
        self.url = url
        self.received: list[dict] = []
        self.types_seen: list[str] = []
        self.round_end_received = False
        self.error: str | None = None

    def run(self) -> None:
        try:
            pub = BusPublisher(self.url, connect_timeout=5.0)
            pub.connect()
            # The server sends a round_state snapshot on connect; skip it.
            try:
                snapshot = json.loads(pub.recv_text(timeout=5.0))
                assert snapshot.get("event") == "round_state", snapshot
            except (TimeoutError, AssertionError, ValueError) as exc:
                self.error = f"no snapshot on connect: {exc!r}"
                return
            while not self.round_end_received:
                try:
                    msg = json.loads(pub.recv_text(timeout=10.0))
                except TimeoutError:
                    break
                self.received.append(msg)
                kind = msg.get("event") or msg.get("type")
                self.types_seen.append(kind)
                if kind == "round_end":
                    self.round_end_received = True
            pub.close()
        except Exception as exc:  # noqa: BLE001 — report, don't crash demo
            self.error = f"{type(exc).__name__}: {exc}"


def run(port: int = 4456, rounds: int = 1, fast: bool = True,
        mc_n: int = 120) -> dict:
    """Play ``rounds`` live on a bus at ``port``; return a summary dict."""
    url = _bus_url(port)
    server = None
    server_thread = None
    try:
        server = create_server("127.0.0.1", port, state_file="none")
        server_thread = threading.Thread(target=server.serve_forever,
                                         kwargs={"poll_interval": 0.5},
                                         daemon=True)
        server_thread.start()
        print(f"bus server listening on 127.0.0.1:{port}")
    except OSError as exc:
        # A bus is probably already running there — use it.
        print(f"could not start a bus server on :{port} ({exc}); "
              "assuming an external bus is running")

    subscriber = _Subscriber(url)
    subscriber.start()
    time.sleep(0.2)  # let the subscriber connect before the round starts

    # The emitter reads this env var when play_round() creates it.
    os.environ["MAS_GOLFS_BUS_URL"] = url
    engine = RoundEngine(fast_mode=fast, mc_n=mc_n)
    emitted = 0
    scores = []
    for _ in range(rounds):
        result = engine.play_round()
        emitted += len(result.events)
        scores.append(result.score)
        print(f"round {result.round_no}: score {result.score} "
              f"({result.score_to_par:+d}), {len(result.events)} events")

    # Events are published synchronously during play, so the subscriber
    # should already have everything; give its thread a moment to drain.
    subscriber.join(timeout=15.0)
    if server is not None:
        server.shutdown()
        server.server_close()

    summary = {
        "bus_url": url,
        "rounds_played": rounds,
        "scores": scores,
        "events_emitted": emitted,
        "events_received": len(subscriber.received),
        "round_end_received": subscriber.round_end_received,
        "types_seen": subscriber.types_seen,
        "subscriber_error": subscriber.error,
    }
    print(f"subscriber received {len(subscriber.received)} events; "
          f"round_end received: {subscriber.round_end_received}")
    if subscriber.error:
        print(f"subscriber error: {subscriber.error}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4456)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--fast", action="store_true",
                        help="rule-based decisions (fast)")
    parser.add_argument("--mc", type=int, default=120,
                        help="Monte Carlo samples per decision")
    args = parser.parse_args()
    summary = run(port=args.port, rounds=args.rounds, fast=args.fast,
                  mc_n=args.mc)
    ok = (summary["round_end_received"]
          and summary["events_received"] >= summary["events_emitted"]
          and not summary["subscriber_error"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
