"""Typed JSON event emitter (spec §1).

The event stream is the only interface between the engine and everything
else (renderer, director, overlays, commentary, record book). Events are
emitted synchronously, in order, with a monotonic ``seq`` per round.

Determinism (§8.4, §10): a replayed round must produce byte-identical
events, so timestamps are derived from the round number and ``seq`` — not
from the wall clock. Round 1 starts at 2026-11-12 00:00:00 UTC; each round
advances one day; each event advances one second.

Live publishing: when a bus URL is configured — explicit ``bus_url``
argument, or the ``MAS_GOLFS_BUS_URL`` environment variable (empty means
the default ``ws://localhost:4456``) — every emitted event is also
published to the sim event bus (``bus/client.py`` ``BusPublisher``) as it
happens. Publishing is best-effort and can never change the round: the
event is always collected in memory first, a dead bus is logged and the
event counted as dropped, reconnects are gated by exponential backoff,
and any publishing error is swallowed. With no bus configured the
emitter behaves exactly as before, so calibration runs pay nothing.
"""

from __future__ import annotations

import datetime
import logging
import os
import time

log = logging.getLogger("sim.events")

#: Default bus URL when live publishing is enabled without a URL.
DEFAULT_BUS_URL = "ws://localhost:4456"
#: Environment variable that enables live publishing (empty = default URL).
BUS_URL_ENV = "MAS_GOLFS_BUS_URL"

#: A dead bus must never stall a round: one short connect attempt, then
#: the emitter stops trying until the backoff window has passed.
_CONNECT_TIMEOUT_S = 1.0
_BACKOFF_START_S = 0.5
_BACKOFF_MAX_S = 10.0

_EPOCH = datetime.datetime(2026, 11, 12, tzinfo=datetime.timezone.utc)


def resolve_bus_url(explicit: str | None = None) -> str | None:
    """Resolve the live-publish URL, or ``None`` when live publishing is off.

    An explicit argument wins; otherwise ``MAS_GOLFS_BUS_URL`` is read
    (unset = off, empty string = the default URL). Off is the default so
    a bare ``EventEmitter(round_no)`` — e.g. inside the calibration
    harness — never touches the network.
    """
    if explicit is not None:
        return explicit or DEFAULT_BUS_URL
    env = os.environ.get(BUS_URL_ENV)
    if env is None:
        return None
    return env or DEFAULT_BUS_URL


class EventEmitter:
    def __init__(self, round_no: int, bus_url: str | None = None):
        self.round_no = round_no
        self.round_id = f"R{round_no:04d}"
        self.seq = 0
        self.events: list[dict] = []
        self._base = _EPOCH + datetime.timedelta(days=round_no - 1)
        # Live publishing (off unless configured — see module docstring).
        self.bus_url = resolve_bus_url(bus_url)
        self._publisher = None
        self._publish_failures = 0
        self._next_retry_at = 0.0
        self._backoff_s = _BACKOFF_START_S
        #: Events emitted while the bus was unreachable (still in memory).
        self.live_dropped = 0

    @property
    def live_enabled(self) -> bool:
        """True when a bus URL is configured (whether or not it is up)."""
        return self.bus_url is not None

    @property
    def live_connected(self) -> bool:
        """True when the publisher currently holds a live socket."""
        return self._publisher is not None and self._publisher.sock is not None

    def _note_failure(self, now: float, exc: BaseException) -> None:
        self._publish_failures += 1
        if self._publish_failures == 1:
            log.warning("live publish to %s failed (%s); events stay in "
                        "memory, retrying with backoff",
                        self.bus_url, exc)
        else:
            log.debug("live publish to %s failed (%s); retry in %.1fs",
                      self.bus_url, exc, self._backoff_s)
        self._next_retry_at = now + self._backoff_s
        self._backoff_s = min(self._backoff_s * 2, _BACKOFF_MAX_S)

    def _close_publisher(self) -> None:
        if self._publisher is not None:
            try:
                self._publisher.close()
            except Exception:
                pass
            self._publisher = None

    def close(self) -> None:
        """Close the live-publish connection, if any (idempotent)."""
        self._close_publisher()

    def __del__(self):  # best effort: never raise from a finalizer
        try:
            self._close_publisher()
        except Exception:
            pass

    def _publish_live(self, event: dict) -> None:
        """Best-effort live publish; never raises, never blocks long."""
        if self.bus_url is None:
            return
        now = time.monotonic()
        if self._publisher is None:
            if now < self._next_retry_at:
                self.live_dropped += 1
                return
            try:
                from bus.client import BusPublisher
            except ImportError:
                log.warning("live publish disabled: bus.client is not "
                            "importable; events stay in memory")
                self.bus_url = None
                self.live_dropped += 1
                return
            try:
                publisher = BusPublisher(self.bus_url,
                                         connect_timeout=_CONNECT_TIMEOUT_S)
                publisher.connect()
            except Exception as exc:  # dead bus, refused, timeout, ...
                self._note_failure(now, exc)
                self.live_dropped += 1
                return
            self._publisher = publisher
            self._backoff_s = _BACKOFF_START_S
        try:
            self._publisher.publish(event)
        except Exception as exc:
            self._close_publisher()
            self._note_failure(now, exc)
            self.live_dropped += 1

    def emit(self, type_: str, hole: int = 0, shot_no: int = 0,
             **fields) -> dict:
        self.seq += 1
        ts = self._base + datetime.timedelta(seconds=self.seq)
        event_id = (f"evt_{ts.strftime('%Y%m%d')}_{self.round_no:04d}_"
                    f"{self.seq:04d}")
        event = {
            "type": type_,
            "v": 1,
            "event_id": event_id,
            "ts": int(ts.timestamp() * 1000),
            "round_id": self.round_id,
            "round_no": self.round_no,
            "hole": hole,
            "shot_no": shot_no,
            "seq": self.seq,
        }
        event.update(fields)
        self.events.append(event)
        # Live publish is best-effort: a bug or a dead bus here must never
        # change the round, so even an unexpected error is swallowed.
        try:
            self._publish_live(event)
        except Exception:
            log.exception("live publish raised unexpectedly; continuing")
        return event
