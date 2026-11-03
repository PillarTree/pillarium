"""Window decorations drawn with customtkinter.

Every managed application window gets a borderless ``CTkToplevel`` that
holds a themed title bar and a plain Tk frame.  The application window is
reparented into that frame by the window manager, which keeps the
toolkit responsible for the frame while Pillarium stays responsible for
the application.
"""

from __future__ import annotations

import time
import tkinter as tk
from typing import Callable

import customtkinter as ctk
from PIL import Image

from ..core.clients import Client
from ..theme.tokens import Theme
from .base import ShellWindow
from .widgets import IconBadge, Themed, bind_widget, button, label

#: Size of the resize grip in the lower right corner.
GRIP_SIZE = 14


class Decoration(ShellWindow):
    """The frame around a managed application window."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        client: Client,
        callbacks: "DecorationCallbacks",
    ):
        super().__init__(master, theme, fg_token="surface")
        self._client_id = client.id
        self._callbacks = callbacks
        self._themed = Themed(theme)
        self._active = False
        self._drag_origin: tuple[int, int] | None = None
        self._drag_geometry: tuple[int, int, int, int] | None = None

        self.titlebar = ctk.CTkFrame(
            self,
            height=theme.metric("titlebar_height"),
            corner_radius=0,
            fg_color=theme.get("titlebar"),
        )
        self.titlebar.pack(side="top", fill="x")
        self.titlebar.pack_propagate(False)

        self.icon = IconBadge(self.titlebar, self._themed, size=22, letter=_initial(client))
        self.icon.pack(side="left", padx=(8, 6), pady=4)

        self.title = label(self.titlebar, self._themed, client.title, weight="bold")
        self.title.pack(side="left", fill="x", expand=True)

        self.minimize_button = button(
            self.titlebar, self._themed, "–", self._on_minimize, width=28, height=24
        )
        self.minimize_button.pack(side="right", padx=2)

        self.maximize_button = button(
            self.titlebar, self._themed, "□", self._on_maximize, width=28, height=24
        )
        self.maximize_button.pack(side="right", padx=2)

        self.close_button = button(
            self.titlebar,
            self._themed,
            "×",
            self._on_close,
            width=28,
            height=24,
            accent=True,
        )
        self.close_button.pack(side="right", padx=(2, 6))

        # A plain Tk frame is used for the client area: a CTk frame would
        # place a canvas on top of the embedded application window.
        self.client_area = tk.Frame(
            self,
            bg=theme.get("surface"),
            highlightthickness=0,
            borderwidth=0,
        )
        self.client_area.pack(side="top", fill="both", expand=True)

        self.grip = ctk.CTkFrame(
            self,
            width=GRIP_SIZE,
            height=GRIP_SIZE,
            corner_radius=0,
            fg_color=theme.get("border_strong"),
        )
        self.grip.place(relx=1.0, rely=1.0, anchor="se")

        self._bind_titlebar()
        self._bind_grip()

    # -----------------------------------------------------------------
    # Client area
    # -----------------------------------------------------------------
    def client_area_xid(self) -> int:
        """X window id of the area the application is embedded in."""
        self.update_idletasks()
        return int(self.client_area.winfo_id())

    def wait_for_client_area(self, attempts: int = 25) -> bool:
        """Wait until the client area is mapped.

        The application window is reparented into this area, so it has
        to be viewable before that happens.
        """
        for _ in range(attempts):
            try:
                self.update_idletasks()
                if self.client_area.winfo_ismapped():
                    return True
            except Exception:
                return False
            time.sleep(0.01)
        return False

    # -----------------------------------------------------------------
    # Interaction
    # -----------------------------------------------------------------
    def _bind_titlebar(self) -> None:
        for widget in (self.titlebar, self.title, self.icon):
            bind_widget(widget, "<ButtonPress-1>", self._on_title_press)
            bind_widget(widget, "<B1-Motion>", self._on_title_motion)
            bind_widget(widget, "<ButtonRelease-1>", self._on_title_release)
            bind_widget(widget, "<Double-Button-1>", self._on_title_double)
            bind_widget(widget, "<Button-3>", self._on_title_menu)

    def _bind_grip(self) -> None:
        bind_widget(self.grip, "<ButtonPress-1>", self._on_grip_press)
        bind_widget(self.grip, "<B1-Motion>", self._on_grip_motion)
        bind_widget(self.grip, "<ButtonRelease-1>", self._on_grip_release)

    def _on_title_press(self, event: tk.Event) -> None:
        self._callbacks.on_activate(self._client_id)
        self._drag_origin = (event.x_root, event.y_root)
        self._drag_geometry = self.current_geometry()

    def _on_title_motion(self, event: tk.Event) -> None:
        if self._drag_origin is None or self._drag_geometry is None:
            return
        dx = event.x_root - self._drag_origin[0]
        dy = event.y_root - self._drag_origin[1]
        x, y, width, height = self._drag_geometry
        self._callbacks.on_move(self._client_id, x + dx, y + dy)

    def _on_title_release(self, _event: tk.Event) -> None:
        self._drag_origin = None
        self._drag_geometry = None

    def _on_title_double(self, _event: tk.Event) -> None:
        self._callbacks.on_maximize(self._client_id)

    def _on_title_menu(self, event: tk.Event) -> None:
        self._callbacks.on_menu(self._client_id, event.x_root, event.y_root)

    def _on_grip_press(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root, event.y_root)
        self._drag_geometry = self.current_geometry()

    def _on_grip_motion(self, event: tk.Event) -> None:
        if self._drag_origin is None or self._drag_geometry is None:
            return
        dx = event.x_root - self._drag_origin[0]
        dy = event.y_root - self._drag_origin[1]
        _x, _y, width, height = self._drag_geometry
        self._callbacks.on_resize(self._client_id, width + dx, height + dy)

    def _on_grip_release(self, _event: tk.Event) -> None:
        self._drag_origin = None
        self._drag_geometry = None

    def _on_close(self) -> None:
        self._callbacks.on_close(self._client_id)

    def _on_minimize(self) -> None:
        self._callbacks.on_minimize(self._client_id)

    def _on_maximize(self) -> None:
        self._callbacks.on_maximize(self._client_id)

    # -----------------------------------------------------------------
    # Geometry
    # -----------------------------------------------------------------
    def current_geometry(self) -> tuple[int, int, int, int]:
        """Position and size of the decoration on screen."""
        try:
            x = self.winfo_x()
            y = self.winfo_y()
            width = self.winfo_width()
            height = self.winfo_height()
        except Exception:
            x = y = width = height = 0
        if width <= 1 or height <= 1:
            width = self._current_width
            height = self._current_height
        return (x, y, width, height)

    def set_geometry(self, x: int, y: int, width: int, height: int) -> None:
        """Move and resize the frame."""
        self.place(x, y, width, height)

    # -----------------------------------------------------------------
    # Appearance
    # -----------------------------------------------------------------
    def set_active(self, active: bool) -> None:
        """Highlight the title bar of the focused window."""
        if active == self._active:
            return
        self._active = active
        color = self._theme.get("titlebar_active" if active else "titlebar")
        self.titlebar.configure(fg_color=color)
        self.title.configure(text_color=self._theme.get("titlebar_fg"))

    def set_title(self, text: str) -> None:
        """Update the title shown in the title bar."""
        self.title.configure(text=text)

    def set_icon(self, image: Image.Image | None, letter: str = "?") -> None:
        """Update the icon shown in the title bar."""
        if image is not None:
            self.icon.set_icon(image)
        else:
            self.icon.set_letter(letter)

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour the decoration after a theme change."""
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.titlebar.configure(
            height=theme.metric("titlebar_height"),
            fg_color=theme.get("titlebar_active" if self._active else "titlebar"),
        )
        self.title.configure(text_color=theme.get("titlebar_fg"))
        self.client_area.configure(bg=theme.get("surface"))
        self.grip.configure(fg_color=theme.get("border_strong"))
        self.icon.set_background(theme.get("accent"))


class DecorationCallbacks:
    """Interface the decoration uses to talk back to the shell."""

    def on_activate(self, client_id: int) -> None:
        """The title bar was clicked; focus the window."""

    def on_close(self, client_id: int) -> None:
        """The close button was pressed."""

    def on_minimize(self, client_id: int) -> None:
        """The minimise button was pressed."""

    def on_maximize(self, client_id: int) -> None:
        """The maximise button was pressed."""

    def on_move(self, client_id: int, x: int, y: int) -> None:
        """The title bar is being dragged."""

    def on_resize(self, client_id: int, width: int, height: int) -> None:
        """The resize grip is being dragged."""

    def on_menu(self, client_id: int, x: int, y: int) -> None:
        """The title bar was right clicked."""


class DecorationManager(DecorationCallbacks):
    """Creates and tracks the decorations of every managed window."""

    def __init__(self, master: ctk.CTk, theme: Theme):
        self._master = master
        self._theme = theme
        self._decorations: dict[int, Decoration] = {}
        self.on_close_requested: Callable[[int], None] | None = None
        self.on_minimize_requested: Callable[[int], None] | None = None
        self.on_maximize_requested: Callable[[int], None] | None = None
        self.on_activate_requested: Callable[[int], None] | None = None
        self.on_move_requested: Callable[[int, int, int], None] | None = None
        self.on_resize_requested: Callable[[int, int, int], None] | None = None
        self.on_menu_requested: Callable[[int, int, int], None] | None = None

    # -----------------------------------------------------------------
    # DecorationHost interface
    # -----------------------------------------------------------------
    def create(self, client: Client) -> int:
        """Create the decoration for ``client`` and return the client area."""
        decoration = Decoration(self._master, self._theme, client, self)
        self._decorations[client.id] = decoration
        # Size and map the frame before the application window is moved
        # into it: reparenting into a window that is not viewable would
        # make the X server unmap the application again.
        decoration.set_geometry(client.x, client.y, client.width, client.height)
        decoration.show()
        decoration.wait_for_client_area()
        return decoration.client_area_xid()

    def destroy(self, client_id: int) -> None:
        """Remove the decoration of a closed window."""
        decoration = self._decorations.pop(client_id, None)
        if decoration is None:
            return
        try:
            decoration.destroy()
        except Exception:
            pass

    def update(self, client: Client) -> None:
        """Refresh the title and icon of a window."""
        decoration = self._decorations.get(client.id)
        if decoration is None:
            return
        decoration.set_title(client.title)
        decoration.set_icon(client.icon_image, _initial(client))

    def set_geometry(self, client_id: int, x: int, y: int, width: int, height: int) -> None:
        decoration = self._decorations.get(client_id)
        if decoration is None:
            return
        decoration.set_geometry(x, y, width, height)

    def set_active(self, client_id: int | None) -> None:
        for window_id, decoration in self._decorations.items():
            decoration.set_active(window_id == client_id)

    def set_visible(self, client_id: int, visible: bool) -> None:
        decoration = self._decorations.get(client_id)
        if decoration is None:
            return
        if visible:
            decoration.show()
        else:
            decoration.hide()

    def raise_client(self, client_id: int) -> None:
        decoration = self._decorations.get(client_id)
        if decoration is None:
            return
        try:
            decoration.lift()
        except Exception:
            pass

    def get_geometry(self, client_id: int) -> tuple[int, int, int, int] | None:
        decoration = self._decorations.get(client_id)
        if decoration is None:
            return None
        return decoration.current_geometry()

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour every decoration."""
        self._theme = theme
        for decoration in self._decorations.values():
            decoration.apply_theme(theme)

    # -----------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------
    def on_activate(self, client_id: int) -> None:
        if self.on_activate_requested is not None:
            self.on_activate_requested(client_id)

    def on_close(self, client_id: int) -> None:
        if self.on_close_requested is not None:
            self.on_close_requested(client_id)

    def on_minimize(self, client_id: int) -> None:
        if self.on_minimize_requested is not None:
            self.on_minimize_requested(client_id)

    def on_maximize(self, client_id: int) -> None:
        if self.on_maximize_requested is not None:
            self.on_maximize_requested(client_id)

    def on_move(self, client_id: int, x: int, y: int) -> None:
        if self.on_move_requested is not None:
            self.on_move_requested(client_id, x, y)

    def on_resize(self, client_id: int, width: int, height: int) -> None:
        if self.on_resize_requested is not None:
            self.on_resize_requested(client_id, width, height)

    def on_menu(self, client_id: int, x: int, y: int) -> None:
        if self.on_menu_requested is not None:
            self.on_menu_requested(client_id, x, y)


def _initial(client: Client) -> str:
    """First letter used for the fallback badge."""
    label_text = (client.title or client.wm_class_name or "?").strip()
    return label_text[:1] if label_text else "?"
