"""Shared machinery for the Mas Golfs end-to-end integration harness.

Owns the live pieces the chain tests need and nothing else:

* the real bus server (``python -m bus``) as a subprocess on port 4456,
* a probe subscriber that records every envelope the bus emits,
* the real commentary service (stub LLM/TTS, fake clock) in a thread,
* the real NodeCG extension driven through the ``ws`` shim (see
  ``node_modules/ws``) as a subprocess.

Nothing here edits production code. All state lands under a caller-owned
temp dir so a harness run never touches the repo's working state.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

for _p in (str(REPO_ROOT), str(REPO_ROOT / "clip-pipeline")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

BUS_PORT = 4456
BUS_URL = f"ws://127.0.0.1:{BUS_PORT}"


def wait_for_port(port: int, timeout: float = 15.0) -> bool:
    """True once something accepts TCP on localhost:port."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class BusServer:
    """The real bus server (``python -m bus``) as a managed subprocess."""

    def __init__(self, tmpdir: Path):
        self.tmpdir = Path(tmpdir)
        self.state_file = self.tmpdir / "last_event"
        self.proc: subprocess.Popen | None = None
        self.log_path = self.tmpdir / "bus-server.log"

    def __enter__(self) -> "BusServer":
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "bus", "--port", str(BUS_PORT),
             "--state-file", str(self.state_file)],
            cwd=str(REPO_ROOT), env=env,
            stdout=log, stderr=subprocess.STDOUT,
        )
        self._log_handle = log
        if not wait_for_port(BUS_PORT, timeout=15.0):
            self.stop()
            raise RuntimeError(
                f"bus server did not start on port {BUS_PORT} "
                f"(see {self.log_path})")
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
            self.proc = None
        handle = getattr(self, "_log_handle", None)
        if handle is not None:
            handle.close()


def publish_events(events: list[dict], url: str = BUS_URL,
                   delay: float = 0.0) -> int:
    """Publish flat sim events to the bus. Returns the count published."""
    from bus.client import BusPublisher

    with BusPublisher(url) as pub:
        for ev in events:
            pub.publish(ev)
            if delay:
                time.sleep(delay)
    return len(events)


class EnvelopeProbe:
    """A subscriber that records every envelope the bus emits.

    Connects as a plain client (so it also proves snapshot-on-connect)
    and collects parsed envelopes in a background thread until stopped.
    """

    def __init__(self, url: str = BUS_URL):
        self.url = url
        self.envelopes: list[dict] = []
        self.snapshot: dict | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    def __enter__(self) -> "EnvelopeProbe":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def _run(self) -> None:
        from bus.client import BusPublisher, BusError

        try:
            with BusPublisher(self.url) as client:
                while not self._stop.is_set():
                    try:
                        raw = client.recv_text(timeout=0.5)
                    except TimeoutError:
                        continue
                    env = json.loads(raw)
                    if self.snapshot is None and env.get("event") == "round_state":
                        self.snapshot = env
                    self.envelopes.append(env)
        except (BusError, OSError, ValueError) as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def sim_seqs_seen(self) -> set[int]:
        """Sim seq numbers the bus fanned out (proves every event arrived)."""
        seen: set[int] = set()
        for env in self.envelopes:
            data = env.get("data") or {}
            if isinstance(data.get("sim_seq"), int):
                seen.add(data["sim_seq"])
        return seen


class FakeClock:
    """A monotonic clock that jumps 20 s per call.

    The commentary service rate-limits to one line per 15 s; a fake clock
    that advances past the limit on every read makes every planned line
    playable, so the harness measures the pipeline instead of the limiter.
    """

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        self.now += 20.0
        return self.now


class CommentaryRunner:
    """The real commentary service (stub LLM/TTS) on the real bus.

    Runs ``CommentaryService.run()`` in a daemon thread against the live
    bus server. Decision log, output log and audio all land under the
    caller-owned tmp dir.
    """

    def __init__(self, tmpdir: Path, url: str = BUS_URL):
        self.tmpdir = Path(tmpdir)
        self.url = url
        self.decision_log = self.tmpdir / "commentary-decisions.jsonl"
        self.output_log = self.tmpdir / "commentary-output.jsonl"
        self.audio_dir = self.tmpdir / "commentary-audio"
        self.cache_dir = self.tmpdir / "commentary-cache"
        self._service = None
        self._bus = None
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    def __enter__(self) -> "CommentaryRunner":
        from commentary.bus import WebSocketBus
        from commentary.config import load_config
        from commentary.service import CommentaryService

        self.tmpdir.mkdir(parents=True, exist_ok=True)
        cfg = load_config(str(REPO_ROOT / "commentary" / "config.yaml"))
        cfg["bus"]["url"] = self.url
        cfg["stub_llm"] = True
        cfg["dry_run"] = True
        cfg["paths"] = {
            "decision_log": str(self.decision_log),
            "output_log": str(self.output_log),
            "audio_dir": str(self.audio_dir),
        }
        cfg.setdefault("tts", {})["cache_dir"] = str(self.cache_dir)
        self._service = CommentaryService(cfg, clock=FakeClock())
        self._bus = WebSocketBus(self.url)
        self._bus.connect()
        self._thread = threading.Thread(
            target=self._run_service, daemon=True)
        self._thread.start()
        return self

    def _run_service(self) -> None:
        try:
            self._service.run(self._bus)
        except Exception as exc:  # noqa: BLE001 - thread boundary; recorded
            self.error = f"{type(exc).__name__}: {exc}"

    def __exit__(self, *exc) -> None:
        self.stop()

    def stop(self, timeout: float = 5.0) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:  # noqa: BLE001 - best-effort shutdown
                pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def decisions(self) -> list[dict]:
        """Parsed decision-log records (empty until the service writes)."""
        if not self.decision_log.exists():
            return []
        out = []
        for line in self.decision_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def wait_for_decisions(self, minimum: int = 1,
                           timeout: float = 15.0) -> list[dict]:
        """Block until at least ``minimum`` decisions are logged."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = self.decisions()
            if len(found) >= minimum:
                return found
            time.sleep(0.2)
        return self.decisions()


class NodeCGRunner:
    """The real NodeCG extension, driven through the ``ws`` shim.

    Runs ``run_nodecg.js`` as a subprocess with NODE_PATH pointed at the
    harness's ``node_modules`` (a stdlib-only ``ws`` shim over Node 24's
    built-in WebSocket client — no npm install needed). The runner dumps
    the replicants to a snapshot JSON file when its run window ends.
    """

    def __init__(self, tmpdir: Path, run_seconds: float = 12.0,
                 url: str = BUS_URL):
        self.tmpdir = Path(tmpdir)
        self.run_seconds = run_seconds
        self.url = url
        self.snapshot_path = self.tmpdir / "nodecg-snapshot.json"
        self.log_path = self.tmpdir / "nodecg.log"
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> "NodeCGRunner":
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        harness_dir = Path(__file__).resolve().parent
        env["NODE_PATH"] = str(harness_dir / "node_modules")
        env["MAS_GOLFS_BUS_URL"] = self.url
        env["NODECG_SNAPSHOT_PATH"] = str(self.snapshot_path)
        env["NODECG_RUN_SECONDS"] = str(self.run_seconds)
        log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            ["node", str(harness_dir / "run_nodecg.js")],
            cwd=str(REPO_ROOT), env=env,
            stdout=log, stderr=subprocess.STDOUT,
        )
        self._log_handle = log
        return self

    def __exit__(self, *exc) -> None:
        self.wait()

    def wait(self, timeout: float = 60.0) -> int:
        """Wait for the runner to exit; returns its exit code."""
        if self.proc is None:
            return -1
        try:
            return self.proc.wait(timeout=timeout)
        finally:
            handle = getattr(self, "_log_handle", None)
            if handle is not None:
                handle.close()

    def snapshot(self) -> dict:
        if not self.snapshot_path.exists():
            raise FileNotFoundError(
                f"NodeCG runner wrote no snapshot (see {self.log_path})")
        return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
