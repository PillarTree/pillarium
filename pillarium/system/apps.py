"""Application catalogue: parsing ``.desktop`` entries and XDG lookups."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .. import paths


@dataclass
class Application:
    """A single launchable application."""

    label: str
    cmd: list[str] = field(default_factory=list)
    icon: str | None = None
    desktop_file: str | None = None
    startup_wm_class: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "cmd": list(self.cmd),
            "icon": self.icon,
            "desktop_file": self.desktop_file,
            "path": self.path,
        }


class ApplicationCatalog:
    """Scans the XDG application directories for launchable entries."""

    def __init__(self) -> None:
        self.applications: list[Application] = []
        self.desktop_icons: list[dict[str, Any]] = []

    # -----------------------------------------------------------------
    # Directories
    # -----------------------------------------------------------------
    @staticmethod
    def application_dirs() -> list[str]:
        """Every directory that may hold ``.desktop`` files."""
        candidates: list[str] = []
        data_home = os.environ.get("XDG_DATA_HOME") or os.path.join("~", ".local", "share")
        candidates.append(os.path.join(os.path.expanduser(data_home), "applications"))
        data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
        for entry in data_dirs.split(":"):
            if entry:
                candidates.append(os.path.join(entry, "applications"))
        home = os.path.expanduser("~")
        candidates.extend(
            [
                os.path.join(home, ".local", "share", "flatpak", "exports", "share", "applications"),
                os.path.join("/var", "lib", "flatpak", "exports", "share", "applications"),
                os.path.join("/var", "lib", "snapd", "desktop", "applications"),
                os.path.join("/usr", "share", "applications"),
                os.path.join("/usr", "local", "share", "applications"),
            ]
        )
        seen: set[str] = set()
        unique: list[str] = []
        for path in candidates:
            resolved = os.path.abspath(os.path.expanduser(path))
            if resolved in seen:
                continue
            seen.add(resolved)
            if os.path.isdir(resolved):
                unique.append(resolved)
        return unique

    # -----------------------------------------------------------------
    # Parsing
    # -----------------------------------------------------------------
    @staticmethod
    def parse_desktop_entry(path: str) -> Application | None:
        """Parse a ``.desktop`` file, returning ``None`` when not launchable."""
        values: dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    values[key.strip()] = value.strip()
        except OSError:
            return None

        if values.get("Type", "Application") != "Application":
            return None
        if values.get("Hidden", "false").lower() == "true":
            return None
        if values.get("NoDisplay", "false").lower() == "true":
            return None
        name = values.get("Name")
        exec_line = values.get("Exec")
        if not name or not exec_line:
            return None

        try:
            cmd = shlex.split(exec_line)
        except ValueError:
            cmd = exec_line.split()
        cleaned: list[str] = []
        for token in cmd:
            if token.startswith("%"):
                if token == "%%":
                    cleaned.append("%")
                continue
            cleaned.append(token)
        if not cleaned:
            return None

        return Application(
            label=name,
            cmd=cleaned,
            icon=values.get("Icon") or None,
            desktop_file=path,
            startup_wm_class=values.get("StartupWMClass") or None,
        )

    # -----------------------------------------------------------------
    # Scanning
    # -----------------------------------------------------------------
    def scan(self, limit: int = 4000) -> list[Application]:
        """Rebuild the catalogue from disk and return the applications."""
        found: dict[str, Application] = {}
        seen_ids: set[str] = set()
        for directory in self.application_dirs():
            for root, dirnames, filenames in os.walk(directory):
                dirnames[:] = [name for name in dirnames if name not in (".git", "cache", "caches")]
                for filename in filenames:
                    if not filename.lower().endswith(".desktop"):
                        continue
                    path = os.path.join(root, filename)
                    real = os.path.realpath(path)
                    if real in seen_ids:
                        continue
                    seen_ids.add(real)
                    app = self.parse_desktop_entry(path)
                    if app is None:
                        continue
                    key = os.path.basename(path)[:-8].lower()
                    found.setdefault(key, app)
                    if len(found) >= limit:
                        break
                if len(found) >= limit:
                    break
            if len(found) >= limit:
                break
        self.applications = sorted(found.values(), key=lambda app: app.label.lower())
        return self.applications

    # -----------------------------------------------------------------
    # Desktop folder
    # -----------------------------------------------------------------
    @staticmethod
    def find_desktop_folder() -> str | None:
        """Locate the user's desktop folder."""
        override = paths.desktop_dir()
        if override and os.path.isdir(override):
            return override
        try:
            result = subprocess.run(
                ["xdg-user-dir", "DESKTOP"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                candidate = result.stdout.strip()
                if candidate and os.path.isdir(candidate):
                    return candidate
        except (OSError, subprocess.SubprocessError):
            pass
        fallback = os.path.join(os.path.expanduser("~"), "Desktop")
        return fallback if os.path.isdir(fallback) else None

    def scan_desktop_folder(self, limit: int = 60) -> list[dict[str, Any]]:
        """Build desktop icon entries from the desktop folder."""
        folder = self.find_desktop_folder()
        if not folder:
            return []
        try:
            names = sorted(
                (name for name in os.listdir(folder) if not name.startswith(".")),
                key=str.lower,
            )
        except OSError:
            return []

        icons: list[dict[str, Any]] = []
        for name in names[:limit]:
            path = os.path.join(folder, name)
            if name.lower().endswith(".desktop"):
                app = self.parse_desktop_entry(path)
                if app is None:
                    continue
                icons.append(
                    {
                        "cmd": list(app.cmd),
                        "label": app.label[:24],
                        "icon": app.icon,
                        "desktop_file": path,
                        "path": path,
                    }
                )
                continue
            if os.path.isdir(path):
                cmd = ["xdg-open", path]
            elif os.access(path, os.X_OK):
                cmd = [path]
            else:
                cmd = ["xdg-open", path]
            icons.append(
                {
                    "cmd": cmd,
                    "label": os.path.splitext(name)[0][:24],
                    "icon": None,
                    "desktop_file": None,
                    "path": path,
                }
            )
        return icons
