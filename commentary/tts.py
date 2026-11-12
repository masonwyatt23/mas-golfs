"""TTS backends for the commentary pipeline (docs/voice-options.md §2, §8).

The default is **Kokoro-FastAPI**, an OpenAI-compatible endpoint
(``POST /v1/audio/speech``) on ``localhost:8880``. One-shot synthesis
per line — no streaming websocket, which is fine for event lines.

:class:`StubTTS` synthesizes nothing: it returns a short deterministic
byte string and records the request. It exists so the demo and the
tests can run the full pipeline with no TTS server. Production must
never use it — a stub voice on air would be silence with extra steps.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class TTSError(RuntimeError):
    """Raised when the TTS backend fails to synthesize a line."""


class KokoroTTS:
    """Kokoro-FastAPI over its OpenAI-compatible HTTP endpoint."""

    def __init__(self, base_url: str, voices: dict[str, dict],
                 timeout_seconds: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.voices = voices
        self.timeout_seconds = timeout_seconds

    def synthesize(self, speaker: str, text: str) -> tuple[bytes, float]:
        """Synthesize one line. Returns (audio_bytes, latency_seconds)."""
        voice_cfg = self.voices[speaker]
        payload = json.dumps({
            "model": "kokoro",
            "input": text,
            "voice": voice_cfg["voice"],
            "speed": float(voice_cfg.get("speed", 1.0)),
            "response_format": "wav",
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/audio/speech",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                audio = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TTSError(f"Kokoro TTS failed: {exc}") from exc
        return audio, time.monotonic() - started

    def healthy(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/audio/voices", timeout=2.0
            ) as resp:
                return resp.status == 200
        except Exception:
            return False


class StubTTS:
    """Deterministic stand-in TTS for the demo and tests."""

    def __init__(self):
        self.name = "stub"
        self.calls: list[tuple[str, str]] = []

    def synthesize(self, speaker: str, text: str) -> tuple[bytes, float]:
        self.calls.append((speaker, text))
        # A minimal valid WAV header + silence, so downstream code that
        # writes/reads the file behaves the same as with real audio.
        return _silent_wav(), 0.0

    def healthy(self) -> bool:
        return True


def _silent_wav(duration_seconds: float = 0.1, sample_rate: int = 24000) -> bytes:
    """A tiny valid WAV file of silence (24 kHz mono, 16-bit)."""
    import struct

    frames = int(sample_rate * duration_seconds)
    data = b"\x00\x00" * frames
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
    )
    return header + data


def build_tts(cfg: dict):
    """Build the TTS backend from config.yaml (stub when dry-running)."""
    if cfg.get("dry_run") or cfg.get("stub_llm"):
        return StubTTS()
    return KokoroTTS(
        base_url=cfg["tts"]["base_url"],
        voices={"host": cfg["tts"]["host"], "color": cfg["tts"]["color"]},
    )
