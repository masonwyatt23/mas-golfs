# Mas Golfs — Livestream & Growth Plan

**The show:** a +3 digital-twin golfer plays 18-hole rounds on repeat, forever. The stream never goes dark. The goal is to make it elite, enjoyable, and cutting edge — and to grow it into the home of autonomous golf.

## 1. The product: what viewers actually watch

- **Always on.** The loop is the product. A viewer can arrive at 3am and Mas is mid-round, chasing something. Permanence is the growth engine — every hour live accumulates watch time, subscribers, and search ranking.
- **A number to chase, always on screen.** Course record, best round, par, last-10 average, live handicap. A golfer just playing golf is ambient; a golfer chasing 65 is a show.
- **A season, not a stream.** Frame it as "Road to 62" — numbered rounds, a season leaderboard, streaks, slumps, and recoveries. Long arcs bring people back; single shots don't.
- **The golfer is a person.** Mas — Mason's digital twin, a real +3, training to get better. Viewers return for *him*: his form, his decisions, his one-fix-per-round learning arc.
- **Stakes on every shot.** Clubhouse Coins predictions before nearly every shot (fairway? GIR? birdie or better? up-and-down?) with moving odds. A prediction every shot is a reason to stay for the next 30 seconds, hundreds of times a day.

## 2. Platforms: where it lives

| Platform | Role | Why |
|----------|------|-----|
| **YouTube Live** | Home base | Discovery, searchable evergreen VODs, biggest golf audience, Shorts funnel. Streams become permanent videos. |
| **Twitch** | Live community | Best chat tooling (Channel Points, Predictions), lowest bar to first money (Affiliate at ~3 avg viewers). |
| **TikTok / Reels / Shorts** | Discovery | Clips only — never the live home. The funnel into the stream. |
| **Instagram (Mason W Golf)** | Brand anchor | Swing clips, the left-handed identity, the training angle, milestones with a direct path to the stream. |

Multistream the same feed to YouTube + Twitch via Restream (free tier covers 2 channels). Treat TikTok as a clip channel, not a live home.

## 3. The technical stack (in build order)

1. **Sim event bus + JSON event schema** — every shot, decision, and milestone as a typed event. Everything else consumes this.
2. **OBS scene collection + autonomous director** — 4–5 camera scenes, obs-websocket state machine, phase→camera map, drama-scored replay triggers.
3. **NodeCG graphics** — scorebug, leaderboard, lower-thirds, ticker, all driven by live data.
4. **Replay system** — replay buffer + slow-motion (0.5×) on dramatic shots, auto-clip save.
5. **Commentary pipeline** — event → LLM → low-latency TTS, two voices (play-by-play + color), event-only with cost guardrails and cached lines. Real golf is mostly quiet — commentate on events, let the ambient bed carry the silence.
6. **Ambient audio** — layered bed (wind, birds, per-hole variation), event stingers (impact, applause).
7. **Multistream + 24/7 reliability** — Restream to YouTube + Twitch, watchdog auto-restart, AI-use disclosure set on YouTube from day one.
8. **Clip pipeline** — auto-cut highlights from replay saves into vertical clips for Shorts/Reels/TikTok.

## 4. The clip machine: how it grows

The stream is the factory; clips are the growth engine. Discovery happens off-platform — no one finds a zero-viewer stream by browsing.

- **Daily clip rhythm:** 1–2 vertical clips a day, cut natively for each platform (best shot, worst miss, the knockdown into the wind, the decision that paid off). Commit to 60 days before judging it.
- **Every round auto-produces 3–5 clips.** Hole-outs, near-misses, recoveries, chunks — the moments, not the routine.
- **Repeatable daily premises:** "Day 14 of the +3 trying to break the course record," "Can he go 3 rounds without a bogey?" A daily, countable quest viewers can follow and return for.
- **Premiere appointment viewing:** the 24/7 loop runs continuously, but cut "episodes" (a full round, a best-of) premiere on a fixed schedule to create chat moments.
- **Mason in chat:** a fixed "prime time" moment each evening when Mason himself drops into chat. The creator is the brand.

## 5. The coin economy (closed-loop, always)

Clubhouse Coins are free, earned by watching and predicting, never purchasable, never convertible to anything of value — status, leaderboard rank, and cosmetic perks only. Golf's own formats map directly onto predictions: per-hole skins pools, Nassau-style front/back/overall markets, par-3 closest-to-pin props, auto-presses when Mas is "down" against par. **No crypto or cash-out, ever, until counsel reviews it** — that is the single biggest legal risk in the project.

## 6. The Unreal leap (when ready)

The web build is the always-on prototype and clip factory — it stays live while the Unreal build matures. The leap, when green-lit:

- **One-hole vertical slice first** (UE 5.8 + LiDAR terrain + MetaHuman Mas + one full shot loop with tracer and NodeCG scorebug), judged against the 2K/GTA 6 bar on real footage before committing to 18 holes.
- **Render once, broadcast to everyone:** one Unreal instance on one GPU (~$250–500/mo cloud, or ~$2,500 one-time for an RTX 4090 box), OBS captures it, one RTMP feed to YouTube + Twitch.
- **The swing is bespoke:** a half-day mocap shoot of Mason's actual swing — no off-the-shelf golf-swing mocap exists. That is the difference between a golfer and a mannequin.
- **Costs:** engine $0 until $1M revenue; Quixel Megascans/Megaplants free; Ultra Dynamic Sky ~$50. The real cost is build effort — weeks for the slice, months for the full broadcast.

## 7. Growth timeline

**Days 0–30 — Launch.**
Stream goes live on YouTube + Twitch. Daily clips start. Instagram funnel active. Goal: stream stable 24/7, clip rhythm established, first regulars.

**Days 30–60 — Find the format.**
Review what clips and moments actually perform on a 60-day cycle. Double down on the winning format. First "Road to 62" season arc in full swing. Goal: returning viewers, not peak concurrents — three regulars beat thirty strangers.

**Days 60–90 — Community.**
Weekly leaderboard reset, fixed prime-time chat moment, guest moments (other golfers' swings as guest golfers in the game). First collab outreach. Goal: follows-per-stream rising, a recognizable core community.

**Months 4–12 — Scale.**
Unreal vertical slice judged and, if it clears the bar, built out. Sponsorship conversations once the audience is real. The stream earns slowly — subs, Super Chat, Bits — and the coin economy carries engagement until the audience does.

## 8. What to measure

- Returning viewers and follows-per-stream (not peak concurrents).
- Clip views and click-through to the live stream.
- Predictions placed per stream (the engagement heartbeat).
- Mas's scoring average and handicap trend (the story).
- Stream uptime — the one metric that must never dip.

## 9. Compliance (from day one)

- YouTube AI-use disclosure set on the stream — realistic AI-generated content must be disclosed; the label doesn't limit audience or earnings.
- Keep "Mas is Mason's digital twin" visible on screen — originality (a real person's swing model, real decisions, a learning arc) is the defense against the generic-AI-content monetization policy.
- Coins stay closed-loop. No purchase path, no conversion path, no secondary market.
