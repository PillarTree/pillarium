"""Configuration model for Pillarium 2.0.

The on-disk format stays JSON so external editors (and the settings GUI)
can keep rewriting ``config.json`` while Pillarium is running.  Unknown
keys are preserved verbatim across a load/save round trip, which keeps
the file friendly to third-party tooling.

The :class:`Config` object is a thin, typed facade over that dictionary:
attributes are exposed as properties, and every mutation goes through
:meth:`Config.set` so a single change notification can be emitted.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from typing import Any

from . import paths

DEFAULT_HOTKEYS: dict[str, str] = {
    "launcher": "Alt+Space",
    "cycle_windows": "Alt+Tab",
    "close_window": "Alt+F4",
    "terminal": "Alt+Return",
    "theme_cycle": "Alt+Shift+D",
    "power_menu": "Alt+Shift+P",
    "wifi_menu": "Alt+Shift+W",
    "ethernet_menu": "Alt+Shift+E",
    "bluetooth_menu": "Alt+Shift+B",
    "audio_menu": "Alt+Shift+A",
    "processes": "Alt+Shift+M",
    "refresh_desktop": "Alt+Shift+R",
    "edit_quick_launch": "Alt+q",
    "next_desktop": "Ctrl+Alt+Right",
    "previous_desktop": "Ctrl+Alt+Left",
    "desktop_1": "Ctrl+Alt+1",
    "desktop_2": "Ctrl+Alt+2",
    "desktop_3": "Ctrl+Alt+3",
    "desktop_4": "Ctrl+Alt+4",
    "show_desktop": "Super+d",
}


def _default_config() -> dict[str, Any]:
    return {
        "theme": "dark",
        "wallpaper": "",
        "wallpapers": {},
        "quick_launch": [],
        "desktop_icons": [],
        "custom_widgets": [],
        "time_format": "%H:%M",
        "date_format": "%m/%d",
        "taskbar_override_redirect": True,
        "desktops": 4,
        "desktop_names": [],
        "taskbar": {
            "position": "bottom",
            "show_desktops": True,
            "show_clock": True,
            "show_battery": True,
            "show_wifi": True,
            "show_bluetooth": True,
            "show_audio": True,
            "show_ethernet": True,
            "show_power": True,
            "show_launcher": True,
            "show_quick_launch": True,
            "compact": False,
        },
        "monitors": {
            "taskbar_per_monitor": True,
            "primary_follows_pointer": False,
            "wallpaper_per_monitor": True,
            "placement": "pointer",
        },
        "focus": {
            "follows_mouse": False,
        },
        "launcher": {
            "max_results": 500,
            "include_desktop_icons": True,
            "include_quick_launch": True,
        },
        "alerts": {
            "enabled": True,
            "sound": True,
            "volume": 0.6,
            "startup": True,
            "warning": True,
            "error": True,
            "startup_timeout": 6.0,
            "warning_timeout": 0.0,
            "error_timeout": 0.0,
        },
        "hotkeys": dict(DEFAULT_HOTKEYS),
    }


def normalize_launch_items(raw: Any) -> list[dict[str, Any]]:
    """Coerce a ``quick_launch``/``desktop_icons`` list into dict form.

    Plain strings are accepted as a shorthand for ``["cmd", ...]`` and the
    label defaults to the basename of the executable.
    """
    normalized: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return normalized
    for item in raw:
        if isinstance(item, str):
            parts = item.split()
            if not parts:
                continue
            normalized.append({"cmd": parts, "label": os.path.basename(parts[0])})
        elif isinstance(item, dict) and item.get("cmd"):
            cmd = item["cmd"]
            parts = cmd.split() if isinstance(cmd, str) else list(cmd)
            if not parts:
                continue
            entry = {
                "cmd": parts,
                "label": item.get("label") or os.path.basename(parts[0]),
            }
            for optional in ("icon", "desktop_file", "path"):
                if item.get(optional) is not None:
                    entry[optional] = item[optional]
            normalized.append(entry)
    return normalized


class Config:
    """Typed access to ``config.json`` with live-reload support."""

    def __init__(self, data: dict[str, Any] | None = None):
        self._data = _default_config()
        if data:
            self._merge(self._data, data)
        self._mtime: float | None = None
        self._last_change = 0.0

    # -----------------------------------------------------------------
    # Loading / saving
    # -----------------------------------------------------------------
    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        """Read the configuration file, falling back to defaults."""
        cfg_path = path or paths.config_path()
        data: dict[str, Any] = {}
        try:
            with open(cfg_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        config = cls(data if isinstance(data, dict) else {})
        config._mtime = config._read_mtime(cfg_path)
        return config

    def save(self, path: str | None = None) -> bool:
        """Write the configuration back to disk atomically."""
        cfg_path = path or paths.config_path()
        try:
            directory = os.path.dirname(cfg_path) or "."
            os.makedirs(directory, exist_ok=True)
            handle, tmp = tempfile.mkstemp(prefix="config-", dir=directory)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, indent=2)
                stream.write("\n")
            os.replace(tmp, cfg_path)
        except OSError:
            return False
        self._mtime = self._read_mtime(cfg_path)
        return True

    @staticmethod
    def _read_mtime(path: str) -> float | None:
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    @staticmethod
    def _merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        """Recursively merge ``source`` into ``target``."""
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                Config._merge(target[key], value)
            else:
                target[key] = value

    # -----------------------------------------------------------------
    # Change detection
    # -----------------------------------------------------------------
    def poll_external_changes(self) -> bool:
        """Return ``True`` when the file changed on disk since last read."""
        mtime = self._read_mtime(paths.config_path())
        if mtime is None or mtime == self._mtime:
            return False
        self._mtime = mtime
        try:
            with open(paths.config_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        fresh = _default_config()
        self._merge(fresh, data)
        self._data = fresh
        return True

    def snapshot(self) -> dict[str, Any]:
        """A deep copy of the raw configuration dictionary."""
        return copy.deepcopy(self._data)

    def replace(self, data: dict[str, Any]) -> None:
        """Replace the whole configuration with ``data``."""
        fresh = _default_config()
        self._merge(fresh, data if isinstance(data, dict) else {})
        self._data = fresh

    # -----------------------------------------------------------------
    # Generic access
    # -----------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        """Set a top-level key and optionally persist the change."""
        self._data[key] = value
        self._last_change = time.time()
        if save:
            self.save()

    def section(self, name: str) -> dict[str, Any]:
        """Return a mutable sub-dictionary (created when missing)."""
        value = self._data.get(name)
        if not isinstance(value, dict):
            value = {}
            self._data[name] = value
        return value

    def opt(self, section: str, key: str, default: Any = None) -> Any:
        block = self._data.get(section)
        if isinstance(block, dict):
            return block.get(key, default)
        return default

    def set_opt(self, section: str, key: str, value: Any, *, save: bool = True) -> None:
        self.section(section)[key] = value
        self._last_change = time.time()
        if save:
            self.save()

    # -----------------------------------------------------------------
    # Convenience properties
    # -----------------------------------------------------------------
    @property
    def theme(self) -> str:
        return str(self._data.get("theme", "dark"))

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value)

    @property
    def wallpaper(self) -> str:
        return str(self._data.get("wallpaper", ""))

    @wallpaper.setter
    def wallpaper(self, value: str) -> None:
        self.set("wallpaper", value)

    @property
    def quick_launch(self) -> list[dict[str, Any]]:
        return normalize_launch_items(self._data.get("quick_launch"))

    @quick_launch.setter
    def quick_launch(self, value: list[dict[str, Any]]) -> None:
        self.set("quick_launch", value)

    @property
    def desktop_icons(self) -> list[dict[str, Any]]:
        return normalize_launch_items(self._data.get("desktop_icons"))

    @desktop_icons.setter
    def desktop_icons(self, value: list[dict[str, Any]]) -> None:
        self.set("desktop_icons", value)

    @property
    def custom_widgets(self) -> list[dict[str, Any]]:
        widgets = self._data.get("custom_widgets")
        return widgets if isinstance(widgets, list) else []

    @property
    def time_format(self) -> str:
        return str(self._data.get("time_format", "%H:%M"))

    @time_format.setter
    def time_format(self, value: str) -> None:
        self.set("time_format", value)

    @property
    def date_format(self) -> str:
        return str(self._data.get("date_format", "%m/%d"))

    @date_format.setter
    def date_format(self, value: str) -> None:
        self.set("date_format", value)

    @property
    def desktops(self) -> int:
        try:
            count = int(self._data.get("desktops", 4))
        except (TypeError, ValueError):
            count = 4
        return max(1, min(12, count))

    @desktops.setter
    def desktops(self, value: int) -> None:
        self.set("desktops", int(value))

    @property
    def desktop_names(self) -> list[str]:
        names = self._data.get("desktop_names")
        if isinstance(names, list):
            return [str(name) for name in names]
        return []

    @property
    def hotkeys(self) -> dict[str, str]:
        block = self._data.get("hotkeys")
        merged = dict(DEFAULT_HOTKEYS)
        if isinstance(block, dict):
            for key, value in block.items():
                if isinstance(value, str):
                    merged[key] = value
        return merged

    @property
    def alerts(self) -> dict[str, Any]:
        block = self._data.get("alerts")
        merged = _default_config()["alerts"]
        if isinstance(block, dict):
            merged.update(block)
        return merged

    @property
    def taskbar(self) -> dict[str, Any]:
        block = self._data.get("taskbar")
        merged = _default_config()["taskbar"]
        if isinstance(block, dict):
            merged.update(block)
        return merged

    @property
    def monitors(self) -> dict[str, Any]:
        block = self._data.get("monitors")
        merged = _default_config()["monitors"]
        if isinstance(block, dict):
            merged.update(block)
        return merged

    @property
    def launcher(self) -> dict[str, Any]:
        block = self._data.get("launcher")
        merged = _default_config()["launcher"]
        if isinstance(block, dict):
            merged.update(block)
        return merged

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------
    def desktop_label(self, index: int) -> str:
        """Human readable name of virtual desktop ``index``."""
        names = self.desktop_names
        if 0 <= index < len(names) and names[index]:
            return names[index]
        return f"Desktop {index + 1}"

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Config theme={self.theme!r} desktops={self.desktops}>"
