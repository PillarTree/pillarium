"""Filesystem layout for Pillarium 2.0.

Every path Pillarium touches is resolved through this module so the
project can live under any directory name and so a single environment
variable (``PILLARIUM_HOME``) relocates the whole runtime state.

Environment variables
---------------------
``PILLARIUM_HOME``
    Base directory for runtime state (config, themes, logs).  Defaults
    to ``~/.pillarium``.
``PILLARIUM_CONFIG``
    Absolute path of ``config.json``.  Defaults to ``$PILLARIUM_HOME/config.json``.
``PILLARIUM_THEMES``
    Directory holding user-authored theme files.  Defaults to
    ``$PILLARIUM_HOME/themes``.
``PILLARIUM_WALLPAPER``
    Absolute path of the default wallpaper image.
``PILLARIUM_DESKTOP``
    Desktop folder scanned for icons (overrides the XDG lookup).
"""

from __future__ import annotations

import os
import shutil

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)


def expand(path: str | os.PathLike[str]) -> str:
    """Expand ``~`` and return an absolute path."""
    return os.path.abspath(os.path.expanduser(str(path)))


def home_dir() -> str:
    """Base directory holding all mutable Pillarium state."""
    return expand(os.environ.get("PILLARIUM_HOME") or os.path.join("~", ".pillarium"))


def config_path() -> str:
    """Absolute path of the JSON configuration file."""
    return expand(
        os.environ.get("PILLARIUM_CONFIG")
        or os.path.join(home_dir(), "config.json")
    )


def themes_dir() -> str:
    """Directory holding user-authored theme files."""
    return expand(
        os.environ.get("PILLARIUM_THEMES")
        or os.path.join(home_dir(), "themes")
    )


def wallpaper_path() -> str:
    """Absolute path of the default wallpaper image."""
    return expand(
        os.environ.get("PILLARIUM_WALLPAPER")
        or os.path.join(home_dir(), "pillarium_wallpaper.png")
    )


def sounds_dir() -> str:
    """Directory of the bundled alert chimes."""
    return os.path.join(PACKAGE_DIR, "sounds")


def log_path() -> str:
    """Absolute path of the Pillarium log file."""
    return os.path.join(home_dir(), "pillarium.log")


def alert_socket_path() -> str:
    """UNIX socket used by ``pillarium-notify`` to raise alerts."""
    return os.path.join(home_dir(), "pillarium-alerts.sock")


def default_config_path() -> str:
    """Path of the configuration file shipped with the package."""
    return os.path.join(PACKAGE_DIR, "defaults", "config.json")




def install_default_config() -> str:
    """Copy the shipped configuration into the home directory.

    Returns the path of the configuration file.  An existing file is
    never overwritten.
    """
    target = config_path()
    if os.path.exists(target):
        return target
    source = default_config_path()
    try:
        os.makedirs(os.path.dirname(target) or home_dir(), exist_ok=True)
        shutil.copyfile(source, target)
    except OSError:
        return target
    return target


def desktop_dir() -> str | None:
    """Explicit desktop-folder override, or ``None`` to auto-detect."""
    override = os.environ.get("PILLARIUM_DESKTOP")
    return expand(override) if override else None


def ensure_dirs() -> None:
    """Create the runtime directories Pillarium expects to exist."""
    for directory in (home_dir(), themes_dir()):
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            pass

