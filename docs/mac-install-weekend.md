# Mas Golfs — Mac Install Weekend Runbook

**Box:** the 8GB MacBook Pro (Apple Silicon — confirmed Nov 12, 2026). Plugged in, lid open, always running.
**Weekend:** one Saturday + one Sunday. Mason runs it, Ash guides.
**Deliverable by Sunday night:** the full stack installed and verified on the real box, the 12-hour soak (Soak B) passed overnight, the 24-hour model soak running toward its Sunday-evening verdict, and the 7-day soak (Soak C) started. **Launch is not this weekend** — Soak C is the go-live gate, and it needs 7 days.
**Do not touch:** the 16GB MacBook Air (Grandpa's poems — permanently off-limits, not even as failover) and the 128GB MacBook Pro (Mason's workhorse — Phantom and real work only).

## How to use this doc

- Work top to bottom. Each step has: the exact command, what "done" looks like (exact expected output or number), how long it takes, and what to do if it fails. Do not skip ahead — each layer is tested before the next is added.
- **Copy-paste rule:** every command block is written for the box, logged in as the `masgolfs` user unless it says `sudo` or "Mason's account". The repo lives at `~/mas-golfs` on the box (not `~/workspace/mas-golfs-repo`, which is the Linux VM path).
- **Log everything.** Open one running log for the weekend: `~/mas-golfs/qa/logs/install-weekend-2026-11-14.log` — paste every command and its output, or `script` the session. The soak logs live in `qa/logs/` and the calibration report in `qa/reports/`; the repo has no `qa/` directory yet, so Step 2.1 creates it.
- **If a step fails twice, stop and fix it — do not push on.** A failed step that gets skipped becomes a failed soak at 3am. The failure playbook for each step is written in; if it does not cover what you see, that is the moment to call Ash, not to improvise.
- **No purchases, no upgrades, no external sends.** Everything in this runbook is free tiers and open source. The only money-adjacent step is entering stream keys you already have.

## Status snapshot — what is already green from the VM vs what only the box can prove

Written Nov 13, 2026, from the repo state that morning. The readiness audit (`docs/reviews/readiness-2026-11-13.md`, ~05:00 UTC Nov 13) said **NOT READY — 0 of 18 gates green**, but several of its reds have landed since. This table is the honest version; §7 re-marks the full §6 go-live checklist against it.

**Evening update (Nov 13, ~4:30pm ET — supersedes the guided-Terminal path below):** the Mac is now drivable autonomously. Mason loaded a LaunchAgent runner (`~/Library/LaunchAgents/ai.ashlr.muse-runner.plist`, runs `~/.masgolfs/runner/run.sh` every 20s); Ash writes a command file and the runner executes it, output in `~/.masgolfs/runner/output.log`. Long jobs must be started via `~/.masgolfs/runner/daemonize.py` (Python setsid — plain `nohup &` dies when launchd reaps the job's process group). **Godot 4.7.2 is installed** (brew --cask) and the Hole 12 v1 scene loads clean headless. **MLX verify gates on the box: CHECK, LATENCY, AUDITION (20/20), THINK, and the blind A/B all PASS** (Qwen3.5-4B-4bit kept; challenger rejected); the 30-min soak is running with the new growth-based gate (< 1 GB swap growth). The 59 Watch prompt fix is in (the 18th-hole requirement is computed in code, not derived by the model). So the weekend's execution path is the runner, not Mason pasting commands — Mason only steps in for the phone eye test and the stream-key entries.

| Area | Already green from this VM (repo state, Nov 13) | Only the box can prove |
|---|---|---|
| Sim suite | `semi` crash fixed; full suite green, **210 tests** (Nov 13, pushed `d2fd34e0`); fast suite 193 tests in ~10 s (`python -m sim.run_tests`). Learning loop (41 tests), Dunmore (18 tests), twins (40/40), putting solver v2 (30 tests), pins rotation tests all in repo. Flight-model retune landed: driver carry 262.6 yd drawn mean / 264.6 pure vs 268 target. | Tier A (200-round) / Tier B (2,000-round) calibration harness per QA plan v1.1 — never run on any machine yet. The old 10,000-round gate is **deferred**, not in flight (see §0.1). |
| Coins | Engine built, 36/36 tests pass | §5 payout/anti-abuse checks on a live test economy; NodeCG/web wiring + persistence not built — launch-with or descope is Mason's call |
| Commentary | Made-putt crash fixed; harness 6/6 green; 34/34 commentary tests | Real MLX server on 8GB silicon, real Kokoro audio, Ollama failover, 24-hour soak — none of this has ever run on the box |
| Bus / NodeCG | Live sim→bus publish hook built; integration harness 6/6 green (NodeCG test_04 flaky ~50%, not root-caused) | Live ws handshake against the real bus on the box; graphics updating from real events |
| Web build | Clean-screen rebuild + mobile/character rebuild landed on the artifact | Frame rate, heap, and the 3-round soak on the real 8GB box; repo `index.html` is v10-era and stale until Ash freezes + exports the build (Step 4.5) |
| MLX verify pack | `mlx-verify/events.json` regenerated to v3 (Hole 12 = 172 yd, zero "164 yards" left) | Every gate in the pack — model load, latency P99, 30-min soak with swap 0, `<think>` grep, blind A/B — has never run on real silicon |
| Ops | `install.sh` + failure tests written | Whether `install.sh` actually installs and the checks actually pass on macOS |

**Known stale bits in the repo (do not "fix" them mid-weekend — note them and keep going):**
- `sim/constants.py` now reads the v3 numbers 76.1/142 and 7,602 yd (fixed Nov 13, verified in code; full suite green, 210 tests, pushed `d2fd34e0` Nov 13).
- **Box RAM confirmed 8GB (Nov 13, ~1:06pm ET — Mason ran `sysctl` in Terminal: hw.memsize = 8GB, 8 cores, Chip "Apple M3", macOS 26.5 build 25F5068a, Python 3.13.1).** The "8GB" label was right; the Mac15,3-ships-18GB+ suspicion is resolved. The 8GB budget stands: Godot ~6.75GB total / 7.0GB hard cap, Qwen3.5-4B stays the commentary default, 8B does not fit alongside the stack. No re-measurement needed in Step 1. SSH to the box is blocked (tunnel approval never landed, Nov 13 ~1:02pm ET); the fallback is guided Terminal — Mason pastes, Ash reads results.
- `sim/README.md:74` is wrong (same stale numbers).
- `mlx-verify/README.md` line 21 says `mlx-audit.sh` where it means `mlx-verify.sh`.
- The audit's "bus is Node.js ws" line is stale: the bus is Python stdlib, and it writes `ops/state/last_event` on every event.

## §0. Before Saturday — pre-weekend gates

These must be true before the box work starts. If any is red, the weekend still runs, but the soak certifies a stack that is not ready to launch — say so in the log.

| # | Gate | Status Nov 13 | If red |
|---|---|---|---|
| 0.1 | **Sim calibration gate decision.** QA plan v1.1 (pushed `0739c4d8`, Nov 13) **decides it**: the 10,000-round / <5-min gate is infeasible in Python (~24 s/round vs <30 ms needed) and is **deferred** until a vectorized/compiled engine exists; replaced by Tier A (200 rounds per change, 60-min target on the box) and Tier B (2,000 rounds nightly). The retune landed the same day: driver carry 262.6 yd drawn mean / 264.6 pure vs 268 target, pushed `d2fd34e0`. | **Decided Nov 13 — see QA plan v1.1.** Tier A/B harness still never run. | Run the weekend anyway, but the 12-hour soak is a *stack* soak, not a *calibration* soak. Do not claim GL-01 green until the Tier A/B harness runs and passes. |
| 0.2 | **Web build frozen.** Ash freezes the `autonomous-golf-world` artifact and exports it to the repo so `~/mas-golfs/index.html` is the current build. | Repo `index.html` is v10-era, stale | Step 4.5 verifies the export. If the export has not landed, stop at Step 4.5 and do not start the soak on a stale build. |
| 0.3 | **Accounts + keys in hand.** YouTube channel + stream key, Twitch channel + stream key, Restream account (free tier) + ingest URL + stream key. | Mason to confirm | No keys = Steps 5.2–5.3 cannot run. Do everything else, then do 5.2–5.3 when the keys exist. |
| 0.4 | **Downloads queued.** OBS Studio (Apple Silicon build, obsproject.com), Node.js LTS (nodejs.org), Docker Desktop for Mac (docker.com), Python 3.12+ (python.org or Homebrew). | — | Download on Mason's account first if the box's Wi-Fi is slow; install as `masgolfs` where the installer allows. |
| 0.5 | **The box is out, plugged in, lid open, on Wi-Fi.** | Mason's call Nov 13 — get it out tonight | If the box is not out, §1 is the whole Saturday morning. |

**What to have on the desk:** the 8GB MBP + its charger, a hard surface or laptop stand (vents unobstructed, room under ~26°C / 79°F), an Ethernet cable if the router is in reach (preferred — see Step 1.6), Mason's phone (for the launch-day phone check later, and for watching the test stream), and the admin password for the box.

---

## §1. Box prep — Saturday morning

Do all of this on the 8GB MacBook Pro. There is no second machine to repeat it on.

### Step 1.1 — Place the box and plug it in

| | |
|---|---|
| **Commands** | None — physical. |
| **Do** | Put the MBP on a hard surface or a stand with airflow underneath. Vents and exhaust unobstructed — never on fabric, never in a closed drawer or cabinet, never with anything stacked on it. Plug the charger in. **Lid open** (recommended; see deployment-runbook §1.2 — lid-closed clamshell needs an external display + keyboard/mouse and a 10-minute test). Display brightness at minimum. |
| **Done looks like** | Charger LED / menu-bar battery icon shows charging; lid open; you can see the screen. |
| **Time** | 5 min. |
| **If it fails** | Charger not recognised: try the other USB-C port, then a different cable. If the battery is dead, charge 15 min before powering on. |

### Step 1.2 — macOS updates off, power settings on, FileVault off

| | |
|---|---|
| **Commands** | In Terminal (admin password required once): |
| | ```bash
# Never sleep, on charger or battery
sudo pmset -a sleep 0
sudo pmset -a displaysleep 0
sudo pmset -a disksleep 0
# Restart automatically after a power failure
sudo pmset -a autorestart 1
# Never power-nap / wake for network access
sudo pmset -a powernap 0
sudo pmset -a womp 0
# Verify
pmset -g
``` |
| **Done looks like** | `pmset -g` shows `sleep 0`, `displaysleep 0`, `disksleep 0`, `autorestart 1`, `powernap 0`, `womp 0`. |
| **Also do (GUI)** | System Settings → General → Software Update: turn **off** "Install macOS updates" automatic install, and turn **off** "Install app updates from the App Store" automatic install. Updates are applied by hand on Sunday (§6), never by the machine at 3am. System Settings → Lock Screen → "Require password after screen saver begins or display is turned off" → **Never** (broadcast box only — it holds no personal data). |
| **FileVault** | **Turn FileVault OFF on the broadcast box** (System Settings → Privacy & Security → FileVault → Turn Off). This is deliberate, not a mistake: no FileVault unlock prompt can be answered by a watchdog, so with FileVault on the box cannot self-recover after a power cut. The box holds no personal data — OBS, NodeCG, the web build, Kokoro, Restream credentials in the Keychain, and the ops log, nothing else. |
| **Time** | 10 min (plus the FileVault decryption time if it was on — let it finish in the background). |
| **If it fails** | `pmset` asks for a password and rejects it: you are not an admin on this user — log into Mason's account and run the `sudo` lines there. If Software Update offers a macOS update, **do not install it now** — that is the Sunday step (§6). |

### Step 1.3 — Dedicated `masgolfs` user, auto-login, remote access

| | |
|---|---|
| **Commands** | GUI + one Terminal check. |
| **Do** | 1. System Settings → Users & Groups → Add User → **Standard** user, full name `masgolfs`, account name `masgolfs`. Log out of Mason's account, log in as `masgolfs` for the rest of the weekend. 2. System Settings → General → Login Items → enable **automatic login** for `masgolfs`. 3. System Settings → General → Sharing → turn on **Remote Login** (SSH) and **Screen Sharing** — key-only, no password logins. Add Mason's public key to `~/.ssh/authorized_keys` on the box (see below). 4. Install Tailscale on the box (tailscale.com/download, free tier) and sign in — this is the remote-access path when the box is not on the home LAN. |
| **SSH key (from Mason's 128GB MBP, one time)** | ```bash
# If Mason has no key yet:
ssh-keygen -t ed25519 -C "mason-128mbp"
# Copy the public key to the box (type the masgolfs password once):
ssh-copy-id masgolfs@<box-hostname-or-ip>
# From then on, key-only:
ssh masgolfs@<box-hostname-or-ip>
``` |
| **Done looks like** | `ssh masgolfs@<box-hostname-or-ip>` logs in with no password prompt. Auto-login is on for `masgolfs`. The box has no personal email, no iCloud, no personal files. |
| **Time** | 15 min. |
| **If it fails** | `ssh-copy-id` not found on macOS: copy the key by hand — `cat ~/.ssh/id_ed25519.pub`, paste it into `~/.ssh/authorized_keys` on the box (create `~/.ssh` with `mkdir -p ~/.ssh && chmod 700 ~/.ssh`, then `chmod 600 ~/.ssh/authorized_keys`). If auto-login is greyed out, FileVault is still on — finish Step 1.2 first. |

### Step 1.4 — Disk floor and network

| | |
|---|---|
| **Commands** | ```bash
df -h /
networkQuality -v
``` |
| **Done looks like** | `df -h /` shows **Available ≥ 20 GB** (the floor — OBS replay-buffer clips and NodeCG logs are the only things that grow; a weekly cleanup job deletes clips older than 7 days and rotates logs). `networkQuality -v` shows **upload ≥ 10 Mbps sustained** (the OBS uplink needs ~8 Mbps + headroom; the runbook's minimum is 5 Mbps, the planning number is ~10 Mbps). Ethernet preferred over Wi-Fi; if Wi-Fi only, run the speed test twice and take the lower number. |
| **Time** | 5 min. |
| **If it fails** | Disk < 20 GB free: delete old clips/recordings, empty the Trash, clear `~/Library/Caches`. Still short: offload anything personal to the 128GB MBP — the box holds only the broadcast stack. Upload < 5 Mbps: move the box closer to the router, switch to Ethernet, or test again at a quiet time. If upload is still < 5 Mbps, the 1080p60/8,000 Kbps setting in §5 cannot hold — drop to 720p60/4,500 Kbps for the soak and note it in the log; the stream must not be the thing that fails. |

### Step 1.5 — Toolchain install

Install in this order. Do not skip ahead.

| | |
|---|---|
| **Commands** | ```bash
# 1. Xcode command-line tools (gives you git)
xcode-select --install
git --version
# 2. Python 3.12+ (python.org installer, or Homebrew)
python3 --version
# 3. Node.js LTS (nodejs.org installer)
node --version
npm --version
# 4. Docker Desktop for Mac (docker.com) — needed only for the Kokoro fallback in §3.2
docker --version
# 5. Homebrew (optional, only if you want it for future installs)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
``` |
| **Done looks like** | `git --version` prints a version (any recent 2.x). `python3 --version` prints **3.12 or higher**. `node --version` prints an LTS (v20+). `docker --version` prints a version and Docker Desktop is running (whale icon in the menu bar). |
| **Time** | 20–30 min (mostly downloads). |
| **If it fails** | `xcode-select --install` says tools already installed: fine, move on. Python < 3.12: install 3.12+ from python.org — do not use the system Python 3.9. Docker Desktop will not start: open it once from Applications and accept the terms; if it still will not start, §3.2 has a native-Kokoro path that does not need Docker at all. |

### Step 1.6 — Power + watchdog verification (the "does it come back?" test)

This is the most important test in §1. It proves the box self-recovers.

| | |
|---|---|
| **Commands** | ```bash
# Reboot the box now (from the masgolfs account):
sudo shutdown -r now
# Walk away. Come back in 5 minutes.
# After it is back:
pmset -g | grep -E "sleep|autorestart"
``` |
| **Done looks like** | The box is back at the `masgolfs` desktop with **no password typed and no click needed** (auto-login worked). `pmset -g` still shows `sleep 0` / `autorestart 1`. |
| **Time** | 10 min. |
| **If it fails** | Box sits at a login screen: auto-login is not on, or FileVault is still on — re-do Steps 1.2–1.3. Box sits at a FileVault unlock prompt: FileVault is on — turn it off (Step 1.2) and re-test. This test is not optional: qa-plan §2.4 requires the full broadcast to be restored ≤ 5 min after boot with no manual login, and that requirement is only testable here. |
| **Note** | The full stack is not installed yet, so this reboot only proves auto-login + power settings. The full "reboot → stream live" test runs again in §4 after `install.sh`, and the watchdog re-verifies it on every restart. |

**§1 checkpoint — do not proceed until all of these are true:**
- [ ] Box plugged in, lid open, on a hard surface, room cool
- [ ] `pmset -g` shows sleep 0 / displaysleep 0 / disksleep 0 / autorestart 1 / powernap 0 / womp 0
- [ ] Automatic macOS/App Store updates OFF; screen-lock password Never
- [ ] FileVault OFF
- [ ] `masgolfs` user exists; auto-login on; SSH key-only works; Tailscale installed
- [ ] Disk ≥ 20 GB free; upload ≥ 10 Mbps (≥ 5 Mbps absolute minimum)
- [ ] git, Python 3.12+, Node LTS, Docker Desktop all print versions
- [ ] Reboot test passed — back at the desktop with no click

---

## §2. Repo clone + the MLX verify pack — Saturday late morning

**Time for the whole section: ~45–60 min, mostly the 30-minute soak.** Nothing here touches the stream; this is the model proving itself on real silicon before anything else is built on top of it.

> **Port warning — read before you start.** Two parts of the stack both want port 8080: the MLX server (`commentary/config.yaml` → `llm.mlx.base_url: http://localhost:8080/v1`) and the web build (ops check 2 expects it on `http://localhost:8080`). They cannot both have it. The resolution for the live stack is in Step 3.1: the MLX server moves to **port 8081** and `config.yaml` is updated to match. The verify pack, however, starts its own server on :8080 — so **run the verify pack with the web server stopped** (it is not running yet at this point in the weekend, so just do §2 before §4's `start_stack.sh`).

### Step 2.1 — Clone the repo and make the QA directories

| | |
|---|---|
| **Commands** | ```bash
cd ~
git clone https://github.com/masonwyatt23/mas-golfs.git mas-golfs
cd ~/mas-golfs
git log -1 --format='%H %ci %s'
# QA artefact homes (the repo has no qa/ directory yet)
mkdir -p qa/logs qa/reports qa/screenshots qa/recordings
# Start the weekend log
touch qa/logs/install-weekend-2026-11-14.log
``` |
| **Done looks like** | `git log -1` prints the latest commit (compare the SHA with the one Ash gives you — they must match; if they do not, `git pull` and re-check). `ls qa/` shows `logs reports screenshots recordings`. |
| **Time** | 5 min. |
| **If it fails** | Clone fails with a network error: check Wi-Fi/Ethernet (Step 1.4) and try again. Clone fails with an auth error: the repo is public — make sure the URL is exactly `https://github.com/masonwyatt23/mas-golfs.git` with no token in it. |

### Step 2.2 — Check: does the model load? (verify pack, step 1)

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs/mlx-verify
# Install the pack's Python deps (from mlx-verify/README.md):
pip3 install -r requirements.txt
# Then run the whole pack, or one gate at a time:
./verify.sh all
# One gate at a time (useful when something fails):
./verify.sh check
``` |
| **Done looks like** | `verify.sh check` prints the Qwen3.5-4B-4bit load and a sample reply, and exits 0. The sample reply is one short line, no `<think>` block. If you ran `./verify.sh all`, it keeps going through latency → think → audition → ab → soak, and prints a per-gate PASS/FAIL table at the end. |
| **Time** | ~5 min for `check` alone; ~45–60 min for `all` (the 30-min soak dominates). |
| **If it fails** | Model download fails or OOM on load: check disk (Step 1.4 — the 4B model is ~2.5 GB) and free RAM (close everything except Terminal). If Qwen3.5-4B will not load at all, fall back to the second candidate `mlx-community/Qwen3-4B-Instruct-2507-4bit` and note it — the blind A/B in Step 2.5 exists to choose between them, so a load failure on one is a real result, not a reason to stop. If both 4B models fail to load, the emergency model is Qwen3-1.7B — run `check` against it and flag it in the log; the 8B and 27B models do not fit on 8GB and are not an option. |

### Step 2.3 — Latency: P99 under 4 seconds (verify pack, step 2)

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs/mlx-verify
./verify.sh latency
``` |
| **Done looks like** | Output shows **P99 < 4 s** per line (the gate is per-line, not per-round — commentary must land inside the gap between shots). P50 is typically well under 2 s. |
| **Time** | ~5 min. |
| **If it fails** | P99 ≥ 4 s: first check nothing else is running (browser closed, OBS not yet installed — if it is, quit it). If it still fails, the model is too slow on this box for live commentary — record the numbers, switch the commentary default to the other 4B candidate and re-run; if both fail, the fallback is Qwen3-1.7B. Do not tune the model or the prompt to pass — the gate is the gate. |

### Step 2.4 — `<think>` grep + audition (verify pack, steps 3–4)

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs/mlx-verify
./verify.sh think
./verify.sh audition
``` |
| **Done looks like** | `think` prints **zero `<think>` leaks over ≥ 100 lines** of generated commentary (the pack greps the output; any `<think>` in the output is a FAIL — reasoning tokens must never reach the viewer). `audition` produces the side-by-side samples of the two 4B candidates on the same events for Step 2.5. |
| **Time** | ~5 min. |
| **If it fails** | Any `<think>` in the output: the model is emitting reasoning tokens. Check that the prompt uses the `enable_thinking: false` (or equivalent) flag for the model in use — Qwen3.5 and Qwen3 both support disabling thinking; if the flag is not being passed, that is a config fix in `commentary/config.yaml`, not a model failure. Re-run `think` after the fix. If it still leaks, that candidate fails and the other one is the default. |

### Step 2.5 — Blind A/B of the two 4B candidates (verify pack, step 5)

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs/mlx-verify
./verify.sh ab
``` |
| **Done looks like** | The pack presents paired samples (same events, both candidates, labels hidden). Mason picks the winner on voice and accuracy. The winner becomes the commentary default in Step 3.1. Record the pick and the reason in one line in the weekend log — e.g. `A/B winner: Qwen3.5-4B — tighter, fewer hedges`. |
| **Time** | ~10 min (mostly Mason reading). |
| **If it fails** | No clear winner: keep the default (`mlx-community/Qwen3.5-4B-4bit`) and note "no preference". One candidate clearly worse: it becomes the documented fallback, not the default. |

### Step 2.6 — 30-minute soak: swap stays 0 (verify pack, step 6)

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs/mlx-verify
# Smoke first (5 min) — catches a fast leak before you spend 30:
SOAK_MINUTES=5 ./verify.sh soak
# Then the real gate:
./verify.sh soak
# While it runs, watch memory in a second Terminal tab:
vm_stat 5 | grep -E "Pages free|Pages active|Swapins|Swapouts"
# Or the one-liner the README uses:
# (the pack's soak step already samples this; the manual watch is a sanity check)
``` |
| **Done looks like** | After 30 minutes: **swap 0 MB** (no swapins/swapouts growth), memory flat, server still answering, zero `<think>` in the soak output. The pack prints PASS. |
| **Time** | 30 min (5 min smoke + 30 min gate — run the smoke, then start the real soak and do §3's reading while it runs; do not start §3's installs until the soak passes). |
| **If it fails** | Swap > 0 MB: the model + server do not fit comfortably in 8 GB. First check nothing else is running. If it still swaps, drop to the smaller candidate or the 1.7B emergency model and re-run the soak. A swap failure is a **box-level red flag** — it is the exact failure mode the deployment runbook warns about ("swap pressure is the failure mode to watch"), and it must be resolved before the 12-hour soak in §5, not during it. |

### Step 2.7 — Verdict and what to write down

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs/mlx-verify
cat mlx-verify-report.md 2>/dev/null | tail -30
# Save the verdict in the weekend log:
echo "MLX VERDICT $(date): default=<winner> latency-P99=<n>s think=<pass/fail> soak-swap=<n>MB" >> ~/mas-golfs/qa/logs/install-weekend-2026-11-14.log
``` |
| **Done looks like** | One line in the log with the winner, the P99 number, the think result, and the swap number. All six gates (check / latency / think / audition / ab / soak) PASS. |
| **If any gate fails** | The pack's own failure playbook is: try the other 4B candidate → try 1.7B → escalate. Do not proceed to §3 with a failed gate and a shrug — the commentary stack in §3 is built on this verdict. |

**§2 checkpoint:**
- [ ] Repo cloned at `~/mas-golfs`; SHA matches Ash's; `qa/` directories exist
- [ ] `verify.sh check` PASS — model loads, one short line, no `<think>`
- [ ] `verify.sh latency` PASS — P99 < 4 s
- [ ] `verify.sh think` PASS — zero `<think>` over ≥ 100 lines
- [ ] `verify.sh ab` done — winner recorded
- [ ] `verify.sh soak` PASS — 30 min, swap 0 MB

---

## §3. Commentary build order — Saturday afternoon

Follow `commentary/README.md` §10 exactly, in order. The 24-hour soak decision (Step 3.5) starts Saturday evening and its verdict lands Sunday evening — it overlaps the 12-hour broadcast soak in §5 on purpose.

### Step 3.1 — MLX server on port 8081 (the port fix) + config

| | |
|---|---|
| **Commands** | ```bash
# Start the MLX server for the A/B winner from Step 2.5, on port 8081
# (NOT 8080 — the web build owns 8080; see the port warning in §2):
python3 -m mlx_lm.server --model mlx-community/Qwen3.5-4B-4bit --port 8081 --max-kv-size 2048
# In a second Terminal tab, check it answers:
curl -s http://localhost:8081/v1/models | head -c 300; echo
# Then point commentary at it — edit commentary/config.yaml:
#   llm.mlx.base_url: http://localhost:8081/v1
# (was http://localhost:8080/v1 — change the port only, nothing else)
``` |
| **Done looks like** | `curl` returns a JSON list containing the model name. `commentary/config.yaml` line 25 reads `base_url: http://localhost:8081/v1`. |
| **Time** | 10 min. |
| **If it fails** | Server will not start on 8081: check nothing else is on that port (`lsof -i :8081`). Server starts but `curl` fails: the model name in the command must match the A/B winner exactly — if the winner was Qwen3-4B-Instruct-2507, use `mlx-community/Qwen3-4B-Instruct-2507-4bit`. If the server starts on 8080 by accident (a stale command), kill it and restart on 8081 — two servers on 8080 will fight the web build in §4. |

### Step 3.2 — Kokoro TTS: native first, Docker fallback

| | |
|---|---|
| **Commands** | ```bash
# Preferred: native (no Docker, no memory cap to fight).
# Follow commentary/README.md §3.4 for the native install on the box.
# If native fights, use the Docker fallback — note the --name and --memory
# flags, which the README's bare command omits (ops needs the container
# named "kokoro", and the box needs the 1 GB cap):
docker run -d --name kokoro --memory=1g --memory-swap=1g \
  -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
# Check it answers:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8880/v1/audio/speech \
  -X POST -H "Content-Type: application/json" \
  -d '{"model":"kokoro","input":"Hello friends, welcome to Wyatt National.","voice":"am_michael","response_format":"wav"}'
``` |
| **Done looks like** | Native: the commentary test in Step 3.4 produces audio. Docker: the `curl` returns **200** and a `.wav` is produced (save it with `--output /tmp/kokoro-test.wav` and play it once — it should sound like a human voice, not static). `docker ps` shows a container named `kokoro` with the 1 GB limit. |
| **Time** | 15 min native, 10 min Docker (mostly the image pull). |
| **If it fails** | Docker image will not pull: check the network (Step 1.4) and Docker Desktop is running. Container starts then dies: `docker logs kokoro` — the usual cause is memory; the `--memory=1g` cap is already set, so if it still dies, the box is out of RAM — close everything except Terminal and retry. Native install fails: use the Docker path and note it in the log; native is preferred, not required. If both fail, commentary runs silent for the soak (the ambient bed carries the stream — qa-plan §2.4) and Kokoro becomes a Sunday fix, not a Saturday blocker. |

### Step 3.3 — Ollama failover drill

| | |
|---|---|
| **Commands** | ```bash
# Install Ollama (ollama.com/download, macOS app) and pull the failover model:
ollama pull qwen3:1.7b
# Confirm it answers:
curl -s http://localhost:11434/api/tags | head -c 300; echo
# FAILOVER DRILL — kill the MLX server, then start the stack and confirm
# commentary still speaks (via Ollama) within 60 s:
#   1. Stop the MLX server (Ctrl-C in its Terminal tab).
#   2. Start the stack (ops/start_stack.sh — see §4.1; if §4 is not done yet,
#      run the commentary service alone: python3 -m commentary --demo).
#   3. Confirm a line is generated and spoken. Then restart the MLX server.
``` |
| **Done looks like** | `ollama pull` completes; `curl` lists `qwen3:1.7b`. The drill: with MLX down, a commentary line is still generated (by Ollama) within 60 s of the event, and the log shows the failover path taken. MLX restarted afterwards and is the default again. |
| **Time** | 15 min (mostly the model pull) + 5 min for the drill. |
| **If it fails** | Ollama pull fails: network or disk — re-check Step 1.4. Failover takes > 60 s or produces nothing: check `commentary/config.yaml` failover settings (the `llm` section lists `mlx` then `ollama` — order matters) and the Ollama server is actually running (`ollama serve` in its own tab if the app did not start it). If the drill fails twice, note it as a known gap and move on — the MLX path is the primary, Ollama is the spare. |

### Step 3.4 — Commentary smoke test + demo + unit tests

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs
# Unit tests (from commentary/README.md §9):
python3 -m unittest discover -s commentary/tests -v
# Smoke: one fake round through the real service:
python3 -m commentary --demo
# Then the real service (it will be started by start_stack.sh in §4;
# for now, confirm it starts and connects):
python3 -m commentary
# (Ctrl-C to stop it after you see it connect to the bus URL.)
``` |
| **Done looks like** | Unit tests: **34/34 pass** (the count from the repo; if the count is higher, take the higher number — all must pass). `--demo` prints a full fake round of lines, one decision line before every shot, one result line at landing, and never a line during a swing. `python3 -m commentary` starts, connects to `ws://localhost:4456`, and waits for events without erroring. |
| **Time** | 10 min. |
| **If it fails** | Tests fail: read the failure — a config error (wrong port, wrong model name) is the usual cause on a fresh box; fix `config.yaml` and re-run. `--demo` crashes on a made putt: that bug was fixed in the repo (snapshot unwrap + score coercion) — if it reappears, `git pull` and re-run; if it persists, log it and do not start the soak. |

### Step 3.5 — The 24-hour soak decision (starts Saturday evening, verdict Sunday evening)

This is local-models §10 step 8, and it is a **decision**, not just a test. The model server runs continuously from Saturday evening (as part of the stack in §4–§5) through Sunday evening.

| | |
|---|---|
| **Commands** | ```bash
# At the start (Saturday evening, when the stack goes up):
# Record the baseline in the weekend log:
date; vm_stat | grep -E "Pages free|Swapins|Swapouts"; echo "---" >> ~/mas-golfs/qa/logs/install-weekend-2026-11-14.log
# During the soak, sample every few hours (or let the watchdog log it):
vm_stat | grep -E "Swapins|Swapouts"
# At the verdict (Sunday evening):
#   - peak memory = worst minute over the 24 hours
#   - swap = total swapins/swapouts growth over the 24 hours
``` |
| **Done looks like — the 4B decision** | The 4B model (whichever won the A/B) is **confirmed as the commentary default** if and only if: **peak memory (worst minute) < 6.5 GB AND swap stays 0 for the full 24 hours.** If both hold, write `4B CONFIRMED` in the log and move on. |
| **Time** | 24 hours wall-clock (unattended — it runs inside the §5 soak). |
| **If it fails** | Peak memory ≥ 6.5 GB or swap > 0: the 4B does not fit comfortably for 24/7. Drop the default to the other 4B candidate and re-run the 24-hour clock, or drop to Qwen3-1.7B. Either way the decision is recorded, not assumed — a model that swaps at hour 18 is a model that drops commentary mid-round on day 3. |

**§3 checkpoint:**
- [ ] MLX server running on **8081**, `config.yaml` points at `:8081`
- [ ] Kokoro answers (native or Docker named `kokoro`, 1 GB cap) — or logged as Sunday fix
- [ ] Ollama `qwen3:1.7b` pulled; failover drill done (commentary speaks with MLX down)
- [ ] Commentary tests 34/34; `--demo` clean; service connects to the bus
- [ ] 24-hour soak clock started Saturday evening; verdict due Sunday evening

---

## §4. Ops install + failure tests + live NodeCG handshake — Saturday evening

### Step 4.1 — Start the bus and the stack (before install.sh)

| | |
|---|---|
| **Commands** | ```bash
cd ~/mas-golfs
# Start the event bus (Python stdlib — no dependencies):
python3 -m bus
# In a second Terminal tab, confirm it answers and writes state:
curl -s http://localhost:4456/ ; echo
ls -la ops/state/last_event
# Start the stack (bus + web build + commentary + NodeCG if installed):
~/mas-golfs/ops/start_stack.sh
``` |
| **Done looks like** | The bus prints its startup line and stays running. `ops/state/last_event` exists and updates on every event (that file is the watchdog's proof the bus is alive — a stale timestamp there is how check 3 fails). `start_stack.sh` brings up each layer in order (bus → web build on :8080 → commentary → NodeCG) and prints a line per layer. |
| **Time** | 10 min. |
| **If it fails** | Bus will not start: port 4456 in use (`lsof -i :4456` — kill the stale process). `start_stack.sh` fails on the web build: the build is not in the repo yet — see Step 4.5; if the build is missing, run the bus and commentary alone for now and come back to the stack after the export lands. Ollama slow to start: `start_stack.sh` §3.3 says allow 60 s; if Ollama still is not up, start it by hand (`ollama serve`) and re-run the stack script. |

### Step 4.2 — Run ops/install.sh and verify the install

| | |
|---|---|
| **Commands** | ```bash
~/mas-golfs/ops/install.sh
# Verify (from ops/README.md §5.2 — run these exactly):
bash -n ~/mas-golfs/ops/*.sh
python3 -m py_compile ~/mas-golfs/ops/obs_client.py
python3 ~/mas-golfs/ops/obs_client.py GetStreamStatus
bash ~/mas-golfs/ops/watchdog.sh
launchctl list | grep -i restart
grep -ri "daily restart" ~/mas-golfs/ops
``` |
| **Done looks like** | `install.sh` exits 0. `bash -n` prints nothing (no syntax errors). `py_compile` prints nothing. `obs_client.py GetStreamStatus` prints a stream status (OBS must be running for this — if OBS is not installed yet, this check moves to §5.1; note it and come back). `watchdog.sh` runs once and prints its checks. **`launchctl list \| grep -i restart` prints nothing** (no scheduled restart exists). **`grep -ri "daily restart"` prints nothing** (no daily restart anywhere in ops). |
| **Time** | 15 min. |
| **If it fails** | `install.sh` fails partway: read the last lines — the usual cause is a missing dependency (Node, Python, or Docker from §1.5). Fix the dependency, re-run `install.sh` from the top (it is idempotent — safe to re-run). `obs_client.py` cannot connect: OBS is not running or obs-websocket is not enabled — that is §5.1, not a failure here. |

### Step 4.3 — Per-check failure tests (ops/README.md §5.3 — run all 11)

These are the tests that prove the watchdog actually catches things. Run them one at a time, in order, and log the result of each. "The watchdog noticed" means the expected action happened and a line appeared in the log — not that you noticed it yourself.

| # | Test | Command / action | Expected result |
|---|---|---|---|
| 1 | Web build unreachable | Stop the web server, run `bash ~/mas-golfs/ops/watchdog.sh` | Check 2 fails; watchdog restarts the web build; restart it yourself afterwards if the watchdog does not |
| 2 | Bus silent | Stop the bus, run the watchdog | Check 3 fails (no `last_event` update); watchdog runs `MAS_GOLFS_BUS_RESTART_CMD` |
| 3 | OBS websocket down | Quit OBS, run `bash ~/mas-golfs/ops/obs_client.py GetStreamStatus` | Error, exit code 1 |
| 4 | Disk full | `df -h /` | Fails the 20 GB floor — this is a drill: confirm the check fires, then free space; do not actually fill the disk |
| 5 | Kokoro down | `docker stop kokoro` (or stop native Kokoro), then POST a test synthesis | `curl` to `http://localhost:8880/v1/audio/speech` fails or times out; commentary falls back to silent + ambient bed |
| 6 | NodeCG down | Stop NodeCG, open `http://localhost:9090/bundles/mas-golfs/graphics/scorebug` | Page fails to load; the stream falls back to the static scorebug (last known state) — never blank overlays > 10 s |
| 7 | Stream offline | Stop the stream in OBS, run `bash ~/mas-golfs/ops/watchdog.sh` | Watchdog restarts the stream via OBS websocket |
| 8 | Upload degraded | `networkQuality -v` | If upload < 5 Mbps, the check fails and the log says so; the response is to drop bitrate (see Step 1.4), not to keep streaming at 8,000 Kbps |
| 9 | Swap pressure | `vm_stat` / Activity Monitor → Memory | Swap > 0: FAIL — see Step 2.6; this is the box-level red flag |
| 10 | Clip disk growth | `du -sh ~/mas-golfs/clips/` | Grows only by the retention policy; > 500 MB over 7 days = FAIL unless the policy says otherwise |
| 11 | No daily restart | `launchctl list \| grep -i restart` and `grep -ri "daily restart" ~/mas-golfs/ops` | Both print nothing |

**Done looks like:** all 11 rows logged with PASS/FAIL and the observed watchdog action. Any row that fails is a real defect to fix now, not a note for later — the soak in §5 is only meaningful if the watchdog has already proven it catches things.
**Time:** 30 min.
**If a test fails:** fix the underlying cause (usually a wrong path, a service not started, or a port conflict), then re-run that single test. If the watchdog does not restart something it is supposed to restart, the bug is in the watchdog or the restart command — read `ops/watchdog.sh` and `MAS_GOLFS_BUS_RESTART_CMD` (set it in the environment before starting the bus: `MAS_GOLFS_BUS_RESTART_CMD='cd ~/mas-golfs && nohup python3 -m bus >> ops/bus.log 2>&1 &'`).

### Step 4.4 — NodeCG: install + live ws handshake against the real bus

This is the test the audit flagged as never having run live. The demo mode (`MAS_GOLFS_DEMO=1`) is not a substitute — it generates fake events. This step uses the real bus and real sim events.

| | |
|---|---|
| **Commands** | ```bash
# 1. Install NodeCG (from nodecg-bundle/README.md):
#    Download NodeCG from nodecg.com (or npm install -g nodecg-cli && nodecg setup),
#    then copy the bundle in:
cp -r ~/mas-golfs/nodecg-bundle /path/to/nodecg/bundles/mas-golfs
cd /path/to/nodecg/bundles/mas-golfs && npm install
# 2. Start NodeCG in LIVE mode (MAS_GOLFS_DEMO unset / 0), bus already running:
cd /path/to/nodecg && node index.js
# 3. In a third Terminal tab, drive real events through the bus:
cd ~/mas-golfs && python3 -m bus.demo --rounds 1 --delay 0.5
# 4. Check the graphics answer:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9090/bundles/mas-golfs/graphics/scorebug
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9090/bundles/mas-golfs/graphics/lower-third
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9090/bundles/mas-golfs/graphics/leaderboard
``` |
| **Done looks like** | All three `curl` checks return **200**. More importantly: open `http://localhost:9090/bundles/mas-golfs/graphics/scorebug` in a browser and watch it while `bus.demo` runs — the hole number, score, and "thru" advance as the demo round plays. Open the lower-third URL and confirm a shot lower-third appears on `strike` and locks in `CARRIED n YDS · TOTAL n YDS` on `landing`. The NodeCG dashboard at `http://localhost:9090` loads and shows the mas-golfs bundle. |
| **Time** | 20 min. |
| **If it fails** | Graphics return 404: the bundle is not in the right place — the path must be `<nodecg>/bundles/mas-golfs` exactly, and `npm install` must have run inside it (it installs `ws`, the bus client). Scorebug loads but never updates: the extension is not connected to the bus — check `MAS_GOLFS_BUS_URL` (default `ws://localhost:4456`) and that the bus is actually running (Step 4.1). Scorebug updates in demo mode but not live: you are running with `MAS_GOLFS_DEMO=1` set — unset it and restart NodeCG. The integration harness (`python3 tests/integration/run.py`) is the automated version of this check — it needs Node; its NodeCG test_04 is flaky ~50% and not root-caused, so a single harness failure is not a verdict, but three in a row is. |

### Step 4.5 — Freeze the web build (Ash exports, Mason verifies)

The repo's `index.html` is v10-era and stale versus the live artifact. The build must be frozen and exported before the soak, or the soak certifies the wrong build.

| | |
|---|---|
| **Commands (Ash does the export; Mason verifies)** | ```bash
cd ~/mas-golfs
git pull
git log -1 --format='%H %ci' -- index.html
grep -c "Road to 59" index.html
grep -c "62" index.html
# Serve it (the stack script does this; by hand it is):
python3 -m http.server 8080
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/
``` |
| **Done looks like** | `git log` shows today's date on `index.html`. `grep -c "Road to 59"` returns ≥ 1. `grep -c "62"` returns **0** in branding text (this is GL-07 — zero "Road to 62" strings). `curl` to `:8080` returns **200** and the page contains "Mas Golfs". |
| **Time** | 10 min (plus Ash's export time). |
| **If it fails** | `git log` shows an old date: the export has not landed — stop here and do not start the soak. `grep "62"` returns > 0: check whether the hits are branding ("Road to 62") or innocent (a yardage, a year) — branding hits must be fixed in the export; innocent hits are logged and ignored. `:8080` does not answer: the MLX server is on 8080 by mistake (see §2's port warning) — kill it and restart on 8081. |

**§4 checkpoint:**
- [ ] Bus running; `ops/state/last_event` updating
- [ ] `install.sh` exits 0; `bash -n` clean; `py_compile` clean
- [ ] `launchctl list | grep -i restart` prints nothing; `grep -ri "daily restart"` prints nothing
- [ ] All 11 failure tests run and logged
- [ ] NodeCG live: scorebug/lower-third/leaderboard all 200, updating from real bus events
- [ ] Web build frozen: `index.html` dated today, "Road to 59" present, zero "Road to 62" in branding, :8080 returns 200

---

## §5. OBS + Restream + the 12-hour soak — Saturday night → Sunday morning

### Step 5.1 — OBS install and settings

| | |
|---|---|
| **Commands** | GUI + one check. Download OBS Studio (Apple Silicon build) from obsproject.com and install. Then in OBS: |
| **Settings** | Settings → Stream → Service: **Restream** (or Custom with the Restream RTMP ingest URL + stream key from Step 5.2). Settings → Output → Output Mode: Advanced; Streaming: Encoder **Apple VT H264 Hardware Encoder** (VideoToolbox — the hardware encoder is what makes 8GB viable); Rate Control **CBR**; Bitrate **8000 Kbps**; Keyframe Interval **2**; Profile **high**. Settings → Audio: Sample Rate **48 kHz**; Channels Stereo; Mic/Aux off unless needed. Settings → Video: Base (Canvas) **1920×1080**; Output (Scaled) **1920×1080**; FPS **60**. Settings → Output → Replay Buffer: **on** (this is what saves clips to `~/mas-golfs/clips/`). Settings → Advanced: enable **obs-websocket** on `localhost:4455`, no authentication (ops check 4 depends on it). |
| **Sources (one scene, "Mas Golfs Live")** | 1. **Game Capture / Window Capture** — the web build (browser, `http://localhost:8080`, fullscreen). 2. **Browser Source** × 6 — the NodeCG graphics, 1920×1080, transparent: Scorebug `http://localhost:9090/bundles/mas-golfs/graphics/scorebug`; Leaderboard `.../leaderboard`; Lower Third `.../lower-third`; Ticker `.../ticker`; Player Card `.../player-card`; Hole Card `.../hole-card`. 3. **Audio Input / Media Source** — the commentary audio output (Kokoro) + the ambient bed. Scene placement per `docs/broadcast-stack.md` §2.2: scorebug + ticker always on in camera scenes; lower-third hidden by default (shown on `strike` / `hole_end`); leaderboard full-screen with game capture hidden; hole card on the flyover scene. |
| **Done looks like** | `python3 ~/mas-golfs/ops/obs_client.py GetStreamStatus` prints a stream status (not a connection error). OBS preview shows the web build + scorebug + ticker, no black frames. The replay buffer is saving to `~/mas-golfs/clips/` (start the buffer, wait 30 s, check the directory is non-empty). |
| **Time** | 30 min. |
| **If it fails** | obs-websocket will not enable: OBS version too old — update OBS. `obs_client.py` cannot connect: websocket is on the wrong port (must be 4455) or authentication is on (must be off for the ops client). Preview is black: the browser source URL is wrong — open `http://localhost:8080` in a normal browser first; if that is black, the web build is not serving (Step 4.5). Dropped frames immediately: check the encoder is VideoToolbox (not x264 — software encoding on 8GB will choke) and nothing else is running. |

### Step 5.2 — Restream + YouTube Live + Twitch (private test destinations)

| | |
|---|---|
| **Commands** | GUI. In Restream (free tier): add **YouTube Live** and **Twitch** as channels, copy the Restream **ingest URL + stream key** into OBS (Settings → Stream). In YouTube Studio: create the stream as **Unlisted** (not Public — this is a test). In Twitch: the stream goes to your channel; set it to not announce. |
| **AI-use disclosure (GL-09) — paste this into both stream descriptions now** | **YouTube:** "AI-generated content: this is a fully autonomous, computer-generated golf broadcast. The golfer 'Mas', the course, the commentary voices, and all gameplay are generated by software — no real person is playing golf. Created with the Mas Golfs simulation and local AI commentary." **Twitch:** "AI-generated broadcast: the golfer, course, commentary and gameplay are computer-generated. No real person is playing." |
| **Done looks like** | Restream dashboard shows YouTube and Twitch connected (green). Both stream descriptions carry the disclosure text above. |
| **Time** | 15 min. |
| **If it fails** | Restream will not connect a channel: re-authorise that channel in Restream (the usual cause is an expired OAuth token). No stream keys yet (§0.3 red): skip to Step 5.4 with the stream going nowhere — the soak can still run locally, but GL-08 stays red and the soak is not a real streaming soak. |

### Step 5.3 — 5-minute private test stream (GL-08)

| | |
|---|---|
| **Commands** | ```bash
# In OBS: click Start Streaming. Then, from a second machine (or Mason's phone):
#   - open the unlisted YouTube link; confirm video + audio play
#   - open the Twitch channel; confirm video + audio play
# After 5 minutes, stop the stream. Check the clip directory:
ls -la ~/mas-golfs/clips/ | head
``` |
| **Done looks like** | Both destinations go live and are viewable (this is GL-08). Audio is present on both. At least one replay-buffer clip exists in `~/mas-golfs/clips/` and plays (GL-11). OBS dropped-frames counter is 0% (or < 0.1%). |
| **Time** | 10 min. |
| **If it fails** | One destination is black but the other works: the fault is in Restream's routing to that destination — re-check that channel in Restream, then re-test that destination alone. Both black: OBS is not actually streaming — check the OBS status bar (it must say LIVE) and the Restream dashboard (it must show an incoming stream). Audio missing: the commentary/ambient source is muted or routed to the wrong track — check OBS Audio Mixer levels while the test runs. Dropped frames > 1%: see Step 5.1 — VideoToolbox, nothing else running, Ethernet if possible. |

### Step 5.4 — Soak B: the 12-hour overnight soak (starts Saturday ~9pm, verdict Sunday ~9am)

This is qa-plan §2, stage B. The full stack runs unattended overnight: web build → OBS → NodeCG → Restream → the **private/unlisted** YouTube test stream. Nobody touches it. The watchdog is the only responder. **One manual intervention = the stage restarts from zero.**

| | |
|---|---|
| **Commands** | ```bash
# Start the soak log:
echo "SOAK B START $(date)" > ~/mas-golfs/qa/logs/soak-2026-11-14.log
# Confirm the stack is up, then start streaming in OBS and walk away.
# Sampling (the watchdog logs continuously; spot-check twice — once before bed,
# once in the morning — with):
curl -s -o /dev/null -w "web:%{http_code}\n" http://localhost:8080/
curl -s -o /dev/null -w "nodecg:%{http_code}\n" http://localhost:9090/bundles/mas-golfs/graphics/scorebug
vm_stat | grep -E "Swapins|Swapouts"
df -h / | tail -1
``` |
| **Done looks like — all §2.3 rows PASS** | S-01 uptime: stream live the full 12 h, zero gaps > 30 s. S-02 GPU memory: flat across rounds, last-round value within ±5% of first. S-03 JS heap: hour-12 within ±10% of hour-1. S-04 frame rate: p50 ≥ 55 fps, p5 ≥ 30 fps, zero 10-s stretches below 20 fps. S-05 rounds: ≥ 1 round per ~2.5 h at broadcast speed; round counter increments monotonically, never resets. S-06 bus: zero `seq` gaps in any round; zero disconnects > 5 s. S-07 director: spot-check 10 random hole transitions — camera holds ≥ 2 s on every cut, never cuts mid-flight, falls back to wide cam (never black) on error. S-08 overlays: scorebug updates within 1 s of the event; leaderboard within 2 s of `hole_end`; no stale data older than 5 s. S-09 commentary: one decision line before every shot, one result line at landing, zero commentary jobs started during a swing. S-10 audio: ambient bed audible, never silent; no clipping; no overlapping stingers. S-11 watchdog: every fault logged with timestamp and action; restart restores the stream without human input. S-12 disk: `~/mas-golfs/clips/` grows only by the retention policy. |
| **Failure responses (§2.4) — what should happen on its own** | Bus drops: director holds the wide cam, overlays freeze on last good data (never blank), bus reconnects ≤ 10 s. OBS crashes: watchdog restarts OBS, stream resumes ≤ 60 s. WebGL context lost: renderer re-initialises, round state restored from the event log, recovery ≤ 30 s. NodeCG crashes: graphics fall back to the static scorebug (last known state), no blank overlays > 10 s. TTS down: commentary silences, ambient bed carries the stream, max 1 retry/min. Machine reboot: autostart brings the full stack back ≤ 5 min after boot, no manual login. |
| **Time** | 12 hours, unattended. |
| **If it fails** | Any §2.3 row fails, or any §2.4 response does not happen as documented: the soak **fails**. Note the failure, the time, and the symptom in `qa/logs/soak-2026-11-14.log` and in `qa/incidents.md` (append-only, one line per incident: date, time, symptom, cause, fix). Fix the cause on Sunday, then **restart Soak B from zero** — a 12-hour soak with a 2am manual restart in the middle is not a 12-hour soak. If the failure is the NodeCG flakiness (test_04, ~50%, not root-caused), that is a real defect: do not wave it through because the harness is flaky — the flake is the thing being tested. |

### Step 5.5 — Sunday morning: read the soak log, give the verdict

| | |
|---|---|
| **Commands** | ```bash
cat ~/mas-golfs/qa/logs/soak-2026-11-14.log
# Check the stream is still live, then stop it in OBS:
curl -s -o /dev/null -w "web:%{http_code}\n" http://localhost:8080/
ls ~/mas-golfs/clips/ | wc -l
du -sh ~/mas-golfs/clips/
# Verdict line:
echo "SOAK B VERDICT $(date): PASS/FAIL — <one line: what passed, what failed>" >> ~/mas-golfs/qa/logs/soak-2026-11-14.log
``` |
| **Done looks like** | The log shows the full 12 hours with **zero manual interventions**, every §2.3 row PASS, and any §2.4 failure handled by the documented response. Write the verdict line. If PASS, Soak C (7 days) starts Sunday — see §7. |
| **Time** | 20 min. |
| **If it fails** | See Step 5.4 — fix, then re-run Soak B from zero (Sunday night, if the fix is quick; otherwise the following night). Do not start Soak C on top of a failed Soak B. |

**§5 checkpoint:**
- [ ] OBS: VideoToolbox, 1080p60, 8,000 Kbps CBR, keyframe 2, AAC 160 Kbps 48 kHz, replay buffer on, obs-websocket :4455 no auth
- [ ] Restream: YouTube + Twitch connected; disclosure text in both descriptions
- [ ] 5-min private test stream: both destinations live and viewable (GL-08); test clip saved and viewable (GL-11)
- [ ] Soak B: 12 h, zero manual interventions, all §2.3 rows PASS — verdict logged

---

## §6. The "pee break" intermission — Sunday update procedure

The box does not restart daily. Restarts happen only on an update, a fault, or watchdog-detected drift. The Sunday update is the one planned restart of the week, and it runs as an on-screen intermission, not a dead stream. Procedure per deployment-runbook §4.5 and local-models §9.

### When it happens

Sunday, after the Soak B verdict (Step 5.5) and before Soak C starts. The update is: macOS updates (by hand) + `git pull` for any repo changes since Saturday + a stack restart. Announce it in advance — in the stream description and a pinned comment — with the time and the expected length.

### The procedure, in order

| # | Step | Detail |
|---|---|---|
| 1 | **Announce** | Post the time in the stream description / pinned comment before Sunday. Viewers should never be surprised by the card. |
| 2 | **Wait for a safe moment** | The director defers the intermission if 59 Watch is on the line (Mas is under the 59 pace and a shot is imminent). Never cut away mid-hole when the chase is live. |
| 3 | **Show the card** | Switch OBS to the intermission scene. The card shows: current score, 59 Watch status, leaderboard top 3, and a countdown to resumption. It is a broadcast graphic, not a black screen and not a "be right back" slide. |
| 4 | **Do the update** | macOS: System Settings → General → Software Update → install. Repo: `cd ~/mas-golfs && git pull` (then re-run `ops/install.sh` if anything in `ops/` changed). Restart the stack with `ops/start_stack.sh`. Typical Sunday update: **10–15 min**. A macOS update is the longest planned intermission, **~30 min**; everything else has a **hard cap of 15 min**. |
| 5 | **Watchdog verifies before resume** | The watchdog runs its 5 health checks (web build answering, bus events flowing, NodeCG graphics up, OBS streaming, disk floor) and only then resumes the stream automatically. If any check fails, the stream does **not** resume until the check passes — the card stays up and the log says why. |
| 6 | **Resume + log** | Switch back to the live scene. Log one line in `qa/logs/install-weekend-2026-11-14.log`: `INTERMISSION $(date): <what was updated> — <duration> min — watchdog 5/5`. |

### If the intermission goes wrong

| Symptom | Response |
|---|---|
| macOS update needs a second reboot | Let it reboot. Auto-login + `launchd` bring the stack back (Step 1.6 proved this). The card stays up until the watchdog's 5 checks pass. |
| `git pull` conflicts | Do not resolve conflicts on the box mid-intermission. `git stash` the local change, pull, and note it — or skip the pull entirely and do it next Sunday. The stream matters more than the pull. |
| Stack will not come back | The watchdog retries; if it is still down after 5 min, stop the stream in OBS (a clean stop beats a frozen one), fix it with the §4 playbooks, and restart the stream by hand. Log it in `qa/incidents.md`. |
| Intermission runs past its cap | Say so on the card (update the countdown), finish the update, and resume. A 30-minute macOS intermission that was announced is fine; an unannounced hour is not. |

---

## §7. Go-live checklist (qa-plan.md §6) — marked for this weekend

One unchecked item = no launch. This is the checklist as it stands at the **end** of the install weekend. Column "VM" is what the repo already proves; column "Box" is what only this weekend (and the week after) can prove.

### 7.1 Gates that must already be green

| # | Item | VM (already green from this VM) | Box (only the box can prove) | Weekend status |
|---|---|---|---|---|
| GL-01 | Sim calibration (§1) | **Not green.** Full suite is green (210 tests, pushed `d2fd34e0`) and the retune landed (driver carry 262.6 / 264.6 vs 268), but the Tier A/B calibration harness (QA plan v1.1) has never run. The old 10,000-round gate is deferred, not undecided (§0.1). | n/a — calibration is a repo job, not a box job. | 🔴 Must land before launch; the weekend does not close it. |
| GL-02 | 7-day soak (§2) | n/a — a soak is a box job by definition. | **Not started.** Soak B runs this weekend; Soak C starts Sunday if B passes. | 🔴 Starts Sunday; verdict 7 days later. |
| GL-03 | Web build (§3) | **Partial.** Earlier DevTools captures pre-date the clean-screen rebuild; the v11 + mobile/character rebuilds are unaudited; the 3-round DevTools soak (§3.5) has never run. | Frame rate / heap / context-loss on the real 8GB box, inside Soak B. | 🟡 Proved or failed by Soak B. |
| GL-04 | Graphics & commentary (§4) | **Partial.** NodeCG stub smoke + placeholder checks pass; commentary 34/34 tests + demo pass; live paths (real bus → real graphics, real MLX → real Kokoro) are stub-only. | Full-round recording reviewed; zero G-08/V-03 failures. | 🟡 Proved or failed by Soak B + Step 4.4. |
| GL-05 | Coins (§5) | **Code green, checks red.** Engine built, 36/36 tests pass (post-audit). But §5 payout/anti-abuse checks have never run on a test economy, and NodeCG/web wiring + persistence are not built. | §5 checks on the test economy, on the box. | 🟡 Code exists; launch-with or descope is Mason's call. |
| GL-06 | Performance audit P0s fixed | **Claimed, unverified.** P0-1 (dispose) and P0-2 (hole-change hitch) are "fixed" in code; neither has been re-verified by re-running K-01/K-02. | K-01/K-02 re-run on the box, fix in the live build not just a branch. | 🟡 Re-run inside Soak B; a hitch on the box is a fail. |

### 7.2 Launch-day checks (run the morning of launch — not this weekend, but the weekend sets them up)

| # | Item | Weekend status |
|---|---|---|
| GL-07 | Build is the latest; zero "Road to 62" in branding | Set up by Step 4.5 (`git log` today, `grep -c "62"` = 0). Re-run on launch morning. |
| GL-08 | Stream keys work — 5-min private test to YouTube + Twitch | **Proved this weekend** by Step 5.3. Re-run on launch morning. |
| GL-09 | AI-use disclosure in both stream descriptions | **Drafted in this runbook** (Step 5.2) and pasted this weekend. Re-check on launch morning. |
| GL-10 | Watchdog armed; last health check < 60 s old; restart path tested this week | **Proved this weekend** by Steps 4.2–4.3. |
| GL-11 | Clip pipeline armed; one test clip produced and viewable | **Proved this weekend** by Steps 5.1/5.3. |
| GL-12 | Coins seeded (10,000 CC pool; weekly board live; test prediction placed + settled) | Blocked on GL-05 — coins wiring/persistence not built. Mason's call. |
| GL-13 | Mason's phone check — 2 min on his phone, looks and sounds right | Do it during Step 5.3's test stream (the only human check in the list). |
| GL-14 | The stranger test (§4.3) on the live build | Do it on the Soak B recording Sunday morning. |

### 7.3 Day-1 monitoring (first 24 hours live — after Soak C, not this weekend)

| # | Item | Note |
|---|---|---|
| GL-15 | Someone watches the first hour live, log open, ready to kill the stream | Mason or a delegate. |
| GL-16 | First auto-clip out within 24 h of go-live | Launch-playbook cadence. |
| GL-17 | Metrics baseline — first row of the weekly tracking sheet filled | Uptime, clips, views, returning viewers, predictions, scoring average. |
| GL-18 | Incident log reviewed before day 2 | `qa/incidents.md`. |

**Honest summary for Sunday night:** after a clean weekend, the gates that are green are GL-08, GL-09, GL-10, GL-11, GL-13, GL-14 (if the stranger test passes) — the *operational* half. The gates that are still red are GL-01 (calibration), GL-02 (7-day soak), GL-05/GL-12 (coins), and GL-03/GL-04/GL-06 pending Soak B's verdict. That is the correct outcome for an install weekend: the box is proven, the show is not yet cleared to launch.

---

## §8. Failover with no spare (deployment-runbook §8.5)

There is no spare machine. The Air is off-limits and the 128GB MBP is Mason's workhorse. Recovery is, in order:

### Path 1 — Repair / restart the box (first, always)

- Watchdog restarts the failed service (OBS ≤ 60 s, bus ≤ 10 s, full stack ≤ 5 min after boot). This covers almost everything — a crash is not an outage, it is a 60-second gap.
- If the box itself is down: power-cycle it, let auto-login + `launchd` bring the stack back, verify with the 5 health checks. If it comes back, the stream resumes and the incident goes in `qa/incidents.md`.
- **Monthly cold-boot drill:** once a month, unplug the box (or `sudo shutdown -r now`) and time the unattended recovery. Target: **< 10 min** from power-on to stream live with zero clicks. If the drill fails, fix the automation that day — do not wait for a real outage to discover it.

### Path 2 — Cloud GPU (if the box is dead for hours, not minutes)

- Rent a cloud GPU box (e.g. RunPod Secure Cloud, RTX 4090, ~$0.69–0.89/hr) and run the web build + OBS there. Only works if it is **pre-staged**: the setup must already exist as a script or image, because building it from scratch mid-outage takes hours. Pre-staging is a future job, not a weekend job — note it in the log if it does not exist yet.
- Time to stream if pre-staged: **~30–60 min**. If not pre-staged, this path does not exist — say so honestly instead of assuming it.

### Path 3 — Static-host fallback + 128GB MBP as an hours-only bridge (last resort)

- Host the web build statically (any free static host) and run OBS on the 128GB MBP **only as a bridge for hours, not days** — the 128GB MBP is Mason's workhorse, and a 24/7 encoder on it means thermal throttling during builds, fan noise during calls, and a stream that dies the day Mason takes the laptop to a meeting. Separation is the whole point of the dedicated box.
- This path keeps *something* live while the 8GB box is repaired or replaced. It is not a second broadcast box.

### What failover is not

- It is not the Air. The 16GB MacBook Air is never used — not as a spare, not as a bridge, not for one night. It holds Grandpa's poems; grandma wants to publish them.
- It is not a purchase made in a panic. Any cloud spend is Mason's call, and the $0 rule still holds unless he explicitly breaks it.

---

## §9. Weekend timeline + sign-off

### Saturday

| Time | What | Section |
|---|---|---|
| 09:00 | Box out, plugged in, lid open; §1 box prep | §1 |
| 10:00 | Toolchain install (downloads) | §1.5 |
| 10:30 | Reboot test — back at the desktop with no click | §1.6 |
| 11:00 | Repo clone; MLX verify pack — check, latency, think, audition, A/B | §2.1–2.5 |
| 12:00 | 30-min soak (swap 0) — run it over lunch | §2.6 |
| 12:30 | MLX verdict logged | §2.7 |
| 13:00 | Commentary build order — MLX on 8081, Kokoro, Ollama drill | §3.1–3.3 |
| 14:30 | Commentary tests + demo | §3.4 |
| 15:00 | ops/install.sh + 11 failure tests | §4.2–4.3 |
| 16:00 | NodeCG live handshake (real bus events → scorebug) | §4.4 |
| 16:30 | Web build freeze — Ash exports, Mason verifies | §4.5 |
| 17:00 | OBS install + settings + sources | §5.1 |
| 18:00 | Restream + disclosure text | §5.2 |
| 18:30 | 5-min private test stream (both destinations) | §5.3 |
| 19:00 | Phone check (GL-13) + stranger test on the test stream | §5.3 / §7 |
| 21:00 | **Start Soak B (12 h) + start the 24-hour model soak clock** | §5.4 / §3.5 |

### Sunday

| Time | What | Section |
|---|---|---|
| 09:00 | Soak B verdict — read the log, write the verdict line | §5.5 |
| 09:30 | Stranger test on the Soak B recording (GL-14) | §7 |
| 10:00 | **Pee-break intermission: macOS update + `git pull` + stack restart** | §6 |
| 10:30 | Watchdog 5-check verification; stream resumes | §6 |
| 11:00 | Fix anything Soak B found; if B failed, restart B Sunday night | §5.4 |
| 12:00 | §7 checklist re-marked with the weekend's evidence | §7 |
| 21:00 | **24-hour model soak verdict — 4B confirmed or dropped** | §3.5 |
| 21:00 | **If Soak B passed: start Soak C (7 days)** — the go-live gate | §7 |

### Weekend sign-off (fill in Sunday night)

```
INSTALL WEEKEND 2026-11-14/15 — SIGN-OFF
Box prep (§1):            PASS / FAIL — notes:
MLX verify (§2):          PASS / FAIL — default model: __________ P99: ____s swap: ____MB
Commentary (§3):          PASS / FAIL — Kokoro: native / docker / deferred — Ollama drill: PASS / FAIL
Ops + NodeCG (§4):        PASS / FAIL — failure tests: __/11 — live handshake: PASS / FAIL
OBS + Restream (§5):      PASS / FAIL — test stream: PASS / FAIL — clips: PASS / FAIL
Soak B (12 h):            PASS / FAIL — interventions: ____ — verdict logged: Y/N
24-h model soak:          4B CONFIRMED / DROPPED TO __________ — peak mem: ____GB swap: ____MB
Soak C (7 d):             STARTED $(date) / NOT STARTED — reason:
GL gates green:           GL-____, GL-____, GL-____
Still red:                GL-01 (calibration) / GL-02 (Soak C) / GL-05+GL-12 (coins) / __________
Next:                     ________________________________________________________
```

---

## Appendix A — Known doc conflicts found while writing this runbook

These are inconsistencies between the source docs. The runbook resolves each one inline (the resolution is stated where it is used); this appendix collects them so they can be fixed at source.

1. **Port 8080 is claimed twice.** `commentary/config.yaml` puts the MLX server on `http://localhost:8080/v1`; ops check 2 expects the web build on `http://localhost:8080`. Resolution in this runbook: MLX moves to **8081**; `config.yaml` is updated (Step 3.1); the verify pack runs with the web server stopped (§2).
2. **Bus implementation drift.** The readiness audit says the bus is Node.js `ws`; it is Python stdlib, and it writes `ops/state/last_event` on every event. The ops README's "check 3 is port-only until the bus ships" is stale — the bus has shipped. Resolution: the runbook states the Python contract everywhere (Steps 4.1, 4.3).
3. **Kokoro Docker command drift.** `commentary/README.md` §3.4 gives a bare `docker run` with no `--name` and no memory limit; ops check 5 needs the container named `kokoro`, and the 8GB box needs the 1 GB cap. Resolution: Step 3.2 gives the corrected command with `--name kokoro --memory=1g --memory-swap=1g`.
4. **`mlx-verify/README.md` line 21** says `mlx-audit.sh` where it means `mlx-verify.sh`.
5. **Intermission length.** Local-models §9 caps maintenance intermissions at 15 min; deployment-runbook §4.5 allows ~30 min for the Sunday macOS update. Resolution: 15 min hard cap for everything except the macOS update, which is ~30 min max and announced in advance (§6).
6. **`sim/constants.py` was stale** (74.6/138, 7,214 yd) versus the v3 rating (76.1/142, 7,602 yd) — **resolved Nov 13**: constants now read 76.1/142, 7,602 yd; full suite re-run in progress to confirm.

## Appendix B — Quick-reference command cheatsheet (the box, `masgolfs` user)

```bash
# Stack
cd ~/mas-golfs && ~/mas-golfs/ops/start_stack.sh   # start everything
python3 -m bus                                     # bus alone (port 4456)
python3 -m commentary                              # commentary alone
python3 -m commentary --demo                       # fake round through commentary
python3 -m mlx_lm.server --model mlx-community/Qwen3.5-4B-4bit --port 8081 --max-kv-size 2048
python3 -m http.server 8080                        # web build alone (from the build dir)

# Health (the five checks the watchdog runs)
curl -s -o /dev/null -w "web:%{http_code}\n" http://localhost:8080/
ls -la ~/mas-golfs/ops/state/last_event
curl -s -o /dev/null -w "nodecg:%{http_code}\n" http://localhost:9090/bundles/mas-golfs/graphics/scorebug
python3 ~/mas-golfs/ops/obs_client.py GetStreamStatus
df -h /

# Memory / swap (the number that matters on 8 GB)
vm_stat | grep -E "Swapins|Swapouts"
networkQuality -v                                  # upload must be >= 5 Mbps, want >= 10

# Watchdog + no-restart proofs
bash ~/mas-golfs/ops/watchdog.sh
launchctl list | grep -i restart                    # must print nothing
grep -ri "daily restart" ~/mas-golfs/ops           # must print nothing

# Logs
tail -f ~/mas-golfs/qa/logs/soak-2026-11-14.log
tail -f ~/mas-golfs/ops/watchdog.log
```

## Appendix C — Sources

- `docs/deployment-runbook.md` (box setup, pmset, launchd, watchdog, failover §8.5)
- `docs/local-models.md` (§10 build order, §9 intermissions, §3.2 memory budget)
- `mlx-verify/README.md` (verify pack gates, thresholds, ~45–60 min)
- `ops/README.md` (install.sh, per-check failure tests)
- `commentary/README.md` (§10 build order, §9 tests, §3.4 Kokoro)
- `bus/README.md` (`MAS_GOLFS_BUS_URL`, `MAS_GOLFS_BUS_RESTART_CMD`)
- `nodecg-bundle/README.md` (graphics URLs, install, live vs demo mode)
- `docs/reviews/readiness-2026-11-13.md` (audit: NOT READY, 0/18, what never ran on the box)
- `docs/qa-plan.md` (§2 soak stages + §2.3/§2.4 tables, §6 go-live checklist GL-01–GL-18)

*Written Nov 13, 2026. No code was changed and nothing was installed to write this doc; nothing here was pushed to GitHub.*
