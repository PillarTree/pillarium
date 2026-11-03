"""The theme editor.

Users can tweak every colour token of the active palette, pick a new
theme from the built-in set or import the colours the desktop
environment advertises through the freedesktop.org Settings portal.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from ..theme.tokens import COLOR_TOKENS, Theme, hex_to_rgb, rgb_to_hex
from .base import ShellWindow
from .widgets import Themed, button, entry, label

PICKER_WIDTH = 300
PICKER_HEIGHT = 260


class ColorPicker(ShellWindow):
    """A small RGB picker."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        color: str,
        on_pick: Callable[[str], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._themed = Themed(theme)
        self._on_pick = on_pick
        red, green, blue = hex_to_rgb(color)
        self._rgb = [red, green, blue]

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        self.preview = ctk.CTkFrame(
            self.container, height=36, corner_radius=6, fg_color=color
        )
        self.preview.pack(fill="x", padx=14, pady=(14, 8))

        for index, (name, value) in enumerate(zip("RGB", self._rgb)):
            row = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
            row.pack(fill="x", padx=14, pady=2)
            label(row, self._themed, name, color_token="text_dim", size=11).pack(side="left")
            slider = ctk.CTkSlider(
                row,
                from_=0,
                to=255,
                width=180,
                height=14,
                fg_color=theme.get("surface_alt"),
                progress_color=theme.get("accent"),
                button_color=theme.get("accent"),
                command=lambda value, channel=index: self._set_channel(channel, value),
            )
            slider.set(value)
            slider.pack(side="left", padx=8)
            self._rgb.append(slider)

        self.hex_entry = entry(self.container, text=rgb_to_hex(*self._rgb), width=110)
        self.hex_entry.pack(pady=(8, 0))

        actions = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        actions.pack(fill="x", padx=14, pady=12)
        button(actions, self._themed, "Cancel", self.dismiss, width=90).pack(side="right")
        button(
            actions,
            self._themed,
            "Apply",
            self._apply,
            accent=True,
            width=90,
        ).pack(side="right", padx=(0, 8))

        self.bind_escape()

    def _set_channel(self, channel: int, value: float) -> None:
        self._rgb[channel] = max(0, min(255, int(value)))
        color = rgb_to_hex(self._rgb[0], self._rgb[1], self._rgb[2])
        self.preview.configure(fg_color=color)
        self.hex_entry.delete(0, "end")
        self.hex_entry.insert(0, color)

    def _apply(self) -> None:
        color = self.hex_entry.get().strip()
        if not color.startswith("#"):
            color = "#" + color
        try:
            hex_to_rgb(color)
        except Exception:
            color = rgb_to_hex(self._rgb[0], self._rgb[1], self._rgb[2])
        self.dismiss()
        self._on_pick(color)

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)


class ThemeEditor(ShellWindow):
    """Edits the colour tokens of a theme."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        on_apply: Callable[[Theme], None],
        on_save: Callable[[Theme, str], None],
        on_delete: Callable[[str], None],
        on_import: Callable[[], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._themed = Themed(theme)
        self._on_apply = on_apply
        self._on_save = on_save
        self._on_delete = on_delete
        self._on_import = on_import
        self._working = theme.copy("Custom")
        self._swatches: dict[str, ctk.CTkButton] = {}

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        header = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", padx=14, pady=(12, 4))
        label(header, self._themed, "Theme Editor", weight="bold").pack(side="left")
        button(
            header, self._themed, "Import from desktop", self._import, width=150, height=26
        ).pack(side="right")

        self.body = ctk.CTkScrollableFrame(
            self.container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=theme.get("border_strong"),
            scrollbar_button_hover_color=theme.get("accent"),
        )
        self.body.pack(fill="both", expand=True, padx=6, pady=6)

        footer = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        footer.pack(fill="x", padx=14, pady=(4, 12))
        button(footer, self._themed, "Apply", self._apply, accent=True, width=90).pack(
            side="right"
        )
        button(
            footer, self._themed, "Save As…", self._save_as, width=110
        ).pack(side="right", padx=(0, 8))
        button(footer, self._themed, "Delete", self._delete, width=90).pack(side="right")

        self._build_rows()
        self.bind_escape()

    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def _build_rows(self) -> None:
        for child in self.body.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._swatches = {}
        for token in COLOR_TOKENS:
            row = ctk.CTkFrame(self.body, fg_color="transparent", corner_radius=0)
            row.pack(fill="x", padx=6, pady=2)
            label(row, self._themed, token, color_token="text_dim", size=11).pack(
                side="left", padx=(6, 10)
            )
            swatch = ctk.CTkButton(
                row,
                text="",
                width=40,
                height=22,
                corner_radius=4,
                fg_color=self._working.get(token),
                hover_color=self._working.get(token),
                border_width=1,
                border_color=self._theme.get("border_strong"),
                command=lambda name=token: self._pick(name),
            )
            swatch.pack(side="left")
            self._swatches[token] = swatch

    def _pick(self, token: str) -> None:
        picker = ColorPicker(
            self._master,
            self._theme,
            self._working.get(token),
            lambda color: self._set_color(token, color),
        )
        picker.place(
            self.winfo_x() + 40,
            self.winfo_y() + 60,
            PICKER_WIDTH,
            PICKER_HEIGHT,
        )
        picker.show()

    def _set_color(self, token: str, color: str) -> None:
        self._working.colors[token] = color
        swatch = self._swatches.get(token)
        if swatch is not None:
            swatch.configure(fg_color=color, hover_color=color)
        self._on_apply(self._working)

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------
    def _apply(self) -> None:
        self._on_apply(self._working)

    def _save_as(self) -> None:
        dialog = ctk.CTkInputDialog(
            text="Name for the new theme:", title="Save theme"
        )
        name = dialog.get_input()
        if not name:
            return
        self._working.name = name
        self._on_save(self._working, name)

    def _delete(self) -> None:
        self._on_delete(self._working.name)

    def _import(self) -> None:
        self._on_import()

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(fg_color=theme.get("surface"))
        self._build_rows()
