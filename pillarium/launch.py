"""Process launching, wallpaper setup and custom widgets."""

import os
import shutil
import subprocess
import sys
import time

from . import paths


class LaunchMixin:
    # -----------------------------------------------------------------
    # Wallpaper handling (variable location, resolved via paths)
    # -----------------------------------------------------------------
    def _set_wallpaper(self):
        if getattr(self, "_wallpaper_process", None):
            try:
                self._wallpaper_process.terminate()
            except Exception:
                pass
            self._wallpaper_process = None
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
        ok = False
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
                        ok = True
                        break
                else:
                    r = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=None,
                        timeout=30,
                    )
                    if r.returncode == 0:
                        print(
                            f"Pillarium: wallpaper loaded with {cmd[0]}",
                            file=sys.stderr,
                        )
                        ok = True
                        break
            except Exception as exc:
                print(
                    f"Pillarium: wallpaper backend {cmd[0]} failed: {exc}",
                    file=sys.stderr,
                )
        # Paint the wallpaper as the desktop-window background so it is
        # visible even without a compositor (the desktop window otherwise
        # covers the root pixmap with black).
        if self._apply_wallpaper_to_desktop():
            ok = True
        if not ok:
            print(
                "Pillarium: no working wallpaper backend found.",
                file=sys.stderr,
            )
        return ok

    def _apply_wallpaper_to_desktop(self, win=None):
        """Fill the desktop window with the wallpaper (cover-cropped)."""
        if win is None:
            win = getattr(self, "desktop_win", None)
        if win is None:
            return False
        path = os.path.expanduser(getattr(self, "wallpaper_path", ""))
        if not path or not os.path.isfile(path):
            return False
        try:
            from PIL import Image

            sw, sh = self.screen_w, self.screen_h
            try:
                img = Image.open(path).convert("RGB")
            except Exception:
                # Pillow cannot decode SVG; rasterize it with cairosvg.
                if path.lower().endswith(".svg"):
                    import cairosvg
                    from io import BytesIO

                    svg_w, svg_h = 0, 0
                    try:
                        import xml.etree.ElementTree as ET

                        root_el = ET.parse(path).getroot()
                        svg_w = int(float(root_el.get("width", 0)))
                        svg_h = int(float(root_el.get("height", 0)))
                    except Exception:
                        pass
                    if svg_w <= 0 or svg_h <= 0:
                        svg_w, svg_h = 1920, 1080
                    scale = max(sw / svg_w, sh / svg_h)
                    out_w = max(1, round(svg_w * scale))
                    out_h = max(1, round(svg_h * scale))
                    png = cairosvg.svg2png(
                        url=path, output_width=out_w, output_height=out_h
                    )
                    img = Image.open(BytesIO(png)).convert("RGB")
                else:
                    raise
            iw, ih = img.size
            scale = max(sw / iw, sh / ih)
            nw = max(1, round(iw * scale))
            nh = max(1, round(ih * scale))
            img = img.resize((nw, nh), Image.LANCZOS)
            x = (nw - sw) // 2
            y = (nh - sh) // 2
            img = img.crop((x, y, x + sw, y + sh))
            pm = self.display.create_pixmap(win, sw, sh, self.screen.depth)
            gc = self._gc(
                pm,
                self.colors.get("text", self.screen.white_pixel),
                self.colors.get("surface", self.screen.white_pixel),
            )
            pm.put_pil_image(gc, 0, 0, img)
            win.change_attributes(background_pixmap=pm.id)
            win.clear_area()
            self._wallpaper_pixmap = pm
            self.display.flush()
            print(
                "Pillarium: wallpaper painted on desktop window",
                file=sys.stderr,
            )
            return True
        except Exception as exc:
            print(
                f"Pillarium: desktop wallpaper pixmap failed: {exc}",
                file=sys.stderr,
            )
            return False

    # -----------------------------------------------------------------
    # Changing the wallpaper at runtime (file picker + persist)
    # -----------------------------------------------------------------
    def _pick_wallpaper_file(self):
        """Return an image path chosen by the user, or None."""
        pickers = []
        if shutil.which("zenity"):
            pickers.append(
                ["zenity", "--file-selection", "--title=Choose a wallpaper image"]
            )
        if shutil.which("kdialog"):
            pickers.append(
                [
                    "kdialog",
                    "--getopenfilename",
                    os.path.expanduser("~"),
                    "Image Files (*.png *.jpg *.jpeg *.webp *.bmp *.svg)",
                ]
            )
        if shutil.which("yad"):
            pickers.append(["yad", "--file", "--title=Choose a wallpaper image"])
        for cmd in pickers:
            try:
                r = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60
                )
            except Exception as exc:
                print(
                    f"Pillarium: wallpaper picker {cmd[0]} failed: {exc}",
                    file=sys.stderr,
                )
                continue
            path = (r.stdout or "").strip()
            if path and os.path.isfile(path):
                return path
        print(
            "Pillarium: no wallpaper file picker found "
            "(install zenity, kdialog or yad).",
            file=sys.stderr,
        )
        return None

    def _change_wallpaper(self):
        picked = self._pick_wallpaper_file()
        if not picked:
            return
        try:
            ext = os.path.splitext(picked)[1].lower() or ".png"
            dest = os.path.join(paths.home_dir(), "user_wallpaper" + ext)
            shutil.copy2(picked, dest)
        except Exception as exc:
            print(
                f"Pillarium: could not copy wallpaper: {exc}",
                file=sys.stderr,
            )
            return
        self.wallpaper_path = dest
        self._set_wallpaper()
        self._save_config()
        print(f"Pillarium: wallpaper changed to {dest}", file=sys.stderr)

    def _reset_default_wallpaper(self):
        self.wallpaper_path = paths.wallpaper_path()
        self._set_wallpaper()
        self._save_config()
        print(
            f"Pillarium: wallpaper reset to {self.wallpaper_path}",
            file=sys.stderr,
        )

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
