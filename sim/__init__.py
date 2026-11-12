"""Mas Golfs simulation engine ("the Brain").

Reference implementation of ``docs/sim-engine.md`` v1.0: a fully
autonomous, self-improving, fast, free golf simulation in which Mas — a
left-handed +3 digital twin — plays 18-hole rounds on repeat at Wyatt
National, emitting the typed JSON event stream the broadcast consumes.

Quick start::

    from sim.engine import RoundEngine
    engine = RoundEngine()
    result = engine.play_round()
    print(result.score, result.stats)

Or from the command line::

    python -m sim.demo            # one round, printed scorecard
    python -m sim.calibrate       # calibration harness (spec §3.7)
"""

from .engine import RoundEngine, RoundResult
from .fifty_nine_watch import FiftyNineWatch

__all__ = ["RoundEngine", "RoundResult", "FiftyNineWatch"]
__version__ = "1.0.0"
