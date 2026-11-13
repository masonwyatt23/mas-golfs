"""Translation between the sim's flat events and the broadcast-stack envelope.

Two dialects exist in this repo and the bus is where they meet:

* The sim (``sim/events.py``) emits **flat** events: ``{"type": ..., "seq": ...,
  "round_no": ..., "hole": ..., ...fields}`` with types like
  ``shot_decision``, ``shot_result``, ``hole_complete``, ``round_complete``.
* The broadcast consumers — NodeCG (``nodecg-bundle/extension/index.js``)
  and the commentary service (``commentary/bus.py``) — speak the
  **broadcast-stack envelope** (``docs/broadcast-stack.md`` §1.2):
  ``{"event": ..., "seq": ..., "ts": ..., "round": ..., "hole": ...,
  "data": {...}}`` with types like ``decision``, ``strike``, ``apex``,
  ``landing``, ``hole_end``, ``round_end``.

The mapping (``translate_event``):

* ``shot_decision`` -> one ``decision`` (the plan, before the swing).
* ``shot_result`` -> three events, in order: ``strike`` (delivery),
  ``apex`` (flight), ``landing`` (outcome). The sim collapses a whole shot
  into one event; the director (§3 of the broadcast doc) needs the three
  phases separately — strike cuts to TRACER, landing cuts to PIN/CATCH.
* ``hole_complete`` -> ``hole_end``; ``round_complete`` -> ``round_end``.
* ``putt_result``, ``fifty_nine_watch``, ``milestone``, ``round_start``,
  ``hole_start`` -> same type, reshaped ``data`` per the broadcast spec.
* ``conditions_change`` -> passed through unchanged (no broadcast
  equivalent; consumers ignore unknown types).
* An event that already arrives in envelope form (``event`` + ``data``)
  passes through unchanged apart from sequencing.

Sequencing: the bus assigns its own monotonically increasing ``seq`` to
every envelope it emits (``BusSequence`` in ``server.py``). The sim's
original ``seq``/``event_id`` are preserved inside ``data`` as ``sim_seq``
/ ``sim_event_id`` for traceability — one sim event fans out to three
broadcast events, so the sim's seq cannot be reused verbatim.

Timestamps: the sim stamps events in epoch milliseconds (deterministic,
derived from round/seq); the envelope uses ISO-8601 UTC with milliseconds.

Shape convention (documented assumption): ``shot_result`` carries
``launch.curve_ft`` (signed lateral curve) and ``spin_axis_deg``. The bus
derives ``shape`` from the curve sign — negative (curving left) is a draw,
positive is a fade, under 5 ft of curve is straight. This is the
right-handed convention; Mas is left-handed, so a future pass may mirror
it — the raw ``curve_yds`` is always included alongside so consumers can
check.
"""

from __future__ import annotations

import copy
import datetime

# Risk bands for the decision event: the sim scores risk as a float
# (0 = safest); the broadcast spec wants safe / standard / aggressive.
_RISK_BANDS = ((0.15, "safe"), (0.40, "standard"))


def iso_ts(epoch_ms: int | float | None) -> str:
    """Epoch milliseconds -> ISO-8601 UTC with milliseconds (``...Z``)."""
    if epoch_ms is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    else:
        dt = datetime.datetime.fromtimestamp(epoch_ms / 1000,
                                             tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def format_handicap(value) -> str:
    """Handicap index -> broadcast string (``3.1`` -> ``"+3.1"``)."""
    if value is None:
        return "+3.1"
    if isinstance(value, str):
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num == 0:
        return "0.0"
    return f"{num:+.1f}"


def _risk_label(risk: float | None) -> str:
    if risk is None:
        return "standard"
    for limit, label in _RISK_BANDS:
        if risk < limit:
            return label
    return "aggressive"


def _shape_from_curve(curve_ft: float | None) -> str:
    if curve_ft is None or abs(curve_ft) < 5:
        return "straight"
    return "draw" if curve_ft < 0 else "fade"


def _landing_result(outcome: dict, launch: dict) -> str:
    if outcome.get("in_water"):
        return "in_water"
    if outcome.get("ob"):
        return "ob"
    if outcome.get("on_green"):
        return "green_hit"
    if outcome.get("fairway_hit"):
        return "fairway_hit"
    hazard = str(outcome.get("hazard") or "")
    if "tree" in hazard:
        return "in_trees"
    offline_ft = launch.get("offline_ft")
    if offline_ft is not None and abs(offline_ft) >= 10:
        return "missed_left" if offline_ft < 0 else "missed_right"
    return "short" if not outcome.get("on_green") else "green_hit"


def _base_envelope(event_type: str, raw: dict) -> dict:
    return {
        "event": event_type,
        "seq": 0,  # replaced by the server's sequence counter
        "ts": iso_ts(raw.get("ts")),
        "round": raw.get("round_no", 0),
        "hole": raw.get("hole", 0),
        "data": {},
    }


def _trace(raw: dict, data: dict) -> dict:
    """Keep the sim's identity on the translated event for traceability."""
    if raw.get("seq") is not None:
        data["sim_seq"] = raw["seq"]
    if raw.get("event_id"):
        data["sim_event_id"] = raw["event_id"]
    return data


def translate_event(raw: dict) -> list[dict]:
    """Translate one inbound message into broadcast-envelope events.

    Returns a list (usually one event; ``shot_result`` fans out to three).
    Returns an empty list for control messages (``subscribe``,
    ``request_round_state``, ``ping``) — the server answers those directly.
    Raises ``ValueError`` for anything that is not a dict.
    """
    if not isinstance(raw, dict):
        raise ValueError("event must be a JSON object")
    event_type = raw.get("type") or raw.get("event")
    if not event_type:
        raise ValueError("event has no type/event field")
    if event_type in ("subscribe", "request_round_state", "ping", "pong"):
        return []

    # Already in broadcast-envelope form: pass through, re-sequenced by
    # the server. (The NodeCG demo loop and any future publisher speak it.)
    if "event" in raw and isinstance(raw.get("data"), dict):
        env = dict(raw)
        env["ts"] = raw.get("ts") or iso_ts(None)
        env.setdefault("round", raw.get("round", 0))
        env.setdefault("hole", raw.get("hole", 0))
        return [env]

    if event_type == "shot_decision":
        env = _base_envelope("decision", raw)
        situation = raw.get("situation") or {}
        decision = raw.get("decision") or {}
        target = decision.get("target") or {}
        env["data"] = _trace(raw, {
            "club": decision.get("club"),
            "shot_type": decision.get("shot_type"),
            "target_yards": target.get("intended_carry_yd")
                             or situation.get("distance_yd"),
            "aim": target.get("aim_point"),
            "aim_offset_ft": target.get("aim_offset_ft"),
            "reason": raw.get("reasoning"),
            "risk": _risk_label(raw.get("risk")),
            "risk_value": raw.get("risk"),
            "lie": situation.get("lie"),
            "wind_mph": situation.get("wind_mph"),
            "ev_strokes": raw.get("ev_strokes"),
            "confidence": raw.get("confidence"),
        })
        return [env]

    if event_type == "shot_result":
        contact = raw.get("contact") or {}
        launch = raw.get("launch") or {}
        outcome = raw.get("outcome") or {}
        club_speed = contact.get("club_speed_mph") or 0
        ball_speed = launch.get("ball_speed_mph") or 0
        smash = round(ball_speed / club_speed, 2) if club_speed else None
        curve_ft = launch.get("curve_ft")
        strike = _base_envelope("strike", raw)
        strike["data"] = _trace(raw, {
            "club": raw.get("club"),
            "club_speed_mph": club_speed,
            "ball_speed_mph": ball_speed,
            "launch_deg": launch.get("launch_deg"),
            "spin_rpm": launch.get("spin_rpm"),
            "spin_axis_deg": launch.get("spin_axis_deg"),
            "smash_factor": smash,
            "contact": (contact.get("quality") or "pure"),
        })
        apex = _base_envelope("apex", raw)
        apex["data"] = _trace(raw, {
            "club": raw.get("club"),
            "apex_ft": launch.get("apex_ft"),
            "carry_yds": launch.get("carry_yd"),
            "shape": _shape_from_curve(curve_ft),
            "curve_yds": (round(curve_ft / 3, 1) if curve_ft is not None
                          else None),
        })
        landing = _base_envelope("landing", raw)
        landing["data"] = _trace(raw, {
            "club": raw.get("club"),
            "total_yds": launch.get("total_yd"),
            "lie": outcome.get("lie"),
            "dist_to_pin_ft": outcome.get("distance_to_pin_ft"),
            "result": _landing_result(outcome, launch),
            "on_green": outcome.get("on_green"),
            "fairway_hit": outcome.get("fairway_hit"),
            "penalty": outcome.get("penalty", 0),
            "drama": raw.get("drama"),
        })
        return [strike, apex, landing]

    if event_type == "putt_result":
        env = _base_envelope("putt_result", raw)
        putt = raw.get("putt") or {}
        env["data"] = _trace(raw, {
            "dist_ft": putt.get("distance_ft"),
            "made": putt.get("made"),
            "putts_this_hole": raw.get("putts_on_hole"),
            "leave_ft": putt.get("leave_ft"),
        })
        return [env]

    if event_type == "hole_start":
        env = _base_envelope("hole_start", raw)
        wind = raw.get("hole_wind") or {}
        env["data"] = _trace(raw, {
            "hole": raw.get("hole"),
            "par": raw.get("par"),
            "yards": raw.get("yardage"),
            "hole_name": raw.get("name"),
            "pin": raw.get("pin"),
            "wind_mph": wind.get("mph"),
            "wind_dir": wind.get("dir_deg"),
            "wind_effect": wind.get("effect"),
            "elevation_ft": raw.get("elevation_ft"),
        })
        return [env]

    if event_type == "round_start":
        env = _base_envelope("round_start", raw)
        course = raw.get("course") or {}
        env["data"] = _trace(raw, {
            "course": course.get("name"),
            "par": course.get("par"),
            "target_score": raw.get("target_score", 59),
            "last10_avg": raw.get("last10_avg"),
            "handicap": format_handicap(raw.get("handicap_index")),
            "focus_fix": raw.get("focus_fix"),
            "conditions": raw.get("conditions"),
        })
        return [env]

    if event_type == "hole_complete":
        env = _base_envelope("hole_end", raw)
        stats = raw.get("hole_stats") or {}
        env["data"] = _trace(raw, {
            "score": raw.get("score"),
            "par": raw.get("par"),
            "score_to_par": raw.get("score_to_par"),
            "fairway_hit": stats.get("fairway_hit"),
            "gir": stats.get("gir"),
            "putts": stats.get("putts"),
            "up_and_down": stats.get("up_and_down"),
            "strokes_gained": raw.get("strokes_gained"),
            "fifty_nine_watch": raw.get("fifty_nine_watch"),
        })
        return [env]

    if event_type == "round_complete":
        env = _base_envelope("round_end", raw)
        env["data"] = _trace(raw, {
            "score": raw.get("score"),
            "score_to_par": raw.get("score_to_par"),
            "round_stats": raw.get("stats"),
            "learning_fix": raw.get("focus_fix"),
            "new_handicap": format_handicap(raw.get("handicap")),
            "records": raw.get("records"),
            "fifty_nine_watch": raw.get("fifty_nine_watch"),
            "road_to_59": raw.get("road_to_59"),
        })
        return [env]

    if event_type == "fifty_nine_watch":
        env = _base_envelope("fifty_nine_watch", raw)
        data = {k: v for k, v in raw.items()
                if k not in ("type", "v", "event_id", "ts", "round_id",
                             "round_no", "hole", "shot_no", "seq")}
        env["data"] = _trace(raw, data)
        return [env]

    if event_type == "milestone":
        env = _base_envelope("milestone", raw)
        env["data"] = _trace(raw, {
            "type": raw.get("kind"),
            "detail": raw.get("text"),
            "value": raw.get("value"),
            "previous_best": raw.get("previous_best"),
        })
        return [env]

    # Unknown sim type (e.g. conditions_change): pass through as its own
    # type with the flat fields as data. Consumers ignore unknown types.
    env = _base_envelope(str(event_type), raw)
    data = {k: v for k, v in raw.items()
            if k not in ("type", "v", "event_id", "ts", "round_id",
                         "round_no", "hole", "shot_no", "seq")}
    env["data"] = _trace(raw, data)
    return [env]


def snapshot_event(state: dict, seq: int) -> dict:
    """Wrap a round_state snapshot in a broadcast envelope."""
    return {
        "event": "round_state",
        "seq": seq,
        "ts": iso_ts(None),
        "round": state.get("round", 0),
        "hole": state.get("hole", 0),
        "data": {"round_state": copy.deepcopy(state)},
    }


class RoundState:
    """The single source of truth (broadcast-stack §1.3).

    Updated from broadcast-envelope events as they flow through the bus.
    ``snapshot()`` returns a deep copy in the §1.3 shape, plus two additive
    fields the spec's graphics also need: ``fifty_nine_watch`` (latest
    pace state) and ``one_fix`` (the single learning fix from the last
    completed round).
    """

    def __init__(self) -> None:
        self._state: dict = {
            "golfer": "Mas",
            "round": 0,
            "hole": 0,
            "hole_par": 0,
            "score_to_par": 0,
            "thru": 0,
            "target_score": 59,
            "handicap": "+3.1",
            "last10_avg": None,
            "all_time_score": 0,
            "course_record": None,
            "best_round": None,
            "course": None,
            "current_hole": {"name": "", "par": 0, "yards": 0},
            "scorecard": [],
            "stats": {"fairways": "0/0", "gir": "0/0", "putts": 0,
                      "up_and_downs": "0/0"},
            "streak": {"birdies": 0, "bogey_free": 0},
            "coins": {"prediction_open": False, "question": "",
                      "odds": {}},
            "fifty_nine_watch": {"status": "off_pace",
                                 "prob_break_60": 0.0,
                                 "strokes_remaining": None},
            "one_fix": None,
        }

    def snapshot(self) -> dict:
        return copy.deepcopy(self._state)

    def apply(self, envelope: dict) -> None:
        """Fold one broadcast-envelope event into the snapshot."""
        event = envelope.get("event")
        data = envelope.get("data") or {}
        state = self._state

        if event == "round_state" and isinstance(data.get("round_state"),
                                                 dict):
            # A publisher re-asserting full state replaces it wholesale.
            incoming = data["round_state"]
            for key in list(state):
                if key in incoming:
                    state[key] = copy.deepcopy(incoming[key])
            return

        if event == "round_start":
            state["round"] = envelope.get("round", 0)
            state["hole"] = 0
            state["score_to_par"] = 0
            state["thru"] = 0
            state["target_score"] = data.get("target_score", 59)
            if data.get("handicap"):
                state["handicap"] = data["handicap"]
            state["last10_avg"] = data.get("last10_avg")
            state["course"] = data.get("course")
            state["scorecard"] = []
            self.__dict__["_flags"] = []
            state["stats"] = {"fairways": "0/0", "gir": "0/0", "putts": 0,
                              "up_and_downs": "0/0"}
            state["streak"] = {"birdies": 0, "bogey_free": 0}
            state["one_fix"] = data.get("focus_fix")
            return

        if event == "hole_start":
            state["hole"] = envelope.get("hole", 0)
            state["hole_par"] = data.get("par", 0)
            state["current_hole"] = {
                "name": data.get("hole_name", ""),
                "par": data.get("par", 0),
                "yards": data.get("yards", 0),
            }
            return

        if event == "hole_end":
            hole = envelope.get("hole", 0)
            entry = {"hole": hole, "par": data.get("par"),
                     "score": data.get("score"), "putts": data.get("putts")}
            card = [e for e in state["scorecard"] if e["hole"] != hole]
            card.append(entry)
            card.sort(key=lambda e: e["hole"])
            state["scorecard"] = card
            state["thru"] = len(card)
            state["score_to_par"] = sum(
                (e["score"] or 0) - (e["par"] or 0) for e in card)
            self._remember_hole_flags(data)
            self._recompute_stats()
            self._recompute_streaks(card)
            if data.get("fifty_nine_watch"):
                state["fifty_nine_watch"] = data["fifty_nine_watch"]
            return

        if event == "round_end":
            if data.get("new_handicap"):
                state["handicap"] = data["new_handicap"]
            if data.get("learning_fix"):
                state["one_fix"] = data["learning_fix"]
            return

        if event == "fifty_nine_watch":
            state["fifty_nine_watch"] = data
            return

        if event == "decision":
            state["coins"]["prediction_open"] = True
            return

    def _recompute_stats(self) -> None:
        # Stats are derived from the scorecard plus the per-hole flags the
        # bus remembers; flags arrive on hole_end events.
        card = self._state["scorecard"]
        fw_made = sum(1 for h in self._hole_flags
                      if h.get("fairway_hit") is True)
        fw_att = sum(1 for h in self._hole_flags
                     if h.get("fairway_hit") is not None)
        gir_made = sum(1 for h in self._hole_flags
                       if h.get("gir") is True)
        ud_made = sum(1 for h in self._hole_flags
                      if h.get("up_and_down") is True)
        ud_att = sum(1 for h in self._hole_flags
                     if h.get("up_and_down") is not None)
        putts = sum((h.get("putts") or 0) for h in card)
        self._state["stats"] = {
            "fairways": f"{fw_made}/{fw_att}",
            "gir": f"{gir_made}/{len(card)}",
            "putts": putts,
            "up_and_downs": f"{ud_made}/{ud_att}",
        }

    def _recompute_streaks(self, card: list[dict]) -> None:
        birdies = 0
        for entry in reversed(card):
            if (entry.get("score") is not None
                    and entry.get("par") is not None
                    and entry["score"] - entry["par"] <= -1):
                birdies += 1
            else:
                break
        bogey_free = 0
        for entry in reversed(card):
            if (entry.get("score") is not None
                    and entry.get("par") is not None
                    and entry["score"] - entry["par"] <= 0):
                bogey_free += 1
            else:
                break
        self._state["streak"] = {"birdies": birdies,
                                 "bogey_free": bogey_free}

    # Per-hole flags remembered for the stats line (not part of the §1.3
    # snapshot itself). Stored on the instance, reset with the round.
    @property
    def _hole_flags(self) -> list[dict]:
        return self.__dict__.setdefault("_flags", [])

    def _remember_hole_flags(self, data: dict) -> None:
        flags = self._hole_flags
        flags.append({"fairway_hit": data.get("fairway_hit"),
                      "gir": data.get("gir"),
                      "up_and_down": data.get("up_and_down")})
