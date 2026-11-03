"""Tests for the shortcut parser and the launcher search."""

from __future__ import annotations

from Xlib import X

from pillarium.core.hotkeys import Hotkey, parse_spec
from pillarium.shell.launcher import score


def test_simple_shortcuts():
    keysym, modifiers = parse_spec("Alt+Space")
    assert modifiers == X.Mod1Mask
    assert keysym == 0x20


def test_shortcuts_with_several_modifiers():
    keysym, modifiers = parse_spec("Ctrl+Alt+Shift+D")
    assert modifiers == (X.ControlMask | X.Mod1Mask | X.ShiftMask)
    assert keysym == ord("d")


def test_named_keys():
    assert parse_spec("Alt+Tab")[0] == 0xFF09
    assert parse_spec("Alt+F4")[0] == 0xFFC1
    assert parse_spec("Ctrl+Alt+Right")[0] == 0xFF53
    assert parse_spec("Alt+Return")[0] == 0xFF0D


def test_invalid_shortcuts_are_rejected():
    assert parse_spec("") is None
    assert parse_spec("Hyper+Nonsense+") is None
    assert parse_spec("Bogus+Key") is None


def test_matching_ignores_lock_keys():
    hotkey = Hotkey(
        action="launcher", keysym=0x20, keycode=65, modifiers=X.Mod1Mask, spec="Alt+Space"
    )
    assert hotkey.matches(65, X.Mod1Mask)
    assert hotkey.matches(65, X.Mod1Mask | X.LockMask)
    assert hotkey.matches(65, X.Mod1Mask | X.Mod2Mask)
    assert not hotkey.matches(65, X.Mod1Mask | X.ControlMask)
    assert not hotkey.matches(66, X.Mod1Mask)


def test_search_scores_prefer_exact_matches():
    exact = {"label": "Firefox", "cmd": ["firefox"]}
    prefix = {"label": "Firefox Nightly", "cmd": ["firefox", "--nightly"]}
    unrelated = {"label": "Thunderbird", "cmd": ["thunderbird"]}
    assert score(exact, "firefox") > score(prefix, "firefox")
    assert score(prefix, "firefox") > score(unrelated, "firefox")


def test_search_matches_case_insensitively():
    entry = {"label": "Files", "cmd": ["nautilus"]}
    assert score(entry, "files") > 0
    assert score(entry, "NAUTILUS") > 0


def test_search_rejects_unrelated_entries():
    entry = {"label": "Files", "cmd": ["nautilus"]}
    assert score(entry, "zzzzzz") < 0
