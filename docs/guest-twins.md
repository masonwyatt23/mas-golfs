# Mas Golfs — Guest Digital Twin System

**The concept:** a guest golfer's swing goes in, and their twin plays Wyatt National against Mas. The guest doesn't travel, doesn't film, doesn't even need to be present. One swing video — or a launch-monitor export, or a stat profile — becomes a calibrated digital twin that competes in the show, and the guest's audience comes to watch *their* golfer try to beat Mas.

This is the collab format no other golf channel has (see [creator-growth.md §4.2](creator-growth.md) — the guest ladder). Every other channel's collab costs a filming day, a location, and a schedule. Ours costs a phone video. That is why it scales.

---

## 1. What a guest twin is (and isn't)

A guest twin is a **calibrated skill model, not a likeness**. It is not a photorealistic avatar of the guest, not a mocap of their body, and not a claim that the twin *is* the guest. It is a golfer model built from the guest's real numbers — handicap, driving distance, dispersion, strengths, weaknesses — that plays by the same physics and the same decision engine as Mas (see [sim-engine.md](sim-engine.md)).

The honesty rule that governs everything: **a twin is better than the guest only if the guest's numbers say so.** Mas is a +3 because his delivery distribution is tighter, not because the physics is kinder — the same rule applies to every guest. If a 12-handicapper's twin shoots 68, the audience knows it's fake, and the format dies. The twin must play like the guest plays: same misses, same strengths, same bad holes.

What the twin *does* carry of the guest:

- Their name, on screen, in the brand system (see §6).
- Their handedness, their shot shape, their tempo — the things a swing video actually shows.
- Their numbers — the calibration (§3).
- Their decisions — the twin uses the same decision engine as Mas, so it clubs up into wind, lays up when the number says lay up, and goes for it when the number says go. The guest's *tendencies* (aggressive vs. conservative) are a calibration input, not a script.

What the twin does *not* carry:

- No face, no voice, no likeness. The guest is represented by their twin card, their name, and their golf — never by a fake body or a fake voice.
- No invented backstory. If the guest wants to tell their story, they do it in their own post, on their own channel.

---

## 2. How a guest submits their swing — three paths

The guest chooses the path that matches what they have. All three end at the same place: a twin profile (see §3). The paths are ranked by how much they tell us, not by how "good" the guest is.

### Path A — Phone video (the default)

**What the guest sends:** one down-the-line swing video, full swing, driver, shot on a phone. 10–20 seconds. No special equipment, no tripod required (a range basket or a friend holding the phone works).

**What we ask for in the video:**

- Down-the-line view (camera behind the golfer, on the target line), full body in frame, ball visible.
- One clean full swing with a driver. A second swing with a 7-iron if they have it — the iron swing tells us more about delivery than the driver does.
- The ball's result if they know it: where it went, roughly how far. ("Drew it, about 250" is enough.)
- Their handicap (or best recent scores), their usual miss, and one sentence on how they play: "I hit it far and wild," "I'm short and straight," "great putter, terrible driver."

**What we take from it:** handedness, tempo, swing shape (draw/fade tendency, steep/shallow), balance, and — honestly — a sanity check on the numbers they claim. A video of a smooth, balanced swing attached to a claimed 300-yard drive is believable. The same claim attached to a swing that loses its balance is not, and the twin is calibrated down.

**Why this is the default:** every golfer has a phone, and every golfer has a swing video already, or can make one in two minutes at the range. Zero friction is the whole point of the format.

### Path B — Launch-monitor data (the precise path)

**What the guest sends:** a launch-monitor export (TrackMan, GCQuad, Mevo+, Rapsodo — any of them) of 10+ driver shots and 10+ 7-iron shots, plus their handicap.

**What we take from it:** the real calibration numbers, directly — club speed, ball speed, launch angle, spin rate, carry distance, and dispersion (left/right spread, distance spread). This is the gold standard: the twin's dispersion table is built from the guest's actual shot pattern, not from a handicap lookup.

**When to use it:** any guest who has access to a monitor (a fitting, a sim session, a TrackMan range) should use this path. It takes five minutes and it makes the twin meaningfully more accurate — and accuracy is what makes the match watchable.

### Path C — Stat profile (the no-video path)

**What the guest sends:** handicap (or GHIN/scoring history), average driving distance, and honest answers to five questions:

1. What's your usual miss off the tee?
2. Best part of your game? (driving / irons / short game / putting)
3. Worst part of your game?
4. Aggressive or conservative — when you're between clubs, do you take the extra club or the smooth one?
5. One number you're proud of (e.g. "I average 28 putts," "I hit 60% of fairways").

**What we take from it:** a twin built from the handicap-benchmark tables in the sim spec (see §3.2). Less precise than Path A or B, but good enough for a fun match — and the guest can always upgrade to Path A or B later and the twin gets re-calibrated.

**When to use it:** celebrities, pros with busy schedules, or anyone who'd rather not film. The barrier to entry must be low enough that saying yes is easier than saying no.

### What we never ask for

- No face video, no voice recording, no personal data beyond golf numbers and a first name (or the name they perform under).
- No money, ever. The guest pays nothing; the show pays nothing. The exchange is the content itself.
- No exclusivity. A guest twin can play anywhere else, against anyone else, whenever they want.

---

## 3. Calibration — from submission to twin profile

Calibration is the product. A badly calibrated twin is a fake golfer; a well calibrated twin is a reason to watch. The process has four steps, and it is the same for every path — the path only changes how much of the data is measured vs. estimated.

### 3.1 The twin profile (the data object)

Every twin is a profile with the same fields as Mas's own model (see [sim-engine.md §3](sim-engine.md) for the full spec). The fields that matter:

| Field | What it is | Source |
|---|---|---|
| `handicap` | WHS index (signed, positive = better than scratch, same convention as Mas's `+3.1`) | Guest-stated, sanity-checked against video/data |
| `driving_distance` | Average total driving distance, yards | Launch monitor, or benchmark table by handicap |
| `club_speed` / `ball_speed` | Mean driver club speed / ball speed | Launch monitor, or derived from distance |
| `fairway_pct` / `gir_pct` | Fairways hit / greens in regulation, % | Stat profile, or benchmark table |
| `dispersion` | Per-club σ for face, path, and strike (the twin's "delivery distribution") | Launch monitor (measured) or benchmark table (estimated) |
| `shot_shape` | Natural shape: draw / fade / straight, and how strong | Swing video, or guest-stated |
| `mishit_profile` | Thin / chunk / toe / heel rates | Benchmark table by handicap, adjusted by video |
| `putting` | Make-rate curve by distance | Benchmark table by handicap |
| `aggression` | Decision-engine risk threshold (how often the twin takes the hero line) | Guest's answer, or 0.5 (neutral) by default |
| `strengths` / `weaknesses` | The 1–2 things the twin is genuinely good/bad at | Guest-stated, confirmed by data where possible |

### 3.2 The benchmark tables (when data is estimated)

When a field is estimated rather than measured, it comes from the handicap-benchmark tables — the same tables Mas is calibrated against, extended down the handicap scale. The principle is the same as the sim spec's §3.1: **calibrate to real golfers at that handicap, not to Tour numbers and not to the guest's best day.**

Indicative benchmarks (the sim spec is the authority; these are the anchors):

| Handicap | Driving distance | Fairways | GIR | Scoring average |
|---|---|---|---|---|
| +3 (Mas) | 265–275 yd | 55–60% | ~60% | 71–73 |
| Scratch (0) | 244–259 yd | ~50% | ~56% | 72–74 |
| 5 | ~245 yd | ~50% | ~52% | ~77 |
| 10 | ~235 yd | ~48% | ~45% | ~82 |
| 15 | ~225 yd | ~45% | ~38% | ~87 |
| 20 | ~215 yd | ~42% | ~32% | ~92 |

A guest who claims numbers far above their handicap's benchmark gets calibrated to the benchmark, not to the claim. The twin card shows the *calibrated* numbers, and the guest sees them before the match — no surprises on air.

### 3.3 Strengths and weaknesses (the personality of the model)

A twin with no strengths and no weaknesses is a grey golfer — statistically average in every category, interesting in none. Every twin gets **one strength and one weakness, stated on the twin card**, drawn from the guest's own words and confirmed by whatever data exists:

- "Long and wild" — driving distance +10 yd vs. benchmark, fairway % −8 pts.
- "Short and straight" — driving −10 yd, fairway % +8 pts.
- "Great putter" — putting make rates one handicap-band better than the rest of the profile.
- "Terrible from sand" — sand-save rate one band worse.
- "Clutch" — dispersion tightens slightly on holes 16–18 (a small, honest effect; the twin doesn't become a different golfer on the 18th).

Strengths and weaknesses are **bounded**: no single adjustment moves any stat more than one handicap band. A 15-handicapper with a great putter is still a 15-handicapper who putts well — not a 15-handicapper who putts like a pro.

### 3.4 Validation — the twin plays a test round

Before any match airs, the twin plays a **validation round** — a full 18 holes at Wyatt National, headless, no broadcast. The round is checked against the twin's stated profile:

- Scoring average within ±3 strokes of the benchmark for the handicap.
- Driving distance within ±8 yards of the calibrated number.
- Fairway and GIR percentages within ±10 points of the calibrated numbers.
- No impossible shots (no 340-yard drives from a 15-handicapper, no 50-footers holed twice in a round).

If the twin fails validation, the calibration is adjusted — never the physics. The physics is identical for every golfer; only the delivery distribution changes. That separation is what makes the model honest, and it is the same separation the sim spec enforces for Mas.

### 3.5 The twin card (what the guest sees and approves)

Before the match, the guest receives their **twin card** — a one-page summary, in the brand system (§6), showing:

- Their name, their handicap, their twin's key numbers (driving, fairways, GIR, scoring average).
- Their strength and weakness, in one line each.
- Their shot shape and usual miss.
- A line that says, in plain language: "This is how your twin plays. If this doesn't look like your game, tell us and we'll fix it."

**The guest approves the twin card before the match airs.** If they say "that's not my game," the calibration is revisited. A guest who feels misrepresented will not come back, will not share the match, and will tell their audience the twin is fake. A guest who says "yeah, that's exactly how I play" becomes an evangelist.

---

## 4. Match formats

Four formats, each with a different length, a different kind of drama, and a different clip yield. All four are played at Wyatt National, all four are fully autonomous once scheduled, and all four use the same twin — the format changes the *contest*, not the golfer.

### 4.1 18-hole match play — the flagship

**The format:** Mas vs. the guest twin, 18 holes, match play. One up, all square, dormie — the language of match play, which is the most watchable form of head-to-head golf.

**Why it's the flagship:** match play has a score that changes on every hole, a comeback is always one hole away, and a match that goes to the 18th is a full episode. It is also the format that best survives a handicap gap: a 12-handicapper's twin can beat Mas on a hole, and a match that is 2-up through 9 is a real contest even if the stroke-play gap is large.

**Handicaps:** full handicap strokes, applied on the stroke-index holes (see [course-design-v2.md](course-design-v2.md) for the stroke index). The twin gets their strokes; Mas gets none. The broadcast shows the match score, not the stroke score — "MAS 2 UP" is the story, and the stroke score is the footnote.

**Length:** a full round, premiered like a normal round premiere (Wed slot, fixed time). The match is the episode.

### 4.2 9-hole skins — the fast one

**The format:** 9 holes (the front nine, or the back nine — the guest picks), skins: win a hole outright, win the skin; tie, the skin carries to the next hole. Each skin is worth Clubhouse Coins for the audience (see §7).

**Why it works:** skins create carryovers, and carryovers create stakes that grow through the round. A skin worth three holes on the 9th is a moment. And 9 holes is half the production time of a full match, so it is the format for Tier 1–2 guests and for weeks when the schedule is full.

**Length:** 9 holes, premiered as a 30–45 minute episode or cut into the Friday best-of.

### 4.3 Closest-to-pin contests — the clip machine

**The format:** one par 3 — the 12th, "The Picture," 164 yards over the pond — one shot each, closest to the pin wins. Best of three rounds if tied. The whole contest is one hole, one shot each, three minutes of television.

**Why it works:** it is the shortest, most clip-friendly format in the system. One shot, one number, one winner. It is the format that travels best on Shorts and Reels: the hook is the result, the payoff is immediate, and the guest's audience can watch the whole contest without committing to a round.

**Length:** a single clip, 20–35 seconds, plus a 3-minute long-form cut. The cheapest guest content in the system — and the easiest yes for a busy guest.

### 4.4 Road to 59 race — the season format

**The format:** the guest twin and Mas each play a full round, separately, on the same day, at Wyatt National — and the question is not who wins the match, but **who gets closer to 59**. Two scorecards, one leaderboard, one number that matters.

**Why it works:** it plugs the guest directly into the season arc. The guest's audience doesn't need to know match-play rules or skins; they need to know one thing: can their golfer get closer to 59 than Mas? And it is the only format where a high-handicapper's twin can genuinely compete — a 15-handicapper's twin isn't going to beat Mas head-to-head, but their *best* round against Mas's *best* round is a real contest, and a 15-handicapper's twin shooting a personal best is a story.

**Length:** a full round each, premiered as a double-header or a Sunday Road to 59 update feature.

### Format picker (which format for which guest)

| Guest tier (creator-growth §4.2) | Default format | Why |
|---|---|---|
| Tier 1 — friends, local players | 9-hole skins or closest-to-pin | Low stakes, fast, fun — the guest's first taste |
| Tier 2 — small creators (5K–50K) | 18-hole match play | The full cross-channel episode; Part 1 on their channel, finale on Mas Golfs |
| Tier 3 — mid creators (100K–1M) | Road to 59 race | "Can [guest] break 59 at Wyatt National?" — the biggest premise |
| Tier 4 — pros & celebrities | 18-hole match play or Road to 59 race | The guest's name carries the episode; the format is their choice |

The guest always gets the final say on format. A guest who wants skins gets skins.

---

## 5. How the broadcast presents two golfers

Two golfers on screen changes the broadcast. The rules:

### 5.1 The split scorebug

The always-on scorebug (see [brand-identity.md §6](brand-identity.md)) becomes a **split scorebug** during guest matches:

- Top-left: the Mas Golfs mark, then `MAS` and the guest's name, each with their score to par in JetBrains Mono, separated by a gold divider.
- Match play: the match score in Archivo caps — `MAS 2 UP` / `ALL SQUARE` / `GUEST 1 UP` — with the hole number beneath.
- Stroke play / Road to 59 race: both scores to par, plus the 59-pace line for each golfer.
- The handicap pill shows **both** handicaps: Mas's `+3.1` in gold, the guest's in cream.

The 3-second rule still applies: a newcomer must understand who is playing, who is winning, and what is at stake within 3 seconds.

### 5.2 Head-to-head graphics

- **Twin card (match start):** a full-screen card for each golfer, in sequence — Mas's card first (the home golfer), then the guest's. Same layout, same fonts, same data fields. The guest's card is not a lesser version of Mas's; it is the same card with different numbers.
- **Hole comparison (between holes):** a lower-third showing both golfers' stats on the hole just played — driving distance, approach distance, putts — side by side, mono, best number in gold.
- **Tale of the tape (match start):** a single graphic with the two golfers' key numbers side by side: handicap, driving, fairways, GIR, scoring average. The classic boxing-poster format, in the brand system.
- **Live win probability (match play only):** a small mono line under the scorebug — "MAS 62% TO WIN" — derived from the match state and both twins' profiles. It updates on every hole. It is a model output, labelled as such, never presented as a fact.

### 5.3 Alternating cameras

The director (see [broadcast-stack.md §3](broadcast-stack.md)) alternates between the two golfers:

- **On the tee:** down-the-line cam on the golfer to play, then the same cam on the other golfer. The camera does not favour Mas — the guest's swing gets the same treatment, the same hold, the same tracer.
- **On the shot:** the tracer is the same Tracer gold (`#FFD34D`) for both golfers. The *lower-third* carries the name, not the tracer colour — two colours would turn the broadcast into a team sport.
- **On the green:** low green-side cam on whoever putts first; the reaction cam holds on whoever just holed out.
- **Between holes:** the aerial flyover shows the hole, then the split scorebug returns. The flyover is neutral ground — it belongs to the course, not to either golfer.

**The fairness rule:** the broadcast gives both golfers equal camera time, equal graphic quality, and equal commentary respect. The guest's audience must feel their golfer was treated like a star, because they were — and because a guest whose audience feels short-changed does not bring their audience back.

### 5.4 Commentary framing

The two-voice booth (see [broadcast-stack.md §5](broadcast-stack.md)) treats the guest twin as a real opponent:

- The host states the guest's strength and weakness early — "He's long and wild, so the 5th is a real chance and the 12th is a real problem" — so the audience knows what to watch for.
- The colour commentator calls the guest's decisions, not just Mas's. A good lay-up by the guest gets the same respect as a good lay-up by Mas.
- The booth never says "the twin" on air. On air, it is the guest's name. "The twin" is technical language for docs and dashboards; the broadcast talks about golfers.

---

## 6. Guest onboarding flow — what happens, in order

The whole flow is designed to take **under a week** from first pitch to aired match, and to ask the guest for **under 30 minutes of their time** in total.

| Step | What happens | Who does it | Guest time |
|---|---|---|---|
| 1. **Pitch** | The format pitch (see creator-growth §4.3): "Your swing as a digital twin, playing my course against my twin, Part 1 on your channel." | Mason (or the outreach agent) | — |
| 2. **Submit** | Guest sends their swing (Path A, B, or C — see §2) + their handicap + their five answers. | Guest | 10–20 min |
| 3. **Calibrate** | Twin profile built from the submission; validation round played headless; twin card produced. | The sim (autonomous) | — |
| 4. **Approve** | Guest receives the twin card and approves it — or asks for a fix. No match airs without approval. | Guest | 5 min |
| 5. **Schedule** | Match format confirmed, air date set, both channels' posting plan agreed (Part 1 / finale split, see §7). | Mason + guest | 5 min |
| 6. **Air** | The match plays autonomously; the broadcast runs the split scorebug, head-to-head graphics, and alternating cameras. | Autonomous | — |
| 7. **Deliver** | Guest receives their package (see below) within 24 hours of the match. | Autonomous + Mason | — |

### What the guest gets (the package)

Every guest, every tier, gets the same package within 24 hours:

1. **Their twin card** — the approved card, as a shareable image (1:1, brand system).
2. **Their match clip** — the best 20–35 second clip of their twin, cut and captioned, clean master (no watermark), ready to post on their own channels.
3. **Social assets** — a milestone post if they won or did something notable (tale-of-the-tape graphic, "GUEST WINS 2&1" in Archivo caps, mono data line), plus the split-scorebug still from the decisive hole.
4. **The full match** — the premiered episode, linked, with the Related Video pointer to their channel's Part 1 (for Tier 2+ cross-channel matches).
5. **Their twin, kept** — the twin profile stays in the system. The guest can come back for a rematch any time, with the same twin, and their twin's record (matches played, wins, best round at Wyatt National) is tracked in the Record Book.

The package is the reason the guest says yes *next* time, and the reason they tell other creators about it. A guest who receives a beautiful clip of their twin winning a hole will post it — and that post is the growth engine.

---

## 7. Growth logic — why a guest brings their audience

The guest-twin system is a growth engine, not a content gimmick. The logic, in order:

### 7.1 The audience follows the golfer, not the channel

A creator's audience watches *them*. When their golfer is playing — even as a twin — the audience has a reason to watch a channel they've never heard of. The guest's name on the scorebug is the distribution: it is the only form of promotion that doesn't feel like promotion, because the audience is watching their person compete, not an ad.

### 7.2 The cross-channel split (Tier 2+)

The Horvat × Bryan Bros structure (see creator-growth §4.1): **Part 1 on the guest's channel, finale on Mas Golfs.** The guest's audience watches Part 1 at home, then crosses over for the ending. Mas Golfs' audience watches the finale, then crosses to the guest's channel for the start. Both audiences move, both channels gain, and neither audience feels like they were tricked — because the split is the format, not a funnel hack.

For Tier 1 guests (friends, local players), there is no split — the match airs on Mas Golfs, and the guest shares the clip on their own social. The clip is the crossover.

### 7.3 The rematch engine

A twin that loses wants a rematch. A twin that wins wants to defend. A guest whose twin lost 2&1 on the 18th has a reason to come back — and a reason to tell their audience to come back too. The system tracks every twin's record (matches, wins, best round, head-to-head vs. Mas), and the Record Book makes rematches a standing invitation, not a new pitch.

### 7.4 The community flywheel

The Discord `#your-swing` channel (see creator-growth §5.2) is the pipeline: viewers post their own swings, the best ones become guest twins, the best-performing twin gets a featured match. Participation → content → more participation. The monthly community tournament — "Your twin vs. Mas" — is the flywheel in its purest form: the audience supplies the guests, the guests supply the audience.

### 7.5 The numbers that decide whether it works

Track these per guest, and review monthly:

- **Crossover rate:** what share of the guest's audience watched the match (measured by the guest's Part 1 views vs. the finale's views, and by new follows during the match window).
- **New followers per guest match:** the direct growth number. A Tier 2 guest should bring more than a Tier 1 guest; if it doesn't, the pitch or the format is wrong.
- **Rematch rate:** what share of guests come back for a second match. Above 50% means the experience is good; below 25% means something in the onboarding or the broadcast is failing the guest.
- **Guest satisfaction:** one question, asked after every match — "Did your twin play like you?" Yes / mostly / no. "No" is a calibration failure, and it gets fixed before the next match.

---

## 8. Rules and guardrails

- **No real money, no crypto, no betting on guest matches.** Clubhouse Coins markets run on guest matches exactly as they run on Mas's rounds — closed-loop play money, free, earned by watching, never purchasable or convertible. The guest's presence changes nothing about the coin economy.
- **No twin without approval.** A match never airs before the guest approves their twin card. No exceptions, no "we'll fix it after."
- **No likeness.** No face, no voice, no body. The twin is a skill model with a name. If a guest wants a visual representation, they get their twin card and their swing video — not a rendered version of themselves.
- **No invented results.** The twin plays the round it plays. If the guest's twin shoots 92, the broadcast says 92. If it beats Mas, the broadcast says so. The show does not protect the guest from their twin's golf, and it does not protect Mas either.
- **No guest is a prop.** The guest must be inside the golf — playing, deciding, reacting — not standing next to it (see creator-growth §4.2). A guest who only introduces the video is not a guest twin; they are a cameo, and cameos don't get a match.
- **Twins retire gracefully.** If a guest asks for their twin to be removed, it is removed — profile, record, and all — within 7 days, and the Record Book notes the retirement rather than erasing the history. The guest owns their golf; the show borrows it.
- **One twin per guest.** A guest has one twin profile, updated when they submit new data. Multiple twins for the same person would make the Record Book meaningless and the calibration untestable.
- **Handicap honesty.** A guest who sandbags (claims a higher handicap than they play to) or vanity-caps (claims a lower one) gets calibrated to their data, not their claim — and the twin card shows the calibrated number. The guest is told, plainly, before the match.

---

## 9. Build order

1. **Twin profile schema** — the data object (§3.1), matching the sim spec's golfer model. One profile, one guest.
2. **Calibration from Path C** — benchmark tables by handicap, so a twin can be built from five answers and a handicap. This unblocks every guest immediately.
3. **Calibration from Path A** — swing-video intake: handedness, tempo, shape, and the sanity check on claimed numbers.
4. **Validation round** — headless 18 holes, checked against the profile (§3.4). No twin airs without passing.
5. **Twin card + approval flow** — the one-page card, the guest's approve/fix step (§3.5).
6. **Split scorebug + head-to-head graphics** — the NodeCG graphics for two golfers (§5.1–5.2).
7. **Alternating director** — the camera rules for two golfers (§5.3).
8. **Match formats** — match play first (the flagship), then skins, then closest-to-pin, then the Road to 59 race (§4).
9. **Guest package** — the twin card image, match clip, social assets, and the kept twin (§6).
10. **Calibration from Path B** — launch-monitor intake, the most precise path, built last because it needs the fewest guests to justify it and the most engineering to do well.

---

## 10. Related docs

- [creator-growth.md](creator-growth.md) — the guest ladder (§4.2), the pitch (§4.3), the community pipeline (§5.2), and the growth numbers this system exists to move.
- [brand-identity.md](brand-identity.md) — the palette, the fonts, the scorebug and twin-card rules, and the naming conventions the guest graphics must follow.
- [sim-engine.md](sim-engine.md) — the golfer model, the dispersion and benchmark tables, and the physics every twin shares with Mas.
- [broadcast-stack.md](broadcast-stack.md) — the director, the NodeCG graphics bundle, and the commentary pipeline the two-golfer presentation plugs into.
- [course-design-v2.md](course-design-v2.md) — Wyatt National, including the stroke index used for handicap strokes in match play.
- [coins-economy.md](coins-economy.md) — the prediction markets that run on guest matches, unchanged from Mas's rounds.
