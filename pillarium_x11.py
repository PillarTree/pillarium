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
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pillarium import Pillarium


def _log_file():
    home = os.environ.get("PILLARIUM_HOME") or os.path.expanduser("~/.pillarium")
    try:
        os.makedirs(home, exist_ok=True)
        return open(os.path.join(home, "pillarium.log"), "a", buffering=1)
    except Exception:
        return None


def main():
    log = _log_file()
    if log is not None:
        try:
            import faulthandler

            faulthandler.enable(file=log, all_threads=True)
        except Exception:
            pass

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
    except SystemExit:
        raise
    except BaseException:
        if log is not None:
            try:
                log.write("Pillarium: fatal error\n")
                traceback.print_exc(file=log)
                log.flush()
            except Exception:
                pass
        raise
    finally:
        try:
            wm._shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
