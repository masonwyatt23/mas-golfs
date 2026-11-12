"""Typed JSON event emitter (spec §1).

The event stream is the only interface between the engine and everything
else (renderer, director, overlays, commentary, record book). Events are
emitted synchronously, in order, with a monotonic ``seq`` per round.

Determinism (§8.4, §10): a replayed round must produce byte-identical
events, so timestamps are derived from the round number and ``seq`` — not
from the wall clock. Round 1 starts at 2026-11-12 00:00:00 UTC; each round
advances one day; each event advances one second.
"""

from __future__ import annotations

import datetime

_EPOCH = datetime.datetime(2026, 11, 12, tzinfo=datetime.timezone.utc)


class EventEmitter:
    def __init__(self, round_no: int):
        self.round_no = round_no
        self.round_id = f"R{round_no:04d}"
        self.seq = 0
        self.events: list[dict] = []
        self._base = _EPOCH + datetime.timedelta(days=round_no - 1)

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
        return event
