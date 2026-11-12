# Mas Golfs — Deployment & Operations Runbook

**What this is:** the complete guide to running the 24/7 autonomous Mas Golfs broadcast on real hardware, for real, forever. Read it end to end once, then use the checklists in §6 as the daily routine.

**The machine plan in one line:** the **8GB MacBook Pro is the dedicated broadcast box** for the web build, and there is **no warm spare**. The **128GB MacBook Pro stays untouched** — it is Mason's workhorse for Phantom and everything else, and the stream must never compete with it for CPU, RAM, or attention. The **16GB MacBook Air is off-limits entirely** — it was Mason's grandpa's computer and holds all of his poems and writing; his grandma wants to publish that material. It is never touched, repurposed, or used for the stream in any way.

**The stack in one line:** web build (static page, ~$0) → OBS Studio → Restream Free (YouTube Live + Twitch) → later, TikTok Live when eligible. Everything free-tier. The Unreal build, when it comes, needs a GPU box or cloud GPU — it does not run on any of these Macs (§7).

**Principles:**
- The stream must survive a power cut, a crash, a reboot, and a macOS update without a human.
- The 128GB MBP is never the stream box. No exceptions, no "just for tonight."
- The 16GB MacBook Air is never touched for this project. It is grandpa's writing archive, not a spare. No exceptions, no "just for a failover test."
- One alert per incident. If Mason is paged twice for the same cause, that is a bug, not an incident.
- If it isn't written down, it didn't happen. Every failure gets a line in the ops log (§6.4).

---

## 0. The three machines

| Machine | Role | Why |
|---|---|---|
| **MacBook Pro, 128GB RAM** | **Mason's workhorse — NOT the stream box** | Runs Phantom coding agents and all of Mason's work. The stream never runs here. It is only ever a *viewer* and a *monitor* of the stream, never a producer. |
| **MacBook Pro, 8GB RAM** | **Primary broadcast box** | Dedicated, always-on. OBS + a browser + NodeCG + Kokoro TTS are light enough for 8GB — with the memory discipline in §3.2. It has a fan, which matters for a 24/7 encoder. Plugged in, lid open or in clamshell, never sleeps. |
| **MacBook Air, 16GB RAM** | **OFF-LIMITS — never used** | This was Mason's grandpa's computer. It holds all of his poems and writing, and his grandma wants to publish that material. It is a writing archive, not a spare. It is never touched, repurposed, powered on for this project, or used for the stream in any way — not even as a failover. |

**Why the 8GB MBP:** it is the machine Mason chose to dedicate, and it is a good choice for a 24/7 encoder: it has a fan (the Air does not), so sustained encoding loads are handled by active cooling instead of thermal throttling. There is no spare machine — that is the honest consequence of the Air being off-limits, and the failover plan in §8.5 is built around that fact instead of pretending otherwise.

### What 8GB changes (read this first)

The web build runs fine on 8GB — OBS + a browser + NodeCG + Kokoro TTS are light — but headroom is thin, and that changes how the box is run:

- **Swap pressure is the failure mode to watch.** On 8GB, the browser and OBS will fight for memory during long runs. A swap-thrashed encoder drops frames first, so the watchdog watches swap, not just RAM (§4.1), and the box runs with the memory discipline in §3.2: nothing else open, browser tab discipline, Kokoro Docker memory-limited, Balanced quality tier as the default.
- **The first upgrade trigger is sustained swap or dropped frames.** If the 8GB MBP shows sustained swap pressure or drops > 1% of frames for two consecutive weeks, that is the signal to accelerate the Unreal GPU-box plan (§7.1) — there is no bigger Mac to move the broadcast to. Do not wait for a dead stream to make that call.
- **There is no spare, so recovery is different.** If the 8GB MBP dies, there is no second machine to fail over to. The recovery paths are: repair/restart the box, or fall back to a rented cloud GPU / the web build hosted elsewhere (§8.5). The watchdog, the daily restart, and the auto-recovery exist precisely because this box is the only box.
- **Nothing else changes.** The multistream architecture, the TikTok plan, the Unreal path, and the failure modes are all the same. 8GB is a constraint on the box, not on the show.

**Why not the 128GB MBP:** it is the most powerful machine and therefore the worst choice. It runs Phantom agents, builds, and Mason's actual work. A 24/7 encoder on it means: thermal throttling during builds, fan noise during calls, a stream that dies the day Mason takes the laptop to a meeting, and a stream that competes with the thing that pays for everything. Separation is the whole point.

---

## 1. Machine setup (per machine)

Do this on the 8GB MacBook Pro. There is no second machine to repeat it on — the Air is off-limits and the 128GB MBP is Mason's workhorse — so this one box has to be configured right the first time.

### 1.1 macOS power settings (the reliable route: `pmset`)

System Settings panes move between macOS versions; `pmset` does not. Run these in Terminal (admin password required once):

```bash
# Never sleep, on charger or battery
sudo pmset -a sleep 0
sudo pmset -a displaysleep 0
sudo pmset -a disksleep 0
# Restart automatically after a power failure
sudo pmset -a autorestart 1
# Never power-nap/wake for network access in a way that disturbs the encoder
sudo pmset -a powernap 0
sudo pmset -a womp 0
# Verify
pmset -g
```

Then in **System Settings → General → Software Update**: turn **off** "Install macOS updates" automatic install, and turn **off** "Install app updates from the App Store" automatic install. Updates are applied by hand on Sunday (§6.2), never by the machine at 3am. An unattended macOS update rebooting the broadcast box mid-round is the most avoidable outage in this whole document.

**Screen lock:** System Settings → Lock Screen → "Require password after screen saver begins or display is turned off" → **Never** (on the broadcast box only — it has no personal data on it). The display may still turn off; the machine must not lock or sleep.

### 1.2 Lid behavior

A MacBook with the lid closed sleeps — unless it is in **clamshell mode**: lid closed, connected to power, connected to an external display, and with an external keyboard/mouse (Bluetooth counts). Two acceptable setups:

- **Lid open (recommended for the 8GB MBP).** Simplest and most reliable. The MBP sits on a desk or a small stand, lid open, display brightness at minimum (or display off via `pmset displaysleep`), plugged in. No clamshell edge cases, no wake failures, and you can see at a glance that it is alive. Lid open also keeps the fan vents and exhaust unobstructed.
- **Lid closed in clamshell.** Only if the desk demands it. Requires a real external display attached and powered, plus an external keyboard or mouse. Test it: close the lid, confirm the stream keeps running for 10 minutes, then open the lid and confirm nothing glitched. If it ever fails the test, go back to lid open.

**Never** run the broadcast box with the lid closed and no external display. That is just a sleeping laptop.

### 1.3 Thermal and ventilation

- The 8GB MBP has a fan — one reason it is the primary. Keep it on a hard surface or a laptop stand with airflow underneath, vents and exhaust unobstructed — never on fabric, never in a closed drawer or cabinet, never with anything stacked on it.
- Keep the room under ~26°C / 79°F. The MBP will thermal-throttle before it shuts down; throttling shows up first as dropped encoder frames, which is exactly the failure you are trying to avoid.
- Check once a month: Activity Monitor → CPU and Memory (watch swap, not just RAM — §4.1), and OBS's dropped-frames counter (§5). Dust the vents (compressed air, machine off).
- (The Air is not a spare and is never used — see §0. There is nothing else to keep ready.)

### 1.4 Auto-login and auto-start

The broadcast box must come back up unattended after any reboot:

1. **Auto-login:** System Settings → General → Login Items → enable automatic login for the dedicated `masgolfs` user account (see §1.5). No FileVault unlock prompt can be answered by a watchdog, so if FileVault is on, the box cannot self-recover after a power cut — **turn FileVault off on the broadcast box** (it holds no personal data).
2. **Login Items:** add OBS Studio, the NodeCG start script, and the Kokoro TTS service to Login Items (or, better, launch them from a single `launchd` agent — see §4.2).
3. **Test it:** reboot the 8GB MBP, walk away, come back in 5 minutes. OBS should be open, the stream should be live, NodeCG should be serving graphics. If any step needs a click, fix the automation, not the checklist.

### 1.5 Accounts and hygiene

- Create a dedicated macOS user account **`masgolfs`** on the 8GB MBP. The stream runs as this user, not as Mason's account. No personal email, no iCloud, no personal files on the broadcast box.
- The broadcast box holds exactly: OBS, NodeCG, the web build, Kokoro, Restream credentials (in the macOS Keychain), and the ops log. Nothing else. No browser with Mason's sessions, no Slack, no code editor.
- **Disk:** keep at least 20GB free at all times. OBS replay-buffer clips and NodeCG logs are the only things that grow; a weekly cleanup job (§4.2) deletes clips older than 7 days and rotates logs.

---

## 2. Software stack — install order

Install in this order on the 8GB MacBook Pro. There is no second machine to repeat it on. Do not skip ahead: each layer is tested before the next is added.

### Step 1 — The web build (the show itself)

1. Clone the repo: `git clone https://github.com/masonwyatt23/mas-golfs.git ~/mas-golfs`
2. The web build is a static page. Serve it locally (never from `file://` — some browser features behave differently):
   ```bash
   # Python's built-in server is enough; it serves one static page
   cd ~/mas-golfs && python3 -m http.server 8080
   ```
   Or use `npx serve` if Node is already installed for NodeCG. Either is fine; pick one and use it on both machines.
3. Open `http://localhost:8080` in Chrome. Confirm: the 3D broadcast plays, Mas swings, the scorebug and 59 Watch show, no console errors. Leave this tab open — it is a scene source in OBS (§3.1).

### Step 2 — OBS Studio (free)

1. Download from [obsproject.com](https://obsproject.com) (Apple Silicon build for both machines).
2. Import the scene collection (see `docs/broadcast-stack.md` §2 for the 8 scenes). The critical sources:
   - **Window Capture** (or Browser Source) pointed at the local web build — this is the picture.
   - **Browser Sources** pointed at the NodeCG graphics URLs (scorebug, lower-thirds, ticker, leaderboard) — these are the overlays.
   - **Audio:** Kokoro TTS output + the ambient bed (see Step 4).
3. Set the output per §3.2. Run the 1-hour smoke test from `docs/qa-plan.md` §2 before going further.

### Step 3 — NodeCG (free, open source)

1. Install Node.js LTS (from [nodejs.org](https://nodejs.org) — LTS only, never a beta on the broadcast box).
2. Install NodeCG and the `mas-golfs` bundle from `~/mas-golfs/nodecg-bundle/` (see its README for install, preview URLs, and OBS browser-source URLs).
3. NodeCG serves the graphics and subscribes to the sim event bus on `ws://localhost:4456` (see `docs/broadcast-stack.md` §1).
4. Test: run the bundle in demo mode (`MAS_GOLFS_DEMO=1`) and confirm the scorebug, leaderboard, and lower-thirds render in OBS. Then switch to live mode and confirm they update from real events.

### Step 4 — Kokoro TTS (free, self-hosted)

1. Per `docs/voice-options.md` §2/§8: run Kokoro-82M via Kokoro-FastAPI in Docker.
2. Install Docker Desktop for Mac (free for personal use) on the 8GB MBP.
3. Pull and run the Kokoro-FastAPI image with the two voices configured: host `am_michael`, color `af_sky`. **Memory-limit the container** (`--memory 2g`) — on an 8GB box, an unbounded Docker allocation is a swap-pressure incident waiting to happen (see §3.2).
4. Test: generate one decision line and one result line, confirm the audio plays through OBS, and confirm the ambient bed ducks under it (see `docs/broadcast-stack.md` §5–§6).

### Step 5 — Restream (free tier)

1. Create the Restream account (see §3.3 for the free-tier facts, verified November 2026).
2. Add the two channels: **YouTube Live** and **Twitch**.
3. In OBS, set the stream service to Restream (custom RTMP with the Restream ingest URL + stream key from the Restream dashboard).
4. Test: go live to both, confirm both platforms show the stream, confirm chat appears in Restream's merged chat.

### Step 6 — Verify the whole chain

Run the go-live checklist from `docs/qa-plan.md` §6. One unchecked item = no launch. Then run the 12-hour overnight soak (§2 in the QA plan) before the 7-day go-live gate.

---

## 3. Multistream architecture

### 3.1 The chain

```
Web build (localhost:8080) ─┐
NodeCG graphics ────────────┤
Kokoro TTS + ambient bed ───┤
                            ▼
                    OBS Studio (8GB MBP)
                            │  one RTMP push, 1080p60
                            ▼
                    Restream (free)
                     ┌──────┴──────┐
                     ▼             ▼
              YouTube Live     Twitch
                     (later) TikTok Live — see §3.4
```

One GPU renders once. One encoder encodes once. Restream distributes to everyone at zero marginal cost. Never pixel-stream per viewer, never run a second encoder for a second platform.

### 3.2 OBS output settings (the broadcast box)

| Setting | Value | Why |
|---|---|---|
| Resolution | 1920×1080 | The web build renders at 1080p; do not upscale a 720p canvas |
| Frame rate | 60 fps | Golf needs 60 — the swing and the tracer smear at 30 |
| Encoder | Apple VideoToolbox H.264 (hardware) | Hardware encoding keeps CPU free for the browser and NodeCG; x264 software encoding on the 8GB MBP would fight the 3D render |
| Bitrate | 8,000 Kbps CBR | Restream passes it through; YouTube and Twitch both accept it |
| Keyframe interval | 2 s | Standard for live; required by most platforms |
| Audio | AAC, 160 Kbps, 48 kHz | Commentary + bed |

**Upload bandwidth needed:** ~10 Mbps sustained upload minimum (8 Mbps video + audio + overhead + headroom). Test with a speed test from the 8GB MBP's actual network connection, at the time of day the stream runs. If the MBP is on Wi-Fi, move it to Ethernet (USB-C adapter) — Wi-Fi jitter is the single most common cause of dropped frames on an otherwise healthy box.

**8GB memory discipline (the box only works if this is enforced):**

- **Nothing else runs on the broadcast box.** No Slack, no code editor, no extra browser windows. OBS + one Chrome window (the web build tab + the NodeCG graphics tabs) + NodeCG + Kokoro. That is the whole machine.
- **Browser tab discipline:** the web build tab stays open and nothing else does. Every extra tab is memory the encoder does not have.
- **Balanced quality tier is the default on 8GB.** The web build's capability tiers (High / Balanced / Lite, see `docs/performance-audit.md`) default to Balanced on this box — High is not for 8GB. If frames drop, the quality controller steps down; do not force High by hand.
- **Kokoro Docker is memory-limited to 2 GB** (§2, Step 4). Docker Desktop itself gets a 3 GB allocation cap in its settings.
- **Watch swap, not RAM.** Activity Monitor → Memory → Swap Used is the number that matters. Sustained swap growth over a round is the early warning (§4.1, check 6); the first upgrade trigger is sustained swap or dropped frames (§0, "What 8GB changes").

### 3.3 Restream Free — verified facts (November 2026)

Sources: Restream's pricing page and help center, as reported by third-party pricing trackers checked October–November 2026.

- **Cost:** $0, no end date.
- **Channels:** **2 at once.** That is YouTube Live + Twitch. A third channel needs Standard ($19/month, 3 channels) or higher.
- **Branding:** Restream branding appears on streams. Note the important detail: the watermark shows on streams from Restream *Studio* (the browser studio). When streaming from OBS, the logo shows only in the Restream preview, not on the stream viewers see. We stream from OBS, so this is a non-issue in practice.
- **Recording:** effectively none on Free (a 15-minute recording trial in the first 7 days only). **Do not rely on Restream for recordings.** The replay buffer and OBS's own recording (§3.5) are the recording path.
- **Quality:** Restream passes through your original resolution and frame rate with no bitrate limits of its own. 1080p60 from OBS arrives as 1080p60.
- **Stream duration:** Restream does not cap how long a live encoder stream runs, but its help center suggests restarting every 24 hours because its servers can be restarted for maintenance. **We restart daily anyway** (§4.3) — and YouTube's own archive truncates live streams at 12 hours, so the daily restart also gives us clean 12-hour VOD boundaries.

**When to pay:** Standard ($19/mo) buys the third channel (TikTok) and removes branding. That is a decision for the day TikTok goes live (§3.4), not before. Until then, Free is the correct plan.

### 3.4 TikTok Live — the hard one (starts later)

**Honest status: TikTok is the third channel, and it starts later, when eligible. Do not plan the launch around it.**

Verified facts (TikTok's own help pages, as of November 2026):

- **Eligibility gate:** to go LIVE you must be **at least 18** and have **at least 1,000 followers** (the follower number may vary by region). Account in good standing, no recent LIVE suspension. Meeting the requirements does not guarantee immediate access — TikTok can delay rollout to new accounts, and trial access can be revoked if you do not go live for at least 25 minutes twice in your first week.
- **Desktop route 1 — TikTok LIVE Studio:** TikTok's free desktop app. **Windows only as of May 2026 — there is no macOS version.** Our broadcast box is a Mac, so LIVE Studio is not an option for us.
- **Desktop route 2 — OBS + RTMP stream key:** the route that works on a Mac. TikTok hands out a server URL and stream key to accounts with **RTMP access** — but **not every account with LIVE access has RTMP access.** The key appears on TikTok's LIVE Center producer page (`livecenter.tiktok.com/producer`) after you click Go LIVE in a desktop browser. Keys expire after a period of inactivity.
- **Simultaneous streaming is permitted** under TikTok's Terms of Service as of 2026 — going live on TikTok and Twitch at the same time is allowed.
- **TikTok Live is capped at 30 fps** as of 2026. A 60 fps feed sent to TikTok is wasted; the vertical format is also a separate layout problem (see below).

**What this means for Mas Golfs:**

1. **Phase 1 (launch): YouTube Live + Twitch only, via Restream Free.** TikTok gets clips (Shorts/Reels/TikTok from the clip pipeline) but no live stream. Clips are how the TikTok follower count grows toward 1,000.
2. **Phase 2 (at 1,000 TikTok followers): check RTMP access.** Open the LIVE Center producer page. If a stream key appears, TikTok is reachable from OBS. If no key appears, the account has LIVE access but not RTMP access — keep posting clips and re-check monthly; do not buy anything or use a sketchy third-party relay to force it.
3. **Phase 3 (RTMP confirmed): add the third channel.** Two options, in order:
   - **Restream Standard ($19/mo)** — adds the third channel, removes branding, and keeps one OBS push. Simplest, and the only option that keeps the "one encoder" architecture.
   - **OBS Multi-RTMP plugin (free)** — a second RTMP push directly from OBS to TikTok's ingest, bypassing Restream. Free, but it doubles the 8GB MBP's upload bandwidth and encoder load, and the TikTok push is a separate thing to monitor and restart. Only if Standard is refused for some reason.
4. **The vertical problem:** TikTok Live is a vertical surface. The broadcast is 16:9 horizontal. Sending the horizontal feed to TikTok is acceptable for a golf stream (viewers watch landscape video on TikTok all the time), but the real answer is Restream Professional's dual-format streaming (horizontal to YouTube, vertical to TikTok in the same broadcast) — which is $49/mo and a decision for much later, after TikTok proves it brings viewers. Do not build a vertical layout before the audience exists.

### 3.5 Recording and the clip pipeline

Restream Free does not record. The recording path is local, on the 8GB MBP:

- **OBS Replay Buffer:** always on, 60-second buffer. Drama-scored moments save automatically (see `docs/broadcast-stack.md` §3.5 and `docs/launch-playbook.md` §1).
- **OBS recording:** the full stream is recorded locally to disk in parallel (same 1080p60 settings). This is the archive and the clip source. Disk math: ~4 GB/hour at 8,000 Kbps, ~96 GB/day. **That will fill the MBP's disk in days.** The weekly cleanup job (§4.2) deletes recordings older than 7 days, and the clip pipeline extracts the keepers daily. If disk pressure becomes a problem, record at 6,000 Kbps or attach an external SSD for recordings only — never let the boot disk fill.
- **The clip pipeline** (`clip-pipeline/`) reads the event log and the replay saves and produces the daily clip manifest. It runs on the 8GB MBP, on a schedule, unattended.

---

## 4. The 24/7 watchdog and auto-recovery

The show must run with no human in the loop. The watchdog is the difference between "autonomous" and "a stream that stops at 3am."

### 4.1 What is watched (in priority order)

| # | Check | Interval | Failure means |
|---|---|---|---|
| 1 | Is OBS streaming? (RTMP connected, frames flowing) | 30 s | Stream is down |
| 2 | Is the web build rendering? (page responds, no console errors, frames advancing) | 60 s | The picture is frozen or dead |
| 3 | Is the event bus alive? (last event < 60 s old) | 60 s | Sim stalled — the show stopped thinking |
| 4 | Is NodeCG serving graphics? (HTTP 200 on the graphics URLs) | 60 s | Overlays are dead |
| 5 | Is Kokoro responding? (test synthesis < 5 s) | 5 min | Commentary is silent |
| 6 | Is GPU memory flat? (no growth > 10% over a round) | 15 min | The memory leak is back — see `docs/performance-audit.md` P0-1 |
| 6b | Is swap pressure flat? (Swap Used not growing over a round) | 15 min | On 8GB, swap growth is the early warning — sustained swap means the box is out of headroom; see §0, "What 8GB changes" |
| 7 | Is the disk above 20GB free? | 15 min | Recordings will fill the disk |
| 8 | Is the network up? (upload > 5 Mbps) | 60 s | The 8GB MBP is offline |

### 4.2 The watchdog itself

A small shell script + `launchd` agent on the 8GB MBP (free, built into macOS — no paid monitoring tool):

- **`launchd` agent** (`~/Library/LaunchAgents/com.masgolfs.broadcast.plist`): starts on login and keeps alive, in order: the local web server → NodeCG → Kokoro (Docker) → OBS. If any process exits, `launchd` restarts it. This is the first line of defence and it needs no code — it is macOS doing what macOS does.
- **Watchdog script** (`~/mas-golfs/ops/watchdog.sh`, run every 30 s by a second `launchd` agent): performs the checks in §4.1 in order. On failure it acts, then logs, then (only for the five paging failures in §5.3) alerts Mason.
- **Weekly cleanup job** (a `launchd` agent on a Sunday 03:00 schedule): deletes OBS recordings older than 7 days, deletes replay saves older than 7 days, rotates NodeCG and watchdog logs, runs `git pull` in `~/mas-golfs` to pick up repo updates, and restarts the stack cleanly if an update landed.
- **The watchdog watches itself:** the watchdog script touches a heartbeat file every run. A third tiny `launchd` agent checks the heartbeat file every 5 minutes; if it is stale, it restarts the watchdog and pages Mason ("watchdog itself down" — one of the five paging failures).

### 4.3 Restart order (the only order that works)

When anything restarts — crash, reboot, power cut, or the daily restart — the order is always:

1. **Local web server** (the picture). Wait for `http://localhost:8080` to respond.
2. **NodeCG** (the graphics). Wait for the graphics URLs to return 200.
3. **Kokoro** (the voices). Wait for a test synthesis to return audio.
4. **OBS** (the encoder). Start streaming to Restream last, only after 1–3 are healthy.

Starting OBS before the web build is up means streaming a black screen or a browser error page to two platforms. The watchdog enforces the order with health checks between steps, not with fixed sleeps.

### 4.4 The daily restart (03:00 local)

Every day at 03:00, the watchdog performs a clean, ordered restart of the whole stack:

- Stop OBS streaming → stop OBS → stop NodeCG → stop Kokoro → stop the web server.
- Start everything again in the §4.3 order.
- Verify the stream is live on both YouTube and Twitch before declaring success.

**Why daily:** Restream suggests restarting every 24 hours for maintenance; YouTube's archive truncates at 12 hours, so a daily restart gives clean VOD boundaries; and a daily restart bounds the blast radius of any slow leak or drift to one day. 03:00 is the lowest-viewership hour. The restart takes ~2–3 minutes. Viewers see the **intermission card** in OBS during the gap (an OBS scene, not a dead stream) — see §4.5.

### 4.5 The "pee break" intermission

The stream never just goes dark. Every planned break — the daily restart, a Sunday update, a model swap — cuts to a branded intermission card: Mas taking a quick break, "back in a moment" energy, a tasteful pee-break joke, the scorebug still visible, and a countdown. The round state is persisted before the break, so the stream resumes exactly where it left off — same hole, same score, same 59 Watch state.

Rules: intermissions are planned, never accidental (a crash shows the same card, but the watchdog logs it as an incident, not a break); the card always says when the show returns; the longest planned intermission is the Sunday macOS update at ~30 minutes, announced in advance; the daily restart intermission is ~2–3 minutes. An intermission is a feature of the show — it makes the stream feel like a live broadcast with a host who takes breaks, not a server that went down.

---

## 5. Remote access and monitoring

Mason monitors from the 128GB MBP. He never touches the broadcast box unless something is broken.

### 5.1 How Mason checks the stream

From the main MacBook, in order of usefulness:

1. **Watch the stream itself** — open the YouTube Live or Twitch page. If the picture is moving and the scorebug is fresh, the show is healthy. This is the only check that matters most of the time.
2. **The status dashboard** — a single static page (served from the 8GB MBP, or a simple status file in the repo) showing: stream uptime, current round/hole/score, 59 Watch state, last event time, GPU memory trend, disk free, and the last watchdog action. One page, six numbers, no login. See `docs/analytics.md` §4 for the dashboard panels.
3. **Restream dashboard** — confirms both channels are receiving, with bitrate and dropped-frame counts per destination.

### 5.2 Remote access to the broadcast box (for fixes only)

- **Screen Sharing (built into macOS):** enable it on the 8GB MBP for the `masgolfs` user, restricted to the local network + Tailscale (see below). Mason connects from the 128GB MBP only when something needs hands-on fixing.
- **Tailscale (free tier):** install Tailscale on the 8GB MBP and the 128GB MBP. It puts both machines on one private network with no port forwarding and no public exposure. This is how Mason reaches the 8GB MBP from anywhere. **Do not expose the 8GB MBP to the public internet** — no open ports, no public SSH, no VNC on the open internet. (The Air is not on Tailscale and never will be — it is grandpa's archive, not part of this network.)
- **SSH:** enabled on the 8GB MBP for the `masgolfs` user, key-only (no password auth), reachable only via Tailscale. This is the fast path for restarts and log checks: `ssh masgolfs@mbp8 "tail -50 ~/mas-golfs/ops/watchdog.log"`.

### 5.3 What Mason sees when something is wrong (alerting)

Deliberately narrow — only five things page Mason (from `docs/analytics.md` §6). Everything else waits for the Sunday review.

| Alert | Means | First action |
|---|---|---|
| Stream down > 5 min | OBS is not streaming and the watchdog could not restart it | Check the status dashboard; SSH in; check §8.1 |
| Event bus silent > 60 s | The sim stalled | SSH in; restart the web build; check §8.2 |
| GPU memory climbing > 10% over a round | The memory leak is back | SSH in; restart the stack; file it as a bug, not an incident |
| WebGL context lost | The browser lost the 3D context | The context-lost recovery should handle it; if it recurs, restart the browser |
| Watchdog itself down | The heartbeat file is stale | SSH in; restart the watchdog agent; this is the one that means "go look now" |

**Alert rules:** one alert per incident (the watchdog suppresses repeats for 30 minutes). No pages 21:30–09:00 except stream-down. A repeat alert for the same cause is a bug, not an incident — fix the cause, don't silence the alert.

---

## 6. The operator checklists (what a human still does)

The system is autonomous. The human does the things only a human can do: judgment, taste, and relationships. Everything else runs itself.

### 6.1 Daily (5 minutes, any time)

- [ ] Glance at the stream (YouTube or Twitch): picture moving, scorebug fresh, 59 Watch state sane.
- [ ] Glance at the status dashboard: uptime, disk free, last watchdog action.
- [ ] Approve today's clips from the clip pipeline's daily queue (the manifest is generated automatically; Mason picks which 1–2 go out — see `docs/launch-playbook.md` §1 and `docs/content-calendar-60-day.md`).
- [ ] Reply to any comments/DMs that need Mason (the community, not the machine).

### 6.2 Weekly — Sunday, 30 minutes (the review ritual)

From `docs/analytics.md` §5:

- [ ] **5 min mechanical:** fill the weekly tracking sheet, pull the dashboard, note any alerts from the week.
- [ ] **20 min on four questions:** Is the machine healthy? Is the audience compounding? What do the clips say? What is Mas doing?
- [ ] **5 min writing:** `docs/reviews/review-<date>.md`, four lines.
- [ ] **Machine care:** apply any pending macOS updates by hand (never automatic), `git pull` the repo on the 8GB MBP. Check Swap Used while you are there — any sustained growth is the first upgrade trigger (§0).
- [ ] **Guest scheduling:** confirm next week's guest twin (see `docs/guest-twins.md` §6) if one is booked.

### 6.3 Monthly

- [ ] Recovery drill (there is no spare — this replaces the failover drill): power the 8GB MBP fully off, power it back on, and confirm the whole stack comes back unattended in §4.3 order with the stream live — no clicks. Target: under 10 minutes from power-on. Then confirm the cloud fallback is still staged (§8.5): the RunPod template exists and the static-host fallback page is current. The drill is the only way to know either path works.
- [ ] Disk and thermal check on the broadcast box (Activity Monitor, OBS dropped frames, vent cleaning).
- [ ] Review the Restream/TikTok position: TikTok follower count vs. the 1,000 gate; if RTMP access appears, plan Phase 2 (§3.4).
- [ ] Review the 30/60/90-day milestones from `docs/launch-playbook.md` §7.

### 6.4 The ops log

`~/mas-golfs/ops/ops-log.md` on the 8GB MBP (and committed to the repo monthly). One line per incident:

```
2026-11-14 03:02 — Daily restart took 4 min (Kokoro slow to start). No viewer impact.
2026-11-16 14:22 — Stream down 6 min. Cause: Wi-Fi dropout. Fix: moved the 8GB MBP to Ethernet.
```

If it isn't written down, it didn't happen. The ops log is how a one-off becomes a pattern, and a pattern becomes a fix.

---

## 7. The upgrade path to Unreal

The 8GB MBP runs the web build. It does **not** run Unreal. Know the trigger points in advance so the upgrade is a decision, not a crisis.

### 7.1 When the web build outgrows the 8GB MBP

Upgrade when **any** of these is true for two consecutive weeks:

- OBS drops > 1% of frames at 1080p60 on the 8GB MBP (the web build is too heavy for the machine).
- Sustained swap pressure (Swap Used growing over a round, §4.1 check 6b) — the box is out of headroom, and there is no bigger Mac to move to.
- The web build can no longer hold 60 fps at the visual quality the show needs (see `docs/performance-audit.md` and `docs/qa-plan.md` §3).
- The Unreal vertical slice passes its go/no-go (see `docs/unreal-vertical-slice.md`) and the decision is made to go Unreal for real.

### 7.2 The Unreal hosting options (costs verified November 2026)

The architecture does not change: **render once, broadcast to everyone.** One Unreal instance on one GPU renders the show; OBS captures it; a single RTMP push goes to Restream. Never pixel-stream per viewer (that costs ~$0.50–$1.20 per viewer per hour and is ruinous at any audience size).

| Option | Cost | Notes |
|---|---|---|
| **RunPod Community GPU, RTX 4090** | ~$0.34/hr ≈ **$248/mo** | Cheapest cloud option. Evictable (spot) — the instance can be reclaimed. Fine for testing, risky for 24/7. |
| **RunPod Secure GPU, RTX 4090** | ~$0.69–$0.89/hr ≈ **$500–$650/mo** | Non-evictable. The honest cloud price for 24/7. |
| **AWS g5.xlarge** | ~**$727/mo** | The expensive cloud option. Only if RunPod is unavailable. |
| **Own RTX 4090 box** | **~$2,500–$3,000 one-time + ~$35–$52/mo power** | Pays for itself in 3–6 months vs. cloud. The right answer once the show is real. |
| **Vast.ai** | Varies | Build and test only, not 24/7. |

**The sequence:** build and validate the Unreal slice locally (zero 24/7 spend until go/no-go passes) → if it passes, rent a RunPod Secure 4090 for one month to prove 24/7 stability → if the show is working and growing, buy the box. Do not buy hardware before the slice passes. Do not rent cloud before the slice passes.

### 7.3 What changes when Unreal arrives

- The 8GB MBP stops being the render box and becomes the **broadcast controller**: OBS, NodeCG, Kokoro, and Restream stay on the MBP (they are light). The GPU box (or cloud instance) renders Unreal and sends its picture to the MBP over NDI or a capture card.
- The web build does not go away: it stays live as the prototype, the clip factory, and the fallback if the Unreal box dies. The failover for Unreal is the web build on the 8GB MBP — the show never goes dark because a GPU died.
- The Macs still do not run Unreal. Unreal on Apple Silicon exists, but the broadcast stack (Lumen, Nanite, DLSS) is built for NVIDIA, and the 128GB MBP is still never the stream box.

---

## 8. Failure modes and recovery times

| # | Failure | Symptom | Recovery | Time |
|---|---|---|---|---|
| 8.1 | OBS crash | Stream goes dark on both platforms | `launchd` restarts OBS; watchdog verifies stream is live | < 2 min, automatic |
| 8.2 | Web build stalls (event bus silent) | Picture frozen, scorebug stale | Watchdog restarts the browser tab / web server; if it recurs, restart the whole stack in §4.3 order | < 3 min, automatic |
| 8.3 | NodeCG crash | Overlays disappear, picture continues | `launchd` restarts NodeCG; graphics reappear on next event | < 1 min, automatic |
| 8.4 | Kokoro down | Commentary silent, bed continues | Watchdog restarts Docker container; if it fails, commentary is disabled (the show continues silent — silence is acceptable, a dead stream is not) | < 2 min, automatic |
| 8.5 | 8GB MBP dies (hardware) | Everything down | **There is no spare machine.** Recovery, in order: (1) repair/restart the box — most "deaths" are a dead charger, a swollen battery, or a stuck boot, all fixable same-day; (2) if the box is truly dead, **rent a cloud GPU** (RunPod Secure RTX 4090, ~$0.69–$0.89/hr) and run the stream from it — the repo, the OBS scene collection, and the NodeCG bundle are all in GitHub, so a fresh cloud instance can be streaming in ~30–60 min if the template is pre-staged (§6.3 drill); (3) if even that is not possible, **host the web build on a static host** (GitHub Pages / Vercel free tier) and point OBS on the 128GB MBP at it as a *temporary* emergency measure only — the 128GB MBP is still never the stream box, this is a bridge of hours, not a plan. Honest times: restart/repair same day if fixable; cloud fallback ~30–60 min once staged, hours if it was never staged — which is why the monthly drill stages it | Minutes (restart) to ~1 hr (cloud), hours if unprepared |
| 8.6 | Power cut (whole room) | Everything down | `autorestart 1` brings the 8GB MBP back when power returns; auto-login + `launchd` bring the stack back in §4.3 order. No human needed unless the power cut outlasts the UPS (there is no UPS — see below) | Automatic on power return + ~5 min |
| 8.7 | Internet outage | Stream down, local stack healthy | Nothing to do locally. The watchdog keeps the stack running and reconnects when the network returns. OBS reconnects to Restream automatically. If the outage exceeds 1 hour, post a note on social that the stream will be back | Automatic on network return |
| 8.8 | Restream outage | Both destinations down, OBS healthy | OBS reconnects automatically. If Restream is down > 30 min, switch OBS to stream directly to YouTube Live (bypassing Restream) as a temporary measure — the stream key is in the Keychain | < 5 min, manual |
| 8.9 | YouTube or Twitch outage (one platform) | One destination dark, the other live | Nothing to do. Restream keeps sending to the healthy platform. Note it in the ops log | N/A |
| 8.10 | macOS update reboot | Stream down during the update window | Updates are manual-only (§1.1), done on Sunday, with the stream announced as "back in 30 minutes." Never automatic | Planned, ~30 min |
| 8.11 | WebGL context lost | 3D picture goes black, overlays continue | The context-lost recovery in the web build (see `docs/performance-audit.md` P2) restores it. If it recurs 3× in an hour, the watchdog restarts the browser | < 30 s, automatic |
| 8.12 | Disk full | Recordings stop, OBS errors | Weekly cleanup (§4.2) prevents this. If it happens anyway, the watchdog deletes the oldest recordings immediately and pages Mason | < 5 min, automatic + alert |

**The one thing this runbook does not cover:** a UPS. The 8GB MBP has a battery — a power cut does not kill it immediately, which is one more reason the broadcast box is a laptop and not a desktop. A desktop GPU box for Unreal (§7) will need a UPS; buy it with the box, not after the first outage.

---

## 9. Quick reference (print this)

```
PRIMARY:  MacBook Pro 8GB   — the broadcast box. OBS + web build + NodeCG + Kokoro.
SPARE:    NONE — there is no spare machine.
NEVER:    MacBook Pro 128GB — Mason's workhorse. Viewer and monitor only.
NEVER:    MacBook Air 16GB  — grandpa's writing archive. Never touched, ever.

STREAM:   OBS → Restream Free → YouTube Live + Twitch (1080p60, 8,000 Kbps)
TIKTOK:   Later — 1,000 followers first, then check RTMP access. Windows LIVE
          Studio does not exist on Mac; OBS + RTMP key is the Mac route.

RESTART:  Daily 03:00, ordered: web server → NodeCG → Kokoro → OBS.
WATCHDOG: launchd keeps processes alive; watchdog.sh checks every 30 s.
ALERTS:   Only 5 things page Mason (§5.3). Everything else waits for Sunday.
FAILOVER: No spare. Box dies → repair/restart, or cloud GPU (~30–60 min if
          staged) / static-host fallback. Cold-boot recovery drill monthly.
UPGRADE:  Unreal needs a GPU box (~$2,500) or cloud (~$500/mo) — never a Mac.
```

---

## Sources

- TikTok LIVE eligibility and RTMP access: TikTok Help Center ("What is TikTok LIVE?"), TikTok LIVE Studio help, TikTok Creator Academy ("TikTok Live 101"), as reported November 2026. Key facts: 18+, 1,000 followers (varies by region), RTMP access is separate from LIVE access and not every eligible account has it, LIVE Studio is Windows-only as of May 2026, TikTok Live is capped at 30 fps.
- Restream Free plan: Restream pricing page and help center, as reported by pricing trackers checked October–November 2026. Key facts: $0, 2 channels, branding on Studio streams (not on OBS-pushed streams), no cloud recording on Free, no bitrate limits, restart suggested every 24 hours, Standard $19/mo for a third channel.
- Unreal hosting costs: RunPod and AWS pricing as reported in the November 2026 Unreal research (`docs/unreal-vertical-slice.md`).
- The rest of this runbook is drawn from the Mas Golfs repo docs: `docs/broadcast-stack.md`, `docs/qa-plan.md`, `docs/analytics.md`, `docs/launch-playbook.md`, `docs/voice-options.md`, `docs/performance-audit.md`, `docs/unreal-vertical-slice.md`.
