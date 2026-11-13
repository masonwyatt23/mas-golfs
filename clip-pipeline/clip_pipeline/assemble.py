"""ffmpeg assembly — turning clip cards into finished, post-ready videos.

Implements the step the README calls "next step, not built here": cut
``source.in_s``–``source.out_s`` from the OBS replay file, reorder per
``segments`` (payoff first — the hook segment is the first frame), burn in
the hook line and the on-screen caption text, crop to 9:16, and export the
finished clip with the replay file's own name
(``round0042-hole12-hole_out-0086.mp4``).

One ffmpeg call per clip, one filter graph:

    [0:v]trim + setpts (+ 0.5x setpts for slow-mo) -> scale -> crop 9:16
          -> fps 30 -> drawtext (hook / caption lines) -> [vN]
    [0:a]atrim + asetpts (+ atempo for slow-mo) -> aresample -> [aN]
    [v0][a0]...[vN][aN] concat -> [outv][outa] -> libx264 + aac

How the manifest's segment table is read (the table is a spec sketch, and
two of its rows overlap — see below):

* ``segments`` are a playlist in list order. The hook segment plays
  first, so the payoff is the first frame; the payoff segment plays
  last. That is the payoff-first ordering from ``assembly.py``.
* Each segment's output slot is ``[start_s, end_s)`` — the output
  timeline is authoritative, so the finished clip is exactly
  ``duration_s`` long and fits the platform length specs.
* Where slots overlap, the earlier segment is truncated at the next
  segment's start: the slow-mo segment sits inside the shot segment's
  span (29–32 inside 6–32), so the shot's full-speed portion ends at
  29 and the slow-mo replay takes over — the last 3 s are shown twice
  (once full speed, once at 0.5x), never double-counted in the total.
* A segment consumes ``(end_s - start_s) * speed`` seconds of source,
  starting at ``source_start_s``. At speed 1.0 that is exactly its
  declared source range. At 0.5x (drama >= 75, ``SLOW_MOTION_THRESHOLD``
  in ``assembly.py``) the first half of the declared range plays at half
  speed to fill the same output slot — the ball's final approach, which
  the hook and payoff segments already show dropping. The rest of the
  declared range is dropped, never stretched into a longer clip.

Captions: the burned-in text is the hook line (hook segment) and each
segment's ``on_screen_text`` (decision line, shot-data strip, REPLAY,
result card). The clip's ``caption`` field is the social post copy — it
is not burned into the video; it goes into the ``.txt`` sidecar next to
the clip, along with the title, hashtags, and CTA per platform, ready to
paste when posting.

Missing input is a skip, never a crash: a clip whose replay file is not
in the recordings directory is logged as ``skipped`` and the rest of the
queue still assembles. An ffmpeg failure is logged as ``failed`` with
ffmpeg's stderr, and the queue continues.

Audio: if the replay file has an audio stream (checked with ffprobe),
it is cut and slowed the same way as the video (atempo 0.5 for slow-mo).
If there is no audio stream, the clip is video-only.

Standard library only — the only external dependency is the ``ffmpeg``
(and ``ffprobe``) binary. See the README for install and the daily
workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from .assembly import REPLAY_BUFFER_S, SLOW_MOTION_THRESHOLD

# Vertical short-form master (launch-playbook §1.2: all three platforms
# take 9:16, 1080x1920).
OUT_W, OUT_H = 1080, 1920
OUT_FPS = 30
SLOW_MO_SPEED = 0.5

# drawtext styling: big white text, top-third safe on every platform
# (Shorts wants top-third; Reels avoids the bottom 25%; TikTok avoids the
# right edge — centered top text is safe for all three).
CAPTION_FONTSIZE = 56
CAPTION_Y_FRAC = 0.08

# Candidate bold fonts, in order. Overridden by MAS_GOLFS_FONT.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

DEFAULT_RECORDINGS_DIR = Path.home() / "mas-golfs" / "clips"


def find_font() -> Path | None:
    """First usable bold font, or None (captions are then skipped)."""
    override = os.environ.get("MAS_GOLFS_FONT")
    if override:
        p = Path(override)
        return p if p.is_file() else None
    for cand in _FONT_CANDIDATES:
        p = Path(cand)
        if p.is_file():
            return p
    return None


def escape_drawtext(text: str) -> str:
    """Escape text for a drawtext=text='...' value.

    ffmpeg's filter parser treats ``:`` as an option separator and
    ``%{...}`` as an expansion, so both are backslash-escaped. A plain
    apostrophe ``'`` is the one character that cannot be escaped safely:
    ``\\'`` inside a quoted value breaks the filtergraph parser
    (verified: exit 234, "Output with label ... does not exist"), so it
    is replaced with the typographic apostrophe ``’`` (U+2019), which
    renders identically on screen. Newlines become spaces.
    """
    return (
        text.replace("'", "\u2019")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("%", "\\%")
        .replace("\n", " ")
    )


def check_ffmpeg(ffmpeg: str = "ffmpeg") -> bool:
    """True when the ffmpeg binary is on PATH."""
    return shutil.which(ffmpeg) is not None


def has_audio(
    source: Path,
    ffprobe: str = "ffprobe",
    runner=subprocess.run,
) -> bool:
    """True when the replay file carries an audio stream (ffprobe).

    Any ffprobe problem (missing binary, unreadable file) is treated as
    "no audio" — the clip still assembles, video-only.
    """
    if shutil.which(ffprobe) is None:
        return False
    try:
        proc = runner(
            [
                ffprobe, "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=index",
                "-of", "json",
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:  # noqa: BLE001 - ffprobe failure must never kill a clip
        return False
    if proc.returncode != 0:
        return False
    try:
        return bool(json.loads(proc.stdout or "{}").get("streams"))
    except json.JSONDecodeError:
        return False


def segment_window(seg: dict) -> tuple[float, float, float]:
    """Source seconds a segment consumes, and its speed.

    Returns (source_start_s, source_end_s, speed). The segment fills its
    output slot ``[start_s, end_s)``; at speed < 1 it consumes only
    ``slot * speed`` seconds of source (see the module docstring).
    """
    out_dur = float(seg["end_s"]) - float(seg["start_s"])
    speed = float(seg.get("speed", 1.0))
    src_start = float(seg["source_start_s"])
    src_end = min(src_start + out_dur * speed, float(seg["source_end_s"]))
    return src_start, src_end, speed


def _drawtext_filters(text: str, font: Path) -> list[str]:
    """One drawtext filter per wrapped line, centered near the top."""
    lines = textwrap.wrap(text, width=28) or [""]
    filters = []
    for i, line in enumerate(lines):
        y = f"h*{CAPTION_Y_FRAC:.2f}+{i * (CAPTION_FONTSIZE + 8)}"
        filters.append(
            "drawtext="
            f"fontfile='{escape_drawtext(str(font))}'"
            f":text='{escape_drawtext(line)}'"
            f":fontsize={CAPTION_FONTSIZE}"
            ":fontcolor=white"
            ":borderw=2:bordercolor=black"
            ":box=1:boxcolor=black@0.5:boxborderw=20"
            f":x=(w-text_w)/2:y={y}"
        )
    return filters


def effective_segments(segments: list[dict]) -> list[dict]:
    """Segments with overlaps resolved: an earlier segment is truncated
    at the next segment's start.

    The manifest's slow-mo segment sits inside the shot segment's span
    (29–32 inside 6–32). Without this, concatenating both would count
    those 3 s twice and the clip would run 3 s over ``duration_s``
    (verified: 38 s for a 35 s card before this fix). The shot's
    full-speed portion ends where the replay begins.
    """
    effective = []
    for i, seg in enumerate(segments):
        seg = dict(seg)
        if i + 1 < len(segments):
            nxt = float(segments[i + 1]["start_s"])
            if nxt < float(seg["end_s"]):
                seg["end_s"] = nxt
        effective.append(seg)
    return effective


def build_filter_graph(clip: dict, font: Path | None, audio: bool) -> str:
    """The -filter_complex graph for one clip card (dict form).

    Segments are concatenated in list order (payoff first — the hook
    segment is first). Slow-mo segments (speed 0.5, drama >= 75) get
    ``setpts=2.0*PTS`` on video and ``atempo=0.5`` on audio; full-speed
    segments get plain ``setpts=PTS-STARTPTS`` / ``asetpts=PTS-STARTPTS``.
    """
    segments = effective_segments(clip["segments"])
    v_parts: list[str] = []
    a_parts: list[str] = []
    for i, seg in enumerate(segments):
        src_start, src_end, speed = segment_window(seg)
        v = (
            f"[0:v]trim=start={src_start:.3f}:end={src_end:.3f},"
            "setpts=PTS-STARTPTS"
        )
        if speed != 1.0:
            v += f",setpts={1.0 / speed:.3f}*PTS"
        v += (
            f",scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},fps={OUT_FPS}"
        )
        if font is not None:
            text = seg.get("on_screen_text") or ""
            if text:
                v += "," + ",".join(_drawtext_filters(text, font))
        v += f",format=yuv420p[v{i}]"
        v_parts.append(v)

        if audio:
            a = (
                f"[0:a]atrim=start={src_start:.3f}:end={src_end:.3f},"
                "asetpts=PTS-STARTPTS"
            )
            if speed != 1.0:
                a += f",atempo={speed}"
            a += f",aresample=48000[a{i}]"
            a_parts.append(a)

    concat_inputs = "".join(
        f"[v{i}]" + (f"[a{i}]" if audio else "") for i in range(len(segments))
    )
    n = len(segments)
    if audio:
        concat = f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]"
    else:
        concat = f"{concat_inputs}concat=n={n}:v=1:a=0[outv]"
    return ";".join(v_parts + a_parts + [concat])


def build_ffmpeg_command(
    clip: dict,
    source_path: Path | str,
    output_path: Path | str,
    font: Path | None = None,
    audio: bool = True,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """The full ffmpeg argv for one clip (no execution)."""
    graph = build_filter_graph(clip, font, audio)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source_path),
        "-filter_complex", graph,
        "-map", "[outv]",
    ]
    if audio:
        cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "128k"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    return cmd


@dataclass
class AssemblyResult:
    """Outcome of assembling one clip."""

    clip_id: str
    source_file: str
    output_path: Path | None
    status: str  # "done" | "skipped" | "failed"
    duration_s: float | None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "clip_id": self.clip_id,
            "source_file": self.source_file,
            "output_path": str(self.output_path) if self.output_path else None,
            "status": self.status,
            "duration_s": self.duration_s,
            "message": self.message,
        }


def expected_duration_s(clip: dict) -> float:
    """Output length: the card's duration_s (timeline is authoritative)."""
    return float(clip["duration_s"])


def assemble_clip_file(
    clip: dict,
    recordings_dir: Path | str,
    out_dir: Path | str,
    font: Path | None = None,
    ffmpeg: str = "ffmpeg",
    runner=subprocess.run,
    dry_run: bool = False,
) -> AssemblyResult:
    """Cut one clip card into a finished video file.

    ``clip`` is a clip-card dict exactly as it appears in the manifest
    (``ClipCard.to_dict()``). The output file keeps the replay file's
    name (``round0042-hole12-hole_out-0086.mp4``); a ``.txt`` sidecar
    with the title, caption, and per-platform post copy is written next
    to it. Missing recordings are skipped, never fatal.
    """
    clip_id = clip.get("clip_id", "?")
    source_file = clip.get("source", {}).get("replay_file", "")
    recordings_dir = Path(recordings_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not source_file:
        return AssemblyResult(clip_id, source_file, None, "failed",
                              None, "clip card has no source.replay_file")
    source_path = recordings_dir / source_file
    if not source_path.is_file():
        return AssemblyResult(
            clip_id, source_file, None, "skipped", None,
            f"replay file not in {recordings_dir}: {source_file} "
            "(OBS replay buffer did not save this moment)",
        )
    segments = clip.get("segments") or []
    if not segments:
        return AssemblyResult(clip_id, source_file, None, "failed",
                              None, "clip card has no segments")

    output_path = out_dir / source_file
    # Dry runs build the command without touching ffprobe or ffmpeg.
    audio = True if dry_run else has_audio(source_path, runner=runner)
    cmd = build_ffmpeg_command(clip, source_path, output_path,
                               font=font, audio=audio, ffmpeg=ffmpeg)
    if dry_run:
        return AssemblyResult(clip_id, source_file, output_path, "done",
                              expected_duration_s(clip),
                              "dry run — command built, ffmpeg not executed: "
                              + " ".join(cmd))

    proc = runner(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        return AssemblyResult(
            clip_id, source_file, None, "failed", None,
            f"ffmpeg exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()[-500:]}",
        )

    _write_sidecar(clip, output_path)
    return AssemblyResult(clip_id, source_file, output_path, "done",
                          expected_duration_s(clip),
                          "slow-mo" if clip.get("slow_motion") else "")


def _write_sidecar(clip: dict, output_path: Path) -> Path:
    """Post copy for the clip: title, caption, per-platform hashtags/CTA."""
    lines = [clip.get("title", ""), "", clip.get("caption", ""), "",
             clip.get("first_comment", ""), ""]
    for key, spec in (clip.get("platforms") or {}).items():
        lines.append(f"[{spec.get('platform', key)}]")
        lines.append(" ".join(spec.get("hashtags", [])))
        lines.append(f"CTA: {spec.get('cta', '')}")
        lines.append(f"Post: {spec.get('posting_window', '')}")
        lines.append("")
    sidecar = output_path.with_suffix(".txt")
    sidecar.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return sidecar


def load_manifest(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assemble_manifest(
    manifest: dict,
    recordings_dir: Path | str,
    out_dir: Path | str,
    only_queue: bool = True,
    font: Path | None = None,
    ffmpeg: str = "ffmpeg",
    runner=subprocess.run,
    dry_run: bool = False,
) -> list[AssemblyResult]:
    """Assemble every clip in a manifest (default: the daily queue only).

    ``manifest`` is the dict from ``manifest.py`` (``queue`` + ``library``).
    A missing replay file skips that clip and the queue continues — the
    return list always covers every clip attempted, in manifest order.
    A report (``assembly_report.json``) is written to ``out_dir``.
    """
    if not check_ffmpeg(ffmpeg):
        raise FileNotFoundError(
            f"ffmpeg binary not found: {ffmpeg} — install ffmpeg "
            "(brew install ffmpeg / apt install ffmpeg) and retry"
        )
    if font is None:
        font = find_font()
        if font is None:
            print("warning: no bold caption font found "
                  "(set MAS_GOLFS_FONT) — clips will assemble "
                  "without burned-in text", file=sys.stderr)
    clips = manifest["queue"] if only_queue else manifest["library"]
    results = [
        assemble_clip_file(
            clip, recordings_dir, out_dir,
            font=font, ffmpeg=ffmpeg, runner=runner, dry_run=dry_run,
        )
        for clip in clips
    ]
    out_dir = Path(out_dir)
    report = {
        "generator": "mas-golfs clip-pipeline 0.1.0",
        "round": manifest.get("round", {}),
        "only_queue": only_queue,
        "summary": {
            "attempted": len(results),
            "done": sum(r.status == "done" for r in results),
            "skipped": sum(r.status == "skipped" for r in results),
            "failed": sum(r.status == "failed" for r in results),
        },
        "results": [r.to_dict() for r in results],
    }
    (out_dir / "assembly_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clip-pipeline-assemble",
        description="Assemble finished clips from a clip manifest "
                    "(ffmpeg cut + slow-mo + burned-in captions).",
    )
    parser.add_argument("--manifest", "-m", required=True,
                        help="Clip manifest JSON (output/manifest.json).")
    parser.add_argument("--recordings", "-r", default=str(DEFAULT_RECORDINGS_DIR),
                        help="OBS replay-buffer recordings dir "
                             "(default ~/mas-golfs/clips).")
    parser.add_argument("--out", "-o", default="output/clips",
                        help="Where finished clips go (default output/clips).")
    parser.add_argument("--all", dest="all_clips", action="store_true",
                        help="Assemble the whole library, not just the queue.")
    parser.add_argument("--ffmpeg", default="ffmpeg",
                        help="ffmpeg binary (default ffmpeg).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the ffmpeg commands but do not run them.")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Only print errors.")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except Exception as exc:  # noqa: BLE001 - surface a bad manifest cleanly
        print(f"error: could not load manifest: {exc}", file=sys.stderr)
        return 1
    try:
        results = assemble_manifest(
            manifest, args.recordings, args.out,
            only_queue=not args.all_clips,
            ffmpeg=args.ffmpeg, dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        done = sum(r.status == "done" for r in results)
        print(f"Assembled {done}/{len(results)} clip(s) -> {args.out}")
        for r in results:
            mark = {"done": "OK ", "skipped": "SKIP", "failed": "FAIL"}[r.status]
            print(f"  {mark} {r.clip_id} {r.source_file} — {r.message}")
    return 0 if all(r.status != "failed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
