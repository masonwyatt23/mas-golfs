# PGA Tour Live Broadcast — Design Reference for Mas Golfs

**Date:** Nov 12, 2026
**Purpose:** steal the best of real PGA Tour broadcast presentation for the autonomous Mas Golfs broadcast — putting, shot coverage, graphics, commentary cadence, and course beauty. Every element ends with a concrete, buildable feature for our show.
**Scope note:** this doc covers the real broadcast only. Golf Clash and other golf video games are a separate research workstream (the user named Golf Clash explicitly); game-specific mechanics (flag-out animations, power meters, wind rings) are not covered here except where they overlap with broadcast practice.

**How to read the "steal" lines:** Mas Golfs already has a director state machine, a NodeCG graphics bundle (scorebug, leaderboard, lower-thirds, ticker, player card, hole card), a Nantz/Gruden commentary booth with a silence budget, drama-scored 0.5× replays, and 59 Watch with live probability (see `docs/broadcast-stack.md`, `docs/commentary-prompts.md`, `docs/brand-identity.md`, `docs/sim-engine.md` §3.5). Steal lines that say "already built — extend it" mean the broadcast already does the thing and the steal is the next step, not a rebuild.

---

## 1. Putting coverage

### 1.1 How the broadcast shoots a putt

The putt is the most-covered shot in golf, and the camera grammar is rigid:

- **Low green-side camera.** The standard putt camera is low, roughly at green level, positioned to show the ball, the hole, and the break in one frame — the "fall line" view. The classic setup around a green is three cameras: a fixed tower/platform camera beside the green, a mobile handheld camera that walks with the play, and an overhead (blimp, and now drone) camera. The low green-side angle is what makes a 6-footer feel like a 6-footer: the viewer reads the slope the same way the player does.
- **The flagstick is a character.** Since the 2019 Rules change (Rule 13.2), a player may putt with the flagstick left in the hole with no penalty — but the classic broadcast moment is still the *tend*: the caddie holds the flagstick and pulls it cleanly the instant the putter strikes the ball, moving clear before the ball arrives. When it goes wrong it becomes the story itself: at the 2021 Ryder Cup, Bryson DeChambeau's caddie could not dislodge a stuck flagstick as the ball rolled toward the cup, and the broadcast's analysts went into brief panic on air. The flagstick is the smallest prop on the course and one of the most dramatic.
- **The putt is held, not cut.** The director holds the low green-side camera through the entire roll — no cutting mid-putt. The camera stays on the ball until it drops or stops. This is the putting equivalent of the "never cut mid-flight" rule: the roll *is* the drama.
- **The reaction shot is the payoff.** After the drop, the cut is to the player's face and the crowd, not to a graphic. The 2001 Tiger Woods 60-foot putt at the 17th at Sawgrass is the canonical example: the ball breaks left, then right, and the camera never leaves it.

**What Mas Golfs should steal:** add a **flagstick tend/pull animation** to the putting sequence — the flag is tended (held, slightly lifted) during the read, and pulls cleanly out of the cup the instant the putter strikes, with the flag laid down on the green. On a made putt, hold the low green-side camera through the whole roll and cut to Mas's reaction (not a graphic) for the payoff. The sim already emits `putt_result` with `dist_ft`, `made`, `break_ft`, `break_dir`, `speed`, and `leave_ft` — the director already cuts to the `PIN` camera for putts; the missing pieces are the flag animation and the reaction hold.

### 1.2 Make vs. lip-out: the broadcast's two different languages

A made putt and a missed putt are presented as two different kinds of television:

- **The make** gets the full treatment: the ball drops, the crowd noise swells, the booth says one short line (or nothing — see §4), and the graphic confirms the score change. The sound of the ball hitting the bottom of the cup is the punctuation. Broadcasts mic every green so the drop is audible; the "rattle" is part of the product.
- **The lip-out / near-miss** gets the *replay* treatment, not the live treatment. The canonical 2026 example: Jake Knapp at the 3M Open hit an approach that came to rest literally on the lip of the cup, touching the flagstick without dropping. The broadcast put up the graphic "HOW IS THAT POSSIBLE?!", the crowd gasped audibly, and the clip went viral — the near-miss *was* the content. A lip-out is always replayed in slow motion from the low angle, usually twice: once at full speed, once super slow-mo, so the viewer can see exactly how the ball caught the edge.
- **The comebacker is its own beat.** After a miss, the broadcast does not rush past the tap-in. The leave distance is stated ("leaves himself 4 feet for par"), the camera stays low, and the comebacker is shown — because the comebacker is where the drama compounds.

**What Mas Golfs should steal:** give lip-outs and near-misses their own presentation language. A putt that lips out or stops on the edge should trigger (a) a slow-motion replay from the low green-side camera, (b) a "SO CLOSE" / "HOW?" lower-third in the broadcast's voice (not a generic miss graphic), and (c) the comebacker shown as its own beat with the leave distance stated on screen. The sim already distinguishes a miss's `leave_ft` and `speed` (a `long` miss leaves a longer comebacker) — wire those into the director so a lip-out (leave ≤ 6 inches, ball on the edge) is a different event from an ordinary miss. The clip pipeline should score lip-outs as high-drama moments (near-miss is already in the drama model; make sure "on the lip" outranks "burned the edge").

### 1.3 The graphics that accompany a putt

The modern broadcast puts three numbers on a putt, and only three:

- **Distance, to the inch.** "14 feet 1 inch" — the broadcast states putt distance precisely (Valero Texas Open, Apr 2026: Marco Penge putting for birdie from 14'1" and 16'2"). Precision is the point: it makes the putt feel measurable and therefore dramatic.
- **Make probability.** Next to the distance, the broadcast shows the Tour's make percentage for that distance — Penge's 14-footer showed 23%, his 16-footer 21%. The number does two jobs: it tells a newcomer how hard the putt is, and it makes a make feel like an upset.
- **Break direction.** The analyst states the break in plain language ("breaking right to left, about a cup outside") before the putt, and the graphic sometimes shows it. The newest layer is **ShotLink putt path** (debuted at the Sony Open, Jan 2026): TOURCAST now visually maps a putt's actual path on the green, built on a LiDAR base layer of the green's slopes, with cameras on the green mapping the ball's X/Y/Z coordinates. Broadcasters are now getting putt tracing in the live truck, not just the app.

**What Mas Golfs should steal:** add a **putt graphic** to the lower-third on every putt: distance to the inch, break ("2 ft, left to right"), and live make probability from the sim's own putting model. The sim already computes all three (`putt_result` carries `dist_ft`, `break_ft`, `break_dir`; the putting model in `sim-engine.md` §3.5 has make rates by distance — 3 ft ~99%, 10 ft ~40%, 20 ft ~14% — so the probability is one table lookup, never invented). And add a **putt-path trace**: draw the ball's actual roll line on the green after the putt, with the predicted break line shown before it — the broadcast's putt path, done with our own physics instead of LiDAR. This is the single highest-value new graphic in this doc: it makes every putt watchable even for a viewer who doesn't know golf.

### 1.4 Sound design on the green

Every tee box and green on a Tour broadcast is microphoned — that is a stated production fact from the Every Shot Live build (120 cameras at THE PLAYERS, mics on every tee and green). The sounds that matter on a putt are, in order: the click of the putter, the roll (near-silent, which is why the booth goes quiet), the ball dropping into the cup, and the crowd. The Masters is the extreme version: bird song is part of the brand, and the broadcast mixes it deliberately.

**What Mas Golfs should steal:** give the putt its own sound moment — a soft putter click, near-silence during the roll (the ambient bed ducks, the booth says nothing), and a distinct cup-drop sound (a short wooden rattle, not a generic chime) on a make. The ambient engine already has layered audio with sidechain ducking (`broadcast-stack.md` §5); the putt is the place to use it most aggressively. Silence during the roll is free and it is the most broadcast-like thing in this whole doc.

---

## 2. Shot coverage

### 2.1 Tracer technology: Toptracer and ShotLink

Two systems, often confused, do two different jobs:

- **Toptracer (formerly Protracer)** is the *television* system: optical cameras track the ball in flight and draw the tracer line over the live picture, with ball speed, launch angle, apex, curve, carry, and dispersion. The same cameras sit above driving-range bays (1000 fps) — "the same technology you see on Sunday afternoon TV." On Tour broadcasts the tracer is drawn from a camera behind the tee (and, at the 17th at Sawgrass, from three Protracers: behind the tee, on the tower behind the green, and on the scoreboard).
- **ShotLink** is the *data* system: ~131–150 cameras and 36 TrackMan radars per event, connected by miles of fiber-optic cable, covering ~220 acres. Radar triggers on the strike; cameras generate a polygon estimating the landing area; the course is pre-mapped with drone-based 3D modeling (elevation, terrain, expected bounce and roll) so the system predicts where the ball will land and points the cameras there. Data lands within seconds for live scoring, tracers, and scoreboards. On each green, ShotLink Plus replaced lasers with three video cameras pointed at the hole (each streaming at 450 Mbps — 54 cameras is 24 Gbps of video) to track ball movement on the greens in 3D. Volunteers with lasers and tablets still mark ball positions as a backstop.
- **The 2024–2026 leap: Live Drone AR.** The Tour's newest system (debuted at the 2024 Travelers, Emmy-winning) puts the tracer on a live drone shot: an overhead drone view of the hole with the ball's flight traced in augmented reality. The 2025 upgrade, **drone AR smart tracing**, colors the trace by outcome — green is good, red is bad — decided by where the ball actually ends up, about 1.2 seconds after the strike. It was built by the Tour with Bolt6 (software), Virtual Eye (graphics), and Kaze Aerial (drones). The Tour now owns the IP. The quote that matters: "The colour of the trace has never really told the story in televised golf. It's traditionally just been some colour the networks or sponsor prefer, and you don't know, aside from shot shape, if the ball's going to be in a good or bad place. So we thought, let's have the colour of the trace be dictated by where the ball ends up." — Alex Turnbull, SVP production technology and analytics.
- **The newest predictive layer:** CBS has experimented since 2023 with technology that predicts where a ball will land while it is still in flight. And the Tour's AWS work adds **Win Probability** (10,000 simulations run every 15 seconds) and an **AI director** that ranks camera feeds in real time by framing, visibility, and shot context.

**What Mas Golfs should steal:** two things. First, **outcome-colored tracers**: our tracer is already gold; make it change color by outcome — gold while the ball is in the air, green when it lands in a good spot, red when it finds trouble. We know the outcome the instant the sim resolves the shot, so this is a render-side color switch, not a prediction problem. The Tour needed 1.2 seconds and six partners to do it; we get it free because the sim *is* the truth. Second, **a drone-AR hole view**: an overhead aerial shot of the hole with the tracer drawn over it, used for the replay of every approach (not just the live flight). The director already has an `AERIAL` camera; the steal is using it for the replay, with the tracer overlaid on the aerial view — the exact Live Drone AR shot, without the drone.

### 2.2 Camera positions

The Tour's camera grammar per hole:

- **Minimum four cameras per hole** (Every Shot Live standard): a stationary unmanned camera on the tee box, a manned greenside camera, and wireless manned cameras on the fairway. At a flagship event like THE PLAYERS there are ~120 cameras total across the course.
- **The tower camera** sits behind the green, high, on a scaffold — the workhorse angle for approaches. **The blimp** gives the high establishing shot and the "fall line" view of a green. **Cablecam** (two-point, e.g. over the 16th–17th at Sawgrass) flies the camera along a wire over the water. **A crane** (up to 120 ft) gives the tee-to-green overview the blimp can't. **A bunker camera** sits in the sand at the 17th. **A super-slo-mo camera** (300 fps) shoots reactions on the island green. **Handhelds** behind the green give the reverse shot. At the Masters the count is ~75 cameras for 18 holes, including cameras hidden in trees and bunkers.
- **The TGL contrast** (useful as a what-not-to-do): the simulator league uses 73 camera sources, 28 robotic, 10 virtual, plus Spyder Cam, Rover Cam, and a 400-ft Rail Cam — impressive, but it reads as a studio show, not golf. Mas Golfs should stay on the Tour's grammar, not TGL's.

**What Mas Golfs should steal:** the director already has six camera scenes (`TEE_DTL`, `TRACER`, `CATCH`, `BUNKER`, `PIN`, `AERIAL`) — the steal is to **name and place them like the Tour does** and add two missing positions: a **tower camera** (high behind the green for approaches — the workhorse angle we don't have) and a **cablecam-style flyover** (a slow wire-cam move along the hole between shots, used on the signature holes). The render already supports per-position FOV and damping; the tower and cablecam are new positions in that same system, not a new system.

### 2.3 Replay language

- **Super slow motion is for the swing, not the ball.** CBS's SwingVision (since 2004, Konica Minolta-sponsored) is a super-slo-mo camera used for swing analysis — the replay shows the swing at a speed where the viewer can see the shaft flex and the hands. Ball-flight replays run at normal speed or 0.5×, never slower: a ball at 0.25× is boring.
- **The replay rule is drama-scored.** The 17th at Sawgrass gets replayed constantly because the producer knows the hole is the story; a routine fairway shot never gets a replay. The slow-mo replay system is used most on the island green to show "each player's eyes at the precise moment he realizes whether his ball will end up in the drink or near the hole" — the replay is about the *reaction*, not the ball.
- **Replays are always introduced.** The broadcast never cuts to a replay cold: a lower-third or a booth line ("let's look at that again") frames it, and the replay ends with a cut back to live.

**What Mas Golfs should steal:** the director already does drama-scored 0.5× replays — extend the rule: **replays are for reactions, not just ball flight**. After a high-drama shot, the replay should cut to Mas's reaction (held finish, head drop, fist pump) in slow motion, not just re-show the tracer. And always introduce the replay with a lower-third ("REPLAY — THE SHOT THAT SAVED THE ROUND") and end it on the live scene, never on a graphic. This is a director-rule change, not a render change.

### 2.4 How the director cuts

The Tour director's rules, distilled from producer Tommy Roy (NBC/Golf Channel, 17th at Sawgrass) and the Every Shot Live build:

- **Cut on the event, never on the clock.** The cut happens when the ball is struck, when it lands, when the player reacts — never because 8 seconds have passed.
- **One camera per phase.** The tee shot is one camera, the flight is one camera, the landing is one camera. The cut is the transition; within a phase the camera moves smoothly.
- **The fallback is always the wide.** If a camera fails, hold the wide shot. Never cut to black, never cut to a graphic as a substitute for a picture.
- **The walk is filled, not skipped.** Between shots, the broadcast fills with a flyover of the hole, the leaderboard, or the FedExCup standings — never dead air, never a static wide.
- **Remote operators, not a single director.** In the Every Shot Live build, remote operators in London and Atlanta cut from shot to shot from preview monitors, each assigned to a group — the traditional director/producer bottleneck is removed. The Tour's 2026 agentic-production test goes further: an AI ranks feeds in real time and pairs the best angle with live ShotLink stats.

**What Mas Golfs should steal:** the director already cuts on events and holds the wide as fallback — the steal is the **walk-fill rule**: between shots, never hold a static wide for more than a few seconds; fill with a slow hole flyover, the leaderboard, or the 59 Watch state. Our "walk to ball" phase already uses the `CATCH` dolly; add a flyover rotation on the longer walks. And the Tour's AI-director test is a direct precedent for our autonomous director — cite it in `broadcast-stack.md` when the director is next revised: we are not inventing the autonomous director, the Tour is building the same thing.

---

## 3. The graphics package

### 3.1 The scorebug

The scorebug is the most important graphic in golf, and the Tour spent 50 years learning to keep it small:

- **CBS went constant in 2021.** Until 2021, CBS golf had no persistent scorebug — the leaderboard appeared and disappeared. In 2021, under coordinating producer Sellers Shy, CBS added a constant mini-leaderboard in the lower right corner, explicitly copying Fox's U.S. Open coverage and the scorebugs of football and basketball. Shy's rule: "whenever anyone comes in the room and they want to know who's leading the tournament, they're going to find out immediately." The bug stays on "primarily all the time" and is only pulled for sponsor obligations.
- **The bug is a mini-leaderboard, not a score.** It shows the leader(s) and the featured player's position — the story of the tournament in one glance. Fox's version, which CBS copied, is the model: a compact strip, not a panel.
- **The 3-second rule** (already in our brand doc): a newcomer must understand the story in 3 seconds. The Tour's bug passes because it shows only: who is leading, by how much, and where the player on screen sits.

**What Mas Golfs should steal:** nothing structural — our scorebug already follows this (gold-ruled, constant, "MAS · THRU · ROAD TO 59"). The steal is the **mini-leaderboard discipline**: our bug should always carry the top 3 of the round leaderboard, not just Mas's score, so a newcomer who walks in mid-round instantly knows the story is "Mas is chasing 59" and how close he is. And the bug should be pulled only for the intermission card, never for a graphic.

### 3.2 Leaderboard, hole graphics, player cards, lower-thirds

- **Leaderboard:** full-screen on the walk between holes, never over live play. The Tour's leaderboard is a clean table — position, name, score to par, thru, today's score — with the leader in gold. It appears on event boundaries (hole end, round end), never mid-shot.
- **Hole graphics:** the hole card shows the hole number, par, yardage, and the hole's name or character ("the island green", "Amen Corner"). The Tour's hole flyover is the visual: a drone or blimp shot from tee to green with the yardage overlaid.
- **Player cards:** name, score, today's score, position, and one stat that matters (driving distance, strokes gained putting). One stat, not five — the card is a headline, not a spreadsheet.
- **Lower-thirds:** three kinds, and only three: the shot-data strip (club, distance, ball speed, carry), the result ("BIRDIE — moves to −4"), and the story ("ON PACE FOR 59"). Each holds ~5 seconds and slides out. The Tour's lower-thirds never stack — one at a time, always.

**What Mas Golfs should steal:** the NodeCG bundle already has all six graphics (scorebug, leaderboard, lower-third ×3, ticker, player card, hole card) — the steal is the **discipline rules**: leaderboard only on event boundaries; hole card only with the flyover between holes; player card carries exactly one stat (rotate it: driving, GIR, putting, strokes gained); lower-thirds never stack, one at a time, 5-second hold. Write these rules into the director as hard rules, the same way "never cut mid-flight" is a hard rule. Our brand doc already states the 3-second rule; the director should enforce it.

### 3.3 Virtual graphics and the SmartCart

CBS works with ARL (Animation Research Ltd, New Zealand) on virtual graphics — animated, data-driven looks that sit inside the picture rather than on top of it (e.g., a virtual line showing a putt's break, or a 3D hole model). The SmartCart (in use since 2016) is a mobile high-brightness touchscreen the on-course team uses to draw on the picture (telestrator) and pull up stats. The point of both: the graphic lives *in* the golf, not *over* it.

**What Mas Golfs should steal:** the putt-path trace (§1.3) and the outcome-colored tracer (§2.1) are both virtual graphics in this sense — they live inside the picture. The steal is a design rule: **prefer in-picture graphics (tracer, putt path, break line) over overlay graphics (panels, boxes)**. Every time the team is tempted to add a panel, ask whether the information can be drawn on the course instead.

---

## 4. Commentary cadence

### 4.1 When the booth talks vs. stays silent

This is the most important section in the doc, and the rule is simple: **the booth talks before the shot and after the result, almost never during it.**

- **Before the shot:** the decision, the numbers, the story. The host sets the scene ("14 feet, breaking right to left, for birdie"), the color analyst breaks down the choice. This is where our Nantz/Gruden booth already lives.
- **During the swing and the roll:** silence. The sound is the club, the ball, the crowd, the birds. The Tour's producers mic the course precisely so the booth *can* shut up.
- **After the result:** one line, then silence again if the moment is big enough. The canonical case is Jim Nantz at the 2019 Masters: after Tiger Woods sank the winning putt on the 18th, Nantz said "A return to glory" — and then said nothing for nearly three minutes while Woods hugged his family and competitors. He told his producer on the talk-back switch, "I'm not saying anything for a long time," and made sure he would be the next voice heard. His mentor, Frank Chirkinian (the "father of televised golf"), taught him to "use silence as a weapon." Nantz's own line: "It was just so big. There was nothing you could do to add to it. You could only ruin it." (One dissenting note for honesty: UK commentator Clive Tyldesley later called it a "waste of a moment" for failing to identify the people Woods was hugging — the counter-argument is that identification is a graphic's job, not the booth's, in a moment that big.)
- **The radio contrast proves the rule.** Mike Tirico called the same putt for Westwood One radio and *couldn't* go silent — radio has no pictures, so the announcer must describe. Television's advantage is that the picture does the work. Our broadcast is television; the booth should act like it.

**What Mas Golfs should steal:** the commentary service already has a silence budget (~half the round silent, 1 line/15 s, max 4/hole) and a director hold (lines queued at `shot_start` wait until `landing`). The steal is the **escalating silence rule**: the bigger the moment, the longer the silence after it. A routine birdie gets one line; a 59 Watch moment on the 18th gets the Nantz treatment — one short line ("Fifty-nine."), then silence until the next hole's card, with the picture and the crowd bed doing the work. Encode it as a rule in the commentary service: silence duration scales with the drama score of the event that just happened. And the booth must never identify people or narrate a celebration — that is the picture's job.

### 4.2 How Nantz-style hosting works on a big putt

- **Set it up, then get out.** Before a big putt, Nantz gives the viewer exactly three facts (distance, break, what's at stake) and then stops talking. The putt is watched, not narrated.
- **The call is short and declarative.** "A return to glory." Not a sentence, a phrase. The booth's job on a make is to name the moment, not describe it.
- **The story is told between shots, not during them.** Nantz's storytelling — the history, the context, the "hello, friends" warmth — happens on the walk, never over a swing. The Masters broadcast is built this way: the booth talks on the way to the ball and shuts up over it.

**What Mas Golfs should steal:** the commentary prompts already encode this (decision line before the shot, silence during, one line after). The steal is a **big-putt template**: for any putt with drama ≥ 75, the host's pre-putt line is exactly three facts (distance, break, stakes) and the post-make line is a phrase, not a sentence. Add this as a template in `commentary-prompts.md` §4 — it is a one-paragraph addition, not a redesign.

### 4.3 Sound design

- **Microphones everywhere.** Frank Chirkinian's founding innovation was placing as many microphones as possible around the course to pick up the sounds of the tournament and the players' conversations, "rather than having commentators talk over silent footage." Every tee and green is mic'd; the roving cameras carry mics too.
- **The crowd is an instrument.** The roar after a make is mixed deliberately — it swells, it doesn't just appear. The Masters mixes birdsong as a brand element. The splash on the 17th at Sawgrass is captured with strategically placed mics because the splash *is* the content on that hole.
- **Impact sound is the signature.** The click of a driver, the thump of an iron, the soft tick of a putter — each is distinct, and the broadcast makes sure the viewer hears it.

**What Mas Golfs should steal:** the ambient engine already layers crowd, birds, wind, and impact sounds with sidechain ducking. The steal is **impact-sound specificity**: a driver, an iron, a wedge, and a putter should each have a distinct impact sound, and the cup-drop should have its own sound (see §1.4). And the crowd bed should swell on a make proportional to the drama score — a routine par gets a murmur, a 59 Watch birdie gets a roar. This is a mixing rule, not a new asset.

---

## 5. Course beauty

### 5.1 How the broadcast makes a course look incredible

- **Light is the whole game.** The cinematic golf filmmakers' rule, stated plainly by MWGolf.tv (a crew with 20+ years filming for Golf Channel, Sky Sports, PGA Tour Productions, and the DP World Tour): "We don't just fly a drone around. We chase the golden hour light, we look for dramatic shadows, and we treat your landscape with the reverence of a cinematic feature." Pre-production is planned around the sun's trajectory; every frame is color-graded in post. Royal Dornoch's "Flying Caddie" series filmed each hole at sunrise and sunset specifically "to capture the natural undulations on the links."
- **The drone shot is a flyover, not a hover.** The standard beauty shot is a slow drone move from tee box to green with a 360-degree look at the putting surface and its undulations — the viewer learns the hole while admiring it. The PGA Tour's broadcast drones at THE PLAYERS (2026: four drones — two AR, two beauty) do exactly this between shots.
- **Signature-hole framing.** Every course has 2–3 holes the broadcast returns to obsessively (the 17th at Sawgrass, Amen Corner at Augusta, the 16th at Scottsdale). The broadcast frames them the same way every time so the viewer learns them: the same camera, the same angle, the same graphic. Familiarity is what makes a hole iconic.
- **The establishing shot is a panorama, then a detail.** The PGA of America's Bandon Dunes coverage is the textbook sequence: wide aerial of the whole property, then the cliffside interface, then a lone golfer at a flagstick, then a top-down bunker detail. Panorama → challenge → human → detail. That is the visual narrative of a tournament broadcast in four shots.
- **The Masters is the extreme version.** Augusta limits commercials to ~4 minutes per hour (vs. a normal sports broadcast), runs on one-year contracts since 1956, and controls the tone of the coverage completely. The result is a broadcast that feels unhurried and reverent — and it is the most-watched golf on television. The lesson is not "be Augusta" (we can't); it is that **restraint is a production value**. Fewer graphics, longer holds, quieter booth = more beautiful.

**What Mas Golfs should steal:** three things. First, **golden-hour grading as a permanent state**: the broadcast build already has a dawn-to-dusk sky and a film grade — lock the default look to the golden-hour end of it (warm horizon glow, long shadows, warm light on the fairways) rather than midday flat light. The course should always look like 5pm at Augusta, not noon at a muni. Second, **signature-hole framing**: pick Wyatt National's three signature holes (the 12th "The Picture" over the pond is the obvious one; add the 5th drivable par 4 and the 17th Road Hole) and give each a fixed, repeated camera treatment — same angle, same flyover, same hole card — every round, so viewers learn them. Third, **the panorama → detail sequence for the round open**: every round should open with a wide aerial of the whole course, then the first hole's challenge, then Mas at the tee, then a detail (the flag, a bunker rake, dew on the green). The director already has an aerial flyover between holes; the steal is making the round-open a fixed four-shot sequence.

---

## 6. Ranked top 10: stealable ideas

Ranked by (watchability gained) ÷ (build cost). All ten are buildable on the current stack — no new machine, no new runtime, no paid service.

1. **Putt-path trace** (§1.3). Draw the ball's actual roll line on the green after every putt, with the predicted break line before it. Uses the sim's existing `break_ft`/`break_dir`; the Tour just debuted this in Jan 2026 and it is the single most watchable new graphic in golf. Cost: render-side line drawing + one lower-third. *Highest value in this doc.*
2. **Outcome-colored tracers** (§2.1). Gold in flight, green on a good result, red on trouble. The Tour needed six partners and an Emmy to do it; we get it free because the sim knows the outcome. Cost: a color switch in the tracer.
3. **Flagstick tend/pull animation + reaction hold** (§1.1). The flag is tended during the read, pulls the instant the putter strikes, and the camera holds low through the roll, cutting to Mas's reaction — not a graphic — on the make. Cost: one animation + one director rule.
4. **Putt graphic: distance to the inch, break, live make %** (§1.3). One table lookup from the sim's own putting model; the Tour shows "14 ft 1 inch, 23%". Cost: one lower-third variant.
5. **Lip-out presentation language** (§1.2). Slow-mo replay from the low angle, a "SO CLOSE" lower-third, and the comebacker as its own beat with the leave distance stated. Cost: director rules + one lower-third; the sim already emits `leave_ft`.
6. **Escalating silence** (§4.1). Silence after a moment scales with its drama score; a 59 Watch moment on the 18th gets the Nantz treatment — one phrase, then silence until the next hole. Cost: one rule in the commentary service.
7. **Drone-AR replay** (§2.1). Every approach replayed from the aerial camera with the tracer overlaid on the overhead view — the Tour's Live Drone AR shot, without the drone. Cost: reuse the existing `AERIAL` camera in the replay path.
8. **Golden-hour lock + signature-hole framing** (§5). Default the grade to warm late light, and give the 12th, 5th, and 17th a fixed repeated camera treatment every round so viewers learn them. Cost: grading defaults + three camera presets.
9. **Tower camera + cablecam flyover positions** (§2.2). Two new camera positions in the existing system: high behind the green for approaches, and a slow wire-cam move along the hole between shots. Cost: two render positions, no new infrastructure.
10. **Cup-drop sound + drama-scaled crowd swell** (§1.4, §4.3). A distinct cup rattle on a make; the crowd bed swells in proportion to the drama score. Cost: one sound asset + one mixing rule.

---

## 7. What I could not verify

- **Specific YouTube clip URLs.** The task asked for YouTube clips of PGA Tour broadcasts. I verified the *moments* through reporting (Tiger's 2019 Masters winning putt and Nantz's silence; Tiger's 2001 60-foot putt at Sawgrass's 17th; Tiger's 2005 chip-in on the 16th at Augusta; Knapp's lip-out at the 2026 3M Open; Penge's putts at the 2026 Valero Texas Open) but I did not verify individual YouTube URLs, and I will not invent them. The canonical place to watch them is the PGA Tour's YouTube channel — add links from there, not from memory.
- **"Hole camera" / cup camera.** I found no verified evidence of a camera *inside* the cup on Tour broadcasts. The putting coverage is the low green-side camera, the tower camera, and the overhead — not a cup cam. Do not build a cup-cam feature on the assumption the Tour has one.
- **Exact make-probability methodology.** The broadcast shows a make % per distance (e.g. 23% at 14 ft), but the Tour has not published the exact model behind the number. Our version should use the sim's own putting model (§3.5 of `sim-engine.md`) and label it as our model's number, not the Tour's.
- **Current drone count and AR usage by event.** The four-drone figure (two AR, two beauty) is from THE PLAYERS 2026 reporting; drone deployment varies by event and network. Treat it as the flagship standard, not a every-week fact.
- **Golf Clash and other games.** Deliberately out of scope for this doc (see scope note). The user's flag-out idea maps to §1.1's tend/pull animation, but game-specific mechanics (wind rings, power meters, needle timing) need their own research pass.

---

## Sources

- PGA Tour — "New ShotLink, TOURCAST enhancements to debut at Sony Open in Hawaii" (putt path, Jan 14, 2026): https://www.pgatour.com/article/news/latest/2026/01/14/new-shotlink-tourcast-enhancements-to-debut-at-sony-open-in-hawaii
- PGA Tour — "How it works: TOURCAST on Korn Ferry Tour" (ShotLink Select, GPS, ~1-inch accuracy): https://www.pgatour.com/korn-ferry-tour/article/news/latest/2024/04/19/how-it-works-tourcast-on-korn-ferry-tour-shotlink-tracking-new-technology
- BizTech Magazine — "How TV Producers Use Technology to Cover the 'Island Green'" (9 cameras, crane, cable cam, Protracer, super slow-mo, mics): https://biztechmagazine.com/article/2015/05/how-tv-producers-use-technology-cover-island-green?amp
- BizTech Magazine — "How Data Helps the PGA TOUR Engage Fans and Boost Performance" (ShotLink Plus: 3 cameras per green, 450 Mbps each, 24 Gbps): https://biztechmagazine.com/article/2020/07/how-data-helps-pga-tour-engage-fans-and-boost-performance?amp
- Front Office Sports video (Aug 2026) — ShotLink: 131 cameras, 220 acres, 36 TrackMan radars, fiber, drone 3D mapping, landing-polygon prediction: https://www.instagram.com/reel/DcGzDI3uCl8/
- Australian Golf Digest — "The PGA Tour's new predictive smart-trace TV technology" (drone AR smart tracing, Bolt6/Virtual Eye/Kaze, Emmy, green/red trace, RBC Canadian Open June 2025): https://www.australiangolfdigest.com.au/pga-tour-color-coded-tv-shot-trace-tv-drone-impressive-technology-but-do-fans-like-it/
- SiliconANGLE — "The intelligent green" (TOURCAST Range, agentic AI director, Win Probability 10,000 sims/15 s): https://siliconangle.com/2026/03/17/intelligent-green-aws-pga-tour-reimagining-fan-experience-agentic-ai/
- Sports Video Group — "PGA TOUR 'Fan Forward' Digital Efforts" (putt tracing in broadcast, LiDAR base layer, ball X/Y/Z mapping): https://www.sportsvideo.org/2026/03/11/304558/
- Sports Video Group — "CBS Sports Adds Constant Scorebug to PGA TOUR Coverage" (Sellers Shy, constant mini-leaderboard, SmartCart, ARL): https://staging.sportsvideo.org/2021/01/27/cbs-sports-adds-constant-scorebug-to-pga-tour-coverage-as-sellers-shy-takes-over-at-front-bench/?print=1
- Sports Business Journal — "Calls by Nantz, Tirico will be part of history" (Nantz: "A return to glory", ~3 min silence, "I'm not saying anything for a long time"): https://www.sportsbusinessjournal.com/Journal/Issues/2019/04/22/Media/Sports-media
- Golf Digest — "Jim Nantz wasn't where you thought he was for Tiger Woods' winning putt" ("silence as a weapon", Frank Chirkinian): https://www.golfdigest.com/story/jim-nantz-wasnt-where-you-thought-he-was-for-tiger-woods-winning-putt-reveals-how-historic-masters-moment-went-down
- Masters.com — "CBS Celebrates 60 Innovative Years at the Masters" (6 cameras 1956, ~75 cameras, first HD 2000, 4K 2016, 3D 2010): https://www.masters.com/en_US/news/articles/2016-04-09/cbs_celebrates_60_innovative_years_at_the_masters.html
- SportsIn.biz — "The Masters at Augusta" (4 min/hour commercials, Amen Corner Live 2006, all 18 holes 2002): https://sportsin.biz/the-masters-at-augusta-a-business-that-keeps-growing-without-losing-its-exclusivity/
- Golf Digest Middle East — "Every shot shown live? It's coming at the Players Championship" (120 cameras, min 4 per hole, Hawk-Eye remote operators, mics on every tee and green): https://golfdigestme.com/every-shot-shown-live-its-coming-at-the-players-championship/
- Wikipedia — "PGA Tour on CBS" (Chirkinian, mics everywhere, SwingVision super slow-mo since 2004, 2021 persistent leaderboard, 2023 landing prediction): https://en.wikipedia.org/wiki/PGA_Tour_on_CBS
- Australian Golf Digest — "Rules Review: What happens when someone tending the flagstick deflects your ball" (2019 Rule 13.2, tending): https://www.australiangolfdigest.com.au/rules-of-golf-review-flagstick-deflects-ball-penalty-or-not/
- GOLF.com — "Bryson DeChambeau, caddie narrowly avoid rarely used ruling at Ryder Cup" (stuck flagstick, 2021): https://golf.com/instruction/rules/bryson-dechambeau-rarely-used-rule-ryder-cup/
- PGA Tour Instagram (July 2026) — Jake Knapp lip-out at the 3M Open ("HOW IS THAT POSSIBLE?!", ball on the lip touching the flagstick): https://www.instagram.com/reel/DbJAmG2jFMn/
- PGA Tour Facebook (Apr 2026) — Marco Penge, Valero Texas Open ("14 feet 1 inch", 23% / 21% make percentages): https://www.facebook.com/reel/945709285091282/
- PGA Tour Fan Forward — competition adjustments (Live Drone AR, betting stream): https://fanforward.pgatour.com/competition-adjustments
- Royal Dornoch — "Capturing the cinematic beauty of Royal Dornoch" (sunrise/sunset drone, tee-to-green 360 look): https://royaldornoch.com/2026/02/18/capturing-the-cinematic-beauty-of-royal-dornoch/
- MWGolf.tv — cinematic golf course storytelling (golden-hour light, sun-trajectory planning, color grading): https://www.mwgolf.tv/
