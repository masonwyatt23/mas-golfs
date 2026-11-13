"""Viewer wallets for Clubhouse Coins (coins-economy.md §2, §3, §7).

A wallet holds two balances: the weekly competition balance (resets every
Monday 00:00 ET to the starting bankroll) and the all-time balance (never
resets). Predictions are staked from the weekly balance; winnings credit
both. The daily allowance and watch-time earnings credit the weekly
balance only.

LEGAL BOUNDARY (see coins/__init__.py): there is no transfer, withdrawal,
cash-out, purchase, or redemption anywhere in this module. Coins can only
be earned (allowance, watch time, winnings, bonuses, achievements) and
spent on predictions and time-limited cosmetics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

STARTING_BANKROLL = 1_000
DAILY_ALLOWANCE = 500
WATCH_RATE_MINUTES = 10       # 10 CC per 10 minutes watched (§3.3)
WATCH_RATE_COINS = 10
WATCH_DAILY_CAP = 360         # 6 hours (§3.3)

# Cosmetic perks (§8.3): cost in CC, 7-day duration. Clubhouse Champion is
# NOT purchasable — it is awarded to the weekly leaderboard winner only.
COSMETICS = {
    "chat_badge": 500,
    "name_color": 1_000,
    "prediction_flair": 2_500,
}
COSMETIC_DURATION_DAYS = 7


def et_date(when: datetime) -> date:
    """Calendar date in ET for a timestamp."""
    return when.astimezone(ET).date()


def monday_of(when: datetime) -> date:
    """The Monday (ET) starting the week containing ``when``."""
    d = et_date(when)
    return date.fromordinal(d.toordinal() - d.weekday())


@dataclass
class Wallet:
    """One viewer's wallet. One wallet per platform identity (§9.1).

    ``viewer_id`` is namespaced by platform (e.g. ``twitch:12345678``);
    cross-platform wallets are never merged.
    """

    viewer_id: str
    platform: str
    display_name: str
    weekly_balance: int = STARTING_BANKROLL
    alltime_balance: int = STARTING_BANKROLL
    daily_allowance_claimed: date | None = None
    watch_minutes_today: int = 0
    watch_earned_today: int = 0
    watch_day: date | None = None
    watch_minutes_total: int = 0   # lifetime, for Clubhouse Regular (§8.2)
    streak_current: int = 0
    streak_best: int = 0
    predictions_placed: int = 0
    predictions_won: int = 0
    skins_won: int = 0
    nassau_sweeps: int = 0
    prime_time_attended: set[str] = field(default_factory=set)
    achievements: set[str] = field(default_factory=set)
    cosmetics: list[dict] = field(default_factory=list)
    daily_net: int = 0            # net winnings today (payouts + bonuses − stakes)
    daily_net_day: date | None = None
    weekly_high: int = STARTING_BANKROLL  # highest weekly balance this week
    weekly_high_at: datetime | None = None  # first time the high was reached
    created_at: datetime | None = None

    # --- earning (§3) -----------------------------------------------------

    def claim_daily_allowance(self, when: datetime) -> int:
        """Credit the 500 CC daily allowance (§3.2).

        One allowance per calendar day (ET), claimed or lost — unclaimed
        days do not stack. Returns the amount credited (500 or 0).
        """
        today = et_date(when)
        if self.daily_allowance_claimed == today:
            return 0
        self.daily_allowance_claimed = today
        self.weekly_balance += DAILY_ALLOWANCE
        self._note_weekly_high(when)
        return DAILY_ALLOWANCE

    def credit_watch(self, minutes: int, when: datetime) -> int:
        """Credit watch-time earnings (§3.3): 10 CC per 10 minutes watched.

        Credited in 10-CC increments, capped at 360 CC/day. Watching 7
        minutes earns 0; at 10 minutes, 10 CC. Returns the amount credited.
        """
        if minutes <= 0:
            return 0
        today = et_date(when)
        if self.watch_day != today:
            self.watch_day = today
            self.watch_minutes_today = 0
            self.watch_earned_today = 0
        self.watch_minutes_today += minutes
        self.watch_minutes_total += minutes
        earned_total = min(
            (self.watch_minutes_today // WATCH_RATE_MINUTES) * WATCH_RATE_COINS,
            WATCH_DAILY_CAP,
        )
        credit = earned_total - self.watch_earned_today
        if credit <= 0:
            return 0
        self.watch_earned_today = earned_total
        self.weekly_balance += credit
        self._note_weekly_high(when)
        return credit

    # --- spending / winning ----------------------------------------------

    def credit_winnings(self, amount: int, when: datetime) -> None:
        """Credit a payout or bonus to BOTH balances (§2.1)."""
        if amount <= 0:
            return
        self.weekly_balance += amount
        self.alltime_balance += amount
        self._note_weekly_high(when)
        self._note_daily_net(amount, when)

    def debit_stake(self, amount: int, when: datetime) -> None:
        """Deduct a stake from the weekly balance (§4.4)."""
        if amount <= 0:
            raise ValueError("stake must be positive")
        if amount > self.weekly_balance:
            raise ValueError("insufficient funds")
        self.weekly_balance -= amount
        self._note_daily_net(-amount, when)

    def buy_cosmetic(self, perk: str, when: datetime) -> dict:
        """Spend weekly coins on a cosmetic perk (§8.3).

        Cosmetics are time-limited (7 days), non-transferable, and never
        affect odds, payouts, stake limits, or market access. There is no
        real-money purchase path for cosmetics.
        """
        if perk not in COSMETICS:
            raise ValueError(f"unknown or non-purchasable cosmetic: {perk!r}")
        cost = COSMETICS[perk]
        if cost > self.weekly_balance:
            raise ValueError("insufficient funds")
        self.weekly_balance -= cost
        from datetime import timedelta

        item = {
            "type": perk,
            "purchased_at": when.isoformat(),
            "expires": (when + timedelta(days=COSMETIC_DURATION_DAYS)).isoformat(),
        }
        self.cosmetics.append(item)
        return item

    # --- weekly reset (§7.1) ----------------------------------------------

    def reset_weekly(self, when: datetime) -> int:
        """Reset the weekly balance to the starting bankroll (§7.1).

        Called every Monday 00:00 ET. Returns the archived weekly balance
        (the figure the weekly leaderboard ranked). The all-time balance is
        never touched. Streaks and achievements survive the reset.
        """
        archived = self.weekly_balance
        self.weekly_balance = STARTING_BANKROLL
        self.weekly_high = STARTING_BANKROLL
        self.weekly_high_at = when
        return archived

    # --- helpers ------------------------------------------------------------

    def _note_weekly_high(self, when: datetime) -> None:
        if self.weekly_balance > self.weekly_high:
            self.weekly_high = self.weekly_balance
            self.weekly_high_at = when

    def _note_daily_net(self, amount: int, when: datetime) -> None:
        today = et_date(when)
        if self.daily_net_day != today:
            self.daily_net_day = today
            self.daily_net = 0
        self.daily_net += amount

    def active_cosmetics(self, when: datetime) -> list[dict]:
        """Cosmetics whose 7-day window has not expired."""
        now = when.isoformat()
        return [c for c in self.cosmetics if c["expires"] > now]

    def to_dict(self) -> dict:
        """Serialisable snapshot (balances, streaks, counts — no secrets)."""
        return {
            "viewer_id": self.viewer_id,
            "platform": self.platform,
            "display_name": self.display_name,
            "weekly_balance": self.weekly_balance,
            "alltime_balance": self.alltime_balance,
            "streak_current": self.streak_current,
            "streak_best": self.streak_best,
            "predictions_placed": self.predictions_placed,
            "predictions_won": self.predictions_won,
            "achievements": sorted(self.achievements),
            "cosmetics": self.cosmetics,
        }
