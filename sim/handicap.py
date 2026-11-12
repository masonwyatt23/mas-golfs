"""Handicap, leaderboard aggregates, form, and Road to 59 pace (spec §7).

Display convention (§7.1): the index is stored as a signed number where
**positive = strokes better than scratch** (so +3.1 displays as ``+3.1``).
Internally, ``display_index = -(whs_index)``.
"""

from __future__ import annotations

import math

from . import constants as C


def differential(score: int, rating: float = C.COURSE_RATING,
                 slope: float = C.COURSE_SLOPE) -> float:
    """WHS differential for one round (§7.1). Negative is good."""
    return (score - rating) * 113.0 / slope


def whs_index(differentials: list) -> float | None:
    """Simplified WHS index from the most recent 20 differentials (§7.1).

    Returns the *display* index (positive = better than scratch), or None
    when fewer than 3 rounds exist ("establishing").
    """
    diffs = sorted(differentials[-20:])
    n = len(differentials)
    if n < 3:
        return None
    if n >= 20:
        k = 8
    else:
        k = C.WHS_BEST_OF[n]
    best = diffs[:k]
    whs = (sum(best) / len(best)) * 0.96
    return -whs


def form_from_scores(scores: list) -> str:
    """Form derived from data, never set (§7.4)."""
    if len(scores) < 10:
        return "neutral"
    last3 = sum(scores[-3:]) / 3.0
    last10 = sum(scores[-10:]) / 10.0
    if last3 <= last10 - 1.5:
        return "hot"
    if last3 >= last10 + 1.5:
        return "cold"
    return "neutral"


def pace_59(score_so_far: int, holes_played: int, pars: list) -> dict:
    """Road to 59 pace arithmetic (§7.5).

    Operational version: ``strokes_remaining_vs_59 = 59 - (score_so_far +
    par_remaining)``. Positive means he can still afford that many
    over-par strokes on the remaining holes and shoot 59.
    """
    par_played = sum(pars[:holes_played])
    par_remaining = sum(pars[holes_played:])
    expected_at_pace = par_played + (-13) * (holes_played / 18.0)
    score_vs_target = score_so_far - expected_at_pace
    strokes_remaining = 59 - (score_so_far + par_remaining)
    return dict(score_vs_target=score_vs_target,
                strokes_to_59_pace=strokes_remaining,
                pace_alive=strokes_remaining >= 0)


class RecordBook:
    """Leaderboard aggregates computed from completed rounds (§7.2)."""

    def __init__(self):
        self.scores: list[int] = []
        self.round_ids: list[str] = []
        self.handicap_history: list[float] = []
        self.best_front9: int | None = None
        self.best_back9: int | None = None
        self.streak_under_par: int = 0
        self.best_streak_under_par: int = 0

    def add_round(self, score: int, round_id: str, front9: int, back9: int,
                  handicap_index: float | None):
        self.scores.append(score)
        self.round_ids.append(round_id)
        if handicap_index is not None:
            self.handicap_history.append(handicap_index)
        if self.best_front9 is None or front9 < self.best_front9:
            self.best_front9 = front9
        if self.best_back9 is None or back9 < self.best_back9:
            self.best_back9 = back9
        if score < C.COURSE_PAR:
            self.streak_under_par += 1
            self.best_streak_under_par = max(self.best_streak_under_par,
                                             self.streak_under_par)
        else:
            self.streak_under_par = 0

    # -- aggregates ---------------------------------------------------------
    @property
    def rounds_played(self) -> int:
        return len(self.scores)

    @property
    def best_score(self) -> int | None:
        return min(self.scores) if self.scores else None

    @property
    def worst_score(self) -> int | None:
        return max(self.scores) if self.scores else None

    @property
    def last10_avg(self) -> float | None:
        if not self.scores:
            return None
        return sum(self.scores[-10:]) / min(10, len(self.scores))

    @property
    def all_time_to_par(self) -> int:
        return sum(s - C.COURSE_PAR for s in self.scores)

    @property
    def last10_to_par(self) -> int:
        return sum(s - C.COURSE_PAR for s in self.scores[-10:])

    @property
    def rounds_under_70(self) -> int:
        return sum(1 for s in self.scores if s < 70)

    @property
    def strokes_from_59(self) -> int | None:
        if self.best_score is None:
            return None
        return self.best_score - C.TARGET_SCORE

    def to_dict(self) -> dict:
        return dict(rounds_played=self.rounds_played,
                    best_score=self.best_score,
                    worst_score=self.worst_score,
                    last10_avg=self.last10_avg,
                    all_time_to_par=self.all_time_to_par,
                    last10_to_par=self.last10_to_par,
                    rounds_under_70=self.rounds_under_70,
                    strokes_from_59=self.strokes_from_59,
                    best_front9=self.best_front9,
                    best_back9=self.best_back9,
                    handicap_history=self.handicap_history)
