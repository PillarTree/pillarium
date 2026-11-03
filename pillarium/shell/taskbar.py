"""The taskbar.

Pillarium shows one taskbar per monitor.  Each taskbar carries the
launcher button, the pinned quick-launch entries, one button per window
of the current virtual desktop, a virtual desktop switcher, the status
indicators and the clock.
"""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from ..core.clients import Client
from ..core.monitors import Monitor
from ..theme.tokens import Theme
from ..util import glyphs, images
from .base import ShellWindow
from .widgets import Themed, bind_widget

#: Width of a taskbar button showing a window.
ITEM_WIDTH = 148
#: Width of the quick launch buttons.
LAUNCH_WIDTH = 40
#: Width of the status buttons.
STATUS_WIDTH = 36
#: Minimum width of the clock.
CLOCK_WIDTH = 96


class Taskbar(ShellWindow):
    """A taskbar bound to a single monitor."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        monitor: Monitor,
        config: Any,
        callbacks: "TaskbarCallbacks",
    ):
        self._monitor = monitor
        self._config = config
        self._callbacks = callbacks
        self._themed = Themed(theme)
        self._items: dict[int, ctk.CTkButton] = {}
        self._quick_items: list[ctk.CTkButton] = []
        self._desktop_buttons: list[ctk.CTkButton] = []
        self._height = theme.metric("taskbar_height")
        self._position = str(config.opt("taskbar", "position", "bottom"))

        super().__init__(master, theme, fg_token="panel")
        self.configure(fg_color=theme.get("panel"))

        self.bar = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.bar.pack(fill="both", expand=True)

        self.left = ctk.CTkFrame(self.bar, fg_color="transparent", corner_radius=0)
        self.left.pack(side="left", fill="y")

        self.center = ctk.CTkFrame(self.bar, fg_color="transparent", corner_radius=0)
        self.center.pack(side="left", fill="both", expand=True)

        self.right = ctk.CTkFrame(self.bar, fg_color="transparent", corner_radius=0)
        self.right.pack(side="right", fill="y")

        self._build_launcher()
        self._build_status()
        self.apply_position()

    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def _build_launcher(self) -> None:
        self.launcher_button = ctk.CTkButton(
            self.left,
            text="",
            image=images.to_ctk_image(glyphs.launcher_icon(20, theme_color(self._theme))),
            width=LAUNCH_WIDTH,
            height=self._height - 8,
            corner_radius=self._themed.radius(),
            fg_color="transparent",
            hover_color=self._theme.get("panel_hover"),
            command=self._callbacks.on_launcher,
        )
        self.launcher_button.pack(side="left", padx=(6, 2), pady=4)

        self.quick_frame = ctk.CTkFrame(self.left, fg_color="transparent", corner_radius=0)
        self.quick_frame.pack(side="left", fill="y")

    def _build_status(self) -> None:
        self.pager_frame = ctk.CTkFrame(self.right, fg_color="transparent", corner_radius=0)
        self.pager_frame.pack(side="right", padx=(4, 6))

        self.clock_button = ctk.CTkButton(
            self.right,
            text="",
            width=CLOCK_WIDTH,
            height=self._height - 8,
            corner_radius=self._themed.radius(),
            fg_color="transparent",
            hover_color=self._theme.get("panel_hover"),
            text_color=self._theme.get("text"),
            font=self._themed.font(11),
            command=self._callbacks.on_clock,
        )
        self.clock_button.pack(side="right", padx=2, pady=4)

        self.battery_button = self._status_button("battery", self._callbacks.on_battery)
        self.ethernet_button = self._status_button("ethernet", self._callbacks.on_ethernet)
        self.audio_button = self._status_button("audio", self._callbacks.on_audio)
        self.bluetooth_button = self._status_button("bluetooth", self._callbacks.on_bluetooth)
        self.wifi_button = self._status_button("wifi", self._callbacks.on_wifi)
        self.power_button = self._status_button("power", self._callbacks.on_power)

    def _status_button(
        self, kind: str, command: Callable[[], None]
    ) -> ctk.CTkButton:
        widget = ctk.CTkButton(
            self.right,
            text="",
            width=STATUS_WIDTH,
            height=self._height - 8,
            corner_radius=self._themed.radius(),
            fg_color="transparent",
            hover_color=self._theme.get("panel_hover"),
            command=command,
        )
        widget.pack(side="right", padx=1, pady=4)
        return widget

    # -----------------------------------------------------------------
    # Placement
    # -----------------------------------------------------------------
    def apply_position(self) -> None:
        """Move the taskbar to the right edge of its monitor."""
        monitor = self._monitor
        height = self._height
        width = monitor.width
        if self._position == "top":
            x, y = monitor.x, monitor.y
        elif self._position == "left":
            x, y = monitor.x, monitor.y
            width = height
        elif self._position == "right":
            x = monitor.x + monitor.width - height
            y = monitor.y
            width = height
        else:
            x = monitor.x
            y = monitor.y + monitor.height - height
        self.place(x, y, width, height)

    def update_monitor(self, monitor: Monitor) -> None:
        """Follow the monitor after a layout change."""
        self._monitor = monitor
        self.apply_position()

    # -----------------------------------------------------------------
    # Window buttons
    # -----------------------------------------------------------------
    def set_windows(self, clients: list[Client], focused_id: int | None) -> None:
        """Show one button per window of the current desktop."""
        wanted = {client.id: client for client in clients}
        for client_id in list(self._items):
            if client_id not in wanted:
                widget = self._items.pop(client_id)
                try:
                    widget.destroy()
                except Exception:
                    pass
        for client_id, client in wanted.items():
            widget = self._items.get(client_id)
            if widget is None:
                widget = self._make_window_button(client)
                self._items[client_id] = widget
                self.center.pack_configure()  # keep the layout stable
            self._update_window_button(widget, client, client_id == focused_id)

    def _make_window_button(self, client: Client) -> ctk.CTkButton:
        widget = ctk.CTkButton(
            self.center,
            text=client.title[:24],
            width=ITEM_WIDTH,
            height=self._height - 10,
            corner_radius=self._themed.radius(),
            fg_color="transparent",
            hover_color=self._theme.get("panel_hover"),
            text_color=self._theme.get("text"),
            font=self._themed.font(11),
            anchor="w",
        )
        widget.pack(side="left", padx=2, pady=5)
        bind_widget(
            widget,
            "<Button-1>",
            lambda _event, cid=client.id: self._callbacks.on_window(cid),
        )
        bind_widget(
            widget,
            "<Button-3>",
            lambda event, cid=client.id: self._callbacks.on_window_menu(
                cid, event.x_root, event.y_root
            ),
        )
        bind_widget(
            widget,
            "<Double-Button-1>",
            lambda _event, cid=client.id: self._callbacks.on_window(cid),
        )
        return widget

    def _update_window_button(
        self, widget: ctk.CTkButton, client: Client, focused: bool
    ) -> None:
        widget.configure(text=client.title[:24])
        widget.configure(
            fg_color=self._theme.get("accent") if focused else "transparent",
            text_color=self._theme.get("accent_fg") if focused else self._theme.get("text"),
        )
        icon = client.icon_image or images.letter_badge(
            (client.title or "?")[:1].upper(),
            20,
            self._theme.get("accent"),
            self._theme.get("accent_fg"),
        )
        widget.configure(image=images.to_ctk_image(icon))

    # -----------------------------------------------------------------
    # Quick launch
    # -----------------------------------------------------------------
    def set_quick_launch(self, items: list[dict], running: Callable[[dict], bool]) -> None:
        """Rebuild the pinned application buttons."""
        for widget in self._quick_items:
            try:
                widget.destroy()
            except Exception:
                pass
        self._quick_items = []
        for item in items:
            widget = ctk.CTkButton(
                self.quick_frame,
                text="",
                width=LAUNCH_WIDTH,
                height=self._height - 8,
                corner_radius=self._themed.radius(),
                fg_color="transparent",
                hover_color=self._theme.get("panel_hover"),
                command=lambda entry=item: self._callbacks.on_quick_launch(entry),
            )
            icon = images.load_icon(item.get("icon"), 20) or images.letter_badge(
                str(item.get("label", "?"))[:1].upper(),
                20,
                self._theme.get("accent"),
                self._theme.get("accent_fg"),
            )
            widget.configure(image=images.to_ctk_image(icon))
            widget.pack(side="left", padx=1, pady=4)
            self._quick_items.append(widget)
            if running(item):
                widget.configure(fg_color=self._theme.get("select"))

    # -----------------------------------------------------------------
    # Virtual desktop switcher
    # -----------------------------------------------------------------
    def set_desktops(self, count: int, current: int, names: list[str]) -> None:
        """Rebuild the virtual desktop buttons."""
        for widget in self._desktop_buttons:
            try:
                widget.destroy()
            except Exception:
                pass
        self._desktop_buttons = []
        for index in range(count):
            active = index == current
            widget = ctk.CTkButton(
                self.pager_frame,
                text=str(index + 1),
                width=22,
                height=22,
                corner_radius=4,
                fg_color=self._theme.get("accent") if active else "transparent",
                hover_color=self._theme.get("panel_hover"),
                text_color=self._theme.get("accent_fg") if active else self._theme.get("text_dim"),
                font=self._themed.font(10),
                command=lambda idx=index: self._callbacks.on_desktop(idx),
            )
            widget.pack(side="left", padx=1)
            self._desktop_buttons.append(widget)

    # -----------------------------------------------------------------
    # Status indicators
    # -----------------------------------------------------------------
    def set_status(
        self,
        wifi: bool = False,
        bluetooth: bool = False,
        audio: bool = False,
        ethernet: bool = False,
        battery: Any = None,
    ) -> None:
        """Update the status indicators."""
        accent = self._theme.get("accent")
        text = self._theme.get("text")

        self.wifi_button.configure(
            image=images.to_ctk_image(glyphs.wifi_icon(20, text if not wifi else accent, wifi)),
            fg_color=self._theme.get("select") if wifi else "transparent",
        )
        self.bluetooth_button.configure(
            image=images.to_ctk_image(glyphs.bluetooth_icon(20, accent if bluetooth else text, bluetooth)),
            fg_color=self._theme.get("select") if bluetooth else "transparent",
        )
        self.audio_button.configure(
            image=images.to_ctk_image(glyphs.speaker_icon(20, text, not audio)),
            fg_color="transparent",
        )
        self.ethernet_button.configure(
            image=images.to_ctk_image(glyphs.ethernet_icon(20, accent if ethernet else text, ethernet)),
            fg_color=self._theme.get("select") if ethernet else "transparent",
        )
        percent = getattr(battery, "percent", 0) if battery is not None else 0
        available = getattr(battery, "available", False) if battery is not None else False
        charging = getattr(battery, "charging", False) if battery is not None else False
        battery_color = accent
        if available and percent <= 20 and not charging:
            battery_color = self._theme.get("danger")
        self.battery_button.configure(
            image=images.to_ctk_image(
                glyphs.battery_icon(20, battery_color, percent if available else 0, charging)
            ),
            fg_color="transparent",
        )

    def set_clock(self, time_text: str, date_text: str) -> None:
        """Update the clock."""
        self.clock_button.configure(text=f"{time_text}\n{date_text}")

    def set_launcher_active(self, active: bool) -> None:
        """Highlight the launcher button while the launcher is open."""
        self.launcher_button.configure(
            fg_color=self._theme.get("select") if active else "transparent"
        )

    def anchor_for(self, kind: str) -> tuple[int, int]:
        """Screen position of a status button, used to anchor its menu."""
        widget = {
            "wifi": self.wifi_button,
            "bluetooth": self.bluetooth_button,
            "audio": self.audio_button,
            "ethernet": self.ethernet_button,
            "battery": self.battery_button,
            "power": self.power_button,
            "clock": self.clock_button,
            "launcher": self.launcher_button,
        }.get(kind)
        if widget is None:
            return (self.winfo_rootx(), self.winfo_rooty())
        try:
            return (int(widget.winfo_rootx()), int(widget.winfo_rooty()))
        except Exception:
            return (self.winfo_rootx(), self.winfo_rooty())

    def set_audio_muted(self, muted: bool) -> None:
        self.audio_button.configure(
            image=images.to_ctk_image(
                glyphs.speaker_icon(20, self._theme.get("text"), muted)
            )
        )

    # -----------------------------------------------------------------
    # Theme
    # -----------------------------------------------------------------
    def apply_theme(self, theme: Theme) -> None:
        """Re-colour the taskbar."""
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.bar.configure(fg_color="transparent")
        self.apply_position()
        for widget in self._items.values():
            widget.configure(
                fg_color="transparent",
                hover_color=theme.get("panel_hover"),
                text_color=theme.get("text"),
                font=self._themed.font(11),
            )
        for widget in self._quick_items:
            widget.configure(hover_color=theme.get("panel_hover"))
        for widget in self._desktop_buttons:
            widget.configure(hover_color=theme.get("panel_hover"))
        for widget in (
            self.launcher_button,
            self.clock_button,
            self.wifi_button,
            self.bluetooth_button,
            self.audio_button,
            self.ethernet_button,
            self.battery_button,
            self.power_button,
        ):
            widget.configure(hover_color=theme.get("panel_hover"))
        self.clock_button.configure(text_color=theme.get("text"))


class TaskbarCallbacks:
    """Interface the taskbar uses to talk back to the shell."""

    def on_launcher(self) -> None:
        """The launcher button was pressed."""

    def on_quick_launch(self, item: dict) -> None:
        """A pinned application was pressed."""

    def on_window(self, client_id: int) -> None:
        """A window button was pressed."""

    def on_window_menu(self, client_id: int, x: int, y: int) -> None:
        """A window button was right clicked."""

    def on_desktop(self, index: int) -> None:
        """A virtual desktop button was pressed."""

    def on_wifi(self) -> None:
        """The Wi-Fi indicator was pressed."""

    def on_bluetooth(self) -> None:
        """The Bluetooth indicator was pressed."""

    def on_audio(self) -> None:
        """The audio indicator was pressed."""

    def on_ethernet(self) -> None:
        """The Ethernet indicator was pressed."""

    def on_battery(self) -> None:
        """The battery indicator was pressed."""

    def on_clock(self) -> None:
        """The clock was pressed."""

    def on_power(self) -> None:
        """The power button was pressed."""


def theme_color(theme: Theme) -> str:
    """Colour used for the launcher glyph."""
    return theme.get("text")
