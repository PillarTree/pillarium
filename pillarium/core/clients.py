"""The model of a managed application window."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Client:
    """Everything Pillarium knows about a managed X11 window."""

    id: int
    window: Any
    title: str = "Window"
    wm_class: list[str] = field(default_factory=list)
    icon_name: str | None = None
    icon_image: Any = None
    desktop: int = 0
    minimized: bool = False
    maximized: bool = False
    x: int = 0
    y: int = 0
    width: int = 760
    height: int = 520
    restore_geometry: tuple[int, int, int, int] | None = None
    monitor: str = ""
    ping_supported: bool = False
    unresponsive: bool = False
    last_ping: float = 0.0
    pinned: bool = False

    # -----------------------------------------------------------------
    # Derived values
    # -----------------------------------------------------------------
    @property
    def wm_class_name(self) -> str:
        """The most likely class name of the application."""
        if not self.wm_class:
            return ""
        return self.wm_class[-1]

    @property
    def geometry(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def matches_class(self, candidate: str) -> bool:
        """Does ``candidate`` name this application?"""
        lowered = candidate.lower()
        return any(lowered in entry.lower() for entry in self.wm_class)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Client {self.id} {self.title!r}>"
