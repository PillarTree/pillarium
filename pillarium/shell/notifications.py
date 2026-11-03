"""Desktop notifications rendered as toasts.

Toasts stack upwards in the bottom right corner of the screen, above the
taskbar.  Clicking a toast runs its first action and dismisses it.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import customtkinter as ctk

from ..system.notifications import Notification
from ..theme.tokens import Theme
from .base import ShellWindow
from .widgets import Themed, bind_widget

#: Width of a toast.
TOAST_WIDTH = 360
#: Height of a toast.
TOAST_HEIGHT = 96
#: Vertical gap between two toasts.
TOAST_GAP = 10
#: Maximum number of visible toasts.
MAX_VISIBLE = 5


class Toast(ShellWindow):
    """A single notification."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        notification: Notification,
        on_activate: Callable[[Notification], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._notification = notification
        self._on_activate = on_activate
        self._themed = Themed(theme)
        self._expires_at = time.time() + max(1.0, notification.expire_timeout / 1000)

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        self.accent = ctk.CTkFrame(
            self.container, width=4, fg_color=theme.get("accent"), corner_radius=2
        )
        self.accent.place(relx=0.0, rely=0.0, relheight=1.0)

        body = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        body.place(relx=0.02, rely=0.0, relwidth=0.96, relheight=1.0)

        self.app_label = ctk.CTkLabel(
            body,
            text=notification.app_name,
            text_color=theme.get("text_faint"),
            font=self._themed.font(10),
            anchor="w",
        )
        self.app_label.pack(fill="x", padx=(10, 10), pady=(8, 0))

        self.summary = ctk.CTkLabel(
            body,
            text=notification.summary,
            text_color=theme.get("text"),
            font=self._themed.font(12, "bold"),
            anchor="w",
            justify="left",
            wraplength=TOAST_WIDTH - 44,
        )
        self.summary.pack(fill="x", padx=(10, 10))

        self.detail = ctk.CTkLabel(
            body,
            text=notification.body,
            text_color=theme.get("text_dim"),
            font=self._themed.font(11),
            anchor="w",
            justify="left",
            wraplength=TOAST_WIDTH - 44,
        )
        self.detail.pack(fill="both", expand=True, padx=(10, 10), pady=(2, 8))

        for widget in (self.container, body, self.app_label, self.summary, self.detail):
            bind_widget(widget, "<Button-1>", self._activate)

    def _activate(self, _event: Any = None) -> None:
        """Run the toast's first action and dismiss it."""
        self.dismiss()
        if self._on_activate is not None:
            self._on_activate(self._notification)

    def expired(self) -> bool:
        return time.time() >= self._expires_at

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour the toast after a theme change."""
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(
            fg_color=theme.get("surface"), border_color=theme.get("border")
        )
        self.accent.configure(fg_color=theme.get("accent"))
        self.app_label.configure(text_color=theme.get("text_faint"))
        self.summary.configure(text_color=theme.get("text"))
        self.detail.configure(text_color=theme.get("text_dim"))


class NotificationCenter:
    """Owns the toast stack."""

    def __init__(self, master: ctk.CTk, theme: Theme, monitor_provider: Callable[[], Any]):
        self._master = master
        self._theme = theme
        self._monitor_provider = monitor_provider
        self._toasts: list[Toast] = []
        self._history: list[Notification] = []
        self._on_action: Callable[[Notification, str], None] | None = None

    # -----------------------------------------------------------------
    # Display
    # -----------------------------------------------------------------
    def show(self, notification: Notification) -> Toast | None:
        """Display a notification as a toast."""
        self._history.append(notification)
        if len(self._history) > 100:
            del self._history[:-100]
        if len(self._toasts) >= MAX_VISIBLE:
            self.dismiss(self._toasts[0])
        toast = Toast(self._master, self._theme, notification, self._activate)
        self._toasts.append(toast)
        self._reposition()
        toast.show()
        return toast

    def _activate(self, notification: Notification) -> None:
        """Handle a click on a toast."""
        self.dismiss_by_id(notification.id)
        if not notification.actions:
            return
        action_key = notification.actions[0]
        if self._on_action is not None:
            self._on_action(notification, action_key)

    # -----------------------------------------------------------------
    # Removal
    # -----------------------------------------------------------------
    def dismiss(self, toast: Toast) -> None:
        """Remove a toast from the stack."""
        if toast in self._toasts:
            self._toasts.remove(toast)
        try:
            toast.dismiss()
        except Exception:
            pass
        self._reposition()

    def dismiss_by_id(self, notification_id: int) -> None:
        """Remove every toast belonging to ``notification_id``."""
        for toast in list(self._toasts):
            if toast._notification.id == notification_id:
                self.dismiss(toast)

    def dismiss_all(self) -> None:
        """Remove every toast."""
        for toast in list(self._toasts):
            try:
                toast.dismiss()
            except Exception:
                pass
        self._toasts.clear()

    def tick(self) -> None:
        """Auto-dismiss the toasts whose time is up."""
        for toast in list(self._toasts):
            if toast.expired():
                self.dismiss(toast)

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------
    def _reposition(self) -> None:
        """Stack the toasts upwards above the taskbar."""
        monitor = self._monitor_provider()
        if monitor is None:
            return
        bottom = monitor.y + monitor.height - 48
        right = monitor.x + monitor.width - 16
        y = bottom
        for toast in reversed(self._toasts):
            y -= TOAST_HEIGHT
            toast.place(right - TOAST_WIDTH, y, TOAST_WIDTH, TOAST_HEIGHT)
            y -= TOAST_GAP

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour every visible toast."""
        self._theme = theme
        for toast in self._toasts:
            toast.apply_theme(theme)
