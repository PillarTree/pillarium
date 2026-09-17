"""Config loading / saving.  The config file lives at a variable
location resolved by :mod:`pillarium.paths` (PILLARIUM_HOME /
PILLARIUM_CONFIG)."""

import json
import os
import subprocess
import sys
import tempfile

from . import paths


def normalize_launch_items(raw):
    normalized = []
    for it in raw:
        if isinstance(it, str):
            normalized.append(
                {
                    "cmd": it.split(),
                    "label": os.path.basename(it.split()[0]),
                }
            )
        elif isinstance(it, dict) and "cmd" in it:
            cmd = it["cmd"]
            if isinstance(cmd, str):
                cmd_list = cmd.split()
            else:
                cmd_list = list(cmd)
            if not cmd_list:
                continue
            normalized.append(
                {
                    "cmd": cmd_list,
                    "label": it.get(
                        "label",
                        os.path.basename(cmd_list[0]),
                    ),
                    "icon": it.get("icon"),
                    "desktop_file": it.get("desktop_file"),
                    "path": it.get("path"),
                }
            )
    return normalized


class ConfigMixin:
    def _init_config(self):
        # -----------------------------------------------------------------
        # Wallpaper handling (variable location)
        # -----------------------------------------------------------------
        self.wallpaper_path = paths.wallpaper_path()
        self._wallpaper_process = None

        # -----------------------------------------------------------------
        # Quick‑launch, desktop icons, custom widgets
        # -----------------------------------------------------------------
        self.taskbar_override = True
        self.quick_launch = [{"cmd": ["xterm"], "label": "xterm"}]
        self.desktop_icons = [{"cmd": ["xterm"], "label": "Terminal"}]
        self.custom_widgets = []
        self.desktop_icons_from_config = False
        self.time_format = "%H:%M"
        self.date_format = "%m/%d"
        # Alert settings are applied later, once the alert subsystem exists.
        self._alerts_cfg = {}

        self._load_config()
        # Re-apply the palette so a "theme" set in config.json wins over
        # the PILLARIUM_LIGHT environment default picked in _init_theme.
        try:
            self._apply_palette()
        except Exception:
            pass
        self._config_mtime = self._config_file_mtime()
        self._config_snapshot = None
        self._last_config_check = 0.0
        self._set_wallpaper()

    def _config_file_mtime(self):
        try:
            return os.path.getmtime(paths.config_path())
        except OSError:
            return None

    def _load_config(self):
        cfg_path = paths.config_path()
        desktop_icons_from_config = False
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, "r") as f:
                    cfg = json.load(f)

                self.taskbar_override = bool(
                    cfg.get("taskbar_override_redirect", True)
                )

                wp = cfg.get("wallpaper")
                if isinstance(wp, str) and wp:
                    self.wallpaper_path = os.path.expanduser(wp)

                ql = cfg.get("quick_launch")
                if isinstance(ql, list) and ql:
                    normalized = normalize_launch_items(ql)
                    if normalized:
                        self.quick_launch = normalized

                di = cfg.get("desktop_icons")
                if isinstance(di, list) and di:
                    normalized_di = normalize_launch_items(di)
                    if normalized_di:
                        self.desktop_icons = normalized_di
                        desktop_icons_from_config = True

                cw = cfg.get("custom_widgets")
                if isinstance(cw, list) and cw:
                    normalized_cw = []
                    for it in cw:
                        if not isinstance(it, dict):
                            continue
                        cmd = it.get("cmd")
                        if not cmd:
                            continue
                        cmd_list = (
                            cmd.split() if isinstance(cmd, str) else cmd
                        )
                        action_cmd = it.get("action_cmd")
                        if isinstance(action_cmd, str):
                            action_cmd = action_cmd.split()
                        normalized_cw.append(
                            {
                                "label": it.get("label", "Widget"),
                                "cmd": cmd_list,
                                "interval": float(it.get("interval", 5.0)),
                                "action_cmd": action_cmd,
                                "text": "",
                                "last_poll": 0.0,
                            }
                        )
                    if normalized_cw:
                        self.custom_widgets = normalized_cw

                tf = cfg.get("time_format")
                if isinstance(tf, str) and tf:
                    self.time_format = tf
                df = cfg.get("date_format")
                if isinstance(df, str) and df:
                    self.date_format = df

                theme = cfg.get("theme")
                if isinstance(theme, str) and theme:
                    self.theme_mode = theme.strip().lower()
                    if self.theme_mode not in ("dark", "light", "retro"):
                        self.theme_mode = "dark"
                    self.dark_mode = self.theme_mode != "light"

                alerts = cfg.get("alerts")
                if isinstance(alerts, dict):
                    self._alerts_cfg = dict(alerts)
        except Exception:
            pass

        self.desktop_icons_from_config = desktop_icons_from_config

    # -----------------------------------------------------------------
    # Live reload (picked up by the run loop when another process, such
    # as Planet Control Center, rewrites config.json)
    # -----------------------------------------------------------------
    def _maybe_reload_config(self):
        """Reload config.json if it changed on disk.

        Returns True when the file was re-read, in which case the caller
        should invoke :meth:`_apply_reloaded_config`.
        """
        mtime = self._config_file_mtime()
        if mtime is None or mtime == getattr(self, "_config_mtime", None):
            return False
        self._config_mtime = mtime
        self._config_snapshot = {
            "theme_mode": getattr(self, "theme_mode", None),
            "wallpaper_path": getattr(self, "wallpaper_path", None),
            "quick_launch": list(getattr(self, "quick_launch", [])),
            "desktop_icons": list(getattr(self, "desktop_icons", [])),
            "time_format": getattr(self, "time_format", None),
            "date_format": getattr(self, "date_format", None),
            "taskbar_override": getattr(self, "taskbar_override", None),
        }
        self._load_config()
        self._apply_palette()
        return True

    def _apply_reloaded_config(self):
        """Apply the differences picked up by :meth:`_maybe_reload_config`.

        Returns True when a taskbar / desktop repaint is warranted.
        """
        snap = getattr(self, "_config_snapshot", None)
        if not snap:
            return False
        self._config_snapshot = None

        # Keep alert preferences in sync with config.json edits.
        alerts_cfg = getattr(self, "_alerts_cfg", {}) or {}
        if hasattr(self, "_sounds"):
            try:
                self._sounds.enabled = bool(alerts_cfg.get("sound", True))
                self._sounds.volume = float(alerts_cfg.get("volume", 0.6))
            except Exception:
                pass
        try:
            self.alerts_enabled = bool(alerts_cfg.get("enabled", True))
        except Exception:
            pass

        if self.theme_mode != snap["theme_mode"]:
            self.set_theme_mode(self.theme_mode)
            return True

        if self.wallpaper_path != snap["wallpaper_path"]:
            try:
                self._set_wallpaper()
            except Exception:
                pass

        if (
            self.quick_launch != snap["quick_launch"]
            or self.desktop_icons != snap["desktop_icons"]
            or self.time_format != snap["time_format"]
            or self.date_format != snap["date_format"]
        ):
            return True
        return False

    # -----------------------------------------------------------------
    # Save config.json (quick‑launch + theme)
    # -----------------------------------------------------------------
    def _save_config(self):
        try:
            cfg_path = paths.config_path()
            cur = {}
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r") as f:
                        cur = json.load(f)
                except Exception:
                    cur = {}
            cur["quick_launch"] = self.quick_launch
            cur["desktop_icons"] = self.desktop_icons
            cur["wallpaper"] = self.wallpaper_path
            cur["theme"] = getattr(self, "theme_mode", "dark")
            cur["taskbar_override_redirect"] = bool(self.taskbar_override)
            cur["time_format"] = self.time_format
            cur["date_format"] = self.date_format
            # atomic write
            dirn = os.path.dirname(cfg_path)
            fd, tmp = tempfile.mkstemp(prefix="config-", dir=dirn)
            with os.fdopen(fd, "w") as f:
                json.dump(cur, f, indent=2)
            os.replace(tmp, cfg_path)
        except Exception as e:
            print(f"Failed to save config: {e}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Open quick‑launch config editor (xdg-open or xterm+nano)
    # -----------------------------------------------------------------
    def _open_quicklaunch_editor(self):
        cfg_path = paths.config_path()
        try:
            subprocess.Popen(
                ["xdg-open", cfg_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
        try:
            subprocess.Popen(["xterm", "-e", "nano", cfg_path])
        except Exception as e:
            print(f"Could not launch editor for quick‑launch: {e}", file=sys.stderr)
