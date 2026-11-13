# Game AI Companies & Techniques — What Mas Golfs Should Steal

**Date:** November 12, 2026
**Purpose:** Deep research into the top video-game AI teams and techniques, as design-pattern inspiration for making Mas Golfs feel elite and alive — the golf equivalent of a real broadcast, not a diorama.
**Scope:** Design patterns only, not code. Everything proposed must be buildable by a small autonomous project on a **free budget** (no paid APIs, no paid services, no paid hosting).
**Companion docs:** `best-golf-games.md`, `golf-clash-mechanics.md`, `pga-tour-broadcast.md` (same folder), `sim-engine.md`, `commentary-prompts.md`, `broadcast-stack.md`, `self-improvement.md`, `unreal-vertical-slice.md`.

> **The one-sentence takeaway:** the best game AI does not try to be perfect — it tries to be *legible*. Players believe an opponent is human when they can read its intent, see it make a mistake, watch it adjust, and hear a story about it. Every pattern in this document is a version of that sentence.

---

## 1. The leading game-AI teams — and what each is actually best at

### 1.1 Ubisoft La Forge — the research lab inside a publisher

**What it is:** Ubisoft's dedicated AI research lab (Montreal / Paris), founded 2017, ~20+ researchers and engineers working directly with production teams. Its mandate is research that ships into real games, not papers for their own sake.

**What it ships:**
- **Ghostwriter** (2023): an in-house LLM tool that drafts the first version of NPC "barks" — the short reactive lines NPCs say in the world ("Watch it!", "Did you see that?"). A human narrative designer still edits and approves every line before it ships. The point is volume: hundreds of small lines a writer would never have time to author by hand, all staying in the game's voice because a human is the gate.
- **Learned Gameplay AI / world-model research**: La Forge works on agents that learn from gameplay data and on procedural systems that let NPCs react to the world rather than follow fixed scripts.
- **Animation research**: motion-matching and learned locomotion work feeding into Ubisoft's animation pipeline.

**What it is best at:** the *authoring pipeline* — using AI to multiply human creative output while keeping a human as the quality gate. The lesson is not "let the model write everything"; it is "let the model write the first draft of the boring 90%, so humans spend their time on the 10% that matters."

> **What Mas Golfs should steal:** the **Ghostwriter pattern for the booth**. Our commentary service already generates lines from a small local model; adopt La Forge's gate explicitly — generate 3–5 candidate lines per event, score them against the hard rules (never invent a stat, never speak over a swing, 280-char cap), and keep a human-readable "approved line" log. More importantly: use the model to draft *barks* — the small ambient reactions (a caddie mutter after a chunk, a gallery gasp, a one-word Gruden aside) — which are currently unwritten because nobody has time to hand-author hundreds of them. Pre-generate a bank of 200+ approved barks offline, cache them, and play them at runtime. Zero runtime cost, huge aliveness payoff.

### 1.2 EA SEED — the applied-research team that builds toys that become features

**What it is:** SEED (Search for Extraordinary Experiences Division), EA's research division, founded ~2017, ~25+ people across Stockholm, LA, Vancouver. It prototypes emerging tech (ML, procedural generation, neural rendering) and hands working prototypes to EA's studios.

**What it ships (or has shipped into games):**
- **Learned motion / animation research**: neural animation systems that blend motion-capture clips the way motion matching does, but learned rather than hand-tuned.
- **Procedural content and world generation** experiments for sports and open-world titles.
- **Agent research**: reinforcement-learning agents trained in EA's games as testbeds, used to stress-test maps and find exploits before humans do.
- **FIFA/EA Sports FC animation**: SEED's work feeds the motion-matching and "HyperMotion" pipelines — thousands of motion-captured animations blended in real time so players move like athletes, not puppets.

**What it is best at:** **prototyping at the boundary** — taking a technique that is 80% ready in a paper and turning it into a playable demo inside a real game, which is what convinces a studio to fund the last 20%.

> **What Mas Golfs should steal:** the **prototype-then-commit discipline**. Before committing to any "AI" feature (a learned swing, a neural crowd), build it as a one-day toy inside the web build — e.g. a crowd of 40 billboard spectators that stand/cheer/sit based on shot drama — and judge it by the stranger test (does a stranger watching for 60 seconds believe it?). If the toy reads, promote it; if not, kill it. This is also the argument for the Unreal vertical slice in `unreal-vertical-slice.md`: one hole, judged on real footage, before 18 holes.

### 1.3 Sony AI / PlayStation — Gran Turismo Sophy, the one ML opponent that actually shipped

**What it is:** Sony AI is Sony's corporate AI research lab; its flagship game project is **Gran Turismo Sophy**, built with Polyphony Digital. Sophy is the most credible shipped example of a machine-learning opponent in a major game — and the details matter because they show what "ML opponent" actually means in production.

**What Sophy actually is:**
- A **deep reinforcement-learning agent** trained to race Gran Turismo 7 cars, developed jointly by Sony AI, Polyphony Digital, and Sony Interactive Entertainment.
- It races with **real-time, fine-grained car control** — throttle, braking, steering at the physics tick — and it learned **overtaking, defensive driving, and slipstreaming** as emergent behaviors, not as scripted rules.
- It was trained in a **distributed cloud environment** (thousands of parallel races), then deployed as a time-limited event in GT7 ("Gran Turismo Sophy" race-together events), not as a permanent replacement for the game's normal AI.
- **Crucially, Sophy is constrained**: it races under the same physics as the player, it does not get unfair grip or speed, and it was tuned to be *beatably human* — fast, but with exploitable lines and occasional mistakes, so racing it feels like racing a person.

**What it is best at:** proving that **a learned opponent can be fair, fast, and human-readable at the same time** — but only with enormous training compute and a team of PhDs. The "AI" is the training pipeline, not a line of code you drop into a game.

> **What Mas Golfs should steal:** **not the training pipeline — the design contract.** Sophy's contract is: *same physics as the player, no hidden advantages, mistakes included, beatable by a good human.* Our sim already honors this (identical physics for every shot, dispersion σ never changes — see `self-improvement.md`). The steal is to **surface the contract on air**: when Mas makes a decision, the booth should be able to say *why* in physics terms ("he's taking the aggressive line because the Monte Carlo says it's worth 0.15 strokes"), and when he misses, the booth should name the *mechanism* ("thin strike, ball speed down 8 mph") rather than shrug. A viewer who can read the decision believes the golfer is real. Also steal Sophy's *event* framing: Sophy shipped as a limited-time event, not a permanent mode. Mas's Road to 59 is already an event structure — treat major weeks and record chases as limited-time events with their own branding, not as background noise.

### 1.4 Inworld AI — the character engine (and its 2025–26 pivot)

**What it is:** Inworld AI, founded 2021, raised ~$100M+, built the best-known runtime for LLM-driven NPCs: characters with memory, personality, goals, and real-time voice, shipped as a Unity/Unreal SDK. Its characters powered demos and early integrations in games and virtual worlds.

**What happened:** by 2025–26 Inworld has **largely stepped back from being a plug-and-play NPC studio and repositioned as B2B AI infrastructure** — selling the underlying character engine to enterprises rather than courting game developers directly. The plug-and-play NPC market turned out to be smaller and harder than the pitch decks assumed: latency, cost per line of dialogue, and the hallucination problem made it hard for studios to ship LLM NPCs as a default feature.

**What it is best at (still):** the **character stack** — persistent memory across sessions, personality as a set of tunable traits, goals that drive behavior, and voice that matches the character. Its design contribution outlives its business pivot: an NPC feels alive when it *remembers* what happened and *wants* something.

> **What Mas Golfs should steal:** the **memory + goals stack, at our scale**. Mas already has a version of this in `self-improvement.md` (the golfer model with a change log, one fix per round, a season budget). The steal is to **make memory visible on air**: the player card should carry "ONE FIX" (it already does), but also a *memory line* — "last time on this hole he went long left; today he's aiming 8 feet right" — and a *goal line* — "needs birdie on two of the last three to stay on 59 pace." A character with a memory and a goal is a character; a character with neither is a screensaver. This costs nothing: it is a text line assembled from the event log.

### 1.5 Convai — the NPC platform that stayed developer-facing

**What it is:** Convai is a hosted platform for real-time conversational NPCs in games and XR — voice in, voice out, with memory, perception (the character can "see" the scene), and actions (the character can trigger animations and movement). Free tier exists (100 interactions/month on the free plan per third-party roundups; paid from $29/month Indie). Unity, Unreal, and three.js/web SDKs.

**What it is best at:** being the **most straightforward on-ramp** to a talking NPC — the whole pipeline (speech-to-text, reasoning, text-to-speech, lip-sync, animation triggers) in one box, with sub-second latency as the design target. Research cited in 2026 roundups: responses under ~800 ms feel conversational; a generic cloud API round trip adds 1–2 s of lag that reads as a stall.

**What it is best at (for us):** nothing we should buy — it is a paid hosted service, and our project is $0/month by design. But its **latency lesson is directly applicable**: our commentary pipeline already pre-generates lines (event-driven, cache-first) for exactly this reason — a line that arrives 2 seconds late is worse than silence. Convai's 800 ms bar is a good acceptance test for our own TTS path.

> **What Mas Golfs should steal:** the **perception hook**. Convai characters react to what they *see* in the scene. Our booth should react to what it *sees* in the event stream — not just the shot result, but the *context*: wind gusting on the tee, a ball trickling toward the water, a putt that lips out. The commentary-prompts doc already has a "bad miss" and "recovery" template; extend it with **scene-aware lines** that reference the visible world ("the flag is tucked behind that bunker — he's got 12 feet of green to work with") rather than only the numbers. And steal the latency bar: **no spoken line may start more than ~800 ms after its trigger event**; if the TTS is not ready, play the cached line or stay silent.

### 1.6 Modl.ai — the invisible AI: testing, bots, and balance

**What it is:** Modl.ai (Copenhagen, founded 2018) builds AI that **plays games the way a QA team does** — at scale, around the clock. Its bots playtest builds, find bugs, probe balance, and generate training data. It works with studios to automate the parts of QA that humans are bad at (repetition, coverage, regression) so humans can do the parts machines are bad at (judgment, taste).

**What it is best at:** **the unglamorous 90% of game AI** — not the opponent you fight, but the thousand invisible playthroughs that make the game fair before you ever touch it. Its pitch is honest: most "game AI" value is in testing and balance, not in a clever opponent.

> **What Mas Golfs should steal:** the **automated playtest loop, wholesale**. We already have the seed of it: the calibration harness (`sim/calibrate.py`, 10,000-round gate in `qa-plan.md`). Steal Modl's framing and make it a *standing system*, not a one-off: **every sim change gets an automatic overnight batch** — N rounds headless, scoring/GIR/fairways/driving compared against the calibration bands, and a one-line verdict written to a log ("PASS — scoring 73.1, within 72–74; driving 268 yd, within 265–275"). No human reads the raw numbers; the human reads the verdict. This is the single highest-leverage "AI" investment for a one-person autonomous project: it is how the golfer *self-improves* without anyone watching.

### 1.7 Kinetix — AI animation for everyone else

**What it is:** Kinetix is a platform that turns text or video into 3D character animation — type "celebrate like you just won" and get a rigged animation, or upload a video and get the motion retargeted onto a game character. It is aimed at creators and small studios that cannot afford a mocap stage.

**What it is best at:** **democratizing animation** — the long tail of movement (celebrations, idle fidgets, reactions) that makes a character feel alive but that no small team can hand-keyframe one by one.

> **What Mas Golfs should steal:** the **animation long tail, hand-built**. We cannot afford a mocap shoot for every reaction (the Unreal doc prices a half-day Xsens/Rokoko shoot at $1,500–$4,000), and we should not buy Kinetix. But the *insight* is free: **a character's aliveness lives in the 2-second reactions, not the 8-second swing**. Mas needs a library of small, cheap, hand-keyed reactions in the web build — the fist pump, the cap tip, the hands-on-hips after a miss, the slow walk, the crouch to read a putt, the flag-pull moment Mason asked for. Each one is a few keyframes. Ten of them, triggered by event type, will do more for believability than any amount of terrain polish. Priority order: (1) celebration on birdie-or-better, (2) disappointment slump on bogey-or-worse, (3) cap-tip / acknowledgment after a great shot, (4) the flag coming out as the ball approaches the hole (Mason's explicit ask), (5) the crouch-and-read before a putt.

### 1.8 Other names worth knowing

| Team / product | What they are best at | Relevance to Mas Golfs |
|---|---|---|
| **NVIDIA ACE** (Avatar Cloud Engine) | Real-time lip-sync, facial animation, and speech for digital humans; the middleware layer under many AI NPC demos. | The lip-sync bar: if the booth ever gets a visible avatar, the mouth must match the words. For now, a *voice-only* booth sidesteps the whole problem — a deliberate advantage. |
| **Ubisoft Scalar / cloud gaming tech** | Distributed simulation; running parts of a game world in the cloud. | Validates our "broadcast, don't pixel-stream" architecture — one render, many viewers. |
| **Rival Theory / RAIN** | Behavior-tree tooling for Unity (Rival Theory's RAIN was an early behavior-tree framework). | Historical note: behavior trees won the NPC war (see §2.2). |
| **Houdini Crowds / Massive** | Large-scale crowd simulation for film and games — tens of thousands of agents with individual behaviors (used in *Game of Thrones*' Battle of Winterfell, among others). | The crowd pattern (§2.5): agents with simple local rules produce believable mass behavior. We need 40 spectators, not 40,000 — the same math, at 0.1% of the cost. |
| **Scenario / Unity Muse** | Generative AI for game assets (textures, sprites, 3D props) trained on a studio's own art. | The asset-pipeline lesson: generate the *repetitive* art (trees, grass tufts, bunker textures) procedurally and spend human effort on the *hero* art (the 12th hole, the golfer). Our web build already does this with procedural trees. |
| **ElevenLabs (game voice)** | Voice cloning and expressive TTS, used for NPC voices in several shipped games. | Ruled out as a paid path for us; but its *voice-consistency* lesson applies — the Nantz host voice and the Gruden color voice must be recognizably the same voice every time, which is why we lock `am_michael` / `af_sky` in `voice-options.md` and never drift. |
| **Krafton / inZOI** | The clearest *shipped* example of LLM NPCs in a commercial game — inZOI (early access March 2025, 1M+ copies in its first week) uses on-device small language models ("CPC" — co-playable characters) for NPCs with memory and personality. | The proof that the Inworld vision can ship — but note it shipped with **small on-device models**, not cloud LLMs. That is exactly our architecture: Qwen3.5-4B on the 8GB Mac. inZOI is the validation of our local-model bet. |

---

## 2. The techniques that make game characters feel alive

### 2.1 Procedural animation and motion matching

**What it is:** Motion matching is the technique that replaced hand-blended animation trees in modern games (FIFA/EA Sports FC, *The Last of Us Part II*, *Forza*). The engine keeps a database of motion-captured clips; every frame it searches for the clip whose pose best matches where the character is and where it needs to go, then blends into it. The result is movement that looks captured, because it *is* captured — just selected by an algorithm instead of an animator.

Procedural animation is the complement: small movements computed at runtime rather than played back — a foot planting on uneven ground, a head tracking a moving ball, a torso leaning into a slope, a hand reaching for a flagstick.

**Why it matters:** the uncanny valley in games is almost never about the face. It is about the *feet* (sliding, floating, planting wrong) and the *transitions* (snapping between poses). Motion matching fixed the transitions; procedural animation fixed the feet.

> **What Mas Golfs should steal:** **procedural micro-animation on the golfer, in the web build.** Our golfer already has a 9-keyframe swing; the steal is everything *around* the swing: (1) the head tracks the ball through the whole flight (a 1-line look-at constraint); (2) the feet plant on the terrain slope — sample the ground height under each foot and rotate the ankles, so Mas never floats on a hillside; (3) the idle sway — a slow weight shift and a club twirl while waiting, so he is never a statue between shots; (4) the walk — a simple two-bone leg cycle with the terrain-following foot plant, so the walk to the ball reads as walking, not gliding. None of this needs mocap. All of it is a few lines of math per frame. In the Unreal slice, the equivalent is GASP Motion Matching (already in `unreal-vertical-slice.md`) — but the web build gets 80% of the believability from the four procedural touches above.

### 2.2 Behavior trees vs utility AI

**What it is:** the two dominant ways to decide what an NPC does next.
- **Behavior trees (BTs):** a hierarchical tree of decisions — "if enemy visible → attack; else if hurt → flee; else patrol." Every AAA game from *Halo* to *Horizon* uses them. They are readable, debuggable, and designers can reason about them. Their weakness: they are brittle at the edges, and they produce *predictable* behavior because the tree is the same every time.
- **Utility AI:** every possible action gets a *score* (a utility function) based on the current world state, and the NPC picks the highest-scoring action. *The Sims* is the canonical example; *Middle-earth: Shadow of Mordor*'s Nemesis system uses utility-style scoring for orc behavior. Utility AI produces more varied, surprising, and human-feeling decisions — because two similar situations can score differently — but it is harder to debug ("why did he do *that*?").

**The industry consensus:** behavior trees for *structure* (the skeleton of what a character can do), utility scoring for *choice within a branch* (which of the valid options to pick right now). Pure utility AI without a tree is unmaintainable; pure BT without scoring is robotic.

> **What Mas Golfs should steal:** **this is already our decision-engine architecture — name it and use it consciously.** The sim's Monte Carlo decision engine (`sim/decisions.py`) *is* utility AI: generate candidates, score each by expected strokes through real physics, pick the best, with a hero-shot threshold (must be worth ≥0.15 strokes). The steal is to **make the utility scores visible**: the shot-data lower-third should show not just the chosen shot but the *rejected alternative* and its cost ("lay-up was 0.12 strokes worse"). A viewer who sees the choice *and* the road not taken believes there is a mind making the choice. Second steal: add a **behavior-tree layer on top of the utility engine for the *between-shot* character** — a simple tree (celebrate → react → walk → read putt → address ball) that decides what Mas *does* when he is not swinging, so his off-ball behavior is structured and readable rather than random. Third steal, from the Nemesis system: **persistent rivals and memory**. The Nemesis system's genius was that orcs *remembered* you. Mas should remember *holes*: a per-hole memory ("he has never birdied the 12th in 47 rounds") that the booth can invoke. That is a database lookup, not AI — and it is the most human-feeling feature in this whole document.

### 2.3 Dynamic difficulty — and why we should steal its *opposite*

**What it is:** dynamic difficulty adjustment (DDA) — the game quietly makes itself easier when you struggle and harder when you dominate. *Resident Evil 4* is the famous example (it adjusts enemy aggression and item drops invisibly); *Left 4 Dead*'s "AI Director" is the celebrated version (it spawns zombies and items based on the players' stress level, pacing the experience like a film director). The *Mario Kart* rubber-band is the crude version everyone notices and hates.

**The honest rule:** DDA works when it is invisible and serves the *experience*; it fails when players detect it, because it breaks the contract that the world is fair. The best DDA is not about difficulty at all — it is about *pacing*.

> **What Mas Golfs should steal:** **the AI Director's pacing job, not difficulty adjustment.** Our golfer must *never* get secretly better or worse to manufacture drama — the calibration targets in `sim-engine.md` are a contract, and the self-improvement doc explicitly forbids changing dispersion σ. That is the right call, and it is also what makes the Road to 59 *credible*: a 59 has to be earned by the physics, not gifted by the director. What we steal from *Left 4 Dead* is the **director's camera and editing decisions**: the drama score (already in `broadcast-stack.md`) should drive *presentation*, not *outcomes* — when drama is high, hold the camera longer, cut to the reaction cam, slow the replay to 0.5×, let the booth go quiet for a beat. When drama is low, cut faster, show the leaderboard, run the ticker. The director shapes the *watching*, never the *golf*. This is the single most important design line in the project: **the sim is honest; the broadcast is theatrical.**

### 2.4 Crowd simulation — 40 people who believe

**What it is:** the techniques behind believable crowds, from Houdini/Massive film crowds (tens of thousands of agents) to stadium games. The core pattern is always the same: **each agent is dumb, but the crowd is smart**. Each agent follows 3–5 local rules (stand near your seat, face the action, react to events with a personal delay and intensity, copy your neighbors with a lag). The believability comes from *variance*: different reaction times, different intensities, different idle behaviors — never synchronized.

The failure mode is synchronization: a crowd that all stands at the same frame reads as a single organism, not people. The fix is always the same — per-agent random phase, per-agent personality (a few are enthusiastic, most are moderate, one or two are bored), and *propagation* (the reaction spreads through the crowd like a wave, not a switch).

**Sports-game specifics:** football games layer thousands of individual voices into a wall of sound that changes with momentum; cameras cut to the stands after a goal to show supporters jumping and hugging; the crowd's *silence* after a miss is as important as its roar after a goal.

> **What Mas Golfs should steal:** **a gallery of 30–50 spectators, built from the same 3-rule pattern, in both the web build and the Unreal slice.** Each spectator is a billboard sprite or a low-poly figure with: (1) a home position (near the green, along the fairway rope line); (2) a personality drawn once (enthusiast / moderate / stoic — sets reaction amplitude and delay); (3) a reaction rule (on shot outcome, amplitude = drama × personality, delayed by 0.2–1.2 s, propagating outward from the green). Add two audio layers: a bed of ambient murmur that rises and falls with the round's drama, and a swell on big moments. Add one camera behavior: **on any drama ≥85 moment, cut to the gallery for 1.5 seconds** — a tight shot of three or four spectators reacting — before returning to Mas. That single cut is the cheapest believability in this document: it tells the viewer *other people are watching*, which is what makes a broadcast feel like an event instead of a screensaver. Golf-specific truth: a golf gallery is mostly *quiet* — the murmur, the held breath before a putt, the polite applause. Do not port a football crowd. Port a golf gallery: restrained, then explosive on the rare great moment.

### 2.5 Realistic NPC reactions — the 2-second rule

**What it is:** the observation, consistent across animation and AI research, that believability is won or lost in the **first 2 seconds after an event**. A character who reacts *immediately and specifically* reads as alive; a character who reacts late, generically, or not at all reads as a mannequin — no matter how good the idle animation is.

The techniques: **reaction libraries** (a set of pre-built responses indexed by event type and intensity), **reaction layering** (face + body + voice all responding to the same event, but at different speeds — the body flinches first, the face follows, the voice comes last), and **anticipation** (the character reacts *before* the outcome is certain — leaning forward as a putt tracks toward the hole, then either exploding or slumping).

> **What Mas Golfs should steal:** **anticipation, specifically.** Our broadcast already has reaction cams and slow-motion replays; the missing piece is the half-second *before* the outcome. When a putt is tracking toward the hole, the camera should already be tight on Mas, and Mas should already be leaning — the body language of hope. When a ball is heading for the water, the gallery should already be inhaling. Implement this as a **prediction hook in the event bus**: the sim knows the ball's trajectory before it lands; emit a `likely_outcome` hint (e.g. `putt_tracking: true`, `ball_heading: water`) 0.5–1.0 s before the result event, and let the director and the character react to the *hint*. The payoff is enormous and the cost is a few lines: it is the difference between watching a result and *feeling* a moment. Second steal: **reaction layering** — on a big moment, sequence the response: (1) Mas's body (fist pump / slump) at t+0.1 s, (2) the gallery swell at t+0.4 s, (3) the booth's first word at t+0.8 s (Nantz's silence doing the work), (4) the lower-third at t+1.5 s. Staggering is free; simultaneity is what reads as fake.

### 2.6 AI-driven commentary and dialogue

**What it is:** two separate problems that get conflated. **Dialogue** (NPCs talking) is the Inworld/Convai problem: open-ended conversation, memory, personality. **Commentary** (a booth describing an event) is a narrower, more tractable problem: the input is a structured event stream, the output is a short line in a fixed voice, and the hard constraints are timing (never speak over the action) and truth (never invent a number).

The state of the art in commentary is not a bigger model — it is a **better pipeline**: event → template + slot-filling → model for the creative 20% → rule-based validation (numbers checked against the event, banned words filtered, length capped) → cache → TTS. The model is the *seasoning*, not the meal. Every shipped system that works (sports games' commentary engines, which have used template + variation systems for decades) does it this way; the systems that fail are the ones that let a raw LLM narrate live.

> **What Mas Golfs should steal:** **we already have the right architecture — deepen it in three places.** (1) **The silence budget as a feature, not a fallback.** The commentary-prompts doc already says ~half the round should be silence; make that *visible* — a "silence is the broadcast" note in the booth spec, and a rule that the booth *never* fills a walk between shots with chatter. Nantz's genius is the pause. (2) **The two-voice contrast as a system.** Gruden's job is not to agree with Nantz — it is to *disagree productively* ("I love the aggressive line here, Jim, but he's got to carry that bunker"). Build a "respectful disagreement" template for decisions where the Monte Carlo margin is thin (<0.1 strokes): Nantz states the safe play, Gruden argues the hero play, and the shot settles it. (3) **The callback.** The most human thing a commentator does is remember: "That's the third time this week he's missed left on this hole." Implement a callback rule: once per round, when a pattern repeats (same miss direction on the same hole, third straight birdie, second lip-out), the booth names the pattern. It is a database query wearing a human voice.

---

## 3. What makes a sports-game AI opponent feel human

This is the section that matters most, because Mas *is* the opponent — the character the audience watches the way a racing fan watches a Drivatar or a fighting-game player watches a CPU rival. The research is consistent across genres, and it converges on five traits.

### 3.1 Mistakes — the right kind, at the right rate

A perfect opponent is boring; a randomly bad opponent is insulting. What reads as human is **a specific, explicable mistake, at a rate that matches the character's skill**. Forza's Drivatar system learned this the hard way: early Drivatars copied real players' bad habits *too* faithfully and became infamously reckless — the community's "Bowie Knife99" (Forza Horizon 6, 2026) became a villain precisely because it was *too* human, ramming players and defying class ratings. Playground Games had to add overrides to stop Drivatars cutting corners or smashing into racers.

**The rule:** mistakes must be *in character* and *in proportion*. A +3 golfer does not shank; he misses a green by 8 feet, or leaves a 20-footer 2 feet short. The sim already models this correctly — named mishits (thin, chunk, heel, toe) drawn as contact quality first, with rates that match a +3 profile (`sim-engine.md` §4). The broadcast's job is to **name the mistake in physical terms** so the viewer can learn from it, not just see a bad number.

> **What Mas Golfs should steal:** a **"mistake card"** on the lower-third after a poor shot: not just the result, but the mechanism in one line — "Thin strike — ball speed 152, down 9 mph" or "Caught it heavy — came up 12 yards short." And a **mistake memory**: track Mas's most common miss (e.g. "misses left 60% of the time on approaches") and surface it as the ONE FIX line and as a booth callback. A golfer with a *known, named weakness* is a character; a golfer who is generically "good" is a screensaver.

### 3.2 Tendencies — a fingerprint, not a random number

Every great sports-game AI has a **fingerprint**: a set of biases that are stable across matches, so a player can learn them and play against them. In fighting games it is a preferred combo; in racing it is a braking point; in golf it is a shot shape, a club preference, a risk appetite.

Forza's Drivatars are literally this: a behavioral profile built from a real player's braking points, aggression, racing lines, and mistakes, carried under that player's gamertag. The profile *is* the opponent.

**Our version:** Mas's fingerprint is already specified in `self-improvement.md` — aim biases (capped at ±12 ft), a risk threshold, a baseline table, a trajectory preference. These change slowly, one fix per round, and only in response to evidence. That is exactly right, and it is the same design as a Drivatar profile: **a stable identity that evolves, never a random draw**.

> **What Mas Golfs should steal:** **put the fingerprint on screen.** The player card should carry a "Tendencies" block — three lines, updated weekly, in plain language: "Fades the driver · Attacks par 5s · Leaves putts short from 20+ feet." This does three things: it gives new viewers a character in 3 seconds; it gives the booth material ("he's a fader, so that draw on 12 was a surprise"); and it gives the *learning loop* a public face — when a tendency changes after a fix, the card changes, and the audience watches the golfer *learn*. That is the digital-twin story in one graphic. Second steal: **guest twins as Drivatars**. The `guest-twins.md` doc already designs this; the Forza lesson is to carry the guest's *name and fingerprint* on screen the way Drivatars carry a gamertag, so a match against a twin feels like a match against a person.

### 3.3 Pressure behavior — the same golfer, tighter

The most human trait of all: **performance changes under pressure, and it changes in a specific direction**. Real athletes do not become randomly worse — they become *tighter*: shorter backswing, more conservative targets, slower tempo, or the opposite (rushing). In games, the best pressure systems are not a hidden "choke" stat; they are a *visible change in decision-making* — the AI picks safer lines, takes fewer risks, or visibly hesitates.

Our sim's decision engine already has the hook: the hero-shot threshold drops to 0.08 strokes "when record in reach" (`sim-engine.md`), meaning Mas gets *more* aggressive when a record is on the line. That is a defensible design choice — but it is worth asking whether the *human* pattern is the opposite on some holes, and whether the pressure effect should be visible rather than just a threshold number.

> **What Mas Golfs should steal:** a **visible pressure model**. Add two things: (1) a `pressure` value on the round state (0–100), computed from context — strokes under par, holes remaining, 59 Watch status, last-three-holes form — and displayed on the 59 Watch bug (it already shows strokes-affordable and live probability; pressure is the third number). (2) A **tempo tell**: when pressure is high, Mas's pre-shot routine gets *longer* (an extra waggle, a longer look at the target) and the booth notes it ("he's taking his time here — he knows what this putt means"). The routine is already animated; the *duration* is a variable. A viewer who sees the routine stretch believes the moment matters. And when Mas *does* pull off a shot under pressure, that is the clip — the clip pipeline's drama model already scores record-chase moments at 70+; pressure should be an input to that score.

### 3.4 Momentum — form that the audience can feel

In sports games, momentum is the sense that the last few minutes *matter* for the next few minutes — a team on a run plays looser, a player who just missed plays tighter. The research is careful here: in real sports, "hot hand" effects are mostly small or illusory, but in *games*, momentum is a pacing tool — it creates arcs within a match (the comeback, the collapse, the steady grind) that keep a viewer watching.

Our sim is deliberately *anti-momentum* in its physics: each shot is an independent draw from a calibrated distribution, and the self-improvement doc is explicit that form is *derived, never set*. That is the right call for the sim's integrity. But the *broadcast* can and should narrate momentum as a story — because the audience experiences a round as a narrative arc, not as 70 independent samples.

> **What Mas Golfs should steal:** a **form strip on the scorebug** — the last 5 holes as five small dots (birdie gold, par cream, bogey red), always visible. It costs nothing, it is pure event data, and it is how every real broadcast tells the momentum story without saying a word. Second steal: **the booth names the arc** — after three straight birdies, Nantz says "he's got it going now"; after two straight bogeys, Gruden says "he's got to stop the bleeding here." Both lines are already template-able from the event stream. The sim stays honest; the booth tells the truth about what the honest numbers *feel* like.

### 3.5 The personality of the miss — and the celebration

The last trait is the smallest and the most important: **what the character does *after* the shot**. In every sports game that feels alive, the post-shot behavior is where the personality lives — the fist pump, the club twirl, the head drop, the slow walk. Players remember the celebration more than the shot.

> **What Mas Golfs should steal:** the **celebration ladder** — a graded set of reactions indexed by drama, not a single "celebrate" animation. Birdie: a small fist pump and a nod. Eagle: the full pump, the cap tip to the gallery, the smile. Hole-out / ace: everything — the run, the arms up, the gallery roar, the replay at 0.5×. Bogey: the hands on hips, the slow exhale, the look at the club. Double: the head drop, the long walk. The ladder is a lookup table (drama → reaction), the animations are a few keyframes each, and the *grading* is what makes it feel human — a golfer who celebrates a tap-in par like a major win is a cartoon; a golfer whose celebration matches the moment is a person.

---

## 4. ML in games — where it actually ships vs where it is marketing

This section is the honesty check. The games industry has spent a decade announcing AI revolutions; the shipped reality is narrower, and knowing the difference is what keeps a small project from chasing the wrong thing.

### 4.1 Where ML actually ships today

| Area | What ships | Example | Verdict |
|---|---|---|---|
| **Opponent behavior from human data** | Behavioral profiles learned from real players, then run through the game's own physics/controller | Forza Drivatars (since 2005, Bayesian nets → deep learning; cloud profiles) | **Real, and the oldest success.** But note: the *controller* is hand-built; ML supplies the *style*. |
| **Learned opponents under fair physics** | Deep RL agent trained in simulation, deployed as a bounded event | Gran Turismo Sophy (Sony AI + Polyphony) | **Real, but expensive.** Thousands of parallel races in the cloud; a team of PhDs; shipped as a limited event, not a default mode. |
| **NPCs with memory and personality** | Small on-device language models driving character behavior | Krafton inZOI "CPC" (2025, 1M+ copies week one) | **Real, and the most relevant to us.** The key detail: *small on-device models*, not cloud LLMs. |
| **Animation (motion matching)** | Learned selection and blending of motion-capture clips | EA Sports FC HyperMotion, *The Last of Us Part II* | **Real, and ubiquitous.** This is the single most impactful ML-adjacent technique in modern games — and it is mostly search + blending, not a neural net. |
| **Testing, QA, and balance** | Bots that playtest builds, find exploits, and verify balance | Modl.ai and every major studio's internal bots | **Real, and the highest ROI.** The least glamorous, the most used. |
| **Procedural content** | Generated terrain, textures, layouts, quests | *No Man's Sky*, *Hades*' room generation, Ubisoft's procedural world tools | **Real, but hand-tuned.** The generator is authored; ML (if used) tunes parameters, it does not invent the game. |
| **Voice and dialogue at runtime** | LLM-driven NPC conversation with voice | inZOI, a handful of indie experiments | **Real but rare.** The shipped count is small; latency and cost are the binding constraints. |

### 4.2 Where it is mostly marketing

- **"AI NPCs" as a bullet point.** Most demos are a cloud LLM with a prompt and a TTS voice, filmed once, never shipped. The failure modes (hallucination, latency, cost per line, breaking character) are the same ones Inworld ran into — which is why Inworld pivoted to B2B infrastructure.
- **"AI-generated worlds."** No shipped game lets a model invent its world at runtime. What ships is *procedural generation with authored rules* — the rules are the game design, and they are written by humans.
- **"The AI learns and gets smarter forever."** No shipped game does unbounded online learning on a live opponent, because it is untestable: you cannot certify a fair game if the opponent changes every match. What ships is *offline* learning (train, validate, freeze, ship) plus *slow, bounded* adaptation (aim biases within caps — exactly our self-improvement design).
- **"AI commentary" that is just a bigger model.** The systems that work are pipelines (event → template → model for flavor → validation → cache → TTS). A raw LLM narrating live is a demo, not a broadcast — it invents stats, talks over the action, and costs money per word.

### 4.3 What this means for Mas Golfs

Our architecture is already on the right side of every line above, and that is worth stating plainly:

- **Local small model, not cloud LLM** — Qwen3.5-4B on the 8GB Mac, the inZOI pattern, $0/month. Correct.
- **Monte Carlo over real physics, not a learned policy** — the decision engine is *utility AI with a physics simulator*, which is more testable and more honest than a neural policy, and it runs in <5 ms. Correct.
- **Bounded learning, frozen physics** — dispersion σ never changes; only aim biases, risk threshold, and the baseline table move, within caps, one fix per round. This is the shipped-games pattern (offline learning + bounded adaptation), not the marketing pattern (unbounded online learning). Correct.
- **Template + model for commentary, with validation and caching** — the pipeline in `commentary/` is the shipped pattern. Correct.
- **Automated calibration as the QA loop** — the Modl.ai pattern. Correct, and worth making a standing system rather than a one-off (§1.6).

The one place we are *behind* the shipped state of the art is **animation**: motion matching (or its cheap cousin, procedural micro-animation) is the single biggest believability lever we have not yet pulled. That is §2.1, and it is the top-ranked item in §6.

> **What Mas Golfs should steal:** **the honesty itself, as a brand position.** "Every shot is real physics. Every number on screen comes from the event log. The golfer learns slowly, the way a real golfer does." That is a defensible claim that no AI-hype golf product can make, and it is the reason the Road to 59 is credible. Put it on the landing page and in the stream's About panel — not as a disclaimer, but as the premise.

---

## 5. What a small autonomous project on a free budget can actually steal

The constraint is the design: **$0/month, one 8GB MacBook Pro, no paid APIs, no cloud GPU (unless Mason green-lights it), stdlib-only where possible.** The good news is that almost everything in this document survives that constraint, because the best game-AI patterns are *design* patterns, not compute patterns. What costs money is training; what costs nothing is *structuring*.

### 5.1 Free (already have the pieces)

| Pattern | Cost | What it needs |
|---|---|---|
| Utility-AI decision display (show the rejected alternative) | $0 | A line in the lower-third template; data already exists in `shot_decision` events |
| Tendencies card (fingerprint on screen) | $0 | A query over the golfer model; a graphic |
| Form strip (last 5 holes) | $0 | Five dots on the scorebug |
| Mistake card (mechanism, not just result) | $0 | A line in the lower-third; data already exists in `shot_result` |
| Callback lines (booth remembers patterns) | $0 | A query over the event log; a template |
| ONE FIX + memory line on the player card | $0 | Already have ONE FIX; add one memory line |
| Silence budget as a feature | $0 | A rule, not a build |
| Celebration ladder (graded reactions) | $0 | A lookup table + a few keyframes |
| Gallery (30–50 spectators, 3-rule agents) | $0 | Billboard sprites + the propagation rule |
| Anticipation hook (`likely_outcome` event) | $0 | One new event type in the bus; the sim already knows the trajectory |
| Reaction layering (staggered timing) | $0 | A timing table in the director |
| Standing calibration verdict (Modl pattern) | $0 | A cron-style run of the existing harness + a one-line log |
| Ghostwriter barks bank (pre-generated, human-gated) | $0 | One offline generation pass with the local model + a human read |

### 5.2 Cheap (a day or two of build, still $0)

| Pattern | Cost | What it needs |
|---|---|---|
| Procedural micro-animation (head tracking, foot plant, idle sway, walk cycle) | $0, ~1–2 days | Four small math additions to the golfer rig |
| Flag-out moment (flag comes out as the ball approaches) | $0, ~half a day | A flagstick animation triggered by ball proximity (Mason's explicit ask) |
| Pressure value + tempo tell | $0, ~half a day | A `pressure` computation + a routine-duration variable |
| Two-voice disagreement template | $0, ~half a day | One new commentary template for thin Monte Carlo margins |
| Gallery camera cut on drama ≥85 | $0, ~half a day | A director rule + a camera position |
| Guest twins as Drivatars (name + fingerprint on screen) | $0, builds on `guest-twins.md` | A twin card graphic |

### 5.3 Not free, not now (Mason's decision, not a default)

| Pattern | Cost | Why it waits |
|---|---|---|
| Motion-capture shoot of Mason's swing (Xsens/Rokoko, half-day) | $1,500–$4,000 | Priced in `unreal-vertical-slice.md`; authentic, but a real purchase. Video-derived pose estimation from Mason's swing video is the near-$0 alternative, already recommended for the slice. |
| Cloud GPU for a bigger model (Qwen3.8-27B as a teacher for distillation) | ~$0.34/hr rented | Documented in `docs/research/qwen-27b-fit.md` §7; legal under Apache 2.0, and the student stays ~2 GB on the box. A real decision, not a default. |
| Unreal vertical slice (Hole 12) | $49.99 (Ultra Dynamic Sky) + GPU box or cloud | The GTA-quality leap; needs Mason's green light (`unreal-vertical-slice.md`). |
| Paid NPC/voice platforms (Convai, Inworld, ElevenLabs) | $29+/month | Ruled out by the $0/month constraint. We steal their *design* (latency bar, memory + goals, voice consistency), not their service. |

---

## 6. Ranked top 10 — what to build, in order

Ranked by **believability gained per hour of build**, under the free-budget constraint. Each item names the owner doc or file it touches.

### #1 — Procedural micro-animation on the golfer (head tracks ball, feet plant on slope, idle sway, walk cycle)
**Why first:** motion matching is the single most impactful aliveness technique in modern games, and its cheap cousin is four lines of math. The swing is already good; the *between* is what reads as fake. A head that follows the ball through its flight will do more for the stranger test than any terrain upgrade.
**Steal from:** EA SEED / FIFA HyperMotion (motion matching), §2.1.
**Touches:** web build golfer rig; Unreal slice (GASP) later.

### #2 — The celebration ladder + the flag-out moment
**Why second:** the 2-second rule (§2.5) — believability is won in the reaction, and the flag coming out as the ball approaches the hole is Mason's explicit ask. Graded reactions (birdie nod → eagle pump → ace explosion) cost a lookup table and a few keyframes, and they are the moments that become clips.
**Steal from:** Kinetix (the animation long tail), §1.7; sports-game post-shot behavior, §3.5.
**Touches:** web build character rig; clip pipeline drama model (reactions are clip-worthy by construction).

### #3 — The gallery: 30–50 spectators with the 3-rule crowd pattern + a gallery camera cut
**Why third:** a crowd that reacts tells the viewer *other people are watching*, which is what turns a screensaver into an event. The pattern is proven from Houdini/Massive down to football games, and at our scale it is billboard sprites with per-agent delay and personality. The gallery cut on drama ≥85 is the cheapest single camera behavior in this document.
**Steal from:** Houdini Crowds / Massive, football-game crowd systems, §2.4.
**Touches:** web build scene + director; broadcast-stack drama score.

### #4 — Tendencies card + mistake card on air (the fingerprint, visible)
**Why fourth:** a character with a *known, named weakness* is a character. The data already exists (golfer model, shot results); this is a graphic and a line of copy. It also makes the learning loop public — when a tendency changes, the audience watches the golfer learn, which is the digital-twin story.
**Steal from:** Forza Drivatars (behavioral fingerprint as identity), §3.2; §3.1.
**Touches:** player card graphic; lower-third template; `self-improvement.md` surfacing rules.

### #5 — Anticipation hook (`likely_outcome` event) + reaction layering
**Why fifth:** the difference between watching a result and *feeling* a moment is the half-second before it. The sim already knows the trajectory; emitting a hint 0.5–1.0 s early lets the camera, the character, and the gallery lean in before the outcome lands. Reaction layering (body → gallery → booth → graphic, staggered) is free and is what separates a broadcast from a slideshow.
**Steal from:** §2.5 (the 2-second rule, anticipation, layering).
**Touches:** `bus/` event types; director state machine; commentary timing.

### #6 — Utility-AI display: show the rejected alternative + the two-voice disagreement
**Why sixth:** a viewer who sees the choice *and* the road not taken believes there is a mind making the choice. The Monte Carlo scores already exist; showing "lay-up was 0.12 strokes worse" is a line of copy. The Nantz/Gruden disagreement on thin margins (<0.1 strokes) turns a statistical near-tie into booth drama.
**Steal from:** utility AI (§2.2); Sony Sophy's design contract (same physics, decisions explainable in physics terms), §1.3.
**Touches:** lower-third template; `commentary-prompts.md` (one new template).

### #7 — Pressure value + tempo tell + form strip
**Why seventh:** pressure is the most human trait (§3.3), and it is currently invisible. A `pressure` number on the 59 Watch bug, a longer pre-shot routine when pressure is high, and a five-dot form strip on the scorebug together tell the momentum story without a word of commentary. All three are event data + a variable.
**Steal from:** sports-game pressure behavior, §3.3; momentum as narrative, §3.4; *Left 4 Dead*'s AI Director (pacing, not difficulty), §2.3.
**Touches:** round state; 59 Watch bug; scorebug; golfer routine timing.

### #8 — Callback lines + memory line on the player card (the booth remembers)
**Why eighth:** the most human thing a commentator does is remember, and the Nemesis system's genius was that orcs remembered *you*. "Last time on this hole he went long left" is a database query wearing a human voice. One callback per round, one memory line on the card.
**Steal from:** Inworld's memory + goals stack (§1.4); *Shadow of Mordor*'s Nemesis system (§2.2).
**Touches:** `commentary-prompts.md` (callback rule); player card; event-log query.

### #9 — Standing calibration verdict (the Modl.ai playtest loop, as a system)
**Why ninth:** the highest-leverage *engineering* investment, even though it is invisible on air. Every sim change gets an automatic overnight batch against the calibration bands, and a human reads a one-line verdict, not raw numbers. This is how the golfer self-improves without anyone watching — and it is the system that prevents a well-meaning tweak from silently breaking the +3 calibration.
**Steal from:** Modl.ai (§1.6); the existing `sim/calibrate.py` + `qa-plan.md` gate.
**Touches:** `sim/calibrate.py`; a scheduled run (launchd on the broadcast box, or a local script); a verdict log.

### #10 — Ghostwriter barks bank (pre-generated, human-gated ambient reactions)
**Why tenth:** La Forge's Ghostwriter pattern is the cheapest way to get *volume* of voice — 200+ small ambient lines (caddie mutters, gallery gasps, Gruden asides) that nobody has time to hand-author, generated once offline with the local model, gated by a human read, cached, and played at runtime for zero marginal cost. It is last only because it needs the human gate to be real — ungated generated lines are how a broadcast starts inventing things.
**Steal from:** Ubisoft La Forge Ghostwriter (§1.1).
**Touches:** `commentary/` cache (`cache.py`); an offline generation pass; a human review checklist.

---

## 7. What we deliberately do NOT steal

- **Unbounded online learning.** No shipped game does it, because it is untestable. Our bounded version (one fix per round, caps, σ frozen) is the shipped pattern. Do not "improve" it into the marketing pattern.
- **Dynamic difficulty that touches outcomes.** The director shapes the *watching*, never the *golf*. A 59 must be earned by the physics. This is a red line, not a preference.
- **Rubber-banding.** The crude version of DDA that every player detects and hates. There is no rubber band in golf, and there will not be one in Mas Golfs.
- **A raw LLM narrating live.** The commentary pipeline (event → template → model for flavor → validation → cache → TTS) is the shipped pattern. A raw model is a demo.
- **Paid NPC/voice platforms.** We steal their design (latency bar, memory + goals, voice consistency), not their service. The $0/month constraint is a feature: it forced the inZOI architecture (small on-device model), which is the right one.
- **Cloud LLM NPCs for the gallery.** The gallery is 3-rule agents, not 50 language models. Dumb agents, smart crowd — that is the whole lesson of crowd simulation.

---

## Sources

Researched November 12, 2026, via web search. Primary sources preferred where available; third-party roundups used where the primary source is paywalled or undated. Prices and plan details are as reported by the cited roundups and were **not** independently verified against the vendors' pricing pages.

- **Ubisoft La Forge / Ghostwriter:** Ubisoft La Forge research pages; coverage of Ghostwriter (2023) as an LLM drafting tool for NPC barks with human editing as the gate.
- **EA SEED:** EA SEED division pages and research publications (neural animation, procedural content, RL agents for testing); EA Sports FC HyperMotion coverage.
- **Sony AI / Gran Turismo Sophy:** Sony AI and Polyphony Digital publications on Sophy — deep RL, distributed cloud training, fair-physics constraint, limited-time event deployment in GT7.
- **Inworld AI:** company pages and 2025–26 coverage of the pivot from plug-and-play NPC studio to B2B AI infrastructure.
- **Convai:** Convai platform pages and 2026 third-party roundups (free tier 100 interactions/month; Indie $29/month; sub-800 ms conversational latency bar; Unity/Unreal/three.js SDKs). Roundups consulted: index.dev, manus.im, switchtools.io, app.cinevva.com (AI NPCs and Dialogue in Games, July 2026).
- **Modl.ai:** Modl.ai product pages and coverage of AI playtesting / balance verification.
- **Kinetix:** Kinetix platform pages (text/video-to-animation for game characters).
- **Forza Drivatars:** Xbox Wire ("Forza Horizon 2: What's a Drivatar, and Why Should I Care?", Sept 2014); Forza Wiki (Drivatar); AI and Games ("How Forza Rebuilt Their Drivatar AI System", 2026); FH6 community coverage of the "Bowie Knife99" incident (Forza Horizon 6, May–June 2026) and Playground Games' public acknowledgment of Drivatar difficulty inconsistency.
- **NVIDIA ACE:** NVIDIA ACE product pages (lip-sync, facial animation, speech for digital humans).
- **Krafton inZOI / CPC:** Krafton announcements and launch coverage (early access March 28, 2025; 1M+ copies in the first week; on-device small language models for NPCs).
- **Houdini Crowds / Massive:** SideFX Houdini crowd documentation and production case studies (incl. *Game of Thrones* Battle of Winterfell); Musketeers Tech "Rush Hour" case study (50,000 agents, Unity DOTS, personality profiles).
- **Football-game crowd systems:** 2026 coverage of dynamic crowd reactions in football games (individual agents, momentum-driven chanting, stadium audio layering).
- **Behavior trees / utility AI:** standard references — *Halo*/*Horizon* (behavior trees); *The Sims* and *Shadow of Mordor* Nemesis system (utility AI); *Left 4 Dead* AI Director (dynamic pacing); *Resident Evil 4* (invisible DDA).
- **Motion matching:** EA Sports FC HyperMotion coverage; *The Last of Us Part II* animation analysis.
- **ML-in-games reality check:** AI and Games (Tommy Thompson) — the long-running critical survey of what ML actually ships in games vs what is announced; corroborated by the Inworld pivot and the small shipped count of LLM NPCs.

## What could not be verified

- **Exact current headcount and project lists** for La Forge and SEED: both teams publish selectively, and their internal roadmaps are not public. The characterizations above rest on their public research pages and shipped-feature coverage, not on an org chart.
- **Sophy's current deployment status in GT7** (whether the Sophy events are still running, and on what schedule): Sony/Polyphony announce events per season; no standing deployment was confirmed in this pass.
- **Inworld's current product line:** the pivot to B2B infrastructure is reported by multiple 2026 roundups, but Inworld's own current positioning page was not opened in this pass. Treat the pivot as reported, not as confirmed from the vendor.
- **Convai's free-tier interaction count (100/month):** reported by third-party roundups (manus.im, app.cinevva.com), not verified against Convai's live pricing page. Irrelevant to our build (we will not use the service), but stated here for accuracy.
- **"Bowie Knife99" details:** the FH6 Drivatar incident is reported by AI and Games and community wikis as a May–June 2026 event; the 11,000-upvote Reddit figure comes from a single community report and was not independently verified.
- **Kinetix pricing and current feature set:** not verified against a live pricing page; the company is cited for its *concept* (text/video-to-animation long tail), not as a purchase candidate.
- **ElevenLabs' use in specific shipped games:** the company is widely cited as a game-voice supplier; no per-title confirmation was sought, because it does not affect any recommendation here.
