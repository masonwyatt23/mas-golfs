"""Embedded constants for the Mas Golfs simulation engine (spec §§2-3, 5).

All calibration targets come from the spec. Where the spec's tables are
incomplete (base spin per club is referenced in §2.2 but the §3.2 table does
not list it), the values here are documented implementation constants chosen
so the driver spin lands on the §3.1 target (~2,900 rpm) and spin rises
smoothly toward the wedges, as in real launch-monitor data.
"""

from __future__ import annotations

# ---------------------------------------------------------------- physics ---
BALL_MASS_KG = 0.04593          # regulation (§2.3)
BALL_DIAMETER_M = 0.04267       # regulation (§2.3)
BALL_AREA_M2 = 3.141592653589793 * (BALL_DIAMETER_M / 2.0) ** 2
GRAVITY = 9.81                  # m/s^2 (§2.3)
RHO_SEA_LEVEL = 1.225           # kg/m^3 at 59 F, sea level (§2.3)
ALTITUDE_FACTOR = 0.955         # Wyatt National ~1,400 ft (§2.3)
DT = 0.01                       # integration timestep, 100 Hz (§2.3)
MAX_FLIGHT_TIME_S = 12.0
MPH_TO_MS = 0.44704
YARD_TO_M = 0.9144
M_TO_YARD = 1.0 / YARD_TO_M
FT_TO_M = 0.3048

COURSE_RATING = 74.6            # Wyatt National, back tees (§1.2)
COURSE_SLOPE = 138
COURSE_PAR = 72
COURSE_YARDAGE = 7214
TARGET_SCORE = 59               # Road to 59 (§1.2)
GHOST_TARGET = 68               # Mason's real-world reference score (§1.2)

# ------------------------------------------------------------------- clubs ---
# Per club: loft, gapping carry (calm, sea level, flat — §5.6), smash factor
# on a pure strike (§2.2), base spin (see module docstring), mean clubhead
# speed, and delivery sigmas (§3.2).
CLUBS = {
    "driver": dict(loft=9.0,  carry=268, smash=1.49, base_spin=2900,
                   speed_mean=110.0, sig_speed=2.1, sig_face=1.15,
                   sig_path=1.30, sig_sx=6.5, sig_sy=5.0, cls="driver"),
    "3-wood": dict(loft=15.0, carry=245, smash=1.47, base_spin=3400,
                   speed_mean=104.0, sig_speed=1.9, sig_face=1.05,
                   sig_path=1.20, sig_sx=6.0, sig_sy=4.8, cls="fairway"),
    "5-wood": dict(loft=18.0, carry=228, smash=1.47, base_spin=3800,
                   speed_mean=101.0, sig_speed=1.8, sig_face=0.95,
                   sig_path=1.10, sig_sx=5.5, sig_sy=4.5, cls="fairway"),
    "hybrid": dict(loft=20.0, carry=218, smash=1.44, base_spin=4200,
                   speed_mean=99.0, sig_speed=1.8, sig_face=0.95,
                   sig_path=1.10, sig_sx=5.5, sig_sy=4.5, cls="hybrid"),
    "4-iron": dict(loft=23.0, carry=205, smash=1.40, base_spin=4600,
                   speed_mean=97.0, sig_speed=1.7, sig_face=0.90,
                   sig_path=1.05, sig_sx=5.2, sig_sy=4.2, cls="long_iron"),
    "5-iron": dict(loft=26.0, carry=193, smash=1.40, base_spin=5000,
                   speed_mean=95.0, sig_speed=1.6, sig_face=0.85,
                   sig_path=1.00, sig_sx=5.0, sig_sy=4.0, cls="long_iron"),
    "6-iron": dict(loft=29.0, carry=182, smash=1.38, base_spin=5400,
                   speed_mean=93.0, sig_speed=1.5, sig_face=0.80,
                   sig_path=0.95, sig_sx=4.8, sig_sy=3.8, cls="mid_iron"),
    "7-iron": dict(loft=32.0, carry=171, smash=1.38, base_spin=5800,
                   speed_mean=91.0, sig_speed=1.5, sig_face=0.75,
                   sig_path=0.90, sig_sx=4.5, sig_sy=3.6, cls="mid_iron"),
    "8-iron": dict(loft=36.0, carry=160, smash=1.35, base_spin=6400,
                   speed_mean=89.0, sig_speed=1.4, sig_face=0.70,
                   sig_path=0.85, sig_sx=4.2, sig_sy=3.4, cls="short_iron"),
    "9-iron": dict(loft=40.0, carry=148, smash=1.35, base_spin=7000,
                   speed_mean=87.0, sig_speed=1.3, sig_face=0.65,
                   sig_path=0.80, sig_sx=4.0, sig_sy=3.2, cls="short_iron"),
    "PW":     dict(loft=44.0, carry=136, smash=1.30, base_spin=8000,
                   speed_mean=85.0, sig_speed=1.2, sig_face=0.60,
                   sig_path=0.75, sig_sx=3.8, sig_sy=3.0, cls="wedge"),
    "GW":     dict(loft=50.0, carry=122, smash=1.30, base_spin=8500,
                   speed_mean=78.0, sig_speed=1.1, sig_face=0.55,
                   sig_path=0.70, sig_sx=3.5, sig_sy=2.8, cls="wedge"),
    "SW":     dict(loft=54.0, carry=108, smash=1.30, base_spin=9000,
                   speed_mean=73.0, sig_speed=1.0, sig_face=0.50,
                   sig_path=0.65, sig_sx=3.2, sig_sy=2.6, cls="wedge"),
    "LW":     dict(loft=58.0, carry=92,  smash=1.30, base_spin=9500,
                   speed_mean=68.0, sig_speed=1.0, sig_face=0.50,
                   sig_path=0.65, sig_sx=3.2, sig_sy=2.6, cls="wedge"),
}
# NOTE (§3.7): the wedge speed means above are lower than the spec's first
# draft (83/81/79 mph). A full sand/lob wedge is a control swing, not a
# max-effort one; at the draft speeds the wedges carried 20-35% long under
# the calibrated flight model. 78/73/68 mph reproduces the gapping table.

# Base launch angle per club (degrees), Trackman-style means for a +3 on a
# full shot. CORRECTION to §2.2: the spec's single-factor formula
# (loft x 0.72) cannot fit driver and wedges at once — it launches the
# driver at 8 deg (real: ~12 deg) and the lob wedge at 38 deg (real: ~31
# deg). The launch is therefore a per-club calibrated constant; the drawn
# angle of attack moves it only by its deviation from the club's typical
# AoA (driver +3 deg, fairway woods +1, hybrid 0, irons/wedges -4).
LAUNCH_DEG = {
    "driver": 12.0, "3-wood": 13.0, "5-wood": 14.0, "hybrid": 15.0,
    "4-iron": 16.0, "5-iron": 17.0, "6-iron": 18.0, "7-iron": 18.0,
    "8-iron": 20.0, "9-iron": 22.0, "PW": 25.0, "GW": 27.0,
    "SW": 29.0, "LW": 31.0,
}

# Smash factor by club class and contact quality (§2.2).
SMASH_BY_QUALITY = {
    "driver":    dict(pure=1.49, thin=1.44, chunk=1.31, toe=1.40, heel=1.40, shank=1.10),
    "fairway":   dict(pure=1.47, thin=1.42, chunk=1.30, toe=1.38, heel=1.38, shank=1.10),
    "hybrid":    dict(pure=1.44, thin=1.40, chunk=1.29, toe=1.36, heel=1.36, shank=1.10),
    "long_iron": dict(pure=1.40, thin=1.36, chunk=1.26, toe=1.33, heel=1.33, shank=1.10),
    "mid_iron":  dict(pure=1.38, thin=1.34, chunk=1.25, toe=1.31, heel=1.31, shank=1.10),
    "short_iron": dict(pure=1.35, thin=1.31, chunk=1.23, toe=1.29, heel=1.29, shank=1.10),
    "wedge":     dict(pure=1.30, thin=1.26, chunk=1.20, toe=1.25, heel=1.25, shank=1.10),
}

# Spin multiplier by contact quality (§2.2).
SPIN_FACTOR_BY_QUALITY = dict(pure=1.0, thin=0.72, chunk=0.55,
                              toe=0.88, heel=0.88, shank=0.60)

# Shot-type dispersion modifiers (§3.2): face/path sigma multiplier,
# carry sigma multiplier.
SHOT_TYPE_MODIFIERS = {
    "full":          dict(sig=1.00, carry=1.00),
    "knockdown":     dict(sig=0.85, carry=0.80),
    "draw":          dict(sig=1.15, carry=1.10),
    "fade":          dict(sig=1.15, carry=1.10),
    "punch":         dict(sig=0.80, carry=0.75),
    "flop":          dict(sig=1.40, carry=1.35),
    "bunker_splash": dict(sig=1.20, carry=1.25),
    "bunker_pick":   dict(sig=1.20, carry=1.25),
    "chip":          dict(sig=0.70, carry=0.70),
    "pitch":         dict(sig=0.70, carry=0.70),
    "layup":         dict(sig=0.85, carry=0.80),
    "putt":          dict(sig=1.00, carry=1.00),
}

# Intended face-angle bias for shaped shots (degrees; + = open/fade for a
# left-hander, per the §1.2 sign convention).
SHAPE_FACE_BIAS = dict(straight=0.0, draw=-1.5, fade=1.5)

# Lie effects on distance / spin / dispersion (§4.2).
# distance_factor scales ball speed by sqrt(factor) (distance ~ v^2).
LIE_EFFECTS = {
    "tee":           dict(dist=1.00, spin=1.00, sig=1.00),
    "fairway":       dict(dist=1.00, spin=1.00, sig=1.00),
    "rough_light":   dict(dist=0.97, spin=None, sig=1.15),  # spin: flyer/grabber 50/50
    "rough_heavy":   dict(dist=0.88, spin=0.60, sig=1.35),
    "bunker_fairway": dict(dist=0.97, spin=0.85, sig=1.10),
    "bunker_green":  dict(dist=1.00, spin=1.00, sig=1.00),
    "trees":         dict(dist=0.62, spin=0.80, sig=1.00),
    "fringe":        dict(dist=1.00, spin=1.00, sig=1.00),
    "green":         dict(dist=1.00, spin=1.00, sig=1.00),
}

# Roll friction mu by surface (§2.5).
ROLL_MU = dict(fairway=0.09, rough=0.16, green=0.05, sand=0.22)

# ------------------------------------------------------- baseline table -----
# Expected strokes to hole out, for a +3 (§5.5). Interpolated linearly.
# Distances: green in feet, everything else in yards.
BASELINE_GREEN_FT = [5, 10, 20, 30, 50]
BASELINE_GREEN_SG = [1.10, 1.62, 1.87, 1.95, 1.99]
BASELINE_FAIRWAY_YD = [50, 100, 150, 200, 250]
BASELINE_FAIRWAY_SG = [2.55, 2.75, 2.95, 3.20, 3.45]
BASELINE_ROUGH_LIGHT_YD = [100, 150]
BASELINE_ROUGH_LIGHT_SG = [2.95, 3.15]
BASELINE_ROUGH_HEAVY_YD = [100, 150]
BASELINE_ROUGH_HEAVY_SG = [3.25, 3.50]
BASELINE_BUNKER_GREEN = 2.75
BASELINE_BUNKER_FAIRWAY_YD = [150]
BASELINE_BUNKER_FAIRWAY_SG = [3.30]
BASELINE_TREES = 3.60
BASELINE_WATER_OB = 4.10

# ------------------------------------------------------------------ putting --
# Make probability by distance in feet (§3.5). Linear interpolation.
PUTT_MAKE_DIST_FT = [3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50]
PUTT_MAKE_PCT = [0.99, 0.97, 0.90, 0.78, 0.58, 0.38,
                 0.22, 0.13, 0.08, 0.05, 0.025, 0.012]

# ------------------------------------------------------------- calibration ---
# §3.1 targets (used by calibrate.py, §3.7).
CALIBRATION_TARGETS = dict(
    club_speed_driver_mph=(110.0, 0.05),
    ball_speed_driver_mph=(161.0, 0.05),
    driving_distance_yd=(270.0, 0.05),   # target band 265-275
    fairway_pct=(0.575, 0.05),           # target band 55-60%
    gir_pct=(0.60, 0.05),
    scoring_avg=(72.0, 0.05),            # target band 71-73
    putts_per_round=(29.5, 0.05),        # target band 29-30
    scrambling_pct=(0.60, 0.05),         # target band 55-65%
    sand_save_pct=(0.50, 0.05),          # target band 45-55%
)

# Approach proximity targets, mean feet by distance bucket (§3.3).
PROXIMITY_TARGETS = {
    (50, 75): 10.0, (75, 100): 14.0, (100, 125): 18.5,
    (125, 150): 22.5, (150, 175): 27.5, (175, 200): 35.5, (200, 999): 41.5,
}

# Form modulation (§3.6).
FORM_SIG_MULT = dict(hot=0.94, neutral=1.00, cold=1.07)
FORM_PUTT_MULT = dict(hot=1.08, neutral=1.00, cold=0.92)

# WHS small-sample table (§7.1): rounds played -> number of best
# differentials to use. 20+ rounds -> best 8 of 20.
WHS_BEST_OF = {3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3,
               12: 4, 13: 4, 14: 4, 15: 5, 16: 5, 17: 6, 18: 6, 19: 7}
