"""Icon handling: theme lookup, rasterization, window icons."""

import os
import re
import shutil
import subprocess
import sys
from Xlib import X


class IconMixin:
    # -----------------------------------------------------------------
    # Icon handling (search, task‑bar, desktop)
    # -----------------------------------------------------------------
    def _icon_search_dirs(self):
        dirs = []
        for base in (
            os.path.expanduser("~/.local/share/icons"),
            os.path.expanduser("~/.icons"),
            "/usr/share/icons",
            "/usr/local/share/icons",
            "/usr/share/pixmaps",
            "/usr/local/share/pixmaps",
        ):
            if os.path.isdir(base) and base not in dirs:
                dirs.append(base)
        for base in os.environ.get("XDG_DATA_DIRS", "").split(":"):
            if base:
                d = os.path.join(os.path.expanduser(base), "icons")
                if os.path.isdir(d) and d not in dirs:
                    dirs.append(d)
        return dirs

    def _rasterize_icon_file(self, path, size):
        try:
            from PIL import Image
        except Exception:
            return None
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".svg":
                try:
                    import cairosvg

                    data = cairosvg.svg2png(
                        url=path, output_width=size, output_height=size
                    )
                    import io

                    img = Image.open(io.BytesIO(data)).convert("RGBA")
                except Exception:
                    rsvg = shutil.which("rsvg-convert")
                    if not rsvg:
                        return None
                    import io

                    proc = subprocess.run(
                        [rsvg, "-w", str(size), "-h", str(size), path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    )
                    if proc.returncode != 0:
                        return None
                    img = Image.open(io.BytesIO(proc.stdout)).convert("RGBA")
            else:
                img = Image.open(path).convert("RGBA")
            img.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
            return canvas
        except Exception:
            return None

    def _load_icon(self, icon_name, size=56):
        """Resolve a .desktop Icon= value and return a Pillow RGBA image.

        Icon= may be:
          * an absolute path
          * a relative filename
          * a theme icon name such as 'firefox'
          * an icon name with an extension
        """

        def _icon_size_key(path, want):
            # Prefer theme-directory icons whose nominal size is closest
            # to the requested size (e.g. hicolor/64x64 for a 64px icon
            # instead of the 16x16 file os.walk often hits first).
            m = re.search(r"/(\d+)x\d+/", path)
            if m:
                s = int(m.group(1))
                return (0, abs(s - want), s)
            return (1, 0, 0)

        if not icon_name:
            return None

        try:
            from PIL import Image
        except Exception:
            return None

        if not hasattr(self, "_icon_cache"):
            self._icon_cache = {}

        raw = os.path.expanduser(str(icon_name).strip())
        key = (raw, int(size))
        if key in self._icon_cache:
            return self._icon_cache[key]

        # Absolute icon path.
        candidates = []
        if os.path.isabs(raw):
            candidates.append(raw)
        else:
            stem, ext = os.path.splitext(raw)
            names = [raw]
            if not ext:
                names += [
                    raw + ".png", raw + ".svg", raw + ".xpm",
                    raw + ".jpg", raw + ".jpeg", raw + ".webp",
                ]

            # XDG icon locations, including application-local icon trees.
            data_home = os.environ.get(
                "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
            )
            data_dirs = os.environ.get(
                "XDG_DATA_DIRS", "/usr/local/share:/usr/share"
            ).split(":")

            bases = [
                os.path.join(os.path.expanduser(data_home), "icons"),
                os.path.expanduser("~/.icons"),
                os.path.join(os.path.expanduser(data_home), "pixmaps"),
                "/usr/local/share/icons",
                "/usr/share/icons",
                "/usr/local/share/pixmaps",
                "/usr/share/pixmaps",
            ]

            for base in data_dirs:
                base = os.path.expanduser(base)
                if base:
                    bases.append(os.path.join(base, "icons"))
                    bases.append(os.path.join(base, "pixmaps"))

            # Flatpak-exported icons are often stored beside exported
            # desktop files rather than in the normal theme directories.
            bases.extend([
                os.path.expanduser("~/.local/share/flatpak/exports/share/icons"),
                "/var/lib/flatpak/exports/share/icons",
            ])

            seen_bases = set()
            for base in bases:
                if base in seen_bases or not os.path.isdir(base):
                    continue
                seen_bases.add(base)

                for name in names:
                    candidates.append(os.path.join(base, name))

                # Theme icons normally live several directories below
                # /usr/share/icons/<theme>/<size>/<category>/.
                try:
                    for root, dirs, files in os.walk(base):
                        dirs[:] = [
                            d for d in dirs
                            if d not in {".git", "cache", "caches"}
                        ]
                        lower_files = {f.lower(): f for f in files}
                        for name in names:
                            actual = lower_files.get(os.path.basename(name).lower())
                            if actual:
                                candidates.append(os.path.join(root, actual))

                        # Some applications use an extensionless Icon= name.
                        if not ext:
                            wanted = raw.lower()
                            for f in files:
                                fs, fe = os.path.splitext(f)
                                if (
                                    fs.lower() == wanted
                                    and fe.lower() in {
                                        ".png", ".svg", ".xpm",
                                        ".jpg", ".jpeg", ".webp"
                                    }
                                ):
                                    candidates.append(os.path.join(root, f))
                except Exception:
                    pass

        seen = set()
        candidates.sort(
            key=lambda p: _icon_size_key(p, size)
        )
        for path in candidates:
            path = os.path.abspath(os.path.expanduser(path))
            if path in seen or not os.path.isfile(path):
                continue
            seen.add(path)

            img = self._rasterize_icon_file(path, size)
            if img is not None:
                self._icon_cache[key] = img
                print(
                    f"Pillarium: ICON OK {icon_name} -> {path}",
                    file=sys.stderr,
                )
                return img

        self._icon_cache[key] = None
        print(f"Pillarium: ICON NOT FOUND: {icon_name}", file=sys.stderr)
        return None

    def _render_icon_body(self, size, fill_hex, border_hex, bg_hex, border_w=2):
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (size, size), self._hex_to_rgb(bg_hex))
        draw = ImageDraw.Draw(img)
        radius = max(4, size // 4)
        draw.rounded_rectangle(
            (0, 0, size - 1, size - 1),
            radius=radius,
            fill=self._hex_to_rgb(fill_hex),
            outline=self._hex_to_rgb(border_hex),
            width=border_w,
        )
        return img

    def _resolve_taskbar_icon(self, data):
        icon = data.get("icon_image")
        if icon is not None:
            return icon

        classes = set(data.get("wm_class", []))
        for app in getattr(self, "applications", []):
            startup = str(
                app.get("startup_wm_class", "") or ""
            ).strip().lower()
            if startup and startup in classes:
                icon = self._load_icon(app.get("icon"), 26)
                if icon is not None:
                    data["icon_image"] = icon
                    return icon

        title = str(data.get("title", "")).strip().lower()
        for app in getattr(self, "applications", []):
            if str(app.get("label", "")).strip().lower() == title:
                icon = self._load_icon(app.get("icon"), 26)
                if icon is not None:
                    data["icon_image"] = icon
                    return icon

        return None

    # -----------------------------------------------------------------
    # Read WM_CLASS for desktop-entry icon matching.
    # -----------------------------------------------------------------
    def _read_window_class(self, client):
        try:
            value = client.get_wm_class()
            if not value:
                return []
            return [
                str(part).strip().lower()
                for part in value
                if str(part).strip()
            ]
        except Exception:
            return []

    # -----------------------------------------------------------------
    # Read _NET_WM_ICON and convert to Pillow Image
    # -----------------------------------------------------------------
    def _read_icon_image(self, client):
        try:
            from PIL import Image
        except Exception:
            return None
        try:
            atom = self.display.intern_atom("_NET_WM_ICON")
            prop = client.get_full_property(atom, X.AnyPropertyType)
            if not prop or not prop.value:
                return None
            vals = list(prop.value)
            i = 0
            icons = []
            while i + 1 < len(vals):
                w = int(vals[i])
                h = int(vals[i + 1])
                i += 2
                if w <= 0 or h <= 0:
                    break
                size = w * h
                pixels = vals[i : i + size]
                i += size
                if not pixels:
                    break
                # Prefer icons near 64 px
                score = -abs(w - 64)
                icons.append((score, w, h, pixels))
            if not icons:
                return None
            icons.sort(reverse=True)
            _, w, h, pixels = icons[0]
            buf = bytearray()
            for p in pixels:
                a = (p >> 24) & 0xFF
                r = (p >> 16) & 0xFF
                g = (p >> 8) & 0xFF
                b = p & 0xFF
                buf.extend([r, g, b, a])
            try:
                img = Image.frombytes("RGBA", (w, h), bytes(buf))
                return img
            except Exception:
                return None
        except Exception:
            return None
