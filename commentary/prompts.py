"""Prompt templates for the commentary pipeline.

System prompts are verbatim from docs/commentary-prompts.md §2.
User-prompt templates are §4, with the doc's ``{{placeholder}}`` syntax
converted to Python ``{placeholder}`` format fields. The fields are
filled from the sim event JSON and the ``round_state`` snapshot — never
from anywhere else (commentary-prompts.md rule 2: never invent a stat).
"""

from __future__ import annotations

HOST_SYSTEM_PROMPT = """You are the play-by-play host of a golf broadcast, in the manner of Jim
Nantz: warm, poetic, unhurried. "Hello, friends" energy — the Masters Sunday
cadence, storytelling over statistics, letting the moment breathe. You
describe Mas, a +3 left-handed golfer, Mason's digital twin, playing Wyatt
National. Your job is the facts, told with warmth: what happened, and the
numbers, and why the moment matters. One or two sentences maximum, 280
characters maximum. Never shout, never use the words "unbelievable",
"incredible", "amazing", or "spectacular". Never invent a fact not present
in the event data you are given. Never mention the simulation, the engine,
the model, or how the broadcast is produced. State the result plainly and
let it speak — and when the moment deserves it, let silence do the work."""

COLOR_SYSTEM_PROMPT = """You are the color commentator of a golf broadcast, in the manner of Jon
Gruden: the coach in the booth, chalk-talk energy, genuine enthusiasm for
great execution. You describe Mas, a +3 left-handed golfer, Mason's digital
twin, playing Wyatt National. Your job is the why: break down the decision
like a play call — the club, the wind, the lie, the target, the risk — and
teach the viewer why the choice is smart or brave. "I love this" energy when
the execution earns it, never forced. One or two sentences maximum, 280
characters maximum. Explain the thinking in plain language a weekend golfer
understands and say what the shot asks of him. Never invent a fact not
present in the event data you are given. Never mention the simulation, the
engine, the model, or how the broadcast is produced. If the event gives
you a reason for the decision, use it; if it does not, describe only what
can be seen."""

# User-prompt templates, keyed by (event type, speaker).
# A missing field is rendered as "—" rather than crashing the pipeline;
# a template that cannot be filled from the event is never silently
# invented around.
TEMPLATES: dict[tuple[str, str], str] = {
    ("decision", "color"): (
        "Mas is on hole {hole} (par {par}), {score_to_par} through {thru}.\n"
        "He has chosen {club}, {shot_type}, target {target_yards} yards,\n"
        "aiming {aim}. Lie: {lie}. Wind: {wind_mph} mph {wind_dir}.\n"
        "The reason for this choice is: {reason}. Risk level: {risk}.\n"
        "Explain the decision in one or two sentences: what he is trying to do,\n"
        "and what the shot asks of him."
    ),
    ("apex", "color"): (
        "The {club} is at its apex, {apex_ft} feet high, carrying\n"
        "{carry_yds} yards, shape {shape}, curving {curve_yds} yards.\n"
        "Read the flight in one short sentence. If it is straight and on line,\n"
        "say nothing — return the word SILENCE."
    ),
    ("landing", "host"): (
        "The {club} finished {total_yds} yards, in the {lie},\n"
        "{dist_to_pin_ft} feet from the pin. Result: {result}.\n"
        "Mas is {score_to_par} through {thru}. State the result in one or\n"
        "two sentences: where it finished and what it leaves him."
    ),
    ("putt_result", "host"): (
        "Putt from {dist_ft} feet: {made_word}.\n"
        "That is putt number {putts_this_hole} on this hole. Mas is\n"
        "{score_to_par} through {thru}. Call the result in one short\n"
        "sentence. If it was made, name the score it gives him. If it was\n"
        "missed, say only what is left."
    ),
    ("hole_end", "host"): (
        "Hole {hole}, {hole_name}, finished in {score} strokes.\n"
        "Fairway: {fairway_hit}. Green in regulation: {gir}.\n"
        "Putts: {putts}. Up and down: {up_and_down}. Mas is\n"
        "{score_to_par} through {hole}. Give the hole summary in one or\n"
        "two sentences, with the score first."
    ),
    ("hole_end", "color"): (
        "The story of this hole: {strokes_gained_summary}. Say in one\n"
        "sentence what this hole means for the round — a streak, a save, a\n"
        "missed chance. If nothing changed, return the word SILENCE."
    ),
    ("round_end", "host"): (
        "Round complete. Mas shot {score}, {score_to_par}.\n"
        "Fairways {fairways}, greens {gir},\n"
        "putts {putts}, up and downs {up_and_downs}.\n"
        "New handicap {new_handicap}. All-time rank {rank}.\n"
        "Summarize the round in one or two sentences."
    ),
    ("round_end", "color"): (
        "The one thing to work on from this round: {leak},\n"
        "costing {strokes_lost} strokes. The adjustment is:\n"
        "{adjustment}. Explain it in one or two sentences in\n"
        "plain language, as the single takeaway from the round. Never add a\n"
        "second fix."
    ),
    ("milestone", "host"): (
        "Milestone: {type}. Detail: {detail}. Mas is {score_to_par}\n"
        "through {thru}. State the milestone in one sentence, plainly."
    ),
    ("milestone", "color"): (
        "Milestone: {type}. Detail: {detail}. Say in one sentence what\n"
        "this means for the round or the season. If it is a record pace, name\n"
        "the record it is chasing, using only the numbers in the detail."
    ),
    ("fifty_nine_watch", "host"): (
        "59 Watch, status {status}. Mas is {score_to_par} through {thru},\n"
        "with {holes_left} holes left. He can afford to drop {strokes_remaining}\n"
        "more strokes and still break 60. Live probability {probability}%.\n"
        "State the 59 Watch position in one or two sentences. He needs {needs} —\n"
        "state that requirement exactly as given, do not derive it yourself."
    ),
    ("fifty_nine_watch", "color"): (
        "59 Watch, status {status}. {holes_left} holes left, and he can\n"
        "afford {strokes_remaining} more dropped strokes. Say in one sentence\n"
        "what the remaining holes ask of him. Keep it calm — the moment is\n"
        "already loud enough."
    ),
    ("bad_miss", "host"): (
        "The {club} finished in the {lie}, {dist_to_pin_ft} feet from\n"
        "the pin. Result: {result}. State where it finished and what it\n"
        "leaves him, in one short sentence. No diagnosis, no judgment."
    ),
    ("recovery", "color"): (
        "Mas is in the {lie} and has chosen {club}, {shot_type},\n"
        "target {target_yards} yards. The reason: {reason}. Explain in\n"
        "one sentence what a good recovery looks like from here."
    ),
    ("recovery", "host"): (
        "The recovery finished {dist_to_pin_ft} feet from the pin.\n"
        "State the result in one short sentence. If it saved par, say so."
    ),
    ("round_start", "host"): (
        "Round {round} at {course}. Par {par}. Target score {target_score}.\n"
        "Handicap {handicap}. Last ten rounds averaged {last10_avg}.\n"
        "Open the round in one or two sentences: where he is, and what he is chasing."
    ),
    ("hole_start", "host"): (
        "Hole {hole}, {hole_name}. Par {par}, {yards} yards, {pin}.\n"
        "Wind: {wind_mph} mph {wind_dir}. Elevation: {elevation_ft} feet.\n"
        "Introduce the hole in one sentence: the name, the distance, and the question it asks."
    ),
}

SYSTEM_PROMPTS = {"host": HOST_SYSTEM_PROMPT, "color": COLOR_SYSTEM_PROMPT}


def render_user_prompt(event_type: str, speaker: str, fields: dict) -> str:
    """Render a user-prompt template with event fields.

    Unknown fields are left as-is by ``str.format_map`` via a defaulting
    dict, so a missing field renders as "—" instead of raising.
    """
    template = TEMPLATES[(event_type, speaker)]

    class _Missing(dict):
        def __missing__(self, key):
            return "—"

    return template.format_map(_Missing(fields))
