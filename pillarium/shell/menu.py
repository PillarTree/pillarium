"""The generic popup menu.

Every context menu in Pillarium - the desktop menu, the window menu, the
Wi-Fi menu, the power menu - is built from a list of :class:`MenuItem`
objects and rendered by :class:`PopupMenu`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import customtkinter as ctk

from ..theme.tokens import Theme
from .base import ShellWindow
from .widgets import Themed

#: Height of a menu row.
ROW_HEIGHT = 30
#: Width of a menu.
MENU_WIDTH = 230
#: Padding around the menu content.
PADDING = 4


@dataclass
class MenuItem:
    """A single entry of a popup menu."""

    label: str
    action: Any = None
    enabled: bool = True
    separator: bool = False
    detail: str = ""

    @classmethod
    def divider(cls) -> "MenuItem":
        """A horizontal rule between menu entries."""
        return cls(label="", separator=True)


def build_items(entries: list[Any]) -> list[MenuItem]:
    """Convert a list of dicts into :class:`MenuItem` objects."""
    items: list[MenuItem] = []
    for entry in entries:
        if isinstance(entry, MenuItem):
            items.append(entry)
        elif isinstance(entry, dict):
            items.append(
                MenuItem(
                    label=str(entry.get("label", "")),
                    action=entry.get("action"),
                    enabled=bool(entry.get("enabled", True)),
                    separator=bool(entry.get("separator", False)),
                    detail=str(entry.get("detail", "")),
                )
            )
        else:
            items.append(MenuItem(label=str(entry)))
    return items


class PopupMenu(ShellWindow):
    """A themed, keyboard dismissable popup menu."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        items: list[MenuItem],
        on_select: Callable[[Any], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._items = items
        self._on_select = on_select
        self._themed = Themed(theme)
        self._rows: list[ctk.CTkButton] = []

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

        self._build()
        self.bind_escape()

    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def _build(self) -> None:
        for item in self._items:
            if item.separator:
                separator = ctk.CTkFrame(
                    self.container, height=1, fg_color=self._theme.get("border")
                )
                separator.pack(fill="x", padx=6, pady=3)
                continue
            row = ctk.CTkButton(
                self.container,
                text=item.label,
                height=ROW_HEIGHT - 6,
                corner_radius=4,
                anchor="w",
                fg_color="transparent",
                hover_color=self._theme.get("panel_hover")
                if item.enabled
                else self._theme.get("surface"),
                text_color=self._theme.get("text")
                if item.enabled
                else self._theme.get("text_faint"),
                font=self._themed.font(),
                command=self._make_handler(item),
            )
            row.pack(fill="x", padx=2)
            self._rows.append(row)

    def _make_handler(self, item: MenuItem) -> Callable[[], None]:
        def handler() -> None:
            if not item.enabled:
                return
            self.dismiss()
            if self._on_select is not None:
                self._on_select(item.action)

        return handler

    # -----------------------------------------------------------------
    # Placement
    # -----------------------------------------------------------------
    def height(self) -> int:
        total = PADDING * 2
        for item in self._items:
            total += 8 if item.separator else ROW_HEIGHT
        return total

    def show_at(self, x: int, y: int, screen: tuple[int, int] | None = None) -> None:
        """Show the menu, keeping it inside the screen."""
        width = MENU_WIDTH
        height = self.height()
        if screen is not None:
            screen_w, screen_h = screen
            x = max(0, min(x, screen_w - width))
            y = max(0, min(y, screen_h - height))
        self.place(x, y, width, height)
        self.show()

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(
            fg_color=theme.get("surface"),
            border_color=theme.get("border"),
        )
        for row, item in zip(self._rows, [i for i in self._items if not i.separator]):
            row.configure(
                text_color=theme.get("text") if item.enabled else theme.get("text_faint"),
                hover_color=theme.get("panel_hover")
                if item.enabled
                else theme.get("surface"),
                font=self._themed.font(),
            )
