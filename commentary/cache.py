"""Cached standard lines and the audio cache (commentary-prompts.md §6).

Two things live here:

1. **Pre-seeded standard lines** — templated, never LLM-generated, for
   the events that repeat: hole intros, standard score updates, routine
   result calls, round openers/closers, and the 59 Watch off-pace notice.
   They are rendered from the event + ``round_state`` and their audio is
   synthesized once and stored under a hash of ``(voice + text)``.
2. **The audio cache** — disk-backed, keyed by that hash. A 24-hour
   round is a few hundred short lines, tens of megabytes on disk.

What is NEVER cached (commentary-prompts.md §6.2): decision lines,
59 Watch moments, milestones, the learning fix, recoveries, and apex
reads. A stale pace line is a wrong line.
"""

from __future__ import annotations

import hashlib
import os

# Event types whose lines are generated fresh every time, never cached.
NEVER_CACHE = {
    "decision",
    "fifty_nine_watch",
    "milestone",
    "recovery",
    "apex",
    "round_end",  # the learning fix is unique per round
}


def cache_key(voice: str, normalized_text: str) -> str:
    """Hash of (voice + normalized text) — the cache key (§6.3)."""
    return hashlib.sha256(f"{voice}\n{normalized_text}".encode("utf-8")).hexdigest()


def _score_words(score_to_par: int) -> str:
    if score_to_par == 0:
        return "even par"
    magnitude = abs(score_to_par)
    word = "one" if magnitude == 1 else str(magnitude)
    return f"{word} under par" if score_to_par < 0 else f"{word} over par"


def standard_line(event_type: str, fields: dict, round_state: dict | None) -> str | None:
    """Render a pre-seeded standard line, or None when there is none.

    ``fields`` is the normalized event dict (flat, with ``type`` removed);
    ``round_state`` is the latest snapshot. Every number in the returned
    line comes from one of the two — nothing is invented.
    """
    state = round_state or {}
    thru = state.get("thru", fields.get("thru"))
    score = state.get("score_to_par", fields.get("score_to_par"))

    if event_type == "hole_start":
        hole = fields.get("hole", state.get("hole"))
        name = fields.get("hole_name") or (state.get("current_hole") or {}).get("name")
        par = fields.get("par", state.get("hole_par"))
        yards = fields.get("yards") or (state.get("current_hole") or {}).get("yards")
        if hole is None or par is None or yards is None:
            return None
        line = f"Hole {hole}"
        if name:
            line += f", {name}"
        return f"{line}. Par {par}, {yards} yards."

    if event_type == "round_start":
        course = fields.get("course", "Wyatt National")
        target = fields.get("target_score", state.get("target_score", 59))
        round_no = fields.get("round_no", state.get("round"))
        if round_no is None:
            return f"Round at {course}. Mas is chasing {target}."
        return f"Round {round_no} at {course}. Mas is chasing {target}."

    if event_type == "hole_end":
        if thru is None or score is None:
            return None
        return f"Mas is {_score_words(int(score))} through {thru}."

    if event_type == "landing":
        result = fields.get("result")
        dist = fields.get("dist_to_pin_ft")
        total = fields.get("total_yds")
        if result == "fairway_hit" and total is not None:
            return f"That's in the fairway, {total} yards."
        if result == "green_hit" and dist is not None:
            return f"That's on the green, {dist} feet."
        return None

    if event_type == "putt_result":
        if fields.get("made"):
            if thru is not None and score is not None:
                return f"The putt drops. Mas is {_score_words(int(score))} through {thru}."
            return "The putt drops."
        dist = fields.get("dist_ft")
        if dist is not None:
            return f"Missed. {dist} feet left."
        return None

    if event_type == "fifty_nine_watch":
        if fields.get("status") == "off_pace":
            return "The 59 is off the table for this round."
        return None

    if event_type == "round_end":
        score_value = fields.get("score")
        if score_value is None or score is None:
            return None
        return f"Mas finishes with a {score_value}, {_score_words(int(score))}."

    return None


class AudioCache:
    """Disk-backed cache of synthesized audio, keyed by voice + text.

    Files are stored as ``<sha256>.wav`` (or whatever extension the TTS
    backend returns) under ``cache_dir``. The cache survives restarts.
    Invalidation is by key: a line whose numbers changed is a different
    text, hence a different key — a stale score can never replay.
    """

    def __init__(self, cache_dir: str, extension: str = "wav"):
        self.cache_dir = os.path.expanduser(cache_dir)
        self.extension = extension
        os.makedirs(self.cache_dir, exist_ok=True)

    def path_for(self, voice: str, normalized_text: str) -> str:
        key = cache_key(voice, normalized_text)
        return os.path.join(self.cache_dir, f"{key}.{self.extension}")

    def get(self, voice: str, normalized_text: str) -> str | None:
        path = self.path_for(voice, normalized_text)
        return path if os.path.exists(path) else None

    def put(self, voice: str, normalized_text: str, audio_bytes: bytes) -> str:
        path = self.path_for(voice, normalized_text)
        with open(path, "wb") as fh:
            fh.write(audio_bytes)
        return path

    def size_bytes(self) -> int:
        total = 0
        for name in os.listdir(self.cache_dir):
            try:
                total += os.path.getsize(os.path.join(self.cache_dir, name))
            except OSError:
                continue
        return total
