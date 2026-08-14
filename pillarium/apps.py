"""Application catalog and desktop-folder scanning."""

import os
import subprocess
import sys

from . import paths


class AppMixin:
    # -----------------------------------------------------------------
    # Desktop‑icon handling
    # -----------------------------------------------------------------
    def _find_desktop_folder(self):
        # PILLARIUM_DESKTOP lets users point at any desktop directory.
        override = paths.desktop_dir()
        if override:
            if os.path.isdir(override):
                return override
            print(
                f"Pillarium: PILLARIUM_DESKTOP points to a missing folder: {override}",
                file=sys.stderr,
            )
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
        except Exception:
            pass
        candidate = os.path.expanduser("~/Desktop")
        if os.path.isdir(candidate):
            return candidate
        return None

    def _parse_desktop_entry(self, path):
        try:
            values = {}
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key in ("Name", "Exec", "Icon", "Type", "NoDisplay", "Hidden", "StartupWMClass"):
                        values.setdefault(key, value.strip())

            if values.get("Type", "Application") != "Application":
                return None
            if values.get("Hidden", "").lower() == "true":
                return None
            name = values.get("Name")
            exec_line = values.get("Exec")
            if not name or not exec_line:
                return None

            import shlex

            cleaned = []
            for tok in shlex.split(exec_line):
                if tok.startswith("%"):
                    continue
                tok = tok.replace("%%", "%")
                if tok:
                    cleaned.append(tok)
            if not cleaned:
                return None

            return {
                "label": name,
                "cmd": cleaned,
                "icon": values.get("Icon"),
                "desktop_file": path,
                "startup_wm_class": values.get("StartupWMClass"),
            }
        except Exception:
            return None

    def _application_dirs(self):
        dirs = []

        data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser(
            "~/.local/share"
        )
        dirs.append(os.path.join(os.path.expanduser(data_home), "applications"))

        data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
        for base in data_dirs.split(":"):
            if base:
                dirs.append(os.path.join(os.path.expanduser(base), "applications"))

        dirs.extend(
            [
                os.path.expanduser(
                    "~/.local/share/flatpak/exports/share/applications"
                ),
                "/var/lib/flatpak/exports/share/applications",
                "/var/lib/snapd/desktop/applications",
                "/usr/share/applications",
                "/usr/local/share/applications",
            ]
        )

        result = []
        seen = set()
        for d in dirs:
            d = os.path.abspath(os.path.expanduser(d))
            if d not in seen and os.path.isdir(d):
                seen.add(d)
                result.append(d)
        return result

    def _scan_applications(self, limit=2000):
        apps = []
        seen_files = set()
        seen_keys = set()

        for app_dir in self._application_dirs():
            try:
                walker = os.walk(app_dir)
                for root, _dirs, files in walker:
                    for entry in sorted(files, key=str.lower):
                        if not entry.lower().endswith(".desktop"):
                            continue
                        path = os.path.abspath(os.path.join(root, entry))
                        if path in seen_files:
                            continue
                        seen_files.add(path)

                        parsed = self._parse_desktop_entry(path)
                        if not parsed:
                            continue

                        desktop_id = entry[:-8].strip().lower()
                        label_key = parsed.get("label", "").strip().lower()
                        key = desktop_id or label_key
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        apps.append(parsed)

                        if len(apps) >= limit:
                            return sorted(apps, key=lambda x: x.get("label", "").lower())
            except Exception as exc:
                print(
                    f"Pillarium: application scan failed for {app_dir}: {exc}",
                    file=sys.stderr,
                )

        print(
            f"Pillarium: application catalog contains {len(apps)} applications",
            file=sys.stderr,
        )
        return sorted(apps, key=lambda x: x.get("label", "").lower())

    def _refresh_applications(self):
        self.applications = self._scan_applications()
        self._enrich_launcher_icons()
        if getattr(self, "search_state", None):
            self._update_search_results()
            self._redraw_search()

    def _enrich_launcher_icons(self):
        apps = getattr(self, "applications", []) or []
        by_name = {}
        by_cmd = {}
        by_file = {}
        for app in apps:
            icon = app.get("icon")
            if not icon:
                continue
            label = str(app.get("label", "")).strip().lower()
            if label:
                by_name[label] = app
            cmd = app.get("cmd") or []
            if cmd:
                full = str(cmd[0]).lower()
                by_cmd[full] = app
                by_cmd[os.path.basename(full)] = app
            df = app.get("desktop_file")
            if df:
                by_file[os.path.splitext(os.path.basename(df))[0].lower()] = app

        special = {"steam": "steam"}
        changed = False
        for collection in (
            getattr(self, "desktop_icons", []),
            getattr(self, "quick_launch", []),
        ):
            for item in collection:
                if not isinstance(item, dict) or item.get("icon"):
                    continue
                label = str(item.get("label", "")).strip().lower()
                cmd = item.get("cmd") or []
                exe = os.path.basename(str(cmd[0])).lower() if cmd else ""
                app = (
                    by_name.get(label)
                    or by_cmd.get(exe)
                    or by_cmd.get(str(cmd[0]).lower() if cmd else None)
                )
                if app is None and label in special:
                    app = {"icon": special[label]}
                if app and app.get("icon"):
                    item["icon"] = app["icon"]
                    if app.get("desktop_file"):
                        item["desktop_file"] = app["desktop_file"]
                    changed = True
                    print(
                        f"Pillarium: launcher '{item.get('label', '')}' -> icon '{item['icon']}'",
                        file=sys.stderr,
                    )
        return changed

    def _scan_desktop_folder(self, limit=40):
        icons = []
        desktop_dir = self._find_desktop_folder()
        if not desktop_dir:
            return icons
        try:
            entries = sorted(os.listdir(desktop_dir), key=str.lower)
        except Exception as exc:
            print(
                f"Pillarium: could not list {desktop_dir}: {exc}",
                file=sys.stderr,
            )
            return icons
        for entry in entries:
            if entry.startswith("."):
                continue
            full_path = os.path.join(desktop_dir, entry)
            label = entry
            cmd = None
            icon = None
            if entry.lower().endswith(".desktop"):
                parsed = self._parse_desktop_entry(full_path)
                if parsed:
                    label = parsed.get("label", entry)
                    cmd = parsed.get("cmd")
                    icon = parsed.get("icon")
            if cmd is None:
                if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                    cmd = [full_path]
                else:
                    cmd = ["xdg-open", full_path]
                if not os.path.isdir(full_path):
                    base, ext = os.path.splitext(entry)
                    if ext:
                        label = base
            icons.append(
                {
                    "cmd": cmd,
                    "label": label[:24],
                    "icon": icon,
                    "path": full_path,
                }
            )
            if len(icons) >= limit:
                break
        print(
            f"Pillarium: found {len(icons)} item(s) in {desktop_dir}",
            file=sys.stderr,
        )
        return icons

    def _refresh_desktop_icons(self):
        if not getattr(self, "desktop_icons_from_config", False):
            scanned = self._scan_desktop_folder()
            if scanned:
                self.desktop_icons = scanned
                self._enrich_launcher_icons()
        self._desktop_selected = None
        self._redraw_desktop_icons()

    def _init_apps(self):
        # Fallback: scan ~/Desktop if config.json didn't provide icons
        if not self.desktop_icons_from_config:
            try:
                scanned = self._scan_desktop_folder()
                if scanned:
                    self.desktop_icons = scanned
            except Exception as exc:
                print(
                    f"Pillarium: desktop folder scan failed: {exc}",
                    file=sys.stderr,
                )

        # Application catalog (everything that has a .desktop file)
        self.applications = self._scan_applications()
        self._enrich_launcher_icons()
