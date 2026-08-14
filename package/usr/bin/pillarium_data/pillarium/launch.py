"""Process launching, wallpaper setup and custom widgets."""

import os
import shutil
import subprocess
import sys
import time


class LaunchMixin:
    # -----------------------------------------------------------------
    # Wallpaper handling (variable location, resolved via paths)
    # -----------------------------------------------------------------
    def _set_wallpaper(self):
        path = os.path.expanduser(getattr(self, "wallpaper_path", ""))
        if not path or not os.path.isfile(path):
            print(
                f"Pillarium: wallpaper not found: {path}",
                file=sys.stderr,
            )
            return False
        backends = []
        if shutil.which("feh"):
            backends.append(["feh", "--no-fehbg", "--bg-fill", path])
        if shutil.which("nitrogen"):
            backends.append(["nitrogen", "--set-zoom-fill", path])
        if shutil.which("hsetroot"):
            backends.append(["hsetroot", "-full", path])
        display = shutil.which("display") or "/opt/imagemagick/bin/display"
        if os.path.exists(display):
            backends.append([display, "-window", "root", path])
        for cmd in backends:
            try:
                if cmd[0].endswith("display"):
                    self._wallpaper_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=None,
                        start_new_session=True,
                    )
                    time.sleep(0.2)
                    if self._wallpaper_process.poll() is None:
                        print(
                            f"Pillarium: wallpaper loaded with {cmd[0]}",
                            file=sys.stderr,
                        )
                        return True
                else:
                    r = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=None,
                        timeout=8,
                    )
                    if r.returncode == 0:
                        print(
                            f"Pillarium: wallpaper loaded with {cmd[0]}",
                            file=sys.stderr,
                        )
                        return True
            except Exception as exc:
                print(
                    f"Pillarium: wallpaper backend {cmd[0]} failed: {exc}",
                    file=sys.stderr,
                )
        print(
            "Pillarium: no working wallpaper backend found.", file=sys.stderr
        )
        return False

    # -----------------------------------------------------------------
    # Process Launching & System Integrations
    # -----------------------------------------------------------------
    def _poll_custom_widgets(self):
        return False

    def _custom_widget_action(self, idx):
        if 0 <= idx < len(self.custom_widgets):
            cmd = self.custom_widgets[idx].get("action_cmd")
            if cmd:
                self._launch_command(cmd)

    def _launch_command(self, cmd):
        if not cmd:
            return
        try:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as exc:
            print(f"Pillarium: Failed to launch command {cmd}: {exc}", file=sys.stderr)

    def _launch_terminal(self):
        self._launch_command(["xterm"])
