#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Pillarium entry point.

The window manager itself lives in the `pillarium` package (split
across focused modules); this script is a thin launcher so the old
command keeps working from anywhere on disk.
"""

import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pillarium import Pillarium


def main():
    wm = Pillarium()

    def _handle_signal(signum, frame):
        # Raising SystemExit unwinds the run loop so the finally block
        # below performs a clean shutdown.
        raise SystemExit(0)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    try:
        wm.run()
    finally:
        try:
            wm._shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
