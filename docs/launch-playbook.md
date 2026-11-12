# Mas Golfs — 90-Day Launch Playbook

**The show:** a +3 digital-twin golfer, Mas — Mason's digital twin — plays 18-hole rounds on repeat, forever. The season arc is **Road to 59**: the chase for a sub-60 round. The stream never goes dark. This playbook is the implementation plan for turning the always-on broadcast into an audience: the clip machine, the funnel, the community, and the first 90 days, day by day.

**Principles that govern everything in this document:**

- The stream is the factory; clips are the growth engine. Discovery happens off-platform.
- Measure regulars, not peak viewers. Three returning viewers beat thirty strangers.
- The coins stay closed-loop play money: free, earned by watching, never purchasable, never convertible to anything of value. No real-money gambling anywhere in this project.
- Revenue is not planned for month one. The coin economy carries engagement until the audience does.
- Everything runs on free tools and free tiers. Greatness without a bill.

---

## 1. The auto-clip system: replay buffer → vertical clip

### 1.1 How a moment becomes a clip

The pipeline has four stages. Every stage is automatic; a human (Mason) only approves the daily post.

**Stage 1 — Capture (always on).** OBS runs a replay buffer continuously (last 120 seconds, 1080p60). The sim engine emits structured JSON events for every shot and milestone. Nothing is recorded in full — only the buffer, which costs almost no disk.

**Stage 2 — Detection (drama scoring).** Every shot gets a drama score the moment it lands. The score decides whether the replay buffer is saved, and what the clip is about.

| Moment | Detection rule | Drama score | Save? |
|---|---|---|---|
| Hole-out (chip-in, holed bunker shot, ace) | Ball enters hole from outside the green, or from a bunker | 100 | Always |
| Eagle | Hole completed 2-under par | 95 | Always |
| Near-miss (lip-out, ball stopping <6 inches, putt burning the edge) | Putt/shots finishing within 6 inches of the hole without dropping | 85 | Always |
| Great recovery | Par or better after a lie in trees/rough/bunker, or a punch-out that saves the hole | 80 | Always |
| Best decision | A strategic choice that paid off — knockdown into wind to 10 feet, draw around a tree to the green, lay-up to the perfect number then stuffed | 75 | Always |
| Worst miss (chunk, thin through the green, shank, topped drive) | Named mishit with a bad outcome, or a shot losing >40 yards vs. plan | 75 | Always |
| Birdie | Hole completed 1-under par | 60 | If it is the round's first, or breaks a drought of 5+ holes |
| Record-chase moment | Any shot while Mas is on pace for the course record or a sub-60 round | 70+ | Always while on pace |
| Streak events | 3rd consecutive birdie, 5th consecutive par, first bogey-free stretch | 70 | Always |

**Stage 3 — Assembly (automatic).** When a save triggers, the system cuts a vertical 9:16 clip from the replay buffer:

1. **Hook (0–2 s):** the result first. The ball dropping, the tracer's final feet, the scorebug changing. No intro, no logo sting — the payoff is the first frame.
2. **Context (2–6 s):** the decision, in one line of text on screen. *"Knockdown 7-iron. Into the wind. Right edge."* Plus the shot-data strip: club, distance, ball speed, carry.
3. **The shot (6–20 s):** the swing and ball flight with the tracer, at full speed. If the moment is dramatic, a 0.5× slow-motion replay of the last 3 seconds.
4. **The payoff (last 3 s):** the result card — score to par, Road to 59 status, and the call to action: *"Mas Golfs — live now, 24/7."*

Total length: **20–35 seconds**. Under 60 seconds always. Captions burned in — most viewers watch muted.

**Stage 4 — Queue (daily).** Saved clips land in a daily queue, ranked by drama score. Mason picks 1–2 per day to post (see §1.3). The rest stay in the library for best-of compilations and the weekly roundup.

### 1.2 Clip specs per platform

One master clip, three exports. Never post the same file everywhere — each platform's player and audience expect different framing.

| | YouTube Shorts | Instagram Reels | TikTok |
|---|---|---|---|
| Aspect / resolution | 9:16, 1080×1920 | 9:16, 1080×1920 | 9:16, 1080×1920 |
| Length | 20–45 s (sweet spot ~30 s) | 20–40 s | 20–35 s |
| Captions | Burned in, large, top-third safe | Burned in, large, avoid bottom 25% (UI) | Burned in, large, avoid right edge (UI) |
| On-screen text | Shot data strip + decision line | Same, plus "Mason W Golf" handle watermark | Same, minimal — TikTok punishes text-heavy frames |
| Hook | Result in first frame | Result in first frame | Result in first frame |
| Sound | Ambient bed + impact sound; trending audio only if it fits the moment | Same | Same; TikTok favors native sounds, use sparingly |
| CTA | "Full round live now — link in bio" | "Live 24/7 — link in bio" | "Live now — link in bio" |
| Hashtags | #golf #golftok #masgolfs #roadto59 #shottracer | #golf #golfreels #masgolfs #roadto59 | #golf #golftok #masgolfs #roadto59 |
| Posting window | 12:00–2:00pm ET and 7:00–9:00pm ET | 11:00am–1:00pm ET and 7:00–9:00pm ET | 12:00–3:00pm ET and 7:00–10:00pm ET |

**Text rules for all platforms:**

- One idea per clip. Never "here are three shots."
- The decision line is the caption and the first comment. Viewers read the decision, then watch to see if it worked.
- Never name a specific client company of AshlrAI in clip copy. Generic descriptors only.
- Every clip carries the same two tags: **Mas Golfs** and **Road to 59**.

### 1.3 Daily cadence: 1–2 clips a day for 60 days

The commitment: **at least one clip every day for the first 60 days, two on days with a drama-90+ moment.** This is the single most important growth input. The stream generates the content; the bottleneck is posting cadence, not filming.

**Daily clip workflow (15 minutes, every evening):**

- [ ] Open the daily queue, sorted by drama score.
- [ ] Pick the best clip (and a second if any scored 90+).
- [ ] Check the hook: does the first frame show the payoff? If not, re-cut to start 1 second later.
- [ ] Check captions: readable on mute, no typos, decision line correct.
- [ ] Post to Reels first (Instagram is the brand anchor), then Shorts, then TikTok — same day, within an hour.
- [ ] First comment on each post: the decision line + "Full round live now — link in bio."
- [ ] Log it: clip, platform, drama score, link (see §4.4 tracking sheet).

**60-day rule:** do not judge the clip strategy before day 60. Expect the first ~30–50 clips to do little. Review formats on a 60-day cycle (see §4.2) and double down on whatever format wins. At 1–2 clips a day, the discovery window is measured in weeks, not months.

### 1.4 Weekly clip products (beyond the daily clip)

| Product | What it is | When | Length |
|---|---|---|---|
| **Round in 60 seconds** | Best 3 shots of the round, stitched, one per round | 2–3× per week | 45–60 s |
| **Road to 59 update** | Where Mas stands this week: scoring average, last-10, handicap trend, how many rounds until the record is realistically in play | Every Sunday | 30–45 s |
| **The one fix** | The single strokes-gained leak from the week and the single adjustment — the training angle | Every Monday | 30 s |
| **Best of the week** | Top 5 moments of the week, ranked | Every Friday | 60–90 s (long-form Short) |

---

## 2. Clip formats that win in golf YouTube

Five formats, ranked by what the research says works. Every daily clip should be one of these — if it doesn't fit a format, it probably isn't a clip.

### Format 1 — Best shot (the workhorse)

**What:** the single best shot of the day, result first.
**Why it works:** the tracer + the payoff is the most legible visual in golf. Viewers understand it in one second.
**Structure:** ball dropping or stopping close (0–2 s) → decision line → swing and tracer → result card.
**Example titles:** "Mas needed this. Knockdown 7-iron into the wind." / "Draw around the tree. 8 feet. That's the shot."
**Post when:** any drama-80+ shot. This is the default daily clip.

### Format 2 — Worst miss (the relatability engine)

**What:** the chunk, the thin through the green, the drive into the trees, the three-putt.
**Why it works:** viewers explicitly prefer relatable imperfection. Creator golf's appeal is missing putts and chunking chips. A +3 who never misses is unwatchable; the miss — and the bounce-back — is the content.
**Structure:** the mishit in full (don't hide it) → the honest caption ("Thinned it. Through the green. That's golf.") → the recovery or the cost on the scorecard.
**Rule:** never mock Mas, never hide the miss. The miss is the story; the recovery is the character.
**Post when:** any drama-75+ mishit. Aim for at least one miss clip per week — if the week had no good miss, the sim is too kind.

### Format 3 — Decision breakdown (the learning format)

**What:** a 30-second lesson. The situation, the options, the choice, the outcome.
**Why it works:** decision talk is the #2 reason people watch golf YouTube. Horvat and Bryson win on talking through decisions in real time. This is the format that makes watching Mas useful for the viewer's own game — and it's the training angle that differentiates the project.
**Structure:** the lie + wind + distance on screen → the two options ("Driver at the green, or 3-wood to the fat part?") → the choice and why → the result → one-line takeaway.
**Example titles:** "Why Mas laid up on a par 5." / "Into the wind, uphill: club up, knock it down."
**Post when:** any drama-75+ best-decision moment. At least 2× per week.

### Format 4 — Record-chase update (the appointment format)

**What:** a short status check on the Road to 59 while Mas is on pace — or the morning after a near-miss.
**Why it works:** a live, countable goal is the strongest retention mechanic in creator golf. "Day X of…" with a clear, trackable goal is the premise that built Bryson's 102M-view challenge series.
**Structure:** the numbers (score through N holes, pace vs. 59, what he needs on the remaining holes) → the next key hole → "Live now."
**Rule:** only post while genuinely on pace (through 9 holes at −4 or better, through 13 at −6 or better) or the morning after a round that finished within 3 of the record. Never manufacture a chase.
**Post when:** on pace, or the morning after a near-miss.

### Format 5 — Day X of Road to 59 (the series format)

**What:** a numbered daily series entry. Same opening line every day, updated numbers.
**Why it works:** series, not one-offs, are what scale. A numbered series with a running score gives viewers a reason to return tomorrow — they are following a quest, not watching a clip.
**Structure (identical every day):** "Day [N] of the Road to 59." → yesterday's round in one line → today's number to beat → best moment from yesterday → "Live now."
**Rule:** never break the numbering. If a day has no great moment, post the numbers and the quietest honest moment. Consistency is the format.
**Post when:** daily, as the second clip on days that already have a best-shot or decision clip — or as the only clip on quiet days.

### Format scoreboard (review every 60 days)

Track per format, over each 60-day cycle: clips posted, median views, median watch time, click-through to the stream, follows gained. Double the top format's share next cycle; cut the bottom format to one clip per week or drop it. The formats above are the starting hypothesis, not gospel — the data decides.

---

## 3. The funnel: Instagram → YouTube → Twitch

### 3.1 The shape of the funnel

```
Instagram (Mason W Golf)          — discovery + brand anchor
   ↓  swing clips, milestones, direct appeals
YouTube (long-form home + Shorts) — depth, VOD library, search
   ↓  premieres, full rounds, best-ofs
Twitch (live community)           — chat, predictions, regulars
   ↓  Channel Points, predictions, prime-time chat
Regulars / superfans              — the audience that sustains it
```

Each platform has one job. Instagram discovers strangers. YouTube keeps them. Twitch turns them into regulars. Do not ask any platform to do another platform's job.

### 3.2 Instagram (Mason W Golf) — the brand anchor

Instagram is where the audience starts, because it is where Mason already is. It is also the only platform where the creator — a real person with a real swing — is the product.

**What to post:**

- **Daily clips** (from §1): the primary feed content. Reels first, every day.
- **Swing posts:** Mason's real swing, side by side with Mas's in-game swing. The digital-twin comparison is the most distinctive content the project owns — nobody else can post it.
- **Milestone posts:** every course record, every handicap move, every Road to 59 near-miss. A milestone post always ends with a direct, frictionless path to the stream: "Live now — link in bio. Come watch him try again."
- **Stories:** daily poll ("Will Mas break 70 today?"), the live scorebug screenshot, the prime-time chat reminder. Stories are the daily touchpoint that keeps followers warm between feed posts.
- **Direct appeals:** periodically, a plain post or story that says, in Mason's own words, "I built this. My digital twin plays golf 24/7 and I'm trying to teach him — and myself — to break 59. The stream is live now, link in bio." Creators who convert Instagram to YouTube do it with a direct ask, not a subtle link.

**Conversion mechanics:**

- Link in bio always points at the live stream (YouTube Live first). Update it once; it should never point at a dead link.
- Every feed post's first comment: the decision line + "Full round live now — link in bio."
- Pin the best-performing clip to the top of the profile. Rotate monthly.
- Reply to every comment in the first hour after posting. The first hour decides reach.

### 3.3 YouTube — the long-form home

YouTube is where the stream lives and where the content compounds. Its algorithm recommends VODs and Shorts to strangers for months; nothing on Twitch does that.

**What lives here:**

- **The 24/7 livestream** (YouTube Live). Always on. The VOD library accumulates automatically.
- **Shorts** (from §1): the daily clips, same day as Reels.
- **Premieres:** cut "episodes" — a full round, a best-of week — premiered on a fixed schedule (see §3.5). Premieres are appointment TV with live chat; the Internet Invitational's biggest numbers came from scheduled premieres, not from going live.
- **Full rounds as VODs:** each completed round, lightly edited, published as a long-form video. Long videos are the revenue engine later and the background-TV content now.

**Conversion mechanics:**

- Every Short's pinned comment and description link to the livestream.
- Every long-form video ends with the same line: "Mas plays 24/7. The stream is live right now."
- Channel page: the livestream is the featured video, always.

### 3.4 Twitch — the live community

Twitch is where the regulars live. Its discovery is poor for small channels — a new channel in a saturated category is invisible — so never rely on Twitch to find viewers. Twitch's job is to keep the viewers Instagram and YouTube send.

**What lives here:**

- **The same 24/7 feed**, multistreamed via Restream.
- **Predictions** (Channel Points): before nearly every shot and hole. This is the engagement engine — see §5.3.
- **Prime-time chat** (see §5.2): Mason in chat every evening at a fixed time.

**Conversion mechanics:**

- Follow alerts and follow goals on screen — each follow is a visible shared moment.
- Channel Points are earned by watching only. No purchase path, ever.

### 3.5 Premiere schedule (appointment viewing)

The 24/7 loop runs continuously, but premieres create the moments people plan around.

| Slot | What | When (ET) |
|---|---|---|
| **Round premiere** | The best full round of the week, premiered as an episode | Wednesdays, 7:00pm |
| **Best-of premiere** | Top 5 moments of the week | Fridays, 7:00pm |
| **Road to 59 update** | Weekly status video | Sundays, 12:00pm |

Fixed times, every week, no exceptions for the first 90 days. Viewers follow when they can predict what they'll get next time.

---

## 4. The 90-day launch plan

### 4.1 Overview

| Phase | Days | Theme | The one thing that matters |
|---|---|---|---|
| **Launch** | 0–30 | Get it live and stable | Stream up 24/7, clip rhythm established |
| **Find the format** | 30–60 | Learn what works | 60-day format review, double the winner |
| **Community** | 60–90 | Turn viewers into regulars | Weekly reset, prime-time chat, guest moments |

### 4.2 Phase 1 — Launch (Days 0–30)

**Goal:** the stream is live and stable, the clip rhythm exists, the first regulars appear.

**Week 1 (Days 0–7) — Go live.**

- [ ] Stream live on YouTube Live + Twitch via Restream. Verify: 24-hour continuous run with no drops.
- [ ] AI-use disclosure set on the YouTube stream. "Mas is Mason's digital twin" visible on screen.
- [ ] Scorebug, leaderboard, and Road to 59 tracker live on the broadcast.
- [ ] Clubhouse Coins predictions live (see §5.3). Verify a prediction resolves correctly end to end.
- [ ] First clip posted (Reels → Shorts → TikTok, same day).
- [ ] Instagram bio link points at the livestream. Pin the launch post: "I built this. My digital twin plays golf 24/7. Road to 59. Link in bio."
- [ ] Watchdog auto-restart tested: kill OBS, confirm the stream comes back on its own.
- **Measure at end of week 1:** uptime %, clips posted, clip views, stream views, follows. Baseline everything — week 1 numbers are the floor, not the verdict.

**Week 2 (Days 8–14) — Establish the rhythm.**

- [ ] Daily clip cadence running (1–2/day). First "Day X of Road to 59" series entry posted.
- [ ] First Wednesday round premiere + first Friday best-of premiere.
- [ ] First prime-time chat moment (see §5.2) — Mason in chat, fixed time, announced in Stories that morning.
- [ ] First decision-breakdown clip posted.
- [ ] Reply to every comment on every clip within the first hour.
- **Measure:** returning viewers (anyone who watched twice), follows-per-stream, predictions placed per day, clip median views. Compare to week 1.

**Week 3 (Days 15–21) — First stress test.**

- [ ] First weekly leaderboard reset (see §5.1).
- [ ] First "one fix" Monday clip (the week's strokes-gained leak).
- [ ] First record-chase clip if Mas goes on pace; if not, post the honest near-miss numbers instead.
- [ ] Check the funnel: which platform is sending viewers to the stream? (YouTube Analytics traffic sources + Twitch referrals.) Shift clip effort toward the winner by 20%.
- **Measure:** same as week 2, plus funnel split (Instagram vs. Shorts vs. TikTok vs. search).

**Week 4 (Days 22–30) — Lock the routine.**

- [ ] 30-day review: total clips posted, median clip views, best and worst format, uptime %, follows gained, returning-viewer count.
- [ ] Write down the one format that outperformed and the one that underperformed. No changes yet — the 60-day review decides.
- [ ] Confirm the stream has run 30 days without a multi-hour outage. If it hasn't, fix reliability before anything else — uptime is the one metric that must never dip.
- **Measure:** 30-day totals. Set the 60-day targets from these numbers (aim for 2× clip median views and 3× returning viewers by day 60).

### 4.3 Phase 2 — Find the format (Days 30–60)

**Goal:** learn what the audience actually wants, and give them more of it.

**Week 5–6 (Days 31–44) — Experiment deliberately.**

- [ ] Post each of the five formats at least twice. Tag every clip with its format in the tracking sheet.
- [ ] Try one variation per week: a different hook (start with the decision instead of the result), a different length (45 s vs. 25 s), a different posting time. One variable at a time.
- [ ] First guest moment (see §5.4): another golfer's swing as a guest golfer in the game, or a collab clip with a golf creator.
- [ ] Start the weekly "Road to 59 update" Sunday video if it isn't running yet.
- **Measure:** per-format median views and watch time. The data is the decision-maker now.

**Week 7–8 (Days 45–60) — The 60-day review and the doubling.**

- [ ] **60-day format review.** Rank the five formats by median views, watch time, and click-through to the stream. The top format doubles its share next cycle; the bottom format drops to one clip per week or is cut.
- [ ] **60-day funnel review.** Which platform sends the most stream viewers? Shift posting effort accordingly. If Instagram is the source, post more Reels; if Shorts, post more Shorts.
- [ ] **60-day community review.** How many returning viewers? How many follows-per-stream? How many predictions per day? Set 90-day targets from these.
- [ ] Publish a "60 days of Mas Golfs" retrospective clip — the best moments so far. This is also a re-launch moment: re-pin it, re-post the direct appeal.
- **Measure:** 60-day totals vs. 30-day totals. The question is not "is it big yet" but "is it compounding" — returning viewers and clip medians rising is compounding.

### 4.4 Phase 3 — Community (Days 60–90)

**Goal:** turn viewers into regulars, and regulars into a community that sustains the stream.

**Week 9–10 (Days 61–74) — Regulars.**

- [ ] Weekly leaderboard reset is now a ritual (see §5.1) — announced in advance, results posted, winner celebrated on screen.
- [ ] Prime-time chat is fixed and known — same time, same days, every week. Mason's presence is the draw; never miss it without announcing why.
- [ ] First community prediction market with a real stake in coins: a full-round Nassau (see §5.3) with the week's leaderboard on the line.
- [ ] Start naming regulars on screen (first names / handles only, with their permission implied by participation). Remembering names is the retention mechanic.
- [ ] First collab outreach to a golf creator: a guest golfer moment or a shared clip. (See §5.4.)
- **Measure:** returning-viewer share of total viewers, follows-per-stream, predictions per stream, chat messages per prime-time session.

**Week 11–12 (Days 75–90) — The 90-day review and the next season.**

- [ ] **90-day review.** Full numbers: uptime, clips posted, median clip views, total follows, returning viewers, predictions placed, funnel split, best format. Write it up as a retrospective post — the audience loves a progress report, and it doubles as a re-launch.
- [ ] **Season 2 framing:** announce the next Road to 59 season arc with a clear start date and a clear goal. Seasons give lapsed viewers a reason to come back.
- [ ] **Unreal decision point:** judge the one-hole vertical slice (if built) against the 2K/GTA 6 bar on real footage. If it clears the bar, commit to the build-out; if not, keep polishing the web build. Do not take the web stream down either way.
- [ ] **Sponsorship readiness check:** only now, with 90 days of audience data, consider outreach — and only to brands that fit golf. No sponsorship is worth a bad fit in the first 90 days.
- **Measure:** 90-day totals vs. 60-day totals. If returning viewers and clip medians are still compounding, the machine works — keep feeding it.

### 4.5 Weekly tracking sheet

Track these every week, same day, same format. The numbers are the strategy.

| Metric | Why it matters | Where to get it |
|---|---|---|
| Stream uptime % | The one metric that must never dip | OBS / Restream logs |
| Clips posted | Cadence is the growth input | Tracking sheet |
| Clip median views (per format) | What the audience wants | Platform analytics |
| Clip click-through to stream | Whether clips convert | YouTube Analytics / link clicks |
| Stream views | Top of the funnel | YouTube + Twitch analytics |
| Returning viewers | The real audience | YouTube returning vs. new |
| Follows-per-stream | Community growth | Twitch + YouTube |
| Predictions placed per day | The engagement heartbeat | Clubhouse Coins log |
| Chat messages per prime-time session | Community depth | Twitch chat logs |
| Mas's scoring average / handicap | The story | The broadcast stat book |
| Funnel split | Where viewers come from | Traffic sources |

**Weekly review checklist (30 minutes, every Sunday):**

- [ ] Fill in the tracking sheet.
- [ ] Name the best clip and the worst clip of the week, and why.
- [ ] Name the one number that moved most, in either direction.
- [ ] Decide one change for next week. Exactly one — more changes mean no learning.
- [ ] Confirm next week's premiere slots are scheduled.

---

## 5. Community mechanics

### 5.1 Weekly leaderboard reset

Every Monday, the Clubhouse Coins leaderboard resets. The week's winner is celebrated on screen and in a clip.

- **Why it works:** a reset gives new viewers a fair start and gives regulars a reason to return on Monday. A leaderboard that never resets is owned forever by the earliest viewers.
- **What resets:** coin balances for the weekly competition only. All-time balances and ranks are kept separately and never reset — the all-time board is the hall of fame; the weekly board is the game.
- **Ritual:** Monday 12:00pm ET — results posted, winner announced on the broadcast bug for the day, winner's handle in the week's first clip. Announce the reset in advance (Sunday's Road to 59 update) so viewers know when to play.

### 5.2 Fixed prime-time chat moment with Mason

**Every evening, same time, same days** (pick the time in week 1 and never move it — e.g. 7:30pm ET, Tuesday/Thursday/Sunday to start).

- Mason drops into Twitch chat for 20–30 minutes. Not to play — Mas plays himself — but to talk: answer questions, react to the round, explain a decision, take a prediction side.
- Announce it that morning in Instagram Stories ("Live in chat tonight 7:30 — come sweat the back nine with me").
- The prime-time session is also a clip source: the best exchange becomes a clip.
- **Never miss it without announcing why.** A missed prime-time with no explanation breaks the habit faster than anything else.

### 5.3 Clubhouse Coins prediction formats (closed-loop play money)

Coins are free, earned by watching and predicting, never purchasable, never convertible to anything of value — status, leaderboard rank, and cosmetic perks only. No cash-out path, no crypto, no secondary market. That is what keeps this legal and clean.

**Per-shot predictions (the heartbeat):** before nearly every shot, one quick market.

| Market | Question | Window |
|---|---|---|
| Fairway | Fairway or rough? | Before the tee shot |
| GIR | Green in regulation? | Before the approach |
| Proximity | Inside 10 feet? | Before the approach |
| Birdie or better | Birdie or better on this hole? | Before the hole |
| Up-and-down | Gets up and down? | From off the green |

Odds move with Mas's form and the hole. Winners split the pool proportionally. No house cut.

**Golf's native formats, translated to viewer games:**

- **Skins (per hole):** each hole is its own coin pot. Ties carry over, so a late hole can be worth several skins. The simplest viewer game and the most exciting.
- **Nassau (per round):** three bets in one round — front 9, back 9, overall 18 — with **presses** when Mas goes 2-down against par. A press doubles the stakes on the remaining holes. Viewers already know this format; no explanation needed.
- **Props:** closest to the pin on a par 3, longest drive, up-and-down yes/no. The simplest of all — one question, one answer.
- **Road to 59 markets:** season-long — "Will Mas break 60 this week?" Long odds, big coin payouts, and a reason to follow the whole season.

**Prediction cadence:** a market before every shot is the goal, but never more than one open market at a time. The announcement, the chat debate, and the resolution are three separate engagement spikes per event.

### 5.4 Guest golfer moments

The top golf channels' breakout pattern is a second name on camera. For Mas Golfs, the equivalent is a guest golfer in the game.

- **What it is:** another golfer's swing (with their permission) modeled as a guest golfer who plays a round, a match, or a single hole against Mas. Or a collab clip: Mason and the guest reacting to Mas's round together.
- **Why it works:** the guest brings their own audience, and a match — even against a digital twin — has stakes a solo round doesn't.
- **How to start:** one guest moment in days 30–60. Pick someone in the golf-creator world Mason already knows, or a local golfer with an audience. Keep it simple: one hole, one clip, one post each.
- **Rule:** the guest's swing is theirs, with credit, and the guest's identity is real. No anonymous or uncredited swings.

### 5.5 Regulars and superfans

The funnel is Discovery → First View → Follow → Return → Interaction → Regular → Superfan. Each stage needs one mechanic:

| Stage | Mechanic |
|---|---|
| Discovery | Daily clips (§1) |
| First View | Scorebug that tells the story in 3 seconds |
| Follow | Follow alerts + follow goals on screen |
| Return | Daily premise, weekly reset, fixed premiere slots |
| Interaction | Predictions before every shot |
| Regular | Prime-time chat, remembered names, weekly leaderboard |
| Superfan | Guest moments, season arcs, all-time hall of fame |

**The rule that matters most:** three regulars who return beat thirty strangers who never come back. Optimize for the return, not the spike.

---

## 6. Monetization ladder

**The rule: revenue is not planned for month one.** The coin economy carries engagement until the audience does. Monetization is a ladder with low early rungs, and ambient streams earn slowly. Plan for it, don't depend on it.

| Rung | Unlock | Realistic timeline | What it pays |
|---|---|---|---|
| **Twitch Affiliate** | 50 followers, 3 avg viewers, 7 streams | Weeks 2–6 | Subs, Bits, Channel Points economy |
| **YouTube fan funding** | 500 subscribers | Months 2–4 | Super Chat, Super Stickers, memberships |
| **YouTube Partner Program (ads)** | 1,000 subscribers + watch-time threshold | Months 4–12 | Ad revenue — needs scale; don't plan on it early |
| **Channel memberships** | With fan funding | Months 3–6 | Recurring — the most reliable early revenue |
| **Sponsorships** | Real audience data (90 days) | Months 4+ | Only brands that fit golf; no bad fits |
| **Merch / digital goods** | Superfan base exists | Months 6+ | Only after the community asks for it |

**Splits to know:** Twitch subs 50/50 (up to 70/30), YouTube memberships/Super Chat ~70%, Kick 95/5. One 2026 estimate puts ~50 average viewers at ~$310/month — treat that as the shape of early money, not a promise.

**What not to do:**

- Do not gate the stream or the predictions behind payment. The show is free; the coins are free.
- Do not take a sponsorship in the first 90 days. No brand is worth a bad fit while the audience is forming.
- Do not add any real-money or crypto lane to the coins. That stays off the roadmap until counsel reviews it.
- Do not chase ad revenue before the audience exists. Ads need scale; community needs care.

**The honest math:** the realistic early money is subs + Super Chat/Bits + memberships later — not ads. The project's value in the first 90 days is the audience and the asset (the show, the data, the brand), not the revenue.

---

## 7. Launch checklists

### 7.1 Day 0 — Go-live checklist

- [ ] Stream live on YouTube Live + Twitch via Restream, verified 24-hour continuous run.
- [ ] AI-use disclosure set on YouTube. "Mas is Mason's digital twin" visible on screen.
- [ ] Scorebug, leaderboard, Road to 59 tracker, live handicap live on the broadcast.
- [ ] Clubhouse Coins predictions live and resolving correctly.
- [ ] First clip posted (Reels → Shorts → TikTok).
- [ ] Instagram bio link points at the livestream. Launch post pinned.
- [ ] Watchdog auto-restart tested.
- [ ] Tracking sheet created, week 1 baseline ready.

### 7.2 Weekly checklist (every Sunday, 30 minutes)

- [ ] Fill in the tracking sheet (§4.5).
- [ ] Name the best and worst clip of the week, and why.
- [ ] Name the one number that moved most.
- [ ] Decide exactly one change for next week.
- [ ] Confirm next week's premiere slots are scheduled.
- [ ] Confirm the weekly leaderboard reset is announced.

### 7.3 90-day review checklist (Day 90)

- [ ] Full numbers written up as a retrospective post.
- [ ] 60-day vs. 90-day format ranking — top format confirmed.
- [ ] Funnel split confirmed — top source confirmed.
- [ ] Season 2 announced with a start date and a goal.
- [ ] Unreal vertical-slice decision made (build out, or keep polishing web).
- [ ] Sponsorship readiness assessed — and only pursued if the audience data supports it.

---

*Mas Golfs — the Mason W Golf endless round. Road to 59.*
