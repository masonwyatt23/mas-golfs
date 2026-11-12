"""Daily queue selection and clip manifest output.

Selection rules (launch-playbook §1.1 Stage 4 and §1.3):
- The queue is ranked by drama score.
- Pick the best clip, and a second only if it scored 90+ ("two on days
  with a drama-90+ moment").
- Maximum one clip per hole, unless the clip scored >= 90 — a hole-out
  earns a second look (broadcast-stack §3.5 replay rule).

The manifest is the single handoff artifact: the daily queue Mason
approves in the evening workflow, plus the full library of saved clips
for best-of compilations and the weekly roundup.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .assembly import ClipCard, assemble_clip
from .scoring import SECOND_LOOK_THRESHOLD, Moment

MAX_QUEUE_CLIPS = 2


def select_daily_queue(clips: list[ClipCard], max_clips: int = MAX_QUEUE_CLIPS) -> list[ClipCard]:
    """Rank clips by drama and pick the daily queue.

    ``clips`` must already be the saved set (drama >= 60). The first pick
    is always the top clip. A second pick is allowed only when it scored
    90+ and comes from a different hole than the first pick, unless it
    scored 90+ itself (second-look rule).
    """
    ranked = sorted(clips, key=lambda c: (-c.drama, c.hole))
    queue: list[ClipCard] = []
    used_holes: set[int] = set()
    for clip in ranked:
        if len(queue) >= max_clips:
            break
        if queue and clip.drama < SECOND_LOOK_THRESHOLD:
            # Second clip of the day needs a 90+ moment.
            break
        if clip.hole in used_holes and clip.drama < SECOND_LOOK_THRESHOLD:
            continue
        queue.append(clip)
        used_holes.add(clip.hole)
    return queue


def build_manifest(
    round_no: int,
    moments: list[Moment],
    clips: list[ClipCard],
    queue: list[ClipCard],
    round_summary: dict | None = None,
) -> dict:
    """Build the clip manifest dict for one round."""
    queue_ids = {c.clip_id for c in queue}
    library = [c.to_dict() for c in sorted(clips, key=lambda c: (-c.drama, c.hole))]
    dropped = [
        m.to_dict()
        for m in moments
        if not m.save_replay
    ]
    return {
        "schema_version": 1,
        "generator": "mas-golfs clip-pipeline 0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "round": {
            "round_no": round_no,
            "round_id": f"R{round_no:04d}",
            **(round_summary or {}),
        },
        "summary": {
            "moments_detected": len(moments),
            "clips_saved": len(clips),
            "queue_size": len(queue),
            "top_drama": max((c.drama for c in clips), default=0),
            "moments_below_threshold": len(dropped),
        },
        "queue": [c.to_dict() for c in queue],
        "library": library,
        "not_saved": dropped,
        "_queue_ids": sorted(queue_ids),
    }


def run_pipeline(events: list[dict]) -> tuple[list[Moment], list[ClipCard], list[ClipCard], dict]:
    """Score a round's events, assemble clips, select the queue, build the manifest.

    Returns (moments, clips, queue, manifest). ``round_summary`` is pulled
    from the round_complete event when present.
    """
    from .scoring import REPLAY_SAVE_THRESHOLD, score_round

    moments = score_round(events)
    saved = [m for m in moments if m.drama >= REPLAY_SAVE_THRESHOLD]
    clips = [assemble_clip(m) for m in saved]
    queue = select_daily_queue(clips)

    round_summary: dict = {}
    for ev in events:
        if ev["type"] == "round_complete":
            round_summary = {
                "course": "Wyatt National",
                "score": ev.get("score"),
                "score_to_par": ev.get("score_to_par"),
                "stats": ev.get("stats", {}),
                "road_to_59": ev.get("road_to_59", {}),
            }
    round_no = events[0]["round_no"] if events else 0
    manifest = build_manifest(round_no, moments, clips, queue, round_summary)
    return moments, clips, queue, manifest


def write_manifest(manifest: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path
