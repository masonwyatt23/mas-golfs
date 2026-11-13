"""The Clubhouse Coins economy service (coins-economy.md §10).

Owns wallets, markets, the append-only ledger, the bonus pool, streaks,
achievements, cosmetics, leaderboards, and the weekly Monday reset.

LEGAL BOUNDARY — structural, not just policy (§12). This service has no
method, endpoint, or code path that moves coins between viewers, converts
coins to anything of value, sells coins, or cashes coins out. Coins enter
only through the documented faucets (starting bankroll, daily allowance,
watch time, prediction winnings, streak bonuses, achievements) and leave
only through stakes and time-limited cosmetic purchases. Any future change
that touches this boundary requires a written review from counsel first.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from .market import (
    STATUS_CLOSED,
    STATUS_OPEN,
    Market,
    Prediction,
)
from .odds import adjust_probability, normalize_probs
from .wallet import (
    COSMETICS,
    DAILY_ALLOWANCE,
    STARTING_BANKROLL,
    Wallet,
    et_date,
    monday_of,
)

BONUS_POOL_WEEKLY_SEED = 10_000   # §6.6: seeded by the system, never by viewers
RATE_LIMIT_PER_HOUR = 60          # §9.2: far above human pace, far below scripts

# Streak bonus tiers (§8.1): streak length reached → bonus on that win's profit.
STREAK_BONUS_TIERS = ((12, 1.00), (8, 0.50), (5, 0.25), (3, 0.10))

# Achievements (§8.2): id → (condition description, grant in CC).
ACHIEVEMENTS = {
    "first_bet": ("Place your first prediction", 100),
    "first_win": ("Win your first prediction", 100),
    "hot_hand": ("Win 3 in a row", 250),
    "sharpshooter": ("Win 5 in a row", 500),
    "oracle": ("Win 8 in a row", 1_000),
    "century_club": ("Place 100 predictions", 500),
    "skin_collector": ("Win 10 skins", 500),
    "nassau_sweep": ("Win all three Nassau legs in one round", 1_000),
    "road_to_59": ("Win a Road to 59 season market", 2_000),
    "clubhouse_regular": ("Watch 10 hours total", 500),
    "prime_time": ("Be present for 5 Monday prime-time moments", 500),
}

NASSAU_SWEEP_BONUS = 0.25   # §6.4: +25% on total Nassau winnings for the round
WATCH_REGULAR_MINUTES = 600  # 10 hours (§8.2)


class Economy:
    """In-memory Clubhouse Coins economy.

    Persistence is the caller's job (the free-tier stack in §10.4 uses
    SQLite for the ledger and in-memory/Redis for live pools); this class
    is deliberately storage-agnostic so the same rules run in tests, in
    the demo, and on the box.
    """

    def __init__(self) -> None:
        self.wallets: dict[str, Wallet] = {}
        self.markets: dict[str, Market] = {}
        self.ledger: list[dict] = []
        self.bonus_pool: int = BONUS_POOL_WEEKLY_SEED
        self.skin_carryover: int = 0
        self.current_week_monday = None  # set on first touch
        self.weekly_winners: list[dict] = []  # archived Monday winners
        self._biggest_wins: list[dict] = []
        self._ledger_seq: int = 0
        self._prediction_seq: int = 0
        self._rate_log: dict[str, deque[datetime]] = {}
        # (round_no, viewer_id) -> {"legs": {leg: bool}, "winnings": int,
        #                            "sweep_paid": bool}
        self._nassau: dict[tuple[int, str], dict] = {}

    # --- wallets (§2, §3) ---------------------------------------------------

    def get_or_create_wallet(
        self, viewer_id: str, platform: str, display_name: str, when: datetime
    ) -> Wallet:
        """Return the wallet for a platform identity, creating it if new.

        One wallet per platform identity (§9.1); cross-platform wallets are
        never merged. A new viewer gets the 1,000 CC starting bankroll the
        moment their identity is created (§3.1).
        """
        self._maybe_rollover(when)
        wallet = self.wallets.get(viewer_id)
        if wallet is None:
            wallet = Wallet(
                viewer_id=viewer_id,
                platform=platform,
                display_name=display_name,
                created_at=when,
            )
            wallet.weekly_high_at = when
            self.wallets[viewer_id] = wallet
            self._log(wallet, "grant", STARTING_BANKROLL, when,
                      note="starting bankroll")
        self._touch(wallet, when)
        return wallet

    def _touch(self, wallet: Wallet, when: datetime) -> None:
        """First activity of the day: claim the daily allowance (§3.2)."""
        credited = wallet.claim_daily_allowance(when)
        if credited:
            self._log(wallet, "allowance", credited, when)

    def record_watch(self, viewer_id: str, minutes: int, when: datetime) -> int:
        """Credit watch-time earnings (§3.3). Returns CC credited."""
        wallet = self._require_wallet(viewer_id)
        self._maybe_rollover(when)
        self._touch(wallet, when)
        credited = wallet.credit_watch(minutes, when)
        if credited:
            self._log(wallet, "watch", credited, when)
            self._check_achievements(wallet, when)
        return credited

    # --- weekly reset (§7.1) ------------------------------------------------

    def _maybe_rollover(self, when: datetime) -> None:
        """Monday 00:00 ET reset: weekly balances → 1,000, bonus pool refills.

        The all-time balance is never touched. The weekly winner is
        archived (tie-break: earlier to reach the balance wins) and gets
        the Clubhouse Champion cosmetic for the following week (§8.3).
        """
        monday = monday_of(when)
        if self.current_week_monday is None:
            self.current_week_monday = monday
            return
        if monday <= self.current_week_monday:
            return
        winner = self._weekly_winner()
        if winner is not None:
            self.weekly_winners.append({
                "week_monday": self.current_week_monday.isoformat(),
                "viewer_id": winner.viewer_id,
                "display_name": winner.display_name,
                "balance": winner.weekly_high,
            })
            from datetime import timedelta

            winner.cosmetics.append({
                "type": "clubhouse_champion",
                "purchased_at": when.isoformat(),
                "expires": (when + timedelta(days=7)).isoformat(),
            })
        for wallet in self.wallets.values():
            wallet.reset_weekly(when)
        self.bonus_pool = BONUS_POOL_WEEKLY_SEED
        self.current_week_monday = monday

    def _weekly_winner(self) -> Wallet | None:
        """Highest weekly balance; ties go to whoever reached it first."""
        best: Wallet | None = None
        for wallet in self.wallets.values():
            if best is None:
                best = wallet
                continue
            if wallet.weekly_high > best.weekly_high:
                best = wallet
            elif (
                wallet.weekly_high == best.weekly_high
                and wallet.weekly_high_at is not None
                and best.weekly_high_at is not None
                and wallet.weekly_high_at < best.weekly_high_at
            ):
                best = wallet
        return best

    # --- markets (§5) ---------------------------------------------------------

    def create_market(
        self,
        market_id: str,
        market_type: str,
        question: str,
        base_probs: dict[str, float],
        form: float = 1.0,
        hole: float = 1.0,
        condition: float = 1.0,
        round_no: int | None = None,
        hole_no: int | None = None,
        shot: int | None = None,
        nassau_leg: str | None = None,
    ) -> Market:
        """Create a market from base probabilities (§5.2–5.3).

        The three adjustment factors are applied, the result is
        normalized (no overround, §5.1), and the opening odds are set.
        Skin markets open with the current carryover pot attached (§6.3).
        """
        adjusted = {
            outcome: adjust_probability(p, form, hole, condition)
            for outcome, p in base_probs.items()
        }
        model_probs = normalize_probs(adjusted)
        market = Market(
            market_id=market_id,
            market_type=market_type,
            question=question,
            outcomes=list(base_probs),
            model_probs=model_probs,
            adjustments={"form": form, "hole": hole, "condition": condition},
            round_no=round_no,
            hole=hole_no,
            shot=shot,
            carryover_in=self.skin_carryover if market_type == "skin" else 0,
            nassau_leg=nassau_leg,
        )
        market.open()
        self.markets[market_id] = market
        return market

    def close_market(self, market_id: str) -> Market:
        """Close a market (§5.5). Stakes lock; odds freeze."""
        market = self._require_market(market_id)
        market.close()
        return market

    # --- predictions (§4) ------------------------------------------------------

    def place_prediction(
        self,
        viewer_id: str,
        market_id: str,
        outcome: str,
        stake: int,
        when: datetime,
    ) -> Prediction:
        """Stake on a market. Validates everything server-side (§9).

        Checks, in order: market exists and is open, stake within the
        per-market limits, one position per market, sufficient weekly
        balance, and the 60-predictions-per-hour rate limit (§9.2).
        Raises ValueError with a human-readable reason on any failure.
        """
        wallet = self._require_wallet(viewer_id)
        self._maybe_rollover(when)
        self._touch(wallet, when)
        market = self._require_market(market_id)
        market.validate_stake(viewer_id, outcome, stake)
        if stake > wallet.weekly_balance:
            raise ValueError(
                "Not enough coins — your daily allowance lands tomorrow, "
                "or keep watching to earn more"
            )
        self._check_rate_limit(viewer_id, when)
        self._prediction_seq += 1
        prediction = Prediction(
            prediction_id=f"pred_{self._prediction_seq:06d}",
            market_id=market_id,
            viewer_id=viewer_id,
            outcome=outcome,
            stake=stake,
            odds_at_stake=market.current_odds()[outcome],
            placed_at=when.isoformat(),
        )
        wallet.debit_stake(stake, when)
        market.add_prediction(prediction)
        wallet.predictions_placed += 1
        self._log(wallet, "stake", -stake, when, market_id=market_id,
                  prediction_id=prediction.prediction_id)
        self._check_achievements(wallet, when)
        return prediction

    def _check_rate_limit(self, viewer_id: str, when: datetime) -> None:
        """Max 60 predictions per hour per viewer (§9.2)."""
        from datetime import timedelta

        log = self._rate_log.setdefault(viewer_id, deque())
        cutoff = when - timedelta(hours=1)
        while log and log[0] <= cutoff:
            log.popleft()
        if len(log) >= RATE_LIMIT_PER_HOUR:
            raise ValueError("rate limit: max 60 predictions per hour")
        log.append(when)

    # --- resolution (§6) -------------------------------------------------------

    def resolve_market(
        self, market_id: str, winning_outcome: str, when: datetime
    ) -> dict[str, int]:
        """Resolve a market: parimutuel payouts, streaks, bonuses (§6).

        Returns ``{viewer_id: payout}``. Payouts credit both balances.
        Streak bonuses come from the bonus pool, never from other viewers'
        stakes (§6.6). If the bonus pool is empty, bonuses pause (§10.5).
        """
        market = self._require_market(market_id)
        self._maybe_rollover(when)
        if market.market_type == "skin":
            raise ValueError("use resolve_skin_market for skin markets")
        payouts = market.resolve(winning_outcome)
        dust = market.dust(payouts)
        if dust:
            self.bonus_pool += dust
        self._apply_payouts(market, payouts, when)
        return payouts

    def resolve_skin_market(
        self, market_id: str, skin_won: bool, when: datetime
    ) -> dict[str, int]:
        """Resolve a skin market (§6.3). Updates the carryover pot."""
        market = self._require_market(market_id)
        self._maybe_rollover(when)
        payouts, new_carryover = market.resolve_skin(skin_won)
        if skin_won:
            pot = market.pool_total + market.carryover_in
            dust = market.dust(payouts, pot)
            if dust:
                self.bonus_pool += dust
            self.skin_carryover = 0
        else:
            self.skin_carryover = new_carryover
        self._apply_payouts(market, payouts, when, skin_won=skin_won)
        return payouts

    def _apply_payouts(
        self, market: Market, payouts: dict[str, int], when: datetime,
        skin_won: bool = False,
    ) -> None:
        """Credit payouts, update streaks, pay bonuses, check achievements."""
        winners = set(payouts)
        for prediction in market.predictions:
            wallet = self.wallets[prediction.viewer_id]
            if prediction.viewer_id in winners:
                payout = payouts[prediction.viewer_id]
                wallet.credit_winnings(payout, when)
                wallet.predictions_won += 1
                self._log(wallet, "payout", payout, when,
                          market_id=market.market_id,
                          prediction_id=prediction.prediction_id)
                self._record_biggest_win(wallet, payout, market, when)
                # Streak: a win extends it; the bonus is on the profit.
                wallet.streak_current += 1
                wallet.streak_best = max(wallet.streak_best,
                                         wallet.streak_current)
                profit = payout - prediction.stake
                self._pay_streak_bonus(wallet, profit, when)
                if skin_won:
                    wallet.skins_won += 1
                if market.market_type == "season":
                    self._grant_achievement(wallet, "road_to_59", when)
                if market.nassau_leg is not None:
                    self._record_nassau_leg(wallet, market, payout, when)
                self._check_achievements(wallet, when)
            elif prediction.status == "lost":
                wallet.streak_current = 0  # a wrong prediction breaks it

    def _pay_streak_bonus(self, wallet: Wallet, profit: int, when: datetime) -> None:
        """Streak bonus from the bonus pool (§8.1, §6.6).

        The bonus is a percentage of the win's PROFIT (not the payout),
        at the highest tier the streak has reached — and it applies to
        EVERY win while the streak is at or above that tier, not just the
        win that reaches the threshold (§8.1's table is "bonus on next
        win": with a 3-streak, the next win pays +10%; with a 5-streak,
        +25%). Paid from the bonus pool; if the pool is empty the bonus
        pauses and resumes at the Monday refill — it never comes from
        other viewers' stakes.
        """
        if profit <= 0:
            return
        pct = 0.0
        for threshold, tier_pct in STREAK_BONUS_TIERS:
            if wallet.streak_current >= threshold:
                pct = tier_pct
                break
        if pct == 0.0:
            return
        bonus = int(profit * pct)
        bonus = min(bonus, self.bonus_pool)
        if bonus <= 0:
            return  # bonus pool empty — bonuses pause (§10.5)
        self.bonus_pool -= bonus
        wallet.credit_winnings(bonus, when)
        self._log(wallet, "bonus", bonus, when,
                  note=f"streak {wallet.streak_current} bonus {int(pct * 100)}%")

    # --- Nassau (§6.4) ----------------------------------------------------------

    def _record_nassau_leg(
        self, wallet: Wallet, market: Market, payout: int, when: datetime
    ) -> None:
        key = (market.round_no, wallet.viewer_id)
        state = self._nassau.setdefault(
            key, {"legs": {}, "winnings": 0, "sweep_paid": False})
        state["legs"][market.nassau_leg] = True
        state["winnings"] += payout
        if (
            not state["sweep_paid"]
            and len(state["legs"]) == 3
            and all(state["legs"].get(leg) for leg in ("front", "back", "overall"))
        ):
            state["sweep_paid"] = True
            bonus = min(int(state["winnings"] * NASSAU_SWEEP_BONUS), self.bonus_pool)
            if bonus > 0:
                self.bonus_pool -= bonus
                wallet.credit_winnings(bonus, when)
                self._log(wallet, "bonus", bonus, when, note="Nassau sweep +25%")
            wallet.nassau_sweeps += 1
            self._grant_achievement(wallet, "nassau_sweep", when)

    # --- void (§6.8) --------------------------------------------------------------

    def void_market(self, market_id: str, when: datetime) -> list[Prediction]:
        """Void a market: refund every stake in full (§6.8).

        Voided markets do not count for or against streaks.
        """
        market = self._require_market(market_id)
        self._maybe_rollover(when)
        predictions = market.void()
        for prediction in predictions:
            wallet = self.wallets[prediction.viewer_id]
            wallet.credit_winnings(prediction.stake, when)
            self._log(wallet, "refund", prediction.stake, when,
                      market_id=market_id,
                      prediction_id=prediction.prediction_id)
        return predictions

    # --- cosmetics (§8.3) -----------------------------------------------------------

    def buy_cosmetic(self, viewer_id: str, perk: str, when: datetime) -> dict:
        """Buy a time-limited cosmetic with weekly coins (§8.3)."""
        wallet = self._require_wallet(viewer_id)
        self._maybe_rollover(when)
        self._touch(wallet, when)
        if perk not in COSMETICS:
            raise ValueError(
                f"unknown or non-purchasable cosmetic: {perk!r} "
                "(Clubhouse Champion is awarded, never sold)"
            )
        item = wallet.buy_cosmetic(perk, when)
        self._log(wallet, "cosmetic", -COSMETICS[perk], when, note=perk)
        return item

    # --- prime time (§8.2) --------------------------------------------------------------

    def record_prime_time(self, viewer_id: str, when: datetime) -> None:
        """Record attendance at a Monday prime-time moment (§8.2)."""
        wallet = self._require_wallet(viewer_id)
        self._maybe_rollover(when)
        wallet.prime_time_attended.add(et_date(when).isoformat())
        self._check_achievements(wallet, when)

    # --- achievements (§8.2) --------------------------------------------------------------

    def _check_achievements(self, wallet: Wallet, when: datetime) -> None:
        """Grant any newly-earned one-time achievements."""
        checks = {
            "first_bet": wallet.predictions_placed >= 1,
            "first_win": wallet.predictions_won >= 1,
            "hot_hand": wallet.streak_current >= 3,
            "sharpshooter": wallet.streak_current >= 5,
            "oracle": wallet.streak_current >= 8,
            "century_club": wallet.predictions_placed >= 100,
            "skin_collector": wallet.skins_won >= 10,
            "clubhouse_regular": wallet.watch_minutes_total >= WATCH_REGULAR_MINUTES,
            "prime_time": len(wallet.prime_time_attended) >= 5,
        }
        for achievement_id, earned in checks.items():
            if earned:
                self._grant_achievement(wallet, achievement_id, when)

    def _grant_achievement(
        self, wallet: Wallet, achievement_id: str, when: datetime
    ) -> None:
        """Pay a one-time achievement grant (once per viewer, ever)."""
        if achievement_id in wallet.achievements:
            return
        wallet.achievements.add(achievement_id)
        _, grant = ACHIEVEMENTS[achievement_id]
        wallet.credit_winnings(grant, when)
        self._log(wallet, "achievement", grant, when, note=achievement_id)

    # --- leaderboards (§7) ------------------------------------------------------------------

    def weekly_leaderboard(self, limit: int = 10) -> list[dict]:
        """Ranked by weekly balance, highest first (§7.1)."""
        ranked = sorted(
            self.wallets.values(),
            key=lambda w: (-w.weekly_balance, w.viewer_id),
        )
        return [self._board_row(w, w.weekly_balance) for w in ranked[:limit]]

    def alltime_leaderboard(self, limit: int = 10) -> list[dict]:
        """Ranked by all-time balance, highest first (§7.2). Never resets."""
        ranked = sorted(
            self.wallets.values(),
            key=lambda w: (-w.alltime_balance, w.viewer_id),
        )
        return [self._board_row(w, w.alltime_balance) for w in ranked[:limit]]

    def daily_leaderboard(self, when: datetime, limit: int = 10) -> list[dict]:
        """Ranked by coins won that day, net of stakes (§7.3)."""
        today = et_date(when)
        ranked = sorted(
            self.wallets.values(),
            key=lambda w: (
                -(w.daily_net if w.daily_net_day == today else 0), w.viewer_id
            ),
        )
        return [
            self._board_row(w, w.daily_net if w.daily_net_day == today else 0)
            for w in ranked[:limit]
        ]

    def biggest_wins(self, limit: int = 10) -> list[dict]:
        """Largest single-market payouts (§7.4)."""
        return sorted(self._biggest_wins, key=lambda r: -r["amount"])[:limit]

    @staticmethod
    def _board_row(wallet: Wallet, value: int) -> dict:
        return {
            "viewer_id": wallet.viewer_id,
            "display_name": wallet.display_name,
            "balance": value,
            "streak": wallet.streak_current,
        }

    def _record_biggest_win(
        self, wallet: Wallet, payout: int, market: Market, when: datetime
    ) -> None:
        self._biggest_wins.append({
            "viewer_id": wallet.viewer_id,
            "display_name": wallet.display_name,
            "amount": payout,
            "market_id": market.market_id,
            "question": market.question,
            "date": when.isoformat(),
        })

    # --- ledger (§10.2) --------------------------------------------------------------------

    def _log(
        self, wallet: Wallet, entry_type: str, amount: int, when: datetime,
        market_id: str | None = None, prediction_id: str | None = None,
        note: str | None = None,
    ) -> dict:
        """Append one entry to the append-only transaction log (§9.4)."""
        self._ledger_seq += 1
        entry = {
            "entry_id": f"led_{self._ledger_seq:08d}",
            "viewer_id": wallet.viewer_id,
            "type": entry_type,
            "amount": amount,
            "balance_after": wallet.weekly_balance,
            "market_id": market_id,
            "prediction_id": prediction_id,
            "timestamp": when.isoformat(),
        }
        if note is not None:
            entry["note"] = note
        self.ledger.append(entry)
        return entry

    # --- helpers -----------------------------------------------------------------------------

    def _require_wallet(self, viewer_id: str) -> Wallet:
        wallet = self.wallets.get(viewer_id)
        if wallet is None:
            raise ValueError(f"no wallet for viewer: {viewer_id!r}")
        return wallet

    def _require_market(self, market_id: str) -> Market:
        market = self.markets.get(market_id)
        if market is None:
            raise ValueError(f"no market: {market_id!r}")
        return market
