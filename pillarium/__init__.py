"""Pillarium – a lightweight X11 window manager / desktop environment.

The project may live under any directory name; all data-file locations
are resolved by :mod:`pillarium.paths` and can be overridden with
environment variables (see that module for details).
"""

from .wm import Pillarium

__version__ = "1.0.4"
__all__ = ["Pillarium"]
