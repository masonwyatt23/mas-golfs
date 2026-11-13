"""Mas Golfs event bus — local WebSocket server on port 4456.

Stdlib only: no third-party dependencies. See ``bus/README.md``.
"""

from .server import create_server, serve_forever, default_state_file
from .client import BusPublisher, BusError
from .translate import translate_event, RoundState

__all__ = [
    "BusPublisher",
    "BusError",
    "RoundState",
    "create_server",
    "default_state_file",
    "serve_forever",
    "translate_event",
]

__version__ = "1.0.0"
