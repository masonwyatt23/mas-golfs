# Wyatt National v3 — Course Rating & Slope (recompute)

**The single number: Wyatt National v3, back tees, par 72, 7,602 yards — Course Rating 76.1, Slope 142.**

This is the one v3 number. It replaces **both** v1 pairs in the record (74.6/138 in `docs/conditions-system.md` and 74.1/141 in the web build) — see §9 for why the 74.6/138 pair is the one the method reproduces and the 74.1/141 pair is retired. Every file that states a rating or slope must use **76.1 / 142** for the Daily (base) setup; the four setup tiers are in §10.

> **Reconstruction, not certification.** This is a reconstruction of a USGA Course Rating and Slope Rating from the written design (`docs/course-design-v3.md`), using the USGA method as documented publicly. It is **not** a USGA-certified rating. Only an authorized golf association's rating team, measuring the built course hole by hole, can issue a certified rating. A certified rating would be expected to land within about ±0.3 rating / ±2 slope of this reconstruction (see §13). Until a rating team visits, 76.1 / 142 is the number the sim, the broadcast, and the conditions system use.

---

## 1. Method

The USGA Course Rating System, as documented in the USGA Rules of Handicapping (Section 13) and Appendix G:

1. **Effective playing length (EPL)** — measured yardage adjusted per hole for roll, elevation, dogleg / forced lay-up, prevailing wind, and altitude. EPL is the length the course actually plays.
2. **Yardage ratings** from the USGA formulas (men):
   - Scratch Yardage Rating = (Scratch EPL / 220) + 40.9
   - Bogey Yardage Rating = (Bogey EPL / 160) + 50.7
3. **Obstacle factors** — 10 factors (topography; fairway; green target; recoverability and rough; bunkers; crossing obstacles; lateral obstacles; trees; green surface; psychology), each rated 0–10 per hole for the scratch and bogey golfer separately, converted to obstacle stroke values.
4. **Course Rating** = Scratch Yardage Rating + Scratch Obstacle Stroke Value. **Bogey Rating** = Bogey Yardage Rating + Bogey Obstacle Stroke Value.
5. **Slope Rating** = 5.381 × (Bogey Rating − Course Rating), for men. A course of standard relative difficulty has slope 113.

**Simplification, stated plainly.** The full USGA procedure rates all 10 obstacles on all 18 holes for both golfers (360 ratings) using the USGA's proprietary rating tables. This reconstruction follows the method the v1 derivation established for this repo: the 10 obstacles are rated once per course (0–10) from the design, converted to stroke values on the same per-factor anchors the v1 derivation used, summed to a bogey-weighted total, and applied to the scratch rating at the v1 weight of 0.35 (obstacles hurt the bogey golfer roughly twice as much as the scratch golfer — that asymmetry is the whole point of slope). The yardage-rating formulas and the slope formula are the real USGA formulas, not approximations. Where this reconstruction simplifies, it says so, and §9 shows the method reproduces the v1 pair exactly when run on the v1 design — which is the evidence the method is sound.

**Sources:** USGA Rules of Handicapping, Section 13 (Course Rating) and Appendix G (The Golf Course, Course Rating and Slope Rating), usga.org; the yardage formulas and 5.381 slope constant are as published there. The 0.35 scratch weight and the per-factor stroke anchors are the v1 derivation's (`docs/conditions-system.md` §4.1), carried forward unchanged so the v3 number is comparable to the v1 number.

---

## 2. Inputs — the v3 design, per hole

From `docs/course-design-v3.md`. Elevation is tee-to-green change in feet (positive = uphill). Holes 2 and 15 are "slightly downhill" in the spec with no number — assumed −10 ft each (see §12).

| Hole | Name | Par | Yards | Elev (ft) | Dogleg / hazard | Bunkers | Green slope |
|---|---|---|---|---|---|---|---|
| 1 | The Handshake | 4 | 432 | −30 | — | 2 | 2.0% back-to-front |
| 2 | The Reach | 5 | 612 | −10* | Dogleg left 280, lake | 2 | Tilted to water |
| 3 | The Postage Stamp | 3 | 196 | +18 | — | 2 | 3.0% back-to-front |
| 4 | The Examination | 4 | 476 | +48 | — | 3 | 1.5%, three-section, spine |
| 5 | The Temptation | 4 | 392 | 0 | Centreline pot | 2 | Front-to-back |
| 6 | The Dogleg | 4 | 452 | −22 | Dogleg right 240 | 1 | 1.5% back-to-front |
| 7 | The Valley | 5 | 586 | −6 | Cross-bunker 496 | 2 | Two-tier, 2-ft step |
| 8 | The Long One | 3 | 238 | 0 | Pond, full carry | 2 | Toward water (Eden) |
| 9 | The Return | 4 | 424 | −34 | — | 2 | 2.5% back-to-front, false front |
| 10 | The Turn | 4 | 440 | −28 | Dogleg left 230 | 2 | 1.8% back-to-front, spine |
| 11 | The Monster | 5 | 624 | +60 | — | 4 | 1.3% up to back |
| 12 | The Picture | 3 | 172 | −22 | Pond, full carry | 1 | 0.8% (flattest) |
| 13 | The Grind | 4 | 482 | +52 | 28-yd fairway | 3 | 2.0% away, false front |
| 14 | The Gambler | 4 | 406 | 0 | Creek at 280 | 1 | 1.5% front-to-back |
| 15 | The Eagle Chance | 5 | 578 | −10* | — | 3 | 1.6% back-to-front |
| 16 | The Test | 3 | 214 | 0 | — | 2 | 2.5% (steepest, Redan) |
| 17 | The Penultimate | 4 | 448 | +12 | Dogleg right 250, OB | 2 | 2.0% back-to-front |
| 18 | The Closer | 4 | 430 | +34 | — | 2 | 2.0% back-to-front, false front |
| **Total** | | **72** | **7,602** | **+62 net** | **4 doglegs, water on 2/8/12/14, OB on 17** | **38** | **Avg 1.9% (14 greens with a stated %)** |

Course totals: front 3,808, back 3,794, par 72. Green slopes with a stated percentage average 1.9% (26.0 over 14 greens); the four greens without a stated percentage (2, 5, 7, 8) are tilted or tiered rather than flat. Bunker count is 38, up from ~37 in v1 (one new bunker on the 11th).

---

## 3. Step 1 — Effective playing length (scratch)

Measured yardage, then the USGA adjustments. Wind and altitude are stated as zero with reasons; every other line is a number from the design.

**Elevation, per hole.** Conversion: 1 yard per 3 feet of elevation change, applied per hole and summed (the standard conversion the v1 derivation used: its ~250 ft net → +85 yd is the same rate). Uphill adds, downhill subtracts.

| Hole | Elev (ft) | Adj (yd) | Hole | Elev (ft) | Adj (yd) |
|---|---|---|---|---|---|
| 1 | −30 | −10 | 10 | −28 | −9 |
| 2 | −10* | −3 | 11 | +60 | +20 |
| 3 | +18 | +6 | 12 | −22 | −7 |
| 4 | +48 | +16 | 13 | +52 | +17 |
| 5 | 0 | 0 | 14 | 0 | 0 |
| 6 | −22 | −7 | 15 | −10* | −3 |
| 7 | −6 | −2 | 16 | 0 | 0 |
| 8 | 0 | 0 | 17 | +12 | +4 |
| 9 | −34 | −11 | 18 | +34 | +11 |

Net elevation +62 ft; per-hole elevation adjustment **+22 yd**. (Netting first and then converting gives +21 yd; the per-hole table is the auditable figure and the one used. The 1-yard difference is rounding.)

Note: the sim's `elev_green_ft` values in `course-design-v3.md` §5.1 (e.g. 1st −10, 4th +34, 11th +34) are a different, simplified quantity — the green's elevation in the sim's linear model — not the tee-to-green elevation change used here. The rating uses the prose tee-to-green numbers above.

**The full EPL build:**

| Adjustment | Yards | Why |
|---|---|---|
| Measured yardage | 7,602 | v3 spec, verified front 3,808 + back 3,794 |
| Roll (firmness normal, 0.60) | −120 | Firm fairways roll ~27 yd vs the 20-yd standard — about 7 yd/hole × 18. Same figure as the v1 derivation; the turf and firmness are unchanged in v3 |
| Elevation (per-hole table above) | +22 | Net +62 ft, climbs longer and steeper than v1 (+85 yd) but the downhill holes grew too, so the net adjustment falls |
| Forced carries (water) | +40 | Holes 2, 8, 12 require carries a scratch golfer must make. Same three carries as v1, unchanged |
| Dogleg adjustment | +30 | Doglegs at 2, 6, 10, 17 force lay-ups off the direct line. Same four doglegs as v1, unchanged |
| Prevailing wind | 0 | Wind rotation balances: helping on 1, 5, 9, 15, 18; into on 4, 8, 11, 13; across on 6, 10, 16, 17. Net zero, as in v1 |
| Altitude (1,400 ft) | 0 | The USGA adjusts the yardage rating downward only at or above 2,000 ft. Wyatt National is at ~1,400 ft (sim-engine.md §1.2), below the threshold. The sim's air-density factor (ρ × 0.955) is a ball-flight physics constant, not a rating input |
| **Scratch effective playing length** | **7,574** | |

v1 for comparison: 7,214 − 120 + 85 + 40 + 30 = 7,249. The v3 EPL grows by **+325 yards** — the +388 measured yards minus the 64-yard fall in the elevation adjustment (the v3 course climbs more in total, but it also descends more; the net is smaller than v1's).

---

## 4. Step 2 — Scratch yardage rating

The USGA formula (men):

```
Scratch Yardage Rating = (Scratch EPL / 220) + 40.9
                       = (7,574 / 220) + 40.9
                       = 34.43 + 40.9
                       = 75.3
```

---

## 5. Step 3 — Obstacle factors

The 10 USGA factors, rated 0–10 from the v3 design, converted to strokes on the same per-factor anchors the v1 derivation used (the anchors are the USGA table values as the v1 derivation recorded them: e.g. topography 6 → 0.35, green target 6 → 0.30, bunkers 6 → 0.25). The strokes below are **bogey weights** — the full cost of each obstacle to a ~20-handicap golfer.

| Obstacle factor | v1 rating | v3 rating | Strokes (v3) | Why (v3 design) |
|---|---|---|---|---|
| Topography | 6 | **7** | +0.40 | Climbs longer and steeper (4th 48 ft, 11th 60 ft, 13th 52 ft); no fairway is flat side-to-side anymore — every fairway cambers. The ground is the defence in v3 |
| Fairway width / landing | 5 | **5** | +0.25 | Widths 28–44 yd, average ~35, same as v1. The 13th narrows to 28 (26 at the bunkers) but the rounded edges and semi-rough gradient forgive a small miss — a wash |
| Green target | 6 | **7** | +0.35 | Greens smaller and more severe: 3rd at 3% with a thumbprint, 5th sloping front-to-back (reverse), 13th sloping away at 2% with a false front, 16th Redan at 2.5% with a 14-inch step, 9th false front. The v2 minimum of 1.3% is now a floor |
| Recoverability / rough | 5 | **5** | +0.20 | Thick rough on 4, 10, 13 as in v1; the 6–8 yd semi-rough band makes a near-miss easier, the deep rough is unchanged — a wash |
| Bunkering | 6 | **7** | +0.30 | 38 bunkers (one new, on the 11th); cross-bunker moved to 496 on the 7th; greenside bunkers moved outward with the greens, so longer approaches must carry them; revetted pots on 5 and 17; three-deep front complex on 15; 8-ft-deep bunker on 16 |
| Water / out of bounds | 5 | **5** | +0.20 | Same hazards as v1: water on 2 (lake), 8 (pond), 12 (pond), 14 (creek); OB on 17. Unchanged in kind |
| Trees | 4 | **4** | +0.10 | Pines frame the fairways; the punch-out is a real shot on 6 and 17; 12th framed by pines. Unchanged |
| Green surface | 6 | **7** | +0.35 | Same 11.0 stimp baseline, but slopes are steeper (up to 3.0% on the 3rd, 2.5% on the 16th and 9th, 2.0% away-slope on the 13th) and more greens are tiered (4th three sections, 7th two-tier with a 2-ft step, 10th spine, 16th two tiers) |
| Psychological | 4 | **4** | +0.10 | Water carries (2, 8, 12), the Road Hole wall (17), the one blind tee shot (17), the deceptive looks on 4 and 11. Same hazards in kind as v1 |
| **Total obstacle strokes (bogey weights)** | | | **+2.25** | v1 total was +2.05; the v3 increase (+0.20) is topography, green target, bunkering, and green surface, one step each |

---

## 6. Step 4 — Course Rating

The USGA system applies the obstacle strokes at a reduced weight for the scratch golfer (the v1 weight, 0.35):

```
Course Rating = Scratch Yardage Rating + (Obstacle total × 0.35)
              = 75.33 + (2.25 × 0.35)
              = 75.33 + 0.79
              = 76.1
```

**Wyatt National v3 Course Rating: 76.1.**

---

## 7. Step 5 — Bogey rating

The bogey golfer (index ~20, drives ~200 yd) faces the same course, but the effective length is longer for them: they cannot cut the dogleg corners (2nd over the lake, 6th, 10th, 17th) and must lay up before forced carries. The v1 derivation's distance penalty implies a bogey EPL of scratch EPL + 342 yd. For v3 the corners are in the same places, so the same gap applies, plus ~8 yd for the lengthened par-3 carries (8th now 238, 12th now 172):

```
Bogey EPL = 7,574 + 350 = 7,924 yd

Bogey Yardage Rating = (Bogey EPL / 160) + 50.7
                     = (7,924 / 160) + 50.7
                     = 49.53 + 50.7
                     = 100.2

Bogey Rating = Bogey Yardage Rating + Obstacle total (full weight)
             = 100.23 + 2.25
             = 102.5
```

**Sensitivity (the one soft assumption, and it does not move the headline):**

| Bogey EPL gap (Δ_b) | Bogey rating | Slope |
|---|---|---|
| +342 yd (v1 gap, unchanged) | 102.4 | 142 |
| **+350 yd (central case)** | **102.5** | **142** |
| +360 yd | 102.5 | 142 |

The slope rounds to 142 across the whole plausible range of the bogey-length gap, and the course rating does not depend on it at all.

---

## 8. Step 6 — Slope Rating

```
Slope = 5.381 × (Bogey Rating − Course Rating)
      = 5.381 × (102.48 − 76.11)
      = 5.381 × 26.36
      = 142
```

**Wyatt National v3 Slope Rating: 142.**

---

## 9. Verification — why this number, and what happens to the two v1 pairs

**The method reproduces the v1 pair.** Run the identical method on the v1 design (7,214 measured; roll −120; elevation +85; carries +40; dogleg +30; EPL 7,249; obstacles 2.05):

```
Scratch yardage = 7,249/220 + 40.9 = 73.85
Course rating   = 73.85 + 2.05 × 0.35 = 74.57 → 74.6
Bogey yardage   = (7,249 + 342)/160 + 50.7 = 98.14
Bogey rating    = 98.14 + 2.05 = 100.19 → 100.2
Slope           = 5.381 × (100.19 − 74.57) = 137.9 → 138
```

74.6 / 138 — exactly the pair `docs/conditions-system.md` §4.1 derives. The method is validated against the record it was built from.

**The 74.1/141 pair cannot be reproduced — it is retired.** The web build's pair implies a bogey rating of 74.1 + 141/5.381 = **100.3**, which matches the v1 bogey rating (100.2) to rounding. The disagreement is therefore entirely in the scratch rating: 74.1 is 0.5 strokes below what the documented derivation supports (74.6). No combination of the documented adjustments produces 74.1 from the v1 design. The 74.1/141 pair is the one that gets dropped; the 74.6/138 pair is the one the method reproduces. From here on, only 76.1/142 exists.

**Cross-check: the +3 scoring band.** A +3 golfer's expected score on a course is approximately its rating minus 3. v3: 76.1 − 3 = **73.1**, dead in the middle of the v3 scoring band the spec expects (72–74, mean ~73.0–73.5). v1: 74.6 − 3 = 71.6, in the middle of the v1 band (71–73, mean ~72). The rating and the sim's scoring expectations agree with each other — two independent routes to the same number.

**Cross-check: the spec's expected delta.** `course-design-v3.md` §5.1 expected the rating to rise "roughly 0.8–1.2 strokes" and the slope "roughly 4–7 points." Actual: rating **+1.5** (74.6 → 76.1), slope **+4** (138 → 142). The slope is inside the expected range; the rating is 0.3–0.7 above the rough estimate. The reason is arithmetic, not judgement: the +325 yards of effective length alone is +1.47 strokes at the USGA formula's 1/220 per yard, and the obstacles add +0.07. The estimate underweighted length. The recompute supersedes the estimate — the estimate was a guess made before the derivation was run, and this document is the derivation.

**Cross-check: real-course band.** A 7,600-yard par-72 championship course with severe greens and real hazards should rate in the mid-70s with a slope in the high 130s to mid-140s. 76.1/142 sits in that band. (For scale: slope 113 is standard difficulty; 142 is a hard championship test, which is what Wyatt National is.)

**Uncertainty.** The headline is robust: ±0.2 rating / ±1 slope. The largest sensitivities are the roll assumption (each 1 yd/hole of roll = 0.08 rating) and the elevation conversion (even at 1 yd per 2 ft instead of 1 yd per 3 ft, the rating moves by +0.05). The obstacle ratings are the most judgemental input, but moving any single factor by one step moves the rating by 0.02 and the slope by ~0.3 — the total is stable.

---

## 10. Setup tiers — the four ratings

The conditions system (`docs/conditions-system.md` §4.3) runs four setups. The tier spreads are the v1 doc's (+0.8 rating per step up, −0.8 for Soft; slope +3 / +7 / −4), because the setup levers are unchanged — the same firmness, stimp, wind, pin, rough, and fairway changes. What changes is the base they sit on: 76.1/142 instead of 74.6/138.

| Setup tier | Rating | Slope | Implied bogey rating | What changes (from conditions-system.md §4.3) |
|---|---|---|---|---|
| **Daily** (base) | **76.1** | **142** | 102.5 | Normal firmness (0.45–0.70), normal stimp (10.5–11.5), wind 0–10, pins mid-difficulty, rough standard |
| **Championship** | **76.9** | **145** | 103.9 | Firm (0.70–0.80), fast stimp (11.5–12.5), wind 8–15, pins tucked (difficulty ≥ 0.7 on 6+ holes), rough +0.5 inch |
| **Major week** | **77.7** | **149** | 105.4 | Firm (0.80–0.90), tournament stimp (12.5–13.0), wind 10–18, pins tucked (difficulty ≥ 0.8 on 8+ holes), rough +1 inch, fairways narrowed to 26 yd, one extra fairway bunker at 300 yd on every par 4/5 (v3 tournament setup, course-design-v3.md §5.2) |
| **Soft / scoring** | **75.3** | **138** | 101.0 | Soft (0.25–0.45), slow stimp (9.5–10.5), wind 0–5, pins accessible (difficulty ≤ 0.5), rough standard |

How the levers move the rating (v1 doc's lever table, unchanged — rating deltas are scratch deltas):

| Lever | Daily → Championship | Championship → Major week |
|---|---|---|
| Firmness (bounce/roll) | +0.2 | +0.2 |
| Green speed | +0.2 | +0.2 |
| Wind | +0.2 | +0.2 |
| Tucked pins (pin difficulty) | +0.1 | +0.1 |
| Longer rough (lie penalties) | +0.1 | +0.1 |
| Narrowed fairways | — | +0.1 |
| **Total** | **+0.8** | **+0.9** |

Note: the Championship → Major lever column sums to +0.9, but the tier spread is +0.8 — the 0.1 is rounding in the individual lever estimates (±0.05 each). The tier values in the table above are the rounded totals and are the numbers to use.

Why the slope rises faster than the rating: each setup hurts the bogey golfer more than the scratch golfer. Championship: bogey rating rises 1.36 vs scratch 0.80 (1.7×). Major week: bogey rises 2.90 vs scratch 1.60 (1.8×). Soft: bogey falls 1.54 vs scratch 0.80 (1.9×). That asymmetry is the slope system working as designed — and it is why a 71 in major week is worth more than a 71 on a calm day (the differential is computed against the setup's rating, sim-engine.md §7.1).

---

## 11. Rating by tee

| Tees | Yardage | Rating | Slope |
|---|---|---|---|
| Back (championship) | 7,602 | **76.1** | **142** |
| Middle | 6,780 | 72.4 | 132 |
| Forward | 6,350 | 70.1 | 126 |

The middle and forward numbers are carried from the v1 derivation, flagged: the v3 lengthening is back-tee-only (new back tees set into the existing land), so the forward-tee yardages are unchanged. The obstacle changes (greens, bunkers) would add roughly +0.1 rating / +1 slope to every tee, which is below the rounding of these figures — they are carried as-is and must be re-derived if the forward tees are ever rebuilt or moved. The broadcast uses the back-tee numbers unless a special event says otherwise.

---

## 12. Assumptions — every number this derivation had to supply

| # | Assumption | Value used | Effect if wrong |
|---|---|---|---|
| A1 | Elevation conversion | 1 yard per 3 ft, per hole, summed | Each 3 ft of net elevation = 1 yd EPL = 0.005 rating. Even at 1 yd/2 ft the rating moves +0.05 |
| A2 | Holes 2 and 15 elevation | −10 ft each ("slightly downhill", no number in the spec) | ±10 ft on either hole = ±3 yd EPL = ±0.01 rating. Immaterial |
| A3 | Roll at normal firmness (0.60) | −120 yd (avg roll ~27 yd vs 20 standard) | The largest sensitivity: each 1 yd/hole of roll = 18 yd EPL = 0.08 rating |
| A4 | Dogleg adjustment | +30 yd (four doglegs) | Carried from v1; corners unchanged in v3 |
| A5 | Forced carries | +40 yd (holes 2, 8, 12) | Carried from v1; same three carries |
| A6 | Prevailing wind | 0 (rotation balances) | A net wind adjustment would move EPL by the wind table; the rotation is designed to balance |
| A7 | Altitude | 0 (1,400 ft < 2,000 ft USGA threshold) | No USGA adjustment below 2,000 ft. The sim's ρ × 0.955 is ball-flight physics, not a rating input |
| A8 | Bogey EPL gap (Δ_b) | +350 yd over scratch EPL | Slope is 142 for Δ_b anywhere in 342–360; rating unaffected |
| A9 | Obstacle stroke anchors | v1 per-factor conversions (e.g. topography 6 → 0.35) | Moving any single factor one step moves the rating 0.02, slope ~0.3 |
| A10 | Scratch obstacle weight | 0.35 (v1 derivation) | The full USGA procedure rates obstacles per hole for both golfers; the 0.35 weight is the v1 simplification, carried for comparability |
| A11 | Green speeds | 11.0 stimp baseline (conditions-system.md §3) | A measured daily stimp of 12+ would raise the green-surface rating a step; rating +0.02, slope +0.3 — immaterial to the base, material to the tiers |
| A12 | Fairway widths | Landing-area widths from the spec (28–44 yd) | The fairway factor is a width rating; the rounded edges are handled in recoverability, not here |

---

## 13. What would change this number

- **A formal USGA rating visit.** A certified team measures each hole's EPL factors and rates all 10 obstacles per hole for both golfers. Expected movement from this reconstruction: ±0.3 rating / ±2 slope. That is the honest error band on 76.1/142, and it is the only thing that could replace it with a certified number.
- **Measured green speeds.** If the daily stimp measures 12.0+ rather than the assumed 11.0 baseline, the green-surface factor rises a step — rating +0.02, slope +0.3. Small for the base rating; the setup tiers move more (their stimp bands are the lever).
- **Tee moves.** Every 22 yards of measured length is 0.1 rating. New back tees, or a tournament tee, re-open the derivation.
- **Rough height / fairway width changes.** A mowing change that moves the recoverability or fairway factor a step moves the rating ~0.02 and the slope ~0.3 per step.
- **Bunker additions or removals.** One bunker is below the resolution of the bunkering factor; a program of changes (e.g. five new bunkers) would move it a step.
- **Pin and setup changes do not change the base rating.** They change the setup tiers (§10), which is exactly what the tiers are for.

---

## 14. Where the old numbers live — update these (follow-up, not done here)

This document is the recompute only. The following places still carry the old pairs and must be updated to **76.1 / 142** (Daily base) and the tier table in §10, in a follow-up pass:

- `docs/conditions-system.md` §4.1 — replace the v1 derivation with a pointer to this document; §4.3 tiers become Daily 76.1/142, Championship 76.9/145, Major week 77.7/149, Soft 75.3/138; §4.2 back-tee row becomes 76.1/142; the "v3 recompute pending" flags close.
- `docs/sim-engine.md` §1.2 — the `rating` / `slope` fields in the course object (74.6/138 → 76.1/142), and any worked differential example that uses them.
- `sim/course.py` — `compute_rating_slope()` must return 76.1/142 (it currently returns the v1 pair; the function itself does not need rewriting, its constants do).
- The web build (`autonomous-golf-world` artifact) — the rating/slope display showing 74.1/141, and any setup-tier display using the v1 tier numbers.
- `docs/qa-plan.md` §1 — the calibration table's rating reference, if it states one.
- `docs/self-improvement.md` — the baseline course rating it states for the improvement ladder.
- `docs/analytics.md` — any alert band stated against the old rating.
- `README.md` — if it states a rating/slope anywhere.

Until those updates land, this document is the single source of truth for the v3 rating and slope.

---

## Sources

- USGA Rules of Handicapping, Section 13 (Course Rating) and Appendix G (The Golf Course, Course Rating and Slope Rating), usga.org — effective playing length factors (roll, elevation, dogleg/forced lay-up, prevailing wind, altitude ≥ 2,000 ft), the 10 obstacle factors, the yardage-rating formulas (Scratch EPL/220 + 40.9; Bogey EPL/160 + 50.7), and the slope formula (5.381 × difference, men).
- `docs/course-design-v3.md` — the design this derivation is computed from (7,602 yards, per-hole yardages, elevations, green slopes, bunker counts).
- `docs/conditions-system.md` §4.1 — the v1 derivation this recompute follows (method, per-factor stroke anchors, 0.35 scratch weight, tier spreads, lever table).
- `docs/sim-engine.md` §1.2 — Wyatt National at ~1,400 ft (altitude input); §7.1 — differentials computed against the setup's rating.
- Verification arithmetic: per-hole elevation table, EPL build, yardage ratings, obstacle total, bogey sensitivity (Δ_b 342/350/360), and the v1 back-check were all computed in a script and the results transcribed above; the script is not part of the repo (no code changes in this task).
