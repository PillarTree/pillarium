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
        self._set_wallpaper()

        # -----------------------------------------------------------------
        # Quick‑launch, desktop icons, custom widgets
        # -----------------------------------------------------------------
        self.taskbar_override = True
        self.quick_launch = [{"cmd": ["xterm"], "label": "xterm"}]
        self.desktop_icons = [{"cmd": ["xterm"], "label": "Terminal"}]
        self.custom_widgets = []
        self.desktop_icons_from_config = False

        self._load_config()

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
        except Exception:
            pass

        self.desktop_icons_from_config = desktop_icons_from_config

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
            cur["theme"] = "dark" if self.dark_mode else "light"
            cur["taskbar_override_redirect"] = bool(self.taskbar_override)
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
