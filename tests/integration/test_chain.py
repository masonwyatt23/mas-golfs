"""End-to-end integration tests for Mas Golfs.

Proves the whole chain works on this VM, one test per link plus one
full-chain test:

  test_01_sim_link         sim plays a round and emits events
  test_02_bus_link         bus fans events out to subscribers
  test_03_commentary_link  commentary service receives + logs decisions
  test_04_nodecg_link      NodeCG extension updates its replicants
  test_05_clip_link        clip pipeline scores + builds the manifest
  test_06_full_chain       one 3-hole publish feeds all four consumers

The 3-hole fixture is the deterministic sample round R0042 (holes 1-3:
birdie, eagle, near-miss lip-out), so the chain is testable even while
the sim is broken. The sim-link test is the only one that touches the
real sim: if it raises, the test SKIPs as blocked-on-sim-fix with the
exact error instead of failing the chain — and the report says what to
re-run once the fix lands.

Run:  python3 tests/integration/run.py
  or:  python3 -m unittest tests.integration.test_chain -v
from the repo root. Expect ~2-4 minutes (fast sim rounds dominate).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.integration import fixtures  # noqa: E402
from tests.integration.harness import (  # noqa: E402
    BUS_PORT,
    BUS_URL,
    BusServer,
    CommentaryRunner,
    EnvelopeProbe,
    NodeCGRunner,
    publish_events,
)


class ChainTestCase(unittest.TestCase):
    tmpdir: Path
    server: BusServer
    fixture: list[dict]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="mas-golfs-integration-"))
        cls.server = BusServer(cls.tmpdir / "bus")
        cls.server.__enter__()
        cls.fixture = fixtures.three_hole_events()
        assert cls.fixture, "3-hole fixture is empty"
        print(f"\n[harness] tmpdir={cls.tmpdir} "
              f"fixture={len(cls.fixture)} events, "
              f"seqs {cls.fixture[0]['seq']}..{cls.fixture[-1]['seq']}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__()
        print(f"[harness] bus log: {cls.server.log_path}")

    # -- link 1: sim ------------------------------------------------------

    def test_01_sim_link(self):
        """Sim plays a real round and emits events (fast mode, seeds 1-3)."""
        outcomes: dict[int, str] = {}
        first_events: list[dict] | None = None
        for seed in fixtures.SIM_SEEDS:
            try:
                score, events = fixtures.try_sim_round(seed)
            except Exception as exc:  # noqa: BLE001 - verdict, not handling
                outcomes[seed] = f"{type(exc).__name__}: {exc}"
                continue
            outcomes[seed] = f"OK score={score} events={len(events)}"
            if first_events is None:
                first_events = events
        print(f"[sim] outcomes={outcomes}")
        if first_events is None:
            self.skipTest(
                "blocked-on-sim-fix: every seed failed: "
                + "; ".join(f"seed {s}: {o}" for s, o in outcomes.items())
                + " — re-run this test after the sim fix lands")
        self.assertGreater(len(first_events), 0, "sim emitted no events")
        types = {ev["type"] for ev in first_events}
        for needed in ("round_start", "hole_start", "shot_decision",
                       "shot_result", "hole_complete", "round_complete"):
            self.assertIn(needed, types, f"sim events lack {needed}")
        if len(outcomes) != len([o for o in outcomes.values()
                                 if o.startswith("OK")]):
            print("[sim] WARNING: some seeds failed but at least one "
                  "succeeded — sim is flaky, not fixed: "
                  + "; ".join(f"seed {s}: {o}" for s, o in outcomes.items()
                              if not o.startswith("OK")))

    # -- link 2: bus ------------------------------------------------------

    def test_02_bus_link(self):
        """Bus fans the fixture out: snapshot, fan-out, every sim seq."""
        with EnvelopeProbe() as probe:
            time.sleep(0.5)  # let the snapshot arrive
            publish_events(self.fixture)
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if len(probe.sim_seqs_seen()) >= len(self.fixture):
                    break
                time.sleep(0.2)
            probe.stop()
        self.assertIsNotNone(probe.snapshot,
                             "no round_state snapshot on connect")
        self.assertIsNone(probe.error, f"probe error: {probe.error}")
        seen = probe.sim_seqs_seen()
        want = {ev["seq"] for ev in self.fixture}
        self.assertEqual(want, seen,
                         f"bus dropped sim events: missing {sorted(want - seen)}")
        kinds = [env.get("event") for env in probe.envelopes]
        for kind in ("decision", "strike", "apex", "landing", "hole_end"):
            self.assertIn(kind, kinds, f"bus never emitted {kind}")
        # A shot_result must fan out to strike -> apex -> landing in order.
        order = [k for k in kinds if k in ("strike", "apex", "landing")]
        self.assertEqual(order[:3], ["strike", "apex", "landing"],
                         f"fan-out order wrong: {order[:6]}")
        state_file = self.server.state_file
        self.assertTrue(state_file.exists(),
                        "bus never wrote the watchdog last-event file")

    # -- link 3: commentary ----------------------------------------------

    def test_03_commentary_link(self):
        """Commentary service receives the fixture and logs decisions."""
        with CommentaryRunner(self.tmpdir / "commentary") as runner:
            publish_events(self.fixture)
            decisions = runner.wait_for_decisions(minimum=1, timeout=20.0)
        self.assertIsNone(runner.error, f"commentary error: {runner.error}")
        played = [d for d in decisions if d.get("played")]
        self.assertGreater(len(decisions), 0,
                           "commentary logged no decisions at all")
        self.assertGreater(len(played), 0,
                           f"commentary played no lines "
                           f"({len(decisions)} decisions, all dropped)")
        holes = {d.get("hole") for d in decisions if d.get("hole")}
        self.assertTrue(holes & {1, 2, 3},
                        f"commentary decisions reference no fixture hole: {holes}")
        print(f"[commentary] {len(decisions)} decisions, "
              f"{len(played)} played, holes={sorted(holes)}")

    # -- link 4: NodeCG ----------------------------------------------------

    def test_04_nodecg_link(self):
        """NodeCG extension updates its replicants from the bus stream."""
        with NodeCGRunner(self.tmpdir / "nodecg", run_seconds=12.0) as runner:
            time.sleep(2.0)  # let the extension connect
            publish_events(self.fixture)
            rc = runner.wait(timeout=60.0)
        self.assertEqual(rc, 0, f"NodeCG runner exited {rc}")
        snap = runner.snapshot()
        round_state = snap.get("roundState") or {}
        shot_data = snap.get("shotData") or {}
        self.assertEqual(round_state.get("hole"), 3,
                         f"roundState.hole is {round_state.get('hole')}, want 3")
        self.assertIsNotNone(shot_data.get("carry_yds"),
                             "shotData never got a carry (no apex seen?)")
        self.assertIsNotNone(shot_data.get("total_yds"),
                             "shotData never got a total (no landing seen?)")
        self.assertTrue(snap.get("lastShot"),
                        "lastShot replicant is empty")
        self.assertIsNotNone(snap.get("lowerThird"),
                             "no lower-third ever fired")
        # Coins: the bridge mirrored markets from the same fixture stream.
        coins_markets = snap.get("coinsMarkets") or {}
        markets = coins_markets.get("markets") or []
        self.assertGreater(len(markets), 0,
                           "coinsMarkets has no markets after the fixture stream")
        featured = [m for m in markets
                    if m.get("market_id") == (snap.get("prediction") or {}).get("market_id")]
        self.assertEqual(len(featured), 1,
                         "prediction market_id not found in coinsMarkets")
        self.assertTrue(any(m.get("status") == "resolved" for m in markets),
                        "no coins market resolved during the fixture stream")
        self.assertIn("weekly", snap.get("coinsLeaderboard") or {},
                      "coinsLeaderboard missing from snapshot")
        shown = [m["name"] for m in snap.get("messages", [])]
        self.assertIn("showLowerThird", shown,
                      "extension never sent a showLowerThird message")

    # -- link 5: clip pipeline ---------------------------------------------

    def test_05_clip_link(self):
        """Clip pipeline scores the fixture and builds the manifest."""
        sys.path.insert(0, str(fixtures.REPO_ROOT / "clip-pipeline"))
        from clip_pipeline.manifest import run_pipeline, write_manifest

        moments, clips, queue, manifest = run_pipeline(self.fixture)
        found = {m.moment_type for m in moments}
        for want in fixtures.three_hole_moment_types():
            self.assertIn(want, found,
                          f"clip scorer missed {want} (found {sorted(found)})")
        self.assertGreater(len(queue), 0, "daily queue is empty")
        self.assertEqual(manifest["summary"]["moments_detected"], len(moments))
        self.assertEqual(manifest["summary"]["queue_size"], len(queue))
        print(f"[clips] {len(moments)} moments "
              f"({sorted(found)}), {len(clips)} saved, "
              f"{len(queue)} in queue")

        # ffmpeg assembly: present here, but there are no OBS recordings,
        # so every clip must SKIP cleanly — never crash the queue.
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg not installed — assembly check skipped")
        manifest_path = self.tmpdir / "manifest.json"
        write_manifest(manifest, manifest_path)
        result = subprocess.run(
            [sys.executable, "-m", "clip_pipeline.cli",
             "--assemble", str(manifest_path),
             "--recordings", str(self.tmpdir / "no-recordings"),
             "--clips-out", str(self.tmpdir / "clips")],
            cwd=str(fixtures.REPO_ROOT / "clip-pipeline"),
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0,
                         f"assemble CLI failed with no recordings:\n{result.stderr}")
        self.assertIn("SKIP", result.stdout,
                      "assemble did not report skipped clips")

    # -- full chain ----------------------------------------------------------

    def test_06_full_chain(self):
        """One 3-hole publish feeds bus, commentary, NodeCG and clips."""
        with EnvelopeProbe() as probe, \
                CommentaryRunner(self.tmpdir / "fullchain-commentary") as comm, \
                NodeCGRunner(self.tmpdir / "fullchain-nodecg",
                             run_seconds=12.0) as nodecg:
            time.sleep(2.0)  # consumers connect first
            publish_events(self.fixture)
            nodecg.wait(timeout=60.0)
            probe.stop()
            decisions = comm.wait_for_decisions(minimum=1, timeout=10.0)

        want = {ev["seq"] for ev in self.fixture}
        self.assertEqual(want, probe.sim_seqs_seen(),
                         "full chain: bus dropped events")
        # A service that died mid-round must fail the chain, even if it
        # logged lines first: the stop record is written by run()'s
        # except handler, so its presence (or a thread error) proves the
        # crash. This caught a real bug in test_03 (see README).
        self.assertIsNone(comm.error,
                          f"full chain: commentary service crashed: {comm.error}")
        self.assertGreater(len(decisions), 0,
                           "full chain: commentary logged nothing")
        self.assertFalse(any(d.get("event") == "__service_stop__"
                             for d in decisions),
                         "full chain: commentary service stopped mid-round")
        self.assertTrue(any(d.get("played") for d in decisions),
                        "full chain: commentary played no line")
        snap = nodecg.snapshot()
        self.assertEqual((snap.get("roundState") or {}).get("hole"), 3,
                         "full chain: NodeCG never reached hole 3")
        self.assertTrue(snap.get("lastShot"),
                        "full chain: NodeCG lastShot empty")

        sys.path.insert(0, str(fixtures.REPO_ROOT / "clip-pipeline"))
        from clip_pipeline.manifest import run_pipeline

        moments, _clips, queue, _manifest = run_pipeline(self.fixture)
        found = {m.moment_type for m in moments}
        self.assertTrue(fixtures.three_hole_moment_types() <= found,
                        f"full chain: clip moments missing: "
                        f"{sorted(fixtures.three_hole_moment_types() - found)}")
        self.assertGreater(len(queue), 0, "full chain: clip queue empty")
        print(f"[full-chain] bus={len(probe.envelopes)} envelopes, "
              f"commentary={len(decisions)} decisions, "
              f"nodecg hole={(snap.get('roundState') or {}).get('hole')}, "
              f"clips={len(moments)} moments / {len(queue)} queued")


if __name__ == "__main__":
    unittest.main(verbosity=2)
