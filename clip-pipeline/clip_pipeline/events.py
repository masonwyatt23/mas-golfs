"""Event-log loading and validation.

Consumes the JSON event stream defined in docs/sim-engine.md §1: one JSON
object per line (JSONL), or a JSON array in a single file. Every event
carries the §1.1 envelope (type, v, event_id, ts, round_id, round_no,
hole, shot_no, seq).
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_ENVELOPE = {"type", "v", "event_id", "ts", "round_id", "round_no", "hole", "shot_no", "seq"}

EVENT_TYPES = {
    "round_start",
    "hole_start",
    "shot_decision",
    "shot_result",
    "putt_result",
    "hole_complete",
    "round_complete",
    "milestone",
}

# Event types that carry a shot decision / result the scorer reads.
SHOT_EVENTS = {"shot_decision", "shot_result", "putt_result"}


class EventLogError(ValueError):
    """Raised when an event log is malformed or violates the schema."""


def validate_event(ev: dict, where: str = "") -> None:
    """Validate one event against the §1.1 envelope. Raises EventLogError."""
    if not isinstance(ev, dict):
        raise EventLogError(f"{where}: event is not a JSON object")
    missing = REQUIRED_ENVELOPE - ev.keys()
    if missing:
        raise EventLogError(f"{where}: missing envelope fields {sorted(missing)}")
    if ev["type"] not in EVENT_TYPES:
        raise EventLogError(f"{where}: unknown event type {ev['type']!r}")
    if ev["v"] != 1:
        raise EventLogError(f"{where}: unsupported schema version {ev['v']!r}")
    if not 0 <= ev["hole"] <= 18:
        raise EventLogError(f"{where}: hole out of range: {ev['hole']}")
    if ev["shot_no"] < 0:
        raise EventLogError(f"{where}: shot_no out of range: {ev['shot_no']}")


def load_events(path: str | Path) -> list[dict]:
    """Load an event log from a JSONL file (or a JSON array file).

    Returns events in file order. Raises EventLogError on any bad line.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    events: list[dict] = []
    if text.startswith("["):
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise EventLogError(f"{path}: top-level JSON is not an array")
        for i, ev in enumerate(raw):
            validate_event(ev, f"{path}:{i}")
            events.append(ev)
        return events
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EventLogError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        validate_event(ev, f"{path}:{line_no}")
        events.append(ev)
    return events


def group_by_round(events: list[dict]) -> dict[int, list[dict]]:
    """Group events by round_no, preserving order within each round."""
    rounds: dict[int, list[dict]] = {}
    for ev in events:
        rounds.setdefault(ev["round_no"], []).append(ev)
    return rounds


def round_events(events: list[dict], round_no: int) -> list[dict]:
    """All events for one round, in order."""
    return [ev for ev in events if ev["round_no"] == round_no]


def check_sequence(events: list[dict]) -> list[str]:
    """Check per-round `seq` ordering; return a list of warnings (empty = clean)."""
    warnings: list[str] = []
    seen: dict[int, int] = {}
    for ev in events:
        prev = seen.get(ev["round_no"], 0)
        if ev["seq"] <= prev:
            warnings.append(
                f"round {ev['round_no']}: seq {ev['seq']} out of order "
                f"after {prev} (event {ev['event_id']})"
            )
        seen[ev["round_no"]] = ev["seq"]
    return warnings
