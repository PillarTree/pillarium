"""Visual theme, fonts and layout constants for Pillarium (matching Cadet)."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Palette (dark, low-glare) - from Cadet
# ---------------------------------------------------------------------------
BG          = (35, 39, 46)       # main background
PANEL       = (44, 49, 58)       # toolbar / status bar
PANEL_LINE  = (23, 26, 31)       # separator lines
TEXT        = (216, 222, 233)    # primary text
TEXT_DIM    = (139, 147, 163)    # secondary text
TEXT_FAINT  = (100, 108, 122)    # hints / placeholders
ACCENT      = (94, 129, 172)     # accent blue
ACCENT_HOT  = (129, 161, 193)    # accent, hover
SELECT      = (76, 86, 106)      # selection row
SELECT_FOC  = (59, 70, 89)       # selection row (focused) - slightly deeper
ROW_HOVER   = (52, 59, 71)       # mouse hover row
ROW_ALT     = (38, 43, 51)       # zebra striping
DIR_COLOR   = (136, 192, 208)    # directory names
LINK_COLOR  = (163, 190, 140)    # symlinks
ERR_RED     = (191, 97, 106)     # errors
OK_GREEN    = (163, 190, 140)    # success
WARN_YELLOW = (235, 203, 139)

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/truetype/freefont"),
    Path("/usr/share/fonts/truetype/ubuntu"),
]

_SANS = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf",
         "FreeSans.ttf", "Ubuntu-Regular.ttf"]
_MONO = ["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "FreeMono.ttf"]
_BOLD = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]


def _find(names):
    for fd in FONT_DIRS:
        if fd.is_dir():
            for name in names:
                p = fd / name
                if p.is_file():
                    return str(p)
    return None


FONT_UI     = _find(_SANS)
FONT_UI_B   = _find(_BOLD)
FONT_MONO   = _find(_MONO)

# ---------------------------------------------------------------------------
# Layout (matching Cadet)
# ---------------------------------------------------------------------------
SIZE_W       = 980
SIZE_H       = 600
TOOLBAR_H    = 42
PATHBAR_H    = 34
STATUSBAR_H  = 26
ROW_H        = 24
PAD          = 6
BTN_H        = 28
ICON_PAD_X   = 10
NAME_COL_W   = 0.56
SCROLL_W     = 12
MENU_W       = 220
MENU_ITEM_H  = 26
MAX_DIALOG_W = 460

# Taskbar specific (adapted from Pillarium constants)
TASKBAR_H    = 36
TITLEBAR_H   = 36
BORDER       = 2
POWER_W      = 44
WIFI_W       = 44
BLUETOOTH_W  = 44
AUDIO_W      = 44
ETH_W        = 44
BATTERY_W    = 64
CLOCK_W      = 140
CUSTOM_WIDGET_W = 90
WINDOW_BTN_SIZE = 18
RESIZE_GRIP  = 14
MIN_WINDOW_W = 280
MIN_WINDOW_H = 220
SEARCH_W     = 44
MIXER_W      = 380
MIXER_ROW_H  = 36
MIXER_HEADER_H = 40
MIXER_SLIDER_X0 = 140
PROC_W       = 440
PROC_HEADER_H = 40
PROC_ROW_H   = 26

# Key repeat throttle (seconds)
KEY_REPEAT_DELAY = 0.45
KEY_REPEAT_RATE  = 0.06

# Background operation poll interval
POLL_INTERVAL = 0.05


def rgb_to_hex(rgb):
    """Convert RGB tuple to hex string."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# Hex versions for X11 color allocation
PALETTE_DARK = {
    "bg": rgb_to_hex(BG),
    "panel": rgb_to_hex(PANEL),
    "panel_line": rgb_to_hex(PANEL_LINE),
    "text": rgb_to_hex(TEXT),
    "text_dim": rgb_to_hex(TEXT_DIM),
    "text_faint": rgb_to_hex(TEXT_FAINT),
    "accent": rgb_to_hex(ACCENT),
    "accent_hot": rgb_to_hex(ACCENT_HOT),
    "select": rgb_to_hex(SELECT),
    "select_foc": rgb_to_hex(SELECT_FOC),
    "row_hover": rgb_to_hex(ROW_HOVER),
    "row_alt": rgb_to_hex(ROW_ALT),
    "dir_color": rgb_to_hex(DIR_COLOR),
    "link_color": rgb_to_hex(LINK_COLOR),
    "err_red": rgb_to_hex(ERR_RED),
    "ok_green": rgb_to_hex(OK_GREEN),
    "warn_yellow": rgb_to_hex(WARN_YELLOW),
    "border": rgb_to_hex(PANEL_LINE),
    "titlebar": rgb_to_hex(PANEL),
    "titlebar_alt": rgb_to_hex(SELECT),
    "surface": rgb_to_hex(BG),
    "taskbar": rgb_to_hex(PANEL),
    "taskbar_active": rgb_to_hex(SELECT),
}

PALETTE_LIGHT = {
    "bg": "#f8fafc",
    "panel": "#e2e8f0",
    "panel_line": "#94a3b8",
    "text": "#1e293b",
    "text_dim": "#64748b",
    "text_faint": "#94a3b8",
    "accent": "#3b82f6",
    "accent_hot": "#2563eb",
    "select": "#dbeafe",
    "select_foc": "#bfdbfe",
    "row_hover": "#f1f5f9",
    "row_alt": "#f8fafc",
    "dir_color": "#0369a1",
    "link_color": "#059669",
    "err_red": "#dc2626",
    "ok_green": "#16a34a",
    "warn_yellow": "#ca8a04",
    "border": "#94a3b8",
    "titlebar": "#e2e8f0",
    "titlebar_alt": "#dbeafe",
    "surface": "#f8fafc",
    "taskbar": "#e2e8f0",
    "taskbar_active": "#dbeafe",
}

PALETTE_RETRO = {
    "bg": "#0a120a",
    "panel": "#0f1a0f",
    "panel_line": "#1d2b1d",
    "text": "#35ff6a",
    "text_dim": "#1f8f45",
    "text_faint": "#145c2f",
    "accent": "#00e255",
    "accent_hot": "#7cffa0",
    "select": "#0f2b18",
    "select_foc": "#123a1e",
    "row_hover": "#12240f",
    "row_alt": "#0e1a10",
    "dir_color": "#66ff99",
    "link_color": "#00ffcc",
    "err_red": "#ff5f57",
    "ok_green": "#35ff6a",
    "warn_yellow": "#ffd166",
    "border": "#1d2b1d",
    "titlebar": "#0f1a0f",
    "titlebar_alt": "#0f2b18",
    "surface": "#0a120a",
    "taskbar": "#0f1a0f",
    "taskbar_active": "#0f2b18",
}

PALETTES = {
    "dark": PALETTE_DARK,
    "light": PALETTE_LIGHT,
    "retro": PALETTE_RETRO,
}


class ThemeMixin:
    def _init_theme(self):
        import os
        self.dark_mode = os.environ.get("PILLARIUM_LIGHT", "0") != "1"
        self.theme_mode = "light" if not self.dark_mode else "dark"
        self._color_cache = {}
        self._apply_palette()

    def set_theme(self, dark_mode):
        """Switch palette and repaint every surface (light/dark mode)."""
        self.set_theme_mode("dark" if dark_mode else "light")

    def set_theme_mode(self, mode):
        """Switch palette and repaint every surface (dark/light/retro)."""
        mode = (mode or "dark").strip().lower()
        if mode not in PALETTES:
            mode = "dark"
        self.theme_mode = mode
        self.dark_mode = mode != "light"
        self._apply_palette()
        self._refresh_theme_windows()

    def cycle_theme(self):
        """Cycle the palette dark -> light -> retro -> dark."""
        order = ("dark", "light", "retro")
        cur = getattr(self, "theme_mode", "dark")
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "dark"
        self.set_theme_mode(nxt)

    def _refresh_theme_windows(self):
        """Repaint Pillarium-owned surfaces with the current palette."""
        import sys

        # -----------------------------------------------------------------
        # Managed client frames + decorations
        # -----------------------------------------------------------------
        for _client_id, data in list(getattr(self, "frames", {}).items()):
            try:
                data["frame"].change_attributes(
                    background_pixel=self.colors["surface"],
                    border_pixel=self.colors["border"],
                )
                data["titlebar"].change_attributes(
                    background_pixel=self.colors["titlebar"],
                    border_pixel=self.colors["border"],
                )
                data["container"].change_attributes(
                    background_pixel=self.colors["surface"],
                    border_pixel=self.colors["border"],
                )
                data["close_button"].change_attributes(
                    background_pixel=self.colors["accent"],
                    border_pixel=self.colors["border"],
                )
                data["minimize_button"].change_attributes(
                    background_pixel=self.colors["titlebar_alt"],
                    border_pixel=self.colors["border"],
                )
                data["maximize_button"].change_attributes(
                    background_pixel=self.colors["titlebar_alt"],
                    border_pixel=self.colors["border"],
                )
                for key in (
                    "titlebar",
                    "frame",
                    "close_button",
                    "minimize_button",
                    "maximize_button",
                    "container",
                ):
                    try:
                        self._redraw_window(data[key])
                    except Exception:
                        pass
            except Exception:
                continue

        # -----------------------------------------------------------------
        # Taskbar
        # -----------------------------------------------------------------
        try:
            self.taskbar.change_attributes(
                background_pixel=self.colors["taskbar"],
                border_pixel=self.colors["border"],
            )
        except Exception:
            pass
        try:
            self._redraw_taskbar()
        except Exception:
            pass

        # -----------------------------------------------------------------
        # Recolour any open popups / dialogs and repaint the desktop.
        # -----------------------------------------------------------------
        redrawers = (
            ("active_menu", "_redraw_menu"),
            ("search_state", "_redraw_search"),
            ("confirm_state", "_redraw_confirm_dialog"),
            ("wifi_auth_state", "_redraw_wifi_auth"),
            ("mixer_state", "_redraw_mixer"),
            ("clock_state", "_redraw_clock_menu"),
            ("_format_menu_state", "_redraw_format_menu"),
            ("process_state", "_redraw_processes"),
            ("alert_state", "_redraw_alert"),
        )
        for state_attr, redraw in redrawers:
            state = getattr(self, state_attr, None)
            window = state.get("window") if isinstance(state, dict) else None
            if window is None:
                continue
            try:
                window.change_attributes(
                    background_pixel=self.colors["surface"],
                    border_pixel=self.colors["border"],
                )
            except Exception:
                pass
            try:
                getattr(self, redraw)()
            except Exception:
                pass

        try:
            self._redraw_desktop_icons()
        except Exception as exc:
            print(
                f"Pillarium: desktop repaint after theme change failed: {exc}",
                file=sys.stderr,
            )
        try:
            self.display.flush()
        except Exception:
            pass

    def _alloc_color(self, color_name, fallback_pixel):
        cached = self._color_cache.get(color_name)
        if cached is not None:
            return cached
        try:
            cmap = self.screen.default_colormap
            color_pixel = cmap.alloc_named_color(color_name).pixel
        except Exception:
            color_pixel = fallback_pixel
        self._color_cache[color_name] = color_pixel
        return color_pixel

    def _apply_palette(self):
        if not hasattr(self, "_color_cache"):
            self._color_cache = {}
        mode = getattr(self, "theme_mode", "light" if not self.dark_mode else "dark")
        pal = PALETTES.get(mode, PALETTE_DARK)
        self.current_palette = pal
        self.colors = {
            "border": self._alloc_color(pal["border"], self.screen.black_pixel),
            "titlebar": self._alloc_color(
                pal.get("taskbar", pal["surface"]), self.screen.black_pixel
            ),
            "titlebar_alt": self._alloc_color(
                pal.get("taskbar_active", pal["titlebar_alt"]), self.screen.black_pixel
            ),
            "surface": self._alloc_color(pal["surface"], self.screen.black_pixel),
            "accent": self._alloc_color(pal["accent"], self.screen.black_pixel),
            "text": self._alloc_color(pal["text"], self.screen.white_pixel),
            "taskbar": self._alloc_color(
                pal.get("taskbar", pal["surface"]), self.screen.black_pixel
            ),
            "taskbar_active": self._alloc_color(
                pal.get("taskbar_active", pal["titlebar_alt"]),
                self.screen.black_pixel,
            ),
        }

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

    def _get_rgb(self, name):
        """Get RGB tuple from current palette."""
        hex_color = self.current_palette.get(name)
        if hex_color:
            return self._hex_to_rgb(hex_color)
        return (255, 255, 255)