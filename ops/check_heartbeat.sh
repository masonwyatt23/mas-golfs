#!/bin/bash
# Mas Golfs — heartbeat checker (runbook §4.2).
#
# Runs every 5 min from launchd (com.masgolfs.heartbeat.plist). The
# watchdog touches $OPS_DIR/state/heartbeat on every run. If the stamp
# is older than 5 minutes the watchdog itself is down — the one failure
# that means "go look now" (runbook §5.3). This script restarts the
# watchdog agent and pages Mason.
#
# It never touches the broadcast stack itself: a dead watchdog does not
# mean a dead stream, and restarting the stream because the monitor
# died would be the wrong cure.

set -u

MAS_GOLFS_HOME="${MAS_GOLFS_HOME:-$HOME/mas-golfs}"
OPS_DIR="${MAS_GOLFS_OPS:-$MAS_GOLFS_HOME/ops}"
HEARTBEAT_FILE="$OPS_DIR/state/heartbeat"
LOG_FILE="$OPS_DIR/watchdog.log"
ALERT_LOG="$OPS_DIR/alerts.log"

STALE_SECONDS=300

log() {
    printf '%s [heartbeat] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" \
        >> "$LOG_FILE" 2>/dev/null || true
}

if [ ! -f "$HEARTBEAT_FILE" ]; then
    log "heartbeat file missing — watchdog has never run"
    exit 0
fi

last="$(cat "$HEARTBEAT_FILE" 2>/dev/null || echo 0)"
now="$(date +%s)"
age=$((now - last))

if [ "$age" -le "$STALE_SECONDS" ]; then
    exit 0
fi

# Watchdog is down. One alert per incident (30-min suppression, same
# rule as the watchdog's alert()).
suppress_file="$OPS_DIR/state/alert_watchdog_down"
if [ -f "$suppress_file" ]; then
    prev="$(cat "$suppress_file" 2>/dev/null || echo 0)"
    if [ $((now - prev)) -lt 1800 ]; then
        log "watchdog heartbeat stale ${age}s — alert suppressed (repeat within 30 min)"
        exit 0
    fi
fi
printf '%s\n' "$now" > "$suppress_file" 2>/dev/null || true

message="Watchdog itself is down — heartbeat stale ${age}s"
log "ALERT: $message"
printf '%s — ALERT [watchdog_down] %s\n' "$(date '+%Y-%m-%d %H:%M')" "$message" \
    >> "$OPS_DIR/ops-log.md" 2>/dev/null || true
printf '%s ALERT [watchdog_down] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$message" \
    >> "$ALERT_LOG" 2>/dev/null || true
if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$message\" with title \"Mas Golfs: watchdog_down\"" \
        >/dev/null 2>&1 || true
fi

# Restart the watchdog agent. kickstart -k kills the running instance
# (if any) and starts a fresh one; the watchdog's own lock prevents
# overlap.
if command -v launchctl >/dev/null 2>&1; then
    log "restarting watchdog agent (launchctl kickstart -k com.masgolfs.watchdog)"
    launchctl kickstart -k "gui/$(id -u)/com.masgolfs.watchdog" \
        >/dev/null 2>&1 || \
    launchctl kickstart -k com.masgolfs.watchdog >/dev/null 2>&1 || \
    log "launchctl kickstart failed — restart the watchdog agent by hand"
fi
exit 0
