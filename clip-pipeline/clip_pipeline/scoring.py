"""Drama scoring — the detection stage of the auto-clip system.

Implements the drama model from docs/launch-playbook.md §1.1 (detection
table) and docs/broadcast-stack.md §3.5 (replay thresholds):

    Moment                  Drama   Save replay?
    ----------------------  ------  ------------
    hole-out (ace/chip-in)    100   always
    road to 59 (shooting 59)  100   always
    eagle                      95   always
    near-miss (<= 6 in)        85   always
    great recovery             80   always
    best decision              75   always
    worst miss                 75   always
    streak (3rd birdie in a    70   always
      row, bogey-free 9)
    record-chase (on pace)     70   always while on pace
    birdie                     60   only if first of the round
                                    or breaks a 5+ hole drought

Replay-save threshold (broadcast-stack §3.5): drama >= 60 triggers
``ReplayBuffer.Save`` — the moment enters the clip library. Below 60 a
moment is routine and is not saved.

Record-chase boost: any moment on a hole where Mas is on 59 pace
(``score_vs_target`` <= 2 at hole start) AND 9+ under par scores +10
drama, capped at 100. The chase only gets interesting deep in the round,
so the boost does not apply early.

One clip per hole, unless drama >= 90 (broadcast-stack replay rule: a
hole-out earns a second look). That rule is applied at selection time in
manifest.py, not here — the scorer reports every moment it finds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .course import PACE_TO_PAR, hole_name, hole_par

# --- Thresholds (see module docstring) -------------------------------------

REPLAY_SAVE_THRESHOLD = 60
SECOND_LOOK_THRESHOLD = 90
ON_PACE_THRESHOLD = 2
RECORD_CHASE_MIN_SCORE = -9  # standalone chase moments only this deep
NEAR_MISS_FT = 0.5           # 6 inches
MISHITS = {"thin", "chunk", "toe", "heel", "shank"}
TROUBLE_LIES = {"trees", "rough_heavy", "bunker_fairway", "bunker_green"}
STRATEGIC_SHOT_TYPES = {"knockdown", "draw", "fade", "punch"}


@dataclass
class Moment:
    """One detected clip-worthy moment."""

    moment_id: str
    moment_type: str  # hole_out | road_to_59 | eagle | near_miss | recovery |
                      # best_decision | worst_miss | streak | record_chase | birdie
    drama: int        # 0-100
    round_no: int
    hole: int
    hole_name: str
    par: int
    shot_no: int      # shot the moment is anchored to (0 = hole-level)
    trigger_event_id: str
    trigger_seq: int
    ts: int           # epoch ms of the trigger event (replay buffer anchor)
    score_to_par: int  # cumulative score to par after the hole
    context: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def save_replay(self) -> bool:
        return self.drama >= REPLAY_SAVE_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "moment_id": self.moment_id,
            "moment_type": self.moment_type,
            "drama": self.drama,
            "round_no": self.round_no,
            "hole": self.hole,
            "hole_name": self.hole_name,
            "par": self.par,
            "shot_no": self.shot_no,
            "trigger_event_id": self.trigger_event_id,
            "trigger_seq": self.trigger_seq,
            "ts": self.ts,
            "score_to_par": self.score_to_par,
            "save_replay": self.save_replay,
            "context": self.context,
            "reasons": self.reasons,
        }


class _RoundState:
    """Mutable per-round tracking while the event stream is scanned."""

    def __init__(self) -> None:
        self.round_no: int = 0
        self.hole: int = 0
        self.par: int = 0
        self.score_to_par: int = 0  # entering the current hole
        self.on_pace: bool = False
        self.strokes_vs_target: int = 99
        self.last_decision: dict | None = None
        self.last_shot: dict | None = None
        self.consecutive_birdies: int = 0
        self.birdie_drought: int = 0  # holes since last under-par hole
        self.first_birdie_seen: bool = False
        self.hole_context: dict[int, dict] = {}  # hole -> {on_pace, score_entering}


def _moment_id(round_no: int, hole: int, moment_type: str, seq: int) -> str:
    return f"R{round_no:04d}-H{hole:02d}-{moment_type}-{seq:04d}"


def _has_moment(moments: list[Moment], hole: int, moment_types: set[str]) -> bool:
    return any(m.hole == hole and m.moment_type in moment_types for m in moments)


def _shot_context(ev: dict, state: _RoundState) -> dict:
    """Human-readable context for a shot, pulled from decision + result."""
    dec = state.last_decision or {}
    decision = dec.get("decision", {}) if isinstance(dec, dict) else {}
    situation = dec.get("situation", {}) if isinstance(dec, dict) else {}
    outcome = ev.get("outcome", {})
    ctx: dict = {
        "club": ev.get("club") or decision.get("club"),
        "shot_type": ev.get("shot_type") or decision.get("shot_type"),
        "lie": situation.get("lie"),
        "contact_quality": (ev.get("contact") or {}).get("quality"),
        "distance_yd": situation.get("distance_yd"),
        "decision_reasoning": decision.get("reasoning"),
        "intended_carry_yd": (decision.get("target") or {}).get("intended_carry_yd"),
        "distance_to_pin_ft": outcome.get("distance_to_pin_ft"),
        "commentary": ev.get("commentary"),
        "sim_drama": ev.get("drama"),
    }
    return {k: v for k, v in ctx.items() if v is not None}


def _score_shot(ev: dict, state: _RoundState, moments: list[Moment]) -> None:
    """Score one shot_result event. At most one moment per shot (the best)."""
    outcome = ev.get("outcome", {})
    contact = ev.get("contact", {})
    launch = ev.get("launch", {})
    dist_pin = outcome.get("distance_to_pin_ft")
    quality = ev.get("shot_quality", 1.0)
    candidates: list[tuple[int, str, list[str]]] = []

    # Hole-out: ball holed from off the green (ace, chip-in, holed bunker shot).
    if dist_pin == 0:
        candidates.append((100, "hole_out", ["ball holed from off the green"]))
    # Near-miss: shot finishing within 6 inches without dropping.
    elif isinstance(dist_pin, (int, float)) and 0 < dist_pin <= NEAR_MISS_FT:
        candidates.append((85, "near_miss", [f"stopped {dist_pin} ft from the hole"]))

    # Worst miss: named mishit with a bad outcome.
    mishit = contact.get("quality") in MISHITS
    bad_outcome = (
        outcome.get("penalty", 0) > 0
        or outcome.get("in_water")
        or outcome.get("ob")
        or quality <= 0.45
    )
    if mishit and bad_outcome:
        candidates.append((75, "worst_miss", [f"named mishit: {contact.get('quality')}"]))
    elif mishit:
        # A mishit that cost > 40 yards vs. the intended carry.
        intended = ((state.last_decision or {}).get("decision") or {}).get("target", {})
        intended_carry = intended.get("intended_carry_yd")
        total = launch.get("total_yd")
        if intended_carry and total is not None and total < intended_carry - 40:
            candidates.append(
                (75, "worst_miss", [f"{contact.get('quality')}: lost {intended_carry - total} yd vs plan"])
            )

    # Best decision: a risky, well-executed strategic choice that paid off.
    dec = (state.last_decision or {}).get("decision", {})
    risk = dec.get("risk", 0)
    if (
        risk >= 0.25
        and quality >= 0.8
        and (outcome.get("gir") or outcome.get("on_green") or (isinstance(dist_pin, (int, float)) and dist_pin <= 15))
    ):
        candidates.append((75, "best_decision", [f"risk {risk:.2f} paid off: {dec.get('reasoning', '')}"]))
    elif (
        ev.get("shot_type") in STRATEGIC_SHOT_TYPES
        and quality >= 0.8
        and (outcome.get("gir") or outcome.get("on_green"))
    ):
        candidates.append((75, "best_decision", [f"{ev.get('shot_type')} executed to the green"]))

    # Great recovery: a trouble lie turned into a green in regulation.
    # (On-green-but-not-GIR recoveries are scored at hole level, via
    # up-and-down / sand-save, and only when the hole is par or better —
    # a bunker splash that still ends in bogey is not a recovery.)
    lie = ((state.last_decision or {}).get("situation") or {}).get("lie")
    if lie in TROUBLE_LIES and outcome.get("gir"):
        candidates.append((80, "recovery", [f"recovered from {lie} to the green in regulation"]))

    if not candidates:
        return
    # One moment per shot: keep the highest drama, merge the reasons.
    drama, moment_type, reasons = max(candidates, key=lambda c: c[0])
    ctx = _shot_context(ev, state)
    moments.append(
        Moment(
            moment_id=_moment_id(state.round_no, state.hole, moment_type, ev["seq"]),
            moment_type=moment_type,
            drama=drama,
            round_no=state.round_no,
            hole=state.hole,
            hole_name=hole_name(state.hole),
            par=state.par,
            shot_no=ev.get("shot_no", 0),
            trigger_event_id=ev["event_id"],
            trigger_seq=ev["seq"],
            ts=ev["ts"],
            score_to_par=state.score_to_par,
            context=ctx,
            reasons=reasons,
        )
    )


def _score_putt(ev: dict, state: _RoundState, moments: list[Moment]) -> None:
    """Score one putt_result event. Only near-misses make the cut."""
    putt = ev.get("putt", {})
    if putt.get("made"):
        return
    leave = putt.get("leave_ft")
    if isinstance(leave, (int, float)) and 0 < leave <= NEAR_MISS_FT:
        ctx = {
            "club": "putter",
            "shot_type": "putt",
            "distance_yd": None,
            "commentary": ev.get("commentary"),
        }
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, state.hole, "near_miss", ev["seq"]),
                moment_type="near_miss",
                drama=85,
                round_no=state.round_no,
                hole=state.hole,
                hole_name=hole_name(state.hole),
                par=state.par,
                shot_no=ev.get("shot_no", 0),
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=state.score_to_par,
                context={k: v for k, v in ctx.items() if v is not None},
                reasons=[f"putt burned the edge, stopped {leave} ft short"],
            )
        )


def _score_hole(ev: dict, state: _RoundState, moments: list[Moment]) -> None:
    """Score one hole_complete event (eagle, birdie, recovery, streak, chase)."""
    score_name = ev.get("score_name")
    hole_stats = ev.get("hole_stats", {})
    new_score = ev.get("score_to_par", state.score_to_par)
    under_par = score_name in {"eagle", "birdie", "hole_in_one", "albatross"}

    # Shot-anchored moments on this hole were scored with the score
    # entering the hole; the clip copy needs the score after the hole.
    for m in moments:
        if m.hole == state.hole and m.shot_no > 0:
            m.score_to_par = new_score

    # Road to 59: the round that ends at 59 (or better).
    if state.hole == 18 and new_score <= PACE_TO_PAR:
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, 18, "road_to_59", ev["seq"]),
                moment_type="road_to_59",
                drama=100,
                round_no=state.round_no,
                hole=18,
                hole_name=hole_name(18),
                par=state.par,
                shot_no=0,
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=new_score,
                context={"commentary": ev.get("commentary")},
                reasons=[f"finished {new_score} under par — 59 at Wyatt National"],
            )
        )

    # Eagle.
    if score_name == "eagle":
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, state.hole, "eagle", ev["seq"]),
                moment_type="eagle",
                drama=95,
                round_no=state.round_no,
                hole=state.hole,
                hole_name=hole_name(state.hole),
                par=state.par,
                shot_no=0,
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=new_score,
                context={"commentary": ev.get("commentary")},
                reasons=["hole completed 2 under par"],
            )
        )

    # Birdie: only the round's first, or one that breaks a 5+ hole drought.
    if score_name == "birdie":
        if not state.first_birdie_seen or state.birdie_drought >= 5:
            moments.append(
                Moment(
                    moment_id=_moment_id(state.round_no, state.hole, "birdie", ev["seq"]),
                    moment_type="birdie",
                    drama=60,
                    round_no=state.round_no,
                    hole=state.hole,
                    hole_name=hole_name(state.hole),
                    par=state.par,
                    shot_no=0,
                    trigger_event_id=ev["event_id"],
                    trigger_seq=ev["seq"],
                    ts=ev["ts"],
                    score_to_par=new_score,
                    context={"commentary": ev.get("commentary")},
                    reasons=[
                        "first birdie of the round"
                        if not state.first_birdie_seen
                        else f"broke a {state.birdie_drought}-hole birdie drought"
                    ],
                )
            )

    # Great recovery: par or better after getting up-and-down / a sand save.
    if (hole_stats.get("up_and_down") or hole_stats.get("sand_save")) and score_name in {
        "par",
        "birdie",
        "eagle",
    }:
        kind = "sand save" if hole_stats.get("sand_save") else "up-and-down"
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, state.hole, "recovery", ev["seq"]),
                moment_type="recovery",
                drama=80,
                round_no=state.round_no,
                hole=state.hole,
                hole_name=hole_name(state.hole),
                par=state.par,
                shot_no=0,
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=new_score,
                context={"commentary": ev.get("commentary")},
                reasons=[f"{kind} to save {score_name}"],
            )
        )

    # Streak: 3rd consecutive birdie (or better).
    if under_par:
        state.consecutive_birdies += 1
    else:
        state.consecutive_birdies = 0
    if state.consecutive_birdies == 3 and not _has_moment(moments, state.hole, {"streak"}):
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, state.hole, "streak", ev["seq"]),
                moment_type="streak",
                drama=70,
                round_no=state.round_no,
                hole=state.hole,
                hole_name=hole_name(state.hole),
                par=state.par,
                shot_no=0,
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=new_score,
                context={"commentary": ev.get("commentary")},
                reasons=["third consecutive birdie"],
            )
        )

    # Record-chase: on pace, deep in the round, and nothing else fired here.
    if (
        state.on_pace
        and new_score <= RECORD_CHASE_MIN_SCORE
        and score_name in {"par", "birdie", "eagle"}
        and not any(m.hole == state.hole for m in moments)
    ):
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, state.hole, "record_chase", ev["seq"]),
                moment_type="record_chase",
                drama=70,
                round_no=state.round_no,
                hole=state.hole,
                hole_name=hole_name(state.hole),
                par=state.par,
                shot_no=0,
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=new_score,
                context={"commentary": ev.get("commentary")},
                reasons=[f"on pace for 59 at {new_score} under par"],
            )
        )

    # Update drought / first-birdie tracking, then the running score.
    if under_par:
        state.birdie_drought = 0
        state.first_birdie_seen = True
    else:
        state.birdie_drought += 1
    state.score_to_par = new_score


def _score_milestone(ev: dict, state: _RoundState, moments: list[Moment]) -> None:
    """Score one milestone event. Dedupes against moments already detected."""
    kind = ev.get("kind")
    if kind == "hole_in_one" and not _has_moment(moments, state.hole, {"hole_out"}):
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, state.hole, "hole_out", ev["seq"]),
                moment_type="hole_out",
                drama=100,
                round_no=state.round_no,
                hole=state.hole,
                hole_name=hole_name(state.hole),
                par=state.par,
                shot_no=ev.get("shot_no", 0),
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=state.score_to_par,
                context={"commentary": ev.get("text")},
                reasons=["hole-in-one"],
            )
        )
    elif kind in {"course_record", "course_record_tied", "personal_best", "road_to_59_step"}:
        if not _has_moment(moments, state.hole, {"road_to_59"}):
            moments.append(
                Moment(
                    moment_id=_moment_id(state.round_no, state.hole, "road_to_59", ev["seq"]),
                    moment_type="road_to_59",
                    drama=100,
                    round_no=state.round_no,
                    hole=state.hole,
                    hole_name=hole_name(state.hole),
                    par=state.par,
                    shot_no=ev.get("shot_no", 0),
                    trigger_event_id=ev["event_id"],
                    trigger_seq=ev["seq"],
                    ts=ev["ts"],
                    score_to_par=state.score_to_par,
                    context={"commentary": ev.get("text")},
                    reasons=[ev.get("text", kind)],
                )
            )
    elif kind == "streak_birdie_3" and not _has_moment(moments, state.hole, {"streak"}):
        moments.append(
            Moment(
                moment_id=_moment_id(state.round_no, state.hole, "streak", ev["seq"]),
                moment_type="streak",
                drama=70,
                round_no=state.round_no,
                hole=state.hole,
                hole_name=hole_name(state.hole),
                par=state.par,
                shot_no=ev.get("shot_no", 0),
                trigger_event_id=ev["event_id"],
                trigger_seq=ev["seq"],
                ts=ev["ts"],
                score_to_par=state.score_to_par,
                context={"commentary": ev.get("text")},
                reasons=["third consecutive birdie"],
            )
        )


def _apply_record_chase_boost(moments: list[Moment], state: _RoundState) -> None:
    """+10 drama (cap 100) for moments on deep-chase, on-pace holes."""
    for m in moments:
        ctx = state.hole_context.get(m.hole, {})
        if ctx.get("on_pace") and ctx.get("score_entering", 0) <= RECORD_CHASE_MIN_SCORE:
            if m.drama < 100:
                m.drama = min(100, m.drama + 10)
                m.reasons.append("record-chase boost: on pace for 59, deep in the round")


def score_round(events: list[dict]) -> list[Moment]:
    """Score every moment in one round's event stream, in drama order.

    Returns moments sorted by drama (desc), then by hole (asc). Moments
    below the replay-save threshold are still returned (with
    ``save_replay == False``) so callers can see what was dropped.
    """
    moments: list[Moment] = []
    state = _RoundState()
    for ev in events:
        etype = ev["type"]
        if etype == "round_start":
            state.round_no = ev["round_no"]
        elif etype == "hole_start":
            state.hole = ev["hole"]
            state.par = ev.get("par", hole_par(ev["hole"]))
            state.score_to_par = ev.get("score_to_par", state.score_to_par)
            state.strokes_vs_target = ev.get("score_vs_target", 99)
            state.on_pace = state.strokes_vs_target <= ON_PACE_THRESHOLD
            state.last_decision = None
            state.hole_context[state.hole] = {
                "on_pace": state.on_pace,
                "score_entering": state.score_to_par,
            }
        elif etype == "shot_decision":
            state.last_decision = ev
        elif etype == "shot_result":
            state.last_shot = ev
            _score_shot(ev, state, moments)
        elif etype == "putt_result":
            _score_putt(ev, state, moments)
        elif etype == "hole_complete":
            _score_hole(ev, state, moments)
        elif etype == "milestone":
            _score_milestone(ev, state, moments)
    _apply_record_chase_boost(moments, state)
    moments.sort(key=lambda m: (-m.drama, m.hole, m.trigger_seq))
    return moments
