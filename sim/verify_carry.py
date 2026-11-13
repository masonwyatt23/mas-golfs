"""Independent verification of the driver-carry retune (Nov 13, 2026).

Measures, with the current code:
  1. Pure driver carry at 161 mph / 12 deg / 2,900 rpm (the gapping
     condition) — target 268 yd.
  2. Drawn 300-shot mean driver carry (mishits included) — the metric
     that measured 240.4 yd in the two pre-fix samples.
  3. Pure-shot carry vs the gapping table for all 14 clubs.
  4. 3-wood drawn mean carry (was 229.0 yd pre-fix, target 245).
Run: python -m sim.verify_carry  (from the repo root; safe to delete)
"""
import statistics

from sim import constants as C
from sim.physics import (classify_contact, delivery_to_launch, draw_delivery,
                         fly, fly_shot)
from sim.rng import Rng


def pure_carry(club, ball_speed=161.0, launch=12.0, spin=2900.0):
    fl = fly(ball_speed, launch, spin, 0.0, 0.0)
    return float(fl.carry_yd[0])


def drawn_mean_carry(club, n=300, seed=99):
    rng = Rng(seed)
    carries = []
    for _ in range(n):
        d = draw_delivery(rng, club, "full", 1.0, "straight", False, "tee")
        q = classify_contact(d, rng)
        launch = delivery_to_launch(d, club, q, "tee", 0.0, rng)
        fl = fly_shot(launch)
        carries.append(float(fl.carry_yd[0]))
    return statistics.mean(carries), statistics.stdev(carries)


def main():
    print("== pure driver carry: 161 mph / 12 deg / 2900 rpm =="
          f" {pure_carry('driver'):.1f} yd (target 268)")
    mean, sd = drawn_mean_carry("driver")
    print(f"== drawn 300-shot driver mean carry == {mean:.1f} yd "
          f"(sd {sd:.1f}; pre-fix 240.4)")
    m3, sd3 = drawn_mean_carry("3-wood")
    print(f"== drawn 300-shot 3-wood mean carry == {m3:.1f} yd "
          f"(sd {sd3:.1f}; pre-fix 229.0, target 245)")
    print("\n== pure-shot gapping check (all 14 clubs) ==")
    errs = []
    for club, spec in C.CLUBS.items():
        # Pure shot at the club's own launch table + base spin; ball speed
        # from the club's mean speed x pure smash.
        bs = spec["speed_mean"] * spec["smash"]
        fl = fly(bs, C.LAUNCH_DEG[club], float(spec["base_spin"]), 0.0, 0.0)
        got = float(fl.carry_yd[0])
        err = (got - spec["carry"]) / spec["carry"] * 100.0
        errs.append(abs(err))
        print(f"  {club:8s} target {spec['carry']:3d}  got {got:6.1f}  "
              f"err {err:+5.1f}%")
    print(f"mean abs err: {statistics.mean(errs):.2f}% "
          f"(pre-fix 2.14%, post-refit claim 1.80%)")


if __name__ == "__main__":
    main()
