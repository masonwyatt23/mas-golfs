# Mas Golfs — Event Bus

The spine of the broadcast (``docs/broadcast-stack.md`` §1): a local
WebSocket server on ``localhost:4456`` that carries every typed sim
event to every consumer — NodeCG graphics, the commentary service, the
director, the ambient engine — plus a ``round_state`` snapshot that is
the single source of truth for all graphics.

**Stdlib only.** No third-party dependencies: the RFC 6455 handshake
and framing are hand-rolled (``server.py`` / ``client.py``), the same
way ``commentary/bus.py`` does it on the client side. Python 3.10+.

## Run it

```bash
# From the repo root:
python -m bus                     # 127.0.0.1:4456
python -m bus --port 4456 --log-level DEBUG
python -m bus --state-file none   # disable the last-event file
```

Environment (all optional, CLI flags win):

| Variable | Default | Meaning |
|---|---|---|
| `MAS_GOLFS_BUS_HOST` | `127.0.0.1` | bind host (server binds localhost only) |
| `MAS_GOLFS_BUS_PORT` | `4456` | bind port |
| `MAS_GOLFS_STATE_FILE` | see below | last-event file path; `none` disables it |
| `MAS_GOLFS_HOME` | `~/mas-golfs` | repo home; `ops/state/last_event` lives under it |

The last-event file defaults to `<repo>/ops/state/last_event` (this
package lives in the repo checkout, so that resolves correctly both on
a dev machine and on the broadcast box at `~/mas-golfs`).

## How the sim feeds it

The sim engine is the single publisher. It publishes by opening a
WebSocket connection to the bus and sending one JSON object per text
message — the same socket subscribers read from. Two mechanisms, in
order of preference:

**1. Live publisher (the broadcast path).** The sim — or a driver
around it — connects with ``bus.client.BusPublisher`` and publishes
each event as it is emitted:

```python
from bus.client import BusPublisher

with BusPublisher("ws://localhost:4456") as pub:
    for event in engine.play_round().events:  # or as they happen
        pub.publish(event)
```

The engine currently runs rounds synchronously and collects events in
``RoundResult.events``; a live in-engine publish hook (publish inside
``EventEmitter.emit``) is the natural next step and needs no bus
change — any client that sends a JSON event is a publisher.

**2. JSONL feed (the file/pipe path — works today).** Dump events one
JSON object per line and pipe them in:

```bash
python -m bus.feed events.jsonl --delay 0.5
cat events.jsonl | python -m bus.feed --delay 0.5
python -m bus.feed events.jsonl --loop --delay 0.5  # endless replay
```

**3. Demo (smoke test).** Plays sim rounds and publishes them live:

```bash
python -m bus.demo --rounds 1 --delay 0.5   # fast decisions
python -m bus.demo --rounds 1 --mc 120 --delay 0.5  # real Monte Carlo
```

## What the bus does to events

The sim and the broadcast consumers speak two dialects
(``translate.py`` is the Rosetta stone):

| Sim event (`sim/events.py`) | Broadcast event(s) (`broadcast-stack.md` §1.2) |
|---|---|
| `shot_decision` | `decision` (plan, before the swing) |
| `shot_result` | `strike` → `apex` → `landing` (one sim event fans out to three — the director needs the phases separately) |
| `hole_complete` | `hole_end` |
| `round_complete` | `round_end` |
| `putt_result`, `fifty_nine_watch`, `milestone`, `round_start`, `hole_start` | same type, `data` reshaped per the broadcast spec |
| `conditions_change` | passed through as its own type (consumers ignore it) |
| already-enveloped (`event` + `data`) | passed through unchanged |

The bus assigns its own monotonically increasing ``seq`` to every
envelope it emits; the sim's original ``seq``/``event_id`` are kept
inside ``data`` as ``sim_seq`` / ``sim_event_id``.

**Round state.** The bus maintains the §1.3 snapshot (``translate.py:
RoundState``) and updates it from the events flowing through:
`round_start` resets the card, `hole_start` sets the current hole,
`hole_end` appends to the scorecard and recomputes thru / score-to-par
/ stats / streaks, `round_end` applies the new handicap and the one
fix, `fifty_nine_watch` stores the latest pace state. Two additive
fields beyond §1.3: ``fifty_nine_watch`` and ``one_fix``.

**Reconnect/resync.** Every client gets the current ``round_state``
snapshot the moment it connects, and again on
``{"type": "request_round_state"}``. ``{"type": "subscribe", ...}``
(NodeCG's connect message) is accepted and ignored — every connection
already receives everything. A publisher never receives its own echo.

**Keepalive.** The server answers WebSocket ping frames with pong and
sends a ping of its own after 30 s idle. Malformed JSON and messages
with no type are dropped with a warning; the connection stays alive.

## Watchdog contract (`ops/watchdog.sh` check 3)

On **every published event** the server atomically writes the epoch
seconds of that event to the last-event file (temp file + rename, so
the watchdog never reads a torn value). Check 3 requires the file to
be < 60 s old; if the sim stalls for 60 s, the watchdog pages
`event_bus_silent` — the file is only ever written for real events,
never faked by a timer. If the file does not exist (bus up, no events
yet), the check degrades to the port check alone.

### `MAS_GOLFS_BUS_RESTART_CMD`

The watchdog restarts the bus only when this is set (otherwise a dead
bus is log + page only). Set it in the environment the watchdog runs
in — the launchd agent (`ops/com.masgolfs.watchdog.plist`) or the
shell that starts the stack — to a command that (re)starts this
server in the background, for example:

```bash
export MAS_GOLFS_BUS_RESTART_CMD='cd ~/mas-golfs && nohup python3 -m bus >> ops/bus.log 2>&1 &'
```

That is the same shape as the web-server start in
`ops/start_stack.sh`. The command must return quickly (it runs in the
background via `nohup ... &`); the watchdog waits 3 s and re-checks
the port. If the bus is started by launchd instead
(`com.masgolfs.broadcast.plist`), set the restart command to reload
that job, e.g. `launchctl kickstart -k gui/$(id -u)/com.masgolfs.bus`
— whichever supervisor owns the bus process.

## Tests

```bash
python -m unittest discover -s bus/tests -v
```

Covers the live server on an ephemeral port (handshake accept/reject,
broadcast fan-out with no self-echo, `shot_result` → three-event
fan-out, snapshot-on-connect and on request, last-event file update,
malformed-message survival, ping/pong frames, subscribe no-op) plus
the pure translation and round-state functions.

## Files

| File | What it is |
|---|---|
| `server.py` | The WebSocket server (handshake, framing, fan-out, state file) |
| `translate.py` | Sim ↔ broadcast translation + `RoundState` snapshot |
| `client.py` | `BusPublisher` — the stdlib WS client publishers use |
| `feed.py` | `python -m bus.feed` — JSONL file/pipe publisher |
| `demo.py` | `python -m bus.demo` — play sim rounds, publish live |
| `__main__.py` | `python -m bus` — server CLI |
| `tests/test_bus.py` | Stdlib unittest suite |
| `requirements.txt` | Empty on purpose — stdlib only |
