"""Raw probe: dump exactly what the mlx-lm server returns for one prompt.

The smoke check reported "streamed an empty completion" — the server
finished prefill and then sent zero content deltas. This script prints
the raw SSE lines and the raw non-streaming JSON body, verbatim, so the
cause (empty choices, null content, reasoning-only output, immediate
stop, server error) is visible instead of guessed.

Reuses mlx_verify.ChatClient so the payload is byte-identical to the
smoke check's: same system prompt, same event, same temperature and
max_tokens. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from mlx_verify import ChatClient, load_events  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:8080/v1")
    ap.add_argument("--model", default="mlx-community/Qwen3.5-4B-4bit")
    ap.add_argument("--events", default=None)
    ap.add_argument("--event-id", default="ev01")
    ap.add_argument("--timeout", type=float, default=180.0)
    args = ap.parse_args()

    events = load_events(args.events) if args.events else None
    if events is None:
        import os
        events = load_events(os.path.join(
            os.path.dirname(__file__), "events.json"))
    ev = next((e for e in events if e["id"] == args.event_id), events[0])

    client = ChatClient(args.base_url, args.model,
                        timeout_seconds=args.timeout)
    print(f"event: {ev['id']} speaker={ev['speaker']}")
    print(f"system prompt (first 200 chars): "
          f"{client._systems[ev['speaker']][:200]!r}")
    print(f"user prompt: {ev['user_prompt']!r}")
    print()

    # 1. What model does the server think it is serving?
    with urllib.request.urlopen(f"{client.base_url}/models",
                                timeout=10.0) as resp:
        print("GET /v1/models ->", resp.status)
        print(resp.read().decode("utf-8")[:1000])
    print()

    # 2. Streaming request: print every raw SSE line verbatim.
    req = urllib.request.Request(
        f"{client.base_url}/chat/completions",
        data=client._payload(ev["speaker"], ev["user_prompt"], stream=True),
        headers={"Content-Type": "application/json"}, method="POST")
    print("POST /v1/chat/completions stream=true -> raw SSE lines:")
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            print(f"  HTTP {resp.status}")
            n = 0
            for raw in resp:
                n += 1
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                print(f"  [{n}] {line[:500]}")
                if n >= 200:
                    print("  ... (truncated at 200 lines)")
                    break
            print(f"  total SSE lines: {n}")
    except Exception as exc:  # noqa: BLE001 - probe must print, not crash
        print(f"  STREAMING REQUEST FAILED: {type(exc).__name__}: {exc}")
    print()

    # 3. Non-streaming request: print the full JSON body verbatim.
    req = urllib.request.Request(
        f"{client.base_url}/chat/completions",
        data=client._payload(ev["speaker"], ev["user_prompt"], stream=False),
        headers={"Content-Type": "application/json"}, method="POST")
    print("POST /v1/chat/completions stream=false -> raw JSON body:")
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            print(f"  HTTP {resp.status}")
            body = resp.read().decode("utf-8")
            print(f"  {body[:3000]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  NON-STREAMING REQUEST FAILED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
