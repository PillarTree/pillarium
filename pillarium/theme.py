"""Theme / colour-palette handling."""

import os


class ThemeMixin:
    palette_dark = {
        "border": "#0f172a",
        "titlebar": "#071027",
        "titlebar_alt": "#1f2937",
        "surface": "#0b1220",
        "accent": "#f43f5e",
        "text": "#e6eef8",
        "taskbar": "#071027",
        "taskbar_active": "#1f2937",
    }
    palette_light = {
        "border": "#0f172a",
        "titlebar": "#ffffff",
        "titlebar_alt": "#e6eef8",
        "surface": "#f8fafc",
        "accent": "#f43f5e",
        "text": "#0b1220",
        "taskbar": "#ffffff",
        "taskbar_active": "#e6eef8",
    }

    def _init_theme(self):
        self.dark_mode = os.environ.get("PILLARIUM_LIGHT", "0") != "1"
        self._apply_palette()

    # -----------------------------------------------------------------
    # Helper: colour allocation
    # -----------------------------------------------------------------
    def _alloc_color(self, color_name, fallback_pixel):
        try:
            cmap = self.screen.default_colormap
            return cmap.alloc_named_color(color_name).pixel
        except Exception:
            return fallback_pixel

    # -----------------------------------------------------------------
    # Palette handling
    # -----------------------------------------------------------------
    def _apply_palette(self):
        pal = self.palette_dark if self.dark_mode else self.palette_light
        self.current_palette = pal
        self.colors = {
            "border": self._alloc_color(pal["border"], self.screen.black_pixel),
            "titlebar": self._alloc_color(
                pal.get("taskbar", pal["surface"]), self.screen.white_pixel
            ),
            "titlebar_alt": self._alloc_color(
                pal.get("taskbar_active", pal["titlebar_alt"]), self.screen.white_pixel
            ),
            "surface": self._alloc_color(pal["surface"], self.screen.white_pixel),
            "accent": self._alloc_color(pal["accent"], self.screen.white_pixel),
            "text": self._alloc_color(pal["text"], self.screen.white_pixel),
            "taskbar": self._alloc_color(
                pal.get("taskbar", pal["surface"]), self.screen.white_pixel
            ),
            "taskbar_active": self._alloc_color(
                pal.get("taskbar_active", pal["titlebar_alt"]),
                self.screen.white_pixel,
            ),
        }

    # -----------------------------------------------------------------
    # Utility: hex → RGB tuple
    # -----------------------------------------------------------------
    def _hex_to_rgb(self, hexstr):
        try:
            h = hexstr.lstrip("#")
            if len(h) == 6:
                return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
            if len(h) == 3:
                return tuple(int(h[i] + h[i], 16) for i in range(3))
        except Exception:
            pass
        return (0, 0, 0)
