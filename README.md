# Mas Golfs

**A fully autonomous golf world.** A +3 digital-twin golfer — Mas, Mason's digital twin — plays 18-hole rounds on repeat, forever, with no human in the loop. Built to be watched and livestreamed.

> Open `index.html` in a browser and he's already on the first tee. He never stops.

## The show

- **The golfer is Mas.** A left-handed +3 handicapper modeled on Mason Wyatt's real swing — smooth tempo, full shoulder turn, high balanced finish held while watching the ball fly. Outfits are customizable; right-handed mode exists for the rest of the world.
- **Real golf, not a dice roll.** Every shot is generated from launch conditions (ball speed, launch angle, spin, spin axis) through real ball-flight physics. Named mishits — thin, chunk, toe, heel — behave physically. Dispersion scales by club and shot type. Lies and wind gate which shots are even available: knockdowns into the wind, draws around trees, punch-outs from the woods.
- **Calibrated to a real +3.** Roughly 265–275 yard driving, ~55–60% fairways, ~60% greens in regulation, scoring ~72–74. Proximity and putting follow real make-rate truth tables, so the leaderboard stays credible with golfers.
- **The broadcast.** Full-screen, open-and-watch. An autonomous director cuts between broadcast cameras (down-the-line tracer cam, catch cam, bunker cam, pin cam, aerial) on shot events, never mid-flight. Shot tracer with ball speed, launch, spin, apex, carry, and shape. Slow-motion instant replays on dramatic shots. A scorebug that tells a newcomer the whole story in 3 seconds.
- **He learns.** After each round the learning loop finds the single biggest strokes-gained leak — approach and driving first — and adjusts. His handicap is tracked live, with history and trend.
- **The record book.** All-time score, most-recent-10 aggregate, best and worst rounds, scoring average, streaks, course record. Every round has a number to chase.
- **Clubhouse Coins.** Play-money predictions before nearly every shot (fairway? GIR? birdie or better?) with moving odds. Coins are free, earned by watching, never purchasable, never convertible to anything of value.

## The course

**Wyatt National** — an 18-hole par-72 in Staunton, Virginia. Played on repeat, round after round, so viewers learn it: the drivable par 4, the par 3 over water, the hole where the smart play is 3-wood.

## Why this exists

YouTube golf now out-subscribes the PGA Tour. Creator golf averages 4–5x the views of a Sunday TV broadcast. But nobody has shipped a consumer golf digital twin — a persistent virtual model of *yourself*, playing on loop, learning, livestreamed. That's this.

## The course

**Wyatt National** — par 72, 7,214 yards. Four par 3s, four par 5s, ten par 4s, two of each short/long hole per nine. Full hole-by-hole design: [docs/course-design.md](docs/course-design.md).

## Project status

- **Web prototype (this repo):** the always-on show. `index.html` is a self-contained build — open it and it plays.
- **Roadmap:** see [docs/architecture.md](docs/architecture.md) — the Unreal Engine 5.8 path to true 4K broadcast realism (one-hole vertical slice first), the OBS + NodeCG director stack, and the event-driven AI commentary booth.
- **Livestream & growth plan:** see [docs/livestream-plan.md](docs/livestream-plan.md) — platforms, the technical stack in build order, the clip machine, the coin economy, the Unreal leap, and the 30/60/90-day growth timeline.
- **Broadcast stack guide:** see [docs/broadcast-stack.md](docs/broadcast-stack.md) — the OBS scene collection, autonomous director state machine, NodeCG graphics, event-driven commentary pipeline, ambient audio, and 24/7 reliability. Free-tier only.
- **90-day launch playbook:** see [docs/launch-playbook.md](docs/launch-playbook.md) — the auto-clip system, winning clip formats, the Instagram → YouTube → Twitch funnel, and the day-by-day 90-day plan with weekly checklists.
- **Brand identity:** see [docs/brand-identity.md](docs/brand-identity.md) — the Mas Golfs logo concept, color palette, typography, on-screen identity rules, social templates, and naming conventions.
- **Sim engine spec:** see [docs/sim-engine.md](docs/sim-engine.md) — the JSON event schema, launch-condition physics, +3 calibration truth tables, lie/wind gating, the local decision engine, and the strokes-gained learning loop.
- **Course design v2:** see [docs/course-design-v2.md](docs/course-design-v2.md) — Wyatt National refined with MacKenzie/Doak principles, template holes, wind rotation, stroke index, and the strategic question on every hole.
- **Clubhouse Coins economy:** see [docs/coins-economy.md](docs/coins-economy.md) — the full prediction economy: odds model, skins/Nassau/props markets, payout math, leaderboards, anti-abuse, and the legal boundary.
- **Unreal vertical slice:** see [docs/unreal-vertical-slice.md](docs/unreal-vertical-slice.md) — the one-hole UE 5.8 plan: Hole 12 "The Picture," software list and costs, LiDAR pipeline, MetaHuman + swing mocap options, and go/no-go criteria.
- **Creator growth playbook:** see [docs/creator-growth.md](docs/creator-growth.md) — what's working for small golf creators in 2026: hooks, conversion math, collabs, community, thumbnails, and realistic timelines.
- **Voice options:** see [docs/voice-options.md](docs/voice-options.md) — free TTS engines compared for the two-voice commentary pipeline, with Kokoro-82M as the recommended default and setup steps.
- **60-day content calendar:** see [docs/content-calendar-60-day.md](docs/content-calendar-60-day.md) — a specific title, hook, and format for every day, with weekly themes and milestone days.
- **QA plan:** see [docs/qa-plan.md](docs/qa-plan.md) — the calibration harness, 24/7 soak test, web build checklist, graphics/commentary checks, coins economy tests, and the go-live checklist.
- **Commentary prompts:** see [docs/commentary-prompts.md](docs/commentary-prompts.md) — paste-ready prompt templates for both broadcast voices, per event type, with the hard rules and line-caching strategy.
- **Mobile experience:** see [docs/mobile-experience.md](docs/mobile-experience.md) — the PWA spec: five tabs, 59 Watch push alerts, one-thumb predictions, catch-up, and mobile performance budgets.
- **Self-improvement system:** see [docs/self-improvement.md](docs/self-improvement.md) — how Mas gets better autonomously: the learning architecture, the improvement ladder, slumps, noise vs. weakness, and the safeguards that keep 59 rare.
- **Analytics & observability:** see [docs/analytics.md](docs/analytics.md) — what to measure on the stream, clips, and sim, the free-tier tooling, the Sunday 30-minute review ritual, and what pages Mason.
- **Guest digital twins:** see [docs/guest-twins.md](docs/guest-twins.md) — how a guest's swing becomes a twin that plays Wyatt National against Mas, no travel, no filming day.

## Contributing

Open source under MIT. Issues and PRs welcome — especially on the shot model, the director logic, and the broadcast graphics. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Links

- Mason W Golf on Instagram — the brand anchor for the stream.
- The stream itself: always on, always playing.

*Mas Golfs — the Mason W Golf endless round.*
