"""Side panels: audio mixer, process manager and calendar."""

from __future__ import annotations

import calendar as calendar_module
import datetime
from typing import Any, Callable

import customtkinter as ctk

from ..theme.tokens import Theme
from ..util import glyphs, images
from .base import ShellWindow
from .widgets import Themed, button, label

MIXER_WIDTH = 380
PROC_WIDTH = 460
CAL_WIDTH = 300


class AudioMixer(ShellWindow):
    """Volume control for every sink and playing stream."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        on_change: Callable[[], None],
        on_mute: Callable[[Any], None],
        on_volume: Callable[[Any, int], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._themed = Themed(theme)
        self._on_change = on_change
        self._on_mute = on_mute
        self._on_volume = on_volume
        self._rows: list[ctk.CTkSlider] = []
        self._nodes: list[Any] = []

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        self.header = label(self.container, self._themed, "Audio Mixer", weight="bold")
        self.header.pack(anchor="w", padx=14, pady=(12, 2))

        self.body = ctk.CTkScrollableFrame(
            self.container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=theme.get("border_strong"),
            scrollbar_button_hover_color=theme.get("accent"),
        )
        self.body.pack(fill="both", expand=True, padx=6, pady=6)

        self.bind_escape()

    # -----------------------------------------------------------------
    # Content
    # -----------------------------------------------------------------
    def set_nodes(self, sinks: list[Any], streams: list[Any]) -> None:
        """Rebuild the list of controllable nodes."""
        for child in self.body.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._rows = []
        self._nodes = []

        if sinks:
            self._add_header("Output Devices")
            for node in sinks:
                self._add_node(node)
        if streams:
            self._add_header("Applications")
            for node in streams:
                self._add_node(node)
        if not sinks and not streams:
            label(self.body, self._themed, "No audio devices found", color_token="text_dim").pack(
                anchor="w", padx=10, pady=10
            )

    def _add_header(self, text: str) -> None:
        label(self.body, self._themed, text, color_token="text_faint", size=11).pack(
            anchor="w", padx=10, pady=(8, 2)
        )

    def _add_node(self, node: Any) -> None:
        row = ctk.CTkFrame(self.body, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=4, pady=2)
        self._nodes.append(node)

        mute = ctk.CTkButton(
            row,
            text="",
            width=28,
            height=28,
            corner_radius=4,
            fg_color="transparent",
            hover_color=self._theme.get("panel_hover"),
            image=images.to_ctk_image(
                glyphs.speaker_icon(18, self._theme.get("text"), getattr(node, "muted", False))
            ),
            command=lambda item=node: self._on_mute(item),
        )
        mute.pack(side="left")

        name = label(row, self._themed, str(getattr(node, "name", ""))[:24])
        name.pack(side="left", padx=6)

        slider = ctk.CTkSlider(
            row,
            from_=0,
            to=150,
            width=160,
            height=16,
            button_color=self._theme.get("accent"),
            progress_color=self._theme.get("accent"),
            fg_color=self._theme.get("surface_alt"),
            command=lambda value, item=node: self._on_volume(item, int(value)),
        )
        slider.set(max(0, min(150, int(getattr(node, "volume", 0)))))
        slider.pack(side="right", padx=(4, 8))
        self._rows.append(slider)

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(fg_color=theme.get("surface"))
        self.set_nodes(
            [node for node in self._nodes if not node.is_stream],
            [node for node in self._nodes if node.is_stream],
        )


class ProcessPanel(ShellWindow):
    """The system process list."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        on_kill: Callable[[int], None],
        on_refresh: Callable[[], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._themed = Themed(theme)
        self._on_kill = on_kill
        self._on_refresh = on_refresh
        self._processes: list[Any] = []

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
        label(header, self._themed, "Processes", weight="bold").pack(side="left")
        button(
            header,
            self._themed,
            "Refresh",
            self._on_refresh,
            width=80,
            height=24,
        ).pack(side="right")

        self.body = ctk.CTkScrollableFrame(
            self.container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=theme.get("border_strong"),
            scrollbar_button_hover_color=theme.get("accent"),
        )
        self.body.pack(fill="both", expand=True, padx=6, pady=6)

        self.bind_escape()

    def set_processes(self, processes: list[Any]) -> None:
        """Rebuild the process list."""
        self._processes = processes
        for child in self.body.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        for process in processes:
            row = ctk.CTkFrame(self.body, fg_color="transparent", corner_radius=0)
            row.pack(fill="x", padx=4, pady=1)
            label(row, self._themed, str(process.name)[:22]).pack(side="left", padx=(8, 4))
            label(
                row, self._themed, f"{process.cpu:5.1f}", color_token="text_dim", size=11, mono=True
            ).pack(side="left")
            label(
                row, self._themed, f"{process.memory:5.1f}", color_token="text_dim", size=11, mono=True
            ).pack(side="left")
            label(
                row, self._themed, str(process.pid), color_token="text_faint", size=11, mono=True
            ).pack(side="left")
            button(
                row,
                self._themed,
                "Kill",
                lambda pid=process.pid: self._on_kill(pid),
                width=54,
                height=22,
            ).pack(side="right", padx=6)

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(fg_color=theme.get("surface"))
        self.set_processes(self._processes)


class CalendarPanel(ShellWindow):
    """A month calendar with day selection."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        on_processes: Callable[[], None],
    ):
        super().__init__(master, theme, fg_token="surface")
        self._themed = Themed(theme)
        self._on_processes = on_processes
        today = datetime.date.today()
        self._year = today.year
        self._month = today.month
        self._selected = today.day
        self._day_buttons: dict[int, ctk.CTkButton] = {}

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        header = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", padx=10, pady=(10, 4))
        self.prev_button = button(
            header, self._themed, "‹", lambda: self._navigate(-1), width=28, height=24
        )
        self.prev_button.pack(side="left")
        self.title = label(header, self._themed, "", weight="bold")
        self.title.pack(side="left", fill="x", expand=True)
        self.next_button = button(
            header, self._themed, "›", lambda: self._navigate(1), width=28, height=24
        )
        self.next_button.pack(side="right")

        self.grid = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        self.grid.pack(fill="both", expand=True, padx=8, pady=4)

        for column, name in enumerate(("M", "T", "W", "T", "F", "S", "S")):
            label(
                self.grid,
                self._themed,
                name,
                color_token="text_faint",
                size=11,
            ).grid(row=0, column=column, padx=2, pady=2)

        footer = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        footer.pack(fill="x", padx=10, pady=(4, 10))
        button(
            footer, self._themed, "Open Process Manager", self._on_processes, width=170, height=26
        ).pack(side="left")

        self.bind_escape()
        self.refresh()

    # -----------------------------------------------------------------
    # Content
    # -----------------------------------------------------------------
    def refresh(self) -> None:
        """Redraw the month grid."""
        self.title.configure(text=f"{calendar_module.month_name[self._month]} {self._year}")
        for widget in self._day_buttons.values():
            try:
                widget.destroy()
            except Exception:
                pass
        self._day_buttons = {}

        today = datetime.date.today()
        days = calendar_module.Calendar(firstweekday=0).monthdayscalendar(self._year, self._month)
        for row, week in enumerate(days):
            for column, day in enumerate(week):
                if day == 0:
                    continue
                is_today = (
                    today.year == self._year
                    and today.month == self._month
                    and today.day == day
                )
                is_selected = day == self._selected
                widget = ctk.CTkButton(
                    self.grid,
                    text=str(day),
                    width=34,
                    height=28,
                    corner_radius=4,
                    fg_color=self._theme.get("accent")
                    if is_today
                    else ("transparent"),
                    hover_color=self._theme.get("panel_hover"),
                    text_color=self._theme.get("accent_fg")
                    if is_today
                    else self._theme.get("text"),
                    border_width=1
                    if is_selected and not is_today
                    else 0,
                    border_color=self._theme.get("accent"),
                    font=self._themed.font(11),
                    command=lambda value=day: self._select_day(value),
                )
                widget.grid(row=row + 1, column=column, padx=1, pady=1)
                self._day_buttons[day] = widget

    def _select_day(self, day: int) -> None:
        self._selected = day
        self.refresh()

    def _navigate(self, delta: int) -> None:
        self._month += delta
        while self._month > 12:
            self._month -= 12
            self._year += 1
        while self._month < 1:
            self._month += 12
            self._year -= 1
        self.refresh()

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(fg_color=theme.get("surface"))
        self.refresh()
