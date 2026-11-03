"""Theme aware widget factories.

Every widget Pillarium creates goes through one of the helpers in this
module so colours, fonts and corner radii stay consistent and a theme
change only has to re-apply a handful of properties.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image

from ..theme.tokens import Theme, contrasting_text
from ..util import images


def bind_widget(
    widget: Any,
    sequence: str,
    handler: Callable[[tk.Event], Any],
    add: bool = False,
) -> None:
    """Bind an event on a customtkinter widget.

    customtkinter widgets are composites: the pointer events are
    delivered to an internal canvas (and sometimes to a text label or
    entry), not to the widget itself.  Tk does not propagate events to
    the parent, so every part that can receive the event has to be
    bound explicitly.
    """
    targets = [widget]
    for attribute in ("_canvas", "_text_label", "_entry"):
        child = getattr(widget, attribute, None)
        if child is not None and child not in targets:
            targets.append(child)
    for target in targets:
        try:
            target.bind(sequence, handler, add=add)
        except Exception:
            continue


class Themed:
    """Small helper bundling a theme with the values widgets need."""

    def __init__(self, theme: Theme):
        self.theme = theme

    # -- colours ---------------------------------------------------
    def color(self, token: str) -> str:
        return self.theme.get(token)

    def transparent(self) -> str:
        return "transparent"

    def on_accent(self) -> str:
        return self.theme.get("accent_fg")

    def font(self, size: int | None = None, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(
            family=self.theme.font("ui"),
            size=size if size is not None else self.theme.metric("font_size"),
            weight=weight,
        )

    def mono_font(self, size: int | None = None) -> ctk.CTkFont:
        return ctk.CTkFont(
            family=self.theme.font("mono") or "TkFixedFont",
            size=size if size is not None else self.theme.metric("font_size") - 1,
        )

    def radius(self) -> int:
        return self.theme.metric("radius")


def button(
    parent: Any,
    themed: Themed,
    text: str = "",
    command: Callable[[], None] | None = None,
    *,
    accent: bool = False,
    width: int = 120,
    height: int = 30,
    hover: bool = True,
    text_color: str | None = None,
) -> ctk.CTkButton:
    """A standard Pillarium button."""
    fg = themed.color("accent") if accent else themed.transparent()
    fg_hover = themed.color("accent_hover") if accent else themed.color("panel_hover")
    fg_text = text_color or (themed.on_accent() if accent else themed.color("text"))
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=width,
        height=height,
        corner_radius=themed.radius(),
        fg_color=fg,
        hover_color=fg_hover,
        text_color=fg_text,
        border_width=0 if accent else 1,
        border_color=themed.color("border_strong"),
        font=themed.font(),
    )


def label(
    parent: Any,
    themed: Themed,
    text: str = "",
    *,
    color_token: str = "text",
    size: int | None = None,
    weight: str = "normal",
    anchor: str = "w",
    mono: bool = False,
) -> ctk.CTkLabel:
    """A text label using the theme's colours."""
    return ctk.CTkLabel(
        parent,
        text=text,
        text_color=themed.color(color_token),
        anchor=anchor,
        font=themed.mono_font(size) if mono else themed.font(size, weight),
    )


def entry(
    parent: Any,
    themed: Themed,
    text: str = "",
    *,
    placeholder: str = "",
    show: str = "",
    width: int = 200,
) -> ctk.CTkEntry:
    """A text input using the theme's colours."""
    return ctk.CTkEntry(
        parent,
        text=text,
        placeholder_text=placeholder,
        show=show,
        width=width,
        height=30,
        corner_radius=themed.radius(),
        fg_color=themed.color("surface_alt"),
        text_color=themed.color("text"),
        placeholder_text_color=themed.color("text_faint"),
        border_color=themed.color("border_strong"),
        font=themed.font(),
    )


def frame(
    parent: Any,
    themed: Themed,
    *,
    fg_token: str = "surface",
    radius: int | None = None,
    border: bool = True,
    **kwargs: Any,
) -> ctk.CTkFrame:
    """A container using the theme's colours."""
    return ctk.CTkFrame(
        parent,
        fg_color=themed.color(fg_token),
        corner_radius=themed.radius() if radius is None else radius,
        border_width=1 if border else 0,
        border_color=themed.color("border"),
        **kwargs,
    )


def scroll_frame(parent: Any, themed: Themed, **kwargs: Any) -> ctk.CTkScrollableFrame:
    """A scrollable container using the theme's colours."""
    return ctk.CTkScrollableFrame(
        parent,
        fg_color=themed.color("surface"),
        corner_radius=themed.radius(),
        border_width=1,
        border_color=themed.color("border"),
        scrollbar_button_color=themed.color("border_strong"),
        scrollbar_button_hover_color=themed.color("accent"),
        **kwargs,
    )


def separator(parent: Any, themed: Themed, orientation: str = "horizontal") -> ctk.CTkFrame:
    """A one pixel divider."""
    if orientation == "horizontal":
        return ctk.CTkFrame(parent, height=1, fg_color=themed.color("border"))
    return ctk.CTkFrame(parent, width=1, fg_color=themed.color("border"))


def option_menu(
    parent: Any,
    themed: Themed,
    values: list[str],
    command: Callable[[str], None] | None = None,
    width: int = 160,
    height: int = 30,
) -> ctk.CTkOptionMenu:
    """A themed drop-down list."""
    return ctk.CTkOptionMenu(
        parent,
        values=list(values),
        command=command,
        width=width,
        height=height,
        corner_radius=themed.radius(),
        fg_color=themed.color("surface_alt"),
        button_color=themed.color("panel_hover"),
        button_hover_color=themed.color("accent"),
        text_color=themed.color("text"),
        dropdown_fg_color=themed.color("surface_alt"),
        dropdown_text_color=themed.color("text"),
        dropdown_hover_color=themed.color("panel_hover"),
        font=themed.font(),
    )


class IconBadge(ctk.CTkLabel):
    """A label showing an application icon or a letter badge."""

    def __init__(
        self,
        parent: Any,
        themed: Themed,
        size: int = 24,
        letter: str = "?",
        background: str | None = None,
    ):
        self._themed = themed
        self._size = size
        self._letter = letter or "?"
        self._background = background
        super().__init__(parent, text="", width=size, height=size)
        self.set_icon(None)

    def set_icon(self, image: Image.Image | None) -> None:
        """Show ``image``, falling back to the letter badge."""
        if image is not None:
            composed = images.compose(image, self._size)
            self.configure(image=images.to_ctk_image(composed), text="")
            return
        background = self._background or self._themed.color("accent")
        badge = images.letter_badge(
            self._letter,
            self._size,
            background,
            contrasting_text(background),
        )
        self.configure(image=images.to_ctk_image(badge), text="")

    def set_letter(self, letter: str) -> None:
        self._letter = letter or "?"
        self.set_icon(None)

    def set_background(self, color: str) -> None:
        self._background = color


def status_dot(parent: Any, themed: Themed, color: str, size: int = 8) -> ctk.CTkFrame:
    """A small coloured dot used in status rows."""
    return ctk.CTkFrame(parent, width=size, height=size, corner_radius=size // 2, fg_color=color)
