"""Mas Golfs auto-clip pipeline.

Reads a sim-engine JSON event log, scores every moment with the drama
model (launch-playbook §1.1), selects the top 1-2 clips per round, and
outputs a clip manifest with in/out points, hook line, title, caption,
hashtags, and per-platform variants. ``assemble`` turns the manifest's
queue into finished videos with ffmpeg (cut + 0.5x slow-mo + burned-in
captions, 9:16).

Public API:
    load_events, score_round, assemble_clip, select_daily_queue,
    run_pipeline, build_manifest, write_manifest,
    assemble_manifest, assemble_clip_file, build_ffmpeg_command
"""

from .assemble import (
    AssemblyResult,
    assemble_clip_file,
    assemble_manifest,
    build_ffmpeg_command,
    build_filter_graph,
    check_ffmpeg,
)
from .assembly import ClipCard, assemble_clip
from .events import EventLogError, check_sequence, group_by_round, load_events, round_events
from .manifest import build_manifest, run_pipeline, select_daily_queue, write_manifest
from .scoring import Moment, score_round

__version__ = "0.1.0"

__all__ = [
    "AssemblyResult",
    "ClipCard",
    "EventLogError",
    "Moment",
    "assemble_clip",
    "assemble_clip_file",
    "assemble_manifest",
    "build_ffmpeg_command",
    "build_filter_graph",
    "build_manifest",
    "check_ffmpeg",
    "check_sequence",
    "group_by_round",
    "load_events",
    "round_events",
    "run_pipeline",
    "score_round",
    "select_daily_queue",
    "write_manifest",
]
