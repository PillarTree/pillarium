"""Alert chimes.

Pillarium ships three Ogg Vorbis cues (startup, warning, error).  They are
played through whichever of the common command line players is installed;
when none is available the terminal bell is used instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .. import paths

DEFAULT_VOLUME = 0.6

#: Cue file for each alert level.
ASSETS: dict[str, str] = {
    "startup": "startup.ogg",
    "warning": "warn.ogg",
    "error": "error.ogg",
    "theme": "theme.ogg",
}

#: Preferred players, in order, with the argument builder for each.
PLAYERS: tuple[tuple[str, object], ...] = (
    ("paplay", lambda path, volume: ["paplay", f"--volume={int(round(volume * 65536))}", path]),
    ("pw-play", lambda path, volume: ["pw-play", f"--volume={volume:.3f}", path]),
    ("ffplay", lambda path, volume: [
        "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
        "-volume", str(int(round(volume * 100))), path,
    ]),
    ("mpv", lambda path, volume: [
        "mpv", "--no-video", "--really-quiet", f"--volume={int(round(volume * 100))}", path,
    ]),
    ("ogg123", lambda path, volume: ["ogg123", "-q", path]),
    ("cvlc", lambda path, volume: ["cvlc", "--play-and-exit", "--intf", "dummy", path]),
    ("play", lambda path, volume: ["play", "-q", path]),
)


def clamp_volume(volume: float) -> float:
    """Clamp a volume into the 0.0 - 1.0 range."""
    try:
        return max(0.0, min(1.0, float(volume)))
    except (TypeError, ValueError):
        return DEFAULT_VOLUME


def asset_path(level: str) -> str | None:
    """Absolute path of the bundled cue for ``level``."""
    filename = ASSETS.get(level)
    if not filename:
        return None
    path = os.path.join(paths.sounds_dir(), filename)
    return path if os.path.isfile(path) else None


def find_player() -> str | None:
    """Name of the first installed audio player."""
    for name, _builder in PLAYERS:
        if shutil.which(name):
            return name
    return None


def build_argv(player: str, path: str, volume: float = DEFAULT_VOLUME) -> list[str]:
    """Command line used to play ``path`` with ``player``."""
    for name, builder in PLAYERS:
        if name == player:
            return list(builder(path, clamp_volume(volume)))
    return [player, path]


class SoundPlayer:
    """Plays the bundled alert cues."""

    def __init__(self) -> None:
        self.player = find_player()
        self.enabled = True
        self.volume = DEFAULT_VOLUME

    def path_for(self, level: str) -> str | None:
        """Path of the cue for ``level``."""
        return asset_path(level)

    def play(self, level: str) -> bool:
        """Play the cue for ``level``.  Never raises."""
        if not self.enabled:
            return False
        path = asset_path(level)
        if path is None:
            return False
        if not self.player:
            try:
                sys.stderr.write("\a")
                sys.stderr.flush()
            except Exception:
                pass
            return False
        try:
            subprocess.Popen(
                build_argv(self.player, path, self.volume),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError):
            return False
        return True
