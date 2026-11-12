"""The strokes-gained learning loop (spec §6).

One fix per round. The loop ranks the four SG categories, drills into the
worst sub-bucket with at least 3 samples in the last 5 rounds, and produces
exactly one fix that changes a real engine parameter. The dispersion
sigmas (§3.2) never change — Mas gets *smarter*, not magically tighter.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShotRecord:
    category: str            # ott / app / arg / putt (§6.2)
    bucket: str              # e.g. app_150_175, ott_left, putt_6_15
    sg: float
    miss_ft: float = 0.0     # offline vs pin, + = right of pin
    distance_yd: float = 0.0


@dataclass
class Fix:
    area: str
    finding: str
    adjustment: str
    expected_gain: float
    mechanism: str           # aim_offset_ft / club_up / trajectory /
                             # target_line / aggression
    magnitude: float
    applies_to: dict
    rounds_active: int = 0


class GolferModel:
    """The three things the learning loop may change (§6.4)."""

    def __init__(self):
        # Per-bucket aim offsets in feet (+ = aim further right).
        self.aim_biases: dict[str, float] = {}
        # Risk-rule threshold delta (§5.3), +/-0.03 per fix.
        self.risk_threshold_delta: float = 0.0
        # Baseline-table adjustments per bucket (+/-0.05 strokes, §6.4).
        self.baseline_adjustments: dict[str, float] = {}
        # Forced trajectory per bucket, e.g. {"app_150_175": "knockdown"}.
        self.forced_trajectory: dict[str, str] = {}
        # Club-up per bucket (take one more club).
        self.club_up_buckets: set[str] = set()
        # Mas's natural miss is left (§9.2) — the loop's first job.
        self.aim_biases["app_150_175"] = -2.0
        self.form: str = "neutral"
        self.active_fix: Fix | None = None

    def aim_bias_for(self, distance_yd: float, lie: str) -> float:
        """Aim offset (ft) for a shot at this distance (§6.3 mechanism)."""
        if lie in ("green", "fringe", "bunker_green"):
            return 0.0
        for lo, hi in ((100, 125), (125, 150), (150, 175), (175, 200),
                       (200, 9999)):
            if lo <= distance_yd < hi:
                return self.aim_biases.get(f"app_{lo}_{hi}", 0.0)
        return 0.0

    def to_dict(self) -> dict:
        return dict(aim_biases=self.aim_biases,
                    risk_threshold_delta=self.risk_threshold_delta,
                    baseline_adjustments=self.baseline_adjustments,
                    forced_trajectory=self.forced_trajectory,
                    club_up_buckets=sorted(self.club_up_buckets),
                    form=self.form,
                    active_fix=(self.active_fix.__dict__
                                if self.active_fix else None))

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
        return m


class LearningLoop:
    """Accumulates shot records across rounds; produces one fix per round."""

    MIN_SAMPLES = 3          # never fix on fewer samples (§6.3)
    HISTORY_ROUNDS = 5       # look back over the last 5 rounds
    ESCALATE_AFTER = 3       # rounds before a non-working fix escalates

    def __init__(self):
        self.history: list[list[ShotRecord]] = []  # per-round records

    def add_round(self, records: list[ShotRecord]):
        self.history.append(records)
        if len(self.history) > self.HISTORY_ROUNDS:
            self.history.pop(0)

    def _bucket_stats(self):
        """(category, bucket) -> (n, mean SG, mean miss_ft)."""
        agg: dict[tuple, list] = {}
        for rnd in self.history:
            for r in rnd:
                agg.setdefault((r.category, r.bucket), []).append(r)
        out = {}
        for key, recs in agg.items():
            if len(recs) >= self.MIN_SAMPLES:
                out[key] = (len(recs),
                            sum(r.sg for r in recs) / len(recs),
                            sum(r.miss_ft for r in recs) / len(recs))
        return out

    def after_round(self, model: GolferModel,
                    round_records: list[ShotRecord]) -> Fix | None:
        """Run the loop after a round; returns the new active fix (or None)."""
        self.add_round(round_records)
        stats = self._bucket_stats()
        if not stats:
            return model.active_fix
        # Worst sub-bucket by strokes gained per shot.
        (cat, bucket), (n, mean_sg, mean_miss) = min(
            stats.items(), key=lambda kv: kv[1][1])
        if mean_sg >= -0.02:
            # Nothing is losing enough to fix; keep the current fix.
            return model.active_fix
        # Escalate an existing fix on the same area instead of replacing it.
        if model.active_fix is not None \
                and model.active_fix.area == bucket \
                and model.active_fix.rounds_active >= self.ESCALATE_AFTER:
            fix = model.active_fix
            fix.rounds_active += 1
            if fix.mechanism == "aim_offset_ft":
                fix.magnitude = min(10.0, fix.magnitude + 3.0)
                fix.adjustment = (f"aim {fix.magnitude:.0f} ft further "
                                  f"{'right' if mean_miss < 0 else 'left'} "
                                  f"on {bucket.replace('_', ' ')} shots")
            elif fix.mechanism == "aggression":
                fix.magnitude = max(-0.06, fix.magnitude - 0.03)
            self._apply(model, fix, mean_miss)
            return fix
        # New fix.
        per_round = mean_sg * n / max(1, len(self.history))
        if cat == "app" and abs(mean_miss) > 2:
            direction = "right" if mean_miss < 0 else "left"
            fix = Fix(area=bucket,
                      finding=(f"Losing {abs(per_round):.2f} strokes/round on "
                               f"{bucket} — missing "
                               f"{'left' if mean_miss < 0 else 'right'} of "
                               f"the pin."),
                      adjustment=f"aim 4 ft further {direction} on {bucket} shots",
                      expected_gain=round(abs(per_round) * 0.8, 2),
                      mechanism="aim_offset_ft", magnitude=4.0,
                      applies_to={"category": "app"})
        elif cat == "ott":
            fix = Fix(area=bucket,
                      finding=(f"Losing {abs(per_round):.2f} strokes/round "
                               f"off the tee ({bucket})."),
                      adjustment="aim at the fat of the fairway, not the corner",
                      expected_gain=round(abs(per_round) * 0.8, 2),
                      mechanism="target_line", magnitude=1.0,
                      applies_to={"category": "ott"})
        elif cat == "arg":
            fix = Fix(area=bucket,
                      finding=(f"Losing {abs(per_round):.2f} strokes/round "
                               f"around the green ({bucket})."),
                      adjustment="take one more club on short-game shots",
                      expected_gain=round(abs(per_round) * 0.8, 2),
                      mechanism="club_up", magnitude=1.0,
                      applies_to={"category": "arg"})
        else:  # putt
            fix = Fix(area=bucket,
                      finding=(f"Losing {abs(per_round):.2f} strokes/round "
                               f"putting ({bucket})."),
                      adjustment="lag putts to tap-in range — die it at the hole",
                      expected_gain=round(abs(per_round) * 0.8, 2),
                      mechanism="aggression", magnitude=-0.03,
                      applies_to={"category": "putt"})
        fix.rounds_active = 1
        self._apply(model, fix, mean_miss)
        model.active_fix = fix
        return fix

    def _apply(self, model: GolferModel, fix: Fix, mean_miss: float):
        """Apply a fix mechanically to a real engine parameter (§6.3)."""
        if fix.mechanism == "aim_offset_ft":
            # Miss left (negative) -> aim right (positive offset).
            sign = 1.0 if mean_miss < 0 else -1.0
            model.aim_biases[fix.area] = sign * abs(fix.magnitude)
        elif fix.mechanism == "club_up":
            model.club_up_buckets.add(fix.area)
        elif fix.mechanism == "trajectory":
            model.forced_trajectory[fix.area] = "knockdown"
        elif fix.mechanism == "aggression":
            model.risk_threshold_delta = max(
                -0.06, min(0.06, model.risk_threshold_delta + fix.magnitude))
        elif fix.mechanism == "target_line":
            model.aim_biases[fix.area] = 0.0
