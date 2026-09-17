"""Alert chimes and best-effort playback for Pillarium.

The three chimes ship as Ogg Vorbis files next to this module in
``pillarium/sounds``:

    startup.ogg   played when Pillarium starts
    warn.ogg      played for warning alerts
    error.ogg     played for error alerts

Playback goes through the first Ogg-capable command line player that is
installed (PipeWire / PulseAudio / ffmpeg / mpv / vorbis-tools / SoX).  If
none is available the terminal bell is used as a last resort.  Playback is
always best-effort: it never raises and never blocks the window manager.
"""

import os
import shutil
import subprocess
import sys

DEFAULT_VOLUME = 0.6

_SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

# Alert level -> bundled asset file name.
_ASSETS = {
    "startup": "startup.ogg",
    "warning": "warn.ogg",
    "error": "error.ogg",
}


def _clamp(volume):
    try:
        return max(0.0, min(1.0, float(volume)))
    except Exception:
        return DEFAULT_VOLUME


def asset_path(level):
    """Return the path to the bundled chime for *level*, or None."""
    name = _ASSETS.get(level)
    if not name:
        return None
    path = os.path.join(_SOUND_DIR, name)
    return path if os.path.exists(path) else None


def _pct(volume):
    return int(round(_clamp(volume) * 100))


# Player commands, in order of preference.  Each entry maps the executable
# name to a function building the argv for a given file path and volume.
_PLAYERS = (
    (
        "paplay",
        lambda p, v: ["paplay", "--volume=%d" % int(round(_clamp(v) * 65536)), p],
    ),
    ("pw-play", lambda p, v: ["pw-play", "--volume=%.3f" % _clamp(v), p]),
    (
        "ffplay",
        lambda p, v: [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "quiet",
            "-volume",
            str(_pct(v)),
            p,
        ],
    ),
    ("mpv", lambda p, v: ["mpv", "--no-video", "--really-quiet", "--volume=%d" % _pct(v), p]),
    ("ogg123", lambda p, v: ["ogg123", "-q", p]),
    ("cvlc", lambda p, v: ["cvlc", "--play-and-exit", "--intf", "dummy", p]),
    ("play", lambda p, v: ["play", "-q", p]),
)


def find_player():
    """Return the name of the first available Ogg-capable player, or None."""
    for name, _builder in _PLAYERS:
        if shutil.which(name):
            return name
    return None


def build_argv(player, path, volume=DEFAULT_VOLUME):
    """Build the argv used to play *path* with *player* at *volume*."""
    for name, builder in _PLAYERS:
        if name == player:
            return builder(path, volume)
    return [player, path]


class SoundPlayer:
    """Plays the bundled alert chimes (best-effort, non-blocking)."""

    def __init__(self):
        self.player = find_player()
        self.enabled = True
        self.volume = DEFAULT_VOLUME

    def path_for(self, level, home=None):
        """Return the bundled asset path for *level* (or None)."""
        return asset_path(level)

    def play(self, level, home=None):
        """Play the chime for *level*.  Never raises, never blocks."""
        if not self.enabled:
            return
        path = asset_path(level)
        if not path:
            return
        if self.player:
            try:
                subprocess.Popen(
                    build_argv(self.player, path, self.volume),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass
        # Last resort: the terminal bell.
        try:
            sys.stderr.write("\a")
            sys.stderr.flush()
        except Exception:
            pass
