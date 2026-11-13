"""Self-improvement learning loop for Mas Golfs (docs/self-improvement.md).

Mas gets better fully autonomously by getting *smarter*, never by hitting
it further or straighter: the loop fixes one decision weakness at a time
(aim, club choice, trajectory, target line, risk) against a frozen swing.

What this module is
-------------------
The complete implementation of docs/self-improvement.md: the two stores
(append-only round store; versioned golfer model with change log), the
one-fix selection algorithm (verdict windows, ratchet, escalation ladder),
the frozen-forever rules, the may-change rules with hard caps, the
weakness-vs-noise thresholds, the five-rung improvement ladder, the
200-round season with hard reset, and the monitoring checks with halt
behaviour. It replaces the earlier spec-§6 skeleton that lived in this
file; the engine-facing API is unchanged (``ShotRecord``, ``Fix``,
``GolferModel``, ``LearningLoop.after_round``).

Frozen forever (spec §1.3) — this module never writes to any of these,
and there is a test that fails if it ever does:
  * dispersion sigma values (the swing never tightens in v1),
  * physics constants (gravity, drag, Magnus, air density),
  * calibration targets (the +3 benchmark table),
  * course data (Wyatt National yardages, pars, ratings).
The v2 "practice" mechanism (sigma tightening 1%/20 rounds, capped 5%)
is explicitly NOT implemented here.

May change, with hard caps (spec §1.3) — a write that would exceed a cap
is REJECTED and logged, never clamped silently:
  * aim biases: +/-12 ft per bucket, cumulative; one fix moves a bucket
    at most 7 ft,
  * risk threshold: baseline +/-0.09 total, in steps of 0.03,
  * baseline table: +/-0.05 strokes per bucket,
  * trajectory preference: only via the ``trajectory`` fix mechanism.

Integration points (where the engine calls in)
----------------------------------------------
* ``RoundEngine`` calls ``LearningLoop.after_round(model, records,
  round_info=None)`` once per round, at the ``LEARNING_LOOP`` step
  between ``ROUND_COMPLETE`` and the next ``ROUND_START``. It returns
  the active ``Fix`` (or ``None`` when no fix is active); the engine
  puts ``fix.__dict__`` on the ``round_complete.focus_fix`` field.
* ``round_info`` is optional and not yet passed by the engine. When
  supplied it is ``{"round_no": int, "score": int, "conditions": {...}}``.
  ``score`` enables season-end detection (200 rounds, or a score <= 59)
  and the 59 monitoring checks; ``conditions`` (notably ``wind_mph``)
  enables the wind -> ``trajectory`` mechanism. Without it the loop
  still runs on shot records alone, and season-end / 59 checks are
  skipped (documented in the outcome log).
* The decision engine reads the model every shot through the existing
  hooks: ``GolferModel.aim_bias_for()``, ``risk_threshold_delta``,
  ``baseline_adjustments`` (consumed by ``strokes_gained``), plus
  ``forced_trajectory`` and ``club_up_buckets``. This module only ever
  writes those five fields.
* The broadcast reads ``LearningLoop.one_fix_line(model)`` for the ONE
  FIX line and ``focus_fix_dict(model)`` for ``round_start.focus_fix``.
* The round store is in-memory per process: it rebuilds from future
  rounds after a save/load (the engine serialises only
  ``LearningLoop.history`` and the model). The change log and fix
  history live inside ``GolferModel.to_dict()`` and DO persist.
* Season reset runs automatically inside ``after_round`` when the
  trigger fires; the archive is in ``loop.last_archive`` /
  ``loop.archives``. Engine-side records (RecordBook best round,
  aggregates, 59 Watch lore) are NOT touched by this module — they
  survive by design (spec §8.2).

Determinism: no randomness anywhere in this module. Same round store,
same fix. Ties are broken by rule (larger sample, then cheapest
mechanism), never at random.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Spec constants (docs/self-improvement.md)
# --------------------------------------------------------------------------

# §1.3 hard caps. A write past a cap is rejected and logged, never clamped.
AIM_BIAS_CAP_FT = 12.0       # per bucket, cumulative
AIM_FIX_FIRST_FT = 4.0       # magnitude of a first-application aim fix
AIM_FIX_MAX_FT = 7.0         # magnitude of an escalated aim fix; also the
                             # largest single-fix move of any bucket
RISK_THRESHOLD_CAP = 0.09    # total, in steps of RISK_STEP
RISK_STEP = 0.03
BASELINE_CAP = 0.05          # per bucket
BASELINE_DEADBAND = 0.10     # only adjust if observed differs by >= this

# §4.2 confidence thresholds.
MAGNITUDE_MIN_SG = 0.25      # bucket losing >= this many strokes/round
CONSISTENCY_MIN_ROUNDS = 3   # negative in at least this many of last 5
DIRECTION_MIN = 0.60         # >= 60% of misses on the same side
SEPARATION_MIN = 0.15        # worst bucket must beat next-worst by this

# §4.3 noise floors (SG/round, 5-round window). A bucket must clear the
# larger of MAGNITUDE_MIN_SG and its category floor.
NOISE_FLOORS = {"ott": 0.20, "app": 0.25, "arg": 0.20, "putt": 0.30}

# §5 verdict window and improvement bar.
VERDICT_WINDOW = 3           # rounds after a fix before it is judged
VERDICT_IMPROVE_MIN = 0.15   # SG/round improvement = "working"

# §2.1 / §8: the ladder and the season.
SEASON_ROUNDS = 200
TARGET_SCORE = 59            # a round <= this ends the season early
# Ladder rungs (spec §2.1, v3 numbers): (band_lo, band_hi, display handicap).
# The bands overlap by design (they are ranges, not partitions), so
# rung_for_avg() uses the band midpoints as thresholds.
LADDER = [
    (72.5, 73.5, 3.1),       # rung 0 — the baseline
    (72.0, 73.0, 3.5),       # rung 1 — smarter, not longer
    (71.5, 72.5, 4.0),       # rung 2 — the aggressive line
    (71.0, 72.0, 4.5),       # rung 3 — plus-four territory
    (70.5, 71.5, 5.0),       # rung 4 — the ceiling
]
LADDER_FRAMING = [
    "Mas, the +3.",
    "He's stopped missing left.",
    "He's taking lines he wouldn't have taken in April.",
    "Mas is a +4 now. The number moved.",
    "This is what a +5 looks like when the swing never changed.",
]

# §7.2 monitoring.
MONITOR_EVERY_ROUNDS = 20
IMPROVEMENT_CAP_STROKES = 1.5   # qa-plan L-05, over a 200-round season
MAX_59_PER_SEASON = 2           # > 2 rounds <= 59 in a season: halt
MAX_NEW_FIXES_PER_20 = 10       # > 1 new fix per 2 rounds: chasing noise
CATEGORY_DRIFT_MAX = 1.0        # 20-round category SG move, either way

# §5.2 escalation: a bucket is abandoned after two escalations, revisited
# only after this many rounds, and only if still worst by >= this much.
RESISTANT_REVISIT_ROUNDS = 10
RESISTANT_WORST_BY = 0.30

# §4.1 minimum samples.
MIN_SHOTS_PER_BUCKET = 3
MIN_SHOTS_BASELINE_BUCKET = 10   # shots in bucket over 20 rounds, §5 step 6

# Cheapest-first mechanism order for tie-breaks (spec §4.2.4).
MECHANISM_COST = {
    "aim_offset_ft": 0,
    "club_up": 1,
    "trajectory": 2,
    "target_line": 3,
    "aggression": 4,
}

# The Season 1 starting aim biases (spec §8.2: a new season re-earns
# every fix from fresh data). Kept identical to the original skeleton.
STARTING_AIM_BIASES = {"app_150_175": -2.0}

# Mechanism switches on escalation (spec §5.2, step 2).
_MECHANISM_SWITCH = {
    "aim_offset_ft": "club_up",
    "club_up": "trajectory",
    "trajectory": "club_up",
    "target_line": "club_up",
    "aggression": "target_line",
}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

@dataclass
class ShotRecord:
    """One shot, as recorded by the engine for the learning loop."""
    category: str            # ott / app / arg / putt (§6.2)
    bucket: str              # e.g. app_150_175, ott, arg, putt_6_15
    sg: float
    miss_ft: float = 0.0     # offline vs pin, + = right of pin
    distance_yd: float = 0.0


@dataclass
class Fix:
    """One mechanical parameter change (spec §6.3 format, extended).

    Every field has a default so fixes saved by older versions of this
    module still construct via ``Fix(**saved)``.
    """
    area: str = ""
    finding: str = ""
    adjustment: str = ""
    expected_gain: float = 0.0
    mechanism: str = "aim_offset_ft"   # aim_offset_ft / club_up /
                                       # trajectory / target_line / aggression
    magnitude: float = 0.0
    applies_to: dict = field(default_factory=dict)
    rounds_active: int = 0
    # --- self-improvement.md extensions ---
    id: int = 0
    status: str = "active"   # active | working | no_effect | harmful |
                             # resolved | superseded | reverted | resistant
    escalation_level: int = 0
    applied_round: int = 0   # season round the fix (last) applied at
    verdict: str | None = None
    evidence: dict = field(default_factory=dict)   # bucket SG, sample, miss %
    previous: dict = field(default_factory=dict)   # parameter values
                             # before apply, for revert on "harmful"


@dataclass
class RoundRecord:
    """One completed round in the append-only round store (spec §1.1)."""
    round_no: int
    score: int | None = None
    sg_by_category: dict = field(default_factory=dict)
    conditions: dict = field(default_factory=dict)
    active_fix_area: str | None = None
    shots: list = field(default_factory=list)   # list[ShotRecord]

    def to_dict(self) -> dict:
        return dict(round_no=self.round_no, score=self.score,
                    sg_by_category=self.sg_by_category,
                    conditions=self.conditions,
                    active_fix_area=self.active_fix_area,
                    shots=[dict(s.__dict__) for s in self.shots])

    @classmethod
    def from_dict(cls, data: dict) -> "RoundRecord":
        return cls(round_no=data["round_no"], score=data.get("score"),
                   sg_by_category=dict(data.get("sg_by_category", {})),
                   conditions=dict(data.get("conditions", {})),
                   active_fix_area=data.get("active_fix_area"),
                   shots=[ShotRecord(**s) for s in data.get("shots", [])])


class RoundStore:
    """Append-only store of every completed round in the season (§1.1).

    Never edited, never deleted within a season. Archived (not deleted)
    by the season reset.
    """

    def __init__(self):
        self.rounds: list[RoundRecord] = []

    def add_round(self, record: RoundRecord) -> None:
        self.rounds.append(record)

    def last_n(self, n: int) -> list[RoundRecord]:
        return self.rounds[-n:] if n > 0 else []

    def bucket_round_sg(self, bucket: str, n: int = 5
                        ) -> list[tuple[int, float, int]]:
        """Per-round (round_no, SG total, shot count) for a bucket over
        the last ``n`` rounds. Rounds with no shots in the bucket
        contribute SG 0.0 — they are not negative rounds."""
        out = []
        for rec in self.last_n(n):
            shots = [s for s in rec.shots if s.bucket == bucket]
            out.append((rec.round_no,
                        sum(s.sg for s in shots), len(shots)))
        return out

    def category_round_sg(self, category: str, n: int = 5
                          ) -> list[tuple[int, float]]:
        out = []
        for rec in self.last_n(n):
            total = sum(s.sg for s in rec.shots if s.category == category)
            out.append((rec.round_no, total))
        return out

    def scores(self) -> list[int]:
        return [r.score for r in self.rounds if r.score is not None]

    def to_dict(self) -> dict:
        return dict(rounds=[r.to_dict() for r in self.rounds])

    @classmethod
    def from_dict(cls, data: dict) -> "RoundStore":
        store = cls()
        store.rounds = [RoundRecord.from_dict(r)
                        for r in data.get("rounds", [])]
        return store


def ladder_rung_for_avg(last20_avg: float) -> int:
    """Rung for a 20-round scoring average (spec §2.1).

    The rung bands overlap, so the thresholds are the band midpoints:
    72.75 / 72.25 / 71.75 / 71.25. Below 71.25 is the ceiling (rung 4).
    """
    for rung, edge in enumerate((72.75, 72.25, 71.75, 71.25)):
        if last20_avg >= edge:
            return rung
    return 4


def display_handicap_for_rung(rung: int) -> float:
    """Display handicap for a rung (spec §2.1)."""
    return LADDER[max(0, min(4, rung))][2]


def season_improvement(scores: list) -> float | None:
    """L-05 improvement: mean of rounds 1-20 minus mean of the last 20.

    Returns None with fewer than 40 rounds. Positive = got better.
    """
    if len(scores) < 40:
        return None
    first20 = sum(scores[:20]) / 20.0
    last20 = sum(scores[-20:]) / 20.0
    return first20 - last20


def _plain_area(bucket: str) -> str:
    """Bucket name in plain golf language for the ONE FIX line (§6.1)."""
    if bucket.startswith("app_"):
        parts = bucket.split("_")
        if len(parts) == 3:
            return f"{parts[1]}–{parts[2]} yd approaches"
        return "approaches"
    if bucket == "ott":
        return "drives"
    if bucket == "arg":
        return "short game"
    if bucket.startswith("putt_"):
        parts = bucket.split("_")
        if len(parts) == 3:
            if parts[2] == "plus":
                return "15 ft+ putts"
            return f"{parts[1]}–{parts[2]} ft putts"
        return "putting"
    return bucket


def _category_of(bucket: str) -> str:
    return bucket.split("_")[0] if bucket else ""


class GolferModel:
    """The mutable parameters the learning loop may change (spec §1.3),
    plus metadata. Versioned — every write bumps ``version`` and appends
    to ``change_log``."""

    def __init__(self):
        # Per-bucket aim offsets in feet (+ = aim further right).
        self.aim_biases: dict[str, float] = dict(STARTING_AIM_BIASES)
        # Risk-rule threshold delta (§5.3), +/-0.09 in 0.03 steps.
        self.risk_threshold_delta: float = 0.0
        # Baseline-table adjustments per bucket (+/-0.05 strokes, §6.4).
        self.baseline_adjustments: dict[str, float] = {}
        # Forced trajectory per bucket, e.g. {"app_150_175": "knockdown"}.
        self.forced_trajectory: dict[str, str] = {}
        # Club-up per bucket (take one more club).
        self.club_up_buckets: set[str] = set()
        # Mas's natural miss is left — the loop's first job.
        self.form: str = "neutral"
        self.active_fix: Fix | None = None
        # --- self-improvement.md extensions ---
        self.version: int = 1
        self.change_log: list[dict] = []
        self.fix_history: list[dict] = []   # every fix ever, with outcome
        self.season_no: int = 1
        self.halted: bool = False
        self.halt_reason: str | None = None
        self.resistant: dict[str, int] = {}  # bucket -> revisit round
        self.new_fix_rounds: list[int] = []  # rounds a NEW fix applied

    # -- change log ---------------------------------------------------------
    def log_change(self, event: str, detail: str, round_no: int = 0) -> None:
        """Append to the audit log and bump the version (spec §1.4)."""
        self.version += 1
        self.change_log.append(dict(round=round_no, season=self.season_no,
                                    event=event, detail=detail))

    def record_fix(self, fix: Fix) -> None:
        """Upsert a fix into the fix history, keyed by id (§1.2)."""
        entry = dict(fix.__dict__)
        for i, old in enumerate(self.fix_history):
            if old.get("id") == fix.id:
                self.fix_history[i] = entry
                return
        self.fix_history.append(entry)

    # -- engine-facing reads (unchanged from the skeleton) ------------------
    def aim_bias_for(self, distance_yd: float, lie: str) -> float:
        """Aim offset (ft) for a shot at this distance (§6.3 mechanism)."""
        if lie in ("green", "fringe", "bunker_green"):
            return 0.0
        for lo, hi in ((100, 125), (125, 150), (150, 175), (175, 200),
                       (200, 9999)):
            if lo <= distance_yd < hi:
                return self.aim_biases.get(f"app_{lo}_{hi}", 0.0)
        return 0.0

    # -- serialisation ------------------------------------------------------
    def to_dict(self) -> dict:
        return dict(aim_biases=self.aim_biases,
                    risk_threshold_delta=self.risk_threshold_delta,
                    baseline_adjustments=self.baseline_adjustments,
                    forced_trajectory=self.forced_trajectory,
                    club_up_buckets=sorted(self.club_up_buckets),
                    form=self.form,
                    active_fix=(dict(self.active_fix.__dict__)
                                if self.active_fix else None),
                    version=self.version,
                    change_log=self.change_log,
                    fix_history=self.fix_history,
                    season_no=self.season_no,
                    halted=self.halted,
                    halt_reason=self.halt_reason,
                    resistant=self.resistant,
                    new_fix_rounds=self.new_fix_rounds)

    @classmethod
    def from_dict(cls, data: dict) -> "GolferModel":
        m = cls()
        m.aim_biases = dict(data.get("aim_biases", {}))
        m.risk_threshold_delta = data.get("risk_threshold_delta", 0.0)
        m.baseline_adjustments = dict(data.get("baseline_adjustments", {}))
        m.forced_trajectory = dict(data.get("forced_trajectory", {}))
        m.club_up_buckets = set(data.get("club_up_buckets", []))
        m.form = data.get("form", "neutral")
        fx = data.get("active_fix")
        m.active_fix = Fix(**fx) if fx else None
        m.version = data.get("version", 1)
        m.change_log = list(data.get("change_log", []))
        m.fix_history = list(data.get("fix_history", []))
        m.season_no = data.get("season_no", 1)
        m.halted = data.get("halted", False)
        m.halt_reason = data.get("halt_reason")
        m.resistant = dict(data.get("resistant", {}))
        m.new_fix_rounds = list(data.get("new_fix_rounds", []))
        return m


class LearningLoop:
    """The one-fix learning loop (spec §5), run once per round.

    ``history`` is the 5-round rolling shot window (kept for the engine's
    save/load); ``store`` is the whole-season append-only round store.
    """

    MIN_SAMPLES = 3          # never fix on fewer samples (§6.3)
    HISTORY_ROUNDS = 5       # look back over the last 5 rounds
    ESCALATE_AFTER = 3       # rounds before a non-working fix escalates

    def __init__(self):
        self.history: list[list[ShotRecord]] = []  # per-round records
        self.store = RoundStore()
        self.rounds_seen: int = 0      # rounds in the current season
        self.season_no: int = 1
        self.archives: list[dict] = []  # past seasons, fix history + rounds
        self.last_archive: dict | None = None
        self.last_outcome: dict | None = None
        self._next_fix_id: int = 1
        self._review_flag_logged: bool = False

    # -- intake -------------------------------------------------------------
    def add_round(self, records: list[ShotRecord],
                  round_info: dict | None = None) -> None:
        """Record one completed round in both stores (§1.1)."""
        info = round_info or {}
        self.history.append(list(records))
        if len(self.history) > self.HISTORY_ROUNDS:
            self.history.pop(0)
        sg_by_category: dict[str, float] = {}
        for rec in records:
            sg_by_category[rec.category] = (
                sg_by_category.get(rec.category, 0.0) + rec.sg)
        self.store.add_round(RoundRecord(
            round_no=info.get("round_no", self.rounds_seen),
            score=info.get("score"),
            sg_by_category={k: round(v, 2)
                            for k, v in sg_by_category.items()},
            conditions=dict(info.get("conditions", {})),
            active_fix_area=None,
            shots=list(records)))

    # -- the loop itself (spec §5) ------------------------------------------
    def after_round(self, model: GolferModel,
                    round_records: list[ShotRecord],
                    round_info: dict | None = None) -> Fix | None:
        """Run the loop after a round; returns the active fix (or None).

        The return value is the fix the broadcast shows on the ONE FIX
        line. The detailed outcome (new fix / verdict / escalation /
        no_fix / halted / season reset) is in ``self.last_outcome``.
        """
        info = round_info or {}
        self.rounds_seen += 1
        self.add_round(round_records, dict(info,
                                           round_no=info.get(
                                               "round_no", self.rounds_seen)))
        score = info.get("score")
        outcome: dict = {"kind": "no_fix", "round": self.rounds_seen,
                         "season": self.season_no, "reason": ""}

        if model.halted:
            # §7.2 halt: the loop stops producing new fixes. The model
            # freezes; the broadcast continues with the frozen model.
            # The season still ends on schedule (the rounds keep being
            # played and recorded); the halt itself survives the reset
            # — only human review resumes the loop.
            model.log_change("halted_no_change",
                             "loop halted; model frozen",
                             self.rounds_seen)
            outcome.update(kind="halted", reason=model.halt_reason or "")
            if self._season_ended(score):
                archive = self.end_season(model)
                outcome.update(kind="season_reset",
                               season=archive["season"],
                               rounds=archive["rounds"],
                               best_score=archive["best_score"])
            self.last_outcome = outcome
            return model.active_fix

        if self.rounds_seen <= 3:
            # §4.4: the first 3 rounds of a season are "establishing" —
            # the loop watches and accumulates, and produces no fix.
            outcome.update(kind="no_fix", reason="establishing")
            self._finish_round(model, outcome, score)
            return model.active_fix

        # Step 2: verdict on the current active fix (if any).
        skip_selection = False
        if model.active_fix is not None:
            fix = model.active_fix
            fix.rounds_active = self.rounds_seen - fix.applied_round
            age = fix.rounds_active
            if age < VERDICT_WINDOW:
                outcome.update(kind="no_fix", reason="fix_pending",
                               fix_id=fix.id)
                skip_selection = True
            else:
                verdict = self._verdict(fix)
                fix.verdict = verdict
                if verdict == "pending":
                    # Not enough shots in the after window to judge yet —
                    # the fix stays active and the verdict is deferred.
                    outcome.update(kind="no_fix", reason="fix_pending",
                                   fix_id=fix.id)
                    skip_selection = True
                elif verdict == "working":
                    fix.status = "resolved"
                    model.record_fix(fix)
                    model.log_change(
                        "fix_resolved",
                        f"fix #{fix.id} {fix.area} working "
                        f"(bucket improved >= {VERDICT_IMPROVE_MIN} "
                        f"strokes/round); parameter change stays",
                        self.rounds_seen)
                    model.active_fix = None
                    outcome.update(kind="fix_resolved", fix_id=fix.id)
                elif verdict == "no_effect":
                    if self._escalate(model, fix):
                        outcome.update(kind="fix_escalated",
                                       fix_id=fix.id,
                                       level=fix.escalation_level)
                        skip_selection = True
                    else:
                        # Resistant: the loop moves on to the next bucket.
                        outcome.update(kind="fix_resistant",
                                       fix_id=fix.id)
                        model.active_fix = None
                else:  # harmful — should be ~impossible; log it loudly.
                    self._revert_fix(model, fix)
                    fix.status = "reverted"
                    model.record_fix(fix)
                    # Learn from it, don't repeat it (§5 step 2e): the
                    # bucket is resistant for 10 rounds, like an
                    # escalation-resistant bucket.
                    model.resistant[fix.area] = (
                        self.rounds_seen + RESISTANT_REVISIT_ROUNDS)
                    model.log_change(
                        "fix_reverted",
                        f"fix #{fix.id} {fix.area} HARMFUL "
                        f"(bucket worsened >= {VERDICT_IMPROVE_MIN}); "
                        f"parameter change reverted; bucket resistant "
                        f"for {RESISTANT_REVISIT_ROUNDS} rounds",
                        self.rounds_seen)
                    model.active_fix = None
                    outcome.update(kind="fix_reverted", fix_id=fix.id)

        # Steps 3-5: find candidates, select one fix, apply it.
        if not skip_selection and model.active_fix is None:
            fix = self._select_fix(model)
            if fix is None:
                outcome.setdefault("reason", "no_actionable_weakness")
            else:
                if self._apply_fix(model, fix):
                    model.active_fix = fix
                    model.new_fix_rounds.append(self.rounds_seen)
                    model.record_fix(fix)
                    model.log_change(
                        "fix_applied",
                        f"fix #{fix.id} {fix.area} [{fix.mechanism} "
                        f"{fix.magnitude}] — {fix.finding}",
                        self.rounds_seen)
                    outcome.update(kind="new_fix", fix_id=fix.id,
                                   area=fix.area,
                                   mechanism=fix.mechanism)
                else:
                    # Cap rejection: never clamp silently (§9.2). Mark
                    # the bucket resistant so the loop does not hammer a
                    # fix it cannot legally apply.
                    model.resistant[fix.area] = (
                        self.rounds_seen + RESISTANT_REVISIT_ROUNDS)
                    model.log_change(
                        "fix_rejected_cap",
                        f"fix #{fix.id} {fix.area} rejected: parameter "
                        f"write would exceed a cap; bucket resistant "
                        f"for {RESISTANT_REVISIT_ROUNDS} rounds",
                        self.rounds_seen)
                    outcome.update(kind="fix_rejected_cap",
                                   fix_id=fix.id, area=fix.area)

        self._finish_round(model, outcome, score)
        return model.active_fix

    def _finish_round(self, model: GolferModel, outcome: dict,
                      score: int | None) -> None:
        """Step 6 baseline maintenance, monitoring, season end (§5.6, §7, §8)."""
        self._baseline_maintenance(model)
        self._monitoring(model, score)
        if self._season_ended(score):
            archive = self.end_season(model)
            outcome.update(kind="season_reset", season=archive["season"],
                           rounds=archive["rounds"],
                           best_score=archive["best_score"])
        self.last_outcome = outcome

    def _bucket_window(self, bucket: str, round_nos: list[int]
                       ) -> list[tuple[float, int]]:
        """(SG total, shot count) for a bucket over specific round numbers.

        Rounds absent from the store contribute (0.0, 0).
        """
        per: dict[int, tuple[float, int]] = {}
        for rec in self.store.rounds:
            shots = [s for s in rec.shots if s.bucket == bucket]
            if shots:
                per[rec.round_no] = (sum(s.sg for s in shots), len(shots))
        return [per.get(n, (0.0, 0)) for n in round_nos]

    # -- step 2: verdict ------------------------------------------------------
    def _verdict(self, fix: Fix) -> str:
        """Judge a fix after its 3-round window (§5 step 2).

        Compares the target bucket's SG/round in the 3 rounds before the
        fix (captured on the fix at application time) vs. the 3 rounds
        after it. With < 3 shots in the after window there is not
        enough data to judge — verdict stays "pending".
        """
        after_nos = [fix.applied_round + 1, fix.applied_round + 2,
                     fix.applied_round + 3]
        after = self._bucket_window(fix.area, after_nos)
        after_shots = sum(n for _, n in after)
        if after_shots < MIN_SHOTS_PER_BUCKET:
            return "pending"
        after_mean = sum(sg for sg, _ in after) / VERDICT_WINDOW
        before_mean = fix.evidence.get(
            "before_sg_per_round",
            fix.evidence.get("sg_per_round", 0.0))
        delta = after_mean - before_mean
        if delta >= VERDICT_IMPROVE_MIN:
            return "working"
        if delta <= -VERDICT_IMPROVE_MIN:
            return "harmful"
        return "no_effect"

    # -- steps 3-4: find candidates, select the fix ---------------------------
    def _bucket_window_stats(self, n: int = HISTORY_ROUNDS) -> dict:
        """Per-bucket stats over the last ``n`` rounds in the store.

        Returns bucket -> dict(shots, sg_per_round, negative_rounds,
        direction, direction_pct, mean_sg_per_shot, category).
        sg_per_round is the mean over the ``n``-round window (rounds
        where the bucket did not occur contribute 0.0).
        """
        buckets: dict[str, list] = {}
        for rec in self.store.last_n(n):
            for shot in rec.shots:
                buckets.setdefault(shot.bucket, []).append(
                    (rec.round_no, shot))
        out = {}
        for bucket, entries in buckets.items():
            per_round: dict[int, float] = {}
            left = right = 0
            for round_no, shot in entries:
                per_round[round_no] = per_round.get(round_no, 0.0) + shot.sg
                if shot.miss_ft < -0.5:
                    left += 1
                elif shot.miss_ft > 0.5:
                    right += 1
            total_sg = sum(per_round.values())
            directional = left + right
            direction = ("left" if left > right else "right"
                         if directional else "")
            direction_pct = (max(left, right) / directional
                             if directional else 0.0)
            out[bucket] = dict(
                shots=len(entries),
                sg_per_round=total_sg / n,
                negative_rounds=sum(1 for v in per_round.values() if v < 0),
                left=left, right=right,
                direction=direction, direction_pct=direction_pct,
                mean_sg_per_shot=(total_sg / len(entries)
                                  if entries else 0.0),
                category=_category_of(bucket))
        return out

    def _find_candidates(self, model: GolferModel) -> list[dict]:
        """Buckets that clear all four §4.2 thresholds, worst first."""
        stats = self._bucket_window_stats()
        candidates = []
        for bucket, st in stats.items():
            category = st["category"]
            floor = max(MAGNITUDE_MIN_SG,
                        NOISE_FLOORS.get(category, MAGNITUDE_MIN_SG))
            if st["shots"] < MIN_SHOTS_PER_BUCKET:
                continue                                   # §4.1
            if st["sg_per_round"] > -floor:
                continue                                   # §4.2.1 + §4.3
            if st["negative_rounds"] < CONSISTENCY_MIN_ROUNDS:
                continue                                   # §4.2.2
            if bucket in model.resistant:
                revisit = model.resistant[bucket]
                if self.rounds_seen < revisit:
                    continue                               # §5.2, step 3
            candidates.append(dict(bucket=bucket, **st))
        candidates.sort(key=lambda c: c["sg_per_round"])
        return candidates

    def _select_fix(self, model: GolferModel) -> Fix | None:
        """Pick the single worst surviving bucket and build its fix (§5.4)."""
        candidates = self._find_candidates(model)
        if not candidates:
            return None
        worst = candidates[0]
        if len(candidates) > 1:
            second = candidates[1]
            if worst["sg_per_round"] - second["sg_per_round"] > -SEPARATION_MIN:
                # Within 0.15: tie-break by larger sample, then cheapest
                # mechanism (§4.2.4). Deterministic, never random.
                tied = [c for c in candidates[:2]
                        if c["sg_per_round"] - worst["sg_per_round"]
                        < SEPARATION_MIN]
                tied.sort(key=lambda c: (
                    -c["shots"],
                    MECHANISM_COST[self._mechanism_for(c)[0]]))
                worst = tied[0]
            # A resistant bucket may only return if still worst by >= 0.30.
            if worst["bucket"] in model.resistant:
                others = [c for c in candidates
                          if c["bucket"] != worst["bucket"]]
                if others and (others[0]["sg_per_round"]
                               - worst["sg_per_round"] < RESISTANT_WORST_BY):
                    return None
        mechanism, magnitude, adjustment = self._mechanism_for(worst)
        area_plain = _plain_area(worst["bucket"])
        if worst["direction_pct"] >= DIRECTION_MIN and worst["direction"]:
            finding = (f"Losing {abs(worst['sg_per_round']):.2f} "
                       f"strokes/round on {area_plain}, missing "
                       f"{worst['direction_pct']:.0%} {worst['direction']}.")
        else:
            finding = (f"Losing {abs(worst['sg_per_round']):.2f} "
                       f"strokes/round on {area_plain}.")
        fix = Fix(
            area=worst["bucket"], finding=finding, adjustment=adjustment,
            expected_gain=round(
                min(0.4, abs(worst["sg_per_round"]) * 0.8), 2),
            mechanism=mechanism, magnitude=magnitude,
            applies_to={"category": worst["category"],
                        "bucket": worst["bucket"]},
            rounds_active=0, id=self._next_fix_id,
            status="active", escalation_level=0,
            applied_round=self.rounds_seen, verdict=None,
            evidence=dict(sg_per_round=round(worst["sg_per_round"], 3),
                          shots=worst["shots"],
                          negative_rounds=worst["negative_rounds"],
                          direction=worst["direction"],
                          direction_pct=round(worst["direction_pct"], 2),
                          category=worst["category"]))
        self._next_fix_id += 1
        # The verdict's "before" window is the 3 rounds ending at
        # application (§5 step 2) — captured now, because the store is
        # in-memory and may not hold them when the verdict is judged.
        before_nos = [self.rounds_seen - 2, self.rounds_seen - 1,
                      self.rounds_seen]
        before = self._bucket_window(worst["bucket"], before_nos)
        fix.evidence["before_sg_per_round"] = round(
            sum(sg for sg, _ in before) / VERDICT_WINDOW, 3)
        return fix

    def _mechanism_for(self, candidate: dict) -> tuple[str, float, str]:
        """Mechanism for a bucket from its evidence (§5 step 4c).

        Short/long (distance) evidence is not present in ShotRecord —
        there is no end-distance field — so club_up is the category
        default for app/arg when the miss is non-directional, and
        target_line for ott. A future ShotRecord carry-vs-target field
        would let the loop distinguish short from pin-hunting.
        """
        bucket = candidate["bucket"]
        category = candidate["category"]
        area_plain = _plain_area(bucket)
        if (candidate["direction_pct"] >= DIRECTION_MIN
                and candidate["direction"]):
            correction = ("right" if candidate["direction"] == "left"
                          else "left")
            return ("aim_offset_ft", AIM_FIX_FIRST_FT,
                    f"Aim {AIM_FIX_FIRST_FT:.0f} ft {correction} on "
                    f"{area_plain}")
        if self._wind_on_losing_rounds(bucket) >= 15.0:
            return ("trajectory", 1.0,
                    f"Flight it down (knockdown) on {area_plain} in wind")
        if category in ("app", "arg"):
            return ("club_up", 1.0,
                    f"Take one more club on {area_plain}")
        if category == "ott":
            return ("target_line", 1.0,
                    "Aim at the fat of the fairway, not the corner")
        return ("aggression", -RISK_STEP,
                "Lag putts to tap-in range — die it at the hole")

    def _wind_on_losing_rounds(self, bucket: str) -> float:
        """Mean wind (mph) on the rounds where this bucket lost SG.

        Returns 0.0 when no round in the window recorded conditions
        (the engine does not pass them yet).
        """
        winds = []
        for rec in self.store.last_n(self.HISTORY_ROUNDS):
            bucket_sg = sum(s.sg for s in rec.shots if s.bucket == bucket)
            wind = rec.conditions.get("wind_mph")
            if bucket_sg < 0 and wind is not None:
                winds.append(float(wind))
        return sum(winds) / len(winds) if winds else 0.0

    # -- step 5: apply / revert / escalate ------------------------------------
    def _apply_fix(self, model: GolferModel, fix: Fix,
                   store_previous: bool = True) -> bool:
        """Write a fix into the golfer model, cap-checked (§1.3, §9.2).

        Returns False (and logs) when the write would exceed a cap —
        never clamped silently.
        """
        if store_previous:
            fix.previous = self._capture_previous(model, fix)
        if fix.mechanism == "aim_offset_ft":
            # Miss left -> aim right (positive offset); escalated fixes
            # carry magnitude 7.0 instead of 4.0.
            direction = fix.evidence.get("direction", "")
            sign = -1.0 if direction == "right" else 1.0
            new_value = sign * abs(fix.magnitude)
            ok, why = self._check_aim_move(model, fix.area, new_value)
            if not ok:
                model.log_change("fix_rejected_cap", why, self.rounds_seen)
                return False
            model.aim_biases[fix.area] = new_value
        elif fix.mechanism == "club_up":
            model.club_up_buckets.add(fix.area)
        elif fix.mechanism == "trajectory":
            model.forced_trajectory[fix.area] = "knockdown"
        elif fix.mechanism == "target_line":
            old = model.aim_biases.get(fix.area, 0.0)
            if abs(0.0 - old) > AIM_FIX_MAX_FT:
                model.log_change(
                    "fix_rejected_cap",
                    f"target_line on {fix.area}: zeroing a {old:+.0f} ft "
                    f"bias exceeds the {AIM_FIX_MAX_FT:.0f} ft single-fix "
                    f"move", self.rounds_seen)
                return False
            model.aim_biases[fix.area] = 0.0
        elif fix.mechanism == "aggression":
            new_delta = round(
                (model.risk_threshold_delta + fix.magnitude) / RISK_STEP
                ) * RISK_STEP
            new_delta = round(new_delta, 2)
            if abs(new_delta) > RISK_THRESHOLD_CAP + 1e-9:
                model.log_change(
                    "fix_rejected_cap",
                    f"aggression: risk delta {new_delta:+.2f} exceeds "
                    f"the +/-{RISK_THRESHOLD_CAP:.2f} cap",
                    self.rounds_seen)
                return False
            model.risk_threshold_delta = new_delta
        else:
            model.log_change("fix_rejected_cap",
                             f"unknown mechanism {fix.mechanism!r}",
                             self.rounds_seen)
            return False
        return True

    def _capture_previous(self, model: GolferModel, fix: Fix) -> dict:
        """Parameter values before a fix, so a harmful fix can revert."""
        prev: dict = {}
        if fix.mechanism == "aim_offset_ft":
            prev["aim_bias"] = model.aim_biases.get(fix.area)
        elif fix.mechanism == "club_up":
            prev["club_up"] = fix.area in model.club_up_buckets
        elif fix.mechanism == "trajectory":
            prev["trajectory"] = model.forced_trajectory.get(fix.area)
        elif fix.mechanism == "target_line":
            prev["aim_bias"] = model.aim_biases.get(fix.area)
        elif fix.mechanism == "aggression":
            prev["risk_delta"] = model.risk_threshold_delta
        return prev

    def _check_aim_move(self, model: GolferModel, bucket: str,
                        new_value: float) -> tuple[bool, str]:
        """Aim caps: +/-12 ft cumulative, one fix moves at most 7 ft."""
        if abs(new_value) > AIM_BIAS_CAP_FT + 1e-9:
            return False, (f"aim bias on {bucket}: {new_value:+.0f} ft "
                           f"exceeds the +/-{AIM_BIAS_CAP_FT:.0f} ft cap")
        old = model.aim_biases.get(bucket, 0.0)
        if abs(new_value - old) > AIM_FIX_MAX_FT + 1e-9:
            return False, (f"aim bias on {bucket}: move {old:+.0f} -> "
                           f"{new_value:+.0f} ft exceeds the "
                           f"{AIM_FIX_MAX_FT:.0f} ft single-fix move")
        return True, ""

    def _revert_fix(self, model: GolferModel, fix: Fix) -> None:
        """Restore the parameter values a fix changed (§5 step 2e)."""
        prev = fix.previous or {}
        if fix.mechanism == "aim_offset_ft" or fix.mechanism == "target_line":
            if prev.get("aim_bias") is None:
                model.aim_biases.pop(fix.area, None)
            else:
                model.aim_biases[fix.area] = prev["aim_bias"]
        elif fix.mechanism == "club_up":
            if not prev.get("club_up"):
                model.club_up_buckets.discard(fix.area)
        elif fix.mechanism == "trajectory":
            if prev.get("trajectory") is None:
                model.forced_trajectory.pop(fix.area, None)
            else:
                model.forced_trajectory[fix.area] = prev["trajectory"]
        elif fix.mechanism == "aggression":
            model.risk_threshold_delta = prev.get("risk_delta", 0.0)

    def _escalate(self, model: GolferModel, fix: Fix) -> bool:
        """Escalate a no-effect fix (spec §5.2).

        Returns True when the escalated fix stays active, False when the
        bucket is marked resistant and the loop should move on.
        """
        if fix.escalation_level >= 2:
            fix.status = "resistant"
            model.resistant[fix.area] = (
                self.rounds_seen + RESISTANT_REVISIT_ROUNDS)
            model.record_fix(fix)
            model.log_change(
                "fix_resistant",
                f"fix #{fix.id} {fix.area} resistant after two "
                f"escalations; revisit after "
                f"{RESISTANT_REVISIT_ROUNDS} rounds",
                self.rounds_seen)
            return False
        fix.escalation_level += 1
        # Compute the escalated fix first; revert under the OLD mechanism
        # (a switch removes the old parameter, a magnitude change does
        # not — 4 -> 7 ft is measured from the value in the model).
        new_mechanism = fix.mechanism
        new_magnitude = fix.magnitude
        new_adjustment = fix.adjustment
        switching = False
        if fix.escalation_level == 1:
            # Step 1: magnitude increases (aim 4 ft -> 7 ft; aggression
            # takes another 0.03 step — its magnitude IS the step, so it
            # stays +/-0.03 and _apply_fix adds it to the current delta).
            # Other mechanisms have no magnitude, so they switch now.
            if fix.mechanism == "aim_offset_ft":
                new_magnitude = AIM_FIX_MAX_FT
                direction = fix.evidence.get("direction", "")
                correction = ("right" if direction == "left" else "left")
                new_adjustment = (f"Aim {AIM_FIX_MAX_FT:.0f} ft "
                                  f"{correction} on "
                                  f"{_plain_area(fix.area)}")
            elif fix.mechanism == "aggression":
                new_adjustment = ("Take the aggressive line less often"
                                  if fix.magnitude < 0 else
                                  "Take the aggressive line more often")
            else:
                new_mechanism = self._switch_mechanism(fix)
                new_magnitude = 1.0
                switching = True
        else:
            # Step 2: mechanism switches.
            new_mechanism = self._switch_mechanism(fix)
            new_magnitude = (1.0 if new_mechanism != "aggression"
                             else -RISK_STEP)
            switching = True
        if switching:
            self._revert_fix(model, fix)
            fix.mechanism = new_mechanism
            fix.magnitude = new_magnitude
            fix.adjustment = self._mechanism_adjustment(fix)
        else:
            fix.magnitude = new_magnitude
            fix.adjustment = new_adjustment
        fix.applied_round = self.rounds_seen
        fix.rounds_active = 0
        fix.verdict = None
        fix.status = "active"
        if not self._apply_fix(model, fix, store_previous=False):
            # Escalation itself hit a cap: treat as resistant.
            fix.status = "resistant"
            model.resistant[fix.area] = (
                self.rounds_seen + RESISTANT_REVISIT_ROUNDS)
            model.record_fix(fix)
            return False
        model.record_fix(fix)
        model.log_change(
            "fix_escalated",
            f"fix #{fix.id} {fix.area} escalated to level "
            f"{fix.escalation_level} [{fix.mechanism} {fix.magnitude}]",
            self.rounds_seen)
        return True

    def _switch_mechanism(self, fix: Fix) -> str:
        """Escalation mechanism switch (§5.2): aim -> club_up, or
        trajectory when the losing rounds were windy."""
        if fix.mechanism == "aim_offset_ft":
            if self._wind_on_losing_rounds(fix.area) >= 15.0:
                return "trajectory"
            return "club_up"
        return _MECHANISM_SWITCH.get(fix.mechanism, "club_up")

    def _mechanism_adjustment(self, fix: Fix) -> str:
        area_plain = _plain_area(fix.area)
        if fix.mechanism == "club_up":
            return f"Take one more club on {area_plain}"
        if fix.mechanism == "trajectory":
            return f"Flight it down (knockdown) on {area_plain} in wind"
        if fix.mechanism == "target_line":
            return "Aim at the fat of the fairway, not the corner"
        if fix.mechanism == "aggression":
            return ("Take the aggressive line less often"
                    if fix.magnitude < 0 else
                    "Take the aggressive line more often")
        return fix.adjustment

    # -- step 6: baseline-table maintenance -----------------------------------
    def _baseline_maintenance(self, model: GolferModel) -> list:
        """Recompute §5.5 baseline expectations from observed play (§5.6).

        Only app_* buckets are addressable by the baseline table's key
        function (strokes_gained._bucket_key); ott/arg/putt buckets have
        no stable table key, so they are skipped and logged as such.
        Adjustments are at most +/-0.05 per bucket per round, only when
        the observed value differs from the stored value by >= 0.10.
        """
        if len(self.store.rounds) < 20:
            return []
        adjusted = []
        window = self.store.last_n(20)
        buckets: dict[str, list] = {}
        for rec in window:
            for shot in rec.shots:
                if shot.bucket.startswith("app_"):
                    buckets.setdefault(shot.bucket, []).append(shot.sg)
        for bucket, sgs in buckets.items():
            if len(sgs) < MIN_SHOTS_BASELINE_BUCKET:
                continue
            observed = -sum(sgs) / len(sgs)   # systematic deviation, strokes
            stored = model.baseline_adjustments.get(bucket, 0.0)
            if abs(observed - stored) < BASELINE_DEADBAND:
                continue
            delta = max(-BASELINE_CAP, min(BASELINE_CAP, observed - stored))
            new = max(-BASELINE_CAP, min(BASELINE_CAP, stored + delta))
            if new != stored:
                model.baseline_adjustments[bucket] = new
                model.log_change(
                    "baseline_adjust",
                    f"{bucket}: {stored:+.2f} -> {new:+.2f} "
                    f"(observed {observed:+.2f} over 20 rounds)",
                    self.rounds_seen)
                adjusted.append((bucket, stored, new))
        return adjusted

    # -- §7.2 monitoring --------------------------------------------------------
    def _monitoring(self, model: GolferModel, score: int | None) -> list:
        """Checks after every 20 rounds, with halt behaviour.

        Returns the list of breaches found. Halting breaches freeze the
        model (loop stops producing new fixes); the broadcast continues
        with the frozen model and the ONE FIX line shows "reviewing".
        The 59 checks run every round because a 59 is an event, not a
        periodic measurement; the rest run on the 20-round cadence.
        """
        breaches: list[dict] = []
        scores = self.store.scores()

        # 59 frequency — every round, needs a score.
        if score is not None and score <= TARGET_SCORE:
            if len(scores) <= 50:
                breaches.append(dict(
                    check="59_in_first_50",
                    detail=f"score {score} in round {self.rounds_seen} "
                           f"of the season — calibration is wrong, not "
                           f"genius (qa-plan §1.5)"))
            if sum(1 for s in scores if s <= TARGET_SCORE) > MAX_59_PER_SEASON:
                breaches.append(dict(
                    check="59_frequency",
                    detail=f"> {MAX_59_PER_SEASON} rounds <= 59 in the "
                           f"season"))

        # Best-round sanity — flag for review only, never a halt.
        if (scores and len(scores) <= 20 and min(scores) <= 62
                and not self._review_flag_logged):
            self._review_flag_logged = True
            model.log_change(
                "review_flag",
                f"best round {min(scores)} in the first 20 rounds — "
                f"suspicious, review (qa-plan R-01)",
                self.rounds_seen)

        if self.rounds_seen % MONITOR_EVERY_ROUNDS != 0:
            return self._apply_breaches(model, breaches)

        # L-05 improvement cap. The gate itself is defined on the actual
        # numbers (rounds 180-200 vs 1-20, <= 1.5 strokes); mid-season
        # the same number is a projection. Integer scores quantize the
        # improvement in whole strokes, so a 1.5 projection threshold
        # false-positives on any healthy arc that steps a full stroke
        # early (73 -> 72 by round 100 projects to 2.0). So: before
        # round 180, halt only on a clear runaway (projected > 2.0);
        # from round 180 on, enforce the 1.5 cap on the actual numbers.
        if len(scores) >= 180:
            first20 = sum(scores[:20]) / 20.0
            last20 = sum(scores[-20:]) / 20.0
            if first20 - last20 > IMPROVEMENT_CAP_STROKES:
                breaches.append(dict(
                    check="improvement_cap",
                    detail=f"season improvement "
                           f"{first20 - last20:.2f} strokes > "
                           f"{IMPROVEMENT_CAP_STROKES} cap"))
        elif len(scores) >= 100:
            first20 = sum(scores[:20]) / 20.0
            recent20 = sum(scores[-20:]) / 20.0
            projected = (first20 - recent20) * SEASON_ROUNDS / len(scores)
            if projected > 2.0:
                breaches.append(dict(
                    check="improvement_cap",
                    detail=f"projected season improvement {projected:.2f} "
                           f"strokes — clear runaway"))

        # Fix churn: > 1 new fix per 2 rounds over a 20-round window.
        recent_new = [r for r in model.new_fix_rounds
                      if r > self.rounds_seen - MONITOR_EVERY_ROUNDS]
        if len(recent_new) > MAX_NEW_FIXES_PER_20:
            breaches.append(dict(
                check="fix_churn",
                detail=f"{len(recent_new)} new fixes in the last 20 "
                       f"rounds — the loop is chasing noise"))

        # Category SG drift: any category's 20-round SG moves > 1.0.
        if len(self.store.rounds) >= 40:
            for category in ("ott", "app", "arg", "putt"):
                prev = self._category_sg_per_round(
                    category, self.store.rounds[-40:-20])
                recent = self._category_sg_per_round(
                    category, self.store.rounds[-20:])
                if abs(recent - prev) > CATEGORY_DRIFT_MAX:
                    breaches.append(dict(
                        check="category_drift",
                        detail=f"{category} SG/round moved {prev:+.2f} -> "
                               f"{recent:+.2f} over 20 rounds"))

        return self._apply_breaches(model, breaches)

    @staticmethod
    def _category_sg_per_round(category: str, rounds: list) -> float:
        if not rounds:
            return 0.0
        total = sum(s.sg for rec in rounds for s in rec.shots
                    if s.category == category)
        return total / len(rounds)

    def _apply_breaches(self, model: GolferModel, breaches: list) -> list:
        """A halting breach freezes the model and is never silent (§7.2)."""
        for breach in breaches:
            model.log_change("monitoring_breach",
                             f"{breach['check']}: {breach['detail']}",
                             self.rounds_seen)
        if breaches:
            model.halted = True
            model.halt_reason = "; ".join(b["check"] for b in breaches)
            model.log_change("loop_halted",
                             f"halted: {model.halt_reason}",
                             self.rounds_seen)
        return breaches

    def resume(self, model: GolferModel, note: str = "human review") -> None:
        """Resume a halted loop after human review (§7.2)."""
        model.halted = False
        model.halt_reason = None
        model.log_change("loop_resumed", note, self.rounds_seen)

    # -- §8 season reset ---------------------------------------------------------
    def _season_ended(self, score: int | None) -> bool:
        if self.rounds_seen >= SEASON_ROUNDS:
            return True
        return score is not None and score <= TARGET_SCORE

    def end_season(self, model: GolferModel) -> dict:
        """Archive the season and hard-reset the golfer model (§8.2).

        What survives: the archived round store and fix history, the
        season counters' record (best round, improvement). What resets:
        aim biases (to Season 1 starting biases), risk threshold,
        baseline table, trajectory, club-up, active fix. What does NOT
        reset: a halt — the loop stays frozen until human review (§7.2).
        Engine-side records (RecordBook best round, aggregates, 59 Watch
        lore) are NOT touched — they survive by design.
        """
        scores = self.store.scores()
        archive = dict(
            season=self.season_no,
            rounds=len(self.store.rounds),
            scores=list(scores),
            best_score=min(scores) if scores else None,
            worst_score=max(scores) if scores else None,
            improvement=season_improvement(scores),
            fix_history=list(model.fix_history),
            change_log=list(model.change_log),
            rounds_archived=len(self.store.rounds))
        self.archives.append(archive)
        self.last_archive = archive
        ended_season = archive["season"]
        model.log_change(
            "season_reset",
            f"season {ended_season} ended after "
            f"{archive['rounds']} rounds; best {archive['best_score']}; "
            f"improvement {archive['improvement']}; model reset to "
            f"+3 baselines",
            0)
        model.fix_history = []
        model.aim_biases = dict(STARTING_AIM_BIASES)
        model.risk_threshold_delta = 0.0
        model.baseline_adjustments = {}
        model.forced_trajectory = {}
        model.club_up_buckets = set()
        model.active_fix = None
        model.resistant = {}
        model.new_fix_rounds = []
        model.season_no += 1
        self.store = RoundStore()
        self.history = []
        self.rounds_seen = 0
        self.season_no += 1
        self._review_flag_logged = False
        return archive

    # -- surfacing (§6) ---------------------------------------------------------
    def one_fix_line(self, model: GolferModel) -> str:
        """The ONE FIX line in plain golf language (§6.1)."""
        if model.halted and model.active_fix is not None:
            return f"ONE FIX: {model.active_fix.adjustment} — reviewing"
        if model.active_fix is not None:
            return f"ONE FIX: {model.active_fix.adjustment}"
        if self.rounds_seen < 4:
            return ("ONE FIX: Learning the game again — first fix "
                    "coming after round 3.")
        return "ONE FIX: None yet — watching the numbers."

    def focus_fix_dict(self, model: GolferModel) -> dict | None:
        """The active fix as a plain dict for round_start.focus_fix."""
        if model.active_fix is None:
            return None
        return dict(model.active_fix.__dict__)

    def ladder_state(self, last20_avg: float | None) -> dict:
        """Rung / handicap / framing for a 20-round average (§2.1)."""
        if last20_avg is None:
            return dict(rung=0, handicap=3.1,
                        framing="Mas, the +3.", avg=None)
        rung = ladder_rung_for_avg(last20_avg)
        return dict(rung=rung,
                    handicap=display_handicap_for_rung(rung),
                    framing=LADDER_FRAMING[rung], avg=last20_avg)
