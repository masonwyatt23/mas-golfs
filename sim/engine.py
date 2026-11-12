"""The round loop and state machine (spec §8).

IDLE -> ROUND_START -> HOLE_START -> SHOT_DECISION -> SHOT_EXECUTION
  -> SHOT_RESULT -> (PUTT_RESULT)* -> HOLE_COMPLETE -> HOLE_START (next)
  -> ROUND_COMPLETE -> LEARNING_LOOP -> ROUND_START (next round)
  -> forever. There is no terminal state.

The simulation and the broadcast run on separate clocks (§8.5): this module
simulates as fast as possible and emits the typed event stream (§1); the
broadcast consumes it at human pace.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field

from . import constants as C
from .course import Course, WYATT_NATIONAL
from .decisions import (Candidate, Situation, decide, resolve_hole_wind,
                        wind_in_shot_frame)
from .events import EventEmitter
from .fifty_nine_watch import (FiftyNineRecordBook, FiftyNineWatch,
                               STATUS_ON_THE_LINE, STATUS_SECURED)
from .handicap import RecordBook, differential, form_from_scores, whs_index
from .learning import GolferModel, LearningLoop, ShotRecord
from .physics import (apply_roll, classify_contact, delivery_to_launch,
                      draw_delivery, fly_shot)
from .putting import make_probability, putt as putt_model
from .rng import Rng, seed_for_round
from .strokes_gained import baseline_strokes, categorize_shot, strokes_gained

PIN_ZONES = ["front_left", "front_center", "front_right",
             "mid_left", "mid_center", "mid_right",
             "back_left", "back_center", "back_right"]
PIN_OFFSETS = {  # (x_ft lateral, y_ft front/back) relative to green centre
    "front_left": (-15, -20), "front_center": (0, -20), "front_right": (15, -20),
    "mid_left": (-15, 0), "mid_center": (0, 0), "mid_right": (15, 0),
    "back_left": (-15, 20), "back_center": (0, 20), "back_right": (15, 20),
}
PIN_DIFFICULTY = {  # 0-1, combines pin depth, tier, nearby hazards
    "front_left": 0.45, "front_center": 0.35, "front_right": 0.55,
    "mid_left": 0.50, "mid_center": 0.40, "mid_right": 0.60,
    "back_left": 0.65, "back_center": 0.55, "back_right": 0.71,
}
SKY_WEIGHTS = [("clear", 0.40), ("partly_cloudy", 0.35),
               ("overcast", 0.15), ("light_rain", 0.10)]

def score_name(score: int, par: int) -> str:
    d = score - par
    if score == 1:
        return "hole_in_one"
    if d <= -3:
        return "albatross"
    if d == -2:
        return "eagle"
    if d == -1:
        return "birdie"
    if d == 0:
        return "par"
    if d == 1:
        return "bogey"
    if d == 2:
        return "double"
    return "triple_plus"


@dataclass
class HoleResult:
    hole: int
    par: int
    score: int
    score_name: str
    putts: int
    fairway_hit: bool | None
    gir: bool
    penalties: int
    driving_yd: float | None
    approach_ft: float | None
    up_and_down: bool | None
    sand_save: bool | None
    approach_dist_yd: float | None = None
    sg: dict = field(default_factory=dict)


@dataclass
class RoundResult:
    round_no: int
    score: int
    score_to_par: int
    hole_scores: list
    holes: list
    stats: dict
    strokes_gained: dict
    handicap_before: float | None
    handicap_after: float | None
    differential: float
    focus_fix: dict | None
    records: dict
    fifty_nine_watch: dict
    events: list
    sim_ms: float
    decisions_ms: float


class RoundEngine:
    """Simulates rounds of Mas Golfs, forever, from a seeded PRNG."""

    def __init__(self, course: Course | None = None,
                 model: GolferModel | None = None,
                 mc_n: int = 120, fast_mode: bool = False,
                 seed_offset: int = 0):
        self.course = course or WYATT_NATIONAL
        self.model = model or GolferModel()
        self.learning = LearningLoop()
        self.record_book = RecordBook()
        self.watch_book = FiftyNineRecordBook()
        self.scores: list[int] = []
        self.differentials: list[float] = []
        self.handicap_index: float | None = 3.1  # display index, +3.1 start
        self.round_no = 0
        self.mc_n = mc_n
        self.fast_mode = fast_mode
        self.seed_offset = seed_offset
        self.total_decisions_ms = 0.0
        self.total_decisions = 0

    # ------------------------------------------------------------- conditions --
    def _draw_conditions(self, rng: Rng) -> dict:
        wind_mph = rng.triangular(0.0, 18.0, 6.0)
        if rng.random() < 0.5:
            wind_dir = rng.uniform(300.0, 330.0)  # prevailing NW (§1.4)
        else:
            wind_dir = rng.uniform(0.0, 360.0)
        temp_f = rng.gauss_clamped(62.0, 10.0, 38.0, 88.0)
        sky = rng.weighted_choice([s for s, _ in SKY_WEIGHTS],
                                  [w for _, w in SKY_WEIGHTS])
        firmness = rng.gauss_clamped(0.6, 0.12, 0.25, 0.9)
        if sky == "light_rain":
            firmness = max(0.25, firmness - 0.15)
        green_speed = rng.gauss_clamped(11.0, 0.6, 9.5, 12.5)
        return dict(wind_mph=wind_mph, wind_dir_deg=wind_dir, temp_f=temp_f,
                    sky=sky, firmness=firmness, green_speed=green_speed)

    def _draw_pin(self, rng: Rng, prev_zone: str | None):
        zone = rng.choice(PIN_ZONES)
        while zone == prev_zone:
            zone = rng.choice(PIN_ZONES)
        return zone

    def _pin_position(self, hole, zone: str):
        """Pin world coords (hole frame) from its zone (§1.2)."""
        gx, gy = hole.green_centre()
        pts = hole.centreline_points()
        dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        seg_len = math.hypot(dx, dy) or 1.0
        ux, uy = dx / seg_len, dy / seg_len
        nx, ny = -uy, ux  # lateral normal (same convention as course.py)
        x_ft, y_ft = PIN_OFFSETS[zone]
        return (gx + (y_ft / 3.0) * ux + (x_ft / 3.0) * nx,
                gy + (y_ft / 3.0) * uy + (x_ft / 3.0) * ny)

    # ------------------------------------------------------------------ round --
    def play_round(self, round_no: int | None = None) -> RoundResult:
        t0 = time.perf_counter()
        dec_ms_start = self.total_decisions_ms
        self.round_no = (round_no if round_no is not None
                         else self.round_no + 1)
        rng = Rng(seed_for_round(self.round_no) + self.seed_offset)
        emitter = EventEmitter(self.round_no)
        cond = self._draw_conditions(rng)
        form = self.model.form
        pars = [h.par for h in self.course.holes]
        watch = FiftyNineWatch(pars, self.record_book.last10_avg, form)
        handicap_before = self.handicap_index
        focus_fix = self.model.active_fix
        emitter.emit(
            "round_start",
            course={"name": self.course.name, "par": self.course.par,
                    "yardage": self.course.yardage,
                    "rating": self.course.rating, "slope": self.course.slope},
            conditions={"wind_mph": round(cond["wind_mph"], 1),
                        "wind_dir_deg": round(cond["wind_dir_deg"]),
                        "temp_f": round(cond["temp_f"]),
                        "sky": cond["sky"],
                        "firmness": round(cond["firmness"], 2),
                        "green_speed": round(cond["green_speed"], 1)},
            handicap_index=handicap_before,
            target_score=C.TARGET_SCORE, ghost_target=C.GHOST_TARGET,
            last10_avg=self.record_book.last10_avg,
            form=form,
            focus_fix=(focus_fix.__dict__ if focus_fix else None))

        hole_results: list[HoleResult] = []
        all_records: list[ShotRecord] = []
        sg_total = {"ott": 0.0, "app": 0.0, "arg": 0.0, "putt": 0.0, "total": 0.0}
        score_so_far = 0
        prev_zone: str | None = None
        birdie_streak = 0
        bogey_free = True
        front9 = 0
        for hole_no in range(1, 19):
            hole = self.course.hole(hole_no)
            zone = self._draw_pin(rng, prev_zone)
            prev_zone = zone
            pin_x, pin_y = self._pin_position(hole, zone)
            w_along, w_lat, w_effect = resolve_hole_wind(
                cond["wind_mph"], cond["wind_dir_deg"], hole.azimuth_deg, rng)
            pace = watch.state
            emitter.emit(
                "hole_start", hole=hole_no, par=hole.par,
                yardage=hole.yardage, name=hole.name, tee="back",
                pin={"x_ft": PIN_OFFSETS[zone][0],
                     "y_ft": PIN_OFFSETS[zone][1], "zone": zone,
                     "difficulty": PIN_DIFFICULTY[zone]},
                hole_wind={"mph": round(math.hypot(w_along, w_lat), 1),
                           "dir_deg": round(cond["wind_dir_deg"]),
                           "effect": w_effect},
                score_to_par=score_so_far - sum(pars[:hole_no - 1]),
                score_vs_target=round(pace.strokes_vs_pace, 2),
                strokes_to_59_pace=pace.strokes_remaining)
            # 18th-tee "59 on the line" moment.
            if hole_no == 18:
                tee_status = watch.status_on_tee(18, score_so_far)
                if tee_status in (STATUS_ON_THE_LINE, STATUS_SECURED):
                    emitter.emit("fifty_nine_watch", hole=18,
                                 **watch.state.to_dict(),
                                 moment="59_on_the_line" if tee_status ==
                                 STATUS_ON_THE_LINE else "59_secured")
            hr, records = self._play_hole(
                emitter, rng, hole_no, hole, pin_x, pin_y, zone, cond,
                w_along, w_lat, w_effect, watch.state.strokes_vs_pace)
            hole_results.append(hr)
            all_records.extend(records)
            for k in ("ott", "app", "arg", "putt"):
                sg_total[k] += hr.sg.get(k, 0.0)
            score_so_far += hr.score
            if hole_no <= 9:
                front9 += hr.score
            if hr.score - hr.par <= -1:
                birdie_streak += 1
            else:
                birdie_streak = 0
            if hr.score - hr.par >= 1:
                bogey_free = False
            # Milestones mid-round.
            if hr.score == 1:
                emitter.emit("milestone", hole=hole_no, kind="hole_in_one",
                             text=f"HOLE IN ONE at the {hole.name}!",
                             value=1, previous_best=None)
            elif hr.score - hr.par <= -2:
                emitter.emit("milestone", hole=hole_no, kind="eagle",
                             text=f"Eagle at the {hole.name}!",
                             value=hr.score, previous_best=None)
            if birdie_streak == 3:
                emitter.emit("milestone", hole=hole_no,
                             kind="streak_birdie_3",
                             text="Three birdies in a row — Mas is rolling.",
                             value=3, previous_best=None)
            if hole_no == 9 and bogey_free:
                emitter.emit("milestone", hole=hole_no,
                             kind="streak_bogey_free_9",
                             text="Bogey-free through the front nine.",
                             value=front9, previous_best=None)
            # 59 Watch: emit on pace-status change; include state in the
            # hole_complete event either way.
            watch_state, changed = watch.update(hole_no, score_so_far)
            if changed:
                moment = ("back_on_pace" if watch_state.status == "on_pace"
                          and hole_no > 1 else watch_state.status)
                emitter.emit("fifty_nine_watch", hole=hole_no,
                             **watch_state.to_dict(), moment=moment)
            emitter.emit(
                "hole_complete", hole=hole_no, par=hole.par, score=hr.score,
                score_name=hr.score_name,
                score_to_par=score_so_far - sum(pars[:hole_no]),
                strokes_gained={k: round(v, 2)
                                for k, v in hr.sg.items()},
                hole_stats={"fairway_hit": hr.fairway_hit, "gir": hr.gir,
                            "putts": hr.putts, "up_and_down": hr.up_and_down,
                            "sand_save": hr.sand_save,
                            "penalties": hr.penalties,
                            "driving_yd": hr.driving_yd,
                            "approach_ft": hr.approach_ft},
                fifty_nine_watch=watch_state.to_dict(),
                commentary=self._hole_commentary(hr, hole, score_so_far,
                                                 sum(pars[:hole_no]), watch_state))
        sg_total["total"] = sum(sg_total[k] for k in ("ott", "app", "arg", "putt"))
        back9 = score_so_far - front9
        stats = self._round_stats(hole_results)
        diff = differential(score_so_far)
        self.differentials.append(diff)
        new_index = whs_index(self.differentials)
        handicap_after = handicap_before
        if new_index is not None and handicap_before is not None:
            # Invariant 6: index change per round clamped to +/-0.5 (§8.7).
            handicap_after = handicap_before + max(
                -0.5, min(0.5, new_index - handicap_before))
        elif new_index is not None:
            handicap_after = new_index
        self.handicap_index = handicap_after
        self.scores.append(score_so_far)
        self.model.form = form_from_scores(self.scores)
        fix = self.learning.after_round(self.model, all_records)
        watch_summary = watch.round_summary()
        self.watch_book.add_round(emitter.round_id, watch_summary)
        self.record_book.add_round(score_so_far, emitter.round_id, front9,
                                   back9, handicap_after)
        records_flags = self._round_records(score_so_far, emitter)
        emitter.emit(
            "round_complete",
            score=score_so_far, score_to_par=score_so_far - C.COURSE_PAR,
            stats=stats,
            strokes_gained={k: round(v, 2) for k, v in sg_total.items()},
            handicap={"index_before": handicap_before,
                      "index_after": handicap_after,
                      "differential": round(diff, 1)},
            focus_fix=(fix.__dict__ if fix else None),
            records=records_flags,
            fifty_nine_watch=watch_summary,
            road_to_59={"rounds_played": self.record_book.rounds_played,
                        "rounds_under_70": self.record_book.rounds_under_70,
                        "best_score": self.record_book.best_score,
                        "strokes_from_59": self.record_book.strokes_from_59})
        sim_ms = (time.perf_counter() - t0) * 1000.0
        return RoundResult(
            round_no=self.round_no, score=score_so_far,
            score_to_par=score_so_far - C.COURSE_PAR,
            hole_scores=[h.score for h in hole_results],
            holes=hole_results, stats=stats,
            strokes_gained={k: round(v, 2) for k, v in sg_total.items()},
            handicap_before=handicap_before, handicap_after=handicap_after,
            differential=round(diff, 1),
            focus_fix=(fix.__dict__ if fix else None),
            records=records_flags, fifty_nine_watch=watch_summary,
            events=emitter.events, sim_ms=sim_ms,
            decisions_ms=self.total_decisions_ms - dec_ms_start)

    # ------------------------------------------------------------------- hole --
    def _play_hole(self, emitter, rng, hole_no, hole, pin_x, pin_y, zone,
                   cond, w_along, w_lat, w_effect, strokes_vs_59_pace):
        pos = (0.0, 0.0)            # tee
        lie = "tee"
        strokes = 0
        putts = 0
        sg = {"ott": 0.0, "app": 0.0, "arg": 0.0, "putt": 0.0}
        records: list[ShotRecord] = []
        penalties = 0
        fairway_hit = None
        gir = False
        driving_yd = None
        approach_ft = None
        approach_dist_yd = None
        up_and_down = None
        sand_save = None
        greenside_bunker_attempted = False
        first_green_strokes = None
        shots_after_green = 0
        holed = False
        prev_pos = pos
        while not holed:
            if strokes >= 12:  # shot cap (§8.2) — safety valve, ~never
                break
            if lie == "green":
                # Putt sub-loop.
                strokes += 1
                putts += 1
                dist_ft = math.hypot(pin_x - pos[0], pin_y - pos[1]) * 3.0
                start_base = baseline_strokes("green", 0, dist_ft)
                res = putt_model(rng, dist_ft, cond["green_speed"],
                                 C.FORM_PUTT_MULT[self.model.form])
                emitter.emit("putt_result", hole=hole_no, shot_no=strokes,
                             putt={"distance_ft": round(dist_ft, 1),
                                   "break_ft": round(res["break_ft"], 1),
                                   "break_dir": res["break_dir"],
                                   "speed": res["speed"],
                                   "made": res["made"],
                                   "leave_ft": round(res["leave_ft"], 1)},
                             putts_on_hole=putts,
                             commentary=self._putt_commentary(res, dist_ft))
                if res["made"]:
                    sg_shot = start_base - 1.0
                    holed = True
                else:
                    sg_shot = start_base - (1.0 + baseline_strokes(
                        "green", 0, res["leave_ft"]))
                    # Move toward the pin by the putt's roll-out.
                    dx, dy = pin_x - pos[0], pin_y - pos[1]
                    d = math.hypot(dx, dy) or 1.0
                    move_yd = max(0.0, dist_ft / 3.0 - res["leave_ft"] / 3.0)
                    pos = (pos[0] + dx / d * move_yd,
                           pos[1] + dy / d * move_yd)
                sg["putt"] += sg_shot
                records.append(ShotRecord(
                    "putt", self._putt_bucket(dist_ft), sg_shot, 0.0, 0.0))
                continue

            # Full-shot decision + execution (§5.2, §2.1).
            strokes += 1
            along, straight = self.course.distance_to_pin(hole, *pos)
            elev = hole.elevation_at(hole.yardage) - hole.elevation_at(
                self.course.hole(hole_no).project(*pos)[0])
            sit = Situation(
                hole=hole, ball_x=pos[0], ball_y=pos[1], lie=lie,
                distance_yd=along, distance_straight_yd=straight,
                elevation_ft=elev, wind_mph=math.hypot(w_along, w_lat),
                wind_effect=w_effect, wind_along_mph=w_along,
                wind_lateral_mph=w_lat, hazard=hole.hazard_label,
                pin_x=pin_x, pin_y=pin_y,
                blocked_by_trees=self._trees_block(hole, pos, pin_x, pin_y),
                hole_no=hole_no, holes_left=18 - hole_no + 1,
                strokes_vs_59_pace=strokes_vs_59_pace,
                temp_f=cond["temp_f"],
                firmness=cond["firmness"], green_speed=cond["green_speed"])
            t_dec = time.perf_counter()
            chosen, rejected = decide(self.course, sit, self.model, rng,
                                      self.mc_n, self.fast_mode)
            self.total_decisions_ms += (time.perf_counter() - t_dec) * 1000.0
            self.total_decisions += 1
            emitter.emit(
                "shot_decision", hole=hole_no, shot_no=strokes,
                situation={"lie": lie, "distance_yd": round(along),
                           "elevation_ft": round(elev),
                           "wind_mph": round(sit.wind_mph, 1),
                           "wind_effect": w_effect,
                           "to_pin_yd": round(straight),
                           "hazard": hole.hazard_label or None},
                decision={
                    "shot_type": chosen.shot_type, "club": chosen.club,
                    "target": {"aim_point": self._aim_label(chosen, sit),
                               "aim_offset_ft": round(chosen.aim_offset_ft, 1),
                               "intended_shape": chosen.intended_shape,
                               "intended_traj": chosen.intended_traj,
                               "intended_carry_yd": round(chosen.intended_carry_yd)},
                    "reasoning": chosen.reasoning,
                    "alternatives_considered": [
                        {"shot_type": r.shot_type, "club": r.club,
                         "ev_strokes": round(r.ev_strokes, 2)}
                        for r in rejected],
                    "ev_strokes": round(chosen.ev_strokes, 2),
                    "risk": round(chosen.risk, 2),
                    "confidence": round(chosen.confidence, 2)})
            is_tee_shot = (lie == "tee")
            start_base = baseline_strokes(
                lie, along, math.hypot(pin_x - pos[0], pin_y - pos[1]) * 3.0,
                self.model.baseline_adjustments)
            cat = categorize_shot(strokes, hole.par, lie, along,
                                  False, is_tee_shot)
            if chosen.shot_type == "putt":  # putter from the fringe
                dist_ft = math.hypot(pin_x - pos[0], pin_y - pos[1]) * 3.0
                res = putt_model(rng, dist_ft, cond["green_speed"],
                                 C.FORM_PUTT_MULT[self.model.form])
                emitter.emit("putt_result", hole=hole_no, shot_no=strokes,
                             putt={"distance_ft": round(dist_ft, 1),
                                   "break_ft": round(res["break_ft"], 1),
                                   "break_dir": res["break_dir"],
                                   "speed": res["speed"],
                                   "made": res["made"],
                                   "leave_ft": round(res["leave_ft"], 1)},
                             putts_on_hole=putts,
                             commentary=self._putt_commentary(res, dist_ft))
                putts += 1
                if res["made"]:
                    sg["putt"] += start_base - 1.0
                    holed = True
                else:
                    sg["putt"] += start_base - (1.0 + baseline_strokes(
                        "green", 0, res["leave_ft"]))
                    dx, dy = pin_x - pos[0], pin_y - pos[1]
                    d = math.hypot(dx, dy) or 1.0
                    move_yd = max(0.0, dist_ft / 3.0 - res["leave_ft"] / 3.0)
                    pos = (pos[0] + dx / d * move_yd,
                           pos[1] + dy / d * move_yd)
                    lie = "green"
                continue

            # Execute the full shot through the physics (§2).
            prev_pos = pos
            form_mult = C.FORM_SIG_MULT[self.model.form]
            delivery = draw_delivery(
                rng, chosen.club, chosen.shot_type, form_mult,
                chosen.intended_shape, chosen.power, lie,
                chosen.speed_fraction)
            quality = classify_contact(delivery, rng)
            wind_into = max(0.0, -w_along)
            launch = delivery_to_launch(delivery, chosen.club, quality,
                                        lie, wind_into, rng)
            aim_ang = math.atan2(chosen.target_y - pos[1],
                                 chosen.target_x - pos[0])
            w_a, w_l = wind_in_shot_frame(hole, pos[0], pos[1], aim_ang,
                                          w_along, w_lat)
            ground_m = elev * C.FT_TO_M
            flight = fly_shot(launch, w_a, w_l, ground_m, cond["temp_f"],
                              cond["firmness"])
            # Roll with the surface the ball actually landed on (§2.5).
            bx = pos[0] + flight.bounce_x_m[0] * C.M_TO_YARD * math.cos(aim_ang) \
                - flight.bounce_z_m[0] * C.M_TO_YARD * math.sin(aim_ang)
            by = pos[1] + flight.bounce_x_m[0] * C.M_TO_YARD * math.sin(aim_ang) \
                + flight.bounce_z_m[0] * C.M_TO_YARD * math.cos(aim_ang)
            lie_b, _, _ = self.course.determine_lie(hole, bx, by)
            mu = {"green": C.ROLL_MU["green"], "fairway": C.ROLL_MU["fairway"],
                  "rough_light": C.ROLL_MU["rough"],
                  "rough_heavy": C.ROLL_MU["rough"],
                  "bunker_fairway": C.ROLL_MU["sand"],
                  "bunker_green": C.ROLL_MU["sand"],
                  "trees": C.ROLL_MU["rough"],
                  "fringe": C.ROLL_MU["fairway"],
                  "water": C.ROLL_MU["fairway"],
                  "ob": C.ROLL_MU["fairway"]}.get(lie_b, C.ROLL_MU["fairway"])
            fx, fz, _ = apply_roll(flight.bounce_x_m, flight.bounce_z_m,
                                   flight.hvel_x_ms, flight.hvel_z_ms, mu,
                                   launch.spin_rpm, on_green=(lie_b == "green"))
            fx_yd = pos[0] + fx[0] * C.M_TO_YARD * math.cos(aim_ang) \
                - fz[0] * C.M_TO_YARD * math.sin(aim_ang)
            fy_yd = pos[1] + fx[0] * C.M_TO_YARD * math.sin(aim_ang) \
                + fz[0] * C.M_TO_YARD * math.cos(aim_ang)
            new_lie, in_water, ob = self.course.determine_lie(hole, fx_yd, fy_yd)
            # Wind carry adjustments (§4.3).
            carry_yd = float(flight.carry_yd[0])
            total_yd = float(flight.total_yd[0])
            if chosen.shot_type == "full" and wind_into >= 8:
                carry_yd *= 0.92
                total_yd *= 0.92
            elif w_along >= 8:
                carry_yd *= 1.07
                total_yd *= 1.07
            dist_pin_ft = math.hypot(pin_x - fx_yd, pin_y - fy_yd) * 3.0
            dist_pin_yd = dist_pin_ft / 3.0
            shot_penalty = 0
            if in_water:
                shot_penalty = 1
                penalties += 1
                strokes += 1  # penalty stroke (§8.3)
                dz = hole.point_at(*hole.drop_zone)
                pos, lie = dz, "fairway"
            elif ob:
                shot_penalty = 1
                penalties += 1
                strokes += 1  # stroke and distance (§8.3)
                pos, lie = prev_pos, lie  # replay from the previous spot
            else:
                pos, lie = (fx_yd, fy_yd), new_lie
                if lie == "bunker_green":
                    greenside_bunker_attempted = True
                if lie == "trees" and chosen.shot_type == "punch" \
                        and rng.random() < 0.05:
                    # Unplayable under a root (§8.3) — rare.
                    shot_penalty = 1
                    penalties += 1
                    strokes += 1
                    s_now, _ = hole.project(*pos)
                    pos = hole.point_at(max(0.0, s_now - 5), 0.0)
                    lie = "fairway"
            # Holed out from off the green (chip-in / hole-in-one).
            if not in_water and not ob and dist_pin_ft <= 0.5:
                holed = True
            # Outcome stats.
            if is_tee_shot and hole.par in (4, 5):
                fairway_hit = (lie == "fairway")
                driving_yd = round(total_yd)
            if lie == "green" and first_green_strokes is None:
                first_green_strokes = strokes
                approach_ft = round(dist_pin_ft, 1)
                if strokes <= hole.par - 2:
                    gir = True
            if first_green_strokes is not None:
                shots_after_green = strokes - first_green_strokes
            # Strokes gained for this shot.
            if holed:
                sg_shot = start_base - 1.0 - shot_penalty
            else:
                end_base = baseline_strokes(
                    lie, *self._baseline_args(hole, pos, pin_x, pin_y),
                    self.model.baseline_adjustments)
                sg_shot = start_base - (1.0 + end_base) - shot_penalty
            sg[cat] += sg_shot
            # Miss direction for the learning loop (ft, + = right of pin).
            miss_ft = self._miss_ft(prev_pos, (pin_x, pin_y), (fx_yd, fy_yd))
            records.append(ShotRecord(
                cat, self._bucket(cat, along), sg_shot, miss_ft, along))
            quality_score = self._shot_quality(quality, carry_yd,
                                               chosen.intended_carry_yd,
                                               float(flight.offline_ft[0]))
            drama = self._drama(sg_shot, holed, shot_penalty, chosen)
            emitter.emit(
                "shot_result", hole=hole_no, shot_no=strokes,
                club=chosen.club, shot_type=chosen.shot_type,
                contact={"quality": quality,
                         "strike_x_mm": round(delivery.strike_x_mm, 1),
                         "strike_y_mm": round(delivery.strike_y_mm, 1),
                         "face_deg": round(delivery.face_deg, 2),
                         "path_deg": round(delivery.path_deg, 2),
                         "club_speed_mph": round(delivery.club_speed_mph, 1)},
                launch={"ball_speed_mph": round(launch.ball_speed_mph, 1),
                        "launch_deg": round(launch.launch_deg, 1),
                        "spin_rpm": int(launch.spin_rpm),
                        "spin_axis_deg": round(launch.spin_axis_deg, 1),
                        "apex_ft": round(float(flight.apex_ft[0]), 1),
                        "carry_yd": round(carry_yd, 1),
                        "total_yd": round(total_yd, 1),
                        "curve_ft": round(float(flight.curve_ft[0]), 1),
                        "offline_ft": round(float(flight.offline_ft[0]), 1)},
                outcome={"lie": lie, "distance_to_pin_ft": round(dist_pin_ft, 1),
                         "on_green": lie == "green",
                         "fairway_hit": fairway_hit
                         if (is_tee_shot and hole.par in (4, 5)) else None,
                         "gir": gir, "hazard": hole.hazard_label or None,
                         "penalty": shot_penalty,
                         "in_water": in_water, "ob": ob},
                shot_quality=round(quality_score, 2),
                commentary=self._shot_commentary(chosen, quality, dist_pin_ft,
                                                 lie, holed),
                drama=round(drama, 2))
            if lie == "green":
                # Next iteration enters the putt sub-loop.
                pass

        hole_score = strokes
        name = score_name(hole_score, hole.par)
        if first_green_strokes is not None and not gir and putts == 1 \
                and hole_score <= hole.par:
            up_and_down = True
        elif first_green_strokes is not None and not gir:
            up_and_down = False
        if greenside_bunker_attempted:
            sand_save = bool(up_and_down)
        sg_hole = dict(sg)
        sg_hole["total"] = sum(sg.values())
        return HoleResult(hole=hole_no, par=hole.par, score=hole_score,
                          score_name=name, putts=putts,
                          fairway_hit=fairway_hit, gir=gir,
                          penalties=penalties, driving_yd=driving_yd,
                          approach_ft=approach_ft, up_and_down=up_and_down,
                          sand_save=sand_save, sg=sg_hole), records

    # -------------------------------------------------------------- helpers --
    def _baseline_args(self, hole, pos, pin_x, pin_y):
        """(distance_yd, distance_ft) for the baseline table at a position."""
        along, straight = self.course.distance_to_pin(hole, *pos)
        return along, math.hypot(pin_x - pos[0], pin_y - pos[1]) * 3.0

    def _miss_ft(self, prev_pos, pin, final_pos):
        """Signed lateral miss vs the pin, feet (+ = right of the pin)."""
        dx, dy = pin[0] - prev_pos[0], pin[1] - prev_pos[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / d, dx / d
        rel_x, rel_y = final_pos[0] - pin[0], final_pos[1] - pin[1]
        return (rel_x * nx + rel_y * ny) * 3.0

    def _bucket(self, category: str, distance_yd: float) -> str:
        if category == "app":
            for lo, hi in ((100, 125), (125, 150), (150, 175), (175, 200),
                           (200, 9999)):
                if lo <= distance_yd < hi:
                    return f"app_{lo}_{hi}"
            return "app_0_100"
        if category == "ott":
            return "ott"
        if category == "arg":
            return "arg"
        return "putt"

    def _putt_bucket(self, distance_ft: float) -> str:
        if distance_ft <= 6:
            return "putt_0_6"
        if distance_ft <= 15:
            return "putt_6_15"
        return "putt_15_plus"

    def _trees_block(self, hole, pos, pin_x, pin_y) -> bool:
        """Is the direct line to the pin blocked by trees (§4.4)?"""
        s0, _ = hole.project(*pos)
        s1, _ = hole.project(pin_x, pin_y)
        for t in hole.trees:
            if s0 < t.s_yd < s1:
                # Lateral distance from the line ball->pin at the tree's s.
                frac = (t.s_yd - s0) / max(1.0, s1 - s0)
                lx = pos[0] + (pin_x - pos[0]) * frac
                ly = pos[1] + (pin_y - pos[1]) * frac
                if math.hypot(t.s_yd - s0, 0) >= 0 and \
                        math.hypot(lx - hole.point_at(t.s_yd, t.lateral_yd)[0],
                                   ly - hole.point_at(t.s_yd, t.lateral_yd)[1]) \
                        <= t.r_ft / 3.0 + 4:
                    return True
        return False

    def _aim_label(self, cand: Candidate, sit: Situation) -> str:
        if cand.shot_type == "putt":
            return "the hole"
        if abs(cand.aim_offset_ft) < 2:
            return "the pin"
        side = "right" if cand.aim_offset_ft > 0 else "left"
        return f"{abs(cand.aim_offset_ft):.0f} ft {side} of the pin"

    def _shot_quality(self, quality: str, carry_yd: float,
                      intended_carry_yd: float, offline_ft: float) -> float:
        base = {"pure": 0.92, "thin": 0.62, "chunk": 0.42, "toe": 0.72,
                "heel": 0.72, "shank": 0.10}[quality]
        q = base - abs(carry_yd - intended_carry_yd) / 120.0 \
            - abs(offline_ft) / 150.0
        return max(0.05, min(1.0, q))

    def _drama(self, sg_shot: float, holed: bool, penalty: int,
               cand: Candidate) -> float:
        d = 0.15 + 0.45 * abs(sg_shot)
        if holed:
            d += 0.45
        if penalty:
            d += 0.25
        if cand.shot_type in ("draw", "fade"):
            d += 0.10
        return max(0.0, min(1.0, d))

    def _shot_commentary(self, cand, quality, dist_pin_ft, lie, holed):
        if holed:
            return "He's holed it! From off the green — are you kidding?"
        if lie == "green":
            return (f"{cand.shot_type.title()} finds the green — "
                    f"{dist_pin_ft:.0f} feet left.")
        if lie == "water":
            return "That's in the water. A costly one."
        if lie == "ob":
            return "Out of bounds. He'll have to reload."
        if quality == "chunk":
            return "Chunked it — heavy contact, and it comes up well short."
        if quality == "thin":
            return "Thinned it — low and hot, running through the back."
        if quality in ("toe", "heel"):
            return f"Off the {quality} — it leaks away from the target."
        if quality == "shank":
            return "Oh no — a shank. That one rockets right."
        if lie == "fairway":
            return "Piped down the middle. A perfect spot."
        return f"Into the {lie.replace('_', ' ')} — work to do from there."

    def _putt_commentary(self, res, dist_ft):
        if res["made"]:
            return (f"{dist_ft:.0f} feet, "
                    f"{res['break_dir'].replace('_', ' ')} — and he pours it in.")
        return f"The {dist_ft:.0f}-footer slides by — {res['leave_ft']:.0f} feet left."

    def _hole_commentary(self, hr, hole, score_so_far, par_so_far, watch_state):
        name = hr.score_name.replace("_", " ")
        base = (f"{name.title()} at the {hole.name}. "
                f"{score_so_far - par_so_far:+d} through {hr.hole}.")
        if watch_state.status == "on_pace":
            return base + " The Road to 59 is alive."
        if watch_state.status == "gone":
            return base + " The 59 is gone for today — but the round goes on."
        return base

    def _round_stats(self, holes: list[HoleResult]) -> dict:
        fw = [h for h in holes if h.fairway_hit is not None]
        fw_hit = sum(1 for h in fw if h.fairway_hit)
        gir_hit = sum(1 for h in holes if h.gir)
        putts = sum(h.putts for h in holes)
        gir_putts = sum(h.putts for h in holes if h.gir)
        ud_att = [h for h in holes if h.up_and_down is not None]
        ud_made = sum(1 for h in ud_att if h.up_and_down)
        ss_att = [h for h in holes if h.sand_save is not None]
        ss_made = sum(1 for h in ss_att if h.sand_save)
        drives = [h.driving_yd for h in holes if h.driving_yd]
        approaches = [h.approach_ft for h in holes if h.approach_ft is not None]
        prox = {}
        for lo, hi in ((100, 125), (125, 150), (150, 175), (175, 200)):
            vals = [h.approach_ft for h in holes
                    if h.approach_ft is not None]
            prox[f"prox_{lo}_{hi}_ft"] = (round(sum(vals) / len(vals), 1)
                                         if vals else None)
        return {
            "fairways": f"{fw_hit}/{len(fw)}",
            "fairway_pct": round(fw_hit / max(1, len(fw)), 2),
            "gir": f"{gir_hit}/18",
            "gir_pct": round(gir_hit / 18, 2),
            "putts": putts,
            "putts_per_gir": round(gir_putts / max(1, gir_hit), 2),
            "scrambling_pct": round(ud_made / max(1, len(ud_att)), 2),
            "sand_saves": f"{ss_made}/{len(ss_att)}",
            "driving_avg_yd": round(sum(drives) / max(1, len(drives))),
            "driving_longest_yd": max(drives) if drives else 0,
            "approach_prox_ft": round(sum(approaches) / max(1, len(approaches)), 1),
            "prox_100_125_ft": prox["prox_100_125_ft"],
            "prox_150_175_ft": prox["prox_150_175_ft"],
            "prox_175_200_ft": prox["prox_175_200_ft"],
            "penalties": sum(h.penalties for h in holes),
            "birdies": sum(1 for h in holes if h.score - h.par == -1),
            "bogeys": sum(1 for h in holes if h.score - h.par == 1),
            "eagles": sum(1 for h in holes if h.score - h.par <= -2),
        }

    def _round_records(self, score: int, emitter) -> dict:
        best = self.record_book.best_score
        prev_best = min(self.scores[:-1]) if len(self.scores) > 1 else None
        flags = {
            "course_record": best is not None and score < (prev_best or 10 ** 9),
            "personal_best": best is not None and score < (prev_best or 10 ** 9),
            "best_front9": False,
            "season_best": best is not None and score <= (prev_best or 10 ** 9),
        }
        if flags["course_record"]:
            emitter.emit("milestone", hole=18, kind="course_record",
                         text=f"New course record — {score} at Wyatt National!",
                         value=score, previous_best=prev_best)
        if self.record_book.rounds_played in (50, 100):
            emitter.emit("milestone", hole=18,
                         kind=f"rounds_milestone_{self.record_book.rounds_played}",
                         text=f"Round {self.record_book.rounds_played} of the season.",
                         value=self.record_book.rounds_played,
                         previous_best=None)
        return flags

    # -------------------------------------------------------------- persistence --
    def to_dict(self) -> dict:
        return dict(model=self.model.to_dict(),
                    scores=self.scores,
                    differentials=self.differentials,
                    handicap_index=self.handicap_index,
                    round_no=self.round_no,
                    record_book=self.record_book.to_dict(),
                    watch_book=self.watch_book.to_dict(),
                    learning_history=[[r.__dict__ for r in rnd]
                                      for rnd in self.learning.history])

    @classmethod
    def from_dict(cls, data: dict, **kwargs) -> "RoundEngine":
        eng = cls(**kwargs)
        eng.model = GolferModel.from_dict(data["model"])
        eng.scores = list(data["scores"])
        eng.differentials = list(data["differentials"])
        eng.handicap_index = data["handicap_index"]
        eng.round_no = data["round_no"]
        for rnd in data.get("learning_history", []):
            eng.learning.history.append([ShotRecord(**r) for r in rnd])
        return eng

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str, **kwargs) -> "RoundEngine":
        with open(path) as f:
            return cls.from_dict(json.load(f), **kwargs)

    def play_rounds(self, n: int):
        """Play n consecutive rounds (the loop never ends, §8.1)."""
        return [self.play_round() for _ in range(n)]
