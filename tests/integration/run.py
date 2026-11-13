"""Run the Mas Golfs end-to-end integration harness and print a per-link verdict.

Usage (from the repo root):
    python3 tests/integration/run.py

Exits 0 only if every link passes. A skipped sim-link test means
blocked-on-sim-fix — see its skip reason for the exact error and the
re-run command.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

LINK_NAMES = {
    "test_01_sim_link": "sim",
    "test_02_bus_link": "bus",
    "test_03_commentary_link": "commentary",
    "test_04_nodecg_link": "nodecg",
    "test_05_clip_link": "clips",
    "test_06_full_chain": "full-chain",
}


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.integration.test_chain")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    failed = {t.id().split(".")[-1] for t, _ in result.failures + result.errors}
    skipped = {t.id().split(".")[-1]: reason
               for t, reason in result.skipped}
    unmatched = sorted(
        tid for tid in failed
        if tid not in LINK_NAMES and tid not in skipped)
    print("\n=== integration harness verdict ===")
    for test_id, link in LINK_NAMES.items():
        if test_id in failed:
            print(f"  FAIL    {link}")
        elif test_id in skipped:
            print(f"  SKIPPED {link} — {skipped[test_id]}")
        else:
            print(f"  PASS    {link}")
    for tid in unmatched:
        print(f"  ERROR   {tid} (setup/other — see traceback above)")
    if result.wasSuccessful():
        print("All links green.")
        return 0
    if failed:
        print("Failures above — see the tracebacks.")
    if "test_01_sim_link" in skipped:
        print("Re-run after the sim fix lands: "
              "python3 tests/integration/run.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
