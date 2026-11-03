"""The desktop surface: wallpaper and desktop icons.

The surface is Pillarium's root window.  It is an override-redirect
window that covers the whole screen, so it always sits below the window
decorations and never interferes with the X window manager.

The wallpaper and the shortcuts are composed into a single image.  A
separate widget for every shortcut would paint an opaque background over
the wallpaper, because neither customtkinter nor Tk can draw a truly
transparent widget on this display.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from ..theme.tokens import Theme
from ..util import images
from .widgets import Themed, bind_widget

#: Size of the icon picture on the desktop.
ICON_SIZE = 44
#: Width of the caption under an icon.
CAPTION_WIDTH = 92
#: Vertical distance between two icons.
ICON_SPACING = 92
#: Distance of the first icon from the top left corner.
ICON_MARGIN = 24

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
)


def _load_font(size: int = 13) -> ImageFont.ImageFont:
    """Load the interface font, falling back to the built-in bitmap font."""
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


class DesktopSurface:
    """The root window of the shell."""

    def __init__(
        self,
        root: ctk.CTk,
        theme: Theme,
        on_launch: Callable[[dict], None] | None = None,
        on_select: Callable[[int | None], None] | None = None,
        on_context_menu: Callable[[int, int], None] | None = None,
    ):
        self._root = root
        self._theme = theme
        self._themed = Themed(theme)
        self._on_launch = on_launch
        self._on_select = on_select
        self._on_context_menu = on_context_menu
        self._items: list[dict] = []
        self._selected: int | None = None
        self._base_image: Image.Image | None = None
        self._display_image: ctk.CTkImage | None = None
        self._font = _load_font(13)

        try:
            self._root.overrideredirect(True)
        except Exception:
            pass
        self._root.configure(fg_color=theme.get("bg"))

        self.wallpaper = ctk.CTkLabel(self._root, text="")
        self.wallpaper.place(x=0, y=0, relwidth=1, relheight=1)

        bind_widget(self.wallpaper, "<Button-1>", self._on_click)
        bind_widget(self.wallpaper, "<Double-Button-1>", self._on_double_click)
        bind_widget(self.wallpaper, "<Button-3>", self._on_background_menu)
        bind_widget(self._root, "<Button-3>", self._on_background_menu)

    # -----------------------------------------------------------------
    # Geometry
    # -----------------------------------------------------------------
    def apply_geometry(self, width: int, height: int) -> None:
        """Resize the surface to cover the whole screen."""
        try:
            self._root.geometry(f"{int(width)}x{int(height)}+0+0")
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Wallpaper
    # -----------------------------------------------------------------
    def set_wallpaper(self, image: Image.Image | None) -> None:
        """Show ``image`` as the wallpaper."""
        self._base_image = image.convert("RGB") if image is not None else None
        self._redraw()

    # -----------------------------------------------------------------
    # Icons
    # -----------------------------------------------------------------
    def set_icons(self, items: list[dict]) -> None:
        """Rebuild the desktop shortcuts."""
        self._items = list(items)
        self._redraw()

    def refresh_icons(self, items: list[dict]) -> None:
        """Replace the shortcut list while keeping the selection."""
        self.set_icons(items)

    def _icon_rects(self) -> list[tuple[int, int]]:
        """Position of every shortcut on the desktop."""
        return [
            (ICON_MARGIN, ICON_MARGIN + index * ICON_SPACING)
            for index in range(len(self._items))
        ]

    def _icon_at(self, x: int, y: int) -> int | None:
        """Index of the shortcut below the point, if any."""
        for index, (left, top) in enumerate(self._icon_rects()):
            if left - 6 <= x <= left + CAPTION_WIDTH and top - 6 <= y <= top + ICON_SIZE + 28:
                return index
        return None

    # -----------------------------------------------------------------
    # Drawing
    # -----------------------------------------------------------------
    def _redraw(self) -> None:
        """Compose the wallpaper and the shortcuts into one image."""
        screen_w = max(1, self._root.winfo_screenwidth())
        screen_h = max(1, self._root.winfo_screenheight())

        if self._base_image is not None:
            canvas = self._base_image.copy()
            if canvas.size != (screen_w, screen_h):
                canvas = canvas.resize((screen_w, screen_h), Image.LANCZOS)
        else:
            canvas = Image.new("RGB", (screen_w, screen_h), self._theme.get("bg"))

        draw = ImageDraw.Draw(canvas)
        accent = self._theme.get("accent")
        text_color = self._theme.get("text")
        shadow = (0, 0, 0)

        for index, (item, (left, top)) in enumerate(zip(self._items, self._icon_rects())):
            picture = images.load_icon(item.get("icon"), ICON_SIZE)
            if picture is not None:
                picture = images.compose(picture, ICON_SIZE)
            else:
                picture = images.letter_badge(
                    str(item.get("label", "?"))[:1].upper() or "?",
                    ICON_SIZE,
                    accent,
                    self._theme.get("accent_fg"),
                )
            canvas.paste(picture, (left + (CAPTION_WIDTH - ICON_SIZE) // 2, top), picture)

            label = str(item.get("label", "?"))[:16]
            if index == self._selected:
                text_color = accent
            else:
                text_color = self._theme.get("text")
            box = draw.textbbox((0, 0), label, font=self._font)
            text_w = box[2] - box[0]
            text_x = left + (CAPTION_WIDTH - text_w) // 2
            text_y = top + ICON_SIZE + 6
            draw.text((text_x + 1, text_y + 1), label, font=self._font, fill=shadow)
            draw.text((text_x, text_y), label, font=self._font, fill=text_color)

        try:
            self._display_image = ctk.CTkImage(
                light_image=canvas, dark_image=canvas, size=(screen_w, screen_h)
            )
            self.wallpaper.configure(image=self._display_image)
            self.wallpaper.lower()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Interaction
    # -----------------------------------------------------------------
    def _on_click(self, event: tk.Event) -> None:
        index = self._icon_at(event.x, event.y)
        if index is None:
            if self._selected is not None:
                self._selected = None
                self._redraw()
                if self._on_select is not None:
                    self._on_select(None)
            return
        if index != self._selected:
            self._selected = index
            self._redraw()
        if self._on_select is not None:
            self._on_select(index)

    def _on_double_click(self, event: tk.Event) -> None:
        index = self._icon_at(event.x, event.y)
        if index is None or self._on_launch is None:
            return
        if 0 <= index < len(self._items):
            self._on_launch(self._items[index])

    def _on_background_menu(self, event: tk.Event) -> None:
        if self._on_context_menu is not None:
            self._on_context_menu(event.x_root, event.y_root)

    # -----------------------------------------------------------------
    # Theme
    # -----------------------------------------------------------------
    def apply_theme(self, theme: Theme) -> None:
        """Re-colour the desktop."""
        self._theme = theme
        self._themed = Themed(theme)
        self._root.configure(fg_color=theme.get("bg"))
        self._redraw()
