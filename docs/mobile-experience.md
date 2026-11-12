# Mas Golfs — Mobile Experience (PWA / Installable App Spec)

**The product:** the Mas Golfs show, in your pocket. A left-handed +3 digital-twin golfer named Mas plays 18-hole rounds on repeat at Wyatt National, forever, on livestream. The season arc is **Road to 59**: the chase for a sub-60 round.

**The one-line rule for mobile:** the phone is not a smaller desktop stream. It is a companion you glance at between holes and a remote control for the show you are watching on TV. Everything on mobile is designed for one thumb, one hand, bad signal, and a 10-second attention window.

Everything in this document is free-tier: no paid push provider, no paid hosting, no paid APIs. The PWA is served from the same free static host as the web build, push runs on free Web Push (VAPID) via a small free-tier worker, and all data comes from the existing sim event bus.

This document is consistent with the rest of the repo:

- [docs/brand-identity.md](brand-identity.md) — colors, fonts, naming, do/don't rules.
- [docs/broadcast-stack.md](broadcast-stack.md) §4 (NodeCG graphics) and §9 (59 Watch).
- [docs/coins-economy.md](coins-economy.md) — Clubhouse Coins: free play money, closed-loop, never purchasable or convertible.
- [docs/sim-engine.md](sim-engine.md) — the JSON event schema the app subscribes to.
- [docs/performance-audit.md](performance-audit.md) — the web build's mobile performance constraints.
- [docs/launch-playbook.md](launch-playbook.md) — the Instagram → YouTube → Twitch funnel the app plugs into.

---

## 1. What the mobile viewer gets

The app has five tabs, in this order. No more. Five is the whole product.

| Tab | What it is | What the viewer does there |
|-----|-----------|---------------------------|
| **Watch** | The live broadcast, vertical-first. | Watches the stream, sees the scorebug, 59 Watch bug, and shot-data lower-thirds. One tap to full-screen. |
| **Predict** | Clubhouse Coins markets. | Stakes coins on the current shot/hole/round market. One thumb, under 10 seconds (§4). |
| **59 Watch** | The chase, live. | Sees Mas's score vs. the 59-pace line, strokes he can afford to drop, live probability of breaking 60, and the closest-calls record book. |
| **Board** | Leaderboards + scorecard. | Live scorecard for the current round, weekly and all-time coin leaderboards, last-10 aggregates, handicap trend. |
| **Clips** | The clip feed. | Vertical clip feed (latest first), 20–35 s each, swipe up for the next. Share to any app. |

### 1.1 Watch tab — the broadcast, vertical-first

- **Default view is the live stream in 16:9, top of screen**, with the broadcast scorebug and 59 Watch bug visible in-frame. Below the player: the current shot market (compact, tappable to the Predict tab), the last-shot line in mono, and the ticker.
- **One tap rotates to full-screen landscape** (or portrait full-screen on phones that prefer it). Full-screen keeps the scorebug and 59 Watch bug; everything else hides until tapped.
- **Portrait full-screen** is a first-class mode, not an afterthought: the video fills the width, the scorebug sits top-left, the 59 Watch bug top-right, and a single swipe up reveals the prediction sheet (§4).
- **No autoplay with sound.** Video starts muted (platform rules); a single large unmute button appears once. Audio state persists across sessions.
- **Background behavior:** when the app is backgrounded, video pauses and the audio bed stops within 5 seconds (same rule as the web build's `visibilitychange` pause). The viewer is never draining battery on a stream they can't see. A persistent mini-player is *not* offered — this is a deliberate choice: the show is a screensaver for a TV, not a podcast for a pocket.
- **Low-data mode** (a toggle in Watch, remembered per device): drops the stream to 480p and disables the 3D preview entirely, showing only the scorebug, shot data, and tracer line as a 2D canvas. See §7 for budgets.

### 1.2 Predict tab — the game

The full coins experience, designed for one thumb (§4). Shows the open market, the viewer's two balances (weekly / all-time), the live leaderboard for the current market, and the last three resolved markets with payouts.

### 1.3 59 Watch tab — the chase

- **Live pace chart:** a simple line chart — Mas's score-to-par after each hole vs. the 59-pace line. One line, two colors (cream for Mas, gold for the pace line). No chart junk, no axes beyond hole numbers.
- **The numbers, in mono:** current score, strokes vs. pace, strokes he can still afford to drop, live probability of breaking 60.
- **The record book:** rounds on pace at the turn, best 59-watch moments, closest calls, and the all-time "closest to 59" board. A round that ends 60 or 61 is a near-miss story, not a failure.
- **Notification control lives here** (§3): the 59 Watch alert toggle is on this tab, not buried in settings, because this is where the viewer decided they care.

### 1.4 Board tab — scorecard and leaderboards

- **Live scorecard** for the current round: hole-by-hole scores, to par, fairways, GIR, putts — the same data the broadcast scorebug carries, in table form.
- **Coin leaderboards:** weekly (resets Monday 00:00 ET) and all-time, top 10 each, with the viewer's own rank highlighted even when they are outside the top 10.
- **Last-10 aggregate and handicap trend** with the trend arrow, per the brand rules.

### 1.5 Clips tab — the feed

- **Vertical feed, latest first, swipe up for the next clip.** Each clip is 20–35 s with the hook in the first 2 seconds, captions burned in, and the mono data line (`7-IRON · 184 YDS · 4 FT`) beneath the player.
- **Share sheet** on every clip: native share to Instagram, TikTok, X, Messages, or copy link. No in-app repost wall — sharing *out* is the growth engine.
- **Offline clips:** the last 10 clips are cached on-device (§5) so the feed works on the subway.

---

## 2. Information architecture and navigation

- **Bottom tab bar, five tabs, always visible.** Labels in Inter, icons in the brand mark style (no stock icon set — the mark's swing-arc language is reused: arc for Watch, coin for Predict, gold "59" for 59 Watch, table for Board, play triangle for Clips).
- **No hamburger menu.** Settings is a single gear on the Board tab; everything else is one tap away.
- **Deep links for every screen** (shareable URLs): `/watch`, `/predict`, `/59`, `/board`, `/clips`, `/clips/<id>`, `/round/<n>`. A clip shared from the app opens in the app when installed, in the browser otherwise.
- **The scorebug is persistent.** On every tab, a slim top strip shows `MAS · THRU n · score to par · 59 PACE` (or `59 WATCH ON` in gold when active). Tapping it jumps to Watch. A viewer never loses the thread of the round while predicting or scrolling clips.

---

## 3. Push notifications — the moment engine

Push is the single most powerful mobile feature and the easiest to ruin. The rules below are the whole design: **notify on moments, never on routine.**

### 3.1 What triggers a notification

| Trigger | When it fires | Priority |
|---------|--------------|----------|
| **59 on the line** | Mas reaches the 18th tee with 59 still possible, or any hole from 15 onward where the pace math flips to "on the line" | **High** — the one notification that matters most. Always allowed, even if the viewer has muted everything else except this one. |
| **Eagle** | Mas holes an eagle | High |
| **Hole-out / hole-in-one** | Any hole-out from off the green, any ace | High |
| **59 Watch turns ON** | Mas goes under the 59-pace line for the first time in a round | High |
| **New round starts** | A new 18-hole round begins | Normal — only if the viewer opted into round starts |
| **New course record** | A round finishes as a new Wyatt National record | High |
| **Weekly leaderboard reset** | Monday 00:00 ET reset + the viewer's final weekly rank | Normal — one per week, Monday morning |
| **Milestone** | Handicap improves, streak record, first bogey-free round | Normal |

### 3.2 What NEVER triggers a notification

- Birdies. (Mas makes birdies constantly; a birdie notification is spam by definition.)
- Every shot, every hole, every market opening. Markets are visible in-app; they do not push.
- Promotional messages, "come back" nudges, or anything that is not a golf moment. **No re-engagement spam, ever.** If there is no moment, there is no notification. Silence is a feature.
- Anything about coins balances, daily allowances, or streaks. Coins are the game inside the app, not a reason to interrupt someone's day.

### 3.3 Frequency caps — the anti-spam contract

| Cap | Value |
|-----|-------|
| Max notifications per day | **3** (hard cap, across all triggers) |
| Max per hour | **1** |
| Quiet hours | **23:00–08:00 local** — no notifications except "59 on the line" (the viewer opted into the chase; a 59 at 2am is still a 59) |
| Cooldown after a High notification | **30 minutes** before another High may fire (a second eagle 10 minutes later is covered by the first notification's context; the app badge updates instead) |
| Duplicate suppression | The same trigger may not fire twice for the same round (e.g. 59 Watch turns on, off, on again — notify once per round) |

Caps are enforced server-side, not in the client, so they hold even if the viewer reinstalls. The caps are stated in the notification settings screen, in plain language: "At most 3 a day. Never after 11pm unless 59 is on the line."

### 3.4 Notification design

- **Title:** the moment, in the brand voice, max 6 words: "59 IS ON THE LINE." / "EAGLE. HOLE 15." / "HE DID IT. 59."
- **Body:** one mono data line: `ROUND 47 · −9 THRU 17 · NEEDS BIRDIE ON 18`.
- **Deep link:** opens the app straight to Watch (or 59 Watch for pace triggers), full-screen, unmuted if the viewer has previously unmuted.
- **Grouping:** notifications stack by round, never by trigger type. One notification per round in the shade, updated in place.
- **Opt-in granularity:** three toggles, all on by default at install prompt time, each independently switchable:
  1. **59 Watch** (59 on the line + pace flips + record) — the chase.
  2. **Big moments** (eagle, hole-out, ace) — the drama.
  3. **Round starts & weekly** (new round, Monday reset) — the routine.
- **The install-time prompt** asks for push permission only *after* the viewer has watched at least one moment in-app (first eagle, first 59-watch flip, or 10 minutes of watch time) — never on first launch. Asking a stranger for notification permission is the fastest way to get a permanent "no."

### 3.5 Delivery (free-tier)

- **Web Push with VAPID**, served from a small free-tier worker (e.g. Cloudflare Workers free tier) that subscribes to the sim event bus and evaluates the trigger table. No paid push provider (no OneSignal, no Firebase paid tier).
- **Subscriptions are per-device, stored server-side** with the viewer's notification preferences. Unsubscribe is one tap in settings and one tap from any notification (Android action button / iOS notification settings deep link).
- **Delivery budget:** the trigger table above produces at most ~5–10 pushes per viewer per week in practice, which stays inside every free tier's limits.

---

## 4. The prediction flow on a phone — one thumb, under 10 seconds

The whole point of Clubhouse Coins on mobile is that a viewer can stake while watching, without looking away from the golf for more than a glance. The flow has exactly three steps and one thumb.

### 4.1 The flow

1. **The market appears.** When a market opens (announced on the broadcast and in-app), a bottom sheet slides up on Watch — or the Predict tab shows it full-screen. The question is one line: "Does Mas hit the fairway on 12?" with the odds and pool shown beneath in mono.
2. **One tap picks a side, one tap picks a stake.** Two large outcome buttons (e.g. YES / NO), then three stake chips: **25 / 50 / 100 CC** (sized to the market's cap; see coins-economy §4). No keyboard, no slider, no custom amount on mobile — custom amounts live on desktop only. The stake chips are at least 48 px tall, thumb-reachable in the bottom third of the screen.
3. **Confirm is automatic.** Tapping a stake chip places the prediction immediately — no separate confirm screen. A 3-second undo window appears ("Staked 50 CC on YES — Undo"), then it locks. This is the only way the flow fits in 10 seconds.

**Total: 2 taps, ~5 seconds, one thumb, no keyboard.** The 10-second budget includes reading the question.

### 4.2 States and feedback

- **Market open:** countdown ring shows seconds to close (markets close before the shot, per the coins-economy lifecycle). The ring turns gold under 10 seconds, Alert red under 5.
- **Staked:** the sheet shows the viewer's position, the payout if they win ("Win: +83 CC"), and the pool size. The outcome buttons show the live split ("62% on YES").
- **Resolved:** the result lands on the same sheet with the payout or loss, then the sheet dismisses itself after 4 seconds. No modal to dismiss.
- **Insufficient balance:** the stake chips that exceed the balance are greyed out with the balance shown ("Balance 40 CC"); the daily allowance reminder appears ("+500 CC tomorrow") — never a prompt to buy coins, because there is nothing to buy.
- **Market closed:** the sheet shows "Market closed" and the next market's open time. No dead ends.

### 4.3 Accessibility and safety

- Minimum touch target **48×48 px** everywhere in the flow; stake chips 56 px tall.
- Odds and payouts always in JetBrains Mono, tabular figures, minimum 16 px.
- The prediction sheet never covers the video entirely in portrait — the top 25% of the screen keeps the stream visible so the viewer can watch the shot they just bet on.
- **No accidental stakes:** the sheet requires a deliberate tap on a stake chip; swiping it away cancels. The 3-second undo covers fat-finger taps.

---

## 5. Offline and catch-up behavior

The show never stops, but the viewer's connection does. The app is built for that.

### 5.1 What works offline

| Feature | Offline behavior |
|---------|-----------------|
| **Scorecard** | Last synced scorecard is cached; shows "As of Hole 14 · 12 min ago" with a stale timestamp. Readable offline, obviously marked. |
| **Leaderboards** | Last synced weekly/all-time boards cached; same stale marking. |
| **59 Watch record book** | Cached; the live pace chart shows the last synced state. |
| **Clips** | Last 10 clips cached on-device (see §5.2); playable offline. |
| **Predictions** | **Cannot be placed offline.** Markets resolve on the live event bus; an offline stake cannot be confirmed. The Predict tab shows "You're offline — markets resume when you reconnect" with the next market's scheduled time. No queued stakes, no ambiguity. |
| **Live stream** | Cannot play offline (obviously). The Watch tab shows the last frame's scorebug state and a "Watch the replay" button that opens the most recent round's clip reel. |

### 5.2 Catch-up: "watch the round later"

- **Round replays:** every completed round gets a catch-up reel — the auto-clipped moments stitched in order (see clip-pipeline), 3–5 minutes, vertical, watchable in the Clips tab. A viewer who missed Round 47 watches the reel, not 4 hours of stream.
- **The scorecard is the catch-up spine:** opening a past round shows the full hole-by-hole card, the 59-watch story for that round, and the reel. One screen, whole round.
- **Catch-up notifications are never sent.** A viewer who missed a round finds it in the app; the app does not chase them about it.
- **Cache policy:** service worker caches the app shell, the last scorecard, the last leaderboards, the 59-watch record book, and the last 10 clips (video, capped at ~150 MB total, evicted oldest-first). Cache storage is checked at install and the viewer is warned if the device is low on space.

### 5.3 Reconnection

- On reconnect, the app re-syncs in this order: scorecard, 59-watch state, open market, leaderboards, clip feed. The whole re-sync is under 2 seconds on a normal connection; a subtle "Updated just now" line confirms it. No full reload, no lost scroll position.

---

## 6. Install prompt and home-screen design

### 6.1 Installability (PWA)

- **Manifest:** `name: "Mas Golfs"`, `short_name: "Mas Golfs"`, `display: "standalone"`, `orientation: "portrait-primary"`, `theme_color: #0B3D2E` (Fairway), `background_color: #062A1F` (Deep Rough), icons in the brand mark (192×192 and 512×512, maskable, gold arc on dark green with the 4 px gold ring from the social-avatar lockup).
- **Service worker:** app-shell caching + the offline policy in §5.2. The worker is versioned; updates install in the background and apply on next launch, never mid-round.
- **Install criteria:** the app meets the standard PWA installability checklist (manifest, service worker with fetch handler, HTTPS, icons) so the browser offers installation natively on Android and iOS (Add to Home Screen).

### 6.2 The install prompt — asked once, at the right moment

- **Never prompt on first launch.** The prompt appears only after the viewer has had a moment in-app: first eagle watched, first 59-watch flip, first prediction placed, or 10 minutes of total watch time — whichever comes first.
- **The prompt is the app's own card, not the browser's default:** "Add Mas Golfs to your home screen — get notified when 59 is on the line." One button: "Add to Home Screen." One dismiss: "Not now." Dismissing hides the prompt for 14 days; it never reappears more than 3 times total.
- **After install, the push-permission ask** follows the rule in §3.4: only after a moment, never immediately after install.

### 6.3 Home-screen icon and splash

- **Icon:** the brand mark alone (gold swing arc over the dark-green ball), centered, on Fairway `#0B3D2E`, with the 4 px gold ring. No wordmark — the icon is 48 px on most home screens and the wordmark would be illegible.
- **Splash screen:** Deep Rough `#062A1F` field, mark centered, "MAS GOLFS" beneath in Archivo, "ROAD TO 59" in small caps beneath that. No spinner, no loading bar — the splash is the brand, and the app shell loads behind it in under 2 seconds.

---

## 7. Performance budgets for mobile

These budgets are pass/fail criteria, not aspirations. They are measured on a mid-range Android phone (e.g. Pixel 6a class) on a 4G connection, and on an iPhone 12 class device on Wi-Fi.

### 7.1 Load budgets

| Metric | Budget |
|--------|--------|
| **First paint** (app shell) | ≤ 1.5 s on 4G, ≤ 1 s on Wi-Fi |
| **Time to interactive** | ≤ 3 s on 4G |
| **First video frame** | ≤ 3 s after tap on 4G (≤ 2 s on Wi-Fi) |
| **App shell size** | ≤ 200 KB gzipped (HTML + CSS + JS, excluding video and fonts) |
| **Total page weight on first load** | ≤ 500 KB excluding the video stream |
| **Fonts** | Two families only (Archivo + Inter on UI; JetBrains Mono loaded lazily for data views). Never render-blocking — `font-display: swap`. |

### 7.2 Runtime budgets

| Metric | Budget |
|--------|--------|
| **Scroll / swipe** | 60 fps, no jank on the clip feed (virtualized list, images lazy-loaded) |
| **Prediction sheet** | Opens in ≤ 200 ms from market announcement |
| **Re-sync on reconnect** | ≤ 2 s (§5.3) |
| **Battery** | ≤ 10% per 30 min of active watching on Wi-Fi (per the QA plan's mobile budget); backgrounded app uses < 1% per hour (video paused, audio stopped, only the push subscription alive) |
| **Data** | Default stream 720p on mobile (~1.5 GB/hr); low-data mode 480p (~0.7 GB/hr) with the 2D tracer view. The viewer is warned before the stream exceeds 1 GB in a session on cellular ("You've used 1 GB on cellular — switch to low-data mode?"). |
| **Memory** | App holds ≤ 150 MB RAM on mobile; clip cache capped at ~150 MB storage (§5.2). |

### 7.3 How the budgets are met (free)

- **The app is a PWA, not a native app:** no app-store build, no native SDKs, no paid distribution. One codebase, served from the same free static host as the web build.
- **The video is the platform's problem:** the live stream is delivered by YouTube Live / Twitch (free), not by our servers. The PWA embeds the platform player; we pay no bandwidth for video.
- **The data layer is the existing event bus:** the app subscribes to the same JSON event stream as the broadcast graphics (see sim-engine.md §1 and broadcast-stack.md §1). No new backend, no new database.
- **The 3D preview is optional on mobile:** the full Three.js scene is desktop-first; on phones the default is the platform video player plus 2D overlays. The 3D build is never forced onto a phone.
- **Images are WebP, lazy-loaded, and sized:** clip thumbnails at 480 px wide, never the 1080 px source.

### 7.4 Measurement

- Budgets are checked with Lighthouse (mobile) on every release: Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95, PWA installable. A release that drops Performance below 90 does not ship.
- Real-user measurement: the app logs first-paint and time-to-interactive to the same free analytics the site already uses (no new vendor), sampled at 10% of sessions.

---

## 8. What mobile does NOT do

- **No native app.** The PWA is the product. No App Store / Play Store submission, no native code, no review queue, no 30% cut. If a native app is ever justified, that is a separate decision with a separate budget — not this document.
- **No in-app purchases.** There is nothing to buy. Coins are earned, never bought (coins-economy §1). No store, no price, no payment flow, no Apple/Google in-app-purchase integration.
- **No account system.** The viewer is identified by their platform identity (YouTube/Twitch) for coins and by device for push. No email signup, no password, no profile page. A viewer who never logs in still watches, still sees the scorebug, still gets 59 Watch — they just can't predict until they connect a platform identity.
- **No chat inside the app.** Chat lives on YouTube/Twitch where the stream lives. The app does not fork the community.
- **No second screen that replaces the TV.** The phone is a companion and a remote, not a replacement. The big screen is where the show lives; the phone is where you stake, check the pace, and get tapped when 59 is on the line.

---

## 9. Build order

1. **PWA shell** — manifest, service worker, app-shell caching, installability checklist. (1 week)
2. **Watch + Board tabs** — embed the platform player, scorebug strip, live scorecard, leaderboards. (1 week)
3. **Predict tab** — the one-thumb flow (§4) against the coins-economy service. (1 week)
4. **59 Watch tab + push** — pace chart, record book, VAPID push worker with the trigger table and caps (§3). (1 week)
5. **Clips tab + offline** — vertical feed, share sheet, cache policy (§5). (1 week)
6. **Polish + budgets** — Lighthouse ≥ 90, the §7 budgets verified on a real mid-range phone, install-prompt timing tuned. (1 week)

Six weeks, one engineer, free tools throughout. Each step is independently shippable; the app is useful from step 2 onward.
