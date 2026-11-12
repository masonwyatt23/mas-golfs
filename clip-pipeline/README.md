# Mas Golfs — Auto-Clip Pipeline

Turns a sim-engine event log into the daily clip queue: detect every
clip-worthy moment, score it with the drama model, assemble post-ready
clip cards, and pick the 1–2 clips Mason posts that evening.

Implements **launch-playbook §1** (auto-clip system: capture → detection
→ assembly → queue) and **broadcast-stack §3.5** (drama-scored replays),
consuming the event schema from **sim-engine §1**. Standard library
only — Python 3.10+, nothing to install.

## The workflow

```
sim engine (JSON events)          OBS replay buffer (60 s, always on)
        │                                   │
        ▼                                   ▼
  clip-pipeline ──drama score──▶ saved replay files
        │                        ~/mas-golfs/clips/round0042-hole12-ace-0086.mp4
        ▼
  clip manifest (JSON)
        │
        ├── queue/    ← Mason approves 1–2 clips each evening (15 min)
        └── library/  ← the rest, for best-ofs and the weekly roundup
```

1. **Capture (OBS, always on).** The replay buffer holds the last 60 s.
   On drama ≥ 60 the director saves it to `~/mas-golfs/clips/` with a
   filename encoding the moment (`round0042-hole12-hole_out-0086.mp4`).
2. **Detection (this tool).** Every shot is scored the moment it lands.
3. **Assembly (this tool).** Each saved moment becomes a clip card:
   20–35 s, result first (hook 0–2 s), decision line, swing + tracer,
   0.5× slow-mo of the last 3 s when drama ≥ 75, payoff card last.
4. **Queue (this tool + Mason).** Ranked by drama. Best clip first; a
   second only when it scored 90+. One clip per hole unless 90+ (a
   hole-out earns a second look). Mason approves, posts Reels → Shorts
   → TikTok, same day, within an hour.

## Quick start

```bash
cd clip-pipeline
python demo.py            # full run on the sample round (R0042, shoots 59)
python -m unittest discover -s tests -v
```

The demo regenerates the sample event log, scores it, and prints the
queue. Expected result: 13 moments detected, 13 clips saved, queue of 2
— the hole-in-one at The Picture (100) and the birdie that completes the
59 (100).

## CLI

```bash
# Score any event log (JSONL, sim-engine §1 schema)
python -m clip_pipeline.cli --input sample_data/round_R0042_events.jsonl \
    --output output/manifest.json

# Regenerate the deterministic sample log
python -m clip_pipeline.cli --generate-sample sample_data/round_R0042_events.jsonl

# Use it as a library
python - <<'EOF'
from clip_pipeline import load_events, run_pipeline
events = load_events("sample_data/round_R0042_events.jsonl")
moments, clips, queue, manifest = run_pipeline(events)
for clip in queue:
    print(clip.drama, clip.title)
EOF
```

## The drama model

| Moment | Drama | Rule |
|---|---|---|
| Hole-out (ace, chip-in, holed bunker shot) | 100 | Ball holed from off the green |
| Road to 59 (round ends at 59 or better) | 100 | Hole 18, score ≤ −13 |
| Eagle | 95 | Hole completed 2 under par |
| Near-miss | 85 | Shot/putt finishing ≤ 6 in (0.5 ft) without dropping |
| Great recovery | 80 | Par or better after trouble (up-and-down / sand save, or trouble lie → GIR) |
| Best decision | 75 | Risky (≥ 0.25) strategic choice, well executed (quality ≥ 0.8), paid off |
| Worst miss | 75 | Named mishit (thin/chunk/toe/heel/shank) with a bad outcome |
| Streak | 70 | 3rd consecutive birdie (or better) |
| Record-chase | 70 | On 59 pace (`score_vs_target` ≤ 2) and 9+ under, nothing else fired that hole |
| Birdie | 60 | Only the round's first, or one breaking a 5+ hole drought |

- **Replay-save threshold: 60.** Below 60 a moment is routine and is not
  saved (broadcast-stack §3.5).
- **Record-chase boost: +10** (cap 100) for any moment on a hole where
  Mas is on 59 pace and 9+ under par.
- **One moment per shot** (the highest-drama rule that fires wins);
  milestone events dedupe against moments already detected.
- A bunker splash that still ends in bogey is **not** a recovery — the
  hole-level rule requires par or better.
- The sim's own `drama` field (0–1) is carried in the moment context
  for tie-breaking and debugging; the pipeline's score is authoritative.

## What a clip card contains

```json
{
  "clip_id": "R0042-H12-hole_out",
  "moment_type": "hole_out", "format": "Best shot", "drama": 100,
  "duration_s": 35,
  "source": {
    "replay_file": "round0042-hole12-hole_out-0086.mp4",
    "in_s": 25, "out_s": 60, "replay_buffer_s": 60
  },
  "slow_motion": true,
  "segments": [
    {"name": "hook", "start_s": 0, "end_s": 2,
     "source_start_s": 58, "source_end_s": 60, "speed": 1.0,
     "on_screen_text": "HOLE IN ONE."},
    {"name": "context", "start_s": 2, "end_s": 6, "...": "..."},
    {"name": "shot", "start_s": 6, "end_s": 32, "...": "..."},
    {"name": "shot_slow_motion", "start_s": 29, "end_s": 32, "speed": 0.5, "...": "..."},
    {"name": "payoff", "start_s": 32, "end_s": 35, "...": "..."}
  ],
  "hook_line": "HOLE IN ONE.",
  "title": "Ace at The Picture — 8-iron from 164 yards.",
  "caption": "It's in! Hole-in-one at The Picture! Mas is 10 under par through 12 ...",
  "first_comment": "Full round live now — link in bio.",
  "platforms": {
    "shorts": {"platform": "YouTube Shorts", "aspect": "9:16",
               "resolution": "1080x1920", "target_length": "20-45 s (sweet spot ~30 s)",
               "captions": "Burned in, large, top-third safe",
               "cta": "Full round live now — link in bio",
               "hashtags": ["#golf", "#golftok", "#masgolfs", "#roadto59", "#shottracer"],
               "posting_window": "12:00-2:00pm ET and 7:00-9:00pm ET"},
    "reels":  {"platform": "Instagram Reels", "...": "..."},
    "tiktok": {"platform": "TikTok", "...": "..."}
  }
}
```

In/out points are offsets into the 60 s replay file: the clip uses the
last `duration_s` seconds, and the segments re-order source ranges so
the payoff is the first frame. An editor (or a future ffmpeg step) cuts
`[in_s, out_s]` from the replay file and assembles the segments.

## The manifest

`output/manifest_R0042.json` has four sections:

- `queue` — the 1–2 clips for tonight, ranked. This is what Mason
  approves in the 15-minute evening workflow.
- `library` — every saved clip (drama ≥ 60), ranked. Best-of
  compilations and the Friday weekly roundup draw from here.
- `not_saved` — moments below the threshold, for tuning the model.
- `summary` — counts, top drama, round score and Road to 59 status.

## The sample round (R0042)

`sample_data/round_R0042_events.jsonl` — 137 events, one full round,
deterministic (seed 42). Mas shoots **59** at Wyatt National. It
exercises every rule, including the negative cases:

- H1 birdie scores 60 (first of the round); the H6 birdie scores
  nothing (not first, no 5+ drought).
- H5 has both a worst miss (chunked drive, 75) and a recovery
  (up-and-down par, 80) — two moments, one hole; the queue takes one.
- H14's bunker splash scores nothing — it ends in bogey.
- H11's pitch is a green in regulation on the par 5, not a recovery;
  only the 3-birdie streak scores.
- H13/H15/H16/H17 fire record-chase moments (on pace, 9+ under);
  H18 fires Road to 59.

Regenerate it any time: `python -m clip_pipeline.cli --generate-sample sample_data/round_R0042_events.jsonl`
— same seed, same bytes.

## Layout

```
clip-pipeline/
├── README.md
├── requirements.txt          # stdlib only — nothing to install
├── demo.py                   # runnable demo (generates log, runs pipeline, prints queue)
├── clip_pipeline/
│   ├── __init__.py           # public API
│   ├── course.py             # Wyatt National data (par, names, 59-pace math)
│   ├── events.py             # JSONL loading + §1.1 envelope validation
│   ├── scoring.py            # the drama model
│   ├── assembly.py           # clip cards: segments, hooks, titles, platform variants
│   ├── manifest.py           # daily-queue selection + manifest output
│   ├── sample_log.py         # deterministic R0042 generator
│   └── cli.py                # argparse CLI
├── sample_data/
│   └── round_R0042_events.jsonl
├── output/
│   ├── manifest_R0042.json   # demo output (full manifest)
│   └── queue_R0042.json      # demo output (tonight's queue only)
└── tests/
    └── test_pipeline.py      # 30 tests (unittest, no dependencies)
```

## Extending it

- **New moment types:** add a rule in `scoring.py` (`_score_shot` /
  `_score_hole` / `_score_milestone`) and a hook/title branch in
  `assembly.py` (`_hook_and_title`) plus a format in `FORMAT_BY_MOMENT`.
- **New platforms:** add an entry to `PLATFORM_SPECS` in `assembly.py`.
- **Tuning thresholds:** the constants at the top of `scoring.py`
  (`REPLAY_SAVE_THRESHOLD`, `SECOND_LOOK_THRESHOLD`, `ON_PACE_THRESHOLD`,
  `RECORD_CHASE_MIN_SCORE`, `NEAR_MISS_FT`) and `SLOW_MOTION_THRESHOLD`
  in `assembly.py`.
- **Real logs:** point the CLI at a real sim-engine JSONL export. The
  pipeline is stateless per round — run it once per completed round, or
  stream events through `score_round` for a live queue.
- **ffmpeg assembly (next step, not built here):** cut
  `source.in_s`–`source.out_s` from the replay file, reorder per
  `segments`, burn in captions, crop to 9:16, export the three platform
  variants. The manifest already carries everything that step needs.

## Rules the copy follows

- Never name a specific AshlrAI client company in clip copy. (There are
  none in this project — the rule is enforced by construction: titles and
  captions are built only from course, shot, and score data.)
- Clubhouse Coins stay closed-loop play money; nothing in this tool
  touches money, odds, or payouts — it only detects and packages moments.
