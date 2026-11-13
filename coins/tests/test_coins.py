"""Tests for the Clubhouse Coins economy (coins-economy.md).

Run:  python3 -m unittest discover -s coins/tests -v
from ~/workspace/mas-golfs-repo.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from coins import Economy
from coins.market import Market
from coins.odds import (
    adjust_probability,
    blended_odds,
    decimal_odds,
    normalize_probs,
    opening_odds,
)
from coins.wallet import Wallet, et_date

ET = ZoneInfo("America/New_York")

# 2026-11-08 is a Sunday; 2026-11-09 is the Monday after it.
SUN = datetime(2026, 11, 8, 12, 0, tzinfo=ET)
SUN_LATE = datetime(2026, 11, 8, 23, 59, tzinfo=ET)
MON = datetime(2026, 11, 9, 0, 0, tzinfo=ET)
MON_NOON = datetime(2026, 11, 9, 12, 0, tzinfo=ET)
TUE = datetime(2026, 11, 10, 12, 0, tzinfo=ET)


def make_econ() -> Economy:
    return Economy()


def add_viewer(econ: Economy, viewer_id: str, name: str,
               when: datetime = SUN) -> Wallet:
    platform = viewer_id.split(":")[0]
    return econ.get_or_create_wallet(viewer_id, platform, name, when)


def open_two_way(econ: Economy, market_id: str, market_type: str,
                 yes_prob: float, when: datetime = SUN,
                 **kwargs) -> Market:
    return econ.create_market(
        market_id, market_type, f"Market {market_id}",
        {"yes": yes_prob, "no": 1.0 - yes_prob}, **kwargs)


def duel(econ: Economy, market_id: str, market_type: str, yes_prob: float,
         winner: str, loser: str, stake: int = 100,
         when: datetime = SUN) -> dict:
    """Two viewers stake opposite sides; ``winner``'s side wins."""
    market = open_two_way(econ, market_id, market_type, yes_prob, when=when)
    econ.place_prediction(winner, market_id, "yes", stake, when)
    econ.place_prediction(loser, market_id, "no", stake, when)
    econ.close_market(market_id)
    return econ.resolve_market(market_id, "yes", when)


class TestOdds(unittest.TestCase):
    def test_decimal_odds(self):
        self.assertEqual(decimal_odds(0.5), 2.0)
        self.assertEqual(decimal_odds(0.4), 2.5)
        self.assertEqual(decimal_odds(0.6), 1.67)

    def test_adjust_probability(self):
        # §5.3 worked values: 0.60 * 1.05 * 0.95 * 1.00 = 0.5985.
        self.assertAlmostEqual(
            adjust_probability(0.60, form=1.05, hole=0.95, condition=1.00),
            0.5985, places=4)

    def test_adjust_probability_clamps(self):
        self.assertEqual(adjust_probability(0.99, form=1.15), 0.98)
        self.assertEqual(adjust_probability(0.01, form=0.85), 0.02)
        # Factors are clamped to their ranges first: form 2.0 → 1.15.
        self.assertAlmostEqual(adjust_probability(0.50, form=2.0), 0.575)

    def test_normalize_probs_no_overround(self):
        probs = normalize_probs({"yes": 0.6, "no": 0.4})
        self.assertAlmostEqual(sum(probs.values()), 1.0)
        # Implied probabilities from opening odds sum to 1.00 (§5.1).
        odds = opening_odds({"yes": 0.6, "no": 0.4})
        implied = sum(1.0 / o for o in odds.values())
        self.assertAlmostEqual(implied, 1.0, places=2)

    def test_blended_odds_no_pool_is_model_price(self):
        opening = {"yes": 1.67, "no": 2.5}
        shown = blended_odds(opening, {"yes": 0.6, "no": 0.4}, {"yes": 0, "no": 0})
        self.assertEqual(shown, {"yes": 1.67, "no": 2.5})

    def test_blended_odds_moves_with_pool_and_caps_at_25pct(self):
        opening = {"yes": 2.0, "no": 2.0}
        # Pool 90/10 on yes: pool share 0.9, model 0.5 → displayed p 0.7
        # → odds 1.43, inside the ±25% band [1.5, 2.5]... 1.43 < 1.5,
        # so the cap binds at 1.5.
        shown = blended_odds(opening, {"yes": 0.5, "no": 0.5},
                             {"yes": 900, "no": 100})
        self.assertEqual(shown["yes"], 1.5)
        # A modest pool move stays inside the cap.
        shown = blended_odds(opening, {"yes": 0.5, "no": 0.5},
                             {"yes": 600, "no": 400})
        self.assertAlmostEqual(shown["yes"], 1 / 0.55, places=2)


class TestParimutuel(unittest.TestCase):
    def test_doc_worked_example_250(self):
        """§6.1: Yes 800 / No 1200, birdie → 100 CC on Yes returns 250."""
        # One position per market, so build the pools via fresh wallets.
        econ2 = make_econ()
        for i in range(8):
            add_viewer(econ2, f"twitch:y{i}", f"Y{i}")
        for i in range(12):
            add_viewer(econ2, f"twitch:n{i}", f"N{i}")
        market = open_two_way(econ2, "m1", "per_hole", 0.4)
        for i in range(8):
            econ2.place_prediction(f"twitch:y{i}", "m1", "yes", 100, SUN)
        for i in range(12):
            econ2.place_prediction(f"twitch:n{i}", "m1", "no", 100, SUN)
        econ2.close_market("m1")
        payouts = econ2.resolve_market("m1", "yes", SUN)
        self.assertEqual(payouts["twitch:y0"], 250)
        self.assertNotIn("twitch:n0", payouts)
        self.assertEqual(market.pool_total, 2000)

    def test_readme_worked_example_166(self):
        """100 CC → 166 back / +66 profit at effective odds 1.67.

        Pools Yes 1200 / No 800, outcome Yes:
        100 × (2000 / 1200) = 166.67 → 166 (rounded down, §6.7).
        """
        econ = make_econ()
        for i in range(12):
            add_viewer(econ, f"twitch:y{i}", f"Y{i}")
        for i in range(8):
            add_viewer(econ, f"twitch:n{i}", f"N{i}")
        market = open_two_way(econ, "m1", "per_hole", 0.4)
        for i in range(12):
            econ.place_prediction(f"twitch:y{i}", "m1", "yes", 100, SUN)
        for i in range(8):
            econ.place_prediction(f"twitch:n{i}", "m1", "no", 100, SUN)
        econ.close_market("m1")
        payouts = econ.resolve_market("m1", "yes", SUN)
        self.assertEqual(payouts["twitch:y0"], 166)
        self.assertEqual(payouts["twitch:y0"] - 100, 66)  # +66 profit
        # Dust: 2000 − 12×166 = 8 CC accrues to the bonus pool.
        self.assertEqual(market.dust(payouts), 8)
        self.assertEqual(econ.bonus_pool, 10_000 + 8)

    def test_multi_outcome_market(self):
        """§6.2: birdie / par / bogey+ pools split on the winning outcome."""
        econ = make_econ()
        for i, outcome in enumerate(["birdie", "par", "bogey"]):
            add_viewer(econ, f"twitch:{outcome}", outcome)
        market = econ.create_market(
            "m1", "per_hole", "Score on 12?",
            {"birdie": 0.12, "par": 0.60, "bogey": 0.28})
        econ.place_prediction("twitch:birdie", "m1", "birdie", 100, SUN)
        econ.place_prediction("twitch:par", "m1", "par", 100, SUN)
        econ.place_prediction("twitch:bogey", "m1", "bogey", 100, SUN)
        econ.close_market("m1")
        payouts = econ.resolve_market("m1", "par", SUN)
        self.assertEqual(payouts, {"twitch:par": 300})

    def test_nobody_on_winning_side_goes_to_bonus_pool(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        market = open_two_way(econ, "m1", "per_shot", 0.6)
        econ.place_prediction("twitch:1", "m1", "no", 100, SUN)
        econ.close_market("m1")
        payouts = econ.resolve_market("m1", "yes", SUN)
        self.assertEqual(payouts, {})
        self.assertEqual(econ.bonus_pool, 10_000 + 100)  # whole pool is dust


class TestWallets(unittest.TestCase):
    def test_starting_bankroll(self):
        econ = make_econ()
        w = add_viewer(econ, "twitch:1", "A")
        # 1,000 starting bankroll + 500 day-1 allowance on first activity.
        self.assertEqual(w.weekly_balance, 1500)
        self.assertEqual(w.alltime_balance, 1000)

    def test_daily_allowance_once_per_day_no_stacking(self):
        econ = make_econ()
        w = add_viewer(econ, "twitch:1", "A", SUN)
        self.assertEqual(w.claim_daily_allowance(SUN), 0)  # already claimed
        # Next day: claimable again. A missed day does not stack (§3.2).
        self.assertEqual(w.claim_daily_allowance(TUE), 500)
        self.assertEqual(w.claim_daily_allowance(TUE), 0)

    def test_watch_time_increments_and_cap(self):
        econ = make_econ()
        w = add_viewer(econ, "twitch:1", "A", SUN)
        self.assertEqual(w.credit_watch(7, SUN), 0)    # 7 min earns 0
        self.assertEqual(w.credit_watch(3, SUN), 10)   # 10 min total → 10 CC
        self.assertEqual(w.credit_watch(400, SUN), 350)  # capped at 360/day
        self.assertEqual(w.watch_earned_today, 360)
        self.assertEqual(w.credit_watch(60, SUN), 0)   # cap reached
        # Next day the cap resets.
        self.assertEqual(w.credit_watch(10, TUE), 10)

    def test_monday_reset_boundary(self):
        """§7.1: weekly resets Monday 00:00 ET; all-time never resets."""
        econ = make_econ()
        w = add_viewer(econ, "twitch:1", "A", SUN)
        # Win something on Sunday so the balances differ.
        add_viewer(econ, "twitch:2", "B", SUN)
        duel(econ, "m1", "per_shot", 0.6, "twitch:1", "twitch:2")
        sunday_weekly = w.weekly_balance
        sunday_alltime = w.alltime_balance
        self.assertGreater(sunday_weekly, 1000)
        # Sunday 23:59 — still the old week, no reset.
        w2 = econ.get_or_create_wallet("twitch:1", "twitch", "A", SUN_LATE)
        self.assertEqual(w2.weekly_balance, sunday_weekly)
        # Monday 00:00 — reset fires.
        w3 = econ.get_or_create_wallet("twitch:1", "twitch", "A", MON)
        self.assertEqual(w3.weekly_balance, 1500)  # 1000 reset + 500 allowance
        self.assertEqual(w3.alltime_balance, sunday_alltime)
        # Bonus pool refills to exactly 10,000 on Monday (§6.6).
        self.assertEqual(econ.bonus_pool, 10_000)

    def test_monday_winner_archived_and_crowned(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A", SUN)
        add_viewer(econ, "twitch:2", "B", SUN)
        duel(econ, "m1", "per_shot", 0.6, "twitch:1", "twitch:2")
        econ.get_or_create_wallet("twitch:1", "twitch", "A", MON)
        self.assertEqual(len(econ.weekly_winners), 1)
        self.assertEqual(econ.weekly_winners[0]["viewer_id"], "twitch:1")
        champ = [c for c in econ.wallets["twitch:1"].cosmetics
                 if c["type"] == "clubhouse_champion"]
        self.assertEqual(len(champ), 1)


class TestStakes(unittest.TestCase):
    def test_stake_caps(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        for market_type, too_low, too_high, ok in [
            ("per_shot", 5, 101, 100),
            ("per_hole", 5, 251, 250),
            ("round_level", 24, 501, 500),
        ]:
            m = open_two_way(econ, f"m-{market_type}", market_type, 0.5)
            with self.assertRaises(ValueError):
                econ.place_prediction("twitch:1", m.market_id, "yes", too_low, SUN)
            with self.assertRaises(ValueError):
                econ.place_prediction("twitch:1", m.market_id, "yes", too_high, SUN)
            econ.place_prediction("twitch:1", m.market_id, "yes", ok, SUN)

    def test_one_position_per_market(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        m = open_two_way(econ, "m1", "per_shot", 0.5)
        econ.place_prediction("twitch:1", "m1", "yes", 50, SUN)
        with self.assertRaises(ValueError):
            econ.place_prediction("twitch:1", "m1", "no", 50, SUN)

    def test_insufficient_funds(self):
        econ = make_econ()
        w = add_viewer(econ, "twitch:1", "A")
        w.weekly_balance = 50  # broke-ish viewer
        m = open_two_way(econ, "m1", "per_shot", 0.5)
        with self.assertRaises(ValueError):
            econ.place_prediction("twitch:1", "m1", "yes", 100, SUN)

    def test_no_changes_after_close(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        m = open_two_way(econ, "m1", "per_shot", 0.5)
        econ.close_market("m1")
        with self.assertRaises(ValueError):
            econ.place_prediction("twitch:1", "m1", "yes", 50, SUN)

    def test_rate_limit_60_per_hour(self):
        """§9.2: max 60 predictions per hour per viewer."""
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        for i in range(60):
            m = open_two_way(econ, f"m{i}", "per_shot", 0.5)
            econ.place_prediction("twitch:1", f"m{i}", "yes", 10, SUN)
        m = open_two_way(econ, "m60", "per_shot", 0.5)
        with self.assertRaises(ValueError):
            econ.place_prediction("twitch:1", "m60", "yes", 10, SUN)
        # An hour later the window slides open again.
        later = SUN + timedelta(hours=1, minutes=1)
        econ.place_prediction("twitch:1", "m60", "yes", 10, later)


class TestStreaksAndBonuses(unittest.TestCase):
    def _three_win_streak(self, econ):
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        for i in range(3):
            duel(econ, f"m{i}", "per_shot", 0.5, "twitch:1", "twitch:2")
        return econ.wallets["twitch:1"]

    def test_streak_bonus_10pct_at_3(self):
        """§8.1: 3 in a row → +10% of that win's profit, from the pool."""
        econ = make_econ()
        pool_before = econ.bonus_pool
        w = self._three_win_streak(econ)
        self.assertEqual(w.streak_current, 3)
        # Each duel: stake 100, payout 200, profit 100. Third win's
        # bonus is 10% of 100 = 10 CC, paid from the bonus pool.
        self.assertEqual(econ.bonus_pool, pool_before - 10)
        # Balance check: 1500 start − 300 stakes + 600 payouts + 10 bonus
        # + 100 first_bet + 100 first_win + 250 hot_hand = 2260.
        self.assertEqual(w.weekly_balance, 2260)

    def test_streak_bonus_25pct_at_5(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        for i in range(5):
            duel(econ, f"m{i}", "per_shot", 0.5, "twitch:1", "twitch:2")
        w = econ.wallets["twitch:1"]
        self.assertEqual(w.streak_current, 5)
        # Bonuses paid on every win at/above a tier: 3rd win +10, 4th win
        # +10 (still the 3-tier), 5th win +25 (the 5-tier) = 45 from pool.
        self.assertEqual(econ.bonus_pool, 10_000 - 45)
        self.assertIn("sharpshooter", w.achievements)

    def test_streak_breaks_on_loss(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        duel(econ, "m0", "per_shot", 0.5, "twitch:1", "twitch:2")
        duel(econ, "m1", "per_shot", 0.5, "twitch:1", "twitch:2")
        self.assertEqual(econ.wallets["twitch:1"].streak_current, 2)
        duel(econ, "m2", "per_shot", 0.5, "twitch:2", "twitch:1")
        self.assertEqual(econ.wallets["twitch:1"].streak_current, 0)

    def test_bonus_pool_empty_pauses_bonuses(self):
        """§10.5: empty pool → bonuses pause, stakes/payouts unaffected."""
        econ = make_econ()
        econ.bonus_pool = 0
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        for i in range(3):
            duel(econ, f"m{i}", "per_shot", 0.5, "twitch:1", "twitch:2")
        w = econ.wallets["twitch:1"]
        self.assertEqual(w.streak_current, 3)
        # No bonus paid (pool was empty), but the payout still landed.
        self.assertEqual(econ.bonus_pool, 0)

    def test_streak_bonus_scales_with_profit_not_stake(self):
        """§9.2: farming a streak on minimum stakes earns a minimum bonus."""
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        for i in range(3):
            duel(econ, f"m{i}", "per_shot", 0.5, "twitch:1", "twitch:2",
                 stake=10)
        # Profit per win is 10; the 3-streak bonus is 10% of 10 = 1 CC.
        self.assertEqual(econ.bonus_pool, 10_000 - 1)


class TestSkinsNassau(unittest.TestCase):
    def test_skins_carryover_then_win(self):
        """§6.3: un-won skin pot carries; a win splits pot + carryover."""
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        m1 = econ.create_market("s1", "skin", "Skin on 11?",
                                {"skin": 0.16, "no_skin": 0.84},
                                round_no=42, hole_no=11)
        econ.place_prediction("twitch:1", "s1", "skin", 100, SUN)
        econ.place_prediction("twitch:2", "s1", "no_skin", 100, SUN)
        econ.close_market("s1")
        payouts = econ.resolve_skin_market("s1", skin_won=False, when=SUN)
        self.assertEqual(payouts, {})
        self.assertEqual(econ.skin_carryover, 200)
        # The correct "no skin" call neither extends nor breaks the streak.
        self.assertEqual(econ.wallets["twitch:2"].streak_current, 0)
        self.assertEqual(econ.wallets["twitch:1"].streak_current, 0)

        m2 = econ.create_market("s2", "skin", "Skin on 12?",
                                {"skin": 0.12, "no_skin": 0.88},
                                round_no=42, hole_no=12)
        self.assertEqual(m2.carryover_in, 200)
        econ.place_prediction("twitch:1", "s2", "skin", 100, SUN)
        econ.place_prediction("twitch:2", "s2", "no_skin", 100, SUN)
        econ.close_market("s2")
        payouts = econ.resolve_skin_market("s2", skin_won=True, when=SUN)
        # Pot = 200 carryover + 200 pool = 400, all to the skin side.
        self.assertEqual(payouts, {"twitch:1": 400})
        self.assertEqual(econ.skin_carryover, 0)
        self.assertEqual(econ.wallets["twitch:1"].skins_won, 1)

    def test_nassau_sweep_bonus(self):
        """§6.4: win all three legs → +25% on Nassau winnings, from pool."""
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        for leg in ("front", "back", "overall"):
            m = econ.create_market(
                f"n-{leg}", "round_level", f"Nassau {leg} under par?",
                {"yes": 0.5, "no": 0.5},
                round_no=42, nassau_leg=leg)
            econ.place_prediction("twitch:1", f"n-{leg}", "yes", 25, SUN)
            econ.place_prediction("twitch:2", f"n-{leg}", "no", 25, SUN)
            econ.close_market(f"n-{leg}")
            econ.resolve_market(f"n-{leg}", "yes", SUN)
        w = econ.wallets["twitch:1"]
        # Each leg: stake 25, payout 50. Total winnings 150.
        # Sweep bonus: 25% of 150 = 37 (floor), from the bonus pool.
        # Plus the 3rd leg's streak bonus: 10% of 25 profit = 2.
        self.assertEqual(w.nassau_sweeps, 1)
        self.assertIn("nassau_sweep", w.achievements)
        self.assertEqual(econ.bonus_pool, 10_000 - 37 - 2)


class TestAchievementsCosmetics(unittest.TestCase):
    def test_first_bet_and_first_win_grants(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        duel(econ, "m0", "per_shot", 0.5, "twitch:1", "twitch:2")
        w = econ.wallets["twitch:1"]
        self.assertIn("first_bet", w.achievements)
        self.assertIn("first_win", w.achievements)
        # Grants are one-time: a second win pays no grant again.
        before = w.weekly_balance
        duel(econ, "m1", "per_shot", 0.5, "twitch:1", "twitch:2")
        self.assertEqual(w.weekly_balance, before - 100 + 200)

    def test_century_club_and_clubhouse_regular(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        # 100 predictions, spread over two hours to respect the 60/hour
        # rate limit (§9.2).
        for i in range(100):
            when = SUN + timedelta(minutes=61 * (i // 60))
            m = open_two_way(econ, f"m{i}", "per_shot", 0.5, when=when)
            econ.place_prediction("twitch:1", f"m{i}", "yes", 10, when)
        w = econ.wallets["twitch:1"]
        self.assertIn("century_club", w.achievements)
        econ.record_watch("twitch:1", 600, SUN)
        self.assertIn("clubhouse_regular", w.achievements)

    def test_prime_time_achievement(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        first_monday = datetime(2026, 11, 9, 20, 0, tzinfo=ET)
        for i in range(5):
            econ.record_prime_time("twitch:1", first_monday + timedelta(weeks=i))
        self.assertIn("prime_time", econ.wallets["twitch:1"].achievements)

    def test_cosmetic_purchase(self):
        econ = make_econ()
        w = add_viewer(econ, "twitch:1", "A")
        item = econ.buy_cosmetic("twitch:1", "chat_badge", SUN)
        self.assertEqual(item["type"], "chat_badge")
        # 1500 − 500 badge = 1000 weekly; all-time untouched by a spend.
        self.assertEqual(w.weekly_balance, 1000)
        self.assertEqual(w.alltime_balance, 1000)
        self.assertEqual(len(w.active_cosmetics(SUN)), 1)
        # Expired after 7 days.
        self.assertEqual(len(w.active_cosmetics(SUN + timedelta(days=8))), 0)
        # Clubhouse Champion is awarded, never sold (§8.3).
        with self.assertRaises(ValueError):
            econ.buy_cosmetic("twitch:1", "clubhouse_champion", SUN)
        with self.assertRaises(ValueError):
            econ.buy_cosmetic("twitch:1", "not_a_perk", SUN)

    def test_road_to_59_achievement(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        m = econ.create_market("s1", "season", "Break 60 this season?",
                               {"yes": 0.05, "no": 0.95})
        econ.place_prediction("twitch:1", "s1", "yes", 25, SUN)
        econ.place_prediction("twitch:2", "s1", "no", 25, SUN)
        econ.close_market("s1")
        econ.resolve_market("s1", "yes", SUN)
        w = econ.wallets["twitch:1"]
        self.assertIn("road_to_59", w.achievements)


class TestVoidAndLeaderboards(unittest.TestCase):
    def test_void_refunds_in_full_and_ignores_streaks(self):
        """§6.8: voided markets refund; streaks are untouched."""
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        duel(econ, "m0", "per_shot", 0.5, "twitch:1", "twitch:2")
        self.assertEqual(econ.wallets["twitch:1"].streak_current, 1)
        m = open_two_way(econ, "m1", "per_shot", 0.5)
        econ.place_prediction("twitch:1", "m1", "yes", 100, SUN)
        before = econ.wallets["twitch:1"].weekly_balance
        econ.close_market("m1")
        econ.void_market("m1", SUN)
        w = econ.wallets["twitch:1"]
        self.assertEqual(w.weekly_balance, before + 100)
        self.assertEqual(w.streak_current, 1)  # void neither breaks nor extends

    def test_leaderboards(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        duel(econ, "m0", "per_shot", 0.5, "twitch:1", "twitch:2")
        weekly = econ.weekly_leaderboard()
        self.assertEqual(weekly[0]["viewer_id"], "twitch:1")
        alltime = econ.alltime_leaderboard()
        self.assertEqual(alltime[0]["viewer_id"], "twitch:1")
        daily = econ.daily_leaderboard(SUN)
        self.assertEqual(daily[0]["viewer_id"], "twitch:1")
        wins = econ.biggest_wins()
        self.assertEqual(wins[0]["amount"], 200)
        self.assertEqual(wins[0]["viewer_id"], "twitch:1")


class TestLegalBoundary(unittest.TestCase):
    def test_no_transfer_withdrawal_or_cashout_path(self):
        """§12: the boundary is structural — these methods must not exist."""
        econ = Economy()
        for forbidden in ("transfer", "withdraw", "cash_out", "cashout",
                          "redeem", "sell_coins", "buy_coins", "send_coins",
                          "convert", "payout_cash", "gift_coins"):
            self.assertFalse(hasattr(econ, forbidden),
                             f"Economy must not have {forbidden}")
        wallet = Wallet(viewer_id="twitch:1", platform="twitch",
                        display_name="A")
        for forbidden in ("transfer", "withdraw", "cash_out", "redeem",
                          "send_coins"):
            self.assertFalse(hasattr(wallet, forbidden))

    def test_ledger_is_append_only(self):
        econ = make_econ()
        add_viewer(econ, "twitch:1", "A")
        add_viewer(econ, "twitch:2", "B")
        duel(econ, "m0", "per_shot", 0.5, "twitch:1", "twitch:2")
        ids = [e["entry_id"] for e in econ.ledger]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))
        types = {e["type"] for e in econ.ledger}
        self.assertTrue({"grant", "allowance", "stake", "payout"} <= types)


if __name__ == "__main__":
    unittest.main()
