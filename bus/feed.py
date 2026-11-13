"""JSONL event feed for the bus (``python -m bus.feed``).

The file/pipe half of the sim-ingest contract: the sim engine runs
rounds synchronously and collects events in memory (``sim/engine.py`` —
``RoundResult.events``), so the simplest reliable way to get those
events onto the bus is a JSONL feed. Dump the events one JSON object
per line and pipe them in::

    python -m bus.feed events.jsonl
    cat events.jsonl | python -m bus.feed
    python -m sim.demo --rounds 1 --save /dev/stdout ... # (see demo.py)

``--delay`` paces the feed (seconds between events) so subscribers see
a realistic cadence instead of a whole round in one burst; ``--loop``
replays the file forever (the endless-round demo). Lines that are blank
or not valid JSON are skipped with a warning on stderr — one bad line
never kills the feed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .client import BusPublisher, BusError


def iter_events(source) -> object:
    """Yield parsed event dicts from a text stream, skipping bad lines."""
    for line_no, line in enumerate(source, 1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"bus.feed: line {line_no}: skipping bad JSON: {exc}",
                  file=sys.stderr)
            continue
        if not isinstance(event, dict):
            print(f"bus.feed: line {line_no}: skipping non-object",
                  file=sys.stderr)
            continue
        yield event


def feed(source, url: str, delay: float = 0.0, loop: bool = False,
         publisher_factory=BusPublisher) -> int:
    """Publish every event from ``source``; returns the count sent."""
    count = 0
    with publisher_factory(url) as pub:
        while True:
            for event in iter_events(source):
                pub.publish(event)
                count += 1
                if delay:
                    time.sleep(delay)
            if not loop:
                break
            try:
                source.seek(0)
            except (AttributeError, OSError):
                print("bus.feed: --loop needs a seekable file, not a pipe",
                      file=sys.stderr)
                break
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", default="-",
                        help="JSONL file of events (default: stdin)")
    parser.add_argument("--url", default="ws://localhost:4456",
                        help="bus URL (default: ws://localhost:4456)")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="seconds between events (default: 0)")
    parser.add_argument("--loop", action="store_true",
                        help="replay the file forever (file only)")
    args = parser.parse_args(argv)
    if args.file == "-":
        if args.loop:
            parser.error("--loop needs a file, not stdin")
        source = sys.stdin
        close = False
    else:
        source = open(args.file, encoding="utf-8")
        close = True
    try:
        return feed(source, args.url, delay=args.delay, loop=args.loop)
    except BusError as exc:
        print(f"bus.feed: {exc}", file=sys.stderr)
        return 1
    finally:
        if close:
            source.close()


if __name__ == "__main__":
    sys.exit(main())
