"""Demo: run the commentary service against a scripted fake event stream.

No model server, no TTS server, no bus needed — the demo uses the
stub LLM and stub TTS, so it runs anywhere. It plays a short script:
round start, hole 12 (The Picture, par 3, 164 yards), a decision,
a swing (director hold), an apex read, a landing, a putt, a hole-out,
and a 59 Watch moment — enough to exercise every decision path.

Usage:
    python -m commentary.service --demo
    python -m commentary.demo
"""

from __future__ import annotations

import json
import os

from .bus import FakeBus
from .config import expand_paths
from .llm import LLMClient, StubLLM
from .service import CommentaryService
from .tts import StubTTS

SCRIPT: list[dict] = [
    {"type": "round_start", "seq": 1, "round_no": 47, "hole": 1,
     "course": "Wyatt National", "par": 72, "target_score": 59,
     "last10_avg": 70.4, "handicap": "+3.1"},
    {"type": "round_state", "seq": 2, "round_no": 47, "hole": 12,
     "score_to_par": -2, "thru": 11, "target_score": 59,
     "handicap": "+3.1", "last10_avg": 70.4,
     "current_hole": {"name": "The Picture", "par": 3, "yards": 164},
     "stats": {"fairways": "6/11", "gir": "7/11", "putts": 19}},
    {"type": "hole_start", "seq": 3, "round_no": 47, "hole": 12,
     "par": 3, "yards": 164, "hole_name": "The Picture",
     "pin": "back left", "wind_mph": 8, "wind_dir": "into",
     "elevation_ft": -12},
    {"type": "decision", "seq": 4, "round_no": 47, "hole": 12,
     "club": "7-iron", "shot_type": "full", "target_yards": 164,
     "aim": "middle of the green", "reason": "pin is back left and the wind is into him",
     "risk": "standard", "lie": "tee", "wind_mph": 8, "wind_dir": "into"},
    {"type": "shot_start", "seq": 5, "round_no": 47, "hole": 12,
     "club": "7-iron", "shot_type": "full"},
    {"type": "apex", "seq": 6, "round_no": 47, "hole": 12,
     "apex_ft": 92, "carry_yds": 158, "shape": "draw", "curve_yds": 8,
     "club": "7-iron"},
    {"type": "landing", "seq": 7, "round_no": 47, "hole": 12,
     "total_yds": 164, "lie": "green", "dist_to_pin_ft": 12,
     "result": "green_hit", "club": "7-iron"},
    {"type": "putt_result", "seq": 8, "round_no": 47, "hole": 12,
     "dist_ft": 12, "made": True, "putts_this_hole": 1},
    {"type": "hole_end", "seq": 9, "round_no": 47, "hole": 12,
     "score": 2, "par": 3, "score_to_par": -3, "fairway_hit": True, "gir": True,
     "putts": 1, "up_and_down": False,
     "strokes_gained": {"approach": 0.42, "putting": 0.51}},
    {"type": "fifty_nine_watch", "seq": 10, "round_no": 47, "hole": 12,
     "status": "on_pace", "score_to_par": -3, "thru": 12,
     "strokes_remaining": 1, "probability": 38, "holes_left": 6},
    {"type": "milestone", "seq": 11, "round_no": 47, "hole": 12,
     "milestone_type": "birdie_streak",
     "detail": "three birdies in a row, holes 10 through 12",
     "score_to_par": -3, "thru": 12},
]


def run_demo(cfg: dict) -> dict:
    """Run the scripted demo against a temp workspace. Returns a summary."""
    import tempfile

    tmp = tempfile.mkdtemp(prefix="mas-golfs-commentary-demo-")
    cfg = dict(cfg)
    cfg["dry_run"] = False
    cfg["stub_llm"] = True
    # The demo relaxes the rate limits so one scripted hole can exercise
    # every decision path. The limits themselves are covered by tests.
    cfg["limits"] = {"min_seconds_between_lines": 0,
                     "max_lines_per_hole": 99, "max_line_chars": 280}
    cfg["paths"] = {
        "decision_log": os.path.join(tmp, "decisions.jsonl"),
        "output_log": os.path.join(tmp, "output.jsonl"),
        "audio_dir": os.path.join(tmp, "audio"),
    }
    cfg["tts"] = dict(cfg["tts"])
    cfg["tts"]["cache_dir"] = os.path.join(tmp, "tts-cache")
    # The demo clock stands still, so the 15-second rate limit would
    # drop everything after the first line. Give the demo a clock that
    # advances 20 seconds per event instead.
    clock = _DemoClock(start=0.0, step=20.0)
    service = CommentaryService(
        cfg, llm=LLMClient(StubLLM()), tts=StubTTS(), clock=clock.tick)
    bus = FakeBus(SCRIPT)
    while True:
        try:
            raw = bus.recv_text()
        except Exception:
            break
        service.handle_event(json.loads(raw))
    played = []
    with open(cfg["paths"]["output_log"], encoding="utf-8") as fh:
        for line in fh:
            played.append(json.loads(line))
    decisions = []
    with open(cfg["paths"]["decision_log"], encoding="utf-8") as fh:
        for line in fh:
            decisions.append(json.loads(line))
    print(f"Demo complete: {len(played)} lines played, "
          f"{len(decisions)} decisions logged, "
          f"silence fraction {service.silence_fraction():.2f}")
    for record in played:
        print(f"  [{record['speaker']:5s}] {record['text']}")
    return {"played": played, "decisions": decisions,
            "silence_fraction": service.silence_fraction(), "tmpdir": tmp}


class _DemoClock:
    """A clock that advances a fixed step on every read (demo only)."""

    def __init__(self, start: float = 0.0, step: float = 20.0):
        self.now = start
        self.step = step

    def tick(self) -> float:
        value = self.now
        self.now += self.step
        return value


if __name__ == "__main__":
    from .config import load_config

    run_demo(load_config())
