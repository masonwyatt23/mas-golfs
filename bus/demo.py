"""Live demo publisher (``python -m bus.demo``).

Plays sim rounds in-process and publishes every event to the bus as it
happens — the end-to-end smoke test for sim -> bus -> subscribers.
This is a demo, not the broadcast path: the real show will have the
sim engine publish live as it plays (see ``bus/README.md``); this
script just proves the wiring with the engine we already have.

Defaults to the fast rule-based decision path (a round takes ~1-2 s)
so the demo finishes quickly; pass ``--mc 120`` for the real Monte
Carlo path. ``--delay`` paces the published events so a subscriber
watching the stream sees a realistic cadence instead of a whole round
in one burst.
"""

from __future__ import annotations

import argparse
import sys
import time

from .client import BusPublisher, BusError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mc", type=int, default=120)
    parser.add_argument("--fast", action="store_true", default=True,
                        help="rule-based decisions (default: on)")
    parser.add_argument("--no-fast", dest="fast", action="store_false")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="seconds between published events")
    parser.add_argument("--url", default="ws://localhost:4456")
    args = parser.parse_args(argv)

    from sim.engine import RoundEngine  # local import: bus stays sim-free

    engine = RoundEngine(mc_n=args.mc, fast_mode=args.fast,
                         seed_offset=args.seed)
    try:
        with BusPublisher(args.url) as pub:
            for _ in range(args.rounds):
                result = engine.play_round()
                print(f"Round {result.round_no}: {result.score} "
                      f"({result.score_to_par:+d}) — "
                      f"{len(result.events)} events", flush=True)
                for event in result.events:
                    pub.publish(event)
                    if args.delay:
                        time.sleep(args.delay)
    except BusError as exc:
        print(f"bus.demo: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
