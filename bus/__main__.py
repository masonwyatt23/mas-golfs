"""Run the event-bus server: ``python -m bus``."""

from __future__ import annotations

import argparse
import logging
import sys

from .server import DEFAULT_HOST, DEFAULT_PORT, serve_forever


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bus",
        description="Mas Golfs event bus — local WebSocket server.")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="bind port (default: 4456)")
    parser.add_argument("--state-file", default=None,
                        help="last-event file path; 'none' disables it "
                             "(default: resolved from MAS_GOLFS_STATE_FILE "
                             "/ MAS_GOLFS_HOME / repo layout)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    serve_forever(args.host, args.port, state_file=args.state_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
