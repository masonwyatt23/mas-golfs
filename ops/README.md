# Mas Golfs — ops automation

The 24/7 watchdog and auto-recovery for the broadcast box (the 8GB
MacBook Pro). Implements `docs/deployment-runbook.md` §4. Free tools
only, macOS built-ins only. The 16GB MacBook Air is off-limits entirely
and never appears in this code as a machine.

## Files

| File | What it is |
|---|---|
| `watchdog.sh` | The watchdog. Runs every 30 s, checks §4.1 in priority order, acts in the §4.3 restart order, logs to `watchdog.log`, touches `state/heartbeat` every run. |
| `start_stack.sh` | Starts the stack in §4.3 order (web server → NodeCG → Kokoro → OBS) with a health check between steps. Run by the broadcast launchd agent on login. Idempotent; sleeps forever so launchd KeepAlive has something to keep. |
| `check_heartbeat.sh` | The watchdog-watches-itself check. Runs every 5 min; if the heartbeat is stale > 5 min it restarts the watchdog agent and pages Mason. |
| `cleanup.sh` | Weekly disk cleanup: recordings/replays older than 7 days, log rotation. Run Sundays 03:00 and on demand by the watchdog (check 7). |
| `obs_client.py` | Minimal obs-websocket client (stdlib only). `GetStreamStatus`, `StartStream`, `StopStream`, `SetCurrentProgramScene`. No auth — the box runs obs-websocket without authentication (locked-down local box, broadcast-stack.md §1). |
| `com.masgolfs.broadcast.plist` | launchd: start the stack on login, KeepAlive. |
| `com.masgolfs.watchdog.plist` | launchd: run the watchdog every 30 s. |
| `com.masgolfs.heartbeat.plist` | launchd: run the heartbeat checker every 5 min. |
| `com.masgolfs.cleanup.plist` | launchd: run the cleanup Sundays 03:00. |
| `install.sh` | Installs everything on the broadcast box and prints a verification checklist. |

## Install

On the 8GB MacBook Pro, as the `masgolfs` user, from the repo checkout:

```bash
~/mas-golfs/ops/install.sh
```

It checks the machine and tools, copies the scripts into
`~/mas-golfs/ops`, substitutes the real home path into the plists,
loads the four agents, and prints a verification checklist. Safe to
re-run after an update. It never touches any other machine.

## No scheduled restart

There is **no daily restart and no scheduled restart of any kind**
(runbook §4.4). The watchdog never restarts anything on a clock.
Restarts happen only on update, fault, or watchdog-detected drift.
Verify it after install:

```bash
launchctl list | grep -i restart   # should print nothing
grep -ri "daily restart" ~/mas-golfs/ops   # should print nothing
```

## What each check does

Checks run in priority order (runbook §4.1). The watchdog runs every
30 s; longer-interval checks are gated so they only run when due.

| # | Check | Interval | Failure → action |
|---|---|---|---|
| 1 | OBS streaming | 30 s | obs-websocket (4455) not answering → restart OBS. Stream not active → `StartStream`. Still down → ordered restart, then page (`stream_down`, pages any time of day). |
| 2 | Web build rendering | 60 s | `http://localhost:8080` must return 200 and contain "Mas Golfs". Fail → restart the web server. Still down → ordered restart, then page. |
| 3 | Event bus alive | 60 s | Port 4456 must be listening. If the bus server writes a last-event timestamp to `ops/state/last_event` (epoch seconds), it must be < 60 s old. Fail → restart the bus if `MAS_GOLFS_BUS_RESTART_CMD` is set, else log + page (`event_bus_silent`). |
| 4 | NodeCG graphics | 60 s | Scorebug URL must return 200. Fail → restart NodeCG. Still down → ordered restart, then page (`overlays_down`). |
| 5 | Kokoro TTS | 5 min | Test synthesis (`POST /v1/audio/speech`, voice `am_michael`) must return 200 within 5 s. Fail → `docker restart kokoro`. Still down → log + page (`kokoro_down`). The stream continues — commentary is silent, the ambient bed carries it. |
| 6 | GPU memory flat | 15 min | Apple Silicon exposes no direct GPU-memory counter to the shell, so this uses browser-process memory as the proxy (the WebGL renderer lives in the browser) against the lowest RSS seen in 24 h. Growth > 10% → page (`gpu_memory`, the leak may be back). Growth > 25% → ordered restart + page. The web build's own perf HUD (`renderer.info.memory`) is the authoritative source; this check is the tripwire. |
| 6b | Swap pressure flat | 15 min | `sysctl vm.swapusage`. Swap Used growing → logged warning. Swap ≥ 2 GB → page (`swap_pressure`): the 8GB box is out of headroom; sustained swap is the first upgrade trigger (runbook §0). |
| 7 | Disk > 20 GB free | 15 min | Below the floor → run `cleanup.sh` (recordings/replays > 7 days) and re-check. Still below → page (`disk_low`). |
| 8 | Network up | 60 s | Default gateway ping + HTTPS HEAD to the Restream ingest host. Every 15 min, `networkQuality` must report upload > 5 Mbps. Fail → page (`network_down` / `network_slow`). |

## Alerting

One alert per incident per 30 minutes (repeats are suppressed and
logged). Quiet hours 21:30–09:00 local for everything **except**
`stream_down`, which always pages. "Paging" on this box is a local
notification (`osascript display notification`) plus a line in
`alerts.log` — there is no external send. The five paging failures are
the runbook §5.3 list: stream down > 5 min, event bus silent > 60 s,
GPU memory climbing > 10% over a round, WebGL context lost, watchdog
itself down.

Every failure and every restart also gets one line in `ops-log.md`
(runbook §6.4): if it isn't written down, it didn't happen.

## Testing each check

Test one failure at a time, on the broadcast box, and watch
`tail -f ~/mas-golfs/ops/watchdog.log`. Each test should recover
without a human; if it doesn't, the log says exactly which step
failed.

| To test | Do this | Expect |
|---|---|---|
| 1 — OBS down | Quit OBS | Watchdog restarts OBS and streaming within ~30 s. |
| 1 — stream stopped | Stop streaming in OBS (leave OBS open) | Watchdog calls `StartStream` within ~30 s. |
| 2 — web build down | `pkill -f "http.server 8080"` | Watchdog restarts the web server within ~60 s. |
| 3 — event bus down | Stop the bus server | Watchdog logs + pages `event_bus_silent`. (Restart only happens if `MAS_GOLFS_BUS_RESTART_CMD` is set — see below.) |
| 4 — NodeCG down | Stop NodeCG | Watchdog restarts NodeCG within ~60 s. |
| 5 — Kokoro down | `docker stop kokoro` | Watchdog restarts the container within ~5 min. |
| 6 — memory growth | Open extra browser tabs until Chrome RSS grows > 10% over baseline | `gpu_memory` alert in `alerts.log`. (Deliberate; close the tabs after.) |
| 6b — swap | Same as 6, on a long run | `swap_pressure` warning in the log once swap starts growing. |
| 7 — disk low | Create a filler file until free < 20 GB (`mkfile 30g /tmp/filler` then delete it after) | Watchdog runs cleanup and re-checks. |
| 8 — network down | Unplug Ethernet / turn off Wi-Fi briefly | `network_down` alert; recovery when the network returns. |
| Watchdog itself down | `launchctl bootout gui/$(id -u)/com.masgolfs.watchdog` | Heartbeat checker restarts it within ~5 min and pages `watchdog_down`. |

## Contracts the watchdog depends on

These are the things other components must provide for the checks to
mean what they say. If a contract is missing, the check degrades to a
logged skip or a port-only check — never to a silent pass.

- **Event bus last-event file.** The bus server (Node.js `ws` on
  `localhost:4456`, broadcast-stack.md §1) should write the epoch
  seconds of the last event it emitted to
  `~/mas-golfs/ops/state/last_event` on every event. Until it does,
  check 3 verifies only that port 4456 is listening. Set
  `MAS_GOLFS_BUS_RESTART_CMD` to the command that restarts the bus
  server once it ships; until then, a dead bus is log + page only.
- **Kokoro container name.** The container must be named `kokoro`
  (the name in `docs/voice-options.md` §2). Override with
  `MAS_GOLFS_KOKORO_CONTAINER`.
- **NodeCG home.** The NodeCG server directory must contain
  `server.js`. Default `~/nodecg`; override with
  `MAS_GOLFS_NODECG_HOME`.
- **Intermission scene.** Before an ordered restart the watchdog tries
  to cut OBS to the scene named by `MAS_GOLFS_INTERMISSION_SCENE`
  (default `INTERMISSION`). If the scene does not exist the call fails
  silently and the restart proceeds — the intermission is a nicety,
  not a dependency.
- **obs-websocket.** OBS must have obs-websocket enabled on
  `localhost:4455` with no authentication (bundled since OBS 28,
  broadcast-stack.md §1). If authentication is ever enabled,
  `obs_client.py` exits 2 and says so.

## Verifying the scripts

```bash
bash -n ~/mas-golfs/ops/*.sh
python3 -m py_compile ~/mas-golfs/ops/obs_client.py
python3 ~/mas-golfs/ops/obs_client.py GetStreamStatus   # needs OBS running
bash ~/mas-golfs/ops/watchdog.sh   # one manual run; check watchdog.log
```

## What the watchdog never does

- It never restarts anything on a schedule (§4.4).
- It never changes scores, scenes (except the intermission cut before
  a restart), or outcomes — it restarts things; it never decides
  things (broadcast-stack.md §7.2).
- It never touches the 16GB MacBook Air, the 128GB MacBook Pro, or any
  machine other than the box it runs on.
- It never sends email, messages, or anything off the box. Alerts are
  local notifications + log lines.
