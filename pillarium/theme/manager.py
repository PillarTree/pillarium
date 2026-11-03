"""Theme discovery, persistence and activation.

Themes live in two places:

* the three built-in palettes in :mod:`pillarium.theme.tokens`, and
* user files in ``$PILLARIUM_HOME/themes/*.json``.

A user file is a JSON document shaped like::

    {
      "name": "Sunset",
      "mode": "dark",
      "colors": {"bg": "#201018", "surface": "#2a1520", ...},
      "metrics": {"radius": 12}
    }

Missing colour tokens fall back to the dark palette, so a theme only has
to describe what it wants to change.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Iterable

from .. import paths
from .freedesktop import FreedesktopPreferences, detect_preferences, theme_from_preferences
from .tokens import BUILTIN_THEMES, CYCLE_ORDER, Theme, _slugify


class ThemeManager:
    """Owns the active theme and notifies listeners when it changes."""

    def __init__(self, directory: str | None = None):
        self._directory = directory or paths.themes_dir()
        self._themes: dict[str, Theme] = {}
        self._current: Theme = BUILTIN_THEMES[0]
        self._listeners: list[Callable[[Theme], None]] = []
        self.reload()

    # -----------------------------------------------------------------
    # Discovery
    # -----------------------------------------------------------------
    def reload(self) -> None:
        """Re-read the theme directory from disk."""
        themes: dict[str, Theme] = {theme.slug: theme for theme in BUILTIN_THEMES}
        for theme in self._load_user_themes():
            themes[theme.slug] = theme
        self._themes = themes

    def _load_user_themes(self) -> Iterable[Theme]:
        try:
            entries = sorted(os.listdir(self._directory))
        except OSError:
            return []
        themes: list[Theme] = []
        for entry in entries:
            if not entry.endswith(".json"):
                continue
            path = os.path.join(self._directory, entry)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            theme = Theme.from_dict(data, builtin=False)
            theme.slug = _slugify(data.get("slug") or entry[:-5])
            themes.append(theme)
        return themes

    # -----------------------------------------------------------------
    # Access
    # -----------------------------------------------------------------
    @property
    def current(self) -> Theme:
        return self._current

    @property
    def current_name(self) -> str:
        return self._current.name

    def names(self) -> list[str]:
        """Names of every available theme, built-ins first."""
        return [theme.name for theme in self._themes.values()]

    def themes(self) -> list[Theme]:
        return list(self._themes.values())

    def get(self, name: str) -> Theme | None:
        if not name:
            return None
        lowered = name.strip().lower()
        for theme in self._themes.values():
            if theme.slug == lowered or theme.name.lower() == lowered:
                return theme
        return None

    def user_themes(self) -> list[Theme]:
        return [theme for theme in self._themes.values() if not theme.builtin]

    # -----------------------------------------------------------------
    # Activation
    # -----------------------------------------------------------------
    def set_theme(self, name: str) -> Theme:
        """Activate the theme called ``name``.

        Unknown names fall back to the built-in dark palette so a stale
        configuration can never leave the UI without colours.
        """
        theme = self.get(name) or BUILTIN_THEMES[0]
        if theme is self._current:
            return theme
        self._current = theme
        for listener in list(self._listeners):
            try:
                listener(theme)
            except Exception:
                continue
        return theme

    def set_colors(self, colors: dict[str, str], name: str = "Custom") -> Theme:
        """Activate an ad-hoc theme built from ``colors``."""
        theme = Theme(name=name, mode=self._current.mode, colors=colors, builtin=False)
        self._current = theme
        for listener in list(self._listeners):
            try:
                listener(theme)
            except Exception:
                continue
        return theme

    def activate(self, theme: Theme) -> Theme:
        """Activate an arbitrary :class:`Theme` instance."""
        self._current = theme
        for listener in list(self._listeners):
            try:
                listener(theme)
            except Exception:
                continue
        return theme

    # -----------------------------------------------------------------
    # Freedesktop.org integration
    # -----------------------------------------------------------------
    def import_freedesktop(self, activate: bool = True) -> tuple[Theme | None, FreedesktopPreferences]:
        """Import the desktop's appearance preferences as a Pillarium theme.

        The preferences come from the freedesktop.org Settings portal when
        the desktop provides one, and from the desktop's native settings
        otherwise.  Returns the generated theme (``None`` when the desktop
        offered no preferences) and the raw preferences.
        """
        preferences = detect_preferences()
        if not preferences.available:
            return None, preferences
        theme = theme_from_preferences(preferences)
        if activate:
            self.activate(theme)
        return theme, preferences

    def cycle(self) -> Theme:
        """Advance to the next built-in theme in the cycle order."""
        current_slug = self._current.slug
        try:
            index = CYCLE_ORDER.index(current_slug)
        except ValueError:
            index = -1
        return self.set_theme(CYCLE_ORDER[(index + 1) % len(CYCLE_ORDER)])

    def subscribe(self, listener: Callable[[Theme], None]) -> None:
        """Register ``listener`` to be called whenever the theme changes."""
        self._listeners.append(listener)

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------
    def save_user_theme(self, theme: Theme, filename: str | None = None) -> str | None:
        """Write ``theme`` to the theme directory as JSON.

        Returns the path written, or ``None`` when the write failed.
        """
        slug = theme.slug or _slugify(theme.name)
        theme.slug = slug
        theme.builtin = False
        try:
            os.makedirs(self._directory, exist_ok=True)
            path = os.path.join(self._directory, filename or f"{slug}.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(theme.to_json())
                handle.write("\n")
        except OSError:
            return None
        self.reload()
        return path

    def delete_user_theme(self, name: str) -> bool:
        """Remove a user theme file.  Built-in themes cannot be removed."""
        theme = self.get(name)
        if theme is None or theme.builtin:
            return False
        path = os.path.join(self._directory, f"{theme.slug}.json")
        try:
            os.remove(path)
        except OSError:
            return False
        self.reload()
        if self._current.slug == theme.slug:
            self.set_theme("dark")
        return True
