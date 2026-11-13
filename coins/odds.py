"""Odds engine for Clubhouse Coins (coins-economy.md §5).

Decimal odds, no overround: implied probabilities across all outcomes of a
market always sum to 1.00. Base probabilities come from Mas's real rolling
stats; three adjustment factors (form, hole, conditions) are applied before
odds are set; once a market opens, displayed odds blend the model price and
the pool price 50/50 and may not move more than ±25% from the opening odds.

Pure functions only — no state, no I/O.
"""

from __future__ import annotations

# --- Adjustment factor ranges (coins-economy.md §5.3) ----------------------
FORM_MIN, FORM_MAX = 0.85, 1.15
HOLE_MIN, HOLE_MAX = 0.70, 1.30
CONDITION_MIN, CONDITION_MAX = 0.80, 1.20

# Probability clamp after adjustment (§5.3).
P_MIN, P_MAX = 0.02, 0.98

# Odds movement cap once a market is open (§5.4).
MOVE_CAP = 0.25

# Model/pool blend for displayed odds (§5.4).
MODEL_WEIGHT = 0.5

# --- Base probabilities (coins-economy.md §5.2, starting calibration) ------
# These are starting values. The odds engine must re-derive them from Mas's
# actual rolling stats (last 10 rounds minimum, last 50 preferred) at least
# once per round; callers pass the live values in and these tables are the
# fallback when no rolling stats exist yet.
BASE_SHOT_RATES = {
    "fairway_par45_tee": 0.575,          # 0.55–0.60
    "gir_approach_100yd": 0.68,
    "gir_approach_150yd": 0.60,
    "gir_approach_200yd": 0.45,
    "proximity_10ft_100yd": 0.28,
    "proximity_10ft_150yd": 0.20,
    "proximity_10ft_200yd": 0.12,
    "up_and_down_bunker": 0.45,
    "up_and_down_rough_short": 0.55,
    "one_putt_inside_6ft": 0.85,
    "one_putt_10ft": 0.40,
    "one_putt_20ft": 0.14,
}

BASE_HOLE_RATES = {
    "birdie_or_better_par5": 0.30,
    "birdie_or_better_par4": 0.16,
    "birdie_or_better_par3": 0.12,
    "par_or_better_any": 0.72,
    "bogey_or_worse_any": 0.28,
}


def clamp(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into [low, high]."""
    return max(low, min(high, value))


def adjust_probability(
    p_base: float,
    form: float = 1.0,
    hole: float = 1.0,
    condition: float = 1.0,
) -> float:
    """Adjust a base probability by the three factors (§5.3).

    ``p_adjusted = clamp(p_base * form * hole * condition, 0.02, 0.98)``.
    Each factor is itself clamped to its documented range first, so a bad
    input can never produce a price outside the model's envelope.
    """
    form = clamp(form, FORM_MIN, FORM_MAX)
    hole = clamp(hole, HOLE_MIN, HOLE_MAX)
    condition = clamp(condition, CONDITION_MIN, CONDITION_MAX)
    return clamp(p_base * form * hole * condition, P_MIN, P_MAX)


def decimal_odds(p: float) -> float:
    """Decimal odds for an implied probability: ``1 / p`` (§5.1)."""
    if p <= 0:
        raise ValueError("probability must be positive")
    return round(1.0 / p, 2)


def implied_probability(odds: float) -> float:
    """Implied probability for decimal odds: ``1 / odds``."""
    if odds <= 0:
        raise ValueError("odds must be positive")
    return 1.0 / odds


def normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    """Scale a probability dict so the values sum to exactly 1.00.

    This is the no-overround rule (§5.1): there is no vig, no house margin.
    Raises ValueError on an empty dict or a non-positive total.
    """
    total = sum(probs.values())
    if not probs or total <= 0:
        raise ValueError("probabilities must sum to a positive number")
    return {outcome: p / total for outcome, p in probs.items()}


def opening_odds(probs: dict[str, float]) -> dict[str, float]:
    """Opening decimal odds for a market, from normalized probabilities."""
    return {outcome: decimal_odds(p) for outcome, p in normalize_probs(probs).items()}


def blended_odds(
    opening: dict[str, float],
    model_probs: dict[str, float],
    pools: dict[str, int],
) -> dict[str, float]:
    """Displayed odds while a market is open (§5.4).

    ``displayed_p(side) = 0.5 * p_model(side) + 0.5 * pool_share(side)``,
    then ``displayed_odds = 1 / displayed_p``, capped at ±25% movement from
    the opening odds. A side with no pool yet keeps its model price (its
    pool share is 0 only when the total pool is 0, in which case the blend
    is the model price alone).

    Note: the ±25% cap is applied per side, so after capping the displayed
    implied probabilities may no longer sum to exactly 1.00. That is per
    spec — the cap exists to stop manipulation — and it never affects
    payouts, which are parimutuel (§6) and do not use displayed odds.
    """
    model = normalize_probs(model_probs)
    total_pool = sum(pools.values())
    displayed: dict[str, float] = {}
    for outcome, p_model in model.items():
        if total_pool > 0:
            pool_share = pools.get(outcome, 0) / total_pool
            p_display = MODEL_WEIGHT * p_model + (1.0 - MODEL_WEIGHT) * pool_share
        else:
            p_display = p_model
        odds = 1.0 / p_display
        open_odds = opening[outcome]
        odds = clamp(odds, open_odds * (1.0 - MOVE_CAP), open_odds * (1.0 + MOVE_CAP))
        displayed[outcome] = round(odds, 2)
    return displayed
