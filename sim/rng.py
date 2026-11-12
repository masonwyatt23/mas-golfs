"""Deterministic PRNG for the Mas Golfs simulation engine.

Spec §8.4: the engine is seeded per round (``seed = hash(round_no, course_id)``)
and all RNG draws come from a single seeded PRNG (mulberry32) so a round can
be replayed byte-identically.

Everything in this module is pure Python, stdlib only, and deterministic
across platforms.
"""

from __future__ import annotations

import math


def seed_for_round(round_no: int, course_id: str = "wyatt_national") -> int:
    """FNV-1a hash of ``"<course_id>:<round_no>"`` -> 32-bit seed (§8.4)."""
    h = 0x811C9DC5
    for ch in f"{course_id}:{round_no}":
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


class Rng:
    """mulberry32 — small, fast, deterministic across platforms."""

    __slots__ = ("state", "_spare", "_has_spare")

    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF
        self._spare = 0.0
        self._has_spare = False

    def next_u32(self) -> int:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        return (t ^ (t >> 14)) & 0xFFFFFFFF

    def random(self) -> float:
        """Uniform [0, 1)."""
        return self.next_u32() / 4294967296.0

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.random()

    def triangular(self, lo: float, hi: float, mode: float) -> float:
        """Triangular distribution (spec §1.4 wind model)."""
        u = self.random()
        c = (mode - lo) / (hi - lo)
        if u < c:
            return lo + math.sqrt(u * (hi - lo) * (mode - lo))
        return hi - math.sqrt((1.0 - u) * (hi - lo) * (hi - mode))

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Normal draw (Box-Muller, with a cached spare)."""
        if self._has_spare:
            self._has_spare = False
            return mu + sigma * self._spare
        u1 = max(self.random(), 1e-12)
        u2 = self.random()
        r = math.sqrt(-2.0 * math.log(u1))
        theta = 2.0 * math.pi * u2
        self._spare = r * math.sin(theta)
        self._has_spare = True
        return mu + sigma * r * math.cos(theta)

    def gauss_clamped(self, mu: float, sigma: float, lo: float, hi: float) -> float:
        """Normal draw clamped to [lo, hi]."""
        return min(hi, max(lo, self.gauss(mu, sigma)))

    def choice(self, items):
        return items[int(self.random() * len(items))]

    def weighted_choice(self, items, weights):
        total = sum(weights)
        roll = self.random() * total
        acc = 0.0
        for item, w in zip(items, weights):
            acc += w
            if roll <= acc:
                return item
        return items[-1]
