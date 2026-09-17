"""Path resolution for Pillarium's data files.

Pillarium never hard-codes the name or location of its own folder any
more: every directory it touches can be overridden through environment
variables, so the project may live under any directory name and still
work unchanged.

Environment variables:
    PILLARIUM_HOME       Base directory holding config.json and the
                         wallpaper image.  Defaults to the directory
                         that contains this package.
    PILLARIUM_CONFIG     Absolute path to the config.json file.
    PILLARIUM_WALLPAPER  Absolute path to the wallpaper image.
    PILLARIUM_DESKTOP    Desktop folder scanned for icons (overrides
                         the xdg-user-dir lookup).
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def expand(path):
    """Expand ~ and make the path absolute."""
    return os.path.abspath(os.path.expanduser(str(path)))


def home_dir():
    """The directory Pillarium stores its own files in (variable name)."""
    return expand(os.environ.get("PILLARIUM_HOME") or PROJECT_DIR)


def config_path():
    """Absolute path to the config.json file (variable location)."""
    return expand(
        os.environ.get("PILLARIUM_CONFIG")
        or os.path.join(home_dir(), "config.json")
    )


def wallpaper_path():
    """Absolute path to the wallpaper image (variable location)."""
    return expand(
        os.environ.get("PILLARIUM_WALLPAPER")
        or os.path.join(home_dir(), "pillarium_wallpaper.png")
    )


def desktop_dir():
    """Explicit desktop-folder override, or None to auto-detect."""
    override = os.environ.get("PILLARIUM_DESKTOP")
    if override:
        return expand(override)
    return None
