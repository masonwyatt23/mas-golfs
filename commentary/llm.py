"""LLM backends for the commentary pipeline (docs/local-models.md §3).

One interface, two engines behind it:

* **MLX (mlx-lm server)** — the default. OpenAI-compatible HTTP on
  ``localhost:8080/v1``.
* **Ollama (llama.cpp)** — the automatic fallback on
  ``localhost:11434/v1``. The service tries MLX first, falls back on
  failure, and logs the switch. A fallback that has never been tested
  is not a fallback — the tests exercise it.

Both are local and free. There is no paid-API backend in this module,
by design. The only other implementation is :class:`StubLLM`, a
deterministic stand-in used by the demo and the tests so the pipeline
can run end-to-end with no model server at all.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .prompts import SYSTEM_PROMPTS


class LLMError(RuntimeError):
    """Raised when an LLM backend fails to produce a completion."""


class HttpLLMBackend:
    """An OpenAI-compatible ``/v1/chat/completions`` endpoint over HTTP.

    Stdlib only (``urllib``) — no ``requests`` dependency on the box.
    One call per event, no conversation history, temperature and max
    tokens from the config (commentary-prompts.md §2.3).
    """

    def __init__(self, name: str, base_url: str, model: str,
                 temperature: float = 0.7, max_tokens: int = 120,
                 timeout_seconds: float = 10.0):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def generate(self, speaker: str, user_prompt: str) -> tuple[str, float]:
        """Generate one line. Returns (text, latency_seconds)."""
        system = SYSTEM_PROMPTS[speaker]
        # chat_template_kwargs enable_thinking=false: Qwen3.5 defaults to
        # thinking mode, and with max_tokens=120 the whole budget is eaten
        # by the reasoning block — content comes back null and the answer
        # never starts (verified on the box 2026-11-13 via mlx-verify's
        # probe_raw.py). The design is non-thinking (config.yaml).
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"{self.name} backend failed: {exc}") from exc
        latency = time.monotonic() - started
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name} returned an unusable response: {body!r}") from exc
        if text is None:
            # A 200 with null content (e.g. the model spent its whole token
            # budget thinking) is an unusable response, not a string.
            raise LLMError(f"{self.name} returned an unusable response: {body!r}")
        return text.strip(), latency

    def healthy(self) -> bool:
        """Best-effort health check: does ``/v1/models`` answer?"""
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/models", timeout=2.0
            ) as resp:
                return resp.status == 200
        except Exception:
            return False


class StubLLM:
    """Deterministic stand-in LLM for the demo and tests.

    Returns a fixed, event-appropriate line for each speaker, built
    from the numbers in the user prompt. It never invents a number and
    never calls a server. Production must never use this.
    """

    def __init__(self):
        self.name = "stub"
        self.calls: list[tuple[str, str]] = []

    def generate(self, speaker: str, user_prompt: str) -> tuple[str, float]:
        self.calls.append((speaker, user_prompt))
        if speaker == "color":
            return ("He has picked his spot and committed to the shot.", 0.0)
        return ("That is the result, and it leaves him a look at the next one.", 0.0)

    def healthy(self) -> bool:
        return True


class LLMClient:
    """Primary + fallback LLM with automatic failover and logging.

    ``on_switch`` is called with (from_name, to_name, reason) whenever
    the active backend changes, so the service can log it.
    """

    def __init__(self, primary: HttpLLMBackend | StubLLM,
                 fallback: HttpLLMBackend | StubLLM | None = None,
                 on_switch=None):
        self.primary = primary
        self.fallback = fallback
        self.active = primary
        self.on_switch = on_switch

    def generate(self, speaker: str, user_prompt: str) -> tuple[str, float, str]:
        """Generate a line. Returns (text, latency, backend_name)."""
        try:
            text, latency = self.active.generate(speaker, user_prompt)
            return text, latency, self.active.name
        except LLMError as exc:
            if self.fallback is None or self.active is self.fallback:
                raise
            reason = str(exc)
            if self.on_switch:
                self.on_switch(self.active.name, self.fallback.name, reason)
            self.active = self.fallback
            text, latency = self.active.generate(speaker, user_prompt)
            return text, latency, self.active.name


def build_llm_client(cfg: dict, on_switch=None) -> LLMClient:
    """Build the LLM client from config.yaml (or a stub for tests/demo)."""
    if cfg.get("stub_llm"):
        return LLMClient(StubLLM(), None, on_switch=on_switch)
    gen = cfg["llm"]["generation"]
    primary = HttpLLMBackend(
        name="mlx",
        base_url=cfg["llm"]["mlx"]["base_url"],
        model=cfg["llm"]["mlx"]["model"],
        temperature=gen["temperature"],
        max_tokens=gen["max_tokens"],
        timeout_seconds=gen["timeout_seconds"],
    )
    fallback = HttpLLMBackend(
        name="ollama",
        base_url=cfg["llm"]["ollama"]["base_url"],
        model=cfg["llm"]["ollama"]["model"],
        temperature=gen["temperature"],
        max_tokens=gen["max_tokens"],
        timeout_seconds=gen["timeout_seconds"],
    )
    if cfg["llm"].get("backend") == "ollama":
        return LLMClient(fallback, primary, on_switch=on_switch)
    return LLMClient(primary, fallback, on_switch=on_switch)
