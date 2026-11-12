#!/bin/bash
# Mas Golfs — install the ops automation on the 8GB MacBook Pro.
#
# What it does:
#   1. Checks the machine is macOS and the required tools exist.
#   2. Copies the ops/ scripts into ~/mas-golfs/ops (or uses them in
#      place when run from the repo checkout) and makes them executable.
#   3. Installs the four launchd agents into ~/Library/LaunchAgents,
#      substituting the real home path into the plists.
#   4. Loads the agents and prints a verification checklist.
#
# Run it on the broadcast box as the masgolfs user:
#   ~/mas-golfs/ops/install.sh
#
# It never touches the 16GB MacBook Air (off-limits — grandpa's writing
# archive) and never installs anything on any other machine. It installs
# no paid software: everything is a macOS built-in or already-free tool
# (OBS, NodeCG, Kokoro, Docker).
#
# Idempotent: safe to run again after an update — it re-copies the
# scripts, re-substitutes the plists, and reloads the agents.

set -u

REPO_OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
MAS_GOLFS_HOME="${MAS_GOLFS_HOME:-$HOME/mas-golfs}"
NODECG_HOME="${MAS_GOLFS_NODECG_HOME:-$HOME/nodecg}"
OPS_DIR="$MAS_GOLFS_HOME/ops"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

PASS=0
FAIL=0

ok()   { PASS=$((PASS + 1)); printf '  [ok] %s\n' "$*"; }
warn() { printf '  [!!] %s\n' "$*"; }
fail() { FAIL=$((FAIL + 1)); printf '  [FAIL] %s\n' "$*"; }

echo "Mas Golfs ops install"
echo "  repo ops dir: $REPO_OPS_DIR"
echo "  install dir:  $OPS_DIR"
echo

# --- 1. Machine checks -------------------------------------------------
echo "1. Machine checks"
if [ "$(uname -s)" != "Darwin" ]; then
    fail "not macOS (uname: $(uname -s)) — this automation is macOS-only"
else
    ok "macOS ($(sw_vers -productVersion 2>/dev/null || echo unknown))"
fi

for tool in python3 curl nc sysctl df ps pgrep launchctl; do
    if command -v "$tool" >/dev/null 2>&1; then
        ok "tool present: $tool"
    else
        fail "tool missing: $tool"
    fi
done

# Optional but expected on the broadcast box — warn, don't fail.
for tool in docker node; do
    if command -v "$tool" >/dev/null 2>&1; then
        ok "tool present: $tool"
    else
        warn "tool missing (install before go-live): $tool"
    fi
done

if [ -d "/Applications/OBS.app" ]; then
    ok "OBS Studio installed"
else
    warn "OBS Studio not found in /Applications — install it before go-live"
fi

if [ -f "$MAS_GOLFS_HOME/index.html" ]; then
    ok "web build present at $MAS_GOLFS_HOME/index.html"
else
    warn "web build not found at $MAS_GOLFS_HOME/index.html — clone the repo first (runbook §2 Step 1)"
fi

if [ -f "$NODECG_HOME/server.js" ] || [ -f "$HOME/nodecg/server.js" ]; then
    ok "NodeCG server.js found"
else
    warn "NodeCG server.js not found — set MAS_GOLFS_NODECG_HOME or install NodeCG (runbook §2 Step 3)"
fi

if [ "$FAIL" -gt 0 ]; then
    echo
    echo "Required checks failed ($FAIL). Fix them and re-run."
    exit 1
fi

# --- 2. Copy scripts into place ---------------------------------------
echo
echo "2. Installing scripts"
mkdir -p "$OPS_DIR/state" "$LAUNCH_AGENTS_DIR"

for f in watchdog.sh start_stack.sh check_heartbeat.sh cleanup.sh obs_client.py; do
    if [ -f "$REPO_OPS_DIR/$f" ]; then
        cp "$REPO_OPS_DIR/$f" "$OPS_DIR/$f"
        chmod +x "$OPS_DIR/$f"
        ok "installed $OPS_DIR/$f"
    else
        fail "missing from repo ops dir: $f"
    fi
done

for f in com.masgolfs.broadcast.plist com.masgolfs.watchdog.plist \
         com.masgolfs.heartbeat.plist com.masgolfs.cleanup.plist; do
    if [ -f "$REPO_OPS_DIR/$f" ]; then
        cp "$REPO_OPS_DIR/$f" "$OPS_DIR/$f"
        ok "copied $f (reference copy in ops/)"
    else
        fail "missing from repo ops dir: $f"
    fi
done

if [ "$FAIL" -gt 0 ]; then
    echo "Missing files ($FAIL). Aborting before touching launchd."
    exit 1
fi

# --- 3. Install launchd agents ----------------------------------------
echo
echo "3. Installing launchd agents (substituting $MAS_GOLFS_HOME)"
for f in com.masgolfs.broadcast.plist com.masgolfs.watchdog.plist \
         com.masgolfs.heartbeat.plist com.masgolfs.cleanup.plist; do
    dest="$LAUNCH_AGENTS_DIR/$f"
    # Unload the old version first (ignore errors: it may not be loaded).
    launchctl bootout "gui/$(id -u)/$f" >/dev/null 2>&1 || \
        launchctl unload "$dest" >/dev/null 2>&1 || true
    # Substitute the real home path for the __MAS_GOLFS_HOME__ placeholder.
    sed "s|__MAS_GOLFS_HOME__|$MAS_GOLFS_HOME|g" "$REPO_OPS_DIR/$f" > "$dest"
    if grep -q "__MAS_GOLFS_HOME__" "$dest"; then
        fail "placeholder left unsubstituted in $dest"
    else
        ok "installed $dest"
    fi
done

if [ "$FAIL" -gt 0 ]; then
    echo "Plist install failed ($FAIL). Aborting before loading agents."
    exit 1
fi

# --- 4. Syntax checks ---------------------------------------------------
echo
echo "4. Syntax checks"
for f in watchdog.sh start_stack.sh check_heartbeat.sh cleanup.sh; do
    if bash -n "$OPS_DIR/$f"; then
        ok "bash -n $f"
    else
        fail "bash -n $f"
    fi
done
if python3 -m py_compile "$OPS_DIR/obs_client.py"; then
    ok "python3 -m py_compile obs_client.py"
else
    fail "python3 -m py_compile obs_client.py"
fi

if [ "$FAIL" -gt 0 ]; then
    echo "Syntax checks failed ($FAIL). Agents NOT loaded."
    exit 1
fi

# --- 5. Load agents -----------------------------------------------------
echo
echo "5. Loading agents"
for label in com.masgolfs.broadcast com.masgolfs.watchdog \
             com.masgolfs.heartbeat com.masgolfs.cleanup; do
    if launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_DIR/$label.plist" 2>/dev/null; then
        ok "loaded $label"
    elif launchctl load "$LAUNCH_AGENTS_DIR/$label.plist" 2>/dev/null; then
        ok "loaded $label (legacy load)"
    else
        fail "could not load $label — run: launchctl bootstrap gui/$(id -u) $LAUNCH_AGENTS_DIR/$label.plist"
    fi
done

sleep 3

# --- 6. Verification checklist -----------------------------------------
echo
echo "6. Verification checklist — run these and confirm each line"
echo "   (the agents need a minute to settle; the stack starts on login)"
echo
cat <<EOF
  [ ] Agents loaded:
        launchctl list | grep masgolfs
      Expect 4 lines: broadcast, watchdog, heartbeat, cleanup.
  [ ] Watchdog is running and touching its heartbeat:
        tail -5 $OPS_DIR/watchdog.log
        stat -f '%Sm' -t '%H:%M:%S' $OPS_DIR/state/heartbeat
      The heartbeat time should be within the last 30 seconds.
  [ ] Stack is up (give it ~60 s after login):
        curl -s -o /dev/null -w 'web build: %{http_code}\n' http://localhost:8080
        curl -s -o /dev/null -w 'NodeCG:    %{http_code}\n' http://localhost:9090/bundles/mas-golfs/graphics/scorebug
        curl -s -o /dev/null -w 'Kokoro:    %{http_code}\n' http://localhost:8880/v1/audio/voices
        python3 $OPS_DIR/obs_client.py GetStreamStatus
      Expect 200 / 200 / 200 and outputActive: true.
  [ ] A forced failure recovers (test one at a time, see ops/README.md):
        kill the web server -> watchdog restarts it within ~60 s
        stop OBS streaming  -> watchdog restarts it within ~30 s
  [ ] No scheduled restart exists:
        launchctl list | grep -i restart   # should print nothing
        grep -ri "daily restart" $OPS_DIR  # should print nothing
EOF

echo
if [ "$FAIL" -gt 0 ]; then
    echo "Install finished with $FAIL failed step(s) — see above."
    exit 1
fi
echo "Install complete: $PASS checks passed. The stream starts on login."
echo "Next: run the go-live checklist (docs/qa-plan.md §6), then the"
echo "12-hour overnight soak before the 7-day go-live gate."
