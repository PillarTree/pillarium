"""Tests for the X error safety net.

An X protocol error must never end the session: Xlib's default error
handler prints a message and calls ``exit(1)``, which would take the
window manager down with it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

from pillarium.core import xerror

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(xerror.__file__)))
)

SCRIPT = textwrap.dedent(
    """
    import ctypes, sys, time
    sys.path.insert(0, sys.argv[1])
    from pillarium.core import xerror
    assert xerror.install()

    from Xlib import display as D
    d = D.Display()
    root = d.screen().root
    win = root.create_window(10, 10, 100, 100, 0, d.screen().root_depth)
    win.map()
    d.sync()
    xid = win.id
    win.destroy()
    d.sync()
    time.sleep(0.3)

    lib = ctypes.CDLL("libX11.so.6")
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XGetWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                         ctypes.c_void_p]
    dpy = lib.XOpenDisplay(None)
    attributes = ctypes.create_string_buffer(256)
    lib.XGetWindowAttributes(dpy, ctypes.c_ulong(xid), attributes)
    lib.XFlush(dpy)
    time.sleep(0.5)
    print("survived")
    """
)


def test_the_error_handler_is_installed():
    assert xerror.install() is True
    assert xerror.installed() is True


def test_an_x_error_does_not_kill_the_process(tmp_path):
    """A BadWindow from libX11 must not take the process down."""
    if not os.environ.get("DISPLAY"):
        import pytest

        pytest.skip("no X display")

    path = tmp_path / "errortest.py"
    path.write_text(SCRIPT, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(path), REPO_ROOT],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ},
    )
    assert "survived" in result.stdout, result.stderr
    assert "X Error of failed request" not in result.stderr
