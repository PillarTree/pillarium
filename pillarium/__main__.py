"""``python -m pillarium`` starts the window manager."""

from __future__ import annotations

import os
import signal
import sys
import traceback


def _log_file():
    from . import paths

    try:
        os.makedirs(paths.home_dir(), exist_ok=True)
        return open(paths.log_path(), "a", buffering=1)
    except Exception:
        return None


def main() -> int:
    """Start Pillarium and run it until the session ends."""
    log = _log_file()
    if log is not None:
        try:
            import faulthandler

            faulthandler.enable(file=log, all_threads=True)
        except Exception:
            pass

    from .app import PillariumApp

    app = PillariumApp()

    def _handle_signal(_signum, _frame):
        raise SystemExit(0)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    try:
        app.run()
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
            app.shutdown()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
