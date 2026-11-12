# Mas Golfs — Analytics & Observability

**The show:** a +3 digital-twin golfer, Mas — Mason's digital twin — plays 18-hole rounds on repeat, forever. The season arc is **Road to 59**: the chase for a sub-60 round. The stream never goes dark.

**Why this document exists:** an always-on autonomous broadcast that nobody watches is a screensaver, and an autonomous system nobody monitors is a blackout waiting to happen. This is the measurement system for both problems — what the audience is doing, what the machine is doing, and what to do about either. Everything here is free-tier: no paid analytics tools, no paid monitoring. The event log is the single source of truth; platform analytics are the second opinion.

**Principles that govern everything in this document:**

- **Measure regulars, not peak viewers.** Three returning viewers beat thirty strangers. (Launch playbook, §4.)
- **The numbers are the strategy.** Every weekly decision comes from the tracking sheet, not from a feeling about the week.
- **One metric must never dip: uptime.** A stream that goes dark loses the habit before it loses the audience.
- **If it isn't written down, it didn't happen.** (QA plan, appendix.) Every review, every alert, every decision lands in the log.
- **Alert on failure, review on trend.** Paging is for things that are broken now. Everything else waits for Sunday.
- **Free, always.** YouTube Analytics, Twitch analytics, and a self-hosted dashboard fed by the event log. Nothing in this document costs money.

---

## 1. What to measure on the stream

The stream has two jobs: stay up, and turn viewers into regulars. These metrics answer both, in order of importance.

### 1.1 Reliability — the metrics that must never dip

| Metric | Definition | Source | Target | Why it matters |
|---|---|---|---|---|
| Stream uptime % | Minutes live ÷ minutes in the period, excluding planned maintenance windows | OBS / Restream status + stream health API | ≥ 99% weekly; zero gaps > 30 s | The one metric that must never dip. A dark stream breaks the habit. |
| Stream gaps | Count of outages, with duration of each | OBS / Restream logs | 0 gaps > 30 s per week | One long gap costs more regulars than a week of bad clips. |
| Event-bus health | WebSocket port 4456 heartbeat + `seq` continuity | Event log, watchdog log | Zero `seq` gaps within a round; zero disconnects > 5 s | A silent bus means frozen overlays and dead commentary. (QA plan S-06.) |
| Overlay freshness | NodeCG replicant timestamps vs. sim events | NodeCG log | Scorebug ≤ 1 s after the event; leaderboard ≤ 2 s after `hole_end`; no stale data > 5 s on screen | Stale data on screen is worse than no data — viewers trust what they see. (QA plan S-08.) |
| GPU memory | `renderer.info.memory` (geometries, textures), sampled every 10 min | In-app perf HUD (press P) / DevTools | Flat across rounds: last-round value within ±5% of first-round value | Any steady climb is the P0-1 leak from the performance audit returning. (QA plan S-02.) |
| JS heap | `performance.memory`, sampled every 10 min | DevTools / in-app readout | Hour 12 within ±10% of hour 1 | A climbing heap is a crash in slow motion. (QA plan S-03.) |
| Frame rate | In-app FPS readout, sampled every 10 min | In-app readout | p50 ≥ 55 fps, p5 ≥ 30 fps (High tier, mid-range laptop); zero 10-second stretches below 20 fps | A stuttering broadcast stops feeling like a broadcast. (QA plan S-04.) |
| Watchdog actions | Every fault logged with timestamp and action | Watchdog log | Every fault handled without human input; restart restores the stream | The watchdog is the only responder. If it stops working, nothing is watching. (QA plan S-11.) |
| Rounds completed | `round_complete` events in the event log | Event log | ≥ 1 round per ~2.5 hours of wall time at broadcast speed; counter increments monotonically, never resets | The round counter is the heartbeat of the whole machine. (QA plan S-05.) |

### 1.2 Audience — the metrics that say whether it's working

| Metric | Definition | Source | Target (first 90 days) | Why it matters |
|---|---|---|---|---|
| Concurrent viewers (avg) | Average simultaneous viewers per stream session | YouTube Live + Twitch analytics | Rising month over month; no absolute target in month one | The top of the funnel. Watch the trend, not the number. |
| Returning viewers | Viewers who have watched before, as a share of total viewers | YouTube returning vs. new; Twitch unique chatters returning | Share rising week over week | **The real audience.** This is the number the whole project is optimised for. |
| Returning-viewer count | Absolute number of returning viewers per week | YouTube Analytics | Compounding: each week ≥ last week's count | Three regulars beat thirty strangers — and regulars compound. |
| Stream views | Total views of the live stream (VOD views counted separately) | YouTube + Twitch analytics | Rising with clip output | Whether the funnel is feeding the stream at all. |
| Average view duration | How long the average viewer stays | YouTube Analytics (live) | Rising; prime-time sessions longer than off-peak | A stream people leave in 2 minutes is a stream with a hook problem. |
| Follows per stream | New follows/subscribes attributed to a stream session | Twitch + YouTube analytics | Track weekly; target set at the 60-day review from the baseline | Community growth, measured at the point of commitment. |
| Chat messages per prime-time session | Messages in chat during the fixed prime-time window | Twitch chat logs | Rising; ≥ 1 message per regular per session | Community depth. Silence during prime time is the earliest warning sign. |
| Prime-time attendance | Unique viewers present during the fixed prime-time window | Twitch + YouTube analytics | Stable or rising; regulars present most weeks | Prime time is the appointment. If nobody shows up to the appointment, the appointment is wrong. |

### 1.3 Engagement — the heartbeat

| Metric | Definition | Source | Target | Why it matters |
|---|---|---|---|---|
| Predictions placed per day | Clubhouse Coins predictions staked, all markets | Coins ledger | Rising with viewership; ≥ 1 prediction per viewer per session at maturity | The engagement heartbeat. If viewers watch but never predict, the coins economy isn't landing. |
| Predictions per viewer | Predictions ÷ unique viewers, per session | Coins ledger + platform analytics | Rising toward 1.0+ | Whether the prediction mechanic is part of watching, or an afterthought. |
| 59 Watch activations | Times the 59 Watch bug turns on per round, and how long it stays on | Event log (`fifty_nine_watch` events) | Track per round; spikes are content | The signature feature. Every activation is a story the broadcast is already telling. |
| 59 Watch engagement | Chat messages + predictions placed while 59 Watch is active, vs. the same holes when it is not | Chat logs + coins ledger | Clearly higher during 59 Watch than outside it | Proof that the chase is what viewers care about — and the reason to make it louder. |
| 59 Watch peak concurrency | Concurrent viewers during 59 Watch windows vs. the round average | Platform analytics | Peak during 59 Watch > round average | If viewers show up when 59 is on the line, the season arc works. |
| Closest-to-59 board views | Clicks/views on the "closest to 59" record-book section | Dashboard / stream analytics | Track; spikes after near-misses | Near-misses (60, 61) are stories. If nobody looks at the board, the story isn't being told. |
| Chat sentiment during 59 Watch | Rough read (positive / neutral / negative) of chat during 59 Watch windows | Manual read of chat logs in the Sunday review | Positive and excited; "he's going to do it" energy | The emotional temperature of the show's best moments. Not a number to optimise directly — a number to notice. |

### 1.4 What NOT to measure on the stream

- **Peak concurrent viewers as a headline.** A raid or a clip spike tells you nothing about the show. Report the average and the returning count; mention the peak only in context.
- **Total followers as a success metric.** Follows are a lagging indicator of everything else. Track them, don't steer by them.
- **Chat volume outside prime time.** The stream runs 24/7; most hours are ambient. Measuring chat at 3am measures the wrong thing.

---

## 2. What to measure on clips

Clips are the growth engine; the stream is where growth lands. Every clip is tagged with its format in the tracking sheet, and formats are judged on a 60-day cycle — never before day 60.

### 2.1 Per-clip metrics

| Metric | Definition | Source | Target | Why it matters |
|---|---|---|---|---|
| Views (per format, median) | Median views across clips of the same format in the period | Platform analytics | Rising 60-day over 60-day; top format doubles its share next cycle | **The** format decision. Median, not mean — one viral clip must not rescue a dead format. |
| Completion rate | Share of viewers who watch to the end | Shorts / Reels / TikTok analytics | ≥ 60% on 20–35 s clips | The strongest ranking signal after the hook. A clip nobody finishes is a clip the algorithm stops showing. |
| Hook survival (1–3 s) | Share of viewers still watching at 3 seconds | Platform analytics (retention graph) | ≥ 70% at 3 s | The hook is the clip. If viewers leave in 2 seconds, the title and thumbnail did not matter. |
| Sends per reach | Shares/sends ÷ reach | Instagram + TikTok analytics | Rising; the single best predictor of breakout | Sends are the audience doing the distribution for you. The highest-leverage metric in short-form. |
| Click-through to the stream | Clicks from the clip to the stream (Related Video link, bio link, pinned comment) | YouTube Analytics / link clicks | Rising; top format should convert best | Whether clips convert, or just entertain and vanish. A clip with 100K views and zero click-through is a dead end. |
| Follows per clip | New follows attributed to a clip in the 24 hours after posting | Platform analytics | Track per format | The clip's job is not just views — it is turning scrollers into followers. |
| Comments per clip | Comments, not just likes | Platform analytics | Rising on the winning formats | Comments are the audience talking back. A clip with views and no comments is wallpaper. |
| Watch time per clip | Total watch time, per format median | Platform analytics | Rising with the format's median views | The platform's own currency. Watch time is what the algorithm actually rewards. |

### 2.2 Per-format scoreboard (60-day cycle)

Rank the five formats — best shot, worst miss, decision breakdown, record-chase update, Day X of Road to 59 (plus The coin call, per the content calendar) — on three numbers each cycle:

1. **Median views** (the reach test).
2. **Median watch time** (the quality test).
3. **Click-through to the stream** (the conversion test).

The top format doubles its share next cycle. The bottom format drops to one clip per week or is cut. One variable changes at a time — never re-cut the format, the hook, and the posting time in the same week, or the data says nothing.

**The 60-day rule:** do not judge the clip strategy before day 60. Expect the first ~30–50 clips to do little. The discovery window is measured in weeks, not months. (Launch playbook §4.2.)

### 2.3 Funnel metrics — where viewers come from

| Metric | Definition | Source | Why it matters |
|---|---|---|---|
| Funnel split | Share of stream viewers arriving from each platform (Shorts, Reels, TikTok, search, direct) | Traffic sources (YouTube + Twitch analytics) | Which platform to feed. If Instagram is the source, post more Reels; if Shorts, post more Shorts. (Launch playbook, 60-day funnel review.) |
| Clip → stream conversion rate | Stream views from clip traffic ÷ total clip views | YouTube Analytics (traffic sources) | The funnel's efficiency. A 10K-view Short brings only ~12–18 subscribers directly (0.1–0.18%) — the funnel is the whole game. (Creator growth playbook.) |
| Instagram → YouTube conversion | Mason W Golf followers who reach the stream | Link clicks, YouTube traffic sources | Whether the brand anchor is actually anchoring. |
| Guest-twin clip performance | Views and conversion on clips featuring a guest golfer's digital twin | Platform analytics | Whether the guest ladder (creator growth playbook) is worth the effort. |

---

## 3. What to measure on the sim

The sim is a machine that must stay calibrated, fast, and honest. If its numbers drift, the show stops being a golf broadcast and becomes a cartoon — and the audience will notice before Mason does.

### 3.1 Calibration — the +3 truth

These are the benchmarks from sim-engine §3 and QA plan §1.2. They do not move without a written reason.

| Metric | Benchmark | Alert band | Source |
|---|---|---|---|
| Driving distance (avg) | 265–275 yd | Outside 260–280 yd over 100 rounds | Event log, rolling 100-round window |
| Fairways hit | 55–60% | Outside 50–65% over 100 rounds | Event log |
| Greens in regulation | ~60% | Outside 55–65% over 100 rounds | Event log |
| Scoring average | 71–73 | Outside 70–74 over 100 rounds | Event log |
| Approach proximity (150 yd) | ~25–30 ft average | Outside 20–35 ft over 100 rounds | Event log |
| Putting make rate (10 ft) | ~40% | Outside 30–50% over 100 rounds | Event log |
| Birdies per round | ~3–4 | Outside 2–5 over 100 rounds | Event log |
| Bogeys per round | ~2–3 | Outside 1–4 over 100 rounds | Event log |

**Calibration drift** is the slow movement of any of these away from benchmark over a rolling 100-round window. Drift is checked weekly in the Sunday review and by the calibration harness (10,000 headless rounds, QA plan §1). A drift of more than ±5% from benchmark on any metric is a failing harness — investigate before the next render, not after the next season.

**The 59 check (QA plan §1.5):** 59 must be possible but rare — ≥ 1 round ≤ 62 in 10,000 harness rounds, and 0–2 rounds ≤ 59. If 59 never happens, the season arc is a lie. If it happens every week, it is not special. Track the harness count monthly.

### 3.2 Handicap and the learning loop

| Metric | Definition | Source | What it tells you |
|---|---|---|---|
| Live handicap index | WHS-style index, updated after every round | Event log / stat book | The story of Mas getting better (or worse) in public. |
| Handicap trend | 30-day slope of the index | Event log, weekly | Whether the learning loop is working. Flat is fine; worsening for 4+ weeks is a signal to check the one-fix rule. |
| Scoring average trend | 10-round and 30-round rolling averages | Event log | The short-term form line. The commentary's "he's hot / he's cold" has to be true. |
| Strokes-gained by category | SG off the tee, approach, around the green, putting — per round and rolling | Event log (`hole_complete` SG splits) | Where Mas is actually gaining and losing. The learning loop reads this, not the score. |
| One fix per round | The single fix chosen after each round, and whether it was applied | Event log (learning object) | The discipline of the system. More than one fix per round, or a fix that changes dispersion σ, is a bug — dispersion never changes. (Sim-engine §6, QA plan §1.4.) |
| Improvement cap | Total strokes gained by the learning loop over 200 rounds | Event log | Must stay ≤ 1.5 strokes. If Mas improves faster than that, the loop is cheating. (QA plan §1.4.) |
| Form (last-3 vs. last-10) | Scoring average over the last 3 rounds vs. the last 10 | Event log | The form line the 59 Watch probability uses. If form is wrong, the probability is wrong. |

### 3.3 Performance of the sim itself

| Metric | Definition | Source | Target |
|---|---|---|---|
| Decision latency (mean) | Time to choose a shot, mean across a round | Sim instrumentation | < 5 ms |
| Decision latency (p99) | 99th percentile decision time | Sim instrumentation | < 20 ms |
| Round simulation time | Wall time to simulate a full 18-hole round headless | Harness | < 50 ms per round (the decision budget); 10,000 rounds < 5 min |
| Event-bus latency | Sim event → NodeCG replicant update | NodeCG log | < 50 ms; strike event and ball launch share a frame |
| Determinism | Same seed → byte-identical event stream | Harness | 100% — any divergence is a bug |
| Impossible shots | Shots outside physical bounds (carry beyond club max + margin, negative spin, etc.) | Harness bounds check | Zero, ever |

---

## 4. The free-tier tooling

No paid analytics tools. No paid monitoring. The stack is: platform analytics for the audience, the event log for the machine, and one small dashboard that reads the log.

### 4.1 Platform analytics (audience, free)

| Tool | What it gives you | Cadence |
|---|---|---|
| YouTube Analytics (Studio) | Live + VOD views, returning vs. new, average view duration, traffic sources, click-through, Shorts views/retention | Weekly (Sunday review); daily glance in week one |
| Twitch analytics (Creator Dashboard) | Concurrent viewers, follows, chat activity, unique chatters | Weekly (Sunday review) |
| Instagram Insights | Reels views, reach, sends, follows, profile visits | Weekly, per clip format |
| TikTok Analytics | Views, completion, shares, follows | Weekly, per clip format |
| Restream analytics | Per-platform stream health, uptime, viewer counts across both channels | Weekly; live during any incident |

### 4.2 The self-hosted dashboard (machine, free)

One small dashboard, fed by the event log. It is not a product — it is a page that reads JSON and draws lines.

**Data source:** the sim's JSON event log (the same log the broadcast-stack event bus emits). Every event already carries a timestamp, a sequence number, and a type. Nothing new needs to be instrumented for the dashboard to work.

**What it shows (one screen, six panels):**

1. **Stream health** — uptime %, current FPS, GPU memory (flat or climbing?), heap, event-bus status (green/amber/red), rounds completed today. This panel is the one Mason glances at.
2. **The show** — Mas's current score, 59 Watch status (on/off, strokes vs. pace, probability), last-10 scoring average, live handicap, the one fix from the last round.
3. **The audience** — returning viewers this week vs. last week, follows per stream, predictions per day, chat messages per prime-time session. All as simple week-over-week lines.
4. **The clips** — per-format median views (this cycle vs. last cycle), best and worst clip of the week, click-through to the stream.
5. **The sim** — rolling 100-round calibration table (each benchmark with its alert band, green/amber/red), decision latency p99, 59-count in the harness.
6. **The coins** — predictions per day, weekly leaderboard top 5, bonus-pool balance, any anti-abuse flags.

**How it is built:** a static page (the same pattern as the web build) that reads the event log and the weekly tracking sheet. No server, no database beyond the log itself, no auth — it runs on Mason's machine or a free static host. If the log is the single source of truth, the dashboard cannot lie about the machine; it can only be out of date, which is itself visible (the "last updated" timestamp is on every panel).

**What it does NOT do:** it does not replace YouTube Analytics (the platforms own the audience numbers), it does not send alerts (see §6), and it does not store anything the event log doesn't already have.

### 4.3 The weekly tracking sheet (the strategy, free)

The tracking sheet from launch playbook §4.5, filled in every Sunday, same day, same format. It is a spreadsheet — one row per week, one column per metric:

| Metric | Source |
|---|---|
| Stream uptime % | OBS / Restream logs |
| Clips posted | Tracking sheet |
| Clip median views (per format) | Platform analytics |
| Clip click-through to stream | YouTube Analytics / link clicks |
| Stream views | YouTube + Twitch analytics |
| Returning viewers | YouTube returning vs. new |
| Follows-per-stream | Twitch + YouTube |
| Predictions placed per day | Clubhouse Coins log |
| Chat messages per prime-time session | Twitch chat logs |
| Mas's scoring average / handicap | The broadcast stat book |
| Funnel split | Traffic sources |
| 59 Watch activations + peak concurrency | Event log + platform analytics |

The sheet is the strategy. If a number is not in the sheet, it is not being managed.

### 4.4 Logs and where they live

| Log | Location | Retention |
|---|---|---|
| Sim event log (JSONL) | `~/mas-golfs/logs/events-<date>.jsonl` | 90 days hot; archive after |
| Watchdog log | `~/mas-golfs/logs/watchdog-<date>.log` | 90 days |
| OBS / Restream logs | OBS logs + Restream dashboard | Platform default |
| Coins ledger (append-only) | Economy service (SQLite) | Forever — the ledger is the audit trail |
| Clip manifests | `clip-pipeline/output/manifest_<round>.json` | Forever — the clip library is the archive |
| Weekly tracking sheet | The spreadsheet | Forever |
| Sunday review notes | `docs/reviews/review-<date>.md` (see §5) | Forever |

---

## 5. The weekly review ritual (Sunday, 30 minutes)

Every Sunday, 30 minutes, same time, same order. The review is the only management the project gets — everything else is autonomous. The ritual exists so that the one human hour a week is spent on decisions, not on gathering numbers.

### 5.1 Before the review (5 minutes, mechanical)

- [ ] Fill in the tracking sheet (§4.3) from platform analytics and the dashboard.
- [ ] Pull the dashboard's six panels into the review note.
- [ ] Note any alerts that fired during the week (§6) and how they were resolved.

### 5.2 The review itself (20 minutes, four questions)

**1. Is the machine healthy? (5 min — if the answer is no, stop here and fix it.)**

- Uptime ≥ 99%? Any gaps > 30 s?
- GPU memory flat? Heap flat? Frame rate holding?
- Event bus clean — zero `seq` gaps, overlays fresh?
- Any watchdog actions? Did they work without a human?
- **Decision:** if anything is red, the week's work is reliability, not content. Fix it before anything else.

**2. Is the audience compounding? (5 min)**

- Returning viewers up or down vs. last week? (The question is direction, not size.)
- Follows per stream, predictions per day, chat per prime-time session — all three in the same direction?
- 59 Watch: how many activations, what was peak concurrency, did engagement spike?
- **Decision:** if returning viewers are flat for 3+ weeks, something about the show needs to change — format, prime-time slot, or the 59 Watch prominence. Name the one change.

**3. What do the clips say? (5 min)**

- Name the best clip and the worst clip of the week, and why.
- Per-format medians: which format is winning, which is losing?
- Click-through: are clips converting, or just entertaining?
- **Decision:** one format adjustment for the coming week (more of the winner, less of the loser, or one variable changed — never three).

**4. What is Mas doing? (5 min)**

- Scoring average and handicap trend — better, worse, flat?
- Strokes-gained: where is he gaining, where is he losing?
- The one fix from the last round — did it work?
- Calibration: any metric outside its alert band over 100 rounds?
- **Decision:** none, usually. The learning loop runs itself. Only intervene if calibration is drifting or the one-fix rule is being violated.

### 5.3 After the review (5 minutes, written down)

Write `docs/reviews/review-<date>.md` with four lines:

1. **Health:** green / amber / red, and why.
2. **Audience:** compounding / flat / shrinking, and the one number that proves it.
3. **Clips:** best format, worst format, the one change for next week.
4. **Mas:** scoring trend, handicap trend, the one fix.

Then post the weekly "Road to 59 update" if it is running — the review note is its source material.

### 5.4 The 30 / 60 / 90-day reviews (same ritual, bigger questions)

- **Day 30:** Is the routine working? (Uptime, cadence, the tracking sheet itself.) If the routine is not working, fix the routine.
- **Day 60:** The format review. Rank all formats on the three numbers (§2.2). Top format doubles its share; bottom format drops to one clip per week or is cut. The funnel review: which platform sends the most stream viewers? Shift posting effort accordingly. The community review: returning viewers, follows per stream, predictions per day — set 90-day targets from these. (Launch playbook §4.2.)
- **Day 90:** Full numbers — uptime, clips posted, median clip views, total follows, returning viewers, predictions placed, funnel split, best format. Write it as a retrospective post. Season 2 framing: announce the next Road to 59 arc. The Unreal decision point: judge the one-hole vertical slice on real footage. (Launch playbook §4.4.)

---

## 6. Alerting — what pages Mason

Alerting is deliberately narrow. Mason gets paged for things that are broken now and cost viewers every minute they stay broken. Everything else waits for Sunday.

### 6.1 What pages Mason (immediately)

| Alert | Trigger | How Mason is reached | First action |
|---|---|---|---|
| **Stream down** | No live stream detected for > 5 minutes during a scheduled live window | Phone notification (Restream/YouTube alert + watchdog message) | Check OBS/Restream; watchdog should already be restarting — if it is not, restart manually. |
| **Event bus silent** | No events on WebSocket port 4456 for > 60 seconds while the sim is running | Watchdog message | The bus is the broadcast's nervous system. Restart the sim; overlays freeze on last good data in the meantime (never blank). |
| **GPU memory climbing** | `renderer.info.memory` up > 10% over one round, or steady climb over 3 rounds | Watchdog message | The P0-1 leak is back. Restart the web build; investigate the shared-asset registry before the next round. |
| **WebGL context lost** | Context-lost event fires | Watchdog message | Context-lost handler should recover in ≤ 30 s. If it does not, restart the renderer; the round state restores from the event log. |
| **Watchdog itself down** | No watchdog heartbeat for > 5 minutes | Phone notification (separate channel from the watchdog) | The only alert that is not sent by the watchdog. If the watchdog is down, nothing is watching. Restart it first, then check the stream. |

### 6.2 What does NOT page Mason

| Condition | Why not | Where it is handled |
|---|---|---|
| A single clip underperforms | One clip is noise. Formats are judged on 60-day medians. | Sunday review, §5. |
| Viewership dips for a day | Daily viewership is weather. Weekly trends are the signal. | Sunday review, §5. |
| Mas shoots a bad round | Bad rounds are content. A +3 who never shoots 76 is not believable. | The record book, and the clip pipeline (worst-miss format). |
| TTS service down | Commentary silences; the ambient bed carries the stream. No error audio, no retry spam. | Watchdog log; Sunday review. (QA plan §2.4.) |
| NodeCG crashes | Graphics fall back to a static scorebug (last known state). The stream continues. | Watchdog log; Sunday review. (QA plan §2.4.) |
| Coins economy down | Predictions pause; the stream is unaffected. The ledger is append-only, so nothing is lost. | Watchdog log; Sunday review. |
| Calibration drift (small) | Drift is a trend, not an emergency. A ±5% band breach is a Sunday decision. | Sunday review, §5; calibration harness monthly. |

### 6.3 Alerting rules

- **One alert per incident.** If the stream is down and the bus is silent, that is one incident, not two pages. The watchdog deduplicates by incident, not by symptom.
- **Every alert is logged** with timestamp, trigger, action taken, and resolution time. The log is the record of how reliable the system actually is.
- **An alert that fires more than twice for the same cause is a bug, not an incident.** Fix the cause; do not silence the alert.
- **No alert may page Mason between 21:30 and 09:00 local except stream-down.** The stream is autonomous; a 3am page for a frozen overlay is not worth the sleep. The watchdog handles it, and the morning review sees it. (Proactive delivery window: 09:00–21:30.)
- **Alert fatigue is a system failure.** If Mason starts ignoring alerts, the alerting is wrong — too many, too vague, or too late. Cut the list, don't add to it.

### 6.4 The watchdog's job (summary)

The watchdog (broadcast-stack §7) is the only responder. It watches: the stream (live?), the bus (events flowing?), the renderer (memory flat? context alive?), the overlays (fresh?), the TTS service (up?), and itself (heartbeat). It restarts what it can, logs everything it does, and pages Mason only for §6.1. One manual intervention during a soak stage restarts that stage from zero (QA plan §2.5) — the watchdog is the reason that rule is survivable.

---

## 7. What good looks like (the numbers, over time)

| Timeframe | Health | Audience | Clips | Mas |
|---|---|---|---|---|
| **Day 30** | Uptime ≥ 99%, zero multi-hour outages | First returning viewers identified by name/handle | 30–60 clips posted; formats all tried at least twice | Scoring average within benchmark; first 59-watch activations logged |
| **Day 60** | Uptime ≥ 99%, ≤ 1 watchdog restart per week | Returning viewers compounding week over week | Format ranking clear on 60-day medians; top format identified | Handicap trend visible; learning loop has applied ~8 one-fixes |
| **Day 90** | Uptime ≥ 99%, soak C (7-day) passed | Regulars present at prime time most weeks; follows per stream stable | Funnel split known; posting effort shifted to the winning platform | 59-watch story has chapters — near-misses, closest calls, a board worth looking at |
| **Month 6** | The machine runs a month without Mason touching it except the Sunday review | A community that notices when the stream is down (and says so in chat) | One format is clearly the show's signature; guest twins are a regular feature | The Road to 59 arc has a real narrative — and the audience knows the number |

**The test of the whole system:** if Mason went away for a week, the stream would keep running, the clips would keep posting (from the queue), the coins would keep settling, and the only thing missing would be the Sunday review. That is what fully autonomous means — and analytics is how you know it is true.

---

## 8. Consistency with the rest of the repo

- **Launch playbook (§4.5):** the weekly tracking sheet here is the playbook's sheet, extended with 59 Watch metrics. The 30/60/90-day reviews here are the playbook's reviews, with the Sunday ritual added as the weekly cadence between them.
- **QA plan (§2):** the reliability metrics in §1.1 are the soak-test pass criteria (S-01 through S-12), promoted from test-time checks to always-on monitoring. The failure responses in QA plan §2.4 are the alerting triggers in §6.1.
- **Sim engine (§3, §6):** the calibration benchmarks in §3.1 are the sim's truth tables; the learning-loop checks in §3.2 are the sim's one-fix rule and improvement cap.
- **Broadcast stack (§7):** the watchdog described in §6.4 is the broadcast stack's watchdog. The event bus (port 4456) and the replicant freshness rules are the stack's.
- **Coins economy:** predictions per day, the weekly leaderboard, and the bonus-pool balance in the dashboard come from the economy's ledger. The ledger is append-only, so the analytics can never rewrite history.
- **Performance audit:** the GPU memory and heap metrics in §1.1 are the P0-1 leak's tripwires. If they ever climb again, the audit's fix has regressed.
- **59 Watch (broadcast stack §9):** the engagement metrics in §1.3 are how you know whether the signature feature is working. If 59 Watch does not lift engagement, make it louder before you make anything else louder.
