"""Command line front end for the Pillarium alert system.

Usage::

    pillarium-notify --warning -t "Disk full" "/home is 90% full"

The command talks to the running session over the UNIX socket created
by :mod:`pillarium.alerts_server`.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys

from . import paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pillarium-notify",
        description="Raise an alert dialog in a running Pillarium session.",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="",
        help="the message shown in the dialog",
    )
    parser.add_argument("--error", action="store_true", help="show an error alert")
    parser.add_argument("--warning", action="store_true", help="show a warning alert")
    parser.add_argument("--startup", action="store_true", help="show a startup alert")
    parser.add_argument("-t", "--title", default="Pillarium", help="dialog title")
    parser.add_argument("-a", "--app", default="", help="application raising the alert")
    parser.add_argument("-d", "--detail", default="", help="extra detail line")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="auto dismiss after this many seconds (0 keeps it open)",
    )
    parser.add_argument("--sound", dest="sound", action="store_true", default=True)
    parser.add_argument("--no-sound", dest="sound", action="store_false")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Send an alert to the running Pillarium session."""
    parser = build_parser()
    args = parser.parse_args(argv)

    level = "warning"
    if args.error:
        level = "error"
    elif args.startup:
        level = "startup"

    payload = {
        "level": level,
        "title": args.title,
        "message": args.message,
        "app": args.app,
        "detail": args.detail,
        "timeout": args.timeout,
        "sound": bool(args.sound),
    }

    path = paths.alert_socket_path()
    if not _socket_exists(path):
        print(
            f"pillarium-notify: no Pillarium session is listening on {path}",
            file=sys.stderr,
        )
        return 1

    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3.0)
        client.connect(path)
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        client.close()
    except OSError as exc:
        print(f"pillarium-notify: could not reach Pillarium: {exc}", file=sys.stderr)
        return 1
    return 0


def _socket_exists(path: str) -> bool:
    import os

    return os.path.exists(path)


if __name__ == "__main__":
    raise SystemExit(main())
