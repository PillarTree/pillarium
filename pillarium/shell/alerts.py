"""Modal alert dialogs.

Alerts are queued: while one dialog is open, further alerts wait their
turn.  Each level has its own colour, glyph and default timeout.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import customtkinter as ctk

from ..theme.tokens import Theme
from .base import ShellWindow
from .widgets import Themed, button

#: Colour token and glyph used for each alert level.
LEVELS: dict[str, dict[str, Any]] = {
    "startup": {"token": "accent", "glyph": "i", "timeout": 6.0},
    "warning": {"token": "warning", "glyph": "!", "timeout": 0.0},
    "error": {"token": "danger", "glyph": "!", "timeout": 0.0},
}

#: Alternative names accepted for each level.
LEVEL_ALIASES: dict[str, str] = {
    "info": "startup",
    "information": "startup",
    "notice": "startup",
    "startup": "startup",
    "warn": "warning",
    "warning": "warning",
    "err": "error",
    "error": "error",
    "critical": "error",
    "fatal": "error",
}

ALERT_WIDTH = 440
ALERT_HEIGHT = 210


@dataclass
class AlertSpec:
    """A queued alert."""

    level: str = "warning"
    title: str = "Pillarium"
    message: str = ""
    app: str = ""
    detail: str = ""
    actions: list[tuple[str, Callable[[], None]]] = field(default_factory=list)
    timeout: float | None = None
    sound: bool = True


class AlertDialog(ShellWindow):
    """The modal alert window."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        spec: AlertSpec,
        on_action: Callable[[Callable[[], None]], None],
        on_dismiss: Callable[[], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._spec = spec
        self._on_action = on_action
        self._on_dismiss = on_dismiss
        self._themed = Themed(theme)
        style = LEVELS.get(spec.level, LEVELS["warning"])
        self._token = style["token"]

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=2,
            border_color=theme.get(self._token),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        header = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", padx=16, pady=(14, 0))

        self.glyph = ctk.CTkLabel(
            header,
            text=str(style["glyph"]),
            width=26,
            height=26,
            corner_radius=13,
            text_color=theme.get("accent_fg"),
            fg_color=theme.get(self._token),
            font=self._themed.font(13, "bold"),
        )
        self.glyph.pack(side="left")

        self.title_label = ctk.CTkLabel(
            header,
            text=spec.title,
            text_color=theme.get("text"),
            font=self._themed.font(14, "bold"),
            anchor="w",
        )
        self.title_label.pack(side="left", padx=(10, 0))

        self.message = ctk.CTkLabel(
            self.container,
            text=spec.message,
            text_color=theme.get("text_dim"),
            font=self._themed.font(12),
            anchor="w",
            justify="left",
            wraplength=ALERT_WIDTH - 44,
        )
        self.message.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        self.detail = ctk.CTkLabel(
            self.container,
            text=spec.detail or (f"Application: {spec.app}" if spec.app else ""),
            text_color=theme.get("text_faint"),
            font=self._themed.font(11),
            anchor="w",
            justify="left",
            wraplength=ALERT_WIDTH - 44,
        )
        self.detail.pack(fill="x", padx=16)

        self.buttons = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        self.buttons.pack(fill="x", padx=16, pady=14)

        actions = spec.actions or [("OK", lambda: None)]
        for index, (label, callback) in enumerate(actions):
            widget = button(
                self.buttons,
                self._themed,
                label,
                lambda cb=callback: self._on_action(cb),
                accent=index == 0,
                width=110,
            )
            widget.pack(side="right", padx=(8, 0))

        self.bind("<Escape>", lambda _event: self._dismiss())
        self.bind("<Return>", lambda _event: self._activate_default())
        self.bind("<space>", lambda _event: self._activate_default())

    def _activate_default(self) -> str:
        actions = self._spec.actions or [("OK", lambda: None)]
        self._on_action(actions[0][1])
        return "break"

    def _dismiss(self) -> None:
        self._on_dismiss()


class AlertManager:
    """Queues alerts and shows them one at a time."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        on_sound: Callable[[str], None] | None = None,
        on_focus: Callable[[int], None] | None = None,
        on_release: Callable[[], None] | None = None,
    ):
        self._master = master
        self._theme = theme
        self._on_sound = on_sound
        self._on_focus = on_focus
        self._on_release = on_release
        self._queue: list[AlertSpec] = []
        self._current: AlertDialog | None = None
        self._current_spec: AlertSpec | None = None
        self._expires_at = 0.0
        self._recent: dict[tuple[str, str, str, str], float] = {}

    # -----------------------------------------------------------------
    # Queue
    # -----------------------------------------------------------------
    def show(self, spec: AlertSpec) -> None:
        """Queue an alert."""
        level = LEVEL_ALIASES.get(spec.level.lower(), "warning")
        spec.level = level
        if spec.timeout is None:
            spec.timeout = float(LEVELS[level]["timeout"])

        key = (level, spec.title, spec.message, spec.app)
        now = time.time()
        previous = self._recent.get(key)
        if previous is not None and now - previous < 3.0:
            return
        self._recent[key] = now
        for stale in [entry for entry, stamp in self._recent.items() if now - stamp > 30.0]:
            self._recent.pop(stale, None)
        if len(self._recent) > 64:
            self._recent.pop(next(iter(self._recent)), None)

        self._queue.append(spec)
        self._present_next()

    def _present_next(self) -> None:
        if self._current is not None or not self._queue:
            return
        spec = self._queue.pop(0)
        self._current_spec = spec
        if spec.sound and self._on_sound is not None:
            self._on_sound(spec.level)
        self._current = AlertDialog(
            self._master, self._theme, spec, self._run_action, self._close_current
        )
        self._center()
        self._current.show()
        if self._on_focus is not None:
            self._request_focus(self._current)
        timeout = spec.timeout or 0.0
        self._expires_at = time.time() + timeout if timeout > 0 else 0.0

    def _request_focus(self, dialog: AlertDialog) -> None:
        """Move the keyboard to the dialog, once it is mapped."""

        def apply() -> None:
            xid = dialog.take_focus()
            if xid and self._on_focus is not None:
                self._on_focus(xid)

        apply()
        try:
            self._master.after(60, apply)
        except Exception:
            pass

    def _center(self) -> None:
        if self._current is None:
            return
        screen_w = self._current.winfo_screenwidth()
        screen_h = self._current.winfo_screenheight()
        x = (screen_w - ALERT_WIDTH) // 2
        y = (screen_h - ALERT_HEIGHT) // 3
        self._current.place(x, y, ALERT_WIDTH, ALERT_HEIGHT)

    def _run_action(self, callback: Callable[[], None]) -> None:
        self._close_current()
        try:
            callback()
        except Exception:
            pass
        self._present_next()

    def _close_current(self) -> None:
        if self._current is not None:
            try:
                self._current.dismiss()
            except Exception:
                pass
            self._current = None
        self._current_spec = None
        self._expires_at = 0.0
        if self._on_release is not None:
            try:
                self._on_release()
            except Exception:
                pass
        self._present_next()

    # -----------------------------------------------------------------
    # Housekeeping
    # -----------------------------------------------------------------
    def tick(self) -> None:
        """Auto-dismiss the current alert when its time is up."""
        if self._current is None or not self._expires_at:
            return
        if time.time() >= self._expires_at:
            self._close_current()

    @property
    def visible(self) -> bool:
        return self._current is not None

    def close_all(self) -> None:
        """Close the current alert and drop the queue."""
        self._queue.clear()
        self._close_current()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._current is not None:
            self._current.apply_theme(theme)
