#!/bin/bash
# Mas Golfs — weekly disk cleanup (runbook §4.2).
#
# Deletes OBS recordings and replay saves older than 7 days, rotates
# the NodeCG and watchdog logs, and reports how much space was freed.
# Run weekly from launchd (com.masgolfs.cleanup.plist, Sunday 03:00) and
# on demand by the watchdog when disk space falls below 20 GB free
# (check 7). Never deletes the current round's files or anything under
# 7 days old.
#
# Paths are overridable for testing:
#   MAS_GOLFS_RECORDINGS_DIR  default ~/mas-golfs/recordings
#   MAS_GOLFS_REPLAYS_DIR     default ~/mas-golfs/replays

set -u

MAS_GOLFS_HOME="${MAS_GOLFS_HOME:-$HOME/mas-golfs}"
OPS_DIR="${MAS_GOLFS_OPS:-$MAS_GOLFS_HOME/ops}"
RECORDINGS_DIR="${MAS_GOLFS_RECORDINGS_DIR:-$MAS_GOLFS_HOME/recordings}"
REPLAYS_DIR="${MAS_GOLFS_REPLAYS_DIR:-$MAS_GOLFS_HOME/replays}"

log() {
    printf '%s [cleanup] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

free_gb() {
    # df -k (1K blocks) works on macOS and GNU alike; -g is BSD-only.
    df -k / 2>/dev/null | awk 'NR==2 {print int($4 / 1048576)}'
}

before="$(free_gb)"
log "disk free before cleanup: ${before:-?} GB"

for dir in "$RECORDINGS_DIR" "$REPLAYS_DIR"; do
    if [ -d "$dir" ]; then
        count="$(find "$dir" -type f -mtime +7 2>/dev/null | wc -l | tr -d ' ')"
        find "$dir" -type f -mtime +7 -delete 2>/dev/null || true
        log "deleted $count files older than 7 days in $dir"
    else
        log "no such directory, skipping: $dir"
    fi
done

# Rotate logs: keep the last 4 weeks of watchdog/nodecg logs.
for f in "$OPS_DIR/watchdog.log" "$OPS_DIR/nodecg.log" "$OPS_DIR/web-server.log"; do
    if [ -f "$f" ] && [ "$(wc -c < "$f" 2>/dev/null | tr -d ' ')" -gt 10485760 ]; then
        mv "$f" "$f.1" 2>/dev/null || true
        touch "$f" 2>/dev/null || true
        log "rotated $f (over 10 MB)"
    fi
done

after="$(free_gb)"
log "disk free after cleanup: ${after:-?} GB"
if [ -n "$before" ] && [ -n "$after" ]; then
    log "freed $((after - before)) GB"
fi
exit 0
