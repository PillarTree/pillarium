"""``pillarium-notify`` - raise a Pillarium alert window from a script.

Sends a small JSON message to the running window manager over the
``pillarium-alerts.sock`` UNIX socket.  Examples::

    pillarium-notify --error "Backup failed" "rsync exited with code 23"
    pillarium-notify --warning --title "Low disk" "Only 4% free on /home"
    pillarium-notify --startup "Session ready"

If the window manager is not running the command exits non-zero with a
message on stderr.
"""

import argparse
import json
import os
import socket
import sys

from . import paths


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="pillarium-notify",
        description="Raise a Pillarium alert window.",
    )
    level = parser.add_mutually_exclusive_group()
    level.add_argument(
        "--error", dest="level", action="store_const", const="error",
        help="show an error alert (red)",
    )
    level.add_argument(
        "--warning", "--warn", dest="level", action="store_const",
        const="warning", help="show a warning alert (amber)",
    )
    level.add_argument(
        "--startup", "--info", dest="level", action="store_const",
        const="startup", help="show a startup/info alert (accent)",
    )
    parser.set_defaults(level="warning")
    parser.add_argument("-t", "--title", default="", help="alert title")
    parser.add_argument(
        "-a", "--app", default="", help="application name shown in the dialog"
    )
    parser.add_argument(
        "-d", "--detail", default="", help="extra detail line"
    )
    parser.add_argument(
        "--timeout", type=float, default=None,
        help="auto-dismiss after N seconds (0 = wait for the user)",
    )
    parser.add_argument(
        "--sound", dest="sound", action="store_true", default=None,
        help="force the alert chime on",
    )
    parser.add_argument(
        "--no-sound", dest="sound", action="store_false",
        help="suppress the alert chime",
    )
    parser.add_argument(
        "message", nargs="*", help="alert message (joined with spaces)"
    )
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    message = " ".join(args.message)
    if not args.title and not message:
        print("pillarium-notify: nothing to show", file=sys.stderr)
        return 2

    payload = {
        "level": args.level,
        "title": args.title or message[:48],
        "message": message,
        "app": args.app,
        "detail": args.detail,
        "timeout": args.timeout,
        "sound": args.sound,
    }

    path = os.path.join(paths.home_dir(), "pillarium-alerts.sock")
    if not os.path.exists(path):
        print(
            "pillarium-notify: Pillarium is not running "
            f"(no socket at {path})",
            file=sys.stderr,
        )
        return 1

    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(2.0)
        conn.connect(path)
        conn.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        conn.close()
    except Exception as exc:
        print(f"pillarium-notify: could not reach Pillarium: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
