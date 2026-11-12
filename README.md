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

## Project status

- **Web prototype (this repo):** the always-on show. `index.html` is a self-contained build — open it and it plays.
- **Roadmap:** see [docs/architecture.md](docs/architecture.md) — the Unreal Engine 5.8 path to true 4K broadcast realism (one-hole vertical slice first), the OBS + NodeCG director stack, and the event-driven AI commentary booth.

## Contributing

Open source under MIT. Issues and PRs welcome — especially on the shot model, the director logic, and the broadcast graphics. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Links

- Mason W Golf on Instagram — the brand anchor for the stream.
- The stream itself: always on, always playing.

*Mas Golfs — the Mason W Golf endless round.*
