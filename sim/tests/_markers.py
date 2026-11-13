"""Test-speed markers for the sim suite.

The full sim suite plays real rounds (a fast-mode round is ~25 s, an
mc_n=60 validation round ~1 min), so running everything on every change
costs ~15 minutes. The suite is therefore split:

- FAST (default, ``python -m sim.run_tests``): every test NOT marked
  slow — pure math, physics, putting solver, pins, learning logic.
  Runs in seconds; this is the loop you run while iterating.
- SLOW (``python -m sim.run_tests --slow``): everything, including the
  round-playing integration tests. Run before any push and on the Mac.

Mark a test that plays a full round (or an MC validation round) with
``@slow``. A test that only calls the putting solver or the physics
functions directly stays fast.
"""


def slow(fn):
    """Mark a test method as slow (plays a full round / MC validation)."""
    fn.__slow__ = True
    return fn


def is_slow(test) -> bool:
    """True if a unittest TestCase instance is a slow test."""
    method = getattr(test, test._testMethodName, None)
    return bool(getattr(method, "__slow__", False))
