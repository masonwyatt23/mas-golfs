# Mas Golfs — Cinematic Direction (Godot Broadcast Slice)

**Status:** direction only, no code. Written Nov 13, 2026.
**For:** the Godot 4.7 Mac-native build, Hole 12 "The Picture" slice.
**Companion docs:** `docs/mac-native-broadcast.md` (the design — engine,
budgets, build order), `docs/broadcast-stack.md` (director rules, NodeCG
overlays), `docs/brand-identity.md` (palette, type, scorebug). This doc is
the *look*; those docs are the *machine*. If they disagree, the design wins
— this doc never overrides a budget, a bus contract, or a frame-rate gate.
**Constraint:** $0, no new dependencies, no changes to the sim. The sim stays
authoritative; the renderer is a dumb visualizer over `ws://localhost:4456`.

---

## 1. The visual bar — what the first 3 seconds must feel like

A viewer opens the stream on their phone, mid-scroll, and in three seconds
must feel: *this is a real golf broadcast, and it is beautiful*. Not a game
menu, not a cartoon, not a tech demo. The reference look is **a real golf
broadcast (CBS/NBC Sunday coverage) crossed with a filmic game cinematic**
— the long-lens compression of a Tour telecast, the golden light and haze of
a prestige game trailer. Calm, expensive, quiet enough that the golf can
supply the drama.

In the first 3 seconds the viewer should see:

- **A golfer, from behind, at address** — a real human silhouette, tour
  proportions, still and set, with the hole falling away in front of him.
- **A real place** — terrain that rolls, a pond catching the sun, trees with
  volume at the edges of frame, a green that reads as a green, not a disc.
- **Light with direction** — long shadows, warm highlights, cool shade. If
  the light looks flat, nothing else in the frame will save it.
- **One clean frame** — the world fills the screen; the only 2D on it is the
  slim scorebug (NodeCG, top-left) and the ticker (bottom). No clutter, no
  HUD, no menus. The picture is the show.

**The anti-bar:** the web build's current captures — faceted low-poly
canopies, a smooth conical ridge, a flat uniform fairway, a small distant
golfer. If a frame from the slice could be mistaken for one of those
captures, the slice is not done. The test is always the phone, never the
editor viewport.

---

## 2. Camera language — the shot list for a hole

The director rules in `docs/broadcast-stack.md` §3 still govern (cut on
events, never mid-flight, minimum 2–3 s holds). This section is *how each
shot should look* inside those rules.

### Shot list (Hole 12, 164 yd, par 3, pond in front of the green)

| Beat | Camera | What the viewer sees |
|------|--------|----------------------|
| **Address** | Behind the golfer, low, slightly to his left (he is left-handed — the camera sits over his right shoulder so club, ball, and hole are all in frame) | The golfer at address, the tee, the pond, the kidney green beyond. The hole must be visible *in the same frame* as the golfer — that is the whole point of the behind-the-golfer rule. |
| **Swing** | Same camera, **no cut, no move** | The swing plays in one held shot. The camera breathes (a hair of handheld drift) but does not pan, push, or cut. The viewer watches the swing the way a Tour viewer watches a swing: still, then it happens. |
| **Ball flight** | Cut to the tracer camera on `strike` (the single allowed fast cut) — a high, slightly trailing tracking shot that keeps ball and green in frame | The ball rises against the sky, the tracer draws its arc (Tracer gold `#FFD34D`), the live distance counter ticks. The green stays in frame so the viewer always knows where the ball is going. |
| **Landing / roll-out** | Tracer camera holds, then eases to a lower green-side angle on `landing` | The ball lands, bounces once, rolls out. The roll is the payoff — hold 2–3 s to see where it stops. Do not cut away the instant it lands. |
| **Green approach / chip** | Low green-side camera, near the pin | The green's slope is visible — the viewer should be able to *see* why the putt breaks. Pin, ball, and cup in one frame. |
| **Putt** | Low, behind the ball, on the putt line | The predicted path (from `putt_read`) is drawn on the green; the ball rolls along the actual path (from `putt_result`) at real putt speed. The predicted line fades as the real line draws — read vs. reality, on screen. Hold through the roll; never cut mid-putt. |
| **Between holes** | Aerial flyover (3 s, mandatory) | The next hole from above, hole card on screen. The viewer needs the reset. Never cut straight from a hole-out to the next tee shot. |

### Camera rules (hard)

- **Always behind the golfer.** Never face-on, side-on, or anywhere the
  golfer would see the camera. The viewer stands where a caddie stands.
- **Never so zoomed on mobile that you can't see the shot.** Golfer, ball,
  and target must all fit a phone frame at once. Telephoto compression is
  good (it pulls the background trees against the player, like a Tour long
  lens); losing the hole is not. If the golfer fills the frame, pull back.
- **Smooth eased moves, always.** Every move accelerates and decelerates
  (damping 0.6–0.9, per the broadcast-stack camera API). No linear slides,
  no snap-to, no whip pans. A move should feel like a fluid-head tripod.
- **No cuts mid-swing, mid-flight, or mid-putt.** The only fast cut is
  address → tracer on `strike`. Everything else waits for an event
  boundary (`landing`, `hole_end`, `hole_start`).
- **One camera position per phase.** The position only changes on an event
  boundary; the render interpolates smoothly between positions.
- **Micro-shake, not shaky-cam.** Handheld drift of 0.1–0.2 — enough to
  feel human, never enough to read as unstable. The shake dies to zero
  during the swing itself; address and swing are the steadiest shots.
- **Focal lengths are fixed per position.** Tee cam narrow (telephoto),
  aerial wide. FOV lives in the render config, not in the director's head.
  Do not zoom to fix a framing problem — reposition instead.

---

## 3. Lighting and atmosphere

**Time of day: golden hour, always.** It matches Mason's swing video (the
swing anchor, shot at golden hour), and it is the most forgiving light for
a game renderer — long shadows hide low-poly sins, warm highlights sell the
grass, and a low sun gives the pond something to reflect. The slice is
judged in golden hour; other times of day are a later problem.

- **Sun:** one directional light, low in the west (tee on the west rim,
  green on the east bench — the sun sits behind the camera at address,
  raking across the hole toward the green). Warm key (~3500–4000 K feel),
  long shadows, shadow distance ~150 m, soft shadows on. Shadows are what
  make terrain read as terrain: a flat-lit hill is a ramp; a shadowed hill
  is a hill.
- **Sky:** Godot `ProceduralSkyMaterial` + sun + a custom cloud shader.
  The sky needs gradient and texture — pale horizon warming to gold near
  the sun, deepening blue overhead, a few slow clouds. A flat blue sky is
  the fastest way to make the whole frame read as a game.
- **Fog:** volumetric fog (Forward+) at low density, plus standard distance
  fog. It gives the valley depth (far rim softens, near grass stays sharp)
  and hides the far edge of the world. It should read as *air*, not a grey
  wash — thin enough that the green is crisp at 164 yd.
- **Grass in the light:** fairway catches the sun as a broad warm sheen
  with cross-hatched mow stripes (alternating light/dark bands — the web
  build proved stripes read at broadcast distance). Rough is darker and
  cooler. The green is the brightest, smoothest surface in frame — it
  should glow slightly, the way a real green glows at golden hour.
- **Sand:** warm, almost white in direct sun, with a soft shadowed lip on
  the far side. Never flat beige — it needs the lip shadow and a hint of
  texture (raked lines close, noise at distance).
- **Water:** the pond is the single most visible "is this real" cue on Hole
  12. Normal-scrolled surface, fresnel (sky reflection at grazing angles,
  dark depth straight down), a reflection probe, subtle ripple driven by
  the wind value in `conditions`. The pond must *move* — a still pond is a
  mirror, and a mirror is a texture, not water. The sun should throw a
  glitter path across it at golden hour.
- **Global illumination:** baked LightmapGI for the static course (free at
  runtime). The bake makes shade under trees feel cool instead of grey and
  keeps the green from blowing out in direct sun. SDFGI is the fallback —
  never no GI.

---

## 4. Color — the filmic grade

The raw Godot render is the *negative*; the grade is the *print*. These
targets are for the render pipeline (tonemapping, color correction in the
Godot environment), not the NodeCG overlays — the overlays already have
their own design system (`docs/brand-identity.md`).

- **Tonemap:** filmic (ACES-style) — never linear, never Reinhard-flat.
  Hold the highlights (sun glitter on the pond, the bright green) without
  clipping to white, and lift the shadows (under trees, the bunker's far
  lip) without crushing to black. If the brightest grass and the darkest
  shade are both readable in one frame, the tonemap is right.
- **Contrast:** push gently — a slight S-curve. The web build's flat look
  came partly from low contrast; the slice needs mow stripes, bunker lips,
  and tree shade to separate. Do not crush: a golf course at golden hour is
  high-key, not a noir frame.
- **Saturation:** pull the greens *down* slightly from the raw render and
  push the warms (gold light, sand, skin) *up* slightly. Raw game grass is
  usually too saturated and too uniform — real grass at golden hour is
  warm-olive, not kelly green. The green (putting surface) stays the most
  saturated green in frame; rough goes olive; trees go deep and cool.
- **Warmth:** overall warm bias in the highlights (golden hour), neutral
  to cool in the shadows. The frame should feel like late afternoon, not
  noon and not dusk.
- **Vignette:** very light — a subtle darkening at the corners to focus the
  eye, the kind a broadcast lens has naturally. If you can *see* the
  vignette, it is too strong.

### How the gold accents sit in the grade

- **Scorebug / 59 Watch gold (`#C9A227`):** the overlays are NodeCG, not
  the 3D grade — they sit *on top* of the picture, unaffected by the
  tonemap. The rule is restraint: gold is the highlight, never the field
  (`docs/brand-identity.md` §9). The 59 Watch pulsing gold bug must read
  against the graded picture without shouting — if the picture is warm and
  golden, the bug needs its dark-green (`#0B3D2E`) field behind it to
  separate. Never let the bug's gold sit directly on sunlit green.
- **Tracer gold (`#FFD34D`):** brighter than brand gold by design, so it
  reads over any terrain. The tracer is the one element allowed to be
  louder than the picture — it is data, not decoration. Keep it thin (a
  line, not a ribbon) and let it fade after `landing`; a tracer that
  lingers is clutter.
- **Flag:** the pin flag is the one in-world gold accent. When 59 Watch is
  on, the flag may carry a subtle gold tint (renderer state, from the
  event — never invented). The tint must be *subtle*: a viewer who is not
  looking for it should not notice it; a viewer who is should feel the
  stakes rise.

---

## 5. Terrain and course furniture — what makes Hole 12 a real place

Hole 12 is 164 yd, 20 ft downhill, pond fronting a 28-yd-wide kidney green
(`docs/course-design-v2.md` §12). The slice is judged on whether that hole
reads as a place you could walk. Each element below is a pass/fail cue.

- **Real LiDAR terrain, not sculpted hills.** The heightmap is real USGS
  1 m LiDAR (505×505, 16-bit, 39.58 m relief — design doc §5.2). The valley
  runs NW–SE; rims high west and east; channel low in the middle. The
  terrain must *keep* that structure — if the import flattens the valley
  or rounds the rims, the hole stops being Hole 12. Verify against the
  hillshade preview before any golf-feature work.
- **The tee is 6 m above the green.** That 20-ft drop is the hole's
  identity — the camera at address looks *down* the hole; the green sits
  below, the pond between. If tee and green read as the same height, the
  terrain import is wrong.
- **Shaped bunkers, not craters.** Two bunkers cut into the terrain with a
  real lip — a raised sand edge the ball can catch, not a flat sand decal.
  The bunker faces the tee (the viewer sees sand, not grass, from
  address). Sand texture: raked lines, warm in sun, shadowed lip.
- **Sloped, contoured greens — the solver's green.** The green mesh comes
  from `sim/greens.py` heightfields (design doc §5.3): the rendered green
  *is* the putting solver's green, not a lookalike. The slope must be
  visible from the green-side camera — the viewer should be able to see
  why the putt breaks. A flat green is a fail, however pretty the rest of
  the frame is.
- **Rounded fairway edges.** Fairway meets rough in a soft, irregular edge
  — mow stripes fading into longer grass — never a hard line, never a
  perfect rectangle. The edge should look grown, not drawn.
- **Trees with volume, not cones.** Trees are the known weakest element
  (design doc §8.5) and the rule is: keep the camera at broadcast
  distance, where instanced trees with wind sway and real shadows read as
  a tree line. No tree close-ups, ever — a close-up is where the illusion
  dies. Canopy must have *volume* (layered foliage, light passing through
  in patches), not a solid cone or a billboard.
- **Water that moves.** See §3 — the pond ripples with the wind value from
  `conditions`. A still pond is a fail.
- **Course furniture, sparingly.** A tee sign with hole name/par/yardage,
  a bench, a ball washer, 150-yd stakes — the small things that say "golf
  course" without saying "theme park." One or two pieces per hole, placed
  where a real course would put them, never in the line of play, never in
  the camera's way. The web build's per-hole furniture proved the point;
  the Godot slice keeps the idea and drops anything that reads as a prop.

---

## 6. The golfer and the swing — what "way better" means

Mason's complaint, three times: the golfer and the swing need to be "way
way better." Here is what that means, concretely, for the slice.

- **Tour-proportioned character.** Not a mascot, not a mannequin. Real
  proportions (shoulder width, leg length, arm hang), a left-handed setup
  (the character is a lefty, matching Mas), a stance that reads as a
  golfer's stance — knees flexed, spine tilted, eyes over the ball. The
  character is Mixamo/MakeHuman quality (design doc §5.4): good, not
  photoreal. The goal is a believable golfer at broadcast distance, not a
  close-up portrait.
- **Swing timing from Mason's real swing.** The swing is video-derived
  (MediaPipe Pose from Mason's swing video, retargeted in Blender — design
  doc §5.4). The timing is the thing: 1.6 s total, hip-lead, lag peak,
  shaft flex — the sequence a real swing has and a keyframed swing does
  not. If the swing *feels* like Mason's swing, it is right; if it feels
  like a robot waving a stick, it is wrong, however smooth the frames are.
  Judge the swing on a phone, the way Mason judges the web build.
- **The swing is the hero moment.** Everything in the frame serves it: the
  camera holds still, the overlays stay quiet, queued commentary waits.
  The swing gets the frame's full attention for 1.6 s. The ball flight is
  the payoff; the swing is the moment.
- **Cloth and hair that don't look plastic.** Shirt and trousers with
  fabric-appropriate roughness (no specular shine on cotton), a cap or
  visor that sits on the head instead of floating above it, hair with a
  matte texture rather than a helmet sheen. The outfit need not match the
  swing video (outfits are customizable) — but it must not look like
  molded plastic. Roughness maps do more work here than polygon count.
- **Feet stay planted.** Foot slide is the fastest tell of a bad retarget.
  The feet plant at address and stay planted through impact; the weight
  shifts, the feet do not glide. If the feet slide, the swing fails the eye
  test regardless of everything else.
- **Scale is honest.** The golfer must be the right size against the hole:
  at address, the golfer is a real person on a real tee, and the green
  164 yd away is small but visible. The web build's failure was partly a
  scale failure (a small distant figure on a flat fairway). The slice must
  keep the golfer large enough to read as a person and the hole large
  enough to read as a hole — a camera framing job (§2), not a
  character-size job.
- **No face close-ups.** The character's face is not the point and will not
  survive one. The camera stays behind the golfer, at broadcast distance,
  for a reason. The swing is judged from behind, like every swing on TV.

---

## 7. What to measure on real footage — the eye test

The slice is green only when all of §5.5 of the design doc holds, judged
from a recorded 1080p60 clip watched on a phone. This is the checklist for
that viewing. Watch the clip once straight through, then check each item.
**If any item fails, the slice fails — fix the item, do not argue the
checklist.**

### The phone eye-test checklist

- [ ] **First 3 seconds:** the frame reads as a golf broadcast, not a game.
  A stranger could tell you what sport this is and that it is beautiful.
- [ ] **The hole is in the same frame as the golfer at address.** Tee,
  pond, green, pin — all visible, none cropped.
- [ ] **The 20-ft drop reads.** You can feel the green sitting below the tee.
- [ ] **The pond moves and reflects.** Ripple visible, sun glitter on the
  water, not a flat blue shape.
- [ ] **The green reads as a green.** Bright, smooth, contoured — and the
  slope is visible from the green-side camera.
- [ ] **The bunkers have lips.** Sand with a shadowed edge, facing the tee.
- [ ] **The trees have volume.** No cones, no billboards, no flat
  silhouettes at broadcast distance.
- [ ] **The swing reads as a real swing on a phone.** Timing, sequence,
  held finish. Feet planted.
- [ ] **The ball flight matches the sim's carry within 5 yd.** Tracer +
  live distance counter visible and legible on a phone.
- [ ] **The putt read vs. reality is visible.** Predicted path drawn,
  actual path drawn, the difference obvious.
- [ ] **No cut mid-swing, mid-flight, or mid-putt.** Only the address →
  tracer cut on `strike`.
- [ ] **The frame is clean.** Scorebug top-left, ticker bottom, nothing
  else. No HUD, no menus, no debug text.
- [ ] **The gold sits right.** Scorebug/59 Watch gold reads against the
  picture without clashing; the tracer is legible over every terrain.
- [ ] **60fps locked for the full hole on the actual 8GB box.** No stutter
  during the swing or the flight.
- [ ] **Memory total under 7.0GB** for the full hole.
- [ ] **Mason says it looks good.** His call, not the builder's.

### The honest ceiling

**Godot on this Mac delivers ~60–70% of the GTA/2K bar.** That is the
design doc's number (§1.2) and this doc repeats it because it is the frame
the whole slice is judged in:

- What the slice *can* deliver: real PBR materials, real light and shadow,
  baked GI, volumetric fog, real LiDAR terrain, a rigged golfer with a
  video-derived swing, water that moves, a green that is the solver's
  green. At broadcast distance, on a phone, that reads as a good modern
  game — a large, visible step from the web build.
- What it *cannot* deliver: Nanite-grade geometry, Lumen-grade real-time
  GI, Megascans-grade photoreal assets, a MetaHuman golfer. Close-ups of
  trees and the golfer will still read as "game," not footage. That is not
  a failure of the slice — it is the ceiling of the hardware.
- **The last ~30% is a hardware gap (GPU box + Unreal), not an effort
  gap.** No amount of additional polish on this box closes it. This doc
  does not promise more than that, and the slice must not be judged against
  a bar it was never going to reach. It is judged against the web build
  (the thing it replaces) and against the checklist above (the thing it
  must do).

If the slice passes the checklist, it is green — and the 18-hole build
proceeds from it. If it fails the checklist, the fallback is Unity URP
(design doc §1.1 rank 2), not more effort on a failing Godot scene, and
not UE on this box.

---

*Direction only. No code was written for this document. No files were
changed except this one. The 16GB MacBook Air was not touched.*
