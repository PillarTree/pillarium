"""Pillarium 2.0 - a lightweight X11 window manager and desktop shell.

The package is organised in four layers:

``pillarium.core``
    The X11 layer: display handling, monitor enumeration, window
    management, hotkeys and the ``_NET_WM_PING`` watchdog.
``pillarium.shell``
    The user interface, built with customtkinter: the desktop surface,
    per-monitor taskbars, window decorations, panels and dialogs.
``pillarium.system``
    Everything that talks to the operating system: applications, audio,
    networking, bluetooth, battery, processes and wallpapers.
``pillarium.theme``
    The theme engine: built-in palettes, user themes and the
    freedesktop.org appearance import.
"""

from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["__version__"]
