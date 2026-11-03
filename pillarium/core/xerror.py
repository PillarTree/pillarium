"""Keep X protocol errors from killing the window manager.

Xlib's default error handler prints a message and calls ``exit(1)``.  A
window manager touches windows that other applications destroy at the
same moment - a client that closes its own window while the manager is
sending it a message, for example - and a single such race would take
the whole session down.

The handler installed here ignores every X error instead.  It is
installed for the whole process, so it also covers the connection that
Tk uses, which python-xlib cannot reach.
"""

from __future__ import annotations

import ctypes
import ctypes.util

#: The C callback, kept alive for the lifetime of the process.
_handler = None
#: The loaded library, kept alive as well.
_library = None


def _ignore(display: object, event: object) -> int:
    """Swallow an X error and let the server carry on."""
    return 0


def install() -> bool:
    """Install the error handler.

    Returns ``True`` when the handler was installed.  Failing to install
    it is not fatal, Pillarium simply keeps the default behaviour.
    """
    global _handler, _library
    if _handler is not None:
        return True

    name = ctypes.util.find_library("X11") or "libX11.so.6"
    try:
        library = ctypes.CDLL(name)
        prototype = ctypes.CFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p
        )
        handler = prototype(_ignore)
        library.XSetErrorHandler(handler)
    except Exception:
        return False
    _handler = handler
    _library = library
    return True


def installed() -> bool:
    """Is the error handler in place?"""
    return _handler is not None
