"""Fast test runner for the sim suite.

The full suite plays real rounds and takes ~15 minutes. This runner
splits it so iteration stays fast:

    python -m sim.run_tests            # FAST suite only (no full rounds)
    python -m sim.run_tests --slow     # everything, slow tests included
    python -m sim.run_tests --only-slow
    python -m sim.run_tests --parallel # fast suite, modules in parallel
    python -m sim.run_tests --parallel --slow

Slow tests are the ones marked ``@slow`` in sim/tests/_markers.py —
every test that plays a full round or an MC validation round. The fast
suite keeps the pure math, physics, putting solver, pins and learning
tests, so it catches regressions in seconds. Run --slow before any push
and on the Mac; the full suite is the pre-push gate, not the edit loop.

Exit code is 0 only when every selected test passes.
"""

import argparse
import concurrent.futures
import sys
import time
import unittest

from sim.tests._markers import is_slow

TEST_DIR = "sim/tests"
MODULES = [
    "sim.tests.test_sim",
    "sim.tests.test_putting_v2",
    "sim.tests.test_pins",
    "sim.tests.test_dunmore",
    "sim.tests.test_learning",
    "sim.tests.test_twins",
    "sim.tests.test_live_publish",
]


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def _load(module_name, include_slow, only_slow):
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(module_name)
    tests = list(_flatten(suite))
    if only_slow:
        return [t for t in tests if is_slow(t)]
    if not include_slow:
        return [t for t in tests if not is_slow(t)]
    return tests


def _run_one(args):
    """Worker: run one module's selected tests, return a summary dict."""
    module_name, include_slow, only_slow = args
    tests = _load(module_name, include_slow, only_slow)
    if not tests:
        return {"module": module_name, "ran": 0, "failures": 0,
                "errors": 0, "seconds": 0.0, "slow": 0}
    suite = unittest.TestSuite(tests)
    stream = open("/dev/null", "w")
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    t0 = time.monotonic()
    result = runner.run(suite)
    dt = time.monotonic() - t0
    stream.close()
    return {"module": module_name, "ran": result.testsRun,
            "failures": len(result.failures), "errors": len(result.errors),
            "seconds": dt, "slow": sum(1 for t in tests if is_slow(t))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--slow", action="store_true",
                    help="include slow (round-playing) tests")
    ap.add_argument("--only-slow", action="store_true",
                    help="run only the slow tests")
    ap.add_argument("--parallel", action="store_true",
                    help="run test modules in parallel processes")
    ap.add_argument("--modules", nargs="+", default=None,
                    help="only these modules (e.g. test_putting_v2)")
    args = ap.parse_args(argv)

    modules = args.modules or MODULES
    modules = [m if m.startswith("sim.tests.") else f"sim.tests.{m}"
               for m in modules]
    jobs = [(m, args.slow or args.only_slow, args.only_slow)
            for m in modules]

    t0 = time.monotonic()
    if args.parallel:
        with concurrent.futures.ProcessPoolExecutor(
                max_workers=min(len(jobs), 8)) as pool:
            summaries = list(pool.map(_run_one, jobs))
    else:
        summaries = [_run_one(j) for j in jobs]
    total = time.monotonic() - t0

    ran = sum(s["ran"] for s in summaries)
    failures = sum(s["failures"] for s in summaries)
    errors = sum(s["errors"] for s in summaries)
    slow_n = sum(s["slow"] for s in summaries)
    print(f"{'module':<28} {'ran':>4} {'slow':>4} {'fail':>4} {'err':>4} {'time':>7}")
    for s in summaries:
        print(f"{s['module']:<28} {s['ran']:>4} {s['slow']:>4} "
              f"{s['failures']:>4} {s['errors']:>4} {s['seconds']:>6.1f}s")
    mode = ("slow-only" if args.only_slow else
            "full" if args.slow else "FAST")
    print(f"\n{mode}: {ran} tests ({slow_n} slow), "
          f"{failures} failures, {errors} errors, {total:.1f}s total")
    return 0 if (failures == 0 and errors == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
