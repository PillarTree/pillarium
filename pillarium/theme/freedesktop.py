"""Import colour preferences from the freedesktop.org desktop portal.

The standard way for an application to learn the user's appearance
preferences is the *Settings* portal (``org.freedesktop.portal.Settings``)
in the ``org.freedesktop.appearance`` namespace.  It exposes the
desktop's colour scheme (``prefer-dark`` / ``prefer-light``), the accent
colour, and the interface foreground/background colours.

Desktops that do not implement the portal are handled by reading their
native settings directly:

============  ==============================================
Desktop       Source
============  ==============================================
GNOME         ``gsettings get org.gnome.desktop.interface ...``
KDE Plasma    ``~/.config/kdeglobals``
XDG fallback  ``$XDG_CURRENT_DESKTOP`` detection
============  ==============================================

The result is a :class:`FreedesktopPreferences` record which
:func:`theme_from_preferences` turns into a Pillarium palette.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .tokens import (
    BUILTIN_DARK,
    BUILTIN_LIGHT,
    Theme,
    contrasting_text,
    hex_to_rgb,
    rgb_to_hex,
)

#: The portal namespace that carries appearance settings.
APPEARANCE_NAMESPACE = "org.freedesktop.appearance"

#: Named GNOME/KDE accents mapped to concrete colours.
NAMED_ACCENTS: dict[str, str] = {
    "blue": "#3584e4",
    "teal": "#2190a4",
    "green": "#3a944a",
    "yellow": "#c88800",
    "orange": "#ed5b00",
    "red": "#e62d42",
    "pink": "#d56199",
    "purple": "#9141ac",
    "slate": "#6f8396",
    "adwaita": "#3584e4",
    "breeze": "#3daee9",
}


@dataclass
class FreedesktopPreferences:
    """Appearance preferences harvested from the desktop environment."""

    color_scheme: str | None = None
    accent_color: str | None = None
    accent_color_dark: str | None = None
    foreground_color: str | None = None
    background_color: str | None = None
    font: str | None = None
    gtk_theme: str | None = None
    source: str = "none"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """``True`` when the desktop told us anything useful."""
        return bool(self.color_scheme or self.accent_color or self.foreground_color)

    @property
    def prefers_dark(self) -> bool | None:
        """``True``/``False`` for a known scheme, ``None`` when unknown."""
        scheme = (self.color_scheme or "").lower()
        if scheme in ("prefer-dark", "dark", "prefers-dark"):
            return True
        if scheme in ("prefer-light", "light", "prefers-light"):
            return False
        return None

    def describe(self) -> str:
        """Short human readable summary used in the settings UI."""
        if not self.available:
            return "No desktop preferences found"
        parts: list[str] = []
        if self.color_scheme:
            parts.append(self.color_scheme)
        if self.accent_color:
            parts.append(f"accent {self.accent_color}")
        if self.foreground_color:
            parts.append(f"text {self.foreground_color}")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Portal access
# ---------------------------------------------------------------------------
def _read_portal(namespace: str = APPEARANCE_NAMESPACE) -> dict[str, Any] | None:
    """Read the appearance namespace through the XDG desktop portal."""
    try:
        import dbus
    except ImportError:
        return None

    try:
        bus = dbus.SessionBus(private=True)
    except Exception:
        return None

    try:
        remote = bus.get_object(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
        )
        settings = dbus.Interface(remote, "org.freedesktop.portal.Settings")
        try:
            values = settings.Read(namespace, {})
        except Exception:
            values = {}
        if not values:
            # Some portals only implement ReadOne for individual keys.
            values = {}
            for key in (
                "color-scheme",
                "accent-color",
                "accent-color-dark",
                "foreground-color",
                "background-color",
                "font",
                "gtk-theme",
            ):
                try:
                    value = settings.ReadOne(namespace, key, {})
                except Exception:
                    value = None
                if value is not None:
                    values[key] = value
        if not values:
            return None
        return {str(key): _unwrap(value) for key, value in values.items()}
    except Exception:
        return None
    finally:
        try:
            bus.close()
        except Exception:
            pass


def _unwrap(value: Any) -> Any:
    """Convert dbus types into plain Python values."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_unwrap(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _unwrap(item) for key, item in value.items()}
    if hasattr(value, "value"):
        try:
            return _unwrap(value.value)
        except Exception:
            return str(value)
    return str(value)


# ---------------------------------------------------------------------------
# Desktop specific fallbacks
# ---------------------------------------------------------------------------
def _gsettings(schema: str, key: str) -> str | None:
    try:
        result = subprocess.run(
            ["gsettings", "get", schema, key],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip().strip("'")
    return value or None


def _read_gnome() -> dict[str, Any]:
    values: dict[str, Any] = {}
    scheme = _gsettings("org.gnome.desktop.interface", "color-scheme")
    if scheme:
        values["color-scheme"] = scheme
    accent = _gsettings("org.gnome.desktop.interface", "accent-color")
    if accent:
        values["accent-color"] = accent
    font = _gsettings("org.gnome.desktop.interface", "font-name")
    if font:
        values["font"] = font
    theme = _gsettings("org.gnome.desktop.interface", "gtk-theme")
    if theme:
        values["gtk-theme"] = theme
    return values


def _read_kde() -> dict[str, Any]:
    path = os.path.join(os.path.expanduser("~"), ".config", "kdeglobals")
    values: dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    except OSError:
        return values

    scheme_match = re.search(r"(?m)^\s*colorScheme\s*=\s*(\S+)", content)
    if scheme_match:
        scheme = scheme_match.group(1).strip("'\"")
        if scheme.lower().endswith("dark"):
            values["color-scheme"] = "prefer-dark"
        elif scheme.lower().endswith("light"):
            values["color-scheme"] = "prefer-light"

    accent_match = re.search(r"(?m)^\s*[Aa]ccent[Cc]olor\s*=\s*([#\w]+)", content)
    if accent_match:
        values["accent-color"] = accent_match.group(1).strip("'\"")

    font_match = re.search(r"(?m)^\s*font\s*=\s*([^,\n]+)", content)
    if font_match:
        values["font"] = font_match.group(1).strip()
    return values


def _detect_desktop() -> str:
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    if "gnome" in desktop or "unity" in desktop or "cinnamon" in desktop:
        return "gnome"
    if "kde" in desktop or "plasma" in desktop:
        return "kde"
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def detect_preferences() -> FreedesktopPreferences:
    """Collect appearance preferences from the running desktop.

    The desktop portal is consulted first because it is the
    freedesktop.org standard; desktop specific settings are used as a
    fallback when the portal is unavailable.
    """
    raw = _read_portal()
    source = "portal"
    if not raw:
        desktop = _detect_desktop()
        if desktop == "gnome":
            raw = _read_gnome()
            source = "gnome"
        elif desktop == "kde":
            raw = _read_kde()
            source = "kde"
        else:
            # Unknown desktop: try GNOME's schema anyway, many desktops
            # reuse it, then KDE's file.
            raw = _read_gnome()
            source = "gnome" if raw else ""
            if not raw:
                raw = _read_kde()
                source = "kde" if raw else ""

    if not raw:
        return FreedesktopPreferences(source="none")

    accent = _normalise_color(raw.get("accent-color"))
    accent_dark = _normalise_color(raw.get("accent-color-dark"))
    foreground = _normalise_color(raw.get("foreground-color"))
    background = _normalise_color(raw.get("background-color"))

    scheme = raw.get("color-scheme")
    if scheme:
        scheme = str(scheme).strip().lower()

    font = raw.get("font")
    if isinstance(font, str) and font:
        # "Noto Sans 11" -> "Noto Sans"
        font = font.rsplit(" ", 1)[0] if font.rsplit(" ", 1)[-1].isdigit() else font

    return FreedesktopPreferences(
        color_scheme=scheme,
        accent_color=accent,
        accent_color_dark=accent_dark,
        foreground_color=foreground,
        background_color=background,
        font=font,
        gtk_theme=raw.get("gtk-theme"),
        source=source or "none",
        raw=raw,
    )


def _normalise_color(value: Any) -> str | None:
    """Turn a colour name or hex string into ``#rrggbb``."""
    if value is None:
        return None
    text = str(value).strip().strip("'\"")
    if not text:
        return None
    if text.startswith("#"):
        if len(text.lstrip("#")) in (3, 6, 8):
            return text[:7] if len(text.lstrip("#")) >= 6 else "#" + "".join(
                char * 2 for char in text.lstrip("#")
            )
        return None
    named = NAMED_ACCENTS.get(text.lower())
    if named:
        return named
    if text.lower().startswith("rgb"):
        match = re.search(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text)
        if match:
            return rgb_to_hex(*(int(value) for value in match.groups()))
    return None


def theme_from_preferences(
    preferences: FreedesktopPreferences,
    name: str = "Freedesktop",
) -> Theme:
    """Build a Pillarium theme from desktop appearance preferences."""
    dark = preferences.prefers_dark
    base = BUILTIN_DARK if dark is not False else BUILTIN_LIGHT
    theme = base.copy(name)
    theme.builtin = False
    theme.slug = "freedesktop"

    colors: dict[str, str] = {}

    accent = preferences.accent_color or (
        preferences.accent_color_dark if dark is not False else None
    )
    if accent:
        red, green, blue = hex_to_rgb(accent)
        colors["accent"] = accent
        colors["accent_hover"] = rgb_to_hex(
            min(255, red + 24), min(255, green + 24), min(255, blue + 24)
        )
        colors["accent_fg"] = contrasting_text(accent)
        colors["select"] = rgb_to_hex(
            min(255, int(red + 40)), min(255, int(green + 40)), min(255, int(blue + 40))
        )

    if preferences.foreground_color:
        colors["text"] = preferences.foreground_color
        colors["titlebar_fg"] = preferences.foreground_color

    if preferences.background_color:
        red, green, blue = hex_to_rgb(preferences.background_color)
        colors["bg"] = preferences.background_color
        colors["surface"] = rgb_to_hex(
            min(255, red + 8), min(255, green + 8), min(255, blue + 8)
        )
        colors["panel"] = rgb_to_hex(
            min(255, red + 20), min(255, green + 20), min(255, blue + 20)
        )

    theme.colors.update(colors)

    if preferences.font:
        font = preferences.font.strip()
        # "Noto Sans 11" -> "Noto Sans"
        parts = font.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            font = parts[0]
        theme.fonts["ui"] = font
        theme.fonts["title"] = font

    if dark is not None:
        theme.mode = "dark" if dark else "light"
    return theme
