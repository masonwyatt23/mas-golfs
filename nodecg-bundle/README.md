# Mas Golfs — NodeCG Graphics Bundle

The broadcast graphics for the Mas Golfs autonomous golf livestream, per
`docs/broadcast-stack.md` §4 and the brand system in `docs/brand-identity.md`.
Free, open source, no paid services: NodeCG (MIT) + plain HTML/CSS/JS.

## What's in here

```
nodecg-bundle/
├── package.json            # NodeCG bundle manifest (graphics + dashboard panel)
├── extension/
│   └── index.js            # Subscribes to the sim event bus (ws://localhost:4456),
│                           # writes replicants, fires lower-third messages
├── graphics/
│   ├── scorebug.html       # Always-on top-left bug — MAS · THRU n · score · handicap
│   ├── leaderboard.html    # Full-screen record book (top 10 + live row + ONE FIX)
│   ├── lower-third.html    # Shot data / hole result / milestone (5 s, slides in/out)
│   ├── ticker.html         # Bottom scrolling ticker from lastShot + roundState
│   ├── player-card.html    # "Mas — Mason's digital twin" + season stats + ONE FIX
│   └── hole-card.html      # Hole number, name, par, yards, wind, pin, elevation
├── dashboard/
│   └── panel.html          # Phone-friendly status + emergency-only manual override
└── shared/
    ├── style.css           # Design system (Fairway #0B3D2E, Gold #C9A227, Cream #F5F1E6)
    ├── mas-golfs.js        # Replicant/message shim + standalone demo loop
    ├── placeholder.js      # Realistic placeholder data (browser copy)
    └── placeholder-data.json # Same placeholder data (extension copy — keep in sync)
```

## Replicants (shared state, written by the extension)

| Replicant | Written on | Contents |
|---|---|---|
| `roundState` | Every event | Full round snapshot (score, thru, handicap, scorecard, stats, streak, coins) |
| `shotData` | `strike`, `apex`, `landing` | Club, ball speed, launch, spin, apex, carry, shape, contact, distance to pin, lie |
| `prediction` | `hole_start`, `decision` | Coins question, odds, pool, close timer, open flag |
| `lastShot` | `landing` | One-line result for the ticker |
| `lowerThird` | `strike`, `hole_end`, `milestone` | Current lower-third payload (also sent as a `showLowerThird` message) |

## Install in NodeCG

```bash
# 1. Copy the bundle into your NodeCG install
cp -r nodecg-bundle /path/to/nodecg/bundles/mas-golfs

# 2. Install dependencies (ws, for the event-bus client)
cd /path/to/nodecg/bundles/mas-golfs && npm install

# 3. Start NodeCG (default dashboard at http://localhost:9090)
node /path/to/nodecg/index.js
```

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `MAS_GOLFS_BUS_URL` | `ws://localhost:4456` | Sim event-bus WebSocket |
| `MAS_GOLFS_DEMO` | `0` | Set to `1` to run a local demo simulator (one shot cycle every ~36 s) with no sim engine |

## Preview each graphic (no NodeCG needed)

Every graphic renders from realistic placeholder data when opened directly in
a browser — no NodeCG, no sim engine required. A demo loop advances the shot
data every 8 seconds so you can see updates live; add `?static=1` to freeze it.

```bash
# From the repo root — serves the bundle so relative paths resolve:
python3 -m http.server 8080 --directory nodecg-bundle
# Then open:
#   http://localhost:8080/graphics/scorebug.html
#   http://localhost:8080/graphics/leaderboard.html
#   http://localhost:8080/graphics/lower-third.html
#   http://localhost:8080/graphics/ticker.html
#   http://localhost:8080/graphics/player-card.html
#   http://localhost:8080/graphics/hole-card.html
#   http://localhost:8080/dashboard/panel.html
```

Or open the files directly with `file://` — the relative `../shared/` paths work
either way. Note: Google Fonts load from the network; offline, the graphics fall
back to system sans/mono fonts.

## Use in OBS

Add each graphic as a **Browser Source**, 1920×1080, transparent:

| Source | URL |
|---|---|
| Scorebug | `http://localhost:9090/bundles/mas-golfs/graphics/scorebug` |
| Leaderboard | `http://localhost:9090/bundles/mas-golfs/graphics/leaderboard` |
| Lower Third | `http://localhost:9090/bundles/mas-golfs/graphics/lower-third` |
| Ticker | `http://localhost:9090/bundles/mas-golfs/graphics/ticker` |
| Player Card | `http://localhost:9090/bundles/mas-golfs/graphics/player-card` |
| Hole Card | `http://localhost:9090/bundles/mas-golfs/graphics/hole-card` |

Scene placement follows `docs/broadcast-stack.md` §2.2: scorebug + ticker always
on in camera scenes, lower-third hidden by default (shown on `strike` /
`hole_end`), leaderboard full-screen with game capture hidden, hole card on the
flyover scene.

## Brand rules applied

- Palette: Fairway `#0B3D2E`, Deep Rough `#062A1F`, Gold `#C9A227`,
  Cream `#F5F1E6`, Mist `#9DB8A6`, Tracer `#FFD34D`, Alert `#E4572E`.
- Fonts (all free, Google Fonts): Archivo (display), Inter (text),
  JetBrains Mono (all data, tabular figures).
- Flat colors only — no decorative gradients in graphics.
- Scorebug tells a newcomer the story in 3 seconds: who, where in the round,
  how he's doing, what he's chasing (Road to 59).
- Lower-thirds slide in over 300 ms, hold 5 s, slide out; never overlap the scorebug.
- The mark is the left-handed swing arc (gold) over the ball (dark green) with
  the impact tick, drawn as inline SVG in `shared/mas-golfs.js`.
