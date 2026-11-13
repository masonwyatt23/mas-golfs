"""Shared fixtures for the Mas Golfs end-to-end integration harness.

Two event sources:

* ``three_hole_events()`` — the deterministic 3-hole demo round used by
  every chain test: ``round_start`` plus holes 1-3 of the sample round
  R0042 (clip-pipeline's deterministic log: H1 birdie, H2 eagle, H3
  near-miss lip-out). Same bytes every run, no sim needed, so the
  bus / commentary / NodeCG / clip links are testable even while the sim
  is broken.
* ``try_sim_round(seed)`` — plays one real fast-mode sim round and returns
  its events. Used only by the sim-link test; it raises whatever the sim
  raises (at the time of writing, ``KeyError: 'semi'`` on seeds whose
  shots land in the v3 semi-rough), and the test reports that as
  blocked-on-sim-fix instead of failing the chain.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

for _p in (str(REPO_ROOT), str(REPO_ROOT / "clip-pipeline")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SIM_SEEDS = (1, 2, 3)
DEMO_HOLES = (1, 2, 3)


def three_hole_events() -> list[dict]:
    """Deterministic 3-hole demo round (round_start + holes 1-3 of R0042)."""
    from clip_pipeline.sample_log import build_round

    events = build_round()
    return [
        ev
        for ev in events
        if ev["type"] == "round_start" or ev["hole"] in DEMO_HOLES
    ]


def three_hole_moment_types() -> set[str]:
    """Moment types the clip scorer must find in the 3-hole fixture."""
    # H1 birdie (first of the round), H2 eagle, H3 near-miss lip-out.
    return {"birdie", "eagle", "near_miss"}


def try_sim_round(seed: int) -> tuple[int, list[dict]]:
    """Play one fast-mode sim round. Returns (score, events).

    Raises whatever the sim raises. Callers must NOT swallow the error:
    report it verbatim as the sim-link verdict.
    """
    from sim.engine import RoundEngine

    engine = RoundEngine(fast_mode=True, seed_offset=seed)
    result = engine.play_round()
    return result.score, list(result.events)


def sim_three_hole_events(seed: int) -> list[dict]:
    """First three holes of a real fast-mode sim round, plus round_start."""
    _score, events = try_sim_round(seed)
    return [
        ev
        for ev in events
        if ev["type"] == "round_start" or ev["hole"] in DEMO_HOLES
    ]
