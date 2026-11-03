"""Base classes for Pillarium's floating windows.

Every panel, menu, dialog and decoration is a ``ctk.CTkToplevel`` in
override-redirect mode.  Override-redirect windows are never touched by
the X window manager - which in this case is Pillarium itself - so the
shell keeps full control over their geometry and stacking.
"""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from ..theme.tokens import Theme


class ShellWindow(ctk.CTkToplevel):
    """A borderless, always-on-top window used by the shell."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        width: int = 320,
        height: int = 240,
        fg_token: str = "panel",
        font: ctk.CTkFont | None = None,
    ):
        super().__init__(master)
        self._theme = theme
        self._fg_token = fg_token
        self.overrideredirect(True)
        self.configure(fg_color=theme.get(fg_token))
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._font = font or ctk.CTkFont(
            family=theme.font("ui"), size=theme.metric("font_size")
        )
        self._dismiss_callbacks: list[Callable[[], None]] = []
        self.withdraw()

    # -----------------------------------------------------------------
    # Theme
    # -----------------------------------------------------------------
    @property
    def theme(self) -> Theme:
        return self._theme

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour the window after a theme change."""
        self._theme = theme
        self.configure(fg_color=theme.get(self._fg_token))
        self._font = ctk.CTkFont(
            family=theme.font("ui"), size=theme.metric("font_size")
        )

    # -----------------------------------------------------------------
    # Geometry
    # -----------------------------------------------------------------
    def place(self, x: int, y: int, width: int | None = None, height: int | None = None) -> None:
        """Move and optionally resize the window."""
        if width is None or height is None:
            try:
                self.geometry(f"+{int(x)}+{int(y)}")
            except Exception:
                pass
            return
        try:
            # Without a minimum size the toolkit shrinks the window to
            # the size its content asks for, which can cut buttons off.
            self.minsize(int(width), int(height))
        except Exception:
            pass
        try:
            self.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")
        except Exception:
            pass

    def resize(self, width: int, height: int) -> None:
        """Resize the window without moving it."""
        try:
            self.geometry(f"{int(width)}x{int(height)}")
        except Exception:
            pass

    def show(self) -> None:
        """Map the window and raise it."""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.update_idletasks()
        except Exception:
            pass

    def hide(self) -> None:
        """Unmap the window."""
        try:
            self.withdraw()
        except Exception:
            pass

    def is_visible(self) -> bool:
        try:
            return bool(self.state() != "withdrawn")
        except Exception:
            return False

    # -----------------------------------------------------------------
    # Dismissal
    # -----------------------------------------------------------------
    def on_dismiss(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked when the window is dismissed."""
        self._dismiss_callbacks.append(callback)

    def dismiss(self) -> None:
        """Close the window and run the dismissal callbacks."""
        self.hide()
        for callback in list(self._dismiss_callbacks):
            try:
                callback()
            except Exception:
                continue

    def dispose(self) -> None:
        """Close the window for good and drop the dismissal callbacks."""
        self.dismiss()
        self._dismiss_callbacks.clear()

    def bind_escape(self) -> None:
        """Close the window when Escape is pressed."""
        self.bind("<Escape>", lambda _event: self.dismiss())

    def bind_focus_out(self, callback: Callable[[], None]) -> None:
        """Run ``callback`` when the window loses the keyboard focus."""
        self.bind("<FocusOut>", lambda _event: callback())

    def take_focus(self, widget: Any = None) -> int:
        """Prepare this window to receive key presses.

        customtkinter windows are override-redirect, so the X server
        will not hand them the keyboard on its own.  The toolkit needs
        the focus for its own bookkeeping and the X server needs to be
        told about it separately.  Returns the X window id that should
        receive the focus.

        The focus can only be moved once the window is mapped, so
        callers should repeat the call shortly after showing a window.
        """
        target = widget if widget is not None else self
        try:
            target.focus_force()
        except Exception:
            return 0
        inner = getattr(target, "_entry", None)
        if inner is not None:
            try:
                return int(inner.winfo_id())
            except Exception:
                pass
        try:
            return int(target.winfo_id())
        except Exception:
            return 0


class TransientManager:
    """Keeps track of the panels that are currently open.

    Opening a new transient window closes the previous one, which gives
    the shell the "only one popup at a time" behaviour users expect.
    """

    def __init__(self) -> None:
        self._windows: list[ShellWindow] = []

    def register(self, window: ShellWindow) -> ShellWindow:
        """Remember ``window`` as the active transient window."""
        self.close_all(exclude=window)
        self._windows.append(window)
        return window

    def unregister(self, window: ShellWindow) -> None:
        if window in self._windows:
            self._windows.remove(window)

    def close_all(self, exclude: ShellWindow | None = None) -> None:
        """Close every transient window except ``exclude``."""
        for window in list(self._windows):
            if window is exclude:
                continue
            try:
                window.dismiss()
            except Exception:
                pass
        self._windows = [window for window in self._windows if window is exclude]

    @property
    def current(self) -> ShellWindow | None:
        return self._windows[-1] if self._windows else None

    def any_visible(self) -> bool:
        return any(window.is_visible() for window in self._windows)
