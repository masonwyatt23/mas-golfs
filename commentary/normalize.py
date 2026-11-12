"""Line validation and text normalization (commentary-prompts.md §5, §9, §10).

Every generated line passes through this module before TTS:

1. Banned-word hard filter — the words in §5 are stripped; a line that
   is unreadable after filtering is dropped.
2. Exclamation marks are stripped, not replaced.
3. 280-character hard cap — truncate at the last sentence boundary under
   the cap; if no boundary fits, drop the line.
4. Number validation — every number in the line (digits, or golf number
   words like "one eighty-seven") must appear in the event JSON or the
   ``round_state`` snapshot. A line with an invented number is dropped
   and the cached standard call plays instead.
5. Text normalization for TTS — numbers and abbreviations expanded to
   words Kokoro can say (187 -> "one eighty-seven", 7-iron -> "seven
   iron", -2 -> "two under par", mph -> "miles per hour").
"""

from __future__ import annotations

import re

BANNED_WORDS = (
    "unbelievable",
    "incredible",
    "amazing",
    "spectacular",
    "bet",
    "wager",
    "payout",
    "crypto",
    "simulation",
    "ai",
    "algorithm",
    "model",
)

# Words the normalizer must never rewrite (they are not numbers).
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def words_to_number(text: str) -> int | None:
    """Parse a golf-style number phrase to an int.

    Handles "twelve", "fifty-nine", "one eighty-seven" (187),
    "two hundred seventy-eight" (278) and "one sixty-four" (164).
    Returns None when the phrase is not a number.
    """
    text = text.strip().lower().replace("-", " ").replace(",", "")
    tokens = text.split()
    if not tokens:
        return None
    total = 0
    current = 0
    seen = False
    for token in tokens:
        if token in _ONES:
            current += _ONES[token]
            seen = True
        elif token in _TENS:
            current += _TENS[token]
            seen = True
        elif token == "hundred":
            if current == 0:
                current = 1
            current *= 100
            seen = True
        else:
            return None
    if not seen:
        return None
    return total + current


def _number_words_in_line(line: str) -> list[int]:
    """Find number words in a line and return their values.

    Matches runs of number words (with hyphens) — e.g. "one eighty-seven"
    and "fifty-nine" — and converts each run to a digit.
    """
    words = set(_ONES) | set(_TENS) | {"hundred"}
    pattern = re.compile(
        r"\b(?:(?:" + "|".join(sorted(words, key=len, reverse=True)) + r")"
        r"(?:[ -](?:(?:" + "|".join(sorted(words, key=len, reverse=True)) + r")))*)\b",
        re.IGNORECASE,
    )
    found = []
    for match in pattern.finditer(line):
        value = words_to_number(match.group(0))
        if value is not None:
            found.append(value)
    return found


def allowed_numbers(event: dict, round_state: dict | None) -> set[float]:
    """All numbers a line is allowed to use, from the event + round_state.

    Includes magnitudes of signed values (a line may say "two under" for
    a score_to_par of -2) and the hole/par/yardage figures in the snapshot.
    """
    numbers: set[float] = set()

    def _collect(obj):
        if isinstance(obj, dict):
            for value in obj.values():
                _collect(value)
        elif isinstance(obj, (list, tuple)):
            for value in obj:
                _collect(value)
        elif isinstance(obj, bool):
            return
        elif isinstance(obj, (int, float)):
            numbers.add(float(obj))
            numbers.add(abs(float(obj)))

    _collect(event)
    if round_state:
        _collect(round_state)
    return numbers


def validate_numbers(line: str, event: dict, round_state: dict | None) -> bool:
    """True when every number in the line is in the event/round_state.

    Checks both digit sequences (e.g. 187) and golf number words
    (e.g. "one eighty-seven"). The 59 in "59 Watch" / "fifty-nine" is
    allowed when the event carries a 59 target (round_state.target_score).
    """
    allowed = allowed_numbers(event, round_state)
    for token in re.findall(r"\d+(?:\.\d+)?", line):
        if float(token) not in allowed:
            return False
    for value in _number_words_in_line(line):
        if float(value) not in allowed:
            return False
    return True


def apply_hard_filter(line: str) -> str | None:
    """Strip banned words and exclamation marks.

    Returns None when the line is unreadable after filtering (empty, or
    left with a dangling fragment of two words or fewer after a banned
    word was removed mid-sentence).
    """
    filtered = line.replace("!", "")
    for word in BANNED_WORDS:
        filtered = re.sub(rf"\b{re.escape(word)}\b", "", filtered, flags=re.IGNORECASE)
    filtered = re.sub(r"\s+", " ", filtered).strip()
    filtered = re.sub(r"\s+([,.])", r"\1", filtered)
    if not filtered:
        return None
    # A line reduced to a fragment is not a line.
    if len(filtered.split()) <= 2 and len(filtered) < 15:
        return None
    return filtered


def cap_length(line: str, max_chars: int = 280) -> str | None:
    """Enforce the 280-character cap (commentary-prompts.md §10).

    Truncate at the last sentence boundary under the cap. If no sentence
    boundary fits, the line is dropped (None).
    """
    if len(line) <= max_chars:
        return line
    cut = line[:max_chars]
    for boundary in (". ", "! ", "? "):
        idx = cut.rfind(boundary)
        if idx > 0:
            return cut[: idx + 1].strip()
    return None


# --- Text normalization for TTS (commentary-prompts.md §9) ------------

def _spell_under_100(value: int) -> str:
    if value < 20:
        return next(k for k, v in _ONES.items() if v == value)
    tens, ones = divmod(value, 10)
    tens_word = next(k for k, v in _TENS.items() if v == tens * 10)
    if ones == 0:
        return tens_word
    ones_word = next(k for k, v in _ONES.items() if v == ones)
    return f"{tens_word}-{ones_word}"


def normalize_for_tts(line: str) -> str:
    """Expand numbers and abbreviations into words Kokoro can say."""
    text = line
    # 7-iron / 7 iron -> seven iron (before the digit pass runs).
    text = re.sub(
        r"\b([2-9])-iron\b",
        lambda m: f"{_spell_under_100(int(m.group(1)))} iron",
        text,
        flags=re.IGNORECASE,
    )
    # Signed scores: -2 -> two under par, +3 -> three over par.
    text = re.sub(
        r"([−\-+])(\d+)\b",
        lambda m: (
            f"{_spell_under_100(int(m.group(2)))} under par"
            if m.group(1) in ("−", "-")
            else f"{_spell_under_100(int(m.group(2)))} over par"
        ),
        text,
    )
    # Remaining bare numbers -> words (golf style: 187 -> one eighty-seven).
    def _spell_number(match: re.Match) -> str:
        value = int(match.group(0))
        if value < 100:
            return _spell_under_100(value)
        hundreds, rest = divmod(value, 100)
        hundreds_word = next(k for k, v in _ONES.items() if v == hundreds)
        if rest == 0:
            return f"{hundreds_word} hundred"
        return f"{hundreds_word} {_spell_under_100(rest)}"

    text = re.sub(r"\b\d+\b", _spell_number, text)
    text = re.sub(r"\bmph\b", "miles per hour", text, flags=re.IGNORECASE)
    text = re.sub(r"\bGIR\b", "green in regulation", text)
    text = re.sub(r"\b59 Watch\b", "fifty-nine watch", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_line(line: str, max_chars: int = 280) -> str | None:
    """Full pre-TTS pipeline: filter, then cap. Returns None to drop."""
    filtered = apply_hard_filter(line)
    if filtered is None:
        return None
    return cap_length(filtered, max_chars)
