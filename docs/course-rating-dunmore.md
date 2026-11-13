# Dunmore Links — Course Rating & Slope (recompute)

**The single number: Dunmore Links, back tees, par 72, 7,195 yards — Course Rating 73.8, Slope 137.**

This is the one Dunmore number. It is the USGA-method recompute for the second course, done exactly the way `docs/course-rating-v3.md` did Wyatt National v3 (76.1/142) — same formulas, same per-factor stroke anchors, same 0.35 scratch obstacle weight, same honesty standards. The sim's `compute_rating_slope()` currently returns **74.6/141** for Dunmore; that number is superseded by this recompute (see §9 for why, and whether the sim function needs recalibration). Until a rating team visits, 73.8/137 is the number the sim, the broadcast, and the conditions system should use for Dunmore.

> **Reconstruction, not certification.** This is a reconstruction of a USGA Course Rating and Slope Rating from the written design (`docs/course-two.md`) and its implementation (`sim/course.py` `build_dunmore_links()`), using the USGA method as documented publicly. It is **not** a USGA-certified rating. Only an authorized golf association's rating team, measuring the built course hole by hole, can issue a certified rating. A certified rating would be expected to land within about ±0.3 rating / ±2 slope of this reconstruction (see §12). Until a rating team visits, 73.8/137 is the number.

---

## 1. Method

The USGA Course Rating System, as documented in the USGA Rules of Handicapping (Section 13) and Appendix G — identical to the Wyatt recompute (`docs/course-rating-v3.md` §1), which this document follows step for step:

1. **Effective playing length (EPL)** — measured yardage adjusted per hole for roll, elevation, dogleg / forced lay-up, prevailing wind, and altitude.
2. **Yardage ratings** from the USGA formulas (men):
   - Scratch Yardage Rating = (Scratch EPL / 220) + 40.9
   - Bogey Yardage Rating = (Bogey EPL / 160) + 50.7
3. **Obstacle factors** — the 10 USGA factors, rated 0–10 from the design, converted to obstacle stroke values on the same per-factor anchors the Wyatt derivation used (the v1 derivation's anchors, carried forward unchanged so the two courses' numbers are comparable).
4. **Course Rating** = Scratch Yardage Rating + (Obstacle total × 0.35). **Bogey Rating** = Bogey Yardage Rating + Obstacle total (full weight).
5. **Slope Rating** = 5.381 × (Bogey Rating − Course Rating), for men. Standard relative difficulty is slope 113.

**Simplification, stated plainly.** As in the Wyatt recompute, the 10 obstacles are rated once per course (0–10) from the design rather than per hole for both golfers (360 ratings) using the USGA's proprietary tables. The yardage-rating formulas and the slope formula are the real USGA formulas, not approximations. The Wyatt recompute validated this simplified method by reproducing the v1 pair (74.6/138) exactly when run on the v1 design; this document applies the identical method to Dunmore, so the two courses' ratings are directly comparable.

**Sources:** USGA Rules of Handicapping, Section 13 (Course Rating) and Appendix G, usga.org; `docs/course-rating-v3.md` §1 (method, anchors, 0.35 weight); `docs/course-two.md` (the design); `sim/course.py` `build_dunmore_links()` (the implemented hole data, which matches the doc — see §2).

---

## 2. Inputs — the Dunmore design, per hole

From `docs/course-two.md`, cross-checked against `sim/course.py` `build_dunmore_links()` — the two agree on every yardage, par, name, and bunker count (115 total). Elevation is tee-to-green change in feet (positive = uphill), from the sim's values, which are the doc's prose numbers (see §11, A2).

| Hole | Name | Par | Yards | Elev (ft) | Dogleg / hazard | Bunkers | Green |
|---|---|---|---|---|---|---|---|
| 1 | The First Light | 4 | 398 | 0 | Double green (shared with 18) | 6 | 1.5% toward fairway, collection hollow |
| 2 | The Burn | 5 | 562 | −6 | Dogleg right 280, burn ×2 (170, 300) | 7 | Large, 34 yd wide, tilted toward burn |
| 3 | The Biarritz | 3 | 178 | 0 | — | 4 | Biarritz, 60 yd deep, swale, two plateaus |
| 4 | The Gauntlet | 4 | 445 | +25 | Into the wind | 7 | 1.3% toward fairway, three sections, spine |
| 5 | The Nose | 4 | 372 | 0 | Principal's Nose at 280 | 8 | Small (5,100 sq ft), sloping toward fairway |
| 6 | The Gales | 5 | 585 | 0 | Sahara shoulder (blind 2nd) | 9 | 1.3% toward fairway, heavily defended |
| 7 | The Hollow | 3 | 214 | 0 | Dune hollow | 4 | Wide/shallow, slopes toward hollow |
| 8 | The Shore | 4 | 431 | −15 | Dogleg left 280, sea OB right | 7 | Angled 30°, open left, deep pot right |
| 9 | The Return | 4 | 406 | −20 | — | 6 | 2% toward fairway, false front |
| 10 | The Dunes | 4 | 424 | −25 | Dogleg left 260, sea OB right | 7 | Long/narrow, spine, tilted toward fairway |
| 11 | The Second Wind | 5 | 578 | +40 | Into the wind | 9 | Large, narrow entrance |
| 12 | The Punchbowl | 3 | 165 | −20 | — | 4 | Punchbowl, flattest on the course |
| 13 | The Anvil | 4 | 452 | +35 | Narrow (30 yd) | 7 | 2% away, false front, two-tier (most severe) |
| 14 | The Dare | 4 | 384 | 0 | Burn at 280 | 5 | Small, firm, sloping toward fairway |
| 15 | The Downwinder | 5 | 548 | −8 | — | 8 | Large, 36 yd wide, back-left bowl |
| 16 | The Plateau | 3 | 196 | 0 | — | 5 | Double Plateau, 3-ft step |
| 17 | The Alps | 4 | 439 | −10* | Blind over 45-ft dune, sea OB right | 6 | Narrow (20 yd), deep pot front-left |
| 18 | The Homecoming | 4 | 418 | +20 | Sea OB right, double green | 6 | 2% toward fairway, false front, back tier |
| **Total** | | **72** | **7,195** | **+16 net** | **3 doglegs, burn on 2/14, sea OB on 8/10/17/18** | **115** | **Avg ~1.5% (greens slope toward the fairway)** |

Course totals: front 3,591, back 3,604, par 72. Green slopes are gentler than Wyatt's (average ~1.5% vs Wyatt's 1.9%) and, crucially, they mostly slope *toward* the fairway — the ground game is invited in, not rejected. Bunker count is 115 revetted pots, all small (rx 12–16 ft, ry 10–12 ft), three times Wyatt's 38. No trees anywhere.

\* The 17th's −10 ft is the net tee-to-green change in the sim's linear elevation model. The 45-foot dune crest mid-hole cannot be represented in that model (see §11, A3); the crest is priced in topography/psychology (§5), not in the elevation adjustment.

---

## 3. Step 1 — Effective playing length (scratch)

Measured yardage, then the USGA adjustments. Every line is a number from the design or a stated assumption (§11).

**Elevation, per hole.** Conversion: 1 yard per 3 feet of elevation change, applied per hole and summed (the same conversion the Wyatt derivation used).

| Hole | Elev (ft) | Adj (yd) | Hole | Elev (ft) | Adj (yd) |
|---|---|---|---|---|---|
| 1 | 0 | 0 | 10 | −25 | −8 |
| 2 | −6 | −2 | 11 | +40 | +13 |
| 3 | 0 | 0 | 12 | −20 | −7 |
| 4 | +25 | +8 | 13 | +35 | +12 |
| 5 | 0 | 0 | 14 | 0 | 0 |
| 6 | 0 | 0 | 15 | −8 | −3 |
| 7 | 0 | 0 | 16 | 0 | 0 |
| 8 | −15 | −5 | 17 | −10 | −3 |
| 9 | −20 | −7 | 18 | +20 | +7 |

Net elevation +16 ft (120 ft uphill, 104 ft downhill); per-hole elevation adjustment **+5 yd**. (Netting first and then converting gives +5 yd as well — 16/3 = 5.3 — so there is no rounding ambiguity here, unlike Wyatt's 1-yard difference.) Dunmore is a dune walk, not a climb: the elevation adjustment is small because the course goes up and down in waves rather than climbing in one direction.

**The full EPL build:**

| Adjustment | Yards | Why |
|---|---|---|
| Measured yardage | 7,195 | Spec, verified front 3,591 + back 3,604 |
| Roll (firm links ground) | −180 | Firm, fast fairways: the ball is meant to run. Roll ~30 yd vs the 20-yd standard — about 10 yd/hole × 18. The doc's own numbers: a 260–270 yd drive "letting the firm ground add 20 yards of run" (1st), a second shot carrying the burn at 300 and "running on" 22 yards (2nd). Firmer than Wyatt's 0.60-firmness roll (~27 yd, −120 in the Wyatt derivation); see §11, A3 and the sensitivity in §9 |
| Elevation (per-hole table above) | +5 | Net +16 ft, in waves |
| Prevailing wind (sea breeze) | +46 | The wind is the main defense, and it does not fully cancel even on a balanced routing — a headwind costs more than a tailwind gains. Per-hole construction: into the wind (4, 6, 11, 13) +15 yd each = +60; downwind (1, 5, 9, 15, 18) −10 yd each = −50; crosswind (2, 3, 7, 8, 10, 12, 14, 16, 17) +4 yd each = +36; net +46. The afternoon land breeze (SW) flips several holes, which is why this is +46 and not larger; see §11, A6 and the sensitivity in §9 |
| Dogleg adjustment | +22 | Three doglegs (2, 8, 10) force lay-ups off the direct line, at the Wyatt rate of ~7.5 yd per dogleg (Wyatt: 4 doglegs → +30) |
| Forced carries (water) | 0 | The burn is a narrow stream (~7 yd wide), not a pond or lake carry — a scratch golfer carries it in the normal course of a full shot, and it forces no extra carry distance. Its cost is in the obstacle factors (§5) and the lay-up decision, not in EPL. Wyatt's +40 was for three genuine water carries (lake, two ponds); Dunmore has none of that kind |
| Altitude (sea level) | 0 | The Outer Banks are at sea level — far below the USGA's 2,000 ft threshold. (Wyatt at ~1,400 ft was also 0.) No adjustment |
| **Scratch effective playing length** | **7,088** | |

For comparison: Wyatt v3 EPL was 7,574 from 7,602 measured. Dunmore's EPL (7,088) is 107 yards *shorter* than its card — the firm ground gives back more than the wind and the (small) elevation take. A links plays shorter than its card on a calm day and longer than its card in a gale; the EPL is the average day, and the average day on the Outer Banks has wind in it.

---

## 4. Step 2 — Scratch yardage rating

The USGA formula (men):

```
Scratch Yardage Rating = (Scratch EPL / 220) + 40.9
                       = (7,088 / 220) + 40.9
                       = 32.22 + 40.9
                       = 73.1
```

---

## 5. Step 3 — Obstacle factors

The 10 USGA factors, rated 0–10 from the Dunmore design, converted to strokes on the same per-factor anchors the Wyatt derivation used. The strokes below are **bogey weights** — the full cost of each obstacle to a ~20-handicap golfer. The anchor table, reconstructed from the Wyatt derivation's stated conversions (topography 6 → 0.35, green target 6 → 0.30, bunkers 6 → 0.25; full table in the Wyatt doc's §5):

| Obstacle factor | Rating | Strokes | Why (Dunmore design) |
|---|---|---|---|
| Topography | **6** | +0.35 | Dune land in waves — uneven lies on every shot, blind crests on 6 and 17, the 45-ft Alps dune, semi-blind approaches. But the absolute climbs are smaller than Wyatt's (biggest single climb 40 ft on the 11th, vs Wyatt's 60 ft) — the ground moves constantly rather than climbing hard. A step below Wyatt v3's 7 |
| Fairway width / landing | **4** | +0.20 | Wide by design — "width is the welcome, because the wind is the punishment." 38 yd intended (13th narrowed to 30, 4th and 17th 34). One step wider than Wyatt's 5. See §11, A8: the sim implements 32 yd, not 38 — the factor is 4 either way, so the rating is unaffected, but the sim and the doc should be aligned |
| Green target | **6** | +0.30 | Open at the front, sloping toward the fairway — the target is effectively bigger for the correct (ground) shot. But several greens are severe: the 13th slopes *away* at 2% with a false front, the 16th is two tiers with a 3-ft step, the 17th is 20 yards wide, the 3rd is a 60-yard Biarritz, the 5th is 5,100 sq ft. Same rating as Wyatt v1's 6, one step below Wyatt v3's 7 |
| Recoverability / rough | **5** | +0.20 | Knee-high fescue on every hole — "a ball in it is a half-shot lost." Playable, but it sits down and the approach must be high and soft, which the wind will not allow. Dune hollows are blind punch-outs. Same as Wyatt's 5; the fescue is everywhere but it is a half-shot penalty, not the full-shot-plus of thick parkland rough |
| Bunkering | **8** | +0.35 | 115 revetted pot bunkers — three times Wyatt's count, and the most severe hazard on either course by design: small, deep, one shot in, one shot out, a full stroke lost, never a heroic escape. Front complexes on 6, 11, 15 (three deep pots each); the Principal's Nose cluster at 280 on the 5th; an 8-ft-deep pot on the 16th. One step above Wyatt v3's 7 |
| Water / out of bounds | **5** | +0.20 | Two kinds of trouble, neither dominant alone: the burn (narrow, on 2 and 14 — a penalty, but a 7-yard target) and the sea (OB, stroke and distance, on 8, 10, 17, 18 — and the wind pushes everything toward it). Same rating as Wyatt's 5, for a different mix: less water, more OB |
| Trees | **0** | +0.00 | No trees anywhere. Nothing to stop the wind, nothing to frame a shot, no blocked lies, no punch-outs from trees. This is a real difference from Wyatt (4 → 0.10) — and it is exactly why the wind is the defense: there is nothing to shelter behind |
| Green surface | **6** | +0.30 | Firm and fast — faster than Wyatt's 11.0 stimp baseline — but the slopes are gentler (mostly 1–2% toward the fairway) and the surfaces are more receptive to the running ball. The severity is in the tiers (16th's 3-ft step, 13th's away-slope, 4th's spine, the Biarritz swale), not in the average slope. One step below Wyatt v3's 7 |
| Psychological | **6** | +0.15 | Blindness is a feature here, not an exception: blind tee shots on 6 and 17, a semi-blind approach on 17, the Alps dune, the burn decisions on 2 and 14, the sea in view on four holes, and a wind that changes by the hour. Two steps above Wyatt v3's 4 — the most psychologically demanding course of the two |
| **Total obstacle strokes (bogey weights)** | | **+2.05** | Same total as Wyatt v1 (2.05), below Wyatt v3 (2.25) — but a different composition: more bunkering and psychology, less trees and green surface |

---

## 6. Step 4 — Course Rating

The USGA system applies the obstacle strokes at a reduced weight for the scratch golfer (the Wyatt weight, 0.35):

```
Course Rating = Scratch Yardage Rating + (Obstacle total × 0.35)
              = 73.12 + (2.05 × 0.35)
              = 73.12 + 0.72
              = 73.8
```

**Dunmore Links Course Rating: 73.8.**

---

## 7. Step 5 — Bogey rating

The bogey golfer (index ~20, drives ~200 yd) faces the same course, but the effective length is longer for them: they cannot cut the dogleg corners (2, 8, 10), they cannot carry the Alps dune (240 yards of sand — a 200-yard drive does not clear it, so they play short of the crest and punch out), and the Sahara shoulder on 6 hides the second landing area from a shorter drive. The Wyatt derivation's bogey gap was +350 yd (v1 gap 342, plus ~8 for the lengthened par-3 carries). Dunmore has fewer doglegs (3 vs 4) but the Alps and the burn lay-ups add distance back, so the same gap is the central case:

```
Bogey EPL = 7,088 + 350 = 7,438 yd

Bogey Yardage Rating = (Bogey EPL / 160) + 50.7
                     = (7,438 / 160) + 50.7
                     = 46.49 + 50.7
                     = 97.2

Bogey Rating = Bogey Yardage Rating + Obstacle total (full weight)
             = 97.19 + 2.05
             = 99.2
```

**Sensitivity (the one soft assumption, and it does not move the headline):**

| Bogey EPL gap (Δ_b) | Bogey rating | Slope |
|---|---|---|
| +330 yd | 99.1 | 136 |
| **+350 yd (central case)** | **99.2** | **137** |
| +370 yd | 99.4 | 137 |

The slope is 136–137 across the whole plausible range of the bogey-length gap, and the course rating does not depend on it at all.

---

## 8. Step 6 — Slope Rating

```
Slope = 5.381 × (Bogey Rating − Course Rating)
      = 5.381 × (99.24 − 73.84)
      = 5.381 × 25.40
      = 137
```

**Dunmore Links Slope Rating: 137.**

---

## 9. Verification — the cross-checks, including the ones that bite

**Cross-check: the +3 scoring band — 0.2 outside, and why that is honest, not a failure.** A +3 golfer's expected score on a course is approximately its rating minus 3. Dunmore: 73.8 − 3 = **70.8**. The design doc (`docs/course-two.md`) estimates "~71–73 for a +3." The recompute lands 0.2 strokes below the low end of that estimate. That estimate was written before any derivation was run, and it is a "~" estimate — but this document does not fudge an input to hit it, because the two inputs that could move it (roll and wind) are the least certain numbers in the derivation, and inflating them to land inside a soft band would be manufacturing agreement.

The sensitivity table shows exactly where the 0.2 lives:

| Roll | Wind | EPL | Rating | +3 expects |
|---|---|---|---|---|
| −120 yd | +46 | 7,148 | 74.1 | 71.1 |
| −180 yd | 0 | 7,042 | 73.6 | 70.6 |
| **−180 yd** | **+46** | **7,088** | **73.8** | **70.8** |
| −180 yd | +80 | 7,122 | 74.0 | 71.0 |
| −240 yd | +46 | 7,028 | 73.6 | 70.6 |

The +3 expectation is 70.6–71.1 across the whole plausible roll/wind range — the band's low end (71) is inside the uncertainty, and the central case is 0.2 below it. The most likely resolutions, in order: (1) the roll is at the firmer end of the range (the doc's "20 yards of run" on drives is consistent with roll ~28 yd, i.e. −150, which gives 73.9 and a +3 expectation of 70.9–71.0); (2) the doc's "~71–73" band was written a touch high — it was an estimate, and the recompute is the derivation. The Monte Carlo calibration harness for Dunmore has not run; when it does, the measured scoring mean will settle this to within ~0.3 strokes, and the band in `course-two.md` should be revised to match the measurement, not the other way around.

**Cross-check: the sim function's 74.6/141 — superseded, and the sim function needs recalibration for Dunmore.** `sim/course.py` `compute_rating_slope()` returns 74.6/141 for Dunmore — 0.8 rating and 4 slope above this recompute. The difference is structural, not a rounding dispute, and it is fully explained by the function's own docstring: it is calibrated to three **Wyatt** anchors (v2 74.6/138, v3 76.1/142, tournament 77.1/149). Applied to Dunmore it over-rates for two identifiable reasons:

1. **It prices bunkers per bunker (0.02 each).** 115 pots → 2.30 obstacle strokes from bunkers alone, against a total obstacle of 3.25. The USGA method rates bunkering as a course-level factor (this recompute: 8 → 0.35) — 115 small pots are one severe factor, not 115 separate 0.02-stroke penalties. The per-bunker pricing is calibrated to Wyatt's 38 bunkers and breaks at Dunmore's count.
2. **Its effective length ignores roll and prices wind flat.** The sim's effective length is yardage + 1.5 yd per foot of net elevation + 40 yd wind: 7,195 + 24 + 40 = 7,259 — *longer* than the card, because it has no roll term. But Dunmore's firm ground is the course's defining length feature: the USGA EPL is 7,088, *shorter* than the card, because the roll (−180) outweighs the wind (+46) and elevation (+5). The sim function cannot see a links at all — it has no firmness input.

**Verdict: yes, the sim function needs recalibration for Dunmore.** The options, in order of preference: (a) per-course calibration constants in `compute_rating_slope()` (a Dunmore parameter set that returns 73.8/137, alongside the Wyatt set); (b) a structural change — cap the bunker contribution and add roll/wind parameters to the effective-length model, then re-fit all four anchors (Wyatt v2/v3/tournament + Dunmore). Option (a) is the smaller, safer change; option (b) is the honest one if a third course ever arrives. Either way, do not ship Dunmore differentials or handicap math against 74.6/141 — the live differential for a 71 at Dunmore would read −2.0 against the sim's number and −1.5 against the recompute, and the recompute is the authoritative one. No code was changed in this task; the recalibration is a follow-up for the sim owner.

**Cross-check: Dunmore vs Wyatt — the 2.3-stroke gap is exactly what the design promises.** Wyatt v3 76.1/142 vs Dunmore 73.8/137. Dunmore is 407 yards shorter, plays shorter than its card on firm ground, has wider fairways, open-fronted greens, and no trees — and its +3 expectation (70.8) sits 2.3 strokes below Wyatt's (73.1), matching the rating gap to the decimal. The design doc's two scoring bands (Wyatt ~72–74, Dunmore ~71–73) differ by ~1 stroke at their midpoints; the recompute says the gap is 2.3 strokes, because the doc's Dunmore band was written high (see the +3 cross-check above). The *relative* statement — Dunmore plays easier for a +3 than Wyatt — is confirmed by both routes.

**Cross-check: real-course band.** A 7,195-yard par-72 links with 115 pot bunkers, a sea wind, and firm, fast ground should rate in the low-to-mid 70s with a slope in the mid-130s. 73.8/137 sits in that band. (For scale: slope 113 is standard difficulty; 137 is a stern test, but a fair one — the width and the open fronts keep it below Wyatt's 142.)

**Uncertainty.** The headline is robust: ±0.3 rating / ±1 slope. The largest sensitivities are the roll assumption (each 1 yd/hole of roll = 0.08 rating — the full −120 to −240 range moves the rating by 0.5) and the wind adjustment (±0.2 rating across 0 to +80). The obstacle ratings are the most judgemental input, but moving any single factor by one step moves the rating by 0.02 and the slope by ~0.3 — the total is stable.

---

## 10. Setup tiers — the four ratings

The conditions system (`docs/conditions-system.md` §4.3) runs four setups, on the same tier spreads as Wyatt (+0.8 rating per step up, −0.8 for Soft; slope +3 / +7 / −4), because the setup levers are the same — firmness, stimp, wind, pins, rough, fairways. What changes is the base they sit on: 73.8/137 instead of 76.1/142.

| Setup tier | Rating | Slope | Implied bogey rating | What changes (from conditions-system.md §4.3, Dunmore-flavoured) |
|---|---|---|---|---|
| **Daily** (base) | **73.8** | **137** | 99.2 | Normal firmness, normal stimp, wind 0–10, pins mid-difficulty, rough standard |
| **Championship** | **74.6** | **140** | 100.6 | Firm, fast stimp, wind 8–15, pins tucked, rough +0.5 inch |
| **Major week** | **75.4** | **144** | 102.1 | Tournament stimp, wind 10–18, pins tucked, rough +1 inch, fairways narrowed, one extra fairway bunker at 300 yd on every par 4/5 |
| **Soft / scoring** | **73.0** | **133** | 97.7 | Soft, slow stimp, wind 0–5, pins accessible, rough standard |

Note: the Championship rating (74.6) is numerically identical to the sim function's Dunmore base number (74.6/141) — that is a coincidence, not an agreement. The sim's 74.6 is an over-rated Daily base; the Championship 74.6 is the Daily base plus the setup levers. Do not confuse the two; the slope differs (140 vs 141) and the meaning differs entirely.

One Dunmore-specific caveat on the tiers: the wind lever is stronger here than at Wyatt (a Major-week wind on a links is worth more than +0.2 rating — the doc says the course "effectively" plays 7,800 yards into a gale), and the firmness lever is weaker (the ground is already firm; there is less headroom to firm it further). The spreads above are carried from Wyatt as specified, so the tiers are comparable across courses; if Major-week scoring at Dunmore measures softer or harder than the tier implies, the wind lever is the first thing to re-derive — not the base rating.

Why the slope rises faster than the rating: each setup hurts the bogey golfer more than the scratch golfer. Championship: bogey rating rises 1.36 vs scratch 0.80 (1.7×). Major week: bogey rises 2.90 vs scratch 1.60 (1.8×). Soft: bogey falls 1.54 vs scratch 0.80 (1.9×). That asymmetry is the slope system working as designed.

---

## 11. Assumptions — every number this derivation had to supply

| # | Assumption | Value used | Effect if wrong |
|---|---|---|---|
| A1 | Elevation conversion | 1 yard per 3 ft, per hole, summed | Each 3 ft of net elevation = 1 yd EPL = 0.005 rating. The total elevation adjustment is only +5 yd, so even a different conversion moves the rating by ~0.02 |
| A2 | Holes 2 and 15 elevation | −6 ft and −8 ft ("slightly downhill", no number in the spec; the sim's values) | ±6–8 ft on either hole = ±2–3 yd EPL = ±0.01 rating. Immaterial |
| A3 | The Alps crest (17th) | Net −10 ft in EPL; the 45-ft crest priced in topography/psychology, not elevation | Counting the climb at 1 yd/3 ft would add +15 yd EPL = +0.07 rating. The crest is a blind-shot feature more than a length feature, and the descent returns most of the climb on the ground game |
| A4 | Roll at links firmness | −180 yd (roll ~30 yd vs 20 standard) | The largest sensitivity: each 1 yd/hole of roll = 18 yd EPL = 0.08 rating. The full −120 to −240 range moves the rating 73.6–74.1 (see §9) |
| A5 | Prevailing wind | +46 yd (into +15, downwind −10, cross +4, per-hole construction in §3) | The second-largest sensitivity: 0 to +80 moves the rating 73.6–74.0. The afternoon land breeze partially cancels the morning pattern, which bounds the upside |
| A6 | Dogleg adjustment | +22 yd (three doglegs at the Wyatt rate) | Carried from Wyatt; corners are in the same kind of places |
| A7 | Forced carries | 0 (the burn is a narrow stream, not a pond/lake carry) | If the burn crossings were priced as carries, EPL would rise by ~20 yd = +0.09 rating — but a 7-yard stream is not a carry in the USGA sense |
| A8 | Fairway widths | Design intent: 38 yd default (13th 30, 4th/17th 34) | The sim implements 32.0 yd default, not 38 — a doc/code discrepancy, flagged not fixed. The fairway factor is 4 either way (32 yd is still wide), so the rating is unaffected; the sim and the doc should be aligned in a follow-up |
| A9 | Green speeds | ~11.5–12 stimp baseline (firmer/faster than Wyatt's 11.0) | A measured daily stimp of 12+ would raise the green-surface factor a step; rating +0.02, slope +0.3 — immaterial to the base, material to the tiers |
| A10 | Bogey EPL gap (Δ_b) | +350 yd over scratch EPL (same as Wyatt) | Slope is 136–137 for Δ_b anywhere in 330–370; rating unaffected |
| A11 | Obstacle stroke anchors | Wyatt per-factor conversions (e.g. bunkering 8 → 0.35) | Moving any single factor one step moves the rating 0.02, slope ~0.3 |
| A12 | Scratch obstacle weight | 0.35 (Wyatt derivation) | The full USGA procedure rates obstacles per hole for both golfers; the 0.35 weight is the Wyatt simplification, carried for comparability |
| A13 | Altitude | 0 (sea level, far below the 2,000 ft USGA threshold) | No USGA adjustment below 2,000 ft |

---

## 12. What would change this number

- **A formal USGA rating visit.** A certified team measures each hole's EPL factors and rates all 10 obstacles per hole for both golfers. Expected movement from this reconstruction: ±0.3 rating / ±2 slope. That is the honest error band on 73.8/137, and it is the only thing that could replace it with a certified number.
- **Measured roll / firmness.** The roll assumption is the biggest lever. If the ground measures firmer (roll ~35 yd) the rating falls ~0.2; if it measures softer (roll ~27 yd, Wyatt's number) the rating rises ~0.2. A Stimpmeter-and-roll measurement day at the (fictional) course would settle it — in practice, the Monte Carlo calibration harness is the measurement: if Dunmore's simulated scoring mean lands above 70.8, the roll is softer than assumed.
- **Measured green speeds.** If the daily stimp measures 12.0+ rather than the assumed ~11.5, the green-surface factor rises a step — rating +0.02, slope +0.3. Small for the base rating; the setup tiers move more.
- **The Dunmore calibration harness.** The sim has not yet run a calibration sample on Dunmore (fast-mode rounds scored 74/80/78, but fast mode is the smoke-only path — it scores ~81–84 on Wyatt, so those numbers are completion checks, not calibration). When the harness runs, the measured scoring mean is the independent check on this rating: rating − 3 should equal the measured +3 mean within ~0.3 strokes.
- **Tee moves.** Every 22 yards of measured length is 0.1 rating. New back tees, or a tournament tee, re-open the derivation.
- **Pin and setup changes do not change the base rating.** They change the setup tiers (§10), which is exactly what the tiers are for.

---

## 13. Where the old numbers live — update these (follow-up, not done here)

This document is the recompute only. The following places still carry numbers this recompute supersedes, and must be updated in a follow-up pass:

- `sim/course.py` — `compute_rating_slope()` returns 74.6/141 for Dunmore and must be recalibrated (per-course constants, or a structural change — see §9). This is the one live number that is wrong today: differentials and handicap math computed against 74.6/141 overstate Dunmore's difficulty by 0.8 strokes. **Do not edit the sim code as part of this document; the recalibration is the sim owner's follow-up, and it must re-verify the three Wyatt anchors (74.6/138, 76.1/142, 77.1/149) after any change.**
- `docs/course-two.md` — the scoring band "~71–73 for a +3" should be revised to match the recompute and, when it lands, the calibration measurement (central expectation 70.8; see §9). The band is an estimate; the recompute is the derivation. The "Scoring" row of the Dunmore-vs-Wyatt table carries the same band.
- `docs/conditions-system.md` — when Dunmore goes live in the conditions system, its §4 needs a Dunmore tier table (Daily 73.8/137, Championship 74.6/140, Major week 75.4/144, Soft 73.0/133 from §10), not a copy of Wyatt's.
- `docs/sim-engine.md` — any course object or worked differential that states Dunmore's rating must use 73.8/137.
- The web build (`autonomous-golf-world` artifact) and the landing page (`mas-golfs` artifact) — any Dunmore rating/slope display must use 73.8/137 when Dunmore is shown.
- The double-green note: `docs/course-two.md` was corrected so the double green is shared by the 1st and 18th only (the 9th's brief was fixed). The sim follows 1 & 18. No rating impact — the double green is one large putting surface either way — but the correction is recorded here so the next reader does not re-open it.

Until those updates land, this document is the single source of truth for the Dunmore rating and slope.

---

## Sources

- USGA Rules of Handicapping, Section 13 (Course Rating) and Appendix G (The Golf Course, Course Rating and Slope Rating), usga.org — effective playing length factors (roll, elevation, dogleg/forced lay-up, prevailing wind, altitude ≥ 2,000 ft), the 10 obstacle factors, the yardage-rating formulas (Scratch EPL/220 + 40.9; Bogey EPL/160 + 50.7), and the slope formula (5.381 × difference, men).
- `docs/course-rating-v3.md` — the Wyatt National v3 recompute this document follows exactly (method, per-factor stroke anchors, 0.35 scratch weight, tier spreads, lever table, and the validation pattern of §9).
- `docs/course-two.md` — the Dunmore design this derivation is computed from (7,195 yards, per-hole yardages, elevations, green complexes, 115 pot bunkers, burn, sea OB, wind rotation, scoring band).
- `sim/course.py` `build_dunmore_links()` — the implemented hole data, cross-checked against the doc (every yardage, par, name, and bunker count agrees; 115 bunkers, 3 water crossings, 0 trees).
- `docs/conditions-system.md` §4.3 — the four setup tiers and their spreads, carried to Dunmore in §10.
- Verification arithmetic: per-hole elevation table, EPL build, yardage ratings, obstacle total, bogey sensitivity (Δ_b 330/350/370), roll/wind sensitivity, tier slopes, and the sim-function comparison (effective length 7,259, obstacle 3.25, 74.63/140.72 → 74.6/141) were all computed in a script and the results transcribed above; the script is not part of the repo (no code changes in this task).
