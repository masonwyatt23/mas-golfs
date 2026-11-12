"""Runnable demo: generate the sample round, run the pipeline, print the queue.

    python demo.py

Writes:
    sample_data/round_R0042_events.jsonl   the deterministic sample event log
    output/manifest_R0042.json             the full clip manifest
    output/queue_R0042.json                the daily queue only (what Mason approves)
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    from clip_pipeline.events import load_events
    from clip_pipeline.manifest import run_pipeline, write_manifest
    from clip_pipeline.sample_log import build_round, write_sample_log

    log_path = write_sample_log(HERE / "sample_data" / "round_R0042_events.jsonl")
    events = load_events(log_path)
    moments, clips, queue, manifest = run_pipeline(events)

    manifest_path = write_manifest(manifest, HERE / "output" / "manifest_R0042.json")
    queue_path = write_manifest(
        {"round": manifest["round"], "queue": manifest["queue"]},
        HERE / "output" / "queue_R0042.json",
    )

    print(f"Sample log:  {log_path} ({len(events)} events)")
    print(f"Manifest:    {manifest_path}")
    print(f"Queue:       {queue_path}")
    print()
    print(f"Round R0042 — Mas shoots 59 at Wyatt National (-13)")
    print(f"Moments detected: {len(moments)} | clips saved: {len(clips)} | queue: {len(queue)}")
    print()
    print("All detected moments (drama order):")
    for m in moments:
        saved = "saved" if m.save_replay else "dropped"
        print(f"  [{m.drama:3d}] H{m.hole:02d} {m.moment_type:<14} {'; '.join(m.reasons)}  ({saved})")
    print()
    print("Today's queue (what Mason approves tonight):")
    for rank, clip in enumerate(queue, start=1):
        print(f"  {rank}. [{clip.drama}] {clip.title}")
        print(f"     hook: \"{clip.hook_line}\"  | {clip.duration_s}s | {clip.clip_format} | "
              f"src {clip.source_file} [{clip.source_in_s:.0f}s-{clip.source_out_s:.0f}s]"
              f"{' | 0.5x slow-mo' if clip.slow_motion else ''}")
        print(f"     caption: {clip.caption}")
    print()
    print("Library (saved, not queued — best-of / weekly roundup material):")
    queued_ids = {c.clip_id for c in queue}
    for clip in clips:
        if clip.clip_id not in queued_ids:
            print(f"  [{clip.drama}] H{clip.hole:02d} {clip.moment_type:<14} {clip.title}")


if __name__ == "__main__":
    main()
