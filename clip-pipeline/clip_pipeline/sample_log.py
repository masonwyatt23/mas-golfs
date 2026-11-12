"""Generate a deterministic sample event log for testing the clip pipeline.

Builds round R0042 at Wyatt National — the round Mas shoots 59. Every
moment type in the drama model appears at least once:

    H1   birdie (first of the round)            drama 60
    H2   eagle                                  drama 95
    H3   near-miss (4 ft putt lips out)         drama 85
    H5   worst miss (chunked drive) + recovery  drama 75 / 80
    H7   best decision (knockdown into wind)    drama 75
    H11  streak (3rd consecutive birdie)       drama 70
    H12  hole-in-one at The Picture             drama 100
    H13  record-chase (on pace, deep)           drama 70 (+10 boost)
    H16  record-chase                           drama 70 (+10 boost)
    H17  record-chase                           drama 70 (+10 boost)
    H18  road to 59 — birdie to shoot 59        drama 100

The H6 birdie deliberately scores nothing: it is not the first birdie
and breaks no 5+ hole drought, exercising the birdie rule. The H14
bogey is routine. All events follow docs/sim-engine.md §1 exactly.
Deterministic: same seed, same bytes, every run.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .course import HOLES, PACE_TO_PAR, score_vs_target

ROUND_NO = 42
DATE_STR = "20261112"
SEED = 42


class RoundBuilder:
    """Emits sim-engine §1 events with envelope, seq, and a moving clock."""

    def __init__(self, round_no: int = ROUND_NO, seed: int = SEED):
        self.round_no = round_no
        self.round_id = f"R{round_no:04d}"
        self.seq = 0
        self.rng = random.Random(seed)
        self.clock = datetime(2026, 11, 12, 6, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        self.events: list[dict] = []

    def _tick(self, lo: int, hi: int) -> int:
        self.clock += timedelta(seconds=self.rng.randint(lo, hi))
        return int(self.clock.timestamp() * 1000)

    def _emit(self, etype: str, hole: int, shot_no: int, **fields) -> dict:
        self.seq += 1
        ev = {
            "type": etype,
            "v": 1,
            "event_id": f"evt_{DATE_STR}_{self.round_no:04d}_{self.seq:04d}",
            "ts": self._tick(5, 15),
            "round_id": self.round_id,
            "round_no": self.round_no,
            "hole": hole,
            "shot_no": shot_no,
            "seq": self.seq,
            **fields,
        }
        self.events.append(ev)
        return ev

    # -- event-type emitters -------------------------------------------------

    def round_start(self) -> None:
        self._emit(
            "round_start", 0, 0,
            course={"name": "Wyatt National", "par": 72, "yardage": 7214, "rating": 74.6, "slope": 138},
            conditions={"wind_mph": 9, "wind_dir_deg": 310, "temp_f": 58,
                        "sky": "partly_cloudy", "firmness": 0.62, "green_speed": 11.2},
            handicap_index=3.1,
            target_score=59,
            ghost_target=68,
            last10_avg=71.4,
            form="hot",
            focus_fix={"area": "approach_150_175",
                       "adjustment": "aim 4 ft further right on approaches from 150-175 yd",
                       "source_round": "R0041"},
        )

    def hole_start(self, hole: int, score_to_par: int) -> None:
        completed = hole - 1
        self._emit(
            "hole_start", hole, 0,
            par=HOLES[hole]["par"],
            yardage=HOLES[hole]["yards"],
            name=HOLES[hole]["name"],
            tee="back",
            pin={"x_ft": self.rng.choice([-18, -6, 0, 6, 18]),
                 "y_ft": self.rng.choice([-12, 0, 12]),
                 "zone": self.rng.choice(["front_left", "mid_center", "back_right"]),
                 "difficulty": round(self.rng.uniform(0.4, 0.8), 2)},
            hole_wind={"mph": self.rng.randint(6, 13), "dir_deg": 295,
                       "effect": self.rng.choice(["into", "down", "cross_left", "cross_right"])},
            score_to_par=score_to_par,
            score_vs_target=score_vs_target(score_to_par, completed),
            # Strokes under par still needed over the remaining holes to reach -13.
            strokes_to_59_pace=max(0, -PACE_TO_PAR + score_to_par),
        )

    def decision(self, hole: int, shot_no: int, spec: dict) -> None:
        self._emit(
            "shot_decision", hole, shot_no,
            situation={
                "lie": spec.get("lie", "fairway"),
                "distance_yd": spec["dist"],
                "elevation_ft": spec.get("elev", 0),
                "wind_mph": spec.get("wind_mph", 9),
                "wind_effect": spec.get("wind_effect", "into"),
                "to_pin_yd": spec["dist"],
                "hazard": spec.get("hazard"),
            },
            decision={
                "shot_type": spec.get("shot_type", "full"),
                "club": spec["club"],
                "target": {
                    "aim_point": spec.get("aim_point", "at the pin"),
                    "aim_offset_ft": spec.get("aim_offset_ft", 0),
                    "intended_shape": spec.get("shape", "straight"),
                    "intended_traj": spec.get("traj", "normal"),
                    "intended_carry_yd": spec.get("carry", spec["dist"]),
                },
                "reasoning": spec.get("reasoning", ""),
                "alternatives_considered": spec.get("alternatives", []),
                "ev_strokes": spec.get("ev", 3.0),
                "risk": spec.get("risk", 0.15),
                "confidence": spec.get("confidence", 0.8),
            },
        )

    def shot(self, hole: int, shot_no: int, spec: dict) -> None:
        carry = spec.get("carry", spec["dist"])
        total = spec.get("total", carry + 6)
        self._emit(
            "shot_result", hole, shot_no,
            club=spec["club"],
            shot_type=spec.get("shot_type", "full"),
            contact={
                "quality": spec.get("contact", "pure"),
                "strike_x_mm": spec.get("strike_x_mm", 0),
                "strike_y_mm": spec.get("strike_y_mm", 0),
                "face_deg": spec.get("face_deg", 0.5),
                "path_deg": spec.get("path_deg", -0.5),
                "club_speed_mph": spec.get("club_speed", 105),
            },
            launch={
                "ball_speed_mph": spec.get("ball_speed", 152),
                "launch_deg": spec.get("launch_deg", 12.0),
                "spin_rpm": spec.get("spin", 2600),
                "spin_axis_deg": spec.get("spin_axis", -2.0),
                "apex_ft": spec.get("apex", 85),
                "carry_yd": carry,
                "total_yd": total,
                "curve_ft": spec.get("curve_ft", -4),
                "offline_ft": spec.get("offline_ft", -3),
            },
            outcome={
                "lie": spec.get("lie_out", "fairway"),
                "distance_to_pin_ft": spec.get("dist_pin"),
                "on_green": spec.get("on_green", False),
                "fairway_hit": spec.get("fairway"),
                "gir": spec.get("gir"),
                "hazard": spec.get("hazard"),
                "penalty": spec.get("penalty", 0),
                "in_water": spec.get("in_water", False),
                "ob": spec.get("ob", False),
            },
            shot_quality=spec.get("quality", 0.85),
            commentary=spec.get("commentary", ""),
            drama=spec.get("drama", 0.2),
        )

    def putt(self, hole: int, shot_no: int, dist_ft: float, made: bool,
             leave_ft: float = 0, break_ft: float = 1.0, commentary: str = "") -> None:
        self._emit(
            "putt_result", hole, shot_no,
            putt={
                "distance_ft": dist_ft,
                "break_ft": break_ft,
                "break_dir": "left_to_right" if break_ft > 0 else "straight",
                "speed": "good",
                "made": made,
                "leave_ft": leave_ft if not made else 0,
            },
            putts_on_hole=shot_no - 2 if HOLES[hole]["par"] > 3 else shot_no - 1,
            commentary=commentary,
        )

    def hole_complete(self, hole: int, score: int, score_name: str, score_to_par: int, **stats) -> None:
        self._emit(
            "hole_complete", hole, 0,
            par=HOLES[hole]["par"],
            score=score,
            score_name=score_name,
            score_to_par=score_to_par,
            strokes_gained={"ott": 0.1, "app": 0.2, "arg": 0.05, "putt": 0.1, "total": 0.45},
            hole_stats={
                "fairway_hit": stats.get("fairway_hit"),
                "gir": stats.get("gir"),
                "putts": stats.get("putts", 2),
                "up_and_down": stats.get("up_and_down"),
                "sand_save": stats.get("sand_save"),
                "penalties": stats.get("penalties", 0),
                "driving_yd": stats.get("driving_yd"),
                "approach_ft": stats.get("approach_ft"),
            },
            commentary=stats.get("commentary", ""),
        )

    def milestone(self, hole: int, kind: str, text: str, value=None, previous_best=None) -> None:
        self._emit(
            "milestone", hole, 0,
            kind=kind, text=text, value=value, previous_best=previous_best,
        )

    def round_complete(self, score: int, score_to_par: int) -> None:
        self._emit(
            "round_complete", 0, 0,
            score=score,
            score_to_par=score_to_par,
            stats={
                "fairways": "12/14", "fairway_pct": 0.86, "gir": "14/18", "gir_pct": 0.78,
                "putts": 27, "putts_per_gir": 1.5, "scrambling_pct": 0.75, "sand_saves": "0/1",
                "driving_avg_yd": 284, "driving_longest_yd": 296,
                "approach_prox_ft": 16.2, "prox_100_125_ft": 11.0,
                "prox_150_175_ft": 22.0, "prox_175_200_ft": 30.0,
                "penalties": 0, "birdies": 8, "bogeys": 1, "eagles": 1,
            },
            strokes_gained={"ott": 0.9, "app": 2.4, "arg": 0.3, "putt": 1.1, "total": 4.7},
            handicap={"index_before": 3.1, "index_after": 3.4, "differential": -8.4},
            focus_fix={"area": "approach_150_175",
                       "adjustment": "aim 4 ft further right on approaches from 150-175 yd",
                       "expected_gain": 0.4},
            records={"course_record": True, "personal_best": True, "best_front9": True, "season_best": True},
            road_to_59={"rounds_played": 42, "rounds_under_70": 12, "best_score": 59, "strokes_from_59": 0},
        )


# --- Hole scripts -----------------------------------------------------------
# Each hole: (score, score_name, score_to_par_after, steps, hole_stats, milestones)
# A step is ("shot", spec) or ("putt", dist_ft, made, leave_ft, commentary).

def _drive(dist, total, fairway=True, **kw):
    spec = {"club": "driver", "shot_type": "full", "lie": "tee", "dist": dist,
            "carry": total - 7, "total": total, "lie_out": "fairway" if fairway else "rough_light",
            "fairway": fairway, "quality": 0.88, "club_speed": 112, "ball_speed": 163,
            "launch_deg": 11.5, "spin": 2400, "apex": 95,
            "commentary": "Striped down the middle."}
    spec.update(kw)
    return ("shot", spec)


def _approach(club, dist, dist_pin, **kw):
    spec = {"club": club, "shot_type": "full", "lie": "fairway", "dist": dist,
            "carry": dist - 2, "total": dist, "dist_pin": dist_pin,
            "lie_out": "green", "on_green": True, "gir": True, "quality": 0.85,
            "club_speed": 95, "ball_speed": 135, "launch_deg": 16.0, "spin": 6200,
            "apex": 70, "commentary": f"To {dist_pin} feet."}
    spec.update(kw)
    return ("shot", spec)


HOLE_SCRIPTS = [
    # H1 — birdie, first of the round.
    (3, "birdie", -1,
     [_drive(412, 285),
      _approach("8-iron", 127, 8, commentary="Eight feet, right of the pin."),
      ("putt", 8, True, 0, "Eight feet — and he pours it in.")],
     {"fairway_hit": True, "gir": True, "putts": 1, "driving_yd": 285, "approach_ft": 8},
     []),
    # H2 — eagle.
    (3, "eagle", -3,
     [_drive(578, 295),
      ("shot", {"club": "3-wood", "shot_type": "full", "lie": "fairway", "dist": 283,
                "carry": 245, "total": 252, "dist_pin": 12, "lie_out": "green",
                "on_green": True, "gir": True, "quality": 0.9, "club_speed": 104,
                "ball_speed": 152, "launch_deg": 13.0, "spin": 3400, "apex": 80,
                "commentary": "Three-wood to twelve feet — eagle putt coming."}),
      ("putt", 12, True, 0, "Twelve feet for eagle — and it's in!")],
     {"fairway_hit": True, "gir": True, "putts": 1, "driving_yd": 295, "approach_ft": 12},
     []),
    # H3 — near-miss: 4 ft putt lips out, stops 0.4 ft short.
    (3, "par", -3,
     [_approach("7-iron", 187, 4, lie="tee", commentary="Four feet. Right at it."),
      ("putt", 4, False, 0.4, "Burned the edge — it stays out."),
      ("putt", 0.4, True, 0, "Tap-in for par.")],
     {"fairway_hit": None, "gir": True, "putts": 2, "approach_ft": 4},
     []),
    # H4 — routine par.
    (4, "par", -3,
     [_drive(448, 278),
      _approach("9-iron", 170, 22, quality=0.78, commentary="Twenty-two feet, uphill."),
      ("putt", 22, False, 3, "Left it short."),
      ("putt", 3, True, 0, "Par.")],
     {"fairway_hit": True, "gir": True, "putts": 2, "driving_yd": 278, "approach_ft": 22},
     []),
    # H5 — chunked drive (worst miss), then up-and-down par (recovery).
    (4, "par", -3,
     [("shot", {"club": "driver", "shot_type": "full", "lie": "tee", "dist": 376,
               "carry": 178, "total": 190, "lie_out": "rough_heavy", "fairway": False,
               "contact": "chunk", "quality": 0.3, "club_speed": 108, "ball_speed": 132,
               "launch_deg": 9.0, "spin": 3100, "apex": 55, "drama": 0.7,
               "reasoning": "Driver at the green — the Temptation.",
               "commentary": "Chunked it. Heavy lie, 186 to go."}),
      ("shot", {"club": "6-iron", "shot_type": "punch", "lie": "rough_heavy", "dist": 186,
                "carry": 58, "total": 66, "lie_out": "fairway", "quality": 0.8,
                "club_speed": 88, "ball_speed": 118, "launch_deg": 10.0, "spin": 4200,
                "apex": 40, "reasoning": "Punch it back to the fat of the fairway.",
                "commentary": "Punched it back to the short grass."}),
      ("shot", {"club": "GW", "shot_type": "pitch", "lie": "fairway", "dist": 120,
                "carry": 118, "total": 120, "dist_pin": 12, "lie_out": "green",
                "on_green": True, "gir": False, "quality": 0.86, "club_speed": 78,
                "ball_speed": 98, "launch_deg": 28.0, "spin": 8200, "apex": 45,
                "commentary": "Twelve feet to save par."}),
      ("putt", 12, True, 0, "Par saved. That's the bounce-back.")],
     {"fairway_hit": False, "gir": False, "putts": 1, "up_and_down": True,
      "driving_yd": 190, "approach_ft": 12},
     []),
    # H6 — birdie that scores nothing (not first, no 5+ drought).
    (3, "birdie", -4,
     [_drive(431, 282),
      _approach("9-iron", 149, 15, commentary="Fifteen feet."),
      ("putt", 15, True, 0, "Birdie at the Dogleg.")],
     {"fairway_hit": True, "gir": True, "putts": 1, "driving_yd": 282, "approach_ft": 15},
     []),
    # H7 — best decision: knockdown 5-iron into the wind to 14 feet.
    (4, "birdie", -5,
     [_drive(552, 287),
      ("shot", {"club": "5-iron", "shot_type": "knockdown", "lie": "fairway", "dist": 238,
                "elev": 14, "wind_mph": 11, "wind_effect": "into_and_left",
                "carry": 226, "total": 232, "dist_pin": 14, "lie_out": "green",
                "on_green": True, "gir": True, "quality": 0.82, "club_speed": 96,
                "ball_speed": 139, "launch_deg": 15.2, "spin": 5200, "apex": 74,
                "risk": 0.31, "ev": 3.24, "confidence": 0.78, "traj": "low", "shape": "fade",
                "aim_point": "right edge of green", "aim_offset_ft": 12,
                "reasoning": "Uphill into the wind — club up one, knock it down, aim right edge and let the wind bring it back.",
                "commentary": "Knocked down beautifully — rode the wind back to 14 feet."}),
      ("putt", 14, False, 2, "Just missed."),
      ("putt", 2, True, 0, "Birdie at the Valley.")],
     {"fairway_hit": True, "gir": True, "putts": 2, "driving_yd": 287, "approach_ft": 14},
     []),
    # H8 — routine par.
    (3, "par", -5,
     [_approach("hybrid", 226, 30, lie="tee", quality=0.8, commentary="Thirty feet, two-putt par."),
      ("putt", 30, False, 4, "Lagged it close."),
      ("putt", 4, True, 0, "Par.")],
     {"fairway_hit": None, "gir": True, "putts": 2, "approach_ft": 30},
     []),
    # H9 — birdie (streak 1).
    (3, "birdie", -6,
     [_drive(402, 281),
      _approach("9-iron", 121, 10, commentary="Ten feet."),
      ("putt", 10, True, 0, "Birdie at the Return.")],
     {"fairway_hit": True, "gir": True, "putts": 1, "driving_yd": 281, "approach_ft": 10},
     []),
    # H10 — birdie (streak 2).
    (3, "birdie", -7,
     [_drive(419, 279),
      _approach("8-iron", 140, 18, commentary="Eighteen feet."),
      ("putt", 18, True, 0, "Birdie at the Turn.")],
     {"fairway_hit": True, "gir": True, "putts": 1, "driving_yd": 279, "approach_ft": 18},
     []),
    # H11 — birdie (streak 3) + milestone.
    (4, "birdie", -8,
     [_drive(591, 292),
      ("shot", {"club": "3-wood", "shot_type": "full", "lie": "fairway", "dist": 299,
                "carry": 250, "total": 259, "dist_pin": 120, "lie_out": "fairway",
                "quality": 0.85, "club_speed": 103, "ball_speed": 150, "launch_deg": 12.5,
                "spin": 3200, "apex": 78, "commentary": "Forty yards short — pitch left."}),
      ("shot", {"club": "LW", "shot_type": "pitch", "lie": "fairway", "dist": 40,
                "carry": 39, "total": 40, "dist_pin": 9, "lie_out": "green",
                "on_green": True, "gir": True, "quality": 0.88, "club_speed": 62,
                "ball_speed": 72, "launch_deg": 32.0, "spin": 9500, "apex": 35,
                "commentary": "Nine feet for the third straight birdie."}),
      ("putt", 9, True, 0, "Three in a row!")],
     {"fairway_hit": True, "gir": True, "putts": 1,
      "driving_yd": 292, "approach_ft": 9},
     [("streak_birdie_3", "Three consecutive birdies — Mas is on fire.", None, None)]),
    # H12 — hole-in-one at The Picture.
    (1, "hole_in_one", -10,
     [("shot", {"club": "8-iron", "shot_type": "full", "lie": "tee", "dist": 164,
               "carry": 162, "total": 164, "dist_pin": 0, "lie_out": "green",
               "on_green": True, "gir": True, "quality": 1.0, "club_speed": 92,
               "ball_speed": 128, "launch_deg": 19.0, "spin": 6800, "apex": 68,
               "drama": 1.0, "commentary": "It's in! Hole-in-one at The Picture!"})],
     {"fairway_hit": None, "gir": True, "putts": 0, "approach_ft": 0},
     [("hole_in_one", "Hole-in-one at The Picture — 164 yards, 8-iron.", 1, None)]),
    # H13 — routine par, on pace for 59 (record-chase).
    (4, "par", -10,
     [_drive(455, 276),
      _approach("7-iron", 179, 25, quality=0.78, commentary="Twenty-five feet."),
      ("putt", 25, False, 3, "Good lag."),
      ("putt", 3, True, 0, "Par at the Grind.")],
     {"fairway_hit": True, "gir": True, "putts": 2, "driving_yd": 276, "approach_ft": 25},
     []),
    # H14 — bogey, routine.
    (5, "bogey", -9,
     [_drive(388, 250, fairway=False, contact="toe", quality=0.55, lie_out="rough_light",
            commentary="Toed it into the right rough."),
      ("shot", {"club": "6-iron", "shot_type": "full", "lie": "rough_light", "dist": 138,
                "carry": 130, "total": 132, "dist_pin": 45, "lie_out": "bunker_green",
                "quality": 0.5, "club_speed": 90, "ball_speed": 122, "launch_deg": 15.0,
                "spin": 5400, "apex": 60, "commentary": "Short — into the greenside bunker."}),
      ("shot", {"club": "SW", "shot_type": "bunker_splash", "lie": "bunker_green", "dist": 45,
                "carry": 43, "total": 45, "dist_pin": 18, "lie_out": "green",
                "on_green": True, "quality": 0.75, "club_speed": 70, "ball_speed": 82,
                "launch_deg": 30.0, "spin": 8800, "apex": 38,
                "commentary": "Splashed it out to eighteen feet."}),
      ("putt", 18, False, 3, "Missed."),
      ("putt", 3, True, 0, "Bogey.")],
     {"fairway_hit": False, "gir": False, "putts": 2, "sand_save": False,
      "driving_yd": 250, "approach_ft": 45},
     []),
    # H15 — birdie.
    (4, "birdie", -10,
     [_drive(545, 296),
      ("shot", {"club": "3-wood", "shot_type": "full", "lie": "fairway", "dist": 249,
                "carry": 242, "total": 249, "dist_pin": 25, "lie_out": "green",
                "on_green": True, "gir": True, "quality": 0.88, "club_speed": 103,
                "ball_speed": 151, "launch_deg": 12.0, "spin": 3300, "apex": 76,
                "commentary": "On in two — twenty-five feet for birdie."}),
      ("putt", 25, False, 2.5, "Close."),
      ("putt", 2.5, True, 0, "Birdie at the Eagle Chance.")],
     {"fairway_hit": True, "gir": True, "putts": 2, "driving_yd": 296, "approach_ft": 25},
     []),
    # H16 — routine par, on pace for 59 (record-chase).
    (3, "par", -10,
     [_approach("6-iron", 203, 28, lie="tee", quality=0.8, commentary="Twenty-eight feet."),
      ("putt", 28, False, 4, "Good pace."),
      ("putt", 4, True, 0, "Par at the Test.")],
     {"fairway_hit": None, "gir": True, "putts": 2, "approach_ft": 28},
     []),
    # H17 — birdie, on pace for 59 (record-chase).
    (3, "birdie", -11,
     [_drive(427, 284),
      _approach("7-iron", 143, 11, commentary="Eleven feet."),
      ("putt", 11, True, 0, "Birdie at the Penultimate — one hole to go.")],
     {"fairway_hit": True, "gir": True, "putts": 1, "driving_yd": 284, "approach_ft": 11},
     []),
    # H18 — birdie to shoot 59.
    (3, "birdie", -13,
     [_drive(410, 290),
      _approach("PW", 120, 7, commentary="Seven feet for 59."),
      ("putt", 7, True, 0, "HE DID IT! 59 at Wyatt National!")],
     {"fairway_hit": True, "gir": True, "putts": 1, "driving_yd": 290, "approach_ft": 7},
     [("course_record", "Mas shoots 59 — new course record at Wyatt National.", 59, 63),
      ("road_to_59_step", "Road to 59: complete. 59 at Wyatt National.", 59, None)]),
]


def build_round(round_no: int = ROUND_NO, seed: int = SEED) -> list[dict]:
    """Build the full R0042 event log. Deterministic for a given seed."""
    b = RoundBuilder(round_no=round_no, seed=seed)
    b.round_start()
    score_to_par = 0
    for hole, (score, score_name, new_score, steps, stats, milestones) in enumerate(HOLE_SCRIPTS, start=1):
        b.hole_start(hole, score_to_par)
        shot_no = 0
        for step in steps:
            if step[0] == "shot":
                shot_no += 1
                b.decision(hole, shot_no, step[1])
                b.shot(hole, shot_no, step[1])
            else:  # putt
                _, dist_ft, made, leave_ft, commentary = step
                shot_no += 1
                b.putt(hole, shot_no, dist_ft, made, leave_ft, commentary=commentary)
        b.hole_complete(hole, score, score_name, new_score, **stats,
                        commentary=f"{score_name.capitalize()} at {HOLES[hole]['name']}.")
        for kind, text, value, prev in milestones:
            b.milestone(hole, kind, text, value=value, previous_best=prev)
        score_to_par = new_score
    b.round_complete(score_to_par + 72, score_to_par)
    return b.events


def write_sample_log(path: str | Path) -> Path:
    """Write the sample event log as JSONL. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    events = build_round()
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
    return path


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "sample_data" / "round_R0042_events.jsonl"
    write_sample_log(out)
    print(f"Wrote {out} ({len(build_round())} events)")
