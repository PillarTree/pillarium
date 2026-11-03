"""Theme tokens and the built-in Pillarium palettes.

A :class:`Theme` is a flat mapping of colour tokens plus a handful of
metrics.  Colours are stored as ``#rrggbb`` strings so they can be handed
straight to customtkinter, Pillow and X11 alike.

User themes are ordinary :class:`Theme` instances loaded from JSON files
in ``$PILLARIUM_HOME/themes``; see :mod:`pillarium.theme.manager`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Iterator

#: Every colour token a theme is expected to define.
COLOR_TOKENS: tuple[str, ...] = (
    "bg",
    "surface",
    "surface_alt",
    "panel",
    "panel_hover",
    "border",
    "border_strong",
    "text",
    "text_dim",
    "text_faint",
    "accent",
    "accent_hover",
    "accent_fg",
    "select",
    "success",
    "warning",
    "danger",
    "titlebar",
    "titlebar_active",
    "titlebar_fg",
    "overlay",
)

#: Every metric a theme may override.
METRIC_TOKENS: tuple[str, ...] = (
    "radius",
    "taskbar_height",
    "titlebar_height",
    "border_width",
    "font_size",
    "icon_size",
    "panel_padding",
)

DEFAULT_METRICS: dict[str, int] = {
    "radius": 8,
    "taskbar_height": 38,
    "titlebar_height": 34,
    "border_width": 1,
    "font_size": 13,
    "icon_size": 22,
    "panel_padding": 8,
}

#: Colours used for tokens a theme does not define.  Declared before
#: :class:`Theme` so the class can use it while the built-ins are still
#: being constructed.
FALLBACK_COLORS: dict[str, str] = {
    "bg": "#1b1f27",
    "surface": "#232833",
    "surface_alt": "#1e232d",
    "panel": "#2b313d",
    "panel_hover": "#39414f",
    "border": "#171b23",
    "border_strong": "#454e5f",
    "text": "#d9dee9",
    "text_dim": "#96a0b3",
    "text_faint": "#6b7488",
    "accent": "#5e81ac",
    "accent_hover": "#7296c4",
    "accent_fg": "#0e1218",
    "select": "#3b4659",
    "success": "#a3be8c",
    "warning": "#ebcb8b",
    "danger": "#bf616a",
    "titlebar": "#2b313d",
    "titlebar_active": "#3b4659",
    "titlebar_fg": "#d9dee9",
    "overlay": "#10141b",
}


@dataclass
class Theme:
    """A named palette with metrics."""

    name: str
    mode: str = "dark"
    colors: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_METRICS))
    fonts: dict[str, str] = field(default_factory=dict)
    builtin: bool = True
    slug: str = ""

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = _slugify(self.name)
        # Unknown tokens are preserved but never used; missing tokens fall
        # back to the dark palette so a partially specified theme still
        # renders sensibly.
        merged = dict(FALLBACK_COLORS)
        merged.update(self.colors)
        self.colors = merged
        metrics = dict(DEFAULT_METRICS)
        metrics.update(self.metrics)
        self.metrics = metrics

    # -----------------------------------------------------------------
    # Access helpers
    # -----------------------------------------------------------------
    def __getitem__(self, token: str) -> str:
        return self.colors.get(token, BUILTIN_DARK.colors.get(token, "#ffffff"))

    def get(self, token: str, default: str | None = None) -> str:
        if token in self.colors:
            return self.colors[token]
        if default is not None:
            return default
        return BUILTIN_DARK.colors.get(token, "#ffffff")

    def metric(self, token: str, default: int | None = None) -> int:
        if token in self.metrics:
            return self.metrics[token]
        if default is not None:
            return default
        return DEFAULT_METRICS.get(token, 0)

    def font(self, token: str = "ui") -> str | None:
        """Font family for ``token`` (``ui``, ``mono``, ``title``)."""
        return self.fonts.get(token)

    # -----------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "colors": dict(self.colors),
            "metrics": dict(self.metrics),
            "fonts": dict(self.fonts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, builtin: bool = False) -> "Theme":
        colors = data.get("colors")
        metrics = data.get("metrics")
        fonts = data.get("fonts")
        return cls(
            name=str(data.get("name") or "Custom"),
            mode=str(data.get("mode") or "dark"),
            colors={str(k): str(v) for k, v in colors.items()} if isinstance(colors, dict) else {},
            metrics={str(k): int(v) for k, v in metrics.items()} if isinstance(metrics, dict) else {},
            fonts={str(k): str(v) for k, v in fonts.items()} if isinstance(fonts, dict) else {},
            builtin=builtin,
            slug=str(data.get("slug") or ""),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def copy(self, name: str | None = None) -> "Theme":
        clone = replace(
            self,
            colors=dict(self.colors),
            metrics=dict(self.metrics),
            fonts=dict(self.fonts),
        )
        if name:
            clone.name = name
            clone.slug = _slugify(name)
            clone.builtin = False
        return clone

    # -----------------------------------------------------------------
    # Derived colours
    # -----------------------------------------------------------------
    def with_alpha(self, token: str, alpha: float) -> str:
        """Return ``token`` as an ``#rrggbbaa`` string."""
        red, green, blue = hex_to_rgb(self[token])
        return f"#{red:02x}{green:02x}{blue:02x}{max(0, min(255, int(alpha * 255))):02x}"

    def lighten(self, token: str, amount: float = 0.08) -> str:
        red, green, blue = hex_to_rgb(self[token])
        red = int(red + (255 - red) * amount)
        green = int(green + (255 - green) * amount)
        blue = int(blue + (255 - blue) * amount)
        return f"#{red:02x}{green:02x}{blue:02x}"

    def darken(self, token: str, amount: float = 0.08) -> str:
        red, green, blue = hex_to_rgb(self[token])
        return f"#{int(red * (1 - amount)):02x}{int(green * (1 - amount)):02x}{int(blue * (1 - amount)):02x}"

    def __iter__(self) -> Iterator[str]:
        return iter(self.colors)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Theme {self.name!r} mode={self.mode!r}>"


def _slugify(name: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in name.lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "custom"


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Parse ``#rgb`` / ``#rrggbb`` into an ``(r, g, b)`` tuple."""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) >= 6:
        try:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            pass
    return 255, 255, 255


def rgb_to_hex(red: int, green: int, blue: int) -> str:
    """Convert an RGB triple into ``#rrggbb``."""
    return f"#{max(0, min(255, int(red))):02x}{max(0, min(255, int(green))):02x}{max(0, min(255, int(blue))):02x}"


def relative_luminance(value: str) -> float:
    """WCAG relative luminance of a colour, used to pick readable text."""
    channels = []
    for component in hex_to_rgb(value):
        channel = component / 255.0
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrasting_text(background: str, light: str = "#ffffff", dark: str = "#101216") -> str:
    """Pick the more readable of ``light``/``dark`` for ``background``."""
    return light if relative_luminance(background) < 0.45 else dark


# ---------------------------------------------------------------------------
# Built-in palettes
# ---------------------------------------------------------------------------
BUILTIN_DARK = Theme(
    name="Dark",
    mode="dark",
    builtin=True,
    slug="dark",
    colors={
        "bg": "#1b1f27",
        "surface": "#232833",
        "surface_alt": "#1e232d",
        "panel": "#2b313d",
        "panel_hover": "#39414f",
        "border": "#171b23",
        "border_strong": "#454e5f",
        "text": "#d9dee9",
        "text_dim": "#96a0b3",
        "text_faint": "#6b7488",
        "accent": "#5e81ac",
        "accent_hover": "#7296c4",
        "accent_fg": "#0e1218",
        "select": "#3b4659",
        "success": "#a3be8c",
        "warning": "#ebcb8b",
        "danger": "#bf616a",
        "titlebar": "#2b313d",
        "titlebar_active": "#3b4659",
        "titlebar_fg": "#d9dee9",
        "overlay": "#10141b",
    },
)

BUILTIN_LIGHT = Theme(
    name="Light",
    mode="light",
    builtin=True,
    slug="light",
    colors={
        "bg": "#eef1f6",
        "surface": "#f8fafc",
        "surface_alt": "#f1f5f9",
        "panel": "#e2e8f0",
        "panel_hover": "#d3dce8",
        "border": "#cbd5e1",
        "border_strong": "#94a3b8",
        "text": "#1e293b",
        "text_dim": "#64748b",
        "text_faint": "#94a3b8",
        "accent": "#3b82f6",
        "accent_hover": "#2563eb",
        "accent_fg": "#ffffff",
        "select": "#dbeafe",
        "success": "#16a34a",
        "warning": "#ca8a04",
        "danger": "#dc2626",
        "titlebar": "#e2e8f0",
        "titlebar_active": "#dbeafe",
        "titlebar_fg": "#1e293b",
        "overlay": "#334155",
    },
)

BUILTIN_RETRO = Theme(
    name="Retro",
    mode="dark",
    builtin=True,
    slug="retro",
    colors={
        "bg": "#07120a",
        "surface": "#0a160d",
        "surface_alt": "#08110a",
        "panel": "#0f1a0f",
        "panel_hover": "#163016",
        "border": "#1d2b1d",
        "border_strong": "#2f5c37",
        "text": "#35ff6a",
        "text_dim": "#1f8f45",
        "text_faint": "#145c2f",
        "accent": "#00e255",
        "accent_hover": "#7cffa0",
        "accent_fg": "#04140a",
        "select": "#0f2b18",
        "success": "#35ff6a",
        "warning": "#ffd166",
        "danger": "#ff5f57",
        "titlebar": "#0f1a0f",
        "titlebar_active": "#123a1e",
        "titlebar_fg": "#35ff6a",
        "overlay": "#04140a",
    },
)

BUILTIN_THEMES: tuple[Theme, ...] = (BUILTIN_DARK, BUILTIN_LIGHT, BUILTIN_RETRO)

#: Themes offered in the cycle order of the "cycle theme" hotkey.
CYCLE_ORDER: tuple[str, ...] = ("dark", "light", "retro")
