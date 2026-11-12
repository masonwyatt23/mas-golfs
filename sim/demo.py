"""Demo: simulate rounds of Mas Golfs and print the scorecard.

Usage:
    python -m sim.demo [--rounds N] [--seed N] [--mc N] [--fast]
                       [--course wyatt|black] [--save PATH]

--mc N sets the Monte Carlo size per decision (default 120, spec §5.4).
--fast uses the rule-based decision path (no Monte Carlo) — much faster,
used by the calibration harness. --course black plays the championship
(black tee) variant with its harder computed rating/slope. --save writes
the engine state (golfer model, records, handicap history) to a JSON file
for the next run.
"""

from __future__ import annotations

import argparse
import json
import sys

from .course import championship_variant
from .engine import RoundEngine


def print_scorecard(result, engine):
    holes = result.holes
    c = engine.course
    print(f"\n=== Mas Golfs — Round {result.round_no} at {c.name} "
          f"(par {c.par}, rating {c.rating}, slope {c.slope}) ===")
    print(f"Score: {result.score} ({result.score_to_par:+d})   "
          f"Handicap: {result.handicap_before} -> {result.handicap_after} "
          f"(diff {result.differential:+.1f})")
    print(f"Sim time: {result.sim_ms:.0f} ms  |  "
          f"Decision time: {result.decisions_ms:.0f} ms over "
          f"{engine.total_decisions} decisions")
    print()
    hdr = "Hole  " + " ".join(f"{h.hole:>3}" for h in holes) + "   Tot"
    par = "Par   " + " ".join(f"{h.par:>3}" for h in holes) + f"   {sum(h.par for h in holes)}"
    scr = "Score " + " ".join(f"{h.score:>3}" for h in holes) + f"   {result.score}"
    print(hdr)
    print(par)
    print(scr)
    print()
    for h in holes:
        marks = []
        if h.score - h.par <= -1:
            marks.append("birdie" if h.score - h.par == -1 else "eagle")
        if h.penalties:
            marks.append(f"{h.penalties} pen")
        print(f"  {h.hole:>2} {h.score_name:<12} {h.score} "
              f"({h.score - h.par:+d})  putts={h.putts} "
              f"GIR={'Y' if h.gir else '-'} "
              f"FW={'Y' if h.fairway_hit else ('-' if h.fairway_hit is None else 'n')}"
              + (f"  drive {h.driving_yd} yd" if h.driving_yd else "")
              + (f"  appr {h.approach_ft} ft" if h.approach_ft is not None else "")
              + (f"  {' '.join(marks)}" if marks else ""))
    print()
    print("Stats:", json.dumps(result.stats, indent=2))
    print("Strokes gained:", json.dumps(result.strokes_gained))
    print("59 Watch:", json.dumps(result.fifty_nine_watch))
    if result.focus_fix:
        print("Focus fix for next round:", json.dumps(result.focus_fix))
    print(f"Events emitted: {len(result.events)} "
          f"({len(set(e['type'] for e in result.events))} types)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0,
                        help="seed offset (0 = spec seeding, §8.4)")
    parser.add_argument("--mc", type=int, default=120)
    parser.add_argument("--fast", action="store_true",
                        help="rule-based decisions, no Monte Carlo")
    parser.add_argument("--course", choices=["wyatt", "black"],
                        default="wyatt")
    parser.add_argument("--save", default=None)
    parser.add_argument("--load", default=None)
    args = parser.parse_args(argv)

    course = championship_variant() if args.course == "black" else None
    if args.load:
        engine = RoundEngine.load(args.load, mc_n=args.mc,
                                  fast_mode=args.fast,
                                  seed_offset=args.seed, course=course)
    else:
        engine = RoundEngine(mc_n=args.mc, fast_mode=args.fast,
                             seed_offset=args.seed, course=course)
    for _ in range(args.rounds):
        result = engine.play_round()
        print_scorecard(result, engine)
    if args.save:
        engine.save(args.save)
        print(f"\nState saved to {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
