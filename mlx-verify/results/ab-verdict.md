# A/B verdict — Qwen3.5-4B vs Qwen3-4B-Instruct-2507 (Nov 13, 2026)

Blind-scored by Muse (the assistant) under Mason's full delegation, using the
booth test (docs/commentary-prompts.md §11): can you tell the score, the hole,
and what Mas is trying to do from the line alone; nothing wrong about the
numbers; no hype; nothing robotic. Scored blind, then the key was opened.

- **A = `mlx-community/Qwen3.5-4B-4bit`** (current default)
- **B = `mlx-community/Qwen3-4B-Instruct-2507-4bit`** (challenger)
- Key: `flipped: false`, n = 50. Source files on the box:
  `~/mas-golfs/mlx-verify/results/ab-side-by-side.md`,
  `~/mas-golfs/mlx-verify/results/ab-key.json`.

## Tally

| | Wins |
|---|---|
| **A (Qwen3.5-4B)** | **27** |
| B (Qwen3-4B-Instruct-2507) | 16 |
| Ties | 7 |

## Decision: keep Qwen3.5-4B-4bit. The challenger is rejected.

Latency gives no reason to switch (medians identical: A 1.675 s, B 1.657 s;
B's p99 of 10.26 s is a single cold-start outlier on the first generation).
Quality decides it, and A wins on the two things that matter most for the
booth: staying grounded in the event data, and staying silent at apex.

## Why B loses

- **Speaks at apex (3 of 4 apex events).** A stays silent (correct); B
  narrates the ball flight at ev07, ev09, ev10 — including ev10, where it
  speaks and then appends a stray literal "SILENCE." Apex is a no-talk
  moment; the challenger does not respect it.
- **Invents stats.** ev11 "two feet from the pin" (event: 12 feet), ev17
  wrong score (1 under, event: 2 under), ev23 "5-under par on the 7th"
  (event: even par), ev31 "tied for the tournament lead" (no tournament
  data in the event).
- **Claims putts were made before they happen.** ev15, ev44, ev45 — the
  event is a landing/recovery with the putt still to come; B reports the
  putt as made.
- **"Mason Mas" (ev46, ev47).** Doubles the name; A uses "Mas".
- **Leaks a field name (ev34).** B prints the literal token "on_the_line"
  in the aired line.

## What A does well — and its own weaknesses

A stays grounded (it names the club, distance, wind, and score from the
event) and is silent at apex in all four apex events. Its putt_result lines
are the weakest spot: ev18 and ev20 say the ball "finds the green" on a
putt, which is muddled (the ball is already on the green). Its 59 Watch
math is also wrong in the same way B's is (see below).

## Open issue: 59 Watch math is wrong in BOTH models

ev34, ev35, ev36 — both models misstate the 59 pace (e.g. "one stroke away
from a 59" when 5 under in 6 holes is needed; "a par to finish at 59"
when par finishes at 60). The models cannot reliably compute the 59 pace
from the event fields. Fix: the 59 Watch prompt should state the required
score explicitly (e.g. "needs a birdie on the 18th to finish at 59")
instead of asking the model to derive it. That is a prompt fix, not a
model-selection fix, and it applies to the winner too.
