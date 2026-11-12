"""59 Watch — the live Road to 59 tracker (season framing, spec §7.3).

59 is the number. This module tracks, hole by hole, whether Mas is on the
pace line for a sub-60 round, how many strokes he can still afford to drop,
and a live probability of breaking 60 — then hands the broadcast the
moments: on pace, off pace, back on pace, and the 18th-hole "59 on the
line" moment.

Pace arithmetic (§7.5): 59 on a par-72 course is -13. After ``n`` holes,
the expected score at pace is ``par_played + (-13) * n / 18``.
``strokes_vs_pace`` is the actual score minus that expectation (negative =
ahead of pace). The operational version the broadcast shows is
``strokes_remaining = 59 - (score_so_far + par_remaining)`` — the number of
over-par strokes he can still afford on the remaining holes and shoot 59.

Probability model: each remaining hole's score is treated as an independent
normal with mean ``par + delta`` (delta = his average strokes over par per
hole from the last 10 rounds, nudged by form) and sigma 1.0 strokes. The
probability of breaking 60 is then P(total <= 59) under that normal. It is
a transparent, explainable model — not a learned predictor — and it is
labelled as an estimate wherever it is shown.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

TARGET_SCORE = 59
PAR_TOTAL = 72
PACE_TO_PAR = TARGET_SCORE - PAR_TOTAL  # -13

# Pace statuses. "on_the_line" and "secured" only occur on hole 18.
STATUS_ON_PACE = "on_pace"
STATUS_OFF_PACE = "off_pace"
STATUS_ON_THE_LINE = "on_the_line"
STATUS_SECURED = "secured"
STATUS_GONE = "gone"

HOLE_SCORE_SIGMA = 1.0  # per-hole score standard deviation (strokes)


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def probability_break_60(score_so_far: int, holes_played: int, pars: list,
                         last10_avg: float | None = None,
                         form: str = "neutral") -> float:
    """Live P(finishing score <= 59) from the current position.

    ``last10_avg`` is the scoring average over the last 10 rounds (None
    before any rounds exist -> assume par golf). Form nudges the per-hole
    expectation by 0.05 strokes (hot = better, cold = worse).
    """
    remaining = pars[holes_played:]
    if not remaining:
        return 1.0 if score_so_far <= TARGET_SCORE else 0.0
    if last10_avg is None:
        delta = 0.0
    else:
        delta = (last10_avg - PAR_TOTAL) / 18.0
    if form == "hot":
        delta -= 0.05
    elif form == "cold":
        delta += 0.05
    mean_remaining = sum(p + delta for p in remaining)
    sd_remaining = HOLE_SCORE_SIGMA * math.sqrt(len(remaining))
    expected_total = score_so_far + mean_remaining
    p = _phi((TARGET_SCORE + 0.5 - expected_total) / sd_remaining)
    return min(0.999, max(0.001, p))


@dataclass
class WatchState:
    hole: int = 0
    score_so_far: int = 0
    strokes_vs_pace: float = 0.0
    strokes_remaining: int = 13       # strokes he can still afford to drop
    prob_break_60: float = 0.0
    status: str = STATUS_ON_PACE
    best_pace: float = 0.0            # most strokes ahead of pace, this round
    best_pace_hole: int = 0
    alive_on_18: bool = False         # 59 was still possible on the 18th tee
    on_pace_at_turn: bool = False     # on pace after hole 9

    def to_dict(self) -> dict:
        return dict(hole=self.hole, score_so_far=self.score_so_far,
                    strokes_vs_pace=round(self.strokes_vs_pace, 2),
                    strokes_remaining=self.strokes_remaining,
                    prob_break_60=round(self.prob_break_60, 3),
                    status=self.status,
                    best_pace=round(self.best_pace, 2),
                    best_pace_hole=self.best_pace_hole,
                    alive_on_18=self.alive_on_18,
                    on_pace_at_turn=self.on_pace_at_turn)


class FiftyNineWatch:
    """Tracks the 59 chase through one round."""

    def __init__(self, pars: list, last10_avg: float | None = None,
                 form: str = "neutral"):
        self.pars = list(pars)
        self.last10_avg = last10_avg
        self.form = form
        self.state = WatchState(
            prob_break_60=probability_break_60(0, 0, self.pars,
                                               last10_avg, form))
        self._last_emitted_status: str | None = None

    def update(self, hole_no: int, score_so_far: int):
        """Update after a hole is completed. Returns (state, status_changed).

        ``status_changed`` is True when the pace status moved — the engine
        emits a ``fifty_nine_watch`` event on exactly those transitions
        (on pace, off pace, back on pace, 59 on the line).
        """
        par_played = sum(self.pars[:hole_no])
        par_remaining = sum(self.pars[hole_no:])
        expected = par_played + PACE_TO_PAR * (hole_no / 18.0)
        vs_pace = score_so_far - expected
        remaining = TARGET_SCORE - (score_so_far + par_remaining)
        prob = probability_break_60(score_so_far, hole_no, self.pars,
                                    self.last10_avg, self.form)
        if hole_no == 18:
            if score_so_far + self.pars[17] <= TARGET_SCORE:
                status = STATUS_SECURED
            elif remaining >= 0:
                status = STATUS_ON_THE_LINE
            else:
                status = STATUS_GONE
        elif remaining < 0:
            status = STATUS_GONE
        elif vs_pace <= 0:
            status = STATUS_ON_PACE
        else:
            status = STATUS_OFF_PACE
        st = self.state
        st.hole = hole_no
        st.score_so_far = score_so_far
        st.strokes_vs_pace = vs_pace
        st.strokes_remaining = remaining
        st.prob_break_60 = prob
        st.status = status
        if vs_pace < st.best_pace:
            st.best_pace = vs_pace
            st.best_pace_hole = hole_no
        if hole_no == 9:
            st.on_pace_at_turn = status in (STATUS_ON_PACE,)
        if hole_no == 18:
            st.alive_on_18 = status in (STATUS_ON_THE_LINE, STATUS_SECURED)
        changed = status != self._last_emitted_status
        self._last_emitted_status = status
        return st, changed

    def status_on_tee(self, hole_no: int, score_so_far: int):
        """Status entering a hole (used for the 18th-tee 'on the line' call)."""
        if hole_no != 18:
            return None
        remaining = TARGET_SCORE - (score_so_far + self.pars[17])
        if score_so_far + self.pars[17] <= TARGET_SCORE:
            return STATUS_SECURED
        if remaining >= 0:
            return STATUS_ON_THE_LINE
        return STATUS_GONE

    def round_summary(self) -> dict:
        """Per-round 59-watch stats for the record book."""
        st = self.state
        return dict(on_pace_at_turn=st.on_pace_at_turn,
                    alive_on_18=st.alive_on_18,
                    best_pace=round(st.best_pace, 2),
                    best_pace_hole=st.best_pace_hole,
                    final_status=st.status,
                    final_prob_break_60=round(st.prob_break_60, 3),
                    closest_call=(st.score_so_far <= 62),
                    final_score=st.score_so_far)


@dataclass
class FiftyNineRecordBook:
    """Season-level 59-watch aggregates (extends the record book, §7.2)."""

    rounds_on_pace_at_turn: int = 0
    rounds_alive_on_18: int = 0
    rounds_59_achieved: int = 0
    best_pace_ever: float = 0.0
    best_pace_round: str = ""
    best_pace_hole: int = 0
    closest_calls: list = field(default_factory=list)  # (round_id, score)

    def add_round(self, round_id: str, summary: dict):
        if summary["on_pace_at_turn"]:
            self.rounds_on_pace_at_turn += 1
        if summary["alive_on_18"]:
            self.rounds_alive_on_18 += 1
        if summary["final_score"] <= TARGET_SCORE:
            self.rounds_59_achieved += 1
        if summary["best_pace"] < self.best_pace_ever:
            self.best_pace_ever = summary["best_pace"]
            self.best_pace_round = round_id
            self.best_pace_hole = summary["best_pace_hole"]
        if summary["closest_call"]:
            self.closest_calls.append((round_id, summary["final_score"]))

    def to_dict(self) -> dict:
        return dict(rounds_on_pace_at_turn=self.rounds_on_pace_at_turn,
                    rounds_alive_on_18=self.rounds_alive_on_18,
                    rounds_59_achieved=self.rounds_59_achieved,
                    best_pace_ever=round(self.best_pace_ever, 2),
                    best_pace_round=self.best_pace_round,
                    best_pace_hole=self.best_pace_hole,
                    closest_calls=self.closest_calls)
