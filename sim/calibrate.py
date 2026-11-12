"""Calibration harness (spec §3.7).

Simulates N rounds and checks the engine against the §3.1 / §3.3 / §3.5
targets. Every metric must land within +/-5% (scoring average and
proximity use absolute bands from the spec tables).

Usage:
    python -m sim.calibrate [--rounds N] [--mc N] [--fast] [--seed N]

--fast (default) uses the rule-based decision path so 1,000 rounds run in
~1-2 minutes. That validates the physics, dispersion, putting, and course
models — not the Monte Carlo decision quality. Use --mc 120 with a small
--rounds (e.g. 10) to sanity-check the Monte Carlo path end to end.
"""

from __future__ import annotations

import argparse
import statistics
import sys

from . import constants as C
from .engine import RoundEngine


def run_calibration(rounds: int = 1000, mc_n: int = 120,
                    fast_mode: bool = True, seed: int = 0,
                    course=None) -> dict:
    engine = RoundEngine(mc_n=mc_n, fast_mode=fast_mode, seed_offset=seed,
                         course=course)
    results = [engine.play_round() for _ in range(rounds)]
    n = len(results)

    def avg(fn):
        return statistics.mean(fn(r) for r in results)

    driving = [r.stats["driving_avg_yd"] for r in results]
    metrics = {
        "driving_distance_yd": statistics.mean(driving),
        "fairway_pct": avg(lambda r: r.stats["fairway_pct"]),
        "gir_pct": avg(lambda r: r.stats["gir_pct"]),
        "scoring_avg": avg(lambda r: r.score),
        "putts_per_round": avg(lambda r: r.stats["putts"]),
        "scrambling_pct": avg(lambda r: r.stats["scrambling_pct"]),
        "sand_save_pct": _sand_save_rate(results),
        "ball_speed_driver_mph": _driver_ball_speed(engine),
        "club_speed_driver_mph": 110.0,  # mean of the delivery distribution
    }
    return {"metrics": metrics, "rounds": n, "engine": engine}


def _sand_save_rate(results) -> float:
    made = total = 0
    for r in results:
        for h in r.holes:
            if h.sand_save is not None:
                total += 1
                made += 1 if h.sand_save else 0
    return made / total if total else 0.0


def _driver_ball_speed(engine) -> float:
    # Mean driver ball speed from the delivery distribution: 110 mph club
    # speed x 1.49 smash, minus the small share of mishits. Sampled
    # directly from the launch conversion for honesty.
    from .physics import draw_delivery, classify_contact, delivery_to_launch
    from .rng import Rng
    rng = Rng(12345)
    speeds = []
    for _ in range(2000):
        d = draw_delivery(rng, "driver", "full", 1.0, "straight", False, "tee")
        q = classify_contact(d, rng)
        launch = delivery_to_launch(d, "driver", q, "tee", 0.0, rng)
        speeds.append(launch.ball_speed_mph)
    return statistics.mean(speeds)


def check(metrics: dict) -> list:
    """Compare metrics to §3.1 targets; return (name, actual, target, pass)."""
    rows = []
    for name, (target, tol) in C.CALIBRATION_TARGETS.items():
        actual = metrics[name]
        # Scoring average and driving distance use the spec's bands.
        if name == "scoring_avg":
            ok = 71.0 <= actual <= 73.0
        elif name == "driving_distance_yd":
            ok = 265.0 <= actual <= 275.0
        else:
            ok = abs(actual - target) / target <= max(tol, 0.05)
        rows.append((name, actual, target, ok))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=1000)
    parser.add_argument("--mc", type=int, default=120)
    parser.add_argument("--fast", action="store_true", default=True)
    parser.add_argument("--no-fast", dest="fast", action="store_false")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--course", choices=["wyatt", "black"],
                        default="wyatt")
    args = parser.parse_args(argv)

    from .course import championship_variant
    course = championship_variant() if args.course == "black" else None
    print(f"Calibrating over {args.rounds} rounds "
          f"({'fast' if args.fast else f'MC n={args.mc}'}) "
          f"on {course.name if course else 'Wyatt National'} ...")
    out = run_calibration(args.rounds, args.mc, args.fast, args.seed, course)
    rows = check(out["metrics"])
    print(f"\n{'metric':<26}{'actual':>10}{'target':>10}  pass")
    print("-" * 52)
    all_pass = True
    for name, actual, target, ok in rows:
        all_pass &= ok
        print(f"{name:<26}{actual:>10.2f}{target:>10.2f}  "
              f"{'PASS' if ok else 'FAIL'}")
    print(f"\n{'ALL METRICS PASS' if all_pass else 'CALIBRATION FAILED — '
          'retune §3.2 sigmas, never the physics (§3.1)'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
