"""Configuration loading for the commentary service.

The box has no PyYAML installed and the service is stdlib-only, so this
module parses the subset of YAML that ``config.yaml`` actually uses:

* ``key: value`` mappings, nested by 2-space indentation
* scalars: strings (plain or single/double quoted), ints, floats, bools
* inline lists: ``[a, b, c]``
* full-line comments (``# ...``) and blank lines

Anything outside that subset raises :class:`ConfigError` with the line
number, rather than silently misreading the file. Keep ``config.yaml``
inside the subset and this stays boring, which is the point.
"""

from __future__ import annotations

import os
import re

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.masgolfs/commentary-config.yaml")


class ConfigError(ValueError):
    """Raised when config.yaml cannot be parsed or is missing a key."""


def _parse_scalar(raw: str, lineno: int):
    raw = raw.strip()
    if raw == "":
        return ""
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item, lineno) for item in inner.split(",")]
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw


def parse_yaml_subset(text: str) -> dict:
    """Parse the small YAML subset described in the module docstring."""
    root: dict = {}
    # Stack of (indent_level, dict). Root is level -1.
    stack: list[tuple[int, dict]] = [(-1, root)]
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2 != 0:
            raise ConfigError(f"line {lineno}: indentation must be a multiple of 2")
        content = line.strip()
        if ":" not in content:
            raise ConfigError(f"line {lineno}: expected 'key: value', got {content!r}")
        key, _, value = content.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            raise ConfigError(f"line {lineno}: empty key")
        # Strip a trailing inline comment on a plain scalar value.
        if value and not value.startswith(('"', "'", "[")):
            value = value.split(" #", 1)[0].strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value, lineno)
    return root


def load_config(path: str | None = None) -> dict:
    """Load config.yaml and validate the keys the service needs."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = parse_yaml_subset(fh.read())
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    required = [
        ("bus", "url"),
        ("llm", "backend"),
        ("llm", "generation", "temperature"),
        ("llm", "generation", "max_tokens"),
        ("llm", "generation", "timeout_seconds"),
        ("tts", "base_url"),
        ("tts", "host", "voice"),
        ("tts", "color", "voice"),
        ("limits", "min_seconds_between_lines"),
        ("limits", "max_lines_per_hole"),
        ("limits", "max_line_chars"),
    ]
    for keys in required:
        node = cfg
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                raise ConfigError(f"config missing required key: {'.'.join(keys)}")
            node = node[key]
    return cfg


def expand_paths(cfg: dict) -> dict:
    """Expand ~ in every configured path, in place. Returns the config."""
    for section in ("tts", "paths"):
        node = cfg.get(section)
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and value.startswith("~"):
                    node[key] = os.path.expanduser(value)
    return cfg
