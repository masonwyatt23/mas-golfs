"""Generate mlx-verify/events.json — 50 real event-shaped prompts.

Deterministic (fixed tables, no randomness). Renders user prompts through
commentary/prompts.py — the same templates the production pipeline uses —
so the verification measures the prompts the broadcast actually sends.

Wyatt National routing/par/yardage from docs/course-design-v3.md.
Score forms use the spoken style the templates expect ("2 under par").

Run:  python3 gen_events.py   (writes events.json next to this file)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from commentary.prompts import render_user_prompt  # noqa: E402

HOLES = {
    1: ("The Handshake", 4, 432),
    2: ("The Reach", 5, 612),
    3: ("The Postage Stamp", 3, 196),
    4: ("The Examination", 4, 476),
    5: ("The Temptation", 4, 392),
    6: ("The Dogleg", 4, 452),
    7: ("The Valley", 5, 586),
    8: ("The Long One", 3, 238),
    9: ("The Return", 4, 424),
    10: ("The Turn", 4, 440),
    11: ("The Monster", 5, 624),
    12: ("The Picture", 3, 172),
    13: ("The Grind", 4, 482),
    14: ("The Gambler", 4, 406),
    15: ("The Eagle Chance", 5, 578),
    16: ("The Test", 3, 214),
    17: ("The Penultimate", 4, 448),
    18: ("The Closer", 4, 430),
}

# (event_type, speaker, fields) — three per template pair, 50 total.
# Fields are the sim event JSON values; nothing here is invented by the
# verifier — every number is a plausible event value.
SPECS: list[tuple[str, str, dict]] = [
    # decision (color) — 4
    ("decision", "color", {"hole": 3, "par": 3, "score_to_par": "1 under par",
     "thru": 2, "club": "7-iron", "shot_type": "full", "target_yards": 196,
     "aim": "middle of the green", "lie": "tee", "wind_mph": 8, "wind_dir": "into",
     "reason": "the pin is back left and the miss is short", "risk": "low"}),
    ("decision", "color", {"hole": 12, "par": 3, "score_to_par": "2 under par",
     "thru": 11, "club": "8-iron", "shot_type": "full", "target_yards": 172,
     "aim": "right edge of the green", "lie": "tee", "wind_mph": 6, "wind_dir": "helping",
     "reason": "downhill over the pond, the safe side is long", "risk": "medium"}),
    ("decision", "color", {"hole": 5, "par": 4, "score_to_par": "even par",
     "thru": 4, "club": "driver", "shot_type": "full", "target_yards": 278,
     "aim": "left center of the fairway", "lie": "tee", "wind_mph": 12, "wind_dir": "left to right",
     "reason": "the drivable green tempts, but the bunker guards the front", "risk": "high"}),
    ("decision", "color", {"hole": 17, "par": 4, "score_to_par": "3 under par",
     "thru": 16, "club": "5-iron", "shot_type": "knockdown", "target_yards": 198,
     "aim": "front edge", "lie": "fairway", "wind_mph": 15, "wind_dir": "into",
     "reason": "into the wind, take one more club and flight it down", "risk": "medium"}),
    ("decision", "color", {"hole": 8, "par": 3, "score_to_par": "even par",
     "thru": 7, "club": "5-iron", "shot_type": "full", "target_yards": 238,
     "aim": "front right", "lie": "tee", "wind_mph": 11, "wind_dir": "into",
     "reason": "the longest par 3 on the course, take plenty of club", "risk": "medium"}),
    ("decision", "color", {"hole": 15, "par": 5, "score_to_par": "4 under par",
     "thru": 14, "club": "3-wood", "shot_type": "full", "target_yards": 248,
     "aim": "left side of the green", "lie": "fairway", "wind_mph": 4, "wind_dir": "helping",
     "reason": "going for the green in two, the eagle chance is real", "risk": "high"}),
    # apex (color) — 3
    ("apex", "color", {"club": "7-iron", "apex_ft": 92, "carry_yds": 178,
     "shape": "draw", "curve_yds": 6}),
    ("apex", "color", {"club": "driver", "apex_ft": 118, "carry_yds": 262,
     "shape": "straight", "curve_yds": 1}),
    ("apex", "color", {"club": "5-iron", "apex_ft": 74, "carry_yds": 196,
     "shape": "fade", "curve_yds": 8}),
    ("apex", "color", {"club": "3-wood", "apex_ft": 96, "carry_yds": 229,
     "shape": "draw", "curve_yds": 11}),
    # landing (host) — 4
    ("landing", "host", {"club": "7-iron", "total_yds": 181, "lie": "green",
     "dist_to_pin_ft": 12, "result": "on the green", "score_to_par": "1 under par", "thru": 3}),
    ("landing", "host", {"club": "driver", "total_yds": 278, "lie": "fairway",
     "dist_to_pin_ft": 142, "result": "in the fairway", "score_to_par": "2 under par", "thru": 11}),
    ("landing", "host", {"club": "8-iron", "total_yds": 166, "lie": "green",
     "dist_to_pin_ft": 4, "result": "on the green", "score_to_par": "3 under par", "thru": 12}),
    ("landing", "host", {"club": "5-iron", "total_yds": 201, "lie": "rough",
     "dist_to_pin_ft": 38, "result": "in the rough", "score_to_par": "even par", "thru": 17}),
    ("landing", "host", {"club": "5-iron", "total_yds": 228, "lie": "green",
     "dist_to_pin_ft": 18, "result": "on the green", "score_to_par": "even par", "thru": 8}),
    ("landing", "host", {"club": "3-wood", "total_yds": 252, "lie": "green",
     "dist_to_pin_ft": 9, "result": "on the green", "score_to_par": "5 under par", "thru": 15}),
    # putt_result (host) — 3
    ("putt_result", "host", {"dist_ft": 12, "made_word": "made", "putts_this_hole": 1,
     "score_to_par": "2 under par", "thru": 3}),
    ("putt_result", "host", {"dist_ft": 22, "made_word": "missed", "putts_this_hole": 1,
     "score_to_par": "1 under par", "thru": 7}),
    ("putt_result", "host", {"dist_ft": 6, "made_word": "made", "putts_this_hole": 2,
     "score_to_par": "3 under par", "thru": 12}),
    ("putt_result", "host", {"dist_ft": 31, "made_word": "missed", "putts_this_hole": 1,
     "score_to_par": "4 under par", "thru": 15}),
    # hole_end host — 3
    ("hole_end", "host", {"hole": 3, "hole_name": "The Postage Stamp", "score": 3,
     "fairway_hit": "n/a", "gir": "yes", "putts": 1, "up_and_down": "n/a",
     "score_to_par": "1 under par"}),
    ("hole_end", "host", {"hole": 12, "hole_name": "The Picture", "score": 2,
     "fairway_hit": "n/a", "gir": "yes", "putts": 1, "up_and_down": "n/a",
     "score_to_par": "3 under par"}),
    ("hole_end", "host", {"hole": 7, "hole_name": "The Valley", "score": 5,
     "fairway_hit": "yes", "gir": "yes", "putts": 2, "up_and_down": "no",
     "score_to_par": "even par"}),
    # hole_end color — 2
    ("hole_end", "color", {"strokes_gained_summary": "three straight birdies, +0.8 strokes gained on approach"}),
    ("hole_end", "color", {"strokes_gained_summary": "a recovery from the trees saved par, +0.4 strokes gained on the short game"}),
    # round_end host — 2
    ("round_end", "host", {"score": 70, "score_to_par": "2 under par", "fairways": "8 of 14",
     "gir": "12 of 18", "putts": 29, "up_and_downs": "4 of 6", "new_handicap": "+3.1", "rank": 2}),
    ("round_end", "host", {"score": 64, "score_to_par": "8 under par", "fairways": "10 of 14",
     "gir": "15 of 18", "putts": 26, "up_and_downs": "5 of 5", "new_handicap": "+3.4", "rank": 1}),
    # round_end color — 2
    ("round_end", "color", {"leak": "approaches from 125 to 150 yards missing left",
     "strokes_lost": 0.6, "adjustment": "aim five yards right of the pin"}),
    ("round_end", "color", {"leak": "three-putts from over 30 feet",
     "strokes_lost": 0.5, "adjustment": "leave the first putt below the hole"}),
    # milestone host — 2
    ("milestone", "host", {"type": "birdie streak", "detail": "three straight birdies, holes 10 through 12",
     "score_to_par": "3 under par", "thru": 12}),
    ("milestone", "host", {"type": "season best round", "detail": "a 64, eight under par, best round of the season",
     "score_to_par": "8 under par", "thru": 18}),
    # milestone color — 2
    ("milestone", "color", {"type": "birdie streak", "detail": "three straight birdies, holes 10 through 12",
     "score_to_par": "3 under par", "thru": 12}),
    ("milestone", "color", {"type": "eagle", "detail": "eagle on the par-5 15th, holed the second shot from 212 yards",
     "score_to_par": "5 under par", "thru": 15}),
    # fifty_nine_watch host — 3
    ("fifty_nine_watch", "host", {"status": "on_pace", "score_to_par": "8 under par",
     "thru": 12, "holes_left": 6, "strokes_remaining": 1, "probability": 34}),
    ("fifty_nine_watch", "host", {"status": "on_the_line", "score_to_par": "8 under par",
     "thru": 17, "holes_left": 1, "strokes_remaining": 0, "probability": 58}),
    ("fifty_nine_watch", "host", {"status": "off_pace", "score_to_par": "2 over par",
     "thru": 14, "holes_left": 4, "strokes_remaining": 0, "probability": 0}),
    # fifty_nine_watch color — 2
    ("fifty_nine_watch", "color", {"status": "on_pace", "holes_left": 6, "strokes_remaining": 1}),
    ("fifty_nine_watch", "color", {"status": "on_the_line", "holes_left": 1, "strokes_remaining": 0}),
    # bad_miss (host) — 3
    ("bad_miss", "host", {"club": "driver", "lie": "right rough", "dist_to_pin_ft": 96, "result": "missed_right"}),
    ("bad_miss", "host", {"club": "9-iron", "lie": "front bunker", "dist_to_pin_ft": 21, "result": "short"}),
    ("bad_miss", "host", {"club": "3-wood", "lie": "left trees", "dist_to_pin_ft": 154, "result": "in_trees"}),
    # recovery color — 2
    ("recovery", "color", {"lie": "right rough", "club": "pitching wedge", "shot_type": "punch",
     "target_yards": 96, "reason": "keep it low under the branches and run it up the front"}),
    ("recovery", "color", {"lie": "front bunker", "club": "sand wedge", "shot_type": "flop",
     "target_yards": 21, "reason": "open the face and land it soft past the lip"}),
    # recovery host — 2
    ("recovery", "host", {"dist_to_pin_ft": 8}),
    ("recovery", "host", {"dist_to_pin_ft": 3}),
    # round_start (host) — 2
    ("round_start", "host", {"round": 47, "course": "Wyatt National", "par": 72,
     "target_score": 59, "handicap": "+3.1", "last10_avg": 70.1}),
    ("round_start", "host", {"round": 48, "course": "Wyatt National", "par": 72,
     "target_score": 59, "handicap": "+3.1", "last10_avg": 69.8}),
    # hole_start (host) — 3
    ("hole_start", "host", {"hole": 12, "hole_name": "The Picture", "par": 3, "yards": 172,
     "pin": "back left, over the pond", "wind_mph": 6, "wind_dir": "helping", "elevation_ft": -22}),
    ("hole_start", "host", {"hole": 8, "hole_name": "The Long One", "par": 3, "yards": 238,
     "pin": "front right", "wind_mph": 11, "wind_dir": "into", "elevation_ft": 6}),
    ("hole_start", "host", {"hole": 15, "hole_name": "The Eagle Chance", "par": 5, "yards": 578,
     "pin": "middle, reachable in two", "wind_mph": 4, "wind_dir": "left to right", "elevation_ft": -12}),
]


def build_events() -> list[dict]:
    events = []
    for i, (event_type, speaker, fields) in enumerate(SPECS, start=1):
        user_prompt = render_user_prompt(event_type, speaker, fields)
        events.append({
            "id": f"ev{i:02d}",
            "event_type": event_type,
            "speaker": speaker,
            "fields": fields,
            "user_prompt": user_prompt,
        })
    return events


def main() -> None:
    events = build_events()
    assert len(events) == 50, f"expected 50 events, got {len(events)}"
    out = os.path.join(os.path.dirname(__file__), "events.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(events, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {out} ({len(events)} events)")


if __name__ == "__main__":
    main()
