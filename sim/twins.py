"""Guest digital twins — Path C (stat profile) — guest-twins.md §2–§3.

A guest twin is a **calibrated skill model, not a likeness**: the same
physics and the same decision engine as Mas, with only the *delivery
distribution* changed (guest-twins.md §1). No face, no voice, no body.
The twin card shows calibrated numbers; the guest approves it before any
match airs (§3.5, §8); one twin per guest (§8).

Path C is the no-video path: handicap + honest answers to five questions
(usual miss, best part, worst part, aggressive/conservative, one proud
number). Calibration comes from the handicap-benchmark tables (§3.2).
Paths A and B plug into the same builder — see "PATH A / PATH B PLUG-IN"
at the end of this docstring.

How a twin plays (the injection points — no existing sim file is edited):

* ``GolferModel`` (learning.py) carries what the engine reads from the
  golfer object: risk-threshold delta (aggression), aim biases (zeroed
  for a twin — a guest has no learned correction), and form ("neutral").
* ``twin_overrides`` temporarily installs the twin's delivery table:
  ``constants.CLUBS`` entries are replaced with scaled copies (speed
  means and sigmas), ``SHAPE_FACE_BIAS["straight"]`` carries the usual
  miss, and ``putting.make_probability`` is wrapped with the twin's
  putt multiplier. Everything is restored on exit. Single-threaded,
  headless use only — the override is process-global while installed.
* Validation (§3.4) plays a real headless round through ``RoundEngine``
  (Monte Carlo decisions, never the fast smoke path — fast mode scores
  ~12 strokes off the real engine and cannot validate anything) and
  checks scoring / driving / fairways / GIR against the benchmark
  bands. If it fails, ``calibrate_twin`` adjusts **only** the delivery
  distribution (speed factor, sigma multiplier) — never the physics —
  and re-plays, bounded to ``max_rounds`` attempts.

Honesty rules enforced in code (guest-twins.md §1, §3.2, §8):

* A twin is only better than the guest if the guest's numbers say so:
  every claimed number is checked against the handicap benchmark and a
  vanity claim is calibrated *down* to the benchmark, with the
  adjustment recorded on the twin (``calibration_notes``) and shown on
  the card. Strength/weakness adjustments are bounded to one handicap
  band (speed ±4%, sigmas ≤20%, putt multiplier ±10%).
* No invented results: the card shows calibrated numbers; the validation
  record shows the numbers the twin *actually* played. The two are kept
  separate and never mixed.
* No match airs without approval: ``can_air`` requires a passed
  validation (running mean of validation rounds, §3.4) AND guest
  approval AND a non-retired twin.
* One twin per guest: ``TwinRegistry`` refuses a second twin for the
  same guest; a re-submission *re-calibrates* the one twin (approval
  resets) instead of creating another.

PATH A / PATH B PLUG-IN (how the other two submission paths land here):

* Both paths end at the same place: a ``TwinProfile``. They differ only
  in how much of it is *measured* vs estimated. ``build_twin`` accepts
  an optional ``measured`` dict — that is the plug-in point.
* Path A (phone video, §2): the video intake produces
  ``measured = {"handedness": ..., "shot_shape": "draw"/"fade"/"straight",
  "face_bias_deg": ..., "tempo": ...}`` plus a sanity check on the
  claimed numbers (a smooth balanced swing attached to a 300-yard claim
  is believable; the same claim on a swing that loses its balance is
  calibrated down — the intake writes the downgrade into
  ``calibration_notes``). Tempo is descriptive (shown on the card) until
  the engine has a tempo parameter; it does not change the delivery.
* Path B (launch-monitor export, §2): the export produces
  ``measured = {"club_speed_mph": ..., "ball_speed_mph": ...,
  "carry_yd": ..., "sig_face_deg": ..., "sig_path_deg": ...,
  "spin_rpm": ...}`` (10+ driver shots, 10+ 7-iron shots). ``carry_yd``
  overrides the speed factor (``sqrt((carry + roll) / Mas measured
  driver mean)``); ``sig_face_deg``
  / ``sig_path_deg`` override the sigma multiplier (ratio to Mas's
  driver sigmas, 1.15° / 1.30°). Measured values replace the benchmark
  estimates for the fields they cover and are marked
  ``measured=True`` on the profile; everything else still comes from
  the benchmark tables. A monitor export never *widens* a tolerance:
  measured dispersion replaces the table, it does not add to it.
* Either path can re-calibrate an existing twin (``TwinRegistry.
  recalibrate``) — the twin keeps its record and its name; only the
  numbers change, and approval resets.
"""

from __future__ import annotations

import contextlib
import copy
import math
import re

from . import constants as C
from . import putting
from .course import WYATT_NATIONAL
from .engine import RoundEngine
from .learning import GolferModel

# --------------------------------------------------------------------------
# Handicap-benchmark tables (guest-twins.md §3.2).
#
# Keyed by strokes over scratch (sos): Mas is +3 -> sos = -3; a scratch
# golfer is 0; a 12-handicapper is 12. The doc's table is the anchor; the
# putts row is a documented estimate (the doc gives no putts-by-handicap
# table): ~29.5 at +3 rising ~0.25 putts per stroke over scratch.
# --------------------------------------------------------------------------
_BENCHMARK_ANCHORS = {
    # sos: (driving_yd, fairway_pct, gir_pct, scoring_avg, putts_per_round)
    -3: (270.0, 0.575, 0.56, 73.0, 29.5),
    0: (251.5, 0.50, 0.56, 73.0, 30.0),
    5: (245.0, 0.50, 0.52, 77.0, 30.5),
    10: (235.0, 0.48, 0.45, 82.0, 31.5),
    15: (225.0, 0.45, 0.38, 87.0, 32.5),
    20: (215.0, 0.42, 0.32, 92.0, 33.5),
}
_BENCHMARK_SOS_MIN = -3   # better than Mas: clamped to Mas's row, never extrapolated
_BENCHMARK_SOS_MAX = 20

# Sigma-multiplier anchors (delivery dispersion vs Mas = 1.00). These are
# *starting estimates* — the validation loop (§3.4) is the calibration:
# if a twin plays outside its bands, sigma is adjusted and re-played.
_SIGMA_ANCHORS = {-3: 1.00, 0: 1.10, 5: 1.35, 10: 1.65, 15: 2.00, 20: 2.40}

# Validation bands (guest-twins.md §3.4).
BAND_SCORING_STROKES = 3.0
BAND_DRIVING_YD = 8.0
BAND_PCT_POINTS = 0.10
MAX_LONGEST_DRIVE_OVER_BENCHMARK_YD = 75.0
# The doc's example is a 340-yard drive from a 15-handicapper (+115 yd).
# A single long drive with roll and wind can run ~70 yd past a mean, so
# the cap flags the physically implausible, not a long day: Mas himself
# has hit 322 in a Monte Carlo round (benchmark 270), and a scratch
# twin 309 (benchmark 251.5) — both must pass this check.
MAX_LONG_PUTTS_MADE = 1          # putts holed from >= 40 ft, per round
LONG_PUTT_FT = 40.0

# Claim tolerances (guest-twins.md §3.2): a claim better than the benchmark
# by more than this is calibrated down to the benchmark, not believed.
CLAIM_DRIVING_TOL_YD = 15.0
CLAIM_FAIRWAY_TOL_PTS = 0.10
CLAIM_PUTTS_TOL = 2.0

# Sigma scaling (guest-twins.md §3.2) — two rates, one lever.
#
# Direction sigmas (face/path) scale fully with the handicap multiplier:
# they drive offline dispersion, and the validation rounds confirm the
# fairway percentages land on benchmark with this scaling.
#
# Strike sigmas (strike x/y, speed) scale at HALF rate and cap — the
# mishit thresholds in physics.classify_contact are ABSOLUTE (toe >8 mm,
# shank <-14 mm), so linear scaling explodes the tail rates
# nonlinearly: at the full 1.79x a 12-handicapper shanked 14.7% of
# drives (measured, 1,500-shot diagnostic) vs ~1.6% for Mas, and only
# 32% of drives were pure (ball speed 136.7 mph vs ~148 expected).
# Real golfers' strike quality degrades far slower than their direction.
_STRIKE_DAMPING = 0.5
_STRIKE_MULT_CAP = 1.25       # strike multiplier ceiling, all handicaps


def strike_mult_for_sigma(sigma_mult: float) -> float:
    """Strike-sigma multiplier for a direction-sigma multiplier.

    Damped (half rate) and capped: the absolute mishit thresholds mean
    strike dispersion must grow gently, or the twin shanks its way to a
    scoring average no real golfer at that handicap has.
    """
    return min(_STRIKE_MULT_CAP, 1.0 + (sigma_mult - 1.0) * _STRIKE_DAMPING)
_FACE_BIAS_DEG = 1.0             # usual-miss bias, engine frame
_RISK_DELTA_AGGRESSIVE = -0.03   # lower threshold -> takes the hero line more
_RISK_DELTA_CONSERVATIVE = 0.03

# Club classes in constants.CLUBS (see "cls" per club).
_DRIVER_CLS = ("driver",)
_IRON_CLS = ("long_iron", "mid_iron", "short_iron")
_WEDGE_CLS = ("wedge",)

# best_part / worst_part -> (strength name, weakness name, one-liners).
_PART_EFFECTS = {
    "driving": (
        ("long", "Long and wild — drives it past the benchmark, misses more fairways."),
        ("wild off the tee", "Wild off the tee — the big miss lives on the tee box."),
    ),
    "irons": (
        ("pure irons", "Pure irons — approaches fly tighter than the handicap says."),
        ("loose irons", "Loose irons — approaches leak wider than the handicap says."),
    ),
    "short game": (
        ("sharp short game", "Sharp short game — chips and pitches stay close."),
        ("shaky short game", "Shaky short game — chips and pitches wander."),
    ),
    "putting": (
        ("great putter", "Great putter — holes more than the handicap says."),
        ("cold putter", "Cold putter — leaves more than the handicap says."),
    ),
}

_PART_ALIASES = {
    "driver": "driving", "drives": "driving", "tee": "driving",
    "iron": "irons", "approach": "irons", "approach play": "irons",
    "short_game": "short game", "shortgame": "short game",
    "chipping": "short game", "chips": "short game",
    "putter": "putting", "putts": "putting", "flat stick": "putting",
    "sand": "short game", "bunker": "short game", "bunkers": "short game",
}

# NOTE (guest-twins.md §3.3): "terrible from sand" and "clutch" are named
# in the doc but are NOT modeled in v1 — sand needs a lie-dependent sigma
# and clutch needs a hole-dependent sigma, and the engine exposes neither.
# A worst part of "sand"/"bunker" maps to the short-game weakness above;
# the card records the guest's own words so the gap is visible, not hidden.


def _interp(x: float, anchors: dict[float, float]) -> float:
    """Linear interpolation over a sorted anchor table, clamped at the ends."""
    keys = sorted(anchors)
    if x <= keys[0]:
        return anchors[keys[0]]
    if x >= keys[-1]:
        return anchors[keys[-1]]
    for lo, hi in zip(keys, keys[1:]):
        if lo <= x <= hi:
            t = (x - lo) / (hi - lo)
            return anchors[lo] + t * (anchors[hi] - anchors[lo])
    return anchors[keys[-1]]  # unreachable


def benchmark_for_handicap(strokes_over_scratch: float) -> dict:
    """Benchmark row for a handicap (guest-twins.md §3.2, Table).

    ``strokes_over_scratch``: -3 = Mas (+3), 0 = scratch, 12 = a
    12-handicapper. Clamped to [-3, 20] — never extrapolated past Mas on
    the good side or past a 20 on the other.
    """
    sos = min(_BENCHMARK_SOS_MAX, max(_BENCHMARK_SOS_MIN, strokes_over_scratch))
    row = {}
    for i, key in enumerate(("driving_yd", "fairway_pct", "gir_pct",
                             "scoring_avg", "putts_per_round")):
        row[key] = _interp(sos, {k: v[i] for k, v in _BENCHMARK_ANCHORS.items()})
    row["strokes_over_scratch"] = sos
    return row


def sigma_mult_for_handicap(strokes_over_scratch: float) -> float:
    """Starting delivery-sigma multiplier vs Mas (1.00). An estimate —
    the validation loop is the calibration."""
    sos = min(_BENCHMARK_SOS_MAX, max(_BENCHMARK_SOS_MIN, strokes_over_scratch))
    return _interp(sos, _SIGMA_ANCHORS)


# Mas's driver-only mean total distance, measured on the current engine:
# 6 Monte Carlo rounds (mc_n=60), driver tee shots on par 4/5 only —
# 271.4, 282.2, 274.9, 291.7, 277.8, 306.1 (mean 284.0). The engine-stat
# mean over the same rounds was 263.7: the gap is the 3-wood layups the
# decision engine takes on some par 5s. Measured 2026-11-13; re-measure
# if the flight model changes.
MAS_DRIVER_MEAN_YD = 284.0
# Mean roll-out behind a drive at Mas's speed (diagnostic, 1,500 shots,
# calm/flat/firmness 0.6): total 282.2 - carry 261.6 = 20.6 yd. Used to
# convert a measured Path B carry into an equivalent total distance.
MAS_DRIVER_ROLL_YD = 20.6


def speed_factor_for_driving(driving_yd: float) -> float:
    """Club-speed factor for a target driving distance.

    Carry is ~v^2 at fixed launch, so speed scales as sqrt(distance).
    Normalised to Mas's MEASURED driver-only mean in the current engine
    (``MAS_DRIVER_MEAN_YD``) — not to the spec's 270 yd target, because
    the engine as it stands drives Mas ~14 yd past the spec target and
    a spec-anchored factor would make every twin drive long. The anchor
    is a measured estimate (6 Monte Carlo rounds, mean 284 yd, range
    271-306 — the round-to-round spread is conditions, mostly firmness
    and wind); if the flight-model retune moves Mas's mean, re-measure
    it. The validation loop is the backstop: it corrects any residual
    anchor error per twin.
    """
    return math.sqrt(max(50.0, driving_yd) / MAS_DRIVER_MEAN_YD)


# --------------------------------------------------------------------------
# Path C submission (guest-twins.md §2, Path C).
# --------------------------------------------------------------------------
def _norm_part(value: str) -> str:
    v = value.strip().lower()
    return _PART_ALIASES.get(v, v)


def _parse_miss(miss: str) -> str:
    """Usual miss -> 'right' / 'left' / 'straight' (the guest's own side)."""
    v = miss.strip().lower()
    if any(w in v for w in ("right", "slice", "fade", "block", "push")):
        return "right"
    if any(w in v for w in ("left", "hook", "draw", "pull")):
        return "left"
    return "straight"


class StatProfile:
    """A Path C submission: handicap + the five honest questions.

    ``handicap`` is the signed WHS index (guest-twins.md §3.1): positive
    is better than scratch, same convention as Mas's +3.1 — so a
    12-handicapper submits ``handicap=-12`` and a scratch golfer ``0``.
    ``between_clubs``: "extra" (takes the extra club — the conservative
    play, more loft and a smooth swing) or "smooth" (takes the smooth
    one — less club, full swing, the aggressive play). The words
    "aggressive" / "conservative" are accepted as well.
    """

    def __init__(self, name: str, handicap: float, miss: str,
                 best_part: str, worst_part: str, between_clubs: str,
                 proud_number: str = "", handedness: str = "right",
                 driving_distance_yd: float | None = None,
                 fairway_pct: float | None = None,
                 putts_per_round: float | None = None):
        self.name = name.strip()
        if not self.name:
            raise ValueError("guest name is required")
        self.handicap = float(handicap)
        if not -30.0 <= self.handicap <= 5.0:
            raise ValueError(f"handicap {handicap} outside [-30, +5]")
        self.miss = miss.strip()
        self.best_part = _norm_part(best_part)
        self.worst_part = _norm_part(worst_part)
        if self.best_part not in _PART_EFFECTS:
            raise ValueError(f"unknown best part: {best_part!r}")
        if self.worst_part not in _PART_EFFECTS:
            raise ValueError(f"unknown worst part: {worst_part!r}")
        if self.best_part == self.worst_part:
            raise ValueError("best part and worst part cannot be the same")
        bc = between_clubs.strip().lower()
        if bc in ("extra", "extra club", "conservative", "safe"):
            self.between_clubs = "extra"
        elif bc in ("smooth", "smooth one", "aggressive", "go for it"):
            self.between_clubs = "smooth"
        elif bc in ("neutral", "either", "depends"):
            self.between_clubs = "neutral"
        else:
            raise ValueError(f"unknown between-clubs answer: {between_clubs!r}")
        self.proud_number = proud_number.strip()
        h = handedness.strip().lower()
        if h not in ("left", "right"):
            raise ValueError(f"handedness must be 'left' or 'right', got {handedness!r}")
        self.handedness = h
        self.driving_distance_yd = driving_distance_yd
        self.fairway_pct = fairway_pct
        self.putts_per_round = putts_per_round

    @property
    def strokes_over_scratch(self) -> float:
        """Strokes over scratch: -3 for Mas, 0 scratch, 12 for a 12-handicapper."""
        return -self.handicap

    def to_dict(self) -> dict:
        return dict(name=self.name, handicap=self.handicap, miss=self.miss,
                    best_part=self.best_part, worst_part=self.worst_part,
                    between_clubs=self.between_clubs,
                    proud_number=self.proud_number,
                    handedness=self.handedness,
                    driving_distance_yd=self.driving_distance_yd,
                    fairway_pct=self.fairway_pct,
                    putts_per_round=self.putts_per_round)

    @classmethod
    def from_dict(cls, data: dict) -> "StatProfile":
        return cls(**data)


# --------------------------------------------------------------------------
# Claim checking (guest-twins.md §3.2): vanity claims calibrate down.
# --------------------------------------------------------------------------
def _check_claims(profile: StatProfile, benchmark: dict) -> tuple[dict, list[str]]:
    """Apply the guest's stated numbers where plausible; clamp vanity.

    Returns (accepted_numbers, notes). Accepted numbers are the ones the
    twin is actually built from — the benchmark where a claim was
    clamped, the claim where it was plausible.
    """
    accepted = dict(
        driving_yd=benchmark["driving_yd"],
        fairway_pct=benchmark["fairway_pct"],
        putts_per_round=benchmark["putts_per_round"],
    )
    notes: list[str] = []
    if profile.driving_distance_yd is not None:
        claimed = profile.driving_distance_yd
        if claimed > benchmark["driving_yd"] + CLAIM_DRIVING_TOL_YD:
            notes.append(
                f"Claimed {claimed:.0f} yd driving — calibrated to the "
                f"{benchmark['strokes_over_scratch']:.0f}-handicap benchmark "
                f"of {benchmark['driving_yd']:.0f} yd, not the claim.")
        else:
            accepted["driving_yd"] = claimed
    if profile.fairway_pct is not None:
        claimed = profile.fairway_pct
        if claimed > benchmark["fairway_pct"] + CLAIM_FAIRWAY_TOL_PTS:
            notes.append(
                f"Claimed {claimed:.0%} fairways — calibrated to the "
                f"benchmark of {benchmark['fairway_pct']:.0%}, not the claim.")
        else:
            accepted["fairway_pct"] = claimed
    if profile.putts_per_round is not None:
        claimed = profile.putts_per_round
        if claimed < benchmark["putts_per_round"] - CLAIM_PUTTS_TOL:
            notes.append(
                f"Claimed {claimed:.1f} putts/round — calibrated to the "
                f"benchmark of {benchmark['putts_per_round']:.1f}, not the claim.")
        else:
            accepted["putts_per_round"] = claimed
    # The proud number is free text; if it carries a recognisable stat,
    # it is checked the same way and the note goes on the card.
    if profile.proud_number:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(putts|fairway|%)", profile.proud_number.lower())
        if m:
            val = float(m.group(1))
            if "putt" in m.group(2) and val < benchmark["putts_per_round"] - CLAIM_PUTTS_TOL:
                notes.append(
                    f"Proud number ({profile.proud_number!r}) is better than "
                    f"the benchmark by more than {CLAIM_PUTTS_TOL:.0f} putts — "
                    f"calibrated to the benchmark.")
            elif ("fairway" in m.group(2) or m.group(2) == "%") and val > 100 * (
                    benchmark["fairway_pct"] + CLAIM_FAIRWAY_TOL_PTS):
                notes.append(
                    f"Proud number ({profile.proud_number!r}) is better than "
                    f"the benchmark by more than "
                    f"{CLAIM_FAIRWAY_TOL_PTS:.0%} — calibrated to the benchmark.")
    return accepted, notes


# --------------------------------------------------------------------------
# The calibrated twin.
# --------------------------------------------------------------------------
class TwinProfile:
    """A calibrated guest twin (guest-twins.md §3.1).

    Built from a ``StatProfile`` by ``build_twin`` (or from measured
    Path A/B data — see the module docstring). ``speed_factor`` /
    ``sigma_mult`` / ``putt_mult`` / ``face_bias_deg`` are the delivery
    distribution; everything else the engine does is identical to Mas.
    """

    def __init__(self, guest_name: str, handicap: float, source: str = "path_c"):
        self.guest_name = guest_name
        self.handicap = float(handicap)
        self.source = source
        self.strokes_over_scratch = -self.handicap
        self.benchmark: dict = {}
        self.speed_factor: float = 1.0
        self.sigma_mult: float = 1.0
        # Per-class multipliers on top of the global ones (strength/weakness).
        self.class_sigma_mult: dict[str, float] = {}
        self.class_speed_mult: dict[str, float] = {}
        self.putt_mult: float = 1.0
        self.face_bias_deg: float = 0.0   # engine frame (see build_twin)
        self.shot_shape: str = "straight"
        self.usual_miss: str = "straight"
        self.handedness: str = "right"
        self.risk_threshold_delta: float = 0.0
        self.strength: str | None = None
        self.weakness: str | None = None
        self.strength_line: str = ""
        self.weakness_line: str = ""
        self.calibration_notes: list[str] = []
        self.measured: dict = {}          # Path A/B measured fields, if any
        self.validation: dict | None = None
        self.validation_history: list[dict] = []
        self.approved: bool = False
        self.approved_by: str | None = None
        self.retired: bool = False
        self.retire_note: str = ""
        self.record: dict = dict(matches=0, wins=0, losses=0,
                                 best_round=None, best_score=None)

    def to_dict(self) -> dict:
        return dict(guest_name=self.guest_name, handicap=self.handicap,
                    source=self.source,
                    strokes_over_scratch=self.strokes_over_scratch,
                    benchmark=self.benchmark,
                    speed_factor=self.speed_factor,
                    sigma_mult=self.sigma_mult,
                    class_sigma_mult=self.class_sigma_mult,
                    class_speed_mult=self.class_speed_mult,
                    putt_mult=self.putt_mult,
                    face_bias_deg=self.face_bias_deg,
                    shot_shape=self.shot_shape,
                    usual_miss=self.usual_miss,
                    handedness=self.handedness,
                    risk_threshold_delta=self.risk_threshold_delta,
                    strength=self.strength, weakness=self.weakness,
                    strength_line=self.strength_line,
                    weakness_line=self.weakness_line,
                    calibration_notes=self.calibration_notes,
                    measured=self.measured,
                    validation=self.validation,
                    validation_history=self.validation_history,
                    approved=self.approved, approved_by=self.approved_by,
                    retired=self.retired, retire_note=self.retire_note,
                    record=self.record)

    @classmethod
    def from_dict(cls, data: dict) -> "TwinProfile":
        t = cls(data["guest_name"], data["handicap"], data.get("source", "path_c"))
        for k, v in data.items():
            if k in ("guest_name", "handicap", "source"):
                continue
            setattr(t, k, v)
        return t


def build_twin(profile: StatProfile, measured: dict | None = None) -> TwinProfile:
    """Calibrate a twin from a Path C profile (guest-twins.md §3).

    ``measured`` is the Path A/B plug-in: a dict of measured fields that
    replace the benchmark estimates for the fields they cover. Accepted
    keys: ``club_speed_mph``, ``carry_yd``, ``sig_face_deg``,
    ``sig_path_deg``, ``putt_mult``, ``handedness``, ``shot_shape``,
    ``face_bias_deg``. Measured values are recorded on
    ``twin.measured`` so the card can say what was measured vs estimated.
    """
    twin = TwinProfile(profile.name, profile.handicap, source="path_c")
    twin.handedness = profile.handedness
    sos = profile.strokes_over_scratch
    twin.benchmark = benchmark_for_handicap(sos)
    accepted, notes = _check_claims(profile, twin.benchmark)
    twin.calibration_notes.extend(notes)

    # Delivery: speed from the (accepted) driving distance, sigma from
    # the handicap anchors. Both are starting estimates — validation is
    # the calibration.
    twin.speed_factor = speed_factor_for_driving(accepted["driving_yd"])
    twin.sigma_mult = sigma_mult_for_handicap(sos)

    # Strength / weakness from the guest's own words (§3.3), bounded to
    # one handicap band.
    s_name, s_line = _PART_EFFECTS[profile.best_part][0]
    w_name, w_line = _PART_EFFECTS[profile.worst_part][1]
    twin.strength, twin.strength_line = s_name, s_line
    twin.weakness, twin.weakness_line = w_name, w_line
    _apply_part_effect(twin, profile.best_part, is_strength=True)
    _apply_part_effect(twin, profile.worst_part, is_strength=False)

    # Usual miss -> face bias. The engine frame's +lateral is the
    # golfer's right *for a left-handed golfer* (course.py §1.2), so a
    # right-handed guest's "miss right" is the opposite engine-frame
    # sign from a left-handed guest's. Magnitude is bounded at 1.0 deg.
    twin.usual_miss = _parse_miss(profile.miss)
    if twin.usual_miss == "right":
        twin.face_bias_deg = _FACE_BIAS_DEG if twin.handedness == "left" else -_FACE_BIAS_DEG
        twin.shot_shape = "fade"
    elif twin.usual_miss == "left":
        twin.face_bias_deg = -_FACE_BIAS_DEG if twin.handedness == "left" else _FACE_BIAS_DEG
        twin.shot_shape = "draw"
    else:
        twin.face_bias_deg = 0.0
        twin.shot_shape = "straight"

    # Aggression -> decision-engine risk threshold (§5.3). Taking the
    # extra club is the conservative play (more loft, smooth swing);
    # taking the smooth one is the aggressive play (less club, full rip).
    if profile.between_clubs == "smooth":
        twin.risk_threshold_delta = _RISK_DELTA_AGGRESSIVE
    elif profile.between_clubs == "extra":
        twin.risk_threshold_delta = _RISK_DELTA_CONSERVATIVE
    else:
        twin.risk_threshold_delta = 0.0

    # Measured overrides (Paths A/B) replace estimates, field by field.
    if measured:
        twin.source = measured.get("source", "path_c")
        twin.measured = {k: v for k, v in measured.items() if k != "source"}
        if "handedness" in measured:
            twin.handedness = measured["handedness"]
        if "shot_shape" in measured:
            twin.shot_shape = measured["shot_shape"]
        if "face_bias_deg" in measured:
            twin.face_bias_deg = float(measured["face_bias_deg"])
        if "carry_yd" in measured:
            twin.speed_factor = math.sqrt(
                (float(measured["carry_yd"]) + MAS_DRIVER_ROLL_YD)
                / MAS_DRIVER_MEAN_YD)
            twin.calibration_notes.append(
                f"Driver carry measured at {measured['carry_yd']:.0f} yd (Path B).")
        elif "club_speed_mph" in measured:
            twin.speed_factor = float(measured["club_speed_mph"]) / 110.0
            twin.calibration_notes.append(
                f"Driver club speed measured at {measured['club_speed_mph']:.0f} mph (Path B).")
        if "sig_face_deg" in measured:
            twin.sigma_mult = float(measured["sig_face_deg"]) / 1.15
            twin.calibration_notes.append(
                "Delivery dispersion measured from launch-monitor export (Path B).")
        elif "sig_path_deg" in measured:
            twin.sigma_mult = float(measured["sig_path_deg"]) / 1.30
            twin.calibration_notes.append(
                "Delivery dispersion measured from launch-monitor export (Path B).")
        if "putt_mult" in measured:
            twin.putt_mult = float(measured["putt_mult"])

    return twin


def _apply_part_effect(twin: TwinProfile, part: str, is_strength: bool) -> None:
    """Apply one strength/weakness adjustment, bounded to one band (§3.3)."""
    if part == "driving":
        if is_strength:      # "long": +4% speed, +5% driver sigma (long and wild)
            twin.class_speed_mult["driver"] = 1.04
            twin.class_sigma_mult["driver"] = 1.05
        else:                # "wild off the tee": +20% driver sigma, -2% speed
            twin.class_sigma_mult["driver"] = 1.20
            twin.class_speed_mult["driver"] = 0.98
    elif part == "irons":
        mult = 0.90 if is_strength else 1.15
        for cls in _IRON_CLS:
            twin.class_sigma_mult[cls] = mult
    elif part == "short game":
        mult = 0.88 if is_strength else 1.15
        for cls in _WEDGE_CLS:
            twin.class_sigma_mult[cls] = mult
    elif part == "putting":
        twin.putt_mult = 1.10 if is_strength else 0.90


# --------------------------------------------------------------------------
# Playing as the twin: the delivery table + the engine model.
# --------------------------------------------------------------------------
def twin_clubs(twin: TwinProfile) -> dict:
    """A scaled copy of ``constants.CLUBS`` for this twin.

    Speed means scale with ``speed_factor`` (and any per-class speed
    multiplier). Direction sigmas (face/path) scale with ``sigma_mult``
    (and any per-class direction multiplier). Strike sigmas (strike x/y,
    speed) scale at half rate via ``strike_mult_for_sigma`` and are
    handicap-driven only — a strength/weakness moves direction and
    speed, not strike quality (a wild driver misses fairways; it does
    not shank more). The reason for the split: the mishit thresholds in
    ``physics.classify_contact`` are absolute (toe >8 mm, shank <-14 mm),
    so full-rate strike scaling explodes the shank rate (measured:
    14.7% of drives at 1.79x vs ~1.6% for Mas). Returns a new dict —
    ``C.CLUBS`` is never mutated here.
    """
    strike_sig = strike_mult_for_sigma(twin.sigma_mult)
    clubs = {}
    for name, spec in C.CLUBS.items():
        cls = spec["cls"]
        s = dict(spec)
        s["speed_mean"] = spec["speed_mean"] * twin.speed_factor * \
            twin.class_speed_mult.get(cls, 1.0)
        dir_sig = twin.sigma_mult * twin.class_sigma_mult.get(cls, 1.0)
        for key in ("sig_face", "sig_path"):
            s[key] = spec[key] * dir_sig
        for key in ("sig_speed", "sig_sx", "sig_sy"):
            s[key] = spec[key] * strike_sig
        clubs[name] = s
    return clubs


def twin_model(twin: TwinProfile) -> GolferModel:
    """The engine-facing golfer model for this twin.

    Aim biases are zeroed — a guest has no learned correction to apply,
    and the usual miss is carried by the face bias, not by aiming off.
    Form is neutral; the twin does not inherit Mas's form.
    """
    model = GolferModel()
    model.aim_biases = {k: 0.0 for k in model.aim_biases}
    model.risk_threshold_delta = twin.risk_threshold_delta
    model.form = "neutral"
    return model


@contextlib.contextmanager
def twin_overrides(twin: TwinProfile):
    """Temporarily play as this twin: install its delivery distribution.

    Swaps ``C.CLUBS`` for ``twin_clubs(twin)``, sets the straight-shot
    face bias for the usual miss, and wraps ``putting.make_probability``
    with the twin's putt multiplier. Everything is restored on exit,
    even on error. Single-threaded, headless use only — the override is
    process-global while installed, so never run two twins' rounds
    concurrently in one process.
    """
    saved_clubs = {k: dict(v) for k, v in C.CLUBS.items()}
    saved_shape_bias = dict(C.SHAPE_FACE_BIAS)
    saved_make_probability = putting.make_probability
    # Build the twin's table BEFORE clearing C.CLUBS — twin_clubs reads
    # C.CLUBS, so clearing first would leave it an empty dict.
    new_clubs = twin_clubs(twin)
    try:
        C.CLUBS.clear()
        C.CLUBS.update(new_clubs)
        if twin.face_bias_deg:
            C.SHAPE_FACE_BIAS["straight"] = twin.face_bias_deg
        if twin.putt_mult != 1.0:
            mult = twin.putt_mult

            def scaled_make_probability(distance_ft, break_ft, green_speed,
                                        _orig=saved_make_probability):
                p = _orig(distance_ft, break_ft, green_speed)
                return min(0.995, max(0.001, p * mult))

            putting.make_probability = scaled_make_probability
        yield
    finally:
        C.CLUBS.clear()
        C.CLUBS.update(saved_clubs)
        C.SHAPE_FACE_BIAS.clear()
        C.SHAPE_FACE_BIAS.update(saved_shape_bias)
        putting.make_probability = saved_make_probability


# --------------------------------------------------------------------------
# Validation (§3.4): the twin plays a headless round, checked vs its profile.
# --------------------------------------------------------------------------
class ValidationResult:
    """One headless validation round, checked against the twin's benchmark.

    The per-round checks are a diagnostic record (kept in
    ``validation_history``). The AIR gate is NOT this round's ``passed``
    — it is the running MEAN across attempts (``_mean_validation``),
    because one round is too noisy to pass or fail on.
    """

    def __init__(self, twin: TwinProfile, score: int, driving_avg_yd: float,
                 driving_longest_yd: float, fairway_pct: float,
                 gir_pct: float, putts: int, long_putts_made: int,
                 seed: int, mc_n: int, round_no: int):
        self.score = score
        self.driving_avg_yd = driving_avg_yd
        self.driving_longest_yd = driving_longest_yd
        self.fairway_pct = fairway_pct
        self.gir_pct = gir_pct
        self.putts = putts
        self.long_putts_made = long_putts_made
        self.seed = seed
        self.mc_n = mc_n
        self.round_no = round_no
        b = twin.benchmark
        self.checks = {
            "scoring": abs(score - b["scoring_avg"]) <= BAND_SCORING_STROKES,
            "driving": abs(driving_avg_yd - b["driving_yd"]) <= BAND_DRIVING_YD,
            "fairway": abs(fairway_pct - b["fairway_pct"]) <= BAND_PCT_POINTS,
            "gir": abs(gir_pct - b["gir_pct"]) <= BAND_PCT_POINTS,
            "no_impossible_drive": driving_longest_yd <= b["driving_yd"] + MAX_LONGEST_DRIVE_OVER_BENCHMARK_YD,
            "no_impossible_putts": long_putts_made <= MAX_LONG_PUTTS_MADE,
        }
        self.passed = all(self.checks.values())
        self.detail = dict(
            score=score, scoring_benchmark=b["scoring_avg"],
            driving_avg_yd=round(driving_avg_yd, 1),
            driving_benchmark=b["driving_yd"],
            driving_longest_yd=round(driving_longest_yd, 1),
            fairway_pct=round(fairway_pct, 3), fairway_benchmark=b["fairway_pct"],
            gir_pct=round(gir_pct, 3), gir_benchmark=b["gir_pct"],
            putts=putts, long_putts_made=long_putts_made,
            checks=self.checks, passed=self.passed,
            seed=seed, mc_n=mc_n, round_no=round_no)

    def to_dict(self) -> dict:
        return dict(self.detail)


def _driver_shots_from_events(result, course) -> tuple[float, float]:
    """Mean and longest DRIVER distance from a round's event stream.

    The engine's ``driving_avg_yd`` stat averages every par 4/5 tee shot
    whatever the club — and the decision engine rightly lays up with
    3-wood on some par 5s. But the benchmark "driving distance" is the
    average of *driver* shots, so validation measures driver tee shots
    only (shot 1, club driver, par 4/5). Falls back to the engine stat
    if the twin somehow hit no driver all round.
    """
    totals = []
    for ev in result.events:
        if ev.get("type") != "shot_result" or ev.get("shot_no") != 1:
            continue
        if ev.get("club") != "driver":
            continue
        hole_no = ev.get("hole", 0)
        if hole_no < 1 or course.hole(hole_no).par not in (4, 5):
            continue
        total = (ev.get("launch") or {}).get("total_yd")
        if total is not None:
            totals.append(float(total))
    if not totals:
        stats = result.stats
        return (stats.get("driving_avg_yd", 0.0),
                stats.get("driving_longest_yd", 0.0))
    return sum(totals) / len(totals), max(totals)


def _count_long_putts_made(result) -> int:
    """Putts holed from >= 40 ft in a round's event stream (§3.4)."""
    n = 0
    for ev in result.events:
        if ev.get("type") == "putt_result":
            putt = ev.get("putt") or {}
            if putt.get("made") and putt.get("distance_ft", 0) >= LONG_PUTT_FT:
                n += 1
    return n


def play_validation_round(twin: TwinProfile, seed: int = 0, mc_n: int = 60,
                          round_no: int = 9001) -> ValidationResult:
    """Play one headless 18-hole validation round as this twin (§3.4).

    Monte Carlo decisions only — the fast smoke path scores ~12 strokes
    off the real engine and cannot validate anything. A fresh engine and
    a fresh model per round, so the learning loop never leaks between
    attempts. Deterministic for a fixed (seed, round_no, mc_n).
    """
    with twin_overrides(twin):
        engine = RoundEngine(course=WYATT_NATIONAL, model=twin_model(twin),
                             mc_n=mc_n, seed_offset=seed)
        engine.handicap_index = twin.handicap
        result = engine.play_round(round_no)
    stats = result.stats
    # Driving is measured on driver tee shots only (see
    # _driver_shots_from_events) — the engine stat mixes in 3-wood layups.
    driving_avg_yd, driving_longest_yd = _driver_shots_from_events(
        result, WYATT_NATIONAL)
    return ValidationResult(
        twin, score=result.score,
        driving_avg_yd=driving_avg_yd,
        driving_longest_yd=driving_longest_yd,
        fairway_pct=stats.get("fairway_pct", 0.0),
        gir_pct=stats.get("gir_pct", 0.0),
        putts=stats.get("putts", 0),
        long_putts_made=_count_long_putts_made(result),
        seed=seed, mc_n=mc_n, round_no=round_no)


def _mean_validation(twin: TwinProfile,
                     attempts: list["ValidationResult"]) -> dict:
    """The validation record for a set of attempts (§3.4).

    The gate is the RUNNING MEAN across the attempts, not any single
    round: one round's score has a ~5-6 stroke standard deviation and
    its driving average swings ~15 yd with conditions (firmness, wind),
    so a single-round gate would pass or fail a perfectly calibrated
    twin on luck. Measured 2026-11-13: Mas himself, played on this
    engine, scored 71-89 and drove 271-306 yd across six seeds — he
    would fail his own single-round gate on some of them. Even the mean
    of three rounds still carries a ~3-stroke standard error, so the
    ±3-stroke band is roughly a one-standard-error gate: a well
    calibrated twin passes it only about two times in three, and the
    loop's adjustments can chase noise. That is a property of the
    engine's round-to-round variance, not of the twin — the loop
    records the mean and the per-round results so the miss is visible
    instead of hidden. Per-round results are kept under ``rounds`` so
    nothing is hidden.
    """
    b = twin.benchmark
    n = len(attempts)
    mean = {
        "score": sum(v.score for v in attempts) / n,
        "driving_avg_yd": sum(v.driving_avg_yd for v in attempts) / n,
        "driving_longest_yd": max(v.driving_longest_yd for v in attempts),
        "fairway_pct": sum(v.fairway_pct for v in attempts) / n,
        "gir_pct": sum(v.gir_pct for v in attempts) / n,
        "putts": sum(v.putts for v in attempts) / n,
        "long_putts_made": sum(v.long_putts_made for v in attempts),
        "scoring_benchmark": b["scoring_avg"],
        "driving_benchmark": b["driving_yd"],
        "fairway_benchmark": b["fairway_pct"],
        "gir_benchmark": b["gir_pct"],
    }
    checks = {
        "scoring": abs(mean["score"] - b["scoring_avg"]) <= BAND_SCORING_STROKES,
        "driving": abs(mean["driving_avg_yd"] - b["driving_yd"]) <= BAND_DRIVING_YD,
        "fairway": abs(mean["fairway_pct"] - b["fairway_pct"]) <= BAND_PCT_POINTS,
        "gir": abs(mean["gir_pct"] - b["gir_pct"]) <= BAND_PCT_POINTS,
        "no_impossible_drive": all(v.checks["no_impossible_drive"] for v in attempts),
        "no_impossible_putts": all(v.checks["no_impossible_putts"] for v in attempts),
    }
    return {"passed": all(checks.values()), "rounds_played": n,
            "mean": mean, "checks": checks,
            "rounds": [v.to_dict() for v in attempts]}


def calibrate_twin(twin: TwinProfile, max_rounds: int = 3,
                   mc_n: int = 60) -> TwinProfile:
    """Validation loop (§3.4): play, check the running mean, adjust, re-play.

    Adjusts ONLY the delivery distribution — speed factor and sigma
    multiplier — never the physics. The gate is the running MEAN across
    attempts (see ``_mean_validation``): a single round is too noisy
    to pass or fail on. After each failed attempt the delivery is
    nudged toward the mean error: driving off by >8 yd scales the speed
    factor by sqrt(target/mean actual); scoring too high (or fairways /
    GIR too low) tightens sigma 5%; scoring too low (or fairways / GIR
    too high) loosens sigma 5%. Bounded to ``max_rounds`` attempts; the
    mean validation (pass or fail) is stored on the twin, with the full
    per-round history in ``validation_history``. A pass only counts once
    at least two rounds have been played — a one-round mean is still
    mostly noise. A twin whose mean never passes cannot air — see
    ``can_air``.
    """
    attempts: list[ValidationResult] = []
    for attempt in range(max_rounds):
        validation = play_validation_round(twin, seed=attempt, mc_n=mc_n,
                                           round_no=9001 + attempt)
        attempts.append(validation)
        twin.validation_history.append(validation.to_dict())
        twin.validation = _mean_validation(twin, attempts)
        if len(attempts) >= 2 and twin.validation["passed"]:
            return twin
        b = twin.benchmark
        n = len(attempts)
        mean = twin.validation["mean"]
        adj_speed = 1.0
        adj_sigma = 1.0
        if abs(mean["driving_avg_yd"] - b["driving_yd"]) > BAND_DRIVING_YD:
            ratio = math.sqrt(max(50.0, b["driving_yd"]) /
                              max(50.0, mean["driving_avg_yd"]))
            adj_speed = min(1.06, max(0.94, ratio))
        if mean["score"] - b["scoring_avg"] > BAND_SCORING_STROKES:
            adj_sigma *= 0.95
        elif b["scoring_avg"] - mean["score"] > BAND_SCORING_STROKES:
            adj_sigma *= 1.05
        if b["fairway_pct"] - mean["fairway_pct"] > BAND_PCT_POINTS:
            adj_sigma *= 0.95
        elif mean["fairway_pct"] - b["fairway_pct"] > BAND_PCT_POINTS:
            adj_sigma *= 1.05
        if b["gir_pct"] - mean["gir_pct"] > BAND_PCT_POINTS:
            adj_sigma *= 0.95
        elif mean["gir_pct"] - b["gir_pct"] > BAND_PCT_POINTS:
            adj_sigma *= 1.05
        twin.speed_factor = min(1.15, max(0.70, twin.speed_factor * adj_speed))
        twin.sigma_mult = min(3.5, max(0.80, twin.sigma_mult * adj_sigma))
        twin.calibration_notes.append(
            f"Validation round {attempt + 1} (score {validation.score}, "
            f"driving {validation.driving_avg_yd:.0f} yd) — running mean "
            f"over {n} round(s) is score {mean['score']:.1f}, "
            f"driving {mean['driving_avg_yd']:.0f} yd — delivery adjusted "
            f"(speed x{adj_speed:.3f}, sigma x{adj_sigma:.3f}); "
            f"physics untouched.")
    return twin


# --------------------------------------------------------------------------
# Twin card + approval flow (§3.5, §8).
# --------------------------------------------------------------------------
def twin_card_dict(twin: TwinProfile) -> dict:
    """The twin card as data (what the guest sees and approves, §3.5)."""
    b = twin.benchmark
    return dict(
        guest_name=twin.guest_name,
        handicap=twin.handicap,
        strokes_over_scratch=twin.strokes_over_scratch,
        source=twin.source,
        driving_yd=round(b["driving_yd"], 0),
        fairway_pct=round(b["fairway_pct"], 3),
        gir_pct=round(b["gir_pct"], 3),
        scoring_avg=round(b["scoring_avg"], 1),
        putts_per_round=round(b["putts_per_round"], 1),
        strength=twin.strength,
        strength_line=twin.strength_line,
        weakness=twin.weakness,
        weakness_line=twin.weakness_line,
        shot_shape=twin.shot_shape,
        usual_miss=twin.usual_miss,
        handedness=twin.handedness,
        risk=("aggressive" if twin.risk_threshold_delta < 0 else
              "conservative" if twin.risk_threshold_delta > 0 else "neutral"),
        calibration_notes=list(twin.calibration_notes),
        validation=twin.validation,
        approved=twin.approved,
        approval_line=("This is how your twin plays. If this doesn't look "
                       "like your game, tell us and we'll fix it."),
    )


def render_twin_card(twin: TwinProfile) -> str:
    """The twin card as plain text (brand system: Fairway / Gold / Mono)."""
    c = twin_card_dict(twin)
    sos = c["strokes_over_scratch"]
    hcp = f"+{twin.handicap:g}" if twin.handicap > 0 else (
        "scratch" if twin.handicap == 0 else f"{abs(twin.handicap):g}")
    lines = [
        "MAS GOLFS — GUEST TWIN CARD",
        "=" * 44,
        f"GUEST     {c['guest_name']}",
        f"HANDICAP  {hcp}  (plays to {sos:.0f} over scratch)",
        f"SOURCE    {c['source']}  (path C: stat profile)"
        if c["source"] == "path_c" else f"SOURCE    {c['source']}",
        "-" * 44,
        f"DRIVING   {c['driving_yd']:.0f} yd avg",
        f"FAIRWAYS  {c['fairway_pct']:.0%}",
        f"GREENS    {c['gir_pct']:.0%} GIR",
        f"SCORING   {c['scoring_avg']:.0f} avg  ·  PUTTS {c['putts_per_round']:.1f}/round",
        "-" * 44,
        f"STRENGTH  {c['strength']}: {c['strength_line']}",
        f"WEAKNESS  {c['weakness']}: {c['weakness_line']}",
        f"SHAPE     {c['shot_shape']}  ·  USUAL MISS: {c['usual_miss']}  ·  {c['handedness']}-handed",
        f"RISK      {c['risk']}",
        "-" * 44,
    ]
    for note in c["calibration_notes"]:
        lines.append(f"NOTE      {note}")
    if c["validation"]:
        v = c["validation"]
        # Mean record from calibrate_twin ({"mean": {...}}) or a flat
        # per-round dict — read whichever is present.
        m = v.get("mean", v)
        if "score" in m and "scoring_benchmark" in m:
            rounds = v.get("rounds_played")
            tag = f" (mean of {rounds} rounds)" if rounds else ""
            lines.append(
                f"VALIDATED score {m['score']:.1f} (benchmark "
                f"{m['scoring_benchmark']:.0f}), "
                f"driving {m['driving_avg_yd']:.0f} yd, "
                f"fairways {m['fairway_pct']:.0%}, GIR {m['gir_pct']:.0%}"
                f"{tag} — {'PASSED' if v['passed'] else 'FAILED'}")
        else:
            lines.append(
                f"VALIDATED {'PASSED' if v.get('passed') else 'FAILED'}")
    lines.append("")
    lines.append(c["approval_line"])
    lines.append(f"STATUS    {'APPROVED' if c['approved'] else 'AWAITING GUEST APPROVAL'}")
    return "\n".join(lines)


def approve_twin(twin: TwinProfile, approver: str = "guest") -> TwinProfile:
    """The guest approves the twin card (§3.5). No match airs without this."""
    if twin.validation is None or not twin.validation.get("passed"):
        raise ValueError("cannot approve a twin that has not passed validation")
    twin.approved = True
    twin.approved_by = approver
    return twin


def request_fix(twin: TwinProfile, note: str) -> TwinProfile:
    """The guest says "that's not my game" — approval resets, note recorded."""
    twin.approved = False
    twin.approved_by = None
    twin.calibration_notes.append(f"Guest asked for a fix: {note}")
    return twin


def can_air(twin: TwinProfile) -> tuple[bool, str]:
    """May this twin's match air? (§8: no twin without approval.)"""
    if twin.retired:
        return False, "twin is retired"
    if twin.validation is None or not twin.validation.get("passed"):
        return False, "twin has not passed validation (mean of validation rounds)"
    if not twin.approved:
        return False, "guest has not approved the twin card"
    return True, "ready to air"


def retire_twin(twin: TwinProfile, note: str = "") -> TwinProfile:
    """Retire a twin at the guest's request (§8): profile flagged, record kept.

    The Record Book notes the retirement rather than erasing the history.
    """
    twin.retired = True
    twin.approved = False
    twin.retire_note = note or "retired at the guest's request"
    return twin


# --------------------------------------------------------------------------
# Registry — one twin per guest (§8).
# --------------------------------------------------------------------------
class TwinAlreadyExists(Exception):
    """A twin already exists for this guest — re-calibrate, don't duplicate."""


def _guest_key(name: str) -> str:
    return " ".join(name.strip().lower().split())


class TwinRegistry:
    """The twin book: one twin per guest, with match records (§6, §8)."""

    def __init__(self):
        self._twins: dict[str, TwinProfile] = {}

    def add(self, twin: TwinProfile) -> TwinProfile:
        key = _guest_key(twin.guest_name)
        if key in self._twins:
            raise TwinAlreadyExists(
                f"a twin already exists for {twin.guest_name!r} — "
                "use recalibrate() to update it")
        self._twins[key] = twin
        return twin

    def get(self, name: str) -> TwinProfile | None:
        return self._twins.get(_guest_key(name))

    def recalibrate(self, profile: StatProfile,
                    measured: dict | None = None) -> TwinProfile:
        """Re-calibrate an existing guest's twin from a new submission.

        The twin keeps its record and its name; only the numbers change,
        and approval + validation reset — the guest approves the new card
        before the next match.
        """
        key = _guest_key(profile.name)
        old = self._twins.get(key)
        if old is None:
            return self.add(build_twin(profile, measured))
        new = build_twin(profile, measured)
        new.record = old.record
        self._twins[key] = new
        return new

    def retire(self, name: str, note: str = "") -> TwinProfile | None:
        twin = self.get(name)
        if twin is None:
            return None
        return retire_twin(twin, note)

    def record_match(self, name: str, won: bool, score: int) -> TwinProfile | None:
        """Record a played match in the twin's Record Book (§6)."""
        twin = self.get(name)
        if twin is None:
            return None
        twin.record["matches"] += 1
        twin.record["wins" if won else "losses"] += 1
        if twin.record["best_score"] is None or score < twin.record["best_score"]:
            twin.record["best_score"] = score
            twin.record["best_round"] = score
        return twin

    def to_dict(self) -> dict:
        return {k: t.to_dict() for k, t in self._twins.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "TwinRegistry":
        reg = cls()
        for k, v in data.items():
            reg._twins[k] = TwinProfile.from_dict(v)
        return reg
