#!/bin/bash
# Mas Golfs watchdog — the 24/7 auto-recovery script.
#
# Runs every 30 s from launchd (com.masgolfs.watchdog.plist) on the
# 8GB MacBook Pro broadcast box. Performs the checks in
# docs/deployment-runbook.md §4.1 in priority order, acts on failure in
# the §4.3 restart order (web server -> NodeCG -> Kokoro -> OBS), logs
# every action to watchdog.log, and touches a heartbeat file every run
# so the heartbeat checker (§4.2) can tell the watchdog itself is alive.
#
# NO SCHEDULED RESTART (runbook §4.4): this script never restarts
# anything on a clock. Restarts happen only on update, fault, or
# watchdog-detected drift. The watchdog's job is to prove the stack is
# healthy, not to restart it on a schedule.
#
# The 16GB MacBook Air is off-limits entirely and never appears in this
# code as a machine. There is no spare; recovery is repair/restart of
# this box or the cloud fallback (runbook §8.5).
#
# Free tools only, macOS built-ins only (curl, nc, sysctl, df, ps,
# osascript, launchctl, docker, node, python3). Every macOS-only command
# is guarded with `command -v` so a missing tool degrades to a logged
# skip instead of a crash.
#
# Environment overrides (all optional):
#   MAS_GOLFS_HOME      repo checkout, default ~/mas-golfs
#   MAS_GOLFS_OPS       ops dir, default $MAS_GOLFS_HOME/ops
#   MAS_GOLFS_WEB_URL   web build, default http://localhost:8080
#   MAS_GOLFS_NODECG_URL NodeCG graphics, default
#                       http://localhost:9090/bundles/mas-golfs/graphics/scorebug
#   MAS_GOLFS_BUS_HOST / MAS_GOLFS_BUS_PORT  event bus, default 127.0.0.1:4456
#   MAS_GOLFS_KOKORO_URL Kokoro TTS, default http://localhost:8880
#   MAS_GOLFS_KOKORO_CONTAINER  docker container, default kokoro
#   MAS_GOLFS_NODECG_HOME  NodeCG server dir, default ~/nodecg
#   MAS_GOLFS_BUS_RESTART_CMD   command that restarts the event-bus
#                       server; empty means "log + alert only" (the bus
#                       server is a separate component — see ops/README.md)
#   MAS_GOLFS_INTERMISSION_SCENE  OBS scene for planned breaks,
#                       default INTERMISSION (best effort, non-fatal)

set -u
umask 022

MAS_GOLFS_HOME="${MAS_GOLFS_HOME:-$HOME/mas-golfs}"
OPS_DIR="${MAS_GOLFS_OPS:-$MAS_GOLFS_HOME/ops}"
LOG_FILE="$OPS_DIR/watchdog.log"
ALERT_LOG="$OPS_DIR/alerts.log"
OPS_LOG="$OPS_DIR/ops-log.md"
HEARTBEAT_FILE="$OPS_DIR/state/heartbeat"
STATE_DIR="$OPS_DIR/state"
LOCK_DIR="$STATE_DIR/watchdog.lock"

WEB_URL="${MAS_GOLFS_WEB_URL:-http://localhost:8080}"
NODECG_URL="${MAS_GOLFS_NODECG_URL:-http://localhost:9090/bundles/mas-golfs/graphics/scorebug}"
BUS_HOST="${MAS_GOLFS_BUS_HOST:-127.0.0.1}"
BUS_PORT="${MAS_GOLFS_BUS_PORT:-4456}"
KOKORO_URL="${MAS_GOLFS_KOKORO_URL:-http://localhost:8880}"
KOKORO_CONTAINER="${MAS_GOLFS_KOKORO_CONTAINER:-kokoro}"
NODECG_HOME="${MAS_GOLFS_NODECG_HOME:-$HOME/nodecg}"
BUS_RESTART_CMD="${MAS_GOLFS_BUS_RESTART_CMD:-}"
INTERMISSION_SCENE="${MAS_GOLFS_INTERMISSION_SCENE:-INTERMISSION}"

# Thresholds (runbook §4.1 / §5.3 / §0)
DISK_FREE_MIN_GB=20          # check 7: disk must stay above 20 GB free
SWAP_ALERT_MB=2048           # check 6b: sustained swap above this is an
                             # upgrade-trigger warning, not just a log line
MEMORY_GROWTH_PCT=10         # check 6: >10% growth over the round baseline
MEMORY_RESTART_PCT=25        # check 6: >25% growth means the leak is back;
                             # restart the stack and file it as a bug
NET_UPLOAD_MIN_MBPS=5        # check 8: upload must stay above 5 Mbps
ALERT_SUPPRESS_SECONDS=1800  # one alert per incident per 30 minutes

mkdir -p "$STATE_DIR" 2>/dev/null || true

# ---------------------------------------------------------------- logging

log() {
    # log LEVEL message — timestamped, to watchdog.log and stdout.
    local level="$1"; shift
    local line
    line="$(date '+%Y-%m-%d %H:%M:%S') [$level] $*"
    printf '%s\n' "$line" >> "$LOG_FILE" 2>/dev/null || true
    printf '%s\n' "$line"
}

ops_log() {
    # One line per incident in ops-log.md (runbook §6.4).
    printf '%s — %s\n' "$(date '+%Y-%m-%d %H:%M')" "$*" >> "$OPS_LOG" 2>/dev/null || true
}

# ---------------------------------------------------------------- alerting

# alert KEY message — one alert per incident per 30 min; quiet hours
# 21:30-09:00 local, except stream-down (KEY=stream_down), which always
# pages. "Paging" on this box is a local notification + alerts.log entry;
# there is no external send. See ops/README.md.
alert() {
    local key="$1"; shift
    local message="$*"
    local now hour_min suppress_file last
    now="$(date +%s)"
    suppress_file="$STATE_DIR/alert_$key"
    if [ -f "$suppress_file" ]; then
        last="$(cat "$suppress_file" 2>/dev/null || echo 0)"
        if [ $((now - last)) -lt "$ALERT_SUPPRESS_SECONDS" ]; then
            log INFO "alert suppressed (repeat within 30 min): $key — $message"
            return 0
        fi
    fi
    hour_min="$(date +%H%M)"
    if [ "$key" != "stream_down" ]; then
        if [ "$hour_min" -ge 2130 ] || [ "$hour_min" -lt 0900 ]; then
            log INFO "alert held for quiet hours (21:30-09:00): $key — $message"
            printf '%s\n' "$now" > "$suppress_file" 2>/dev/null || true
            return 0
        fi
    fi
    printf '%s\n' "$now" > "$suppress_file" 2>/dev/null || true
    printf '%s ALERT [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$key" "$message" \
        >> "$ALERT_LOG" 2>/dev/null || true
    log ALERT "[$key] $message"
    ops_log "ALERT [$key] $message"
    if command -v osascript >/dev/null 2>&1; then
        osascript -e "display notification \"$message\" with title \"Mas Golfs: $key\"" \
            >/dev/null 2>&1 || true
    fi
}

# ---------------------------------------------------------------- locking

# Single-instance lock: a second watchdog run exits quietly instead of
# stacking up if a previous run is still working (e.g. a slow
# networkQuality test in the 15-minute slot).
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# ---------------------------------------------------------------- helpers

# due INTERVAL_SECONDS NAME — true when NAME has not run within the
# interval (state files under $STATE_DIR). The watchdog itself runs
# every 30 s; checks with longer intervals are gated through this.
due() {
    local interval="$1"
    local name="$2"
    local stamp_file="$STATE_DIR/last_$name"
    local now last
    now="$(date +%s)"
    if [ -f "$stamp_file" ]; then
        last="$(cat "$stamp_file" 2>/dev/null || echo 0)"
        [ $((now - last)) -ge "$interval" ]
    else
        return 0
    fi
}

mark_done() {
    date +%s > "$STATE_DIR/last_$1" 2>/dev/null || true
}

http_ok() {
    # http_ok URL [timeout_s] — true on HTTP 200.
    local url="$1" timeout="${2:-5}"
    [ "$(curl -fsS -o /dev/null -w '%{http_code}' -m "$timeout" "$url" 2>/dev/null)" = "200" ]
}

wait_for_url() {
    # wait_for_url URL TIMEOUT_S — poll until 200 or timeout.
    local url="$1" timeout="$2" waited=0
    while [ "$waited" -lt "$timeout" ]; do
        if http_ok "$url" 3; then
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

port_open() {
    # port_open HOST PORT — true if something is listening.
    local host="$1" port="$2"
    if command -v nc >/dev/null 2>&1; then
        nc -z -w 2 "$host" "$port" 2>/dev/null
    else
        python3 -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('$host', $port)) == 0 else 1)" 2>/dev/null
    fi
}

obs_request() {
    # obs_request TYPE [JSON-DATA] — one obs-websocket call, prints the
    # JSON response. Exit 0 on success.
    python3 "$OPS_DIR/obs_client.py" "$@"
}

# ---------------------------------------------------------------- stack control
# Start/stop primitives. Every start waits for its health check before
# the caller moves on (runbook §4.3: health checks between steps, never
# fixed sleeps alone).

web_server_pid() {
    pgrep -f "http.server 8080" 2>/dev/null | head -1
}

start_web_server() {
    if [ -n "$(web_server_pid)" ]; then
        log INFO "web server already running (pid $(web_server_pid))"
    else
        log INFO "starting web server (python3 -m http.server 8080 in $MAS_GOLFS_HOME)"
        (cd "$MAS_GOLFS_HOME" && nohup python3 -m http.server 8080 \
            >> "$OPS_DIR/web-server.log" 2>&1 &)
    fi
    if wait_for_url "$WEB_URL" 30; then
        log OK "web server healthy: $WEB_URL"
        return 0
    fi
    log FAIL "web server did not answer $WEB_URL within 30 s"
    return 1
}

stop_web_server() {
    local pid
    pid="$(web_server_pid)"
    if [ -n "$pid" ]; then
        log INFO "stopping web server (pid $pid)"
        kill "$pid" 2>/dev/null || true
        sleep 2
        kill -9 "$pid" 2>/dev/null || true
    fi
}

nodecg_pid() {
    pgrep -f "node.*server.js" 2>/dev/null | head -1
}

start_nodecg() {
    if [ -n "$(nodecg_pid)" ]; then
        log INFO "NodeCG already running (pid $(nodecg_pid))"
    else
        if [ -f "$NODECG_HOME/server.js" ]; then
            log INFO "starting NodeCG in $NODECG_HOME"
            (cd "$NODECG_HOME" && nohup node server.js \
                >> "$OPS_DIR/nodecg.log" 2>&1 &)
        else
            log FAIL "NodeCG server.js not found in $NODECG_HOME — cannot start NodeCG"
            return 1
        fi
    fi
    if wait_for_url "$NODECG_URL" 30; then
        log OK "NodeCG healthy: $NODECG_URL"
        return 0
    fi
    log FAIL "NodeCG did not answer $NODECG_URL within 30 s"
    return 1
}

stop_nodecg() {
    local pid
    pid="$(nodecg_pid)"
    if [ -n "$pid" ]; then
        log INFO "stopping NodeCG (pid $pid)"
        kill "$pid" 2>/dev/null || true
        sleep 2
        kill -9 "$pid" 2>/dev/null || true
    fi
}

start_kokoro() {
    if ! command -v docker >/dev/null 2>&1; then
        log FAIL "docker not found — cannot start Kokoro"
        return 1
    fi
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$KOKORO_CONTAINER"; then
        log INFO "Kokoro container already running"
    else
        log INFO "starting Kokoro container $KOKORO_CONTAINER"
        docker start "$KOKORO_CONTAINER" >/dev/null 2>&1 || {
            log FAIL "docker start $KOKORO_CONTAINER failed"
            return 1
        }
    fi
    if wait_for_url "$KOKORO_URL/v1/audio/voices" 30; then
        log OK "Kokoro healthy: $KOKORO_URL"
        return 0
    fi
    log FAIL "Kokoro did not answer $KOKORO_URL within 30 s"
    return 1
}

stop_kokoro() {
    if command -v docker >/dev/null 2>&1; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$KOKORO_CONTAINER"; then
            log INFO "stopping Kokoro container $KOKORO_CONTAINER"
            docker stop "$KOKORO_CONTAINER" >/dev/null 2>&1 || true
        fi
    fi
}

obs_running() {
    pgrep -x OBS >/dev/null 2>&1
}

start_obs() {
    if obs_running; then
        log INFO "OBS already running"
    else
        log INFO "starting OBS"
        open -a OBS >/dev/null 2>&1 || {
            log FAIL "could not launch OBS (open -a OBS failed)"
            return 1
        }
    fi
    # Wait for obs-websocket, then start streaming last (runbook §4.3).
    local waited=0
    while [ "$waited" -lt 60 ]; do
        if port_open 127.0.0.1 4455; then
            break
        fi
        sleep 2
        waited=$((waited + 2))
    done
    if ! port_open 127.0.0.1 4455; then
        log FAIL "obs-websocket (4455) did not answer within 60 s"
        return 1
    fi
    if obs_request StartStream >/dev/null 2>&1; then
        log OK "OBS streaming (StartStream via obs-websocket)"
        return 0
    fi
    log FAIL "OBS is up but StartStream failed"
    return 1
}

stop_obs() {
    if obs_running; then
        log INFO "stopping OBS"
        obs_request StopStream >/dev/null 2>&1 || true
        sleep 2
        pkill -x OBS 2>/dev/null || true
        sleep 3
        pkill -9 -x OBS 2>/dev/null || true
    fi
}

show_intermission() {
    # Best effort: cut to the intermission scene before a restart
    # (runbook §4.5). Non-fatal if the scene does not exist yet.
    obs_request SetCurrentProgramScene "{\"sceneName\": \"$INTERMISSION_SCENE\"}" \
        >/dev/null 2>&1 || true
}

# restart_stack REASON — full ordered restart (runbook §4.3):
# stop OBS -> NodeCG -> Kokoro -> web server, then start web server ->
# NodeCG -> Kokoro -> OBS, with a health check between each start.
restart_stack() {
    local reason="$1"
    log WARN "ordered restart: $reason"
    ops_log "Ordered restart: $reason"
    show_intermission
    stop_obs
    stop_nodecg
    stop_kokoro
    stop_web_server
    sleep 2
    start_web_server || { log FAIL "restart aborted: web server failed"; return 1; }
    start_nodecg   || { log FAIL "restart aborted: NodeCG failed"; return 1; }
    start_kokoro   || { log FAIL "restart aborted: Kokoro failed"; return 1; }
    start_obs      || { log FAIL "restart aborted: OBS failed"; return 1; }
    log OK "ordered restart complete: $reason"
    ops_log "Ordered restart complete: $reason"
    return 0
}

# ---------------------------------------------------------------- checks
# Run in priority order (runbook §4.1). Each check returns 0 when the
# thing it watches is healthy. Longer-interval checks are gated with
# due() — the watchdog itself runs every 30 s.

# Check 1 — OBS streaming (every 30 s). Failure means the stream is down.
check_obs_streaming() {
    local status active
    if ! port_open 127.0.0.1 4455; then
        if obs_running; then
            log WARN "check 1: OBS is running but obs-websocket (4455) is not answering"
        else
            log WARN "check 1: OBS is not running"
        fi
        log INFO "check 1 action: restarting OBS"
        stop_obs
        if start_obs; then
            ops_log "OBS restarted (obs-websocket unresponsive)"
            return 0
        fi
        alert stream_down "OBS could not be restarted — stream is down"
        return 1
    fi
    status="$(obs_request GetStreamStatus 2>/dev/null || echo '')"
    active="$(printf '%s' "$status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("outputActive", False))' 2>/dev/null || echo False)"
    if [ "$active" = "True" ]; then
        return 0
    fi
    log WARN "check 1: obs-websocket answers but the stream is not active"
    if obs_request StartStream >/dev/null 2>&1; then
        log OK "check 1: streaming restarted via obs-websocket"
        ops_log "Streaming restarted via obs-websocket"
        return 0
    fi
    log WARN "check 1 action: StartStream failed — ordered restart"
    if restart_stack "OBS streaming could not be restarted"; then
        return 0
    fi
    alert stream_down "OBS streaming could not be restarted — stream is down"
    return 1
}

# Check 2 — web build rendering (every 60 s). The page must answer 200
# and contain the show title. (A true frame-advance check needs the
# build's perf HUD endpoint — see ops/README.md. HTTP + title is the
# proxy until then.)
check_web_build() {
    if ! due 60 web_build; then
        return 0
    fi
    mark_done web_build
    local body
    body="$(curl -fsS -m 5 "$WEB_URL" 2>/dev/null || echo '')"
    if [ -n "$body" ] && printf '%s' "$body" | grep -qi "mas golfs"; then
        return 0
    fi
    log WARN "check 2: web build not rendering at $WEB_URL"
    stop_web_server
    if start_web_server; then
        ops_log "Web server restarted (build not rendering)"
        return 0
    fi
    log WARN "check 2 action: web server restart failed — ordered restart"
    if restart_stack "web build not rendering after restart"; then
        return 0
    fi
    alert stream_down "Web build is down and the stack could not be restarted"
    return 1
}

# Check 3 — event bus alive (every 60 s). The bus must be listening on
# 4456, and if the bus server writes a last-event timestamp file
# ($STATE_DIR/last_event, epoch seconds), it must be < 60 s old. If the
# file does not exist the port check alone applies — see ops/README.md.
check_event_bus() {
    if ! due 60 event_bus; then
        return 0
    fi
    mark_done event_bus
    if ! port_open "$BUS_HOST" "$BUS_PORT"; then
        log WARN "check 3: event bus not listening on $BUS_HOST:$BUS_PORT"
        if [ -n "$BUS_RESTART_CMD" ]; then
            log INFO "check 3 action: running BUS_RESTART_CMD"
            eval "$BUS_RESTART_CMD" >/dev/null 2>&1 || true
            sleep 3
            if port_open "$BUS_HOST" "$BUS_PORT"; then
                log OK "check 3: event bus back after restart"
                ops_log "Event bus restarted"
                return 0
            fi
        fi
        alert event_bus_silent "Event bus silent — sim stalled (bus not listening on $BUS_PORT)"
        return 1
    fi
    local last_event_file="$STATE_DIR/last_event"
    if [ -f "$last_event_file" ]; then
        local last_event now
        last_event="$(cat "$last_event_file" 2>/dev/null || echo 0)"
        now="$(date +%s)"
        if [ $((now - last_event)) -ge 60 ]; then
            log WARN "check 3: last event $((now - last_event)) s ago (limit 60 s)"
            alert event_bus_silent "Event bus silent > 60 s — sim stalled"
            return 1
        fi
    fi
    return 0
}

# Check 4 — NodeCG serving graphics (every 60 s).
check_nodecg() {
    if ! due 60 nodecg; then
        return 0
    fi
    mark_done nodecg
    if http_ok "$NODECG_URL" 5; then
        return 0
    fi
    log WARN "check 4: NodeCG not serving graphics at $NODECG_URL"
    stop_nodecg
    if start_nodecg; then
        ops_log "NodeCG restarted (graphics not serving)"
        return 0
    fi
    log WARN "check 4 action: NodeCG restart failed — ordered restart"
    if restart_stack "NodeCG graphics not serving after restart"; then
        return 0
    fi
    alert overlays_down "NodeCG graphics are down and the stack could not be restarted"
    return 1
}

# Check 5 — Kokoro responding (every 5 min). One short test synthesis
# must return audio within 5 s.
check_kokoro() {
    if ! due 300 kokoro; then
        return 0
    fi
    mark_done kokoro
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -X POST \
        "$KOKORO_URL/v1/audio/speech" \
        -H 'Content-Type: application/json' \
        -d '{"model":"kokoro","voice":"am_michael","input":"Watchdog test.","response_format":"mp3"}' \
        2>/dev/null)"
    code="${code:-000}"
    if [ "$code" = "200" ]; then
        return 0
    fi
    log WARN "check 5: Kokoro test synthesis failed (HTTP $code)"
    if command -v docker >/dev/null 2>&1; then
        log INFO "check 5 action: docker restart $KOKORO_CONTAINER"
        docker restart "$KOKORO_CONTAINER" >/dev/null 2>&1 || true
        sleep 5
        if wait_for_url "$KOKORO_URL/v1/audio/voices" 30; then
            log OK "check 5: Kokoro back after container restart"
            ops_log "Kokoro restarted (test synthesis failed)"
            return 0
        fi
    fi
    log WARN "check 5: Kokoro still down — commentary is silent, stream continues"
    alert kokoro_down "Kokoro TTS is down — commentary is silent (stream continues)"
    return 1
}

# Check 6 — GPU memory flat (every 15 min). Apple Silicon exposes no
# direct GPU-memory counter to the shell, so this uses the browser
# process memory (the WebGL renderer lives in it) as the proxy, plus
# system memory pressure when available. Baseline = the lowest browser
# RSS seen in the last 24 h, stored in state. Growth > 10% over the
# baseline is the leak warning (runbook §4.1, P0-1); > 25% restarts
# the stack and files it as a bug.
check_gpu_memory() {
    if ! due 900 gpu_memory; then
        return 0
    fi
    mark_done gpu_memory
    local browser_rss baseline_file baseline growth_pct chrome_pids
    chrome_pids="$(pgrep -x 'Google Chrome' 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
    if [ -z "$chrome_pids" ]; then
        log INFO "check 6: no Chrome process found — skipping GPU-memory proxy"
        return 0
    fi
    browser_rss="$(ps -ax -o rss= -c -p "$chrome_pids" 2>/dev/null | awk '{s+=$1} END {print s+0}')"
    if [ -z "$browser_rss" ] || [ "$browser_rss" = "0" ]; then
        log INFO "check 6: no Chrome process found — skipping GPU-memory proxy"
        return 0
    fi
    baseline_file="$STATE_DIR/browser_rss_baseline"
    if [ -f "$baseline_file" ]; then
        baseline="$(cat "$baseline_file" 2>/dev/null || echo "$browser_rss")"
    else
        baseline="$browser_rss"
    fi
    # Baseline ratchets down only: the lowest RSS in 24 h is the floor.
    if [ "$browser_rss" -lt "$baseline" ]; then
        printf '%s\n' "$browser_rss" > "$baseline_file" 2>/dev/null || true
        baseline="$browser_rss"
    fi
    if [ "$baseline" -gt 0 ]; then
        growth_pct=$(( (browser_rss - baseline) * 100 / baseline ))
    else
        growth_pct=0
    fi
    log INFO "check 6: browser RSS ${browser_rss} KB, baseline ${baseline} KB, growth ${growth_pct}%"
    if [ "$growth_pct" -ge "$MEMORY_RESTART_PCT" ]; then
        log WARN "check 6: browser memory up ${growth_pct}% over baseline — the leak may be back"
        ops_log "GPU/browser memory up ${growth_pct}% over baseline — ordered restart (possible leak)"
        if restart_stack "browser memory up ${growth_pct}% over baseline"; then
            return 0
        fi
        alert gpu_memory "GPU/browser memory climbing > ${MEMORY_RESTART_PCT}% and the stack could not be restarted"
        return 1
    fi
    if [ "$growth_pct" -ge "$MEMORY_GROWTH_PCT" ]; then
        alert gpu_memory "GPU/browser memory climbing ${growth_pct}% over a round (limit ${MEMORY_GROWTH_PCT}%) — the leak may be back"
        return 1
    fi
    return 0
}

# Check 6b — swap pressure flat (every 15 min). On 8GB, swap growth is
# the early warning (runbook §0). Swap Used must not be growing; above
# 2 GB sustained is the first upgrade trigger.
check_swap() {
    if ! due 900 swap; then
        return 0
    fi
    mark_done swap
    if ! command -v sysctl >/dev/null 2>&1; then
        return 0
    fi
    local swap_line swap_used_mb swap_file prev
    swap_line="$(sysctl vm.swapusage 2>/dev/null || echo '')"
    # vm.swapusage: "total = 1024.00M  used = 123.00M  free = 901.00M  ..."
    swap_used_mb="$(printf '%s' "$swap_line" | sed -n 's/.*used = \([0-9.]*\)M.*/\1/p')"
    if [ -z "$swap_used_mb" ]; then
        return 0
    fi
    swap_used_mb="${swap_used_mb%.*}"
    swap_file="$STATE_DIR/swap_used_mb"
    prev="$(cat "$swap_file" 2>/dev/null || echo 0)"
    printf '%s\n' "$swap_used_mb" > "$swap_file" 2>/dev/null || true
    log INFO "check 6b: swap used ${swap_used_mb} MB (previous sample ${prev} MB)"
    if [ "$swap_used_mb" -ge "$SWAP_ALERT_MB" ]; then
        alert swap_pressure "Swap used ${swap_used_mb} MB (>= ${SWAP_ALERT_MB} MB) — the 8GB box is out of headroom; sustained swap is the first upgrade trigger"
        return 1
    fi
    if [ "$swap_used_mb" -gt 0 ] && [ "$swap_used_mb" -gt "$prev" ]; then
        log WARN "check 6b: swap growing (${prev} -> ${swap_used_mb} MB)"
        return 0
    fi
    return 0
}

# Check 7 — disk above 20 GB free (every 15 min). Below the floor, run
# the cleanup (recordings/replays older than 7 days) and re-check.
check_disk() {
    if ! due 900 disk; then
        return 0
    fi
    mark_done disk
    local free_gb
    # df -k (1K blocks) works on macOS and GNU alike; -g is BSD-only.
    free_gb="$(df -k / 2>/dev/null | awk 'NR==2 {print int($4 / 1048576)}')"
    if [ -z "$free_gb" ]; then
        return 0
    fi
    log INFO "check 7: disk free ${free_gb} GB (floor ${DISK_FREE_MIN_GB} GB)"
    if [ "$free_gb" -ge "$DISK_FREE_MIN_GB" ]; then
        return 0
    fi
    log WARN "check 7: disk below ${DISK_FREE_MIN_GB} GB free — running cleanup"
    if [ -x "$OPS_DIR/cleanup.sh" ]; then
        "$OPS_DIR/cleanup.sh" >> "$LOG_FILE" 2>&1 || true
    fi
    free_gb="$(df -k / 2>/dev/null | awk 'NR==2 {print int($4 / 1048576)}')"
    if [ -n "$free_gb" ] && [ "$free_gb" -ge "$DISK_FREE_MIN_GB" ]; then
        log OK "check 7: disk back above floor after cleanup (${free_gb} GB)"
        ops_log "Disk cleanup recovered space (${free_gb} GB free)"
        return 0
    fi
    alert disk_low "Disk free ${free_gb:-?} GB (floor ${DISK_FREE_MIN_GB} GB) even after cleanup — recordings will fill the disk"
    return 1
}

# Check 8 — network up (every 60 s). Fast check each run: default
# gateway reachable + an HTTPS HEAD to the Restream ingest host. Every
# 15 min, run macOS networkQuality and require upload > 5 Mbps.
check_network() {
    if ! due 60 network; then
        return 0
    fi
    mark_done network
    local gateway
    gateway="$(route -n get default 2>/dev/null | awk '/gateway:/ {print $2}' | head -1)"
    if [ -n "$gateway" ]; then
        if ! ping -c 1 -t 2 "$gateway" >/dev/null 2>&1; then
            log WARN "check 8: default gateway $gateway unreachable"
            alert network_down "Network down — default gateway unreachable"
            return 1
        fi
    fi
    # Any HTTP response (even a 404) proves the network path works; only
    # a total failure (curl code 000) means unreachable. Restream's
    # ingest host answers 404 to a bare HEAD — that still counts as up.
    # A second probe guards against one host being down while the
    # network itself is fine.
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -I https://ingest.restream.io 2>/dev/null)"
    if [ -z "$code" ] || [ "$code" = "000" ]; then
        code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -I https://www.google.com 2>/dev/null)"
    fi
    if [ -z "$code" ] || [ "$code" = "000" ]; then
        log WARN "check 8: Restream ingest and fallback host both unreachable"
        alert network_down "Network down — Restream ingest unreachable"
        return 1
    fi
    if due 900 network_quality; then
        mark_done network_quality
        if command -v networkQuality >/dev/null 2>&1; then
            local nq upload
            nq="$(networkQuality -s 2>/dev/null || echo '')"
            upload="$(printf '%s' "$nq" | grep -i "Upload capacity" | grep -o '[0-9.]*' | head -1)"
            if [ -n "$upload" ]; then
                upload="${upload%.*}"
                log INFO "check 8: upload capacity ${upload} Mbps (floor ${NET_UPLOAD_MIN_MBPS} Mbps)"
                if [ "$upload" -lt "$NET_UPLOAD_MIN_MBPS" ]; then
                    alert network_slow "Upload capacity ${upload} Mbps (floor ${NET_UPLOAD_MIN_MBPS} Mbps) — the stream is likely dropping frames"
                    return 1
                fi
            fi
        fi
    fi
    return 0
}

# ---------------------------------------------------------------- main

# Touch the heartbeat every run — even a run that finds failures. The
# heartbeat means "the watchdog is alive", not "the stream is healthy".
date +%s > "$HEARTBEAT_FILE" 2>/dev/null || true

failures=0
check_obs_streaming || failures=$((failures + 1))
check_web_build     || failures=$((failures + 1))
check_event_bus     || failures=$((failures + 1))
check_nodecg        || failures=$((failures + 1))
check_kokoro        || failures=$((failures + 1))
check_gpu_memory    || failures=$((failures + 1))
check_swap          || failures=$((failures + 1))
check_disk          || failures=$((failures + 1))
check_network       || failures=$((failures + 1))

if [ "$failures" -eq 0 ]; then
    log INFO "watchdog run clean"
fi

# Heartbeat again at the end, so a run that dies mid-way still leaves a
# fresh-enough stamp only if it got this far.
date +%s > "$HEARTBEAT_FILE" 2>/dev/null || true
exit 0
