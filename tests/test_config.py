"""Tests for the configuration model."""

from __future__ import annotations

import json
import os

from pillarium.config import Config, DEFAULT_HOTKEYS, normalize_launch_items


def test_defaults_are_used_when_the_file_is_missing(home):
    config = Config.load()
    assert config.theme == "dark"
    assert config.desktops == 4
    assert config.hotkeys["launcher"] == "Alt+Space"
    assert config.taskbar["position"] == "bottom"


def test_unknown_keys_survive_a_round_trip(home):
    path = home / "config.json"
    path.write_text(json.dumps({"custom_key": {"a": 1}}), encoding="utf-8")
    config = Config.load()
    config.theme = "light"
    config.save()
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["custom_key"] == {"a": 1}
    assert data["theme"] == "light"


def test_saving_is_atomic(home):
    config = Config.load()
    config.theme = "retro"
    assert config.save()
    leftovers = [name for name in os.listdir(home) if name.startswith("config-")]
    assert leftovers == []


def test_external_changes_are_detected(home):
    path = home / "config.json"
    config = Config.load()
    path.write_text(json.dumps({"theme": "light", "desktops": 6}), encoding="utf-8")
    os.utime(path, (0, 0))
    assert config.poll_external_changes() is True
    assert config.theme == "light"
    assert config.desktops == 6
    assert config.poll_external_changes() is False


def test_launch_items_are_normalised():
    items = normalize_launch_items(["xterm -e ls", {"cmd": "firefox", "label": "Firefox"}])
    assert items[0]["cmd"] == ["xterm", "-e", "ls"]
    assert items[0]["label"] == "xterm"
    assert items[1]["cmd"] == ["firefox"]
    assert items[1]["label"] == "Firefox"


def test_desktop_names_fall_back_to_numbers(home):
    config = Config.load()
    assert config.desktop_label(0) == "Desktop 1"
    config.set("desktop_names", ["Work", "Play"])
    assert config.desktop_label(0) == "Work"
    assert config.desktop_label(3) == "Desktop 4"


def test_hotkeys_can_be_overridden(home):
    config = Config.load()
    config.set("hotkeys", {"launcher": "Super+space"})
    assert config.hotkeys["launcher"] == "Super+space"
    assert config.hotkeys["cycle_windows"] == DEFAULT_HOTKEYS["cycle_windows"]


def test_the_desktop_count_is_clamped(home):
    config = Config.load()
    config.set("desktops", 99)
    assert config.desktops == 12
    config.set("desktops", 0)
    assert config.desktops == 1
