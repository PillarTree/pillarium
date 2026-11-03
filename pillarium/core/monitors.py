"""Monitor discovery and hotplug handling.

Pillarium supports an arbitrary number of monitors.  The layout is read
from the X RandR extension: every active output becomes a monitor with
its own geometry, scale and primary flag.

When RandR is unavailable the whole screen is reported as a single
monitor so the rest of the shell keeps working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

try:
    from Xlib.ext import randr
except Exception:  # pragma: no cover - RandR is optional
    randr = None  # type: ignore[assignment]


@dataclass
class Monitor:
    """A single physical (or virtual) output."""

    name: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    primary: bool = False
    index: int = 0
    scale: float = 1.0

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains(self, px: int, py: int) -> bool:
        """Is the point inside this monitor?"""
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def intersection(self, other: "Monitor") -> int:
        """Area shared with ``other``."""
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.x + self.width, other.x + other.width)
        bottom = min(self.y + self.height, other.y + other.height)
        if right <= left or bottom <= top:
            return 0
        return (right - left) * (bottom - top)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Monitor {self.name} {self.width}x{self.height}+{self.x}+{self.y}>"


class MonitorManager:
    """Keeps track of the connected monitors."""

    def __init__(self, display: Any):
        self._display = display
        self._root = display.screen().root
        self._monitors: list[Monitor] = []
        self._listeners: list[Any] = []
        self.refresh()

    # -----------------------------------------------------------------
    # Discovery
    # -----------------------------------------------------------------
    def refresh(self) -> list[Monitor]:
        """Re-read the monitor layout from the X server."""
        monitors = self._enumerate()
        if not monitors:
            monitors = [self._fallback_monitor()]
        self._monitors = monitors
        return monitors

    def _fallback_monitor(self) -> Monitor:
        screen = self._display.screen()
        return Monitor(
            name="screen",
            x=0,
            y=0,
            width=screen.width_in_pixels,
            height=screen.height_in_pixels,
            primary=True,
            index=0,
        )

    def _enumerate(self) -> list[Monitor]:
        if randr is None:
            return []
        try:
            if not self._display.has_extension("RANDR"):
                return []
        except Exception:
            return []

        try:
            reply = randr.get_monitors(self._root)
        except Exception:
            return []

        output_names = self._output_names()
        monitors: list[Monitor] = []
        automatic: list[Monitor] = []
        try:
            entries = list(reply.monitors)
        except Exception:
            entries = []

        for entry in entries:
            try:
                name = self._display.get_atom_name(entry.name)
                name = name.decode() if isinstance(name, bytes) else str(name)
            except Exception:
                name = ""
            crtcs = list(getattr(entry, "crtcs", []) or [])
            names: list[str] = []
            for crtc in crtcs:
                names.extend(output_names.get(crtc, []))
            if not name or name == "screen":
                if names:
                    name = "+".join(names)
                elif not name:
                    name = "monitor"
            monitor = Monitor(
                name=name or "monitor",
                x=int(entry.x),
                y=int(entry.y),
                width=int(entry.width_in_pixels),
                height=int(entry.height_in_pixels),
                primary=bool(entry.primary),
            )
            if getattr(entry, "automatic", 0):
                # The automatic "screen" monitor covers the whole root
                # window; it is only useful when nothing else is set.
                automatic.append(monitor)
            else:
                monitors.append(monitor)

        if not monitors:
            monitors = automatic
        if not monitors:
            monitors = self._enumerate_crtcs()
        return self._sort(monitors)

    def _enumerate_crtcs(self) -> list[Monitor]:
        """Fall back to the CRTC list for RandR versions without monitors."""
        try:
            resources = self._root.xrandr_get_screen_resources()
        except Exception:
            return []
        monitors: list[Monitor] = []
        for crtc in resources.crtcs:
            try:
                info = self._display.xrandr_get_crtc_info(crtc)
            except Exception:
                continue
            if not info.width or not info.height:
                continue
            names = []
            for output_atom in getattr(info, "outputs", []) or []:
                try:
                    output = self._display.xrandr_get_output_info(output_atom)
                except Exception:
                    continue
                if output.connection == 0:  # Connection.Connected
                    names.append(output.name)
            monitors.append(
                Monitor(
                    name="+".join(names) or f"crtc-{crtc}",
                    x=int(info.x),
                    y=int(info.y),
                    width=int(info.width),
                    height=int(info.height),
                    primary=bool(getattr(info, "primary", False)),
                )
            )
        return monitors

    def _output_names(self) -> dict[int, list[str]]:
        """Map CRTC ids to the names of the outputs driving them."""
        mapping: dict[int, list[str]] = {}
        try:
            resources = self._root.xrandr_get_screen_resources()
        except Exception:
            return mapping
        for crtc in resources.crtcs:
            try:
                info = self._display.xrandr_get_crtc_info(crtc)
            except Exception:
                continue
            names: list[str] = []
            for output_atom in getattr(info, "outputs", []) or []:
                try:
                    output = self._display.xrandr_get_output_info(output_atom)
                except Exception:
                    continue
                if output.connection == 0:
                    names.append(output.name)
            if names:
                mapping[crtc] = names
        return mapping

    @staticmethod
    def _sort(monitors: list[Monitor]) -> list[Monitor]:
        monitors.sort(key=lambda mon: (mon.y, mon.x))
        for index, monitor in enumerate(monitors):
            monitor.index = index
        if monitors and not any(monitor.primary for monitor in monitors):
            monitors[0].primary = True
        return monitors

    # -----------------------------------------------------------------
    # Access
    # -----------------------------------------------------------------
    @property
    def monitors(self) -> list[Monitor]:
        return self._monitors

    @property
    def count(self) -> int:
        return len(self._monitors)

    @property
    def primary(self) -> Monitor:
        for monitor in self._monitors:
            if monitor.primary:
                return monitor
        return self._monitors[0]

    def by_name(self, name: str) -> Monitor | None:
        for monitor in self._monitors:
            if monitor.name == name:
                return monitor
        return None

    def by_index(self, index: int) -> Monitor | None:
        if 0 <= index < len(self._monitors):
            return self._monitors[index]
        return None

    def at(self, px: int, py: int) -> Monitor:
        """Monitor containing the point, falling back to the primary one."""
        for monitor in self._monitors:
            if monitor.contains(px, py):
                return monitor
        return self.primary

    def pointer_position(self) -> tuple[int, int]:
        """Current pointer position in root coordinates."""
        try:
            pointer = self._root.query_pointer()
            return int(pointer.root_x), int(pointer.root_y)
        except Exception:
            return self.primary.center

    def pointer_monitor(self) -> Monitor:
        return self.at(*self.pointer_position())

    # -----------------------------------------------------------------
    # Hotplug
    # -----------------------------------------------------------------
    def watch(self) -> bool:
        """Ask the server to send screen-change notifications."""
        if randr is None:
            return False
        try:
            if not self._display.has_extension("RANDR"):
                return False
            self._root.xrandr_select_input(
                randr.RRScreenChangeNotifyMask
                | randr.RRCrtcChangeNotifyMask
                | randr.RROutputChangeNotifyMask
            )
        except Exception:
            return False
        return True

    def on_change(self, listener) -> None:
        """Register a callback invoked when the layout changes."""
        self._listeners.append(listener)

    def notify_changed(self) -> list[Monitor]:
        """Refresh the layout and tell the listeners about it."""
        monitors = self.refresh()
        for listener in list(self._listeners):
            try:
                listener(monitors)
            except Exception:
                continue
        return monitors

    # -----------------------------------------------------------------
    # Geometry helpers
    # -----------------------------------------------------------------
    def work_area(self, monitor: Monitor, taskbar_height: int, position: str = "bottom") -> tuple[int, int, int, int]:
        """Usable area of ``monitor`` once the taskbar is subtracted."""
        x, y, width, height = monitor.rect
        if position == "bottom":
            height = max(120, height - taskbar_height)
        elif position == "top":
            y += taskbar_height
            height = max(120, height - taskbar_height)
        elif position == "left":
            width = max(120, width - taskbar_height)
        elif position == "right":
            x += taskbar_height
            width = max(120, width - taskbar_height)
        return (x, y, width, height)

    @staticmethod
    def clamp_to_monitor(monitor: Monitor, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        """Keep a window rectangle inside ``monitor``."""
        max_x = monitor.x + max(0, monitor.width - width)
        max_y = monitor.y + max(0, monitor.height - height)
        return (
            max(monitor.x, min(x, max_x)),
            max(monitor.y, min(y, max_y)),
        )

    def iter_all(self) -> Iterable[Monitor]:
        return iter(self._monitors)
