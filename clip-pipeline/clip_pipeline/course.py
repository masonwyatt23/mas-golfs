"""Wyatt National course data.

Mirrors docs/course-design.md. The clip pipeline only needs par, yardage,
and hole names (for titles and captions); the sim engine owns the full
course model.
"""

COURSE = {
    "name": "Wyatt National",
    "par": 72,
    "yardage": 7214,
    "rating": 74.6,
    "slope": 138,
    "location": "Staunton, Virginia",
}

HOLES = {
    1: {"par": 4, "yards": 412, "name": "The Handshake"},
    2: {"par": 5, "yards": 578, "name": "The Reach"},
    3: {"par": 3, "yards": 187, "name": "The Postage Stamp"},
    4: {"par": 4, "yards": 448, "name": "The Examination"},
    5: {"par": 4, "yards": 376, "name": "The Temptation"},
    6: {"par": 4, "yards": 431, "name": "The Dogleg"},
    7: {"par": 5, "yards": 552, "name": "The Valley"},
    8: {"par": 3, "yards": 226, "name": "The Long One"},
    9: {"par": 4, "yards": 402, "name": "The Return"},
    10: {"par": 4, "yards": 419, "name": "The Turn"},
    11: {"par": 5, "yards": 591, "name": "The Monster"},
    12: {"par": 3, "yards": 164, "name": "The Picture"},
    13: {"par": 4, "yards": 455, "name": "The Grind"},
    14: {"par": 4, "yards": 388, "name": "The Gambler"},
    15: {"par": 5, "yards": 545, "name": "The Eagle Chance"},
    16: {"par": 3, "yards": 203, "name": "The Test"},
    17: {"par": 4, "yards": 427, "name": "The Penultimate"},
    18: {"par": 4, "yards": 410, "name": "The Closer"},
}

# Road to 59: par 72 course, so 59 pace is 13 under par.
TARGET_SCORE = 59
PACE_TO_PAR = TARGET_SCORE - COURSE["par"]  # -13


def hole_name(hole: int) -> str:
    return HOLES[hole]["name"]


def hole_par(hole: int) -> int:
    return HOLES[hole]["par"]


def score_vs_target(score_to_par: int, holes_completed: int) -> int:
    """Strokes vs. the Road to 59 pace after `holes_completed` holes.

    Positive = behind pace. Pace after h holes is -13 * h / 18.
    """
    pace = PACE_TO_PAR * holes_completed / 18.0
    return int(round(score_to_par - pace))
