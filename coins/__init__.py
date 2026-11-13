"""Clubhouse Coins — the Mas Golfs prediction economy.

Free play money. Earned by watching and predicting. Never purchasable,
never convertible to anything of value, never transferable, never cashable
out. Status, leaderboard rank, and cosmetic perks only. No cash-out path,
no crypto, no secondary market — ever, until counsel reviews it.

LEGAL BOUNDARY (coins-economy.md §12) — enforced structurally, not just by
policy:

- There is NO transfer function in this package. No API, no method, no
  command moves coins between viewers. Coins cannot move between wallets,
  period.
- There is NO purchase path. No store, no price, no payment flow. Coins
  enter only through the documented faucets: starting bankroll, daily
  allowance, watch time, prediction winnings, streak bonuses, achievements.
- There is NO withdrawal, redemption, or cash-out path. No cash, gift
  cards, crypto, or merchandise redemption. Cosmetics are status only,
  time-limited (7 days), and non-transferable.
- There is NO marketplace for coins, cosmetics, or accounts.
- Any change to these rules requires a written review from counsel first
  (coins-economy.md §12.4). The "eventually crypto" idea stays off the
  roadmap until counsel reviews it.

Public API:
    Economy, Wallet, Market, Prediction,
    adjust_probability, decimal_odds, opening_odds, blended_odds,
    normalize_probs, BASE_SHOT_RATES, BASE_HOLE_RATES, STAKE_LIMITS,
    ACHIEVEMENTS, COSMETICS, BONUS_POOL_WEEKLY_SEED
"""

from .economy import (
    ACHIEVEMENTS,
    BONUS_POOL_WEEKLY_SEED,
    RATE_LIMIT_PER_HOUR,
    STREAK_BONUS_TIERS,
    Economy,
)
from .market import MARKET_TYPES, STAKE_LIMITS, Market, Prediction
from .odds import (
    BASE_HOLE_RATES,
    BASE_SHOT_RATES,
    adjust_probability,
    blended_odds,
    decimal_odds,
    normalize_probs,
    opening_odds,
)
from .wallet import (
    COSMETICS,
    DAILY_ALLOWANCE,
    STARTING_BANKROLL,
    WATCH_DAILY_CAP,
    Wallet,
)

__version__ = "0.1.0"

__all__ = [
    "ACHIEVEMENTS",
    "BASE_HOLE_RATES",
    "BASE_SHOT_RATES",
    "BONUS_POOL_WEEKLY_SEED",
    "COSMETICS",
    "DAILY_ALLOWANCE",
    "MARKET_TYPES",
    "RATE_LIMIT_PER_HOUR",
    "STARTING_BANKROLL",
    "STAKE_LIMITS",
    "STREAK_BONUS_TIERS",
    "WATCH_DAILY_CAP",
    "Economy",
    "Market",
    "Prediction",
    "Wallet",
    "adjust_probability",
    "blended_odds",
    "decimal_odds",
    "normalize_probs",
    "opening_odds",
]
