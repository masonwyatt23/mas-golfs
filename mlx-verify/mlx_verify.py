"""MLX verification helpers for the Mas Golfs broadcast box.

Stdlib only — no third-party dependencies on the box. The bash wrapper
(verify.sh) owns platform checks, installs, and the server lifecycle;
this module owns everything that must be unit-testable on any machine:
prompt loading, HTTP calls against an OpenAI-compatible server,
timing statistics, <think> leakage detection, audition validation,
and the blind A/B writer.

Server-agnostic by design: it talks to any OpenAI-compatible
``/v1/chat/completions`` endpoint. The default endpoint is the mlx-lm
server from docs/local-models.md (localhost:8080, Qwen3.5-4B-4bit),
but the same checks run unchanged against oMLX or any other
OpenAI-compatible server by passing a different --base-url. Only the
install/start steps in verify.sh are mlx-lm-specific.

Thresholds (sources in README.md):
* Latency: P99 total < 4 s over 20 real prompts (qwen3-family §10).
  P99 > 5 s is the operational alert line (local-models §8).
* <think>: zero tolerance across >= 100 generated lines (qwen3-family §10).
* Soak: swap growth after the model loads must stay under 1 GB for the
  whole 30 minutes (qwen3-family §10; local-models §10 step 8 extends
  this to the 24-hour soak). The box baselines at ~2.6 GB swap with no
  model running, so an absolute zero is unmeasurable; growth from the
  post-load baseline is the leak signal (gate changed Nov 13, 2026,
  under Mason's full delegation).
* Audition: every generated line <= 280 chars, no banned words, no
  number that is not in the event prompt (local-models §10 step 4,
  commentary-prompts §5).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

# --- Models (docs/local-models.md §3.5, commentary/config.yaml) ---------
DEFAULT_MODEL = "mlx-community/Qwen3.5-4B-4bit"
FALLBACK_MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
EMERGENCY_MODEL = "mlx-community/Qwen3-1.7B-4bit"
DEFAULT_BASE_URL = "http://localhost:8080/v1"
TEMPERATURE = 0.7
MAX_TOKENS = 120

# --- Thresholds ----------------------------------------------------------
LATENCY_P99_MAX_S = 4.0
LATENCY_P99_ALERT_S = 5.0
LATENCY_N = 20
THINK_MIN_LINES = 100
AUDITION_MAX_CHARS = 280
AB_N_EVENTS = 50

# Banned words (commentary-prompts.md §5, hard filter).
BANNED_WORDS = [
    "unbelievable", "incredible", "amazing", "spectacular",
    "bet", "wager", "payout", "crypto",
    "simulation", "ai", "algorithm", "model",
]

# <think> leakage: any opening or closing think tag, any case, with
# optional whitespace. Also matches the HTML-escaped form, which a
# server could emit if it escapes its own output.
THINK_RE = re.compile(r"(?:<|&lt;)\s*/?\s*think\s*(?:>|&gt;)", re.IGNORECASE)

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100,
}
_WORD_TO_NUM = {w: n for w, n in _NUMBER_WORDS.items()}
# A hyphen is a minus only when it is NOT part of a compound word:
# "par-5" is the number 5, not negative five (caught 2026-11-13:
# ev12 was flagged [-5] for "par-5"). A real negative ("score -5",
# "-5 under") is preceded by a space or nothing, so it still parses.
_INT_RE = re.compile(r"(?<![A-Za-z])-?\d+")
_WORD_RE = re.compile(r"[a-z]+(?:-[a-z]+)?")

# Numeric context for a bare number word (mirrors
# commentary/normalize.py _WORDS_BEFORE / _UNITS_AFTER). A number word
# only counts as a number when it sits in a numeric phrase: a
# hyphenated compound ("fifty-nine"), after through/hole/putt/number/on
# ("putt number two"), or before a unit ("twelve feet", "two under
# par"). Without that context it is prose, not a stat.
_WORDS_BEFORE = {"through", "hole", "putt", "number", "on"}
_UNITS_AFTER = {
    "yards", "yard", "feet", "foot", "under", "over", "strokes",
    "stroke", "putts", "putt", "holes", "hole", "par", "iron", "irons",
}


# --- System prompts ------------------------------------------------------
# Prefer the single source of truth (commentary/prompts.py). The embedded
# copies below are verbatim from docs/commentary-prompts.md §2 and are
# used only if the import fails (e.g. the pack is copied off the repo).

_EMBEDDED_HOST = """You are the play-by-play host of a golf broadcast, in the manner of Jim
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

_EMBEDDED_COLOR = """You are the color commentator of a golf broadcast, in the manner of Jon
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


def system_prompts() -> dict[str, str]:
    """System prompts, preferring commentary/prompts.py."""
    try:
        repo_root = os.path.join(os.path.dirname(__file__), "..")
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from commentary.prompts import SYSTEM_PROMPTS  # noqa: PLC0415
        return dict(SYSTEM_PROMPTS)
    except Exception:
        return {"host": _EMBEDDED_HOST, "color": _EMBEDDED_COLOR}


# --- Events --------------------------------------------------------------

REQUIRED_EVENT_KEYS = {"id", "event_type", "speaker", "user_prompt"}


def load_events(path: str) -> list[dict]:
    """Load and validate an events file. Raises ValueError on bad input."""
    with open(path, encoding="utf-8") as fh:
        events = json.load(fh)
    if not isinstance(events, list) or not events:
        raise ValueError(f"{path}: expected a non-empty JSON list of events")
    seen: set[str] = set()
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            raise ValueError(f"{path}: event {i} is not an object")
        missing = REQUIRED_EVENT_KEYS - ev.keys()
        if missing:
            raise ValueError(f"{path}: event {i} missing keys {sorted(missing)}")
        if ev["speaker"] not in ("host", "color"):
            raise ValueError(f"{path}: event {ev['id']} has bad speaker {ev['speaker']!r}")
        if not ev["user_prompt"].strip():
            raise ValueError(f"{path}: event {ev['id']} has an empty prompt")
        if ev["id"] in seen:
            raise ValueError(f"{path}: duplicate event id {ev['id']!r}")
        seen.add(ev["id"])
    return events


# --- Statistics ----------------------------------------------------------

def percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted list."""
    if not sorted_values:
        raise ValueError("percentile of empty list")
    rank = max(1, int(-(-pct * len(sorted_values) // 100)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def latency_stats(samples: list[float]) -> dict:
    """Median / mean / P99 / max of latency samples in seconds."""
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "median_s": round(statistics.median(ordered), 3),
        "mean_s": round(statistics.mean(ordered), 3),
        "p99_s": round(percentile(ordered, 99), 3),
        "max_s": round(max(ordered), 3),
    }


# --- <think> and audition validation -------------------------------------

def find_think_leaks(text: str) -> list[str]:
    """All <think>-style tags in text (empty list = clean)."""
    return THINK_RE.findall(text)


def find_banned_words(text: str) -> list[str]:
    """Banned words present in text (word-boundary match, case-insensitive)."""
    lowered = text.lower()
    return [w for w in BANNED_WORDS
            if re.search(rf"\b{re.escape(w)}\b", lowered)]


def _numbers_in(text: str) -> set[int]:
    """Integers in text, as digits or as English words in numeric context.

    Digits always count. A number word counts only in a numeric phrase
    (see _WORDS_BEFORE / _UNITS_AFTER): the prose word "zero" in "zero
    tolerance" or "one" in "the next one" is an idiom, not a stat
    (caught 2026-11-13: ev06 failed on "zero tolerance", which invents
    no number). A hyphenated compound ("fifty-nine") always counts.
    """
    nums = {int(m) for m in _INT_RE.findall(text)}
    lowered = text.lower()
    # Pure word tokens (punctuation stripped, hyphens split) so the
    # before/after context check sees "feet", not "feet." — a trailing
    # period otherwise defeats the unit match (caught 2026-11-13:
    # "fifteen feet." was not counted, so an invented 15 went unflagged).
    tokens = re.findall(r"[a-z]+", lowered)
    for match in _WORD_RE.finditer(lowered):
        word = match.group(0)
        if "-" in word:
            parts = word.split("-")
            if all(p in _WORD_TO_NUM for p in parts):
                nums.add(sum(_WORD_TO_NUM[p] for p in parts))
            continue
        if word not in _WORD_TO_NUM:
            continue
        start = len(re.findall(r"[a-z]+", lowered[:match.start()]))
        before = tokens[start - 1] if start > 0 else ""
        end = start + 1
        after = tokens[end] if end < len(tokens) else ""
        if before in _WORDS_BEFORE or after in _UNITS_AFTER:
            nums.add(_WORD_TO_NUM[word])
    return nums


def find_invented_numbers(line: str, prompt: str) -> list[int]:
    """Numbers in the line that do not appear (digit or word) in the prompt.

    The 280-char line may restate a prompt number in words ("twelve feet"
    for "12 feet"), so both forms count as present. A number the prompt
    never mentions is an invented stat (commentary-prompts rule 2).

    Percentages are not stats — "120%" is an effort idiom ("giving
    120%"), not a distance or a score — so they are stripped from both
    sides before the check (caught 2026-11-13: ev05 failed on
    "shouting 120%", which invents no stat). A bare number in the line
    must still be grounded in a bare number in the prompt: stripping
    both sides means a prompt that only ever said "120%" does not
    ground a line claiming "120 yards".

    The literal "+3" is Mas's handicap, stated in the system prompts
    the model is given ("a +3 left-handed golfer"); the model may
    reference it as "+3" and that is not an invented stat (caught
    2026-11-13: ev03 failed on "+3 lefty"). Only the exact "+3"
    notation is exempt — a bare 3 ("3 under par") is still checked.
    """
    pct_re = re.compile(r"-?\d+\s*%")
    line_nums = _numbers_in(pct_re.sub("", re.sub(r"\+3\b", "", line)))
    prompt_nums = _numbers_in(pct_re.sub("", prompt))
    return sorted(line_nums - prompt_nums)


def validate_line(line: str, prompt: str) -> dict:
    """Audition validation for one generated line. Returns failure reasons."""
    failures = []
    if len(line) > AUDITION_MAX_CHARS:
        failures.append(f"over 280 chars ({len(line)})")
    banned = find_banned_words(line)
    if banned:
        failures.append(f"banned words: {', '.join(banned)}")
    invented = find_invented_numbers(line, prompt)
    if invented:
        failures.append(f"invented numbers: {invented}")
    leaks = find_think_leaks(line)
    if leaks:
        failures.append(f"<think> leakage: {leaks}")
    return {"ok": not failures, "failures": failures, "chars": len(line)}


# --- HTTP client ---------------------------------------------------------

class LLMError(RuntimeError):
    """The server failed to produce a usable completion."""


class ChatClient:
    """OpenAI-compatible /v1/chat/completions client (stdlib urllib).

    ``generate`` streams (``stream=true``) so time-to-first-token is
    measured from the first SSE delta; if the server refuses streaming,
    it falls back to a single non-streaming call (TTFT then equals total).
    """

    def __init__(self, base_url: str, model: str,
                 temperature: float = TEMPERATURE, max_tokens: int = MAX_TOKENS,
                 timeout_seconds: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self._systems = system_prompts()

    def _payload(self, speaker: str, user_prompt: str, stream: bool) -> bytes:
        # chat_template_kwargs enable_thinking=false: Qwen3.5 defaults to
        # thinking mode, and with max_tokens=120 the whole budget is eaten
        # by the reasoning block — content comes back null, finish_reason
        # "length", and the answer never starts (verified on the box
        # 2026-11-13 via probe_raw.py). The design is non-thinking
        # (commentary/config.yaml). The mlx-lm server honors this kwarg —
        # its own --chat-template-args help text gives exactly this example.
        return json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._systems[speaker]},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")

    def _request(self, speaker: str, user_prompt: str, stream: bool):
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=self._payload(speaker, user_prompt, stream),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urllib.request.urlopen(req, timeout=self.timeout_seconds)

    def generate(self, speaker: str, user_prompt: str) -> dict:
        """Generate one line. Returns text, ttft_s, total_s, streamed."""
        started = time.monotonic()
        try:
            with self._request(speaker, user_prompt, stream=True) as resp:
                return self._read_stream(resp, started)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            # Streaming refused or failed mid-flight: one non-streaming try.
            started = time.monotonic()
            try:
                with self._request(speaker, user_prompt, stream=False) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError) as exc:
                raise LLMError(f"{self.model} request failed: {exc}") from exc
            total = time.monotonic() - started
            try:
                text = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMError(f"{self.model} unusable response: {body!r}") from exc
            if text is None:
                # The server can answer 200 with a null content (e.g. the
                # generation was cut short); that is an unusable response,
                # not a string to strip (caught on the box 2026-11-13).
                raise LLMError(f"{self.model} unusable response: {body!r}")
            return {"text": text.strip(), "ttft_s": round(total, 3),
                    "total_s": round(total, 3), "streamed": False}

    def _read_stream(self, resp, started: float) -> dict:
        text_parts: list[str] = []
        ttft: float | None = None
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            try:
                delta = chunk["choices"][0]["delta"].get("content", "")
            except (KeyError, IndexError, TypeError):
                continue
            if delta:
                if ttft is None:
                    ttft = time.monotonic() - started
                text_parts.append(delta)
        total = time.monotonic() - started
        if not text_parts and ttft is None:
            raise LLMError(f"{self.model} streamed an empty completion")
        return {"text": "".join(text_parts).strip(),
                "ttft_s": round(ttft if ttft is not None else total, 3),
                "total_s": round(total, 3), "streamed": True}

    def healthy(self) -> bool:
        """Does /v1/models answer? (Same probe verify.sh uses.)"""
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/models", timeout=5.0
            ) as resp:
                return resp.status == 200
        except Exception:
            return False


# --- Checks --------------------------------------------------------------

def run_latency(client: ChatClient, events: list[dict], n: int = LATENCY_N) -> dict:
    """Generate n real prompts; report TTFT and total-time statistics."""
    chosen = events[:n]
    if len(chosen) < n:
        raise ValueError(f"latency needs {n} events, file has {len(events)}")
    rows = []
    for ev in chosen:
        result = client.generate(ev["speaker"], ev["user_prompt"])
        rows.append({"event_id": ev["id"], "event_type": ev["event_type"],
                     "speaker": ev["speaker"], "ttft_s": result["ttft_s"],
                     "total_s": result["total_s"], "chars": len(result["text"]),
                     "text": result["text"]})
    totals = [r["total_s"] for r in rows]
    ttfts = [r["ttft_s"] for r in rows]
    stats = {"total": latency_stats(totals), "ttft": latency_stats(ttfts)}
    p99 = stats["total"]["p99_s"]
    verdict = "PASS" if p99 < LATENCY_P99_MAX_S else "FAIL"
    return {"check": "latency", "verdict": verdict, "stats": stats,
            "p99_bar_s": LATENCY_P99_MAX_S, "alert_bar_s": LATENCY_P99_ALERT_S,
            "model": client.model, "rows": rows}


def _clean_line_fn():
    """Production normalizer (commentary/normalize.py clean_line), or None.

    The audition judges the line as it would air, not the raw
    generation: production truncates over-long lines at the last
    sentence boundary under 280 chars and drops unreadable ones
    (normalize.py cap_length / apply_hard_filter). Validating the raw
    line would fail lines the broadcast handles correctly.
    """
    try:
        repo_root = os.path.join(os.path.dirname(__file__), "..")
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from commentary.normalize import clean_line  # noqa: PLC0415
        return clean_line
    except Exception:
        return None


def run_audition(client: ChatClient, events: list[dict], n: int = 20) -> dict:
    """Local-models §10 step 4: 20 generated lines, all within the rules.

    Each line is judged after the production normalizer (clean_line):
    a line that truncates to a good first sentence passes; a line the
    normalizer drops, or whose aired portion breaks a rule (invented
    number, banned word, think leak), fails.
    """
    clean_line = _clean_line_fn()
    rows = []
    for ev in events[:n]:
        result = client.generate(ev["speaker"], ev["user_prompt"])
        raw = result["text"]
        # SILENCE is a pass, not a drop: the apex prompt tells the model
        # to return the word SILENCE when the shot is on line, and the
        # production service intercepts it before the normalizer
        # (service.py: llm_returned_silence) to say nothing. The
        # normalizer's fragment rule would drop it, which is the wrong
        # verdict for a line that did exactly what it was asked.
        # "SILENCE." counts too — it also ends silent in production
        # (via the drop path).
        if raw.strip().upper().rstrip(".") == "SILENCE":
            rows.append({"event_id": ev["id"], "event_type": ev["event_type"],
                         "speaker": ev["speaker"], "text": raw,
                         "aired": "SILENCE", "ok": True, "failures": [],
                         "chars": len(raw)})
            continue
        aired = clean_line(raw) if clean_line is not None else raw
        if aired is None:
            check = {"ok": False,
                     "failures": ["dropped by normalizer (unreadable after "
                                  "filter / no sentence boundary under 280)"],
                     "chars": len(raw)}
        else:
            check = validate_line(aired, ev["user_prompt"])
        rows.append({"event_id": ev["id"], "event_type": ev["event_type"],
                     "speaker": ev["speaker"], "text": raw, "aired": aired,
                     **check})
    failed = [r for r in rows if not r["ok"]]
    verdict = "PASS" if not failed else "FAIL"
    return {"check": "audition", "verdict": verdict,
            "n": len(rows), "failed": len(failed),
            "model": client.model, "rows": rows}


def run_ab(client_a: ChatClient, client_b: ChatClient,
           events: list[dict], n: int = AB_N_EVENTS,
           seed: int | None = None) -> tuple[dict, dict]:
    """Blind A/B: same events through both models, labels randomized.

    Returns (results, key). The key maps "A"/"B" to model names and must
    be kept sealed (ab-key.json) until the human judge scores the
    side-by-side file. One coin flip for the whole file, not per event —
    the judge compares two consistent voices, not a shuffled deck.
    """
    chosen = events[:n]
    if len(chosen) < n:
        raise ValueError(f"A/B needs {n} events, file has {len(events)}")
    rng = random.Random(seed)
    flipped = rng.random() < 0.5
    label_for = {client_a.model: "B" if flipped else "A",
                 client_b.model: "A" if flipped else "B"}
    rows = []
    for ev in chosen:
        out = {}
        for client in (client_a, client_b):
            result = client.generate(ev["speaker"], ev["user_prompt"])
            out[label_for[client.model]] = {
                "text": result["text"], "total_s": result["total_s"],
                "chars": len(result["text"]),
            }
        rows.append({"event_id": ev["id"], "event_type": ev["event_type"],
                     "speaker": ev["speaker"], "user_prompt": ev["user_prompt"],
                     "A": out["A"], "B": out["B"]})
    key = {"A": client_b.model if flipped else client_a.model,
           "B": client_a.model if flipped else client_b.model,
           "flipped": flipped, "n": len(rows)}
    results = {"check": "ab", "model_a": client_a.model,
               "model_b": client_b.model, "n": len(rows), "rows": rows}
    return results, key


def write_ab_side_by_side(results: dict, path: str) -> None:
    """Human-readable A/B file. No model names anywhere in it."""
    lines = ["# Mas Golfs — blind A/B: commentary lines\n",
             "Two voices, labelled **A** and **B**. The key mapping labels to",
             "models is sealed in `ab-key.json` — do not open it until you",
             "have scored every event. Judge each pair on the booth test",
             "(commentary-prompts.md §11): can you tell the score, the hole,",
             "and what Mas is trying to do — from the line alone? Nothing",
             "wrong about the numbers, no hype, nothing robotic.\n",
             "Score each event: A wins / B wins / tie. Tally at the end.\n"]
    for row in results["rows"]:
        lines.append(f"## {row['event_id']} — {row['event_type']} ({row['speaker']})\n")
        lines.append(f"> {row['user_prompt']}\n")
        lines.append(f"**A** ({row['A']['chars']} chars, {row['A']['total_s']}s): "
                     f"{row['A']['text']}\n")
        lines.append(f"**B** ({row['B']['chars']} chars, {row['B']['total_s']}s): "
                     f"{row['B']['text']}\n")
        lines.append("Winner: _____\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# --- Soak sampling (macOS only at runtime) -------------------------------

def parse_swapusage(output: str) -> float:
    """Parse `sysctl vm.swapusage` output; return MB currently swapped.

    Sample input: "vm.swapusage: total = 64.00M  used =  0.00M  free = 64.00M
    (encrypted)". Raises ValueError on unparseable input.
    """
    match = re.search(r"used\s*=\s*([\d.]+)\s*([KMG])", output)
    if not match:
        raise ValueError(f"cannot parse vm.swapusage output: {output!r}")
    value, unit = float(match.group(1)), match.group(2)
    return value * {"K": 1 / 1024, "M": 1, "G": 1024}[unit]


def parse_ps_rss(output: str) -> int:
    """Parse `ps -o rss= -p <pid>` output; return resident KB."""
    return int(output.strip().split()[0])


# --- Soak ----------------------------------------------------------------

def default_sampler(server_pid: int | None) -> tuple[float, int | None]:
    """One soak sample: (swap used MB, server RSS KB or None).

    macOS only at runtime (sysctl vm.swapusage, ps). Raises on failure so
    a broken sample fails loudly instead of silently recording zeros.
    """
    import subprocess  # noqa: PLC0415
    out = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True,
                         text=True, check=True).stdout
    swap_mb = parse_swapusage(out)
    rss_kb: int | None = None
    if server_pid:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(server_pid)],
                             capture_output=True, text=True, check=True).stdout
        rss_kb = parse_ps_rss(out)
    return swap_mb, rss_kb


def soak_verdict(samples: list[dict]) -> dict:
    """Verdict from soak samples.

    The gate is swap GROWTH, not absolute swap. The box baselines at
    ~2.6 GB swap with no model running (measured Nov 13, 2026), so an
    absolute "swap stays at 0 MB" is unmeasurable on this machine. The
    first sample is taken with the model already loaded, so it is the
    post-load baseline; growth above it is the leak signal. FAIL if
    growth (max - first) exceeds 1 GB, if the server died, or if any
    warm-up generation failed. The 1 GB threshold is set from the two
    5-minute runs (observed growth 331-499 MB); the 30-minute soak
    validates it — if growth approaches 1 GB, investigate before
    trusting a longer soak.
    """
    if not samples:
        return {"verdict": "INCOMPLETE", "reason": "no samples recorded"}
    baseline = samples[0]["swap_used_mb"]
    max_swap = max(s["swap_used_mb"] for s in samples)
    growth = max_swap - baseline
    server_dead = any(s.get("server_rss_kb") is None for s in samples)
    failed_gens = sum(1 for s in samples if s.get("warmup_ok") is False)
    fields = {"baseline_mb": round(baseline, 2),
              "growth_mb": round(growth, 2),
              "max_swap_mb": max_swap}
    if growth > 1000:
        return {"verdict": "FAIL",
                "reason": f"swap grew {growth:.0f} MB after load (>1000 MB)",
                **fields}
    if server_dead:
        return {"verdict": "FAIL", "reason": "MLX server process disappeared",
                **fields}
    if failed_gens:
        return {"verdict": "FAIL",
                "reason": f"{failed_gens} warm-up generations failed",
                **fields}
    return {"verdict": "PASS",
            "reason": "swap growth stayed under 1 GB for the whole soak",
            **fields}


def run_soak(client: ChatClient, events: list[dict],
             server_pid: int | None, minutes: float,
             sample_interval_s: float = 60.0, warmup_every_s: float = 90.0,
             out_path: str | None = None,
             sampler=None) -> dict:
    """Sample swap + server RSS for `minutes`, warming the model on schedule.

    `sampler` is injectable for tests; default is default_sampler.
    Writes one JSON object per sample to out_path (if given) plus a
    summary dict. Returns the summary.
    """
    sampler = sampler or (lambda: default_sampler(server_pid))
    samples: list[dict] = []
    start = time.monotonic()
    end = start + minutes * 60
    next_warmup = start
    warmup_i = 0
    fh = open(out_path, "w", encoding="utf-8") if out_path else None
    try:
        while True:
            now = time.monotonic()
            if now >= end and samples:
                break
            swap_mb, rss_kb = sampler()
            sample: dict = {"t_s": round(now - start, 1),
                            "swap_used_mb": swap_mb,
                            "server_rss_kb": rss_kb}
            if now >= next_warmup:
                try:
                    ev = events[warmup_i % len(events)]
                    result = client.generate(ev["speaker"], ev["user_prompt"])
                    sample["warmup_ok"] = True
                    sample["warmup_event"] = ev["id"]
                    sample["warmup_total_s"] = result["total_s"]
                except Exception as exc:  # noqa: BLE001 - a failed warm-up is data
                    sample["warmup_ok"] = False
                    sample["warmup_error"] = str(exc)[:200]
                warmup_i += 1
                next_warmup = now + warmup_every_s
            samples.append(sample)
            if fh:
                fh.write(json.dumps(sample) + "\n")
                fh.flush()
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(sample_interval_s, remaining))
    finally:
        if fh:
            fh.close()
    verdict = soak_verdict(samples)
    summary = {"check": "soak", "minutes": minutes,
               "samples": len(samples),
               "max_swap_mb": max(s["swap_used_mb"] for s in samples) if samples else None,
               "max_server_rss_kb": max((s["server_rss_kb"] for s in samples
                                         if s.get("server_rss_kb") is not None),
                                        default=None),
               **verdict}
    return summary


def _extract_texts(obj, out: list[str]) -> None:
    """Recursively collect every \"text\" string from parsed JSON."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "text" and isinstance(value, str):
                out.append(value)
            else:
                _extract_texts(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _extract_texts(item, out)


def scan_think(paths: list[str]) -> dict:
    """Scan files for <think> leakage.

    .json files are parsed and every \"text\" value is scanned (one
    generated line each); other files are scanned one line per line.
    Returns the verdict dict used by the CLI.
    """
    total_lines = 0
    hits: list[dict] = []
    for path in paths:
        if path.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                texts: list[str] = []
                _extract_texts(json.load(fh), texts)
            for i, text in enumerate(texts):
                total_lines += 1
                found = find_think_leaks(text)
                if found:
                    hits.append({"file": path, "line": i + 1,
                                 "leaks": found, "text": text[:200]})
        else:
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    total_lines += 1
                    found = find_think_leaks(line)
                    if found:
                        hits.append({"file": path, "line": lineno,
                                     "leaks": found, "text": line.strip()[:200]})
    verdict = "PASS" if not hits else "FAIL"
    if total_lines < THINK_MIN_LINES:
        verdict = "INCOMPLETE"
    return {"check": "think", "verdict": verdict,
            "lines_scanned": total_lines, "min_lines": THINK_MIN_LINES,
            "hits": hits}


# --- Platform gate -------------------------------------------------------

def platform_gate(uname_s: str | None = None, uname_m: str | None = None) -> dict:
    """Is this the Apple Silicon Mac the MLX plan needs?

    Returns {"ok": bool, "reason": str}. Pure function so the tests can
    drive it with fake uname values; the real values come from
    platform.uname() in main().
    """
    import platform  # noqa: PLC0415
    system = uname_s if uname_s is not None else platform.uname().system
    machine = uname_m if uname_m is not None else platform.uname().machine
    if system != "Darwin":
        return {"ok": False,
                "reason": f"MLX runs on macOS only; this is {system}. "
                          "Run this pack on the 8GB MacBook Pro."}
    if machine != "arm64":
        return {"ok": False,
                "reason": f"MLX needs Apple Silicon (arm64); this is {machine}. "
                          "An Intel Mac cannot run MLX — use the llama.cpp "
                          "fallback in docs/local-models.md instead."}
    return {"ok": True, "reason": f"Darwin {machine} — Apple Silicon, MLX can run."}


# --- CLI -----------------------------------------------------------------

def _events_arg(args) -> list[dict]:
    return load_events(args.events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MLX verification helpers (see verify.sh for the full pack).")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--events", default=os.path.join(
        os.path.dirname(__file__), "events.json"))
    parser.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(__file__), "results"))
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="per-request timeout in seconds (the first "
                             "generation after a fresh model load is slow — "
                             "Metal kernel compile + prefill — so the smoke "
                             "step passes a much longer one)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("gate", help="Apple Silicon platform check")
    p = sub.add_parser("latency", help="20 real prompts, P99 < 4s")
    p.add_argument("--n", type=int, default=LATENCY_N)
    p = sub.add_parser("audition", help="20 lines within the §10 step-4 rules")
    p.add_argument("--n", type=int, default=20)
    p = sub.add_parser("think", help="grep result files for <think> leakage")
    p.add_argument("files", nargs="+")
    p = sub.add_parser("soak", help="sample swap + server RSS for N minutes")
    p.add_argument("--minutes", type=float, default=30.0)
    p.add_argument("--server-pid", type=int, default=None)
    p.add_argument("--interval", type=float, default=60.0)
    p.add_argument("--warmup-every", type=float, default=90.0)
    p = sub.add_parser("ab", help="blind A/B over 50 events, two models")
    p.add_argument("--model-b", default=FALLBACK_MODEL)
    p.add_argument("--base-url-b", default=None)
    p.add_argument("--n", type=int, default=AB_N_EVENTS)
    p.add_argument("--seed", type=int, default=None)

    args = parser.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)

    if args.command == "gate":
        gate = platform_gate()
        print(f"{'OK' if gate['ok'] else 'FAIL'}: {gate['reason']}")
        return 0 if gate["ok"] else 2

    if args.command == "think":
        result = scan_think(args.files)
        print(json.dumps(result, indent=2))
        verdict = result["verdict"]
        return 0 if verdict == "PASS" else (3 if verdict == "INCOMPLETE" else 1)

    events = _events_arg(args)
    client = ChatClient(args.base_url, args.model,
                        timeout_seconds=args.timeout)
    if not client.healthy():
        print(f"FAIL: no OpenAI-compatible server answering at {args.base_url}",
              file=sys.stderr)
        return 1

    if args.command == "soak":
        summary = run_soak(client, events, args.server_pid, args.minutes,
                           sample_interval_s=args.interval,
                           warmup_every_s=args.warmup_every,
                           out_path=os.path.join(args.out_dir, "soak.jsonl"))
        path = os.path.join(args.out_dir, "soak-summary.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"{summary['verdict']}: {summary['reason']} "
              f"({summary['samples']} samples, max swap "
              f"{summary['max_swap_mb']} MB) -> {path}")
        return 0 if summary["verdict"] == "PASS" else 1

    if args.command == "latency":
        result = run_latency(client, events, args.n)
        path = os.path.join(args.out_dir, "latency.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"{result['verdict']}: P99 total {result['stats']['total']['p99_s']}s "
              f"(bar {LATENCY_P99_MAX_S}s), median total "
              f"{result['stats']['total']['median_s']}s, "
              f"median TTFT {result['stats']['ttft']['median_s']}s "
              f"-> {path}")
        return 0 if result["verdict"] == "PASS" else 1

    if args.command == "audition":
        result = run_audition(client, events, args.n)
        path = os.path.join(args.out_dir, "audition.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"{result['verdict']}: {result['n'] - result['failed']}/{result['n']} lines "
              f"within the rules -> {path}")
        if result["failed"]:
            for row in result["rows"]:
                if not row["ok"]:
                    print(f"  {row['event_id']}: {row['failures']}")
        return 0 if result["verdict"] == "PASS" else 1

    if args.command == "ab":
        client_b = ChatClient(args.base_url_b or args.base_url, args.model_b)
        if not client_b.healthy():
            print(f"FAIL: second server not answering at {client_b.base_url}",
                  file=sys.stderr)
            return 1
        results, key = run_ab(client, client_b, events, args.n, args.seed)
        json_path = os.path.join(args.out_dir, "ab-results.json")
        md_path = os.path.join(args.out_dir, "ab-side-by-side.md")
        key_path = os.path.join(args.out_dir, "ab-key.json")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, ensure_ascii=False)
        write_ab_side_by_side(results, md_path)
        with open(key_path, "w", encoding="utf-8") as fh:
            json.dump(key, fh, indent=2)
        print(f"A/B complete: {results['n']} events -> {md_path}")
        print(f"Key sealed in {key_path} — do not open it until scoring is done.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
