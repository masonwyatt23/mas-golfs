# Mas Golfs — NodeCG Graphics Bundle

The broadcast graphics for the Mas Golfs autonomous golf livestream, per
`docs/broadcast-stack.md` §4 and the brand system in `docs/brand-identity.md`.
Free, open source, no paid services: NodeCG (MIT) + plain HTML/CSS/JS.

## What's in here

```
nodecg-bundle/
├── package.json            # NodeCG bundle manifest (graphics + dashboard panel)
├── extension/
│   ├── index.js            # Subscribes to the sim event bus (ws://localhost:4456),
│   │                       # writes replicants, fires lower-third messages
│   └── coins-bridge.js     # Clubhouse Coins mirror: bus events -> coins replicants.
│                           # Mirrors market state only — never runs the economy
│                           # (no balances, no payouts). See "Clubhouse Coins" below.
├── graphics/
│   ├── scorebug.html       # Always-on top-left bug — MAS · THRU n · score · handicap
│   ├── leaderboard.html    # Full-screen record book (top 10 + live row + ONE FIX)
│   ├── lower-third.html    # Shot data / hole result / milestone (5 s, slides in/out)
│   ├── ticker.html         # Bottom scrolling ticker from lastShot + roundState
│   ├── player-card.html    # "Mas — Mason's digital twin" + season stats + ONE FIX
│   ├── hole-card.html      # Hole number, name, par, yards, wind, pin, elevation
│   └── coins.html          # Bottom-left Clubhouse Coins panel — open market, odds, top 5
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
| `shotData` | `strike`, `apex`, `landing` | Club, ball speed, launch, spin, target carry (intended carry at strike), apex, carry, shape, contact, distance to pin, lie, total distance |
| `prediction` | Every event (via the coins bridge) | Featured coins market: question, odds, pool, open flag, market id, status. `closes_in_s` is `null` from the mirror — the market closes at the swing (per-shot) or at hole end (per-hole), and the mirror never knows the seconds. |
| `coinsMarkets` | Every event (via the coins bridge) | `{ markets: [...], active_market_id }` — every market this round in `Market.to_replicant()` shape, plus `market_type` (`per_hole` / `per_shot`), `round_no`, `hole`, `shot`, and `source` (`mirror` / `economy`) |
| `coinsLeaderboard` | Every event (via the coins bridge) | `{ week_monday, weekly: [top 5], alltime: [top 5], champion, bonus_pool }` — weekly top 5 resets Monday 00:00 ET; all-time never resets |
| `lastShot` | `landing` | One-line result for the ticker |
| `lowerThird` | `strike`, `hole_end`, `milestone` | Current lower-third payload (also sent as a `showLowerThird` message) |

## Clubhouse Coins — the coins mirror and the bridge contract

The bundle shows Clubhouse Coins markets, but it does **not** run the
economy. `extension/coins-bridge.js` is a mirror: it turns sim bus events
into market replicants using the same base-rate tables and odds math as
`coins/odds.py`, so the screen is right even before the economy process
exists. It owns no balances, takes no stakes, and computes no payouts —
there is no payout code in the bundle, by design. The economy itself lives
in `coins/` (Python) and is the only authority on wallets, stakes, and
payouts.

### Market lifecycle (driven by the bus)

| Bus event | Mirror action |
|---|---|
| `hole_start` | Open the per-hole market ("Birdie or better on N?", par-based rate: par 3 0.12 / par 4 0.16 / par 5 0.30) |
| `decision` | Open the per-shot market: fairway (par-4/5 tee shot), GIR (approach or par-3 tee shot), inside-10-ft (pitch/chip), or one-putt (putt). Layups and bunker recoveries open no per-shot market — the per-hole market stays featured. |
| `putt_read` | Refine an open one-putt market with the real distance and make % (the decision has no distance to the pin) |
| `strike` | Close the open per-shot market (stakes lock at the swing) |
| `landing` | Resolve the per-shot market from the real result (`fairway_hit` / `on_green` / `dist_to_pin_ft ≤ 10`). Putt markets wait for `putt_result`. |
| `putt_result` | Resolve the open one-putt market (`made` → yes) |
| `hole_end` | Resolve the per-hole market (birdie or better → yes); void any per-shot market still open |
| `round_start` | Clear the previous round's markets |
| `round_end` | Void any market still open |

The featured market (the `prediction` replicant and the coins graphic's
headline) is the open per-shot market while a shot is live, else the open
per-hole market, else the most recently resolved market. With no pools yet,
displayed odds equal opening odds; when the economy feeds pools, the
displayed odds are the 50/50 model/pool blend from `coins/odds.py`,
moving at most ±25% from the opening odds.

### Weekly reset

The weekly leaderboard resets **Monday 00:00 ET**: the week's winner is
archived as Clubhouse Champion, the weekly board clears, and the bonus
pool refills to 10,000 CC. The all-time board never resets. The reset is
checked on every bus event (and every snapshot poll), so it fires on the
first event after midnight — there is no separate timer.

### How the real economy feeds the mirror (bridge contract)

When the economy process exists, it writes a JSON snapshot **atomically**
(write to a temp file, then rename) to the path in
`MAS_GOLFS_COINS_SNAPSHOT`. The extension polls that file every 2 s and
merges it into the mirror. Economy-fed values always win: a market in the
snapshot replaces the mirror market with the same id, economy odds are
shown as-is, and economy leaderboards replace the mirror's (empty) board.
A malformed snapshot is logged and ignored — the mirror keeps carrying
the screen.

Snapshot shape (markets are `Market.to_replicant()` plus optional
`pools` / `winning_outcome`):

```json
{
  "week_monday": "2026-11-09",
  "bonus_pool": 9950,
  "markets": [
    {
      "market_id": "r47-h12-hole",
      "market_type": "per_hole",
      "question": "Birdie or better on 12?",
      "odds": { "yes": 2.4, "no": 1.6 },
      "pool_coins": 1840,
      "open": true,
      "status": "open",
      "winning_outcome": null,
      "pools": { "yes": 800, "no": 1040 }
    }
  ],
  "weekly_leaderboard": [{ "display_name": "FairwayFan", "balance": 2616, "streak": 3 }],
  "alltime_leaderboard": [{ "display_name": "FairwayFan", "balance": 12480, "streak": 3 }],
  "champion": { "display_name": "FairwayFan" }
}
```

### What is live vs what still needs the economy process

- **Live now:** market open/close/resolve from real bus events, display
  odds from the base tables, the coins graphic, the weekly-reset boundary.
- **Not live yet (needs the economy process):** real pools and blended
  odds (mirror shows empty pools, so displayed odds equal opening odds),
  real leaderboards and champion (mirror shows an empty board — the
  graphic says "No bets yet this week"), and all staking/payouts. The
  economy process does not exist yet; until it does, nothing on the
  coins graphic is backed by real coins.

## Course data — Wyatt National v3

The course is **par 72, 7,602 yards** (front 3,808 / back 3,794), per
`docs/course-design-v3.md`. The full 18-hole table (name, par, yards per hole)
lives in `shared/placeholder-data.json` and `shared/placeholder.js` under
`course` — keep both copies in sync. The placeholder round is on hole 12,
"The Picture", a par 3 of **172 yards** (22 ft downhill).

Hole-by-hole yardages are **not** hardcoded into the graphics: the hole card,
scorebug, and ticker read the current hole from `roundState.current_hole`,
which the extension writes from `hole_start` bus events. The `course` table
is the single reference copy for previews and for any graphic that needs the
full routing.

## Live distance counter (lower-third, shot variant)

The bus fans a shot out as `strike` → `apex` → `landing`, and the extension
mirrors each phase into `shotData`. The shot lower-third turns those three
discrete updates into a live readout:

- **Strike:** the counter starts at 0 and counts up over an estimated flight
  time (ballistic estimate from ball speed + launch angle, stretched 15% for
  drag — close enough for a counter, and corrected the moment real data
  arrives). The estimate aims at `target_yards`, the intended carry the
  extension stores from the `strike` event.
- **Apex:** `carry_yds` arrives and the counter snaps its target to the real
  carry, so the number on screen is never an estimate for long.
- **Landing:** `total_yds` arrives and the line locks in:
  `CARRIED 166 YDS · TOTAL 172 YDS`.

Because the extension clears the previous shot's outcome fields (`apex_ft`,
`carry_yds`, `total_yds`, `shape`, `lie`, `dist_to_pin_ft`) on every `strike`,
a new shot always restarts the counter from zero instead of flashing the last
shot's numbers. The shot lower-third holds **8 s** (other variants hold 5 s)
so the flight and the landing result stay on screen.

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
| `MAS_GOLFS_DEMO` | `0` | Set to `1` to run a local demo simulator (one shot cycle every ~54 s) with no sim engine |
| `MAS_GOLFS_COINS_SNAPSHOT` | *(unset)* | Path to the coins-economy snapshot JSON (see "Clubhouse Coins" above). Unset = the mirror runs standalone with empty pools and an empty board. |

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
#   http://localhost:8080/graphics/coins.html
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
| Coins | `http://localhost:9090/bundles/mas-golfs/graphics/coins` |

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
