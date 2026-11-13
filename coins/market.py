"""Prediction markets for Clubhouse Coins (coins-economy.md §4, §5, §6).

Lifecycle (§5.5): announce → open → close → resolve → settle, or void.
Stakes are capped per market type, one position per viewer per market, and
locked at close — no editing, no cancelling, no early cash-out (§4.2–4.3).

Payouts are parimutuel with no house cut (§6): all staked coins go to the
winners, split proportional to stake. Payouts are rounded DOWN to the whole
coin; fractional remainders (dust) accrue to the bonus pool (§6.7).

Skins (§6.3): each hole is its own pot. If Mas does not win the skin, the
whole pool carries over to the next hole — the "no skin" side is not paid,
because the pot IS the stakes; when a skin is won, the pot (carryover +
current pool) is split proportionally among that hole's winners and the
carryover resets to zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .odds import blended_odds, opening_odds

# Per-market stake limits (§4.1): (min, max) in CC.
STAKE_LIMITS = {
    "per_shot": (10, 100),
    "per_hole": (10, 250),
    "round_level": (25, 500),
    "skin": (10, 250),        # skins are per-hole markets (§6.3)
    "season": (25, 500),      # Road to 59 season markets (§6.5)
}

MARKET_TYPES = tuple(STAKE_LIMITS)

# Market statuses (§5.5).
STATUS_ANNOUNCED = "announced"
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
STATUS_RESOLVED = "resolved"
STATUS_VOID = "void"


@dataclass
class Prediction:
    """A single stake (§10.2)."""

    prediction_id: str
    market_id: str
    viewer_id: str
    outcome: str
    stake: int
    odds_at_stake: float
    placed_at: str
    status: str = "pending"   # pending | won | lost | void | pushed
    payout: int | None = None
    resolved_at: str | None = None


@dataclass
class Market:
    """One prediction market (§10.2)."""

    market_id: str
    market_type: str
    question: str
    outcomes: list[str]
    model_probs: dict[str, float]
    adjustments: dict[str, float] = field(default_factory=dict)
    round_no: int | None = None
    hole: int | None = None
    shot: int | None = None
    status: str = STATUS_ANNOUNCED
    pools: dict[str, int] = field(default_factory=dict)
    predictions: list[Prediction] = field(default_factory=list)
    opening: dict[str, float] = field(default_factory=dict)
    winning_outcome: str | None = None
    carryover_in: int = 0     # skin carryover pot entering this market (§6.3)
    nassau_leg: str | None = None  # "front" | "back" | "overall" (§6.4)

    def __post_init__(self) -> None:
        if self.market_type not in MARKET_TYPES:
            raise ValueError(f"unknown market type: {self.market_type!r}")
        if set(self.outcomes) != set(self.model_probs):
            raise ValueError("outcomes and model_probs must cover the same sides")
        self.pools = {outcome: 0 for outcome in self.outcomes}
        self.opening = opening_odds(self.model_probs)

    # --- lifecycle (§5.5) --------------------------------------------------

    def open(self) -> None:
        """Announce → open. Viewers may stake from now until close."""
        if self.status != STATUS_ANNOUNCED:
            raise ValueError(f"cannot open a market in status {self.status}")
        self.status = STATUS_OPEN

    def close(self) -> None:
        """Close the market. Stakes lock; odds freeze (§4.3)."""
        if self.status != STATUS_OPEN:
            raise ValueError(f"cannot close a market in status {self.status}")
        self.status = STATUS_CLOSED

    @property
    def min_stake(self) -> int:
        return STAKE_LIMITS[self.market_type][0]

    @property
    def max_stake(self) -> int:
        return STAKE_LIMITS[self.market_type][1]

    @property
    def pool_total(self) -> int:
        return sum(self.pools.values())

    def current_odds(self) -> dict[str, float]:
        """Displayed odds right now (§5.4): 50/50 model/pool blend, ±25% cap."""
        return blended_odds(self.opening, self.model_probs, self.pools)

    # --- staking (§4) ------------------------------------------------------

    def validate_stake(self, viewer_id: str, outcome: str, stake: int) -> None:
        """Validate a stake. Raises ValueError with a human-readable reason."""
        if self.status != STATUS_OPEN:
            raise ValueError("market is not open")
        if outcome not in self.outcomes:
            raise ValueError(f"unknown outcome: {outcome!r}")
        if stake < self.min_stake:
            raise ValueError(
                f"minimum stake is {self.min_stake} CC for {self.market_type}"
            )
        if stake > self.max_stake:
            raise ValueError(
                f"maximum stake is {self.max_stake} CC for {self.market_type}"
            )
        if any(p.viewer_id == viewer_id for p in self.predictions):
            raise ValueError("one position per market — you already staked here")

    def add_prediction(self, prediction: Prediction) -> None:
        """Record an accepted stake and grow the pool."""
        self.pools[prediction.outcome] += prediction.stake
        self.predictions.append(prediction)

    # --- resolution (§6) ---------------------------------------------------

    def resolve(self, winning_outcome: str) -> dict[str, int]:
        """Resolve the market and compute parimutuel payouts (§6.1–6.2).

        Returns ``{viewer_id: payout}`` for the winners (losers are absent,
        i.e. they receive 0). Each payout is
        ``floor(stake * pool_total / pool(winning_outcome))`` — stake
        returned plus a proportional share of the losing side's pool, with
        no house cut. The caller credits the payouts and handles the dust
        (``pool_total - sum(payouts)``), which accrues to the bonus pool
        (§6.7). For skin markets the carryover pot is included in
        ``pool_total`` via :meth:`resolve_skin`.
        """
        if self.status != STATUS_CLOSED:
            raise ValueError(f"cannot resolve a market in status {self.status}")
        if winning_outcome not in self.outcomes:
            raise ValueError(f"unknown outcome: {winning_outcome!r}")
        self.status = STATUS_RESOLVED
        self.winning_outcome = winning_outcome
        return self._split_pool(self.pool_total, winning_outcome)

    def resolve_skin(self, skin_won: bool) -> tuple[dict[str, int], int]:
        """Resolve a skin market (§6.3).

        Returns ``(payouts, new_carryover)``. If the skin is won, the pot
        (carryover + current pool) is split among the "skin" side and the
        carryover resets to 0. If not won, nobody is paid and the whole
        pool carries to the next hole.
        """
        if self.market_type != "skin":
            raise ValueError("resolve_skin is only for skin markets")
        if self.status != STATUS_CLOSED:
            raise ValueError(f"cannot resolve a market in status {self.status}")
        if skin_won:
            self.status = STATUS_RESOLVED
            self.winning_outcome = "skin"
            pot = self.pool_total + self.carryover_in
            payouts = self._split_pool(pot, "skin")
            return payouts, 0
        self.status = STATUS_RESOLVED
        self.winning_outcome = "no_skin"
        # The whole pool carries to the next hole (§6.3). The "skin" side
        # was wrong (streak breaks); the "no skin" side was right, but its
        # stake feeds the pot, so those predictions are "pushed" — they
        # neither extend nor break the streak and pay nothing.
        for p in self.predictions:
            if p.outcome == "no_skin":
                p.status = "pushed"
            else:
                p.status = "lost"
            p.payout = 0
        return {}, self.carryover_in + self.pool_total

    def _split_pool(self, pot: int, winning_outcome: str) -> dict[str, int]:
        """Proportional split of ``pot`` among the winning side's stakers."""
        winning_pool = self.pools[winning_outcome]
        if winning_pool <= 0:
            # Nobody staked on the winning side: the whole pot is dust.
            for p in self.predictions:
                p.status = "lost"
                p.payout = 0
            return {}
        payouts: dict[str, int] = {}
        for p in self.predictions:
            if p.outcome == winning_outcome:
                p.status = "won"
                p.payout = (p.stake * pot) // winning_pool
                payouts[p.viewer_id] = p.payout
            else:
                p.status = "lost"
                p.payout = 0
        return payouts

    def dust(self, payouts: dict[str, int], pot: int | None = None) -> int:
        """Fractional remainder after rounding payouts down (§6.7)."""
        pot = self.pool_total if pot is None else pot
        return pot - sum(payouts.values())

    # --- void (§6.8) --------------------------------------------------------

    def void(self) -> list[Prediction]:
        """Void the market: all stakes are refunded in full (§6.8).

        Returns the predictions so the caller can refund each stake.
        Voided markets do not count for or against streaks.
        """
        if self.status in (STATUS_RESOLVED, STATUS_VOID):
            raise ValueError(f"cannot void a market in status {self.status}")
        self.status = STATUS_VOID
        for p in self.predictions:
            p.status = "void"
        return list(self.predictions)

    # --- display (§5.5, broadcast-stack §4.3) -------------------------------

    def to_replicant(self) -> dict:
        """The NodeCG ``prediction`` replicant shape for this market."""
        return {
            "question": self.question,
            "odds": self.current_odds(),
            "pool_coins": self.pool_total,
            "open": self.status == STATUS_OPEN,
            "market_id": self.market_id,
            "status": self.status,
        }
