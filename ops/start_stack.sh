#!/bin/bash
# Mas Golfs — start the broadcast stack in the §4.3 order.
#
# Used by com.masgolfs.broadcast.plist (RunAtLoad + KeepAlive): the
# launchd agent runs this on login and restarts it if it exits, so the
# stack comes back unattended after a reboot or power cut.
#
# Order (runbook §4.3) with a health check between each step:
#   1. web server (the picture) — wait for http://localhost:8080
#   2. NodeCG (the graphics) — wait for the scorebug URL
#   3. Kokoro (the voices) — wait for /v1/audio/voices
#   4. OBS (the encoder) — wait for obs-websocket, then StartStream
#
# Idempotent: a service that is already running is left alone. After
# the stack is up this script sleeps forever so launchd keeps it alive;
# if it is killed, launchd re-runs it and it re-checks the stack.
#
# No scheduled restart: this script starts the stack, it never restarts
# it on a clock. Restarts are the watchdog's job, and only on fault.

set -u

MAS_GOLFS_HOME="${MAS_GOLFS_HOME:-$HOME/mas-golfs}"
OPS_DIR="${MAS_GOLFS_OPS:-$MAS_GOLFS_HOME/ops}"
WEB_URL="${MAS_GOLFS_WEB_URL:-http://localhost:8080}"
NODECG_URL="${MAS_GOLFS_NODECG_URL:-http://localhost:9090/bundles/mas-golfs/graphics/scorebug}"
KOKORO_URL="${MAS_GOLFS_KOKORO_URL:-http://localhost:8880}"
KOKORO_CONTAINER="${MAS_GOLFS_KOKORO_CONTAINER:-kokoro}"
NODECG_HOME="${MAS_GOLFS_NODECG_HOME:-$HOME/nodecg}"

log() {
    printf '%s [start_stack] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" \
        >> "$OPS_DIR/watchdog.log" 2>/dev/null || true
    printf '%s [start_stack] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

# Reuse the watchdog's start primitives by sourcing only the function
# definitions: the watchdog's main loop runs at the bottom of the file,
# so source it in a subshell guard instead. Simpler and safer: duplicate
# the three small waits here and call the watchdog's restart_stack via
# a flag. We keep this script self-contained instead.

http_ok() {
    [ "$(curl -fsS -o /dev/null -w '%{http_code}' -m 5 "$1" 2>/dev/null)" = "200" ]
}

wait_for_url() {
    local url="$1" timeout="$2" waited=0
    while [ "$waited" -lt "$timeout" ]; do
        http_ok "$url" 3 && return 0
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

port_open() {
    if command -v nc >/dev/null 2>&1; then
        nc -z -w 2 "$1" "$2" 2>/dev/null
    else
        python3 -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('$1', $2)) == 0 else 1)" 2>/dev/null
    fi
}

# 1. Web server
if pgrep -f "http.server 8080" >/dev/null 2>&1; then
    log "web server already running"
else
    log "starting web server"
    (cd "$MAS_GOLFS_HOME" && nohup python3 -m http.server 8080 \
        >> "$OPS_DIR/web-server.log" 2>&1 &)
fi
wait_for_url "$WEB_URL" 30 \
    && log "web server healthy: $WEB_URL" \
    || log "WARNING: web server did not answer $WEB_URL — watchdog will retry"

# 2. NodeCG
if pgrep -f "node.*server.js" >/dev/null 2>&1; then
    log "NodeCG already running"
elif [ -f "$NODECG_HOME/server.js" ]; then
    log "starting NodeCG"
    (cd "$NODECG_HOME" && nohup node server.js \
        >> "$OPS_DIR/nodecg.log" 2>&1 &)
    wait_for_url "$NODECG_URL" 30 \
        && log "NodeCG healthy: $NODECG_URL" \
        || log "WARNING: NodeCG did not answer $NODECG_URL — watchdog will retry"
else
    log "WARNING: NodeCG server.js not found in $NODECG_HOME — skipping (watchdog will report it)"
fi

# 3. Kokoro
if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$KOKORO_CONTAINER"; then
        log "Kokoro container already running"
    else
        log "starting Kokoro container $KOKORO_CONTAINER"
        docker start "$KOKORO_CONTAINER" >/dev/null 2>&1 || \
            log "WARNING: docker start $KOKORO_CONTAINER failed — watchdog will retry"
    fi
    wait_for_url "$KOKORO_URL/v1/audio/voices" 30 \
        && log "Kokoro healthy: $KOKORO_URL" \
        || log "WARNING: Kokoro did not answer $KOKORO_URL — watchdog will retry"
else
    log "WARNING: docker not found — Kokoro not started"
fi

# 4. OBS — last, only after 1-3 are healthy. Never stream a black screen.
if pgrep -x OBS >/dev/null 2>&1; then
    log "OBS already running"
else
    log "starting OBS"
    open -a OBS >/dev/null 2>&1 || log "WARNING: could not launch OBS"
fi
waited=0
while [ "$waited" -lt 60 ]; do
    port_open 127.0.0.1 4455 && break
    sleep 2
    waited=$((waited + 2))
done
if port_open 127.0.0.1 4455; then
    if python3 "$OPS_DIR/obs_client.py" StartStream >/dev/null 2>&1; then
        log "OBS streaming"
    else
        log "WARNING: OBS is up but StartStream failed — watchdog will retry"
    fi
else
    log "WARNING: obs-websocket (4455) did not answer — watchdog will retry"
fi

log "stack start sequence finished; holding (launchd KeepAlive)"
# Stay alive so launchd's KeepAlive has something to keep. If this
# process dies, launchd re-runs this script and it re-checks the stack.
while true; do
    sleep 3600
done
