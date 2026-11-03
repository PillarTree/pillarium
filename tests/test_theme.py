"""Tests for the theme engine."""

from __future__ import annotations

import json
import os

from pillarium.theme import Theme, ThemeManager
from pillarium.theme.freedesktop import (
    FreedesktopPreferences,
    theme_from_preferences,
)
from pillarium.theme.tokens import (
    BUILTIN_DARK,
    BUILTIN_LIGHT,
    COLOR_TOKENS,
    contrasting_text,
    hex_to_rgb,
    rgb_to_hex,
)


def test_every_token_is_defined_by_the_built_in_themes():
    for theme in (BUILTIN_DARK, BUILTIN_LIGHT):
        for token in COLOR_TOKENS:
            assert token in theme.colors, f"{theme.name} misses {token}"
            assert theme.colors[token].startswith("#")


def test_colour_helpers_round_trip():
    assert hex_to_rgb("#ff8800") == (255, 136, 0)
    assert hex_to_rgb("#f80") == (255, 136, 0)
    assert rgb_to_hex(255, 136, 0) == "#ff8800"
    assert contrasting_text("#ffffff") != contrasting_text("#000000")


def test_partial_themes_fall_back_to_the_dark_palette():
    theme = Theme(name="Partial", colors={"accent": "#123456"})
    assert theme.colors["accent"] == "#123456"
    assert theme.colors["bg"] == BUILTIN_DARK.colors["bg"]


def test_user_themes_are_saved_and_loaded(home):
    manager = ThemeManager()
    assert "Dark" in manager.names()
    custom = manager.current.copy("Sunset")
    custom.colors["accent"] = "#ff6600"
    path = manager.save_user_theme(custom)
    assert path and os.path.isfile(path)

    manager.reload()
    loaded = manager.get("sunset")
    assert loaded is not None
    assert loaded.colors["accent"] == "#ff6600"
    assert not loaded.builtin

    manager.set_theme("sunset")
    assert manager.current.colors["accent"] == "#ff6600"


def test_user_themes_can_be_deleted(home):
    manager = ThemeManager()
    manager.save_user_theme(manager.current.copy("Temp"))
    manager.reload()
    assert manager.delete_user_theme("temp")
    manager.reload()
    assert manager.get("temp") is None
    assert not manager.delete_user_theme("dark")


def test_theme_cycling_follows_the_built_in_order(home):
    manager = ThemeManager()
    manager.set_theme("dark")
    assert manager.cycle().slug == "light"
    assert manager.cycle().slug == "retro"
    assert manager.cycle().slug == "dark"


def test_listeners_are_notified_on_theme_changes(home):
    manager = ThemeManager()
    seen = []
    manager.subscribe(seen.append)
    manager.set_theme("light")
    assert seen and seen[-1].slug == "light"


def test_freedesktop_preferences_build_a_theme():
    preferences = FreedesktopPreferences(
        color_scheme="prefer-dark",
        accent_color="#3b82f6",
        foreground_color="#eeeeee",
        background_color="#111111",
        font="Noto Sans 11",
        source="portal",
    )
    theme = theme_from_preferences(preferences)
    assert theme.mode == "dark"
    assert theme.colors["accent"] == "#3b82f6"
    assert theme.colors["text"] == "#eeeeee"
    assert theme.colors["bg"] == "#111111"
    assert theme.fonts["ui"] == "Noto Sans"


def test_freedesktop_light_scheme_is_detected():
    preferences = FreedesktopPreferences(color_scheme="prefer-light", source="portal")
    theme = theme_from_preferences(preferences)
    assert theme.mode == "light"


def test_theme_files_are_json(home):
    manager = ThemeManager()
    path = manager.save_user_theme(manager.current.copy("Json"))
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["name"] == "Json"
    assert "colors" in data and "metrics" in data
