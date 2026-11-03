"""The application launcher.

A fuzzy-searchable list of every installed application, opened with the
taskbar button or the ``Alt+Space`` shortcut.
"""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from ..theme.tokens import Theme
from ..util import images
from .base import ShellWindow
from .widgets import Themed, bind_widget

#: Width of the launcher window.
LAUNCHER_WIDTH = 420
#: Height of a result row.
ROW_HEIGHT = 38
#: Maximum number of results kept in memory.
MAX_RESULTS = 200
#: Number of applications listed before the user types something.
DEFAULT_RESULTS = 60


def score(entry: dict, query: str) -> int:
    """Score a search entry against ``query``.

    Higher scores are better matches; ``-1`` means "no match".
    """
    if not query:
        return 0
    label = str(entry.get("label", "")).lower()
    command = " ".join(entry.get("cmd") or []).lower()
    query = query.lower()

    if label == query:
        return 1000
    if command == query:
        return 950
    if label.startswith(query):
        return 900 - (len(label) - len(query))
    if command.startswith(query):
        return 850 - (len(command) - len(query))
    if query in label:
        index = label.index(query)
        word_start = index == 0 or label[index - 1] in " -_./"
        return (700 if word_start else 600) - index
    if query in command:
        return 550
    # Character level fuzzy match.
    position = 0
    matched = 0
    for char in query:
        found = label.find(char, position)
        if found < 0:
            continue
        matched += 1
        position = found + 1
    if matched == len(query):
        return 400 - position
    if matched >= max(3, len(query) - 1):
        return 200 - position
    return -1


class Launcher(ShellWindow):
    """The application search popup."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        on_launch: Callable[[dict], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._on_launch = on_launch
        self._themed = Themed(theme)
        self._entries: list[dict] = []
        self._results: list[dict] = []
        self._selected = 0
        self._provider: Callable[[], list[dict]] | None = None

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        self.search = ctk.CTkEntry(
            self.container,
            placeholder_text="Search applications...",
            height=32,
            corner_radius=self._themed.radius(),
            fg_color=theme.get("surface_alt"),
            text_color=theme.get("text"),
            placeholder_text_color=theme.get("text_faint"),
            border_color=theme.get("border_strong"),
            font=self._themed.font(),
        )
        self.search.pack(fill="x", padx=8, pady=(8, 4))
        bind_widget(self.search, "<KeyPress>", self._on_key)

        self.results_frame = ctk.CTkScrollableFrame(
            self.container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=theme.get("border_strong"),
            scrollbar_button_hover_color=theme.get("accent"),
        )
        self.results_frame.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        self.status = ctk.CTkLabel(
            self.container,
            text="",
            text_color=theme.get("text_faint"),
            font=self._themed.font(11),
        )
        self.status.pack(pady=(0, 6))

        self.bind_escape()

    # -----------------------------------------------------------------
    # Content
    # -----------------------------------------------------------------
    def set_provider(self, provider: Callable[[], list[dict]]) -> None:
        """Register the callable that produces the search corpus."""
        self._provider = provider

    def open(self, x: int, y: int, screen: tuple[int, int] | None = None) -> None:
        """Show the launcher and refresh the application list."""
        self.refresh()
        height = 460
        width = LAUNCHER_WIDTH
        if screen is not None:
            screen_w, screen_h = screen
            height = min(height, screen_h - 80)
            x = max(0, min(x, screen_w - width))
            y = max(0, min(y, screen_h - height))
        self.place(x, y, width, height)
        self.show()
        self.search.focus_force()
        self.search.delete(0, "end")

    def refresh(self) -> None:
        """Re-read the application catalogue."""
        if self._provider is not None:
            try:
                self._entries = list(self._provider())
            except Exception:
                self._entries = []
        self._apply_query()

    def _apply_query(self) -> None:
        query = self.search.get().strip()
        if query:
            scored = []
            for entry in self._entries:
                value = score(entry, query)
                if value >= 0:
                    scored.append((value, entry))
            scored.sort(key=lambda item: (-item[0], str(item[1].get("label", "")).lower()))
            self._results = [entry for _value, entry in scored[:MAX_RESULTS]]
        else:
            self._results = list(self._entries[:DEFAULT_RESULTS])
        self._selected = 0
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        for child in self.results_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        if not self._results:
            message = (
                "No matches"
                if self.search.get().strip()
                else "No applications found"
            )
            self.status.configure(text=message)
            return

        self.status.configure(text=f"{len(self._results)} applications")
        for index, entry in enumerate(self._results):
            row = ctk.CTkButton(
                self.results_frame,
                text="",
                height=ROW_HEIGHT - 6,
                anchor="w",
                corner_radius=4,
                fg_color="transparent",
                hover_color=self._theme.get("panel_hover"),
                font=self._themed.font(),
                command=lambda item=entry: self._launch(item),
            )
            icon = images.load_icon(entry.get("icon"), 22) or images.letter_badge(
                str(entry.get("label", "?"))[:1].upper(),
                22,
                self._theme.get("accent"),
                self._theme.get("accent_fg"),
            )
            row.configure(image=images.to_ctk_image(icon), text=str(entry.get("label", "")))
            row.pack(fill="x", padx=2, pady=1)
            bind_widget(row, "<Button-1>", lambda _event, item=entry: self._launch(item))

    # -----------------------------------------------------------------
    # Interaction
    # -----------------------------------------------------------------
    def _on_key(self, event: Any) -> None:
        key = event.keysym
        if key in ("Up", "KP_Up"):
            self._move(-1)
            return "break"
        if key in ("Down", "KP_Down"):
            self._move(1)
            return "break"
        if key in ("Return", "KP_Enter"):
            self._launch_selected()
            return "break"
        if key == "Escape":
            self.dismiss()
            return "break"
        if key == "BackSpace":
            self.search.after_idle(self._apply_query)
            return None
        self.search.after_idle(self._apply_query)
        return None

    def _move(self, delta: int) -> None:
        if not self._results:
            return
        self._selected = max(0, min(len(self._results) - 1, self._selected + delta))
        children = self.results_frame.winfo_children()
        if 0 <= self._selected < len(children):
            children[self._selected].focus_set()

    def _launch_selected(self) -> None:
        if 0 <= self._selected < len(self._results):
            self._launch(self._results[self._selected])

    def _launch(self, entry: dict) -> None:
        self.dismiss()
        if self._on_launch is not None:
            self._on_launch(entry)

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(fg_color=theme.get("surface"))
        self.search.configure(
            fg_color=theme.get("surface_alt"),
            text_color=theme.get("text"),
            border_color=theme.get("border_strong"),
        )
        self._rebuild_rows()
