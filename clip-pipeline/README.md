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
4. **ffmpeg assembly (this tool, `clip_pipeline/assemble.py`).** The
   queue's clip cards become finished 9:16 videos, ready to post.
5. **Queue (this tool + Mason).** Ranked by drama. Best clip first; a
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

# Assemble the daily queue from a manifest (ffmpeg — see below)
python -m clip_pipeline.cli --assemble output/manifest.json \
    --recordings ~/mas-golfs/clips --clips-out output/clips

# Same thing as a standalone module
python -m clip_pipeline.assemble --manifest output/manifest.json \
    --recordings ~/mas-golfs/clips --out output/clips

# Assemble the whole library instead of just the queue
python -m clip_pipeline.cli --assemble output/manifest.json --all-clips

# See the ffmpeg commands without running them
python -m clip_pipeline.assemble --manifest output/manifest.json --dry-run

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

## ffmpeg assembly

The only non-stdlib dependency in this pipeline. Install it once on
the machine that assembles clips (the broadcast box):

```bash
brew install ffmpeg        # macOS (the 8GB MacBook Pro)
sudo apt install ffmpeg    # Ubuntu/Debian
```

`assemble.py` shells out to the `ffmpeg` binary (and `ffprobe`, which
ships with it) — there is no Python ffmpeg binding to install. If the
binary is missing, assembly fails fast with a clear error; nothing is
half-written.

What one ffmpeg call does per clip:

```
replay file (60 s, 1920x1080)
  ├─ cut each segment [source_start_s, source_end_s) from the manifest
  ├─ 0.5x slow-mo for drama >= 75 (setpts=2.0*PTS video, atempo=0.5 audio)
  ├─ burn in the hook line + on-screen caption text (drawtext, top-third)
  ├─ scale + center-crop to 9:16, 1080x1920, 30 fps
  └─ concat in manifest order (hook first = payoff first, payoff last)
     → libx264 (veryfast, CRF 20) + AAC 128k, +faststart
```

Output: one finished `.mp4` per clip, keeping the replay file's name
(`round0042-hole12-hole_out-0086.mp4`), plus a `.txt` sidecar with the
title, caption, first comment, and per-platform hashtags/CTA/posting
window — the post copy, ready to paste. All three platform variants
are the same 9:16 1080x1920 video (per the manifest, they differ only in
post copy); there is one master file per clip, never three renders.

Segment timing rule (read this before editing `assembly.py`): the
manifest's segment table is a spec sketch and two of its rows overlap
(the shot segment declares 28 s of source for a 26 s output slot, and
the slow-mo segment sits inside the shot's span). The assembler treats
the output timeline as authoritative — each segment fills its
`[start_s, end_s)` slot, and where slots overlap the earlier segment
is truncated at the next segment's start, so the shot's full-speed
portion ends where the slow-mo replay begins and the finished clip is
exactly `duration_s` long (verified: 35 s, not the 38 s an untruncated
concatenation produces). A segment consumes `slot * speed` seconds of
source: at 0.5x the slow-mo segment plays the first half of its
declared range at half speed. See `assemble.py`'s docstring.

Missing input is a skip, never a crash: if a clip's replay file is not
in the recordings dir (OBS didn't save it, or it was already moved),
that clip is logged `skipped` in `assembly_report.json` and the rest of
the queue still assembles. An ffmpeg failure is logged `failed` with
ffmpeg's stderr. The CLI exits non-zero only if a clip *failed*
(skips do not fail the run).

### The daily queue, end to end

```bash
cd clip-pipeline
# 1. Score the round's event log -> manifest (queue of 1-2 clips)
python -m clip_pipeline.cli --input <round-events>.jsonl --output output/manifest.json
# 2. Assemble the queue -> finished clips (needs ~/mas-golfs/clips recordings)
python -m clip_pipeline.cli --assemble output/manifest.json \
    --recordings ~/mas-golfs/clips --clips-out output/clips
# 3. Mason approves in output/clips/ (video + .txt sidecar per clip),
#    posts Reels -> Shorts -> TikTok. 15 minutes, same evening.
```

On the broadcast box this is one cron/launchd line after the round
completes (the runbook's Sunday review owns the schedule — the tool
itself is stateless per round).

### Verifying with a real ffmpeg run

The unit tests mock subprocess and never invoke ffmpeg. To verify the
real thing, generate two synthetic 60 s replay files and assemble the
sample manifest:

```bash
for f in round0042-hole12-hole_out-0086 round0042-hole18-road_to_59-0136; do
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i testsrc=size=1920x1080:rate=60:duration=60 \
    -f lavfi -i sine=frequency=440:duration=60 -shortest \
    -c:v libx264 -preset veryfast -c:a aac /tmp/replay/$f.mp4
done
python -m clip_pipeline.assemble --manifest output/manifest_R0042.json \
    --recordings /tmp/replay --out /tmp/clips-out
ffprobe -v error -show_entries format=duration \
    -show_entries stream=codec_type,width,height \
    /tmp/clips-out/round0042-hole12-hole_out-0086.mp4
# Expect: two 1080x1920 clips, 35 s each, video + audio streams.
```

### Known limitations

- **Caption font:** drawtext needs a bold font file. `assemble.py`
  looks for DejaVu Sans Bold (Linux) or Arial Bold / Helvetica (macOS);
  override with `MAS_GOLFS_FONT=/path/to/font.ttf`. If no font is found,
  the clip still assembles — without burned-in text — and the run
  prints a warning to stderr.
- **Center crop:** the 16:9 → 9:16 crop is centered. A tracer that runs
  to the frame edge can be cropped out; a ball-tracking smart crop is
  future work.
- **No audio bed is mixed in:** the replay file's own audio is kept
  (slowed with the video on slow-mo segments). The ambient bed / impact
  sound from the playbook is not yet mixed — the posting step owns it.
- **Slow-mo consumes half its declared source range** (see the timing
  rule above) — the tail of the slow-mo range is dropped, not stretched.

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
│   ├── assemble.py           # ffmpeg assembly: cut + slow-mo + captions -> 9:16 video
│   ├── manifest.py           # daily-queue selection + manifest output
│   ├── sample_log.py         # deterministic R0042 generator
│   └── cli.py                # argparse CLI (score, assemble, generate-sample)
├── sample_data/
│   └── round_R0042_events.jsonl
├── output/
│   ├── manifest_R0042.json   # demo output (full manifest)
│   ├── queue_R0042.json      # demo output (tonight's queue only)
│   └── clips/                # assemble.py output (video + .txt sidecar per clip)
└── tests/
    ├── test_pipeline.py      # 30 tests (unittest, no dependencies)
    └── test_assemble.py      # 26 tests (ffmpeg command construction, mocked subprocess)
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
- **ffmpeg assembly:** built — see `assemble.py` and the "ffmpeg
  assembly" section above.

## Rules the copy follows

- Never name a specific AshlrAI client company in clip copy. (There are
  none in this project — the rule is enforced by construction: titles and
  captions are built only from course, shot, and score data.)
- Clubhouse Coins stay closed-loop play money; nothing in this tool
  touches money, odds, or payouts — it only detects and packages moments.
