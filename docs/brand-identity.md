# Mas Golfs — Brand Identity System

**The show:** Mas Golfs — the Mason W Golf endless round. A left-handed +3 digital-twin golfer named Mas plays 18-hole rounds on repeat at Wyatt National, forever, on livestream. The season arc is **Road to 59**: the chase for a sub-60 round.

Everything in this document is free to implement: free fonts, hex values (no licensed assets), rules an agent or a human can follow without a designer on call.

---

## 1. Brand story

Mas is Mason's digital twin — a real +3 handicapper, a real left-handed swing, a real person behind the pixels — playing golf forever on a course that never closes. He is not a character invented for content; he is a golfer, learning in public, chasing the most meaningful number in golf: 59. The show is the loop, the learning, and the chase. Viewers don't watch because the golf is perfect. They watch because it's real, because it's always on, and because one day — maybe today, maybe in three weeks — Mas breaks 60, and everyone who was there gets to say they saw it happen live.

## 2. Brand voice

**Calm, knowledgeable, understated — CBS/NBC golf cadence, never hype.** The broadcast talks like a golf broadcast: short sentences, space between them, the decision stated before the shot, the result allowed to speak for itself. On social, the same voice, tightened: one line that makes the moment, never a paragraph that explains it. We never shout, never beg for follows, never manufacture drama — the golf supplies the drama. We never claim a result we haven't earned, never name a client, never promise a timeline we can't keep. When Mas misses, we say so plainly and move on; when he learns, we show the work.

---

## 3. Logo concept

### Wordmark

**MAS GOLFS** — set in the display face (see §5), all caps, tight tracking, with the "59" as a silent partner: the wordmark is often followed by a small gold "59" in the mono face, or by the season line *ROAD TO 59* underneath in small caps. The wordmark must read at broadcast-bug size (as small as ~24 px tall on a 1080p frame), so it is never set below 11 px in print terms and never relies on thin strokes.

### The mark

A simple geometric mark that works as a social avatar, a broadcast bug, and a watermark:

- **The concept:** a left-handed swing arc. A single gold arc (the club path) sweeping up and over a dark-green circle (the ball), with a small horizontal tick where the arc meets the ball — impact. The arc is open at the top, suggesting a finish held high.
- **Why it works:** it reads at 32×32 px, it is drawable in two colors, it says "golf" without a flagstick cliché, and the leftward sweep is a quiet nod to Mas being a lefty.
- **Construction:** circle diameter = 1 unit; arc radius = 1.4 units, centered on the ball, sweeping from 7 o'clock to 1 o'clock; stroke weight = 0.14 units; the impact tick is a 0.3-unit horizontal bar at the ball's equator. Clear space around the mark = one ball-diameter on all sides.
- **Variants:** full-color (gold arc on dark green), reversed (cream arc on dark green), mono (single-color, any brand color), and bug (mark alone, no wordmark, for the broadcast corner).

### Lockups

1. **Primary:** mark left, MAS GOLFS wordmark right, ROAD TO 59 beneath in small caps.
2. **Broadcast bug:** mark alone, top-left of frame, with the live scorebug beside it.
3. **Social avatar:** mark alone, centered, on dark green, with a 4 px gold ring.
4. **End card:** mark large, MAS GOLFS beneath, then the season line.

Never stretch, recolor outside the palette, add drop shadows, or place the mark on a busy photograph without a dark-green scrim behind it.

---

## 4. Color palette

Broadcast-safe, works on dark green/gold, legible on video at small sizes. All colors are flat — no gradients in the core identity (gradients are for the 3D world, not the brand).

| Name | Hex | Role |
|------|-----|------|
| **Fairway** | `#0B3D2E` | Primary dark green. Backgrounds, broadcast bug, avatar field, end cards. |
| **Deep Rough** | `#062A1F` | Darker green. Panels, lower-third backs, footer. |
| **Gold** | `#C9A227` | Accent. The mark, key numbers, live indicators, "59". Used sparingly — gold is the highlight, never the field. |
| **Cream** | `#F5F1E6` | Primary text on dark. Scorebug text, headlines, captions. |
| **Mist** | `#9DB8A6` | Secondary text on dark. Labels, metadata, timestamps. |
| **Sky** | `#7FB3D5` | Functional only. Water, weather, and the tracer's cool end. Never for text. |
| **Tracer** | `#FFD34D` | The shot tracer line and its glow. Bright gold, distinct from brand Gold so it reads over any terrain. |
| **Alert** | `#E4572E` | Functional only. Bogey-or-worse moments, warnings. Never decorative. |

**Contrast rules:** Cream on Fairway is the default text pairing (contrast ≈ 11:1). Gold on Fairway is for numbers and accents only, never body text. Mist on Fairway is for secondary text only, minimum 14 px. Never set Cream text on Gold, and never set Gold text on Cream.

---

## 5. Typography — free fonts only

All fonts are free (Google Fonts, OFL license). No paid typefaces anywhere in the project.

| Role | Font | Use |
|------|------|-----|
| **Display** | **Archivo** (Black / ExtraBold, all caps, tight tracking) | MAS GOLFS wordmark, headlines, big numbers (score, handicap, "59"), lower-third names. |
| **Text** | **Inter** (Regular / Medium / SemiBold) | Commentary captions, body copy, social captions, UI text, docs. |
| **Mono (data)** | **JetBrains Mono** (Regular / Bold) | All data: yardages, ball speed, spin, carry, scores, leaderboard tables, handicap, timestamps. Numbers must align — never set data in a proportional face. |

**Type rules:** headlines in all caps, never letterspaced beyond +0.02 em. Body copy in sentence case. Data always in JetBrains Mono with tabular figures. Minimum sizes on broadcast: scorebug text 20 px, lower-third body 18 px, ticker 16 px (at 1080p). Never use more than two weights of one family in a single graphic.

---

## 6. On-screen identity rules

### Scorebug (always on)

Top-left of frame: the Mas Golfs mark (bug variant) + `MAS · THRU n` in Archivo, then the score to par in JetBrains Mono, then the live handicap pill (`+3.1`) in gold. Beneath it, the season line in small caps: `ROAD TO 59 · BEST 63`. The bug must tell a newcomer the whole story in 3 seconds: who, where in the round, how he's doing, what he's chasing.

### Lower-thirds

Dark-green panel (Deep Rough, 92% opacity), gold left rule (4 px), name in Archivo caps, data in JetBrains Mono. Three variants: **shot data** (club, ball speed, launch, spin, apex, carry, shape), **player card** (Mas, +3, last-10 average, handicap trend), **milestone** (record chase, streak, season stat). Lower-thirds slide in on shot events and out after 6 seconds — never lingering.

### Player card

Shown between holes and on the aerial flyover: mark, MAS GOLFS, "Mason's digital twin — left-handed +3", then three lines of mono data: scoring average, last-10 aggregate, handicap with trend arrow. One line of voice: the one fix he's working on this round.

### End card

Full-screen Fairway field, mark large, MAS GOLFS beneath, then `ROAD TO 59` and the final score in mono. Below: "Follow Mas Golfs — Mason W Golf on Instagram." End cards appear at the end of every round and every premiered episode, never mid-round.

### Ticker

Bottom of frame, Mist text on Deep Rough: rolling season facts — last-10 average, course record, today's score, next milestone. Updates on events, never scrolling faster than a viewer can read.

---

## 7. Social templates

All templates are 9:16 vertical for clips (1080×1920) and 1:1 or 4:5 for feed posts. Built from the same three elements every time: Fairway field, mark, Archivo headline, mono data line.

### Clip cover (9:16)

- Full-bleed still from the moment (tracer mid-flight or the held finish).
- Dark-green scrim, bottom third.
- Headline in Archivo caps, cream, max 6 words: "HE DID IT." / "THE KNOCKDOWN WORKED." / "DAY 14. STILL CHASING 59."
- Mono data line beneath: `7-IRON · 184 YDS · 4 FT` or `ROUND 23 · 67 · -5`.
- Mark, top-left, small. No other text on the cover.

### Milestone post (1:1)

- Fairway field, mark centered large.
- Archivo headline: "NEW COURSE RECORD" / "BACK-TO-BACK 67s" / "HANDICAP: +3.4".
- Mono data line with the numbers and the date.
- One line of voice beneath, Inter, Mist: what it means, in one sentence.
- Footer: "Mas Golfs — Mason W Golf on Instagram."

### Leaderboard post (4:5)

- Deep Rough panel, gold header rule.
- Title in Archivo: "ROAD TO 59 — LAST 10".
- Table in JetBrains Mono: round number, date, score, to par. Best round in gold.
- Footer line: all-time average and handicap with trend arrow.
- Mark top-left. No photography — the numbers are the image.

### Caption rules (all posts)

- One line that makes the moment, then the data, then the call to watch. Never more than three lines before the fold. Always end with the stream: "Live now — link in bio." Hashtags, max five, always including #MasGolfs and #RoadTo59.

---

## 8. Naming conventions

### Series

- **Mas Golfs** — the show itself. Always two words, always title case.
- **Road to 59** — the season arc. Always "Road to 59", never "Road to 60" or "Chasing 59".
- **The Endless Round** — the always-on loop, used only when describing the format, never as the show title.

### Episodes and days

- **Rounds:** `Round 23 — 67 (-5) · Wyatt National`. Round number, score, to par, course. Always in that order.
- **Daily series:** `Day 14 of Road to 59`. Day count is consecutive days of the season, not days since launch.
- **Premiered episodes:** `Mas Golfs — Round 23: The One Where He Nearly Did It` (only when a round earns a title; most rounds stay untitled).
- **Clips:** named by the moment, not the hole: `The Knockdown`, `The Punch-Out`, `Four Feet for 59`. Hole numbers go in the data line, never the title.

### The golfer

- **Mas** — always, on screen and in copy. "Mason" appears only in the "Mason's digital twin" line and in Instagram bio context. Never "Mason Wyatt" on the broadcast.
- **The Brain** — the on-device decision engine, named only in technical docs and deep-dive content, never on the broadcast.

---

## 9. Do / Don't

**Do:**
- Lead with the number: 59, the score, the handicap, the streak.
- Let the golf supply the drama; the brand stays calm.
- Keep gold scarce — when everything is gold, nothing is.
- Set all data in mono, always.
- Say "Mas is Mason's digital twin" somewhere visible, always.
- Make every graphic readable in 3 seconds at broadcast size.

**Don't:**
- Don't shout, hype, or beg for follows.
- Don't use more than the palette above — no extra colors, no gradients in brand graphics.
- Don't put the mark on a busy photo without a scrim.
- Don't set body text in the display face or data in a proportional face.
- Don't promise dates, scores, or milestones that haven't happened.
- Don't use real-money or crypto language anywhere near Clubhouse Coins.
- Don't rename the show, the season, or the golfer — MAS GOLFS, Road to 59, Mas. That's the brand.
