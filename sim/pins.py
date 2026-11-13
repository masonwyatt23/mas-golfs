"""Pin rotation for Mas Golfs — pins move like a real course.

THE SCHEME
----------
Pins move to a new position **every 2 rounds** and never mid-round.
Rounds 1-2 play rotation 0, rounds 3-4 rotation 1, and so on::

    rotation_index = (round_no - 1) // 2

A rotation is one of six setup profiles that repeat every 12 rounds:

    0  Accessible    — the friendly spots (centres and mid-depth), easy reads
    1  Standard      — the full nine zones, no character either way
    2  Sunday        — edge pins only, no centres; tucked, hardest reads
    3  Front         — front-row pins, attackable but short-sided
    4  Back          — back-row pins, longer approaches, false-front edges
    5  Championship  — the full nine zones, difficulty turned up

The zone for a hole is deterministic from ``(course_id, hole_no,
rotation_index)``: SHA-256 of ``"course:hole:rotation"`` picks a zone
from the profile's pool. ``hashlib`` (not ``hash()``) is used on purpose
— Python's ``hash()`` is salted per process, so a ``hash()``-based pin
would move between runs and break replays. The SHA-256 pick is stable
across processes, rebuilds, and machines, so a seeded round replays
byte-identically.

The pin is GUARANTEED to move between adjacent rotations on every
hole: the pick is walked from rotation 0 up to the requested rotation,
and whenever a rotation would repeat the previous rotation's zone on
that hole, the pick steps one place along the pool. A pin therefore
changes every 2 rounds and never stays put across a rotation boundary.

WHAT THE ROTATION FEEDS
-----------------------
* **Approach strategy** — the pin position (``pin_x``, ``pin_y``) is the
  only pin input the decision engine reads, and it comes from the
  existing ``RoundEngine._pin_position`` fed with the rotated zone.
  A back pin changes the club and the aim; nothing in the decision
  code knows or cares that the zone came from a rotation.
* **The Green solver's coordinate mapping** — ``sim/greens.py``
  ``to_green_local`` / ``from_green_local`` mirror ``_pin_position``
  exactly (a pin placed from ``PIN_OFFSETS`` lands at green-local
  ``(-y_ft, x_ft)``). The rotation changes only WHICH zone is picked,
  never the mapping, so the solver, the ball, and the broadcast keep
  reading the same array. Do not "improve" the mapping here.
* **The putt_read make %** — ``build_putt_read`` takes the rotation's
  effective pin difficulty and reads a tucked pin harder (see
  ``PIN_READ_WEIGHT`` in ``sim/putting.py``). That is a read/display
  effect only: the outcome draw still uses the calibrated make table,
  so the read is the caddie's judgment, not a second table.

DIFFICULTY
----------
Each zone carries an intrinsic difficulty (depth, tier, nearby
hazards — the old ``PIN_DIFFICULTY`` table, now owned here). The
rotation profile multiplies it (Accessible 0.85, Standard 1.0,
Sunday 1.25, Front 1.0, Back 1.05, Championship 1.15), clamped to
[0.30, 0.95]. The effective difficulty is what ``hole_start`` reports
and what the putt read uses.

VALIDITY
--------
Every zone in every pool sits inside the green by construction: the
furthest offset is 25 ft from the green centre (15 ft lateral, 20 ft
front/back) and the smallest green radius in play is 36 ft
(tournament setup). ``tests/test_pins.py`` asserts it geometrically
anyway — every pin, every hole, every rotation: inside the green
radius and outside every bunker ellipse.

HISTORY
-------
Before rotation, pins were drawn per hole from the round PRNG
(``_draw_pin``), which consumed PRNG state and made the pin depend on
everything drawn before it in the round. Rotation removes the pin
from the PRNG stream entirely: same ``(course, hole, rotation)``,
same pin, whatever else happened in the round.
"""

from __future__ import annotations

import hashlib

# Pins move every 2 rounds (rounds 1-2, 3-4, ...).
ROTATION_ROUNDS = 2
# Six setup profiles; the cycle repeats every 12 rounds.
ROTATION_CYCLE = 6

PIN_ZONES = ["front_left", "front_center", "front_right",
             "mid_left", "mid_center", "mid_right",
             "back_left", "back_center", "back_right"]

# Intrinsic zone difficulty, 0-1 (depth, tier, nearby hazards).
# Moved here from engine.py so the rotation owns the whole pin.
ZONE_DIFFICULTY = {
    "front_left": 0.45, "front_center": 0.35, "front_right": 0.55,
    "mid_left": 0.50, "mid_center": 0.40, "mid_right": 0.60,
    "back_left": 0.65, "back_center": 0.55, "back_right": 0.71,
}

# Setup profiles, in cycle order. "zones" is the pool the hash picks
# from; "difficulty_mult" scales the zone difficulty into the
# effective pin difficulty the read and the broadcast use.
_PROFILES = (
    {"name": "Accessible",
     "zones": ["mid_center", "mid_left", "mid_right",
               "front_center", "back_center"],
     "difficulty_mult": 0.85},
    {"name": "Standard",
     "zones": list(PIN_ZONES),
     "difficulty_mult": 1.0},
    {"name": "Sunday",
     "zones": ["front_left", "front_right", "back_left", "back_right",
               "mid_left", "mid_right"],
     "difficulty_mult": 1.25},
    {"name": "Front",
     "zones": ["front_left", "front_center", "front_right"],
     "difficulty_mult": 1.0},
    {"name": "Back",
     "zones": ["back_left", "back_center", "back_right"],
     "difficulty_mult": 1.05},
    {"name": "Championship",
     "zones": list(PIN_ZONES),
     "difficulty_mult": 1.15},
)


def rotation_index_for_round(round_no: int) -> int:
    """Rotation index for a round number (1-based). Rounds 1-2 -> 0."""
    return max(0, (round_no - 1) // ROTATION_ROUNDS)


def rotation_profile_name(rotation_index: int) -> str:
    """Setup profile name for a rotation index (\"Sunday\", ...)."""
    return _PROFILES[rotation_index % ROTATION_CYCLE]["name"]


def _hash_int(course_id: str, hole_no: int, rotation_index: int) -> int:
    """Stable pick integer for (course, hole, rotation).

    SHA-256, not ``hash()``: the pick must be identical in every
    process, or replays diverge.
    """
    key = f"{course_id}:{hole_no}:{rotation_index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def pin_zone_for(course_id: str, hole_no: int, rotation_index: int) -> str:
    """The pin zone for a hole in a rotation.

    Deterministic from (course_id, hole_no, rotation_index). The pick
    is walked from rotation 0 so the anti-repeat rule can compare
    against the previous rotation's zone: whenever a rotation would
    repeat the previous zone on this hole, the pick steps one place
    along the pool, so the pin is guaranteed to move between adjacent
    rotations.
    """
    zone: str | None = None
    for r in range(rotation_index + 1):
        profile = _PROFILES[r % ROTATION_CYCLE]
        pool = profile["zones"]
        idx = _hash_int(course_id, hole_no, r) % len(pool)
        z = pool[idx]
        if zone is not None and z == zone:
            z = pool[(idx + 1) % len(pool)]
        zone = z
    assert zone is not None  # rotation_index >= 0, loop runs at least once
    return zone


def pin_difficulty_for(course_id: str, hole_no: int,
                       rotation_index: int) -> float:
    """Effective pin difficulty (0.30-0.95) for a hole in a rotation.

    Zone difficulty times the profile multiplier, clamped. This is
    the number ``hole_start`` reports and the putt read uses.
    """
    zone = pin_zone_for(course_id, hole_no, rotation_index)
    mult = _PROFILES[rotation_index % ROTATION_CYCLE]["difficulty_mult"]
    return round(min(0.95, max(0.30, ZONE_DIFFICULTY[zone] * mult)), 2)
