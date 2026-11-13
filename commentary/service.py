"""Commentary service — the orchestrator (docs/broadcast-stack.md §5).

Event flow, per event:

    sim event (bus)
      -> normalize envelope, update round_state snapshot
      -> decide: is a line due? (event-only, director hold, rate limits)
      -> cached standard line first (commentary-prompts.md §6.1)
      -> else LLM generation (MLX, Ollama fallback), validated
      -> text normalization -> TTS (Kokoro, cached audio)
      -> emit text + audio to the broadcast pipeline (output log + files)
      -> log every decision to the JSONL decision log

Hard rules enforced here, not just in the prompts
(commentary-prompts.md §5):

* Never speak over a swing — a line queued when ``shot_start`` arrives
  is held until ``landing`` (director hold).
* Max 1 line / 15 s, max 4 lines / hole. When events arrive faster,
  the lowest-priority line is dropped: result > 59 Watch > color >
  apex read.
* 59 Watch lines are generated fresh every time — never cached.
* Silence is a valid output. Roughly half the round should be silence;
  the service tracks the spoken fraction and logs when it exceeds 50%.
* No paid API, ever. The fallback hierarchy is: fresh generation ->
  cached line -> silence.
"""

from __future__ import annotations

import datetime
import json
import os
import time

from . import normalize as norm
from .bus import FakeBus, WebSocketBus, connect_with_backoff, normalize_event
from .cache import NEVER_CACHE, AudioCache, standard_line
from .config import expand_paths, load_config
from .llm import LLMClient, build_llm_client
from .prompts import render_user_prompt
from .tts import build_tts

# Priority order (commentary-prompts.md §10): result > 59 Watch > color > apex.
PRIORITY_RESULT = 4
PRIORITY_59_WATCH = 3
PRIORITY_COLOR = 2
PRIORITY_APEX = 1

MISS_RESULTS = {"missed_left", "missed_right", "short", "long", "in_water", "in_trees"}
RECOVERY_SHOTS = {"punch", "flop", "chip"}
# Apex flight reads are only worth naming when the ball is working
# (draw/fade with real curve) or clearly offline.
APEX_MIN_CURVE_YDS = 5
APEX_MIN_OFFLINE_CURVE_YDS = 10

# Estimated speaking rate for the silence budget (150 words/minute).
WORDS_PER_SECOND = 2.5


def format_score(score_to_par) -> str:
    """Format a score-to-par number the way the prompts expect it."""
    if score_to_par is None:
        return "—"
    score_to_par = int(score_to_par)
    if score_to_par == 0:
        return "E"
    sign = "+" if score_to_par > 0 else "−"
    return f"{sign}{abs(score_to_par)}"


class LineRequest:
    """A candidate commentary line, before generation/validation."""

    def __init__(self, event_type: str, speaker: str, priority: int,
                 template_key: tuple[str, str], fields: dict,
                 cacheable: bool):
        self.event_type = event_type
        self.speaker = speaker
        self.priority = priority
        self.template_key = template_key
        self.fields = fields
        self.cacheable = cacheable


class CommentaryService:
    """Stateful commentary pipeline. One instance per broadcast."""

    def __init__(self, cfg: dict, llm: LLMClient | None = None,
                 tts=None, cache: AudioCache | None = None,
                 clock=None):
        self.cfg = expand_paths(cfg)
        self.clock = clock or time.monotonic
        self.llm = llm or build_llm_client(cfg, on_switch=self._on_llm_switch)
        self.tts = tts or build_tts(cfg)
        self.cache = cache or AudioCache(cfg["tts"]["cache_dir"])
        self.limits = cfg["limits"]
        self.round_state: dict = {}
        self.in_swing = False
        self.pending: list[LineRequest] = []  # held by the director hold
        self.last_played_at: float | None = None
        self.lines_this_hole = 0
        self.current_hole: int | None = None
        self.spoken_seconds = 0.0
        self.broadcast_started_at: float | None = None
        self._switches: list[dict] = []
        self._ensure_dirs()

    # -- setup ----------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for key in ("decision_log", "output_log"):
            path = self.cfg["paths"][key]
            os.makedirs(os.path.dirname(path), exist_ok=True)
        os.makedirs(self.cfg["paths"]["audio_dir"], exist_ok=True)

    def _on_llm_switch(self, from_name: str, to_name: str, reason: str) -> None:
        self._switches.append(
            {"from": from_name, "to": to_name, "reason": reason,
             "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()})

    # -- logging ----------------------------------------------------------

    def _append_jsonl(self, path: str, record: dict) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def log_decision(self, record: dict) -> None:
        record.setdefault(
            "ts", datetime.datetime.now(datetime.timezone.utc).isoformat())
        record["silence_fraction"] = round(self.silence_fraction(), 3)
        self._append_jsonl(self.cfg["paths"]["decision_log"], record)

    # -- silence budget ---------------------------------------------------

    def silence_fraction(self) -> float:
        """Fraction of broadcast time spent speaking (target: <= 0.5)."""
        if self.broadcast_started_at is None:
            return 0.0
        elapsed = self.clock() - self.broadcast_started_at
        if elapsed <= 0:
            return 0.0
        return min(1.0, self.spoken_seconds / elapsed)

    # -- round state ------------------------------------------------------

    def _update_round_state(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "round_state":
            nested = event.get("round_state")
            if isinstance(nested, dict):
                # Bus snapshot (bus/translate.py snapshot_event): the real
                # state lives in the nested dict. Storing the raw envelope
                # left score_to_par/thru unreachable, so the first made
                # putt of a round crashed in standard_line (int('—')).
                self.round_state = dict(nested)
            else:
                # Flat form (commentary/demo.py): the event itself is the
                # state; keep its fields, minus the routing keys.
                self.round_state = {
                    k: v for k, v in event.items()
                    if k not in ("type", "seq", "event")
                }
            return
        if "score_to_par" in event:
            self.round_state["score_to_par"] = event["score_to_par"]
        if event_type == "hole_end":
            self.round_state["thru"] = event.get("hole", self.round_state.get("thru"))
            self.round_state["score_to_par"] = event.get(
                "score_to_par", self.round_state.get("score_to_par"))
        if event_type == "hole_start":
            self.round_state["hole"] = event.get("hole")
            self.round_state["current_hole"] = {
                "name": event.get("hole_name"),
                "par": event.get("par"),
                "yards": event.get("yards"),
            }

    def _template_fields(self, event: dict) -> dict:
        """Merge event fields with round_state for prompt templates."""
        state = self.round_state
        fields = dict(event)
        fields["thru"] = state.get("thru", event.get("thru", event.get("hole", 0)))
        fields["score_to_par"] = format_score(
            state.get("score_to_par", event.get("score_to_par")))
        fields["par"] = event.get("par", state.get("hole_par"))
        fields["hole_name"] = event.get(
            "hole_name", (state.get("current_hole") or {}).get("name"))
        fields["made_word"] = "made" if event.get("made") else "missed"
        fields["round"] = event.get("round_no", state.get("round"))
        fields["course"] = event.get("course", "Wyatt National")
        fields["target_score"] = event.get(
            "target_score", state.get("target_score", 59))
        fields["handicap"] = event.get("handicap", state.get("handicap", "+3.1"))
        fields["last10_avg"] = event.get(
            "last10_avg", state.get("last10_avg", "—"))
        fields["type"] = event.get("milestone_type") or event.get("type")
        stats = event.get("round_stats") or {}
        for key in ("fairways", "gir", "putts", "up_and_downs"):
            fields.setdefault(key, stats.get(key, "—"))
        fix = event.get("learning_fix") or {}
        fields["leak"] = fix.get("leak", "—")
        fields["strokes_lost"] = fix.get("strokes_lost", "—")
        fields["adjustment"] = fix.get("adjustment", "—")
        fields["new_handicap"] = event.get("new_handicap", "—")
        fields["rank"] = event.get("rank", "—")
        fields["strokes_gained_summary"] = self._strokes_gained_summary(event)
        fields["status"] = event.get("status", "—")
        fields["holes_left"] = event.get("holes_left", "—")
        fields["strokes_remaining"] = event.get("strokes_remaining", "—")
        fields["needs"] = event.get("needs", "—")
        fields["probability"] = event.get("probability", "—")
        fields["detail"] = event.get("detail", "—")
        return fields

    @staticmethod
    def _strokes_gained_summary(event: dict) -> str:
        sg = event.get("strokes_gained")
        if isinstance(sg, dict) and sg:
            parts = [f"{k} {v:+.2f}" for k, v in sorted(sg.items())]
            return "strokes gained: " + ", ".join(parts)
        if isinstance(sg, str):
            return sg
        return "—"

    # -- decision: is a line due? ------------------------------------------

    def plan_lines(self, event: dict) -> list[LineRequest]:
        """Decide which lines (if any) an event is due.

        Returns LineRequests in play order. An empty list means silence
        is the correct output for this event.
        """
        event_type = event.get("type")
        fields = self._template_fields(event)
        lines: list[LineRequest] = []

        if event_type == "round_start":
            lines.append(LineRequest(event_type, "host", PRIORITY_RESULT,
                                     ("round_start", "host"), fields, True))
        elif event_type == "hole_start":
            lines.append(LineRequest(event_type, "host", PRIORITY_RESULT,
                                     ("hole_start", "host"), fields, True))
        elif event_type == "decision":
            if event.get("shot_type") in RECOVERY_SHOTS:
                lines.append(LineRequest("recovery", "color", PRIORITY_COLOR,
                                         ("recovery", "color"), fields, False))
            else:
                lines.append(LineRequest(event_type, "color", PRIORITY_COLOR,
                                         ("decision", "color"), fields, False))
        elif event_type == "apex":
            if self._apex_worth_naming(event):
                lines.append(LineRequest(event_type, "color", PRIORITY_APEX,
                                         ("apex", "color"), fields, False))
            # A straight, on-line ball needs no call: silence.
        elif event_type == "landing":
            if event.get("result") in MISS_RESULTS:
                lines.append(LineRequest("bad_miss", "host", PRIORITY_RESULT,
                                         ("bad_miss", "host"), fields, False))
            else:
                lines.append(LineRequest(event_type, "host", PRIORITY_RESULT,
                                         ("landing", "host"), fields, True))
        elif event_type == "putt_result":
            lines.append(LineRequest(event_type, "host", PRIORITY_RESULT,
                                     ("putt_result", "host"), fields, True))
        elif event_type == "hole_end":
            lines.append(LineRequest(event_type, "host", PRIORITY_RESULT,
                                     ("hole_end", "host"), fields, True))
            if self._story_changed(event):
                lines.append(LineRequest(event_type, "color", PRIORITY_COLOR,
                                         ("hole_end", "color"), fields, False))
        elif event_type == "milestone":
            lines.append(LineRequest(event_type, "host", PRIORITY_RESULT,
                                     ("milestone", "host"), fields, False))
            lines.append(LineRequest(event_type, "color", PRIORITY_COLOR,
                                     ("milestone", "color"), fields, False))
        elif event_type == "fifty_nine_watch":
            lines.append(LineRequest(event_type, "host", PRIORITY_59_WATCH,
                                     ("fifty_nine_watch", "host"), fields, False))
            lines.append(LineRequest(event_type, "color", PRIORITY_59_WATCH,
                                     ("fifty_nine_watch", "color"), fields, False))
        elif event_type == "round_end":
            lines.append(LineRequest(event_type, "host", PRIORITY_RESULT,
                                     ("round_end", "host"), fields, False))
            lines.append(LineRequest(event_type, "color", PRIORITY_COLOR,
                                     ("round_end", "color"), fields, False))
        return lines

    @staticmethod
    def _apex_worth_naming(event: dict) -> bool:
        shape = (event.get("shape") or "straight").lower()
        try:
            curve = abs(float(event.get("curve_yds", 0) or 0))
        except (TypeError, ValueError):
            curve = 0
        if shape in ("draw", "fade"):
            return curve >= APEX_MIN_CURVE_YDS
        return curve >= APEX_MIN_OFFLINE_CURVE_YDS

    @staticmethod
    def _story_changed(event: dict) -> bool:
        """Did this hole change the round's story? (birdie, bogey, save)."""
        score = event.get("score")
        par = event.get("par")
        if score is not None and par is not None and score != par:
            return True
        return bool(event.get("up_and_down"))

    # -- generation ---------------------------------------------------------

    def _generate_line(self, request: LineRequest, event: dict) -> tuple[str | None, dict]:
        """Produce the line text for a request.

        Cached standard line first; else LLM generation with validation.
        Returns (text, info) where info carries cache_hit / backend /
        latency / drop_reason.
        """
        info: dict = {"cache_hit": False, "backend": None, "latency_ms": 0}
        if request.cacheable and request.event_type not in NEVER_CACHE:
            text = standard_line(request.event_type, request.fields, self.round_state)
            if text is not None:
                info["cache_hit"] = True
                return text, info
        if self.cfg.get("dry_run"):
            info["drop_reason"] = "dry_run_no_fresh_generation"
            return None, info
        user_prompt = render_user_prompt(
            request.template_key[0], request.template_key[1], request.fields)
        try:
            text, latency, backend = self.llm.generate(request.speaker, user_prompt)
        except Exception as exc:  # LLM down: drop the line, never pay for one.
            info["drop_reason"] = f"llm_failed: {exc}"
            return None, info
        info["backend"] = backend
        info["latency_ms"] = round(latency * 1000)
        if text.strip().upper() == "SILENCE":
            info["drop_reason"] = "llm_returned_silence"
            return None, info
        cleaned = norm.clean_line(text, self.limits["max_line_chars"])
        if cleaned is None:
            info["drop_reason"] = "line_failed_filter_or_length"
            return None, info
        if not norm.validate_numbers(cleaned, event, self.round_state):
            info["drop_reason"] = "invented_number"
            return None, info
        return cleaned, info

    # -- emission -----------------------------------------------------------

    def _rate_limited(self) -> bool:
        now = self.clock()
        if self.last_played_at is not None:
            if now - self.last_played_at < self.limits["min_seconds_between_lines"]:
                return True
        return self.lines_this_hole >= self.limits["max_lines_per_hole"]

    def _play(self, request: LineRequest, text: str, info: dict, event: dict) -> None:
        """Normalize, synthesize (cached audio), and emit a line."""
        voice_cfg = self.cfg["tts"][request.speaker]
        spoken = norm.normalize_for_tts(text)
        audio_path = self.cache.get(voice_cfg["voice"], spoken)
        tts_latency_ms = 0
        if audio_path is None:
            try:
                audio_bytes, tts_latency = self.tts.synthesize(request.speaker, spoken)
                tts_latency_ms = round(tts_latency * 1000)
            except Exception as exc:
                self.log_decision({
                    "event": event.get("type"), "seq": event.get("seq"),
                    "hole": event.get("hole"), "speaker": request.speaker,
                    "template": f"{request.template_key[0]}/{request.template_key[1]}",
                    "text": text, "voice": voice_cfg["voice"],
                    "backend": info.get("backend"), "latency_ms": info.get("latency_ms"),
                    "cache_hit": info.get("cache_hit", False),
                    "played": False, "drop_reason": f"tts_failed: {exc}",
                })
                return
            audio_path = self.cache.put(voice_cfg["voice"], spoken, audio_bytes)
            # The played file is also copied to the audio output dir so
            # the broadcast pipeline has one place to watch.
            out_path = os.path.join(
                self.cfg["paths"]["audio_dir"],
                os.path.basename(audio_path))
            if out_path != audio_path:
                with open(audio_path, "rb") as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
                audio_path = out_path
        else:
            out_path = os.path.join(
                self.cfg["paths"]["audio_dir"], os.path.basename(audio_path))
            if not os.path.exists(out_path):
                with open(audio_path, "rb") as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
            audio_path = out_path

        self.last_played_at = self.clock()
        self.lines_this_hole += 1
        self.spoken_seconds += len(text.split()) / WORDS_PER_SECOND
        record = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event": event.get("type"), "seq": event.get("seq"),
            "hole": event.get("hole"), "speaker": request.speaker,
            "voice": voice_cfg["voice"], "text": text,
            "spoken_text": spoken, "audio_path": audio_path,
            "cache_hit": info.get("cache_hit", False),
            "backend": info.get("backend"),
            "llm_latency_ms": info.get("latency_ms"),
            "tts_latency_ms": tts_latency_ms,
        }
        self._append_jsonl(self.cfg["paths"]["output_log"], record)
        self.log_decision({
            "event": event.get("type"), "seq": event.get("seq"),
            "hole": event.get("hole"), "speaker": request.speaker,
            "template": f"{request.template_key[0]}/{request.template_key[1]}",
            "text": text, "voice": voice_cfg["voice"],
            "backend": info.get("backend"), "latency_ms": info.get("latency_ms"),
            "cache_hit": info.get("cache_hit", False),
            "played": True, "drop_reason": None,
        })

    def _emit_or_hold(self, request: LineRequest, event: dict) -> None:
        """Generate a line, then play it now or hold it through the swing."""
        if not self.in_swing and self._rate_limited():
            # Check before generating: a rate-limited line must never
            # waste an LLM call.
            self.log_decision({
                "event": event.get("type"), "seq": event.get("seq"),
                "hole": event.get("hole"), "speaker": request.speaker,
                "template": f"{request.template_key[0]}/{request.template_key[1]}",
                "text": None, "voice": self.cfg["tts"][request.speaker]["voice"],
                "backend": None, "latency_ms": None,
                "cache_hit": False,
                "played": False, "drop_reason": "rate_limited",
            })
            return
        text, info = self._generate_line(request, event)
        if text is None:
            self.log_decision({
                "event": event.get("type"), "seq": event.get("seq"),
                "hole": event.get("hole"), "speaker": request.speaker,
                "template": f"{request.template_key[0]}/{request.template_key[1]}",
                "text": None, "voice": self.cfg["tts"][request.speaker]["voice"],
                "backend": info.get("backend"), "latency_ms": info.get("latency_ms"),
                "cache_hit": info.get("cache_hit", False),
                "played": False, "drop_reason": info.get("drop_reason"),
            })
            return
        if self.in_swing:
            # Rule 1: never speak over a swing. Hold until landing.
            self.pending.append((request, text, info, event))
            return
        self._play(request, text, info, event)

    def _flush_pending(self) -> None:
        """Release held lines after the swing, highest priority first."""
        if not self.pending:
            return
        held = sorted(self.pending, key=lambda item: -item[0].priority)
        self.pending = []
        for request, text, info, event in held:
            if self._rate_limited():
                self.log_decision({
                    "event": event.get("type"), "seq": event.get("seq"),
                    "hole": event.get("hole"), "speaker": request.speaker,
                    "template": f"{request.template_key[0]}/{request.template_key[1]}",
                    "text": text, "voice": self.cfg["tts"][request.speaker]["voice"],
                    "backend": info.get("backend"), "latency_ms": info.get("latency_ms"),
                    "cache_hit": info.get("cache_hit", False),
                    "played": False, "drop_reason": "rate_limited_after_hold",
                })
                continue
            self._play(request, text, info, event)

    # -- event handling -----------------------------------------------------

    def handle_event(self, raw_event: dict) -> None:
        """Process one bus event, end to end."""
        event = normalize_event(raw_event)
        if self.broadcast_started_at is None:
            self.broadcast_started_at = self.clock()
        event_type = event.get("type")
        hole = event.get("hole")
        if hole and hole != self.current_hole:
            self.current_hole = hole
            self.lines_this_hole = 0
        self._update_round_state(event)

        if event_type == "shot_start":
            self.in_swing = True
            return
        if event_type in ("landing", "putt_result"):
            self.in_swing = False
            self._flush_pending()
        if event_type == "strike":
            return  # No line is ever due at impact.

        for request in self.plan_lines(event):
            self._emit_or_hold(request, event)

    # -- main loop ----------------------------------------------------------

    def run(self, bus=None) -> None:
        """Connect to the bus and process events until it closes."""
        bus = bus or WebSocketBus(self.cfg["bus"]["url"])
        if isinstance(bus, WebSocketBus):
            connect_with_backoff(bus, self.cfg)
        try:
            while True:
                raw = bus.recv_text(timeout=30)
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self.handle_event(event)
        except (KeyboardInterrupt, Exception) as exc:
            # Bus closed / error: log and exit so launchd restarts us.
            self.log_decision({
                "event": "__service_stop__", "seq": None, "hole": self.current_hole,
                "speaker": None, "template": None, "text": None, "voice": None,
                "backend": None, "latency_ms": None, "cache_hit": False,
                "played": False, "drop_reason": f"service_stopped: {exc}",
            })
            raise


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Mas Golfs commentary service: sim events -> LLM -> Kokoro -> broadcast.")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--demo", action="store_true",
                        help="run the scripted fake-event demo instead of the live bus")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if args.demo:
        from .demo import run_demo
        run_demo(cfg)
        return 0
    service = CommentaryService(cfg)
    service.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
