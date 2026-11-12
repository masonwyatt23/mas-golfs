"""Dynamic conditions engine (extends spec §1.4).

Every round gets drawn conditions — weather, wind, turf firmness, and green
speed — and they can *change mid-round*. The spec's §1.4 model draws
conditions once per round; this module keeps that opening draw and adds a
per-hole random walk, so a round can start calm and clear, turn overcast
with a rising wind, and finish in light rain on softening greens.

Conditions flow everywhere they matter:
- physics: firmness sets bounce restitution (§2.5) and roll friction;
  green speed sets green roll; rain adds spin and softens the turf;
  wind acts on the ball in flight (§2.3).
- decisions: club up in wind, knockdowns into the wind, and safer
  targets on firm/fast days (§4.3, decisions.py).
- events: ``round_start`` carries the opening conditions and a
  ``conditions_change`` event fires on every notable mid-round shift.

Firmness labels: soft < 0.45, normal 0.45-0.70, firm > 0.70.
Green speed is a Stimpmeter reading in feet (slow ~9.5, tournament-fast
~12.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rng import Rng

SKY_WEIGHTS = [("clear", 0.40), ("partly_cloudy", 0.35),
               ("overcast", 0.15), ("light_rain", 0.10)]

# Sky transitions: a change moves to a neighbouring state.
SKY_NEIGHBOURS = {
    "clear": ["partly_cloudy"],
    "partly_cloudy": ["clear", "overcast"],
    "overcast": ["partly_cloudy", "light_rain"],
    "light_rain": ["overcast"],
}


def firmness_label(firmness: float) -> str:
    if firmness < 0.45:
        return "soft"
    if firmness <= 0.70:
        return "normal"
    return "firm"


def roll_mu(surface: str, firmness: float, green_speed: float) -> float:
    """Roll friction mu for a surface under current conditions (§2.5).

    Firm fairways roll further; fast greens (high Stimp) roll further.
    Rough and sand are unchanged by conditions.
    """
    if surface == "green":
        return 0.05 * (11.0 / green_speed)
    if surface == "fairway":
        return 0.09 * (1.2 - 0.4 * firmness)
    if surface in ("rough_light", "rough_heavy", "trees"):
        return 0.16
    if surface in ("bunker_fairway", "bunker_green"):
        return 0.22
    return 0.09


def green_spin_factor(firmness: float) -> float:
    """How much backspin checks the ball on the green (§2.5).

    Firm greens hold less: the effective spin that stops the ball is
    lower, so approaches release further. Soft greens check up.
    """
    return 1.15 - 0.3 * firmness


@dataclass
class Conditions:
    wind_mph: float
    wind_dir_deg: float      # direction the wind blows FROM
    temp_f: float
    sky: str                 # clear / partly_cloudy / overcast / light_rain
    firmness: float          # 0-1 (0 = soft, 1 = firm)
    green_speed: float       # Stimpmeter feet

    @property
    def firmness_name(self) -> str:
        return firmness_label(self.firmness)

    @property
    def is_raining(self) -> bool:
        return self.sky == "light_rain"

    def to_dict(self) -> dict:
        return dict(wind_mph=round(self.wind_mph, 1),
                    wind_dir_deg=round(self.wind_dir_deg),
                    temp_f=round(self.temp_f),
                    sky=self.sky,
                    firmness=round(self.firmness, 2),
                    firmness_label=self.firmness_name,
                    green_speed=round(self.green_speed, 1))


class ConditionsEngine:
    """Draws opening conditions and walks them hole by hole."""

    # Per-hole change probabilities — tuned so a typical round sees 2-4
    # notable shifts, not a new forecast every hole.
    P_WIND_SHIFT = 0.10      # a real wind shift (direction and/or speed)
    P_SKY_CHANGE = 0.08
    P_GUST = 0.60            # small wind-speed wobble

    def __init__(self, rng: Rng):
        self.conditions = self._draw_opening(rng)

    def _draw_opening(self, rng: Rng) -> Conditions:
        wind_mph = rng.triangular(0.0, 18.0, 6.0)
        if rng.random() < 0.5:
            wind_dir = rng.uniform(300.0, 330.0)  # prevailing NW (§1.4)
        else:
            wind_dir = rng.uniform(0.0, 360.0)
        temp_f = rng.gauss_clamped(62.0, 10.0, 38.0, 88.0)
        sky = rng.weighted_choice([s for s, _ in SKY_WEIGHTS],
                                  [w for _, w in SKY_WEIGHTS])
        firmness = rng.gauss_clamped(0.6, 0.12, 0.25, 0.9)
        if sky == "light_rain":
            firmness = max(0.25, firmness - 0.15)
        green_speed = rng.gauss_clamped(11.0, 0.6, 9.5, 12.5)
        return Conditions(wind_mph, wind_dir, temp_f, sky, firmness,
                          green_speed)

    def update(self, hole_no: int, rng: Rng) -> dict | None:
        """Advance conditions one hole. Returns notable changes, or None.

        A change is "notable" when it is big enough for the broadcast to
        mention: wind speed +/-3 mph, wind direction +/-15 deg, a sky
        change, a firmness-label change, or green speed +/-0.5 ft.
        """
        c = self.conditions
        before = c.to_dict()
        # Wind: mostly a wobble, sometimes a real shift.
        if rng.random() < self.P_GUST:
            c.wind_mph = min(22.0, max(0.0,
                                       c.wind_mph + rng.gauss(0.0, 1.5)))
        if rng.random() < self.P_WIND_SHIFT:
            c.wind_dir_deg = (c.wind_dir_deg + rng.gauss(0.0, 25.0)) % 360.0
            c.wind_mph = min(22.0, max(0.0,
                                       c.wind_mph + rng.gauss(0.0, 3.0)))
        # Direction drift, always a little.
        c.wind_dir_deg = (c.wind_dir_deg + rng.gauss(0.0, 5.0)) % 360.0
        # Sky.
        if rng.random() < self.P_SKY_CHANGE:
            c.sky = rng.choice(SKY_NEIGHBOURS[c.sky])
        # Temperature drift.
        c.temp_f = min(90.0, max(36.0, c.temp_f + rng.gauss(0.0, 0.5)))
        # Firmness: rain softens, sun firms, plus a slow random walk.
        if c.sky == "light_rain":
            c.firmness = max(0.25, c.firmness - 0.04)
        elif c.sky == "clear":
            c.firmness = min(0.9, c.firmness + 0.015)
        c.firmness = min(0.9, max(0.25, c.firmness + rng.gauss(0.0, 0.02)))
        # Green speed: rain slows, drying speeds up.
        if c.sky == "light_rain":
            c.green_speed = max(9.5, c.green_speed - 0.08)
        elif c.sky == "clear":
            c.green_speed = min(12.5, c.green_speed + 0.04)
        c.green_speed = min(12.5, max(9.5,
                                      c.green_speed + rng.gauss(0.0, 0.08)))
        after = c.to_dict()
        changes = {}
        if abs(after["wind_mph"] - before["wind_mph"]) >= 3.0:
            changes["wind_mph"] = after["wind_mph"]
        d_dir = abs((after["wind_dir_deg"] - before["wind_dir_deg"] + 180) % 360 - 180)
        if d_dir >= 15.0:
            changes["wind_dir_deg"] = after["wind_dir_deg"]
        if after["sky"] != before["sky"]:
            changes["sky"] = after["sky"]
        if after["firmness_label"] != before["firmness_label"]:
            changes["firmness"] = after["firmness"]
            changes["firmness_label"] = after["firmness_label"]
        if abs(after["green_speed"] - before["green_speed"]) >= 0.5:
            changes["green_speed"] = after["green_speed"]
        if not changes:
            return None
        changes["hole"] = hole_no
        return changes
