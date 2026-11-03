"""Launching applications and resolving their icons."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from .apps import ApplicationCatalog

ICON_EXTENSIONS = (".png", ".svg", ".xpm", ".jpg", ".jpeg", ".webp")


class Launcher:
    """Starts applications and keeps track of quick-launch items."""

    def __init__(self, catalog: ApplicationCatalog | None = None):
        self.catalog = catalog or ApplicationCatalog()

    # -----------------------------------------------------------------
    # Launching
    # -----------------------------------------------------------------
    @staticmethod
    def launch(cmd: list[str] | str) -> bool:
        """Start ``cmd`` detached from the session.  Never raises."""
        if isinstance(cmd, str):
            cmd = cmd.split()
        if not cmd:
            return False
        try:
            subprocess.Popen(
                list(cmd),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError):
            return False
        return True

    def launch_terminal(self, command: str = "xterm") -> bool:
        return self.launch([command])

    # -----------------------------------------------------------------
    # Icon resolution
    # -----------------------------------------------------------------
    @staticmethod
    def icon_search_dirs() -> list[str]:
        """Directories scanned for icon themes."""
        candidates = [
            os.path.join(os.path.expanduser("~"), ".local", "share", "icons"),
            os.path.join(os.path.expanduser("~"), ".icons"),
            os.path.join("/usr", "share", "icons"),
            os.path.join("/usr", "local", "share", "icons"),
            os.path.join("/usr", "share", "pixmaps"),
            os.path.join("/usr", "local", "share", "pixmaps"),
        ]
        data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
        for entry in data_dirs.split(":"):
            if entry:
                candidates.append(os.path.join(entry, "icons"))
        seen: set[str] = set()
        result: list[str] = []
        for path in candidates:
            resolved = os.path.abspath(os.path.expanduser(path))
            if resolved in seen or not os.path.isdir(resolved):
                continue
            seen.add(resolved)
            result.append(resolved)
        return result

    def find_icon_file(self, icon_name: str | None) -> str | None:
        """Resolve an icon name or path to a file on disk."""
        if not icon_name:
            return None
        if os.path.isabs(icon_name) and os.path.isfile(icon_name):
            return icon_name

        stem = os.path.splitext(os.path.basename(icon_name))[0]
        for base in self.icon_search_dirs():
            for extension in ICON_EXTENSIONS:
                candidate = os.path.join(base, f"{stem}{extension}")
                if os.path.isfile(candidate):
                    return candidate
            for root, dirnames, filenames in os.walk(base):
                dirnames[:] = [name for name in dirnames if name not in (".git", "cache", "caches")]
                for filename in filenames:
                    if filename.lower() == f"{stem}.png":
                        return os.path.join(root, filename)
        return None

    # -----------------------------------------------------------------
    # Quick-launch enrichment
    # -----------------------------------------------------------------
    def enrich(self, items: list[dict[str, Any]]) -> bool:
        """Fill in missing icons for quick-launch / desktop entries.

        Returns ``True`` when at least one entry was changed.
        """
        by_label: dict[str, dict[str, Any]] = {}
        by_command: dict[str, dict[str, Any]] = {}
        by_basename: dict[str, dict[str, Any]] = {}
        by_desktop: dict[str, dict[str, Any]] = {}
        for app in self.catalog.applications:
            payload = {
                "icon": app.icon,
                "desktop_file": app.desktop_file,
                "cmd": list(app.cmd),
            }
            by_label.setdefault(app.label.lower(), payload)
            if app.cmd:
                by_command.setdefault(app.cmd[0].lower(), payload)
                by_basename.setdefault(os.path.basename(app.cmd[0]).lower(), payload)
            if app.desktop_file:
                by_desktop.setdefault(os.path.basename(app.desktop_file).lower(), payload)

        changed = False
        for item in items:
            if item.get("icon"):
                continue
            cmd = item.get("cmd") or []
            payload = None
            label = str(item.get("label", "")).lower()
            if label in by_label:
                payload = by_label[label]
            elif cmd:
                if cmd[0].lower() in by_command:
                    payload = by_command[cmd[0].lower()]
                elif os.path.basename(cmd[0]).lower() in by_basename:
                    payload = by_basename[os.path.basename(cmd[0]).lower()]
            if payload is None:
                desktop_file = item.get("desktop_file")
                if desktop_file:
                    payload = by_desktop.get(os.path.basename(desktop_file).lower())
            if payload and payload.get("icon"):
                item["icon"] = payload["icon"]
                changed = True
            if payload and not item.get("desktop_file") and payload.get("desktop_file"):
                item["desktop_file"] = payload["desktop_file"]
        return changed

    # -----------------------------------------------------------------
    # Wallpaper helpers
    # -----------------------------------------------------------------
    @staticmethod
    def wallpaper_backends() -> list[str]:
        """External wallpaper setters, most preferred first."""
        available: list[str] = []
        for tool, args in (
            ("feh", ["--no-fehbg", "--bg-fill"]),
            ("nitrogen", ["--set-zoom-fill"]),
            ("hsetroot", ["-full"]),
        ):
            if shutil.which(tool):
                available.append(tool)
        return available
