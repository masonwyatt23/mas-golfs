#!/usr/bin/env bash
# Mas Golfs — on-box MLX verification pack.
#
# Runs on the 8GB MacBook Pro (Apple Silicon, confirmed Nov 12 2026) and
# proves the local-model stack from docs/local-models.md actually works
# on the real hardware before the broadcast depends on it:
#
#   1. check     mlx-lm installed (installs it if missing), model loads,
#                server answers on localhost:8080, smoke generation works
#   2. latency   20 real commentary prompts, P99 total < 4 s
#   3. audition  20 generated lines within the local-models §10 step-4 rules
#   4. soak      30 minutes with the model resident, median swap growth < 1 GB, max < 4.8 GB
#   5. think     zero-tolerance <think> grep over >= 100 generated lines
#   6. ab        blind A/B: same 50 events through Qwen3.5-4B and
#                Qwen3-4B-Instruct-2507, side by side for a human judge
#
# Usage:
#   ./verify.sh [check|latency|audition|soak|think|ab|merge-ab|all]
#   ./verify.sh all            # the full pack, in order (default)
#   SOAK_MINUTES=5 ./verify.sh soak     # short soak smoke run
#   MLX_VERIFY_KEEP_SERVER=1 ./verify.sh check   # leave server running
#
# Exit codes: 0 all requested checks passed; 1 a check failed;
# 2 wrong hardware (not Apple Silicon macOS) or unfixable prerequisite;
# 3 incomplete (e.g. think check without 100 generated lines yet).
#
# The runtime decision is settled (Mason, Nov 12 2026): plain mlx-lm,
# not oMLX. The Python helper is server-agnostic (any OpenAI-compatible
# endpoint via --base-url), but only the mlx-lm install/start steps
# below are supported here. oMLX stays an option only if multi-model
# serving is ever needed.
#
# Nothing here costs money: mlx-lm is free, the models are Apache 2.0
# open weights, and no paid API is ever called.
set -euo pipefail

PACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$PACK_DIR/.." && pwd)"
RESULTS_DIR="${MLX_VERIFY_RESULTS_DIR:-$PACK_DIR/results}"
VENV_DIR="${MLX_VERIFY_VENV:-$HOME/.masgolfs/mlx-venv}"
# Default interpreter for the offline steps (think, merge-ab).
# ensure_python() refines this to the venv and verifies mlx-lm for the
# server steps; think never needs the server, but it still needs a
# Python to run mlx_verify.py (caught 2026-11-13: `think` failed with
# "PY: unbound variable" because main() skipped ensure_python for it).
if [[ -x "$VENV_DIR/bin/python" ]]; then
    PY="$VENV_DIR/bin/python"
else
    PY="python3"
fi
MODEL="${MLX_VERIFY_MODEL:-mlx-community/Qwen3.5-4B-4bit}"
MODEL_B="${MLX_VERIFY_MODEL_B:-mlx-community/Qwen3-4B-Instruct-2507-4bit}"
PORT="${MLX_VERIFY_PORT:-8080}"
BASE_URL="http://localhost:${PORT}/v1"
SOAK_MINUTES="${SOAK_MINUTES:-30}"
SERVER_PID_FILE="$RESULTS_DIR/server.pid"

mkdir -p "$RESULTS_DIR"

log() { printf '[mlx-verify] %s\n' "$*"; }
fail() { printf '[mlx-verify] FAIL: %s\n' "$*" >&2; }

# --- 0. Platform gate (Apple Silicon macOS, nothing else) ----------------
gate() {
    local system machine
    system="$(uname -s)"
    machine="$(uname -m)"
    if [[ "$system" != "Darwin" ]]; then
        fail "MLX runs on macOS only; this machine is $system."
        fail "Run this pack on the 8GB MacBook Pro."
        return 2
    fi
    if [[ "$machine" != "arm64" ]]; then
        fail "MLX needs Apple Silicon (arm64); this machine is $machine."
        fail "An Intel Mac cannot run MLX — use the llama.cpp fallback in"
        fail "docs/local-models.md instead."
        return 2
    fi
    log "Platform OK: Darwin $machine (Apple Silicon)."
}

# --- Python / venv / mlx-lm ----------------------------------------------
ensure_python() {
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        PY="$VENV_DIR/bin/python"
    else
        PY="python3"
    fi
    if ! "$PY" -c "import mlx_lm" 2>/dev/null; then
        log "mlx-lm not installed — installing into $VENV_DIR ..."
        if [[ ! -x "$VENV_DIR/bin/python" ]]; then
            python3 -m venv "$VENV_DIR"
            PY="$VENV_DIR/bin/python"
        fi
        "$PY" -m pip install --upgrade pip -q
        "$PY" -m pip install mlx-lm
    fi
    if ! "$PY" -c "import mlx_lm" 2>/dev/null; then
        fail "mlx-lm still not importable after install. Check pip output above."
        return 2
    fi
    log "mlx-lm importable via $PY."
}

# --- Server lifecycle ------------------------------------------------------
server_is_up() {
    curl -fsS -m 2 "$BASE_URL/models" >/dev/null 2>&1
}

start_server() {
    local model="$1"
    if server_is_up; then
        log "A server is already answering on $BASE_URL — reusing it."
        return 0
    fi
    log "Starting mlx-lm server: model=$model port=$PORT ..."
    # Context cap (verified on the box 2026-11-13, mlx-lm 0.32.2):
    # --max-kv-size does NOT exist in the 0.32.x server (it lives only
    # in `mlx_lm generate`). The bound is enforced two ways instead:
    #   --prompt-cache-size 1  — one cached prompt prefix, not the
    #       default 10 (the maintainer's preferred direction: bound
    #       the cache count, since output degrades once a KV cap is
    #       hit). This is the multiplier that could accumulate memory
    #       across requests.
    #   --max-tokens 120       — server-level generation cap matching
    #       commentary/config.yaml. Requests are stateless single
    #       prompts (~200 tokens) + at most 120 generated tokens, so
    #       the active KV per request is ~320 tokens max.
    # Together these preserve the 2K context cap's intent (the
    # commentary prompts are ~300-500 tokens; 2,048 is generous).
    # Also note the invocation: `python -m mlx_lm server` (subcommand)
    # — the old `-m mlx_lm.server` form is deprecated in 0.32.x.
    nohup "$PY" -m mlx_lm server --model "$model" --port "$PORT" \
        --prompt-cache-size 1 --max-tokens 120 \
        >"$RESULTS_DIR/server.log" 2>&1 &
    echo $! >"$SERVER_PID_FILE"
    local waited=0
    while ! server_is_up; do
        sleep 5
        waited=$((waited + 5))
        if [[ $waited -ge 300 ]]; then
            fail "mlx-lm server did not answer within 300 s. See $RESULTS_DIR/server.log"
            return 1
        fi
        if ! kill -0 "$(cat "$SERVER_PID_FILE")" 2>/dev/null; then
            fail "mlx-lm server exited during startup. See $RESULTS_DIR/server.log"
            return 1
        fi
    done
    log "Server up on $BASE_URL (pid $(cat "$SERVER_PID_FILE"))."
}

stop_server() {
    if [[ "${MLX_VERIFY_KEEP_SERVER:-0}" == "1" ]]; then
        log "KEEP_SERVER=1 — leaving the server running."
        return 0
    fi
    if [[ -f "$SERVER_PID_FILE" ]]; then
        local pid
        pid="$(cat "$SERVER_PID_FILE")"
        if kill -0 "$pid" 2>/dev/null; then
            log "Stopping mlx-lm server (pid $pid)."
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$SERVER_PID_FILE"
    fi
}

server_pid() {
    [[ -f "$SERVER_PID_FILE" ]] && cat "$SERVER_PID_FILE" || echo ""
}

# --- Stack coverage (what the soak actually proves) ------------------------
# The 30-minute soak is only fully valid with the real broadcast stack
# running (qwen3-family §10: "boot the full stack"). Record what was
# present so a PASS is never overstated.
stack_coverage() {
    local parts=() missing=()
    for proc in OBS "Google Chrome" "Safari" "Node" "Docker"; do
        if pgrep -x "$proc" >/dev/null 2>&1 || pgrep -f "$proc" >/dev/null 2>&1; then
            parts+=("$proc")
        else
            missing+=("$proc")
        fi
    done
    # Kokoro has no stable process name to grep for; check its port instead.
    if curl -fsS -m 2 http://localhost:8880/v1/models >/dev/null 2>&1; then
        parts+=("Kokoro:8880")
    else
        missing+=("Kokoro:8880")
    fi
    if [[ ${#missing[@]} -eq 0 ]]; then
        log "SOAK-COVERAGE: FULL (OBS, browser, Node, Docker, Kokoro all present)."
    else
        log "SOAK-COVERAGE: PARTIAL — present: ${parts[*]:-none}; missing: ${missing[*]}."
        log "A partial-coverage soak still proves the model itself does not"
        log "swap; repeat with the full stack running for the §10 gate."
    fi
}

# --- Checks ------------------------------------------------------------------
run_check() {
    gate || return $?
    ensure_python || return $?
    start_server "$MODEL" || return $?
    # Smoke generation through the real pipeline path.
    # NOTE: --out-dir must come BEFORE the subcommand — it is a main-
    # parser flag, and argparse rejects it after `latency` (caught on
    # the box 2026-11-13: "unrecognized arguments: --out-dir ...").
    # NOTE: --timeout 180 — this is the first generation after a fresh
    # model load, so it pays the cold-start cost (Metal kernel compile
    # + prefill; the server log showed prefill alone at ~5s and the
    # 30s default timed out). Warm generations are measured by the
    # latency check, so the long timeout here does not hide slowness.
    "$PY" "$PACK_DIR/mlx_verify.py" --base-url "$BASE_URL" --model "$MODEL" \
        --timeout 180 --out-dir "$RESULTS_DIR/smoke" latency --n 1 >/dev/null
    log "Smoke generation OK: 1 real prompt through $MODEL."
    log "CHECK PASS."
}

# Diagnostic: dump the raw server response for one prompt (raw SSE lines
# + raw non-streaming JSON). Added 2026-11-13 after the smoke reported
# "streamed an empty completion" with prefill complete and zero deltas —
# the cause is only visible in the raw response.
run_probe() {
    start_server "$MODEL" || return $?
    "$PY" "$PACK_DIR/probe_raw.py" --base-url "$BASE_URL" --model "$MODEL"
}

run_latency() {
    start_server "$MODEL" || return $?
    "$PY" "$PACK_DIR/mlx_verify.py" --base-url "$BASE_URL" --model "$MODEL" \
        --out-dir "$RESULTS_DIR" latency --n 20
}

run_audition() {
    start_server "$MODEL" || return $?
    "$PY" "$PACK_DIR/mlx_verify.py" --base-url "$BASE_URL" --model "$MODEL" \
        --out-dir "$RESULTS_DIR" audition --n 20
}

run_soak() {
    start_server "$MODEL" || return $?
    stack_coverage
    local pid
    pid="$(server_pid)"
    log "Soak: ${SOAK_MINUTES} minutes, sampling swap every 60 s, warm-up"
    log "generation every 90 s. Median swap growth after the model loads must stay under 1 GB; max swap under 4.8 GB."
    "$PY" "$PACK_DIR/mlx_verify.py" --base-url "$BASE_URL" --model "$MODEL" \
        --out-dir "$RESULTS_DIR" soak --minutes "$SOAK_MINUTES" \
        --server-pid "${pid:-0}" --interval 60 --warmup-every 90
}

run_think() {
    # Scans every generated line so far: latency (20) + audition (20) +
    # A/B (100). The check needs >= 100 lines to be meaningful.
    local files=()
    for f in "$RESULTS_DIR/latency.json" "$RESULTS_DIR/audition.json" \
             "$RESULTS_DIR/ab-results.json"; do
        [[ -f "$f" ]] && files+=("$f")
    done
    if [[ ${#files[@]} -eq 0 ]]; then
        fail "No generation results yet — run latency/audition/ab first."
        return 3
    fi
    "$PY" "$PACK_DIR/mlx_verify.py" --out-dir "$RESULTS_DIR" think "${files[@]}"
}

# Merge the two latency runs (ab-a, ab-b) into the blind A/B files.
# The labels are randomized by one coin flip for the whole file; the
# key is sealed separately. No re-generation happens here — this is
# offline, so it can be re-run on its own (`./verify.sh merge-ab`)
# if a full `ab` run was interrupted after the generations finished.
# argv: 1 = results dir, 2 = model A, 3 = model B.
merge_ab() {
    PYTHONPATH="$PACK_DIR" "$PY" - "$RESULTS_DIR" "$MODEL" "$MODEL_B" <<'PYEOF'
import json, os, random, sys
from mlx_verify import write_ab_side_by_side, load_events
def rows(path):
    return json.load(open(path))["rows"]
a = rows(os.path.join(sys.argv[1], "ab-a", "latency.json"))
b = rows(os.path.join(sys.argv[1], "ab-b", "latency.json"))
events = load_events(os.path.join(os.path.dirname(sys.argv[1]), "events.json"))
flipped = random.Random().random() < 0.5
out_rows = []
for ev, ra, rb in zip(events[:50], a, b):
    pair = {"A": ra, "B": rb} if not flipped else {"A": rb, "B": ra}
    out_rows.append({"event_id": ev["id"], "event_type": ev["event_type"],
                     "speaker": ev["speaker"], "user_prompt": ev["user_prompt"],
                     "A": {"text": pair["A"]["text"], "total_s": pair["A"]["total_s"],
                           "chars": pair["A"]["chars"]},
                     "B": {"text": pair["B"]["text"], "total_s": pair["B"]["total_s"],
                           "chars": pair["B"]["chars"]}})
results = {"check": "ab", "n": len(out_rows), "rows": out_rows}
# ra came from model A (argv[2]), rb from model B (argv[3]).
key = {"A": sys.argv[3] if flipped else sys.argv[2],
       "B": sys.argv[2] if flipped else sys.argv[3],
       "flipped": flipped, "n": len(out_rows)}
json.dump(results, open(os.path.join(sys.argv[1], "ab-results.json"), "w"), indent=2)
write_ab_side_by_side(results, os.path.join(sys.argv[1], "ab-side-by-side.md"))
json.dump(key, open(os.path.join(sys.argv[1], "ab-key.json"), "w"), indent=2)
print(f"A/B complete: {len(out_rows)} events -> {sys.argv[1]}/ab-side-by-side.md")
print(f"Key sealed in {sys.argv[1]}/ab-key.json — do not open it until scoring is done.")
PYEOF
}

run_ab() {
    # Two sequential server runs: model A, then model B. Each load takes
    # a minute or two; 100 generations at ~1–3 s each is ~5 minutes.
    log "A/B: 50 events through $MODEL, then 50 through $MODEL_B."
    start_server "$MODEL" || return $?
    # NOTE: the latency subcommand exits non-zero when its verdict is
    # FAIL, and this script runs under `set -e`. An A/B is a comparison,
    # not a gate — both models' rows are data even if one side's p99
    # fails (caught 2026-11-13: model B's first generation took 10.3 s,
    # a cold-start spike after a fresh load, which failed its p99 and
    # aborted the script before the merge, losing the whole A/B).
    # So a FAIL verdict must not abort the merge: `|| true` here.
    "$PY" "$PACK_DIR/mlx_verify.py" --base-url "$BASE_URL" --model "$MODEL" \
        --out-dir "$RESULTS_DIR/ab-a" latency --n 50 >/dev/null || true
    log "Model A done (50 generations). Switching servers..."
    stop_server
    start_server "$MODEL_B" || return $?
    "$PY" "$PACK_DIR/mlx_verify.py" --base-url "$BASE_URL" --model "$MODEL_B" \
        --out-dir "$RESULTS_DIR/ab-b" latency --n 50 >/dev/null || true
    stop_server
    merge_ab
}

# --- Main ----------------------------------------------------------------------
main() {
    local cmd="${1:-all}"
    trap stop_server EXIT
    # Every command except `think` needs the Apple Silicon Mac and mlx-lm.
    # (`think` is offline: it only greps files already generated.)
    if [[ "$cmd" != "think" ]]; then
        gate || exit $?
        ensure_python || exit $?
    fi
    case "$cmd" in
        check)    run_check ;;
        probe)    run_probe ;;
        latency)  run_latency ;;
        audition) run_audition ;;
        soak)     run_soak ;;
        think)    run_think ;;
        ab)       run_ab ;;
        merge-ab) merge_ab ;;
        all)
            run_check || exit $?
            run_latency || exit $?
            run_audition || exit $?
            run_soak || exit $?
            run_ab || exit $?
            run_think || exit $?
            log "ALL CHECKS DONE. Results in $RESULTS_DIR."
            log "Remaining human step: score $RESULTS_DIR/ab-side-by-side.md"
            log "(booth test, commentary-prompts.md §11), then open ab-key.json."
            ;;
        *)
            fail "Unknown command: $cmd"
            echo "Usage: $0 [check|latency|audition|soak|think|ab|merge-ab|all]" >&2
            exit 2
            ;;
    esac
}

main "$@"
