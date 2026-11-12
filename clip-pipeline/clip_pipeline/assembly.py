"""Clip assembly — turning a scored moment into a post-ready clip card.

Implements docs/launch-playbook.md §1.1 Stage 3 (assembly) and §1.2
(platform specs):

Structure (20-35 s, result first):
    Hook     0-2 s   the payoff — ball dropping, tracer's final feet,
                     scorebug changing. No intro, no logo sting.
    Context  2-6 s   the decision in one line of text + the shot-data strip
                     (club, distance, ball speed, carry).
    Shot     6-(D-3) s  swing and ball flight with the tracer at full speed;
                     if the moment is dramatic, the last 3 s play at 0.5x.
    Payoff   last 3 s  result card: score to par, Road to 59 status, CTA.

Source material: the OBS replay buffer saves the 60 s ending at the
trigger event (broadcast-stack §3.5), written to
``~/mas-golfs/clips/round{NNNN}-hole{HH}-{moment}-{seq}.mp4``. In/out
points are offsets into that 60 s file: the clip uses the last
``duration`` seconds, and the segments re-order source ranges so the
payoff lands first (see ``segments``).

Platform variants follow the playbook §1.2 table: one master clip, three
exports — never the same file everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .scoring import Moment

REPLAY_BUFFER_S = 60  # OBS replay buffer length (broadcast-stack §3.5)
SLOW_MOTION_THRESHOLD = 75  # drama >= 75 earns a 0.5x replay of the last 3 s

PLATFORM_SPECS = {
    "shorts": {
        "platform": "YouTube Shorts",
        "aspect": "9:16",
        "resolution": "1080x1920",
        "length": "20-45 s (sweet spot ~30 s)",
        "captions": "Burned in, large, top-third safe",
        "on_screen_text": "Shot data strip + decision line",
        "sound": "Ambient bed + impact sound; trending audio only if it fits",
        "cta": "Full round live now — link in bio",
        "hashtags": ["#golf", "#golftok", "#masgolfs", "#roadto59", "#shottracer"],
        "posting_window": "12:00-2:00pm ET and 7:00-9:00pm ET",
    },
    "reels": {
        "platform": "Instagram Reels",
        "aspect": "9:16",
        "resolution": "1080x1920",
        "length": "20-40 s",
        "captions": "Burned in, large, avoid bottom 25% (UI)",
        "on_screen_text": "Same, plus 'Mason W Golf' handle watermark",
        "sound": "Ambient bed + impact sound",
        "cta": "Live 24/7 — link in bio",
        "hashtags": ["#golf", "#golfreels", "#masgolfs", "#roadto59"],
        "posting_window": "11:00am-1:00pm ET and 7:00-9:00pm ET",
    },
    "tiktok": {
        "platform": "TikTok",
        "aspect": "9:16",
        "resolution": "1080x1920",
        "length": "20-35 s",
        "captions": "Burned in, large, avoid right edge (UI)",
        "on_screen_text": "Same, minimal — TikTok punishes text-heavy frames",
        "sound": "Ambient bed + impact sound; native sounds sparingly",
        "cta": "Live now — link in bio",
        "hashtags": ["#golf", "#golftok", "#masgolfs", "#roadto59"],
        "posting_window": "12:00-3:00pm ET and 7:00-10:00pm ET",
    },
}

# Moment type -> clip format (launch-playbook §2).
FORMAT_BY_MOMENT = {
    "hole_out": "Best shot",
    "road_to_59": "Record-chase update",
    "eagle": "Best shot",
    "near_miss": "Worst miss",
    "recovery": "Best shot",
    "best_decision": "Decision breakdown",
    "worst_miss": "Worst miss",
    "streak": "Record-chase update",
    "record_chase": "Record-chase update",
    "birdie": "Best shot",
}


def _fmt_score(score_to_par: int) -> str:
    if score_to_par == 0:
        return "even par"
    if score_to_par < 0:
        return f"{-score_to_par} under par"
    return f"{score_to_par} over par"


def _hook_and_title(m: Moment) -> tuple[str, str]:
    """Hook line (first frame) and title, per moment type."""
    ctx = m.context
    hole = f"Hole {m.hole} — {m.hole_name}"
    club = ctx.get("club") or ""
    dist = ctx.get("distance_to_pin_ft")
    if m.moment_type == "hole_out":
        if m.par == 3 and m.shot_no == 1:
            return ("HOLE IN ONE.", f"Ace at {m.hole_name} — {club} from {ctx.get('distance_yd', '?')} yards.")
        return ("He holed it.", f"Holed it from {dist} feet — {hole}.")
    if m.moment_type == "road_to_59":
        return ("59. HE DID IT.", "Mas shoots 59 at Wyatt National — the Road to 59 is complete.")
    if m.moment_type == "eagle":
        return ("Eagle.", f"Eagle at {m.hole_name}. { _fmt_score(m.score_to_par) } through {m.hole}.")
    if m.moment_type == "near_miss":
        return ("This close.", f"Six inches from dropping — {hole}.")
    if m.moment_type == "recovery":
        return ("From trouble. Saved.", f"The recovery that saved {hole}.")
    if m.moment_type == "best_decision":
        reasoning = ctx.get("decision_reasoning") or "The right call."
        return (reasoning, f"{club}. {reasoning} — {hole}.")
    if m.moment_type == "worst_miss":
        verb = {"thin": "Thinned", "chunk": "Chunked", "toe": "Toed",
                "heel": "Heeled", "shank": "Shanked"}.get(
            ctx.get("contact_quality"), "Missed")
        return ("That's golf.", f"{verb} it. The miss is the story — {hole}.")
    if m.moment_type == "streak":
        return ("Three in a row.", f"Three straight birdies. { _fmt_score(m.score_to_par) } through {m.hole}.")
    if m.moment_type == "record_chase":
        return ("On pace for 59.", f"{_fmt_score(m.score_to_par).capitalize()} through {m.hole} — the 59 pace is alive.")
    if m.moment_type == "birdie":
        return ("Birdie.", f"Birdie at {m.hole_name}. {_fmt_score(m.score_to_par)} through {m.hole}.")
    return ("Mas Golfs.", f"{hole}.")


def _caption(m: Moment) -> str:
    """Caption = decision line + outcome + score status + CTA."""
    ctx = m.context
    parts: list[str] = []
    reasoning = ctx.get("decision_reasoning")
    if reasoning:
        parts.append(reasoning)
    commentary = ctx.get("commentary")
    if commentary and commentary != reasoning:
        parts.append(commentary)
    parts.append(f"Mas is {_fmt_score(m.score_to_par)} through {m.hole} at Wyatt National.")
    parts.append("Mas Golfs — live now, 24/7. Road to 59.")
    return " ".join(parts)


@dataclass
class ClipCard:
    """One assembled clip, ready for the daily queue."""

    clip_id: str
    moment_id: str
    moment_type: str
    clip_format: str
    drama: int
    round_no: int
    hole: int
    hole_name: str
    duration_s: int
    source_file: str
    source_in_s: float
    source_out_s: float
    slow_motion: bool
    segments: list[dict] = field(default_factory=list)
    hook_line: str = ""
    title: str = ""
    caption: str = ""
    first_comment: str = ""
    platforms: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "clip_id": self.clip_id,
            "moment_id": self.moment_id,
            "moment_type": self.moment_type,
            "format": self.clip_format,
            "drama": self.drama,
            "round_no": self.round_no,
            "hole": self.hole,
            "hole_name": self.hole_name,
            "duration_s": self.duration_s,
            "source": {
                "replay_file": self.source_file,
                "in_s": self.source_in_s,
                "out_s": self.source_out_s,
                "replay_buffer_s": REPLAY_BUFFER_S,
            },
            "slow_motion": self.slow_motion,
            "segments": self.segments,
            "hook_line": self.hook_line,
            "title": self.title,
            "caption": self.caption,
            "first_comment": self.first_comment,
            "platforms": self.platforms,
        }


def _duration_for(drama: int) -> int:
    """20-35 s, longer for bigger moments (playbook §1.1 Stage 3)."""
    if drama >= 90:
        return 35
    if drama >= 75:
        return 30
    return 25


def assemble_clip(moment: Moment) -> ClipCard:
    """Assemble a clip card from a scored moment."""
    duration = _duration_for(moment.drama)
    in_s = REPLAY_BUFFER_S - duration
    out_s = REPLAY_BUFFER_S
    slow_motion = moment.drama >= SLOW_MOTION_THRESHOLD
    hook_line, title = _hook_and_title(moment)
    caption = _caption(moment)
    decision = moment.context.get("decision_reasoning") or moment.context.get("commentary") or ""
    first_comment = f"{decision} Full round live now — link in bio." if decision else "Full round live now — link in bio."

    # Segments re-order the source so the payoff is the first frame.
    payoff_start = duration - 3
    segments = [
        {
            "name": "hook",
            "start_s": 0,
            "end_s": 2,
            "source_start_s": out_s - 2,
            "source_end_s": out_s,
            "speed": 1.0,
            "on_screen_text": hook_line,
        },
        {
            "name": "context",
            "start_s": 2,
            "end_s": 6,
            "source_start_s": in_s,
            "source_end_s": in_s + 4,
            "speed": 1.0,
            "on_screen_text": decision,
        },
        {
            "name": "shot",
            "start_s": 6,
            "end_s": payoff_start,
            "source_start_s": in_s + 4,
            "source_end_s": out_s - 3,
            "speed": 1.0,
            "on_screen_text": "Shot data strip: club, distance, ball speed, carry",
        },
    ]
    if slow_motion:
        # Last 3 s of the shot play at 0.5x (playbook §1.1 Stage 3).
        segments.append(
            {
                "name": "shot_slow_motion",
                "start_s": payoff_start - 3,
                "end_s": payoff_start,
                "source_start_s": out_s - 6,
                "source_end_s": out_s - 3,
                "speed": 0.5,
                "on_screen_text": "REPLAY",
            }
        )
    segments.append(
        {
            "name": "payoff",
            "start_s": payoff_start,
            "end_s": duration,
            "source_start_s": out_s - 3,
            "source_end_s": out_s,
            "speed": 1.0,
            "on_screen_text": f"Result card: {_fmt_score(moment.score_to_par)} through {moment.hole} · Road to 59 · Mas Golfs — live now, 24/7",
        }
    )

    platforms = {}
    for key, spec in PLATFORM_SPECS.items():
        platforms[key] = {
            "platform": spec["platform"],
            "aspect": spec["aspect"],
            "resolution": spec["resolution"],
            "target_length": spec["length"],
            "captions": spec["captions"],
            "on_screen_text": spec["on_screen_text"],
            "sound": spec["sound"],
            "cta": spec["cta"],
            "hashtags": spec["hashtags"],
            "posting_window": spec["posting_window"],
        }

    return ClipCard(
        clip_id=f"R{moment.round_no:04d}-H{moment.hole:02d}-{moment.moment_type}",
        moment_id=moment.moment_id,
        moment_type=moment.moment_type,
        clip_format=FORMAT_BY_MOMENT.get(moment.moment_type, "Best shot"),
        drama=moment.drama,
        round_no=moment.round_no,
        hole=moment.hole,
        hole_name=moment.hole_name,
        duration_s=duration,
        source_file=f"round{moment.round_no:04d}-hole{moment.hole:02d}-{moment.moment_type}-{moment.trigger_seq:04d}.mp4",
        source_in_s=float(in_s),
        source_out_s=float(out_s),
        slow_motion=slow_motion,
        segments=segments,
        hook_line=hook_line,
        title=title,
        caption=caption,
        first_comment=first_comment,
        platforms=platforms,
    )
