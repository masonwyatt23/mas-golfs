"""Command-line interface for the Mas Golfs auto-clip pipeline.

Usage:
    python -m clip_pipeline.cli --input sample_data/round_R0042_events.jsonl
    python -m clip_pipeline.cli --input events.jsonl --output out/manifest.json --top 2
    python -m clip_pipeline.cli --generate-sample sample_data/round_R0042_events.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .events import check_sequence, load_events
from .manifest import run_pipeline, write_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clip-pipeline",
        description="Score a Mas Golfs event log and build the daily clip manifest.",
    )
    parser.add_argument("--input", "-i", default="sample_data/round_R0042_events.jsonl",
                        help="Event log (JSONL, sim-engine §1 schema).")
    parser.add_argument("--output", "-o", default="output/manifest.json",
                        help="Where to write the clip manifest JSON.")
    parser.add_argument("--top", type=int, default=2,
                        help="Max clips in the daily queue (default 2).")
    parser.add_argument("--generate-sample", metavar="PATH",
                        help="Regenerate the deterministic sample event log and exit.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Only print errors.")
    args = parser.parse_args(argv)

    if args.generate_sample:
        from .sample_log import write_sample_log

        write_sample_log(args.generate_sample)
        if not args.quiet:
            print(f"Sample event log written to {args.generate_sample}")
        return 0

    try:
        events = load_events(args.input)
    except Exception as exc:  # noqa: BLE001 - surface any load failure cleanly
        print(f"error: could not load event log: {exc}", file=sys.stderr)
        return 1
    if not events:
        print(f"error: no events in {args.input}", file=sys.stderr)
        return 1

    warnings = check_sequence(events)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    moments, clips, queue, manifest = run_pipeline(events)
    write_manifest(manifest, args.output)

    if not args.quiet:
        round_no = events[0]["round_no"]
        print(f"Round R{round_no:04d}: {len(events)} events, "
              f"{len(moments)} moments detected, {len(clips)} clips saved, "
              f"{len(queue)} in today's queue -> {args.output}")
        for rank, clip in enumerate(queue, start=1):
            print(f"  {rank}. [{clip.drama}] {clip.title} "
                  f"({clip.duration_s}s, {clip.clip_format}, hole {clip.hole})")
        if clips and len(queue) < len(clips):
            print(f"  Library holds {len(clips) - len(queue)} more saved clip(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
