"""Keyboard shortcut handling.

Shortcuts are described in ``config.json`` with a compact string syntax::

    "Alt+Shift+D"
    "Ctrl+Alt+Right"
    "Super+d"

The manager converts those strings into X11 keycodes and modifier masks,
grabs them on the root window and reports the matching action back to the
application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from Xlib import X, XK

#: Modifier names accepted in shortcut strings.
MODIFIERS: dict[str, int] = {
    "ctrl": X.ControlMask,
    "control": X.ControlMask,
    "alt": X.Mod1Mask,
    "mod1": X.Mod1Mask,
    "shift": X.ShiftMask,
    "super": X.Mod4Mask,
    "meta": X.Mod4Mask,
    "mod4": X.Mod4Mask,
    "hyper": X.Mod5Mask,
    "mod5": X.Mod5Mask,
    "numlock": X.Mod2Mask,
    "mod2": X.Mod2Mask,
    "capslock": X.LockMask,
    "lock": X.LockMask,
}

#: Lock keys that are ignored when matching a shortcut.
LOCK_MASK = X.LockMask | X.Mod2Mask


@dataclass
class Hotkey:
    """A single grabbed key combination."""

    action: str
    keysym: int
    keycode: int
    modifiers: int
    spec: str

    def matches(self, keycode: int, state: int) -> bool:
        """Does the given key event match this shortcut?

        The key *code* is compared rather than the key symbol: holding
        shift changes the symbol a key reports (``d`` becomes ``D``),
        which would make shifted shortcuts impossible to match.
        """
        if keycode != self.keycode:
            return False
        return (state & ~LOCK_MASK) == (self.modifiers & ~LOCK_MASK)


def parse_spec(spec: str) -> tuple[int, int] | None:
    """Parse ``"Alt+Shift+D"`` into ``(keysym, modifier_mask)``."""
    if not spec:
        return None
    parts = [part.strip() for part in spec.split("+") if part.strip()]
    if not parts:
        return None

    modifiers = 0
    key_part = parts[-1]
    for part in parts[:-1]:
        mask = MODIFIERS.get(part.lower())
        if mask is None:
            return None
        modifiers |= mask

    keysym = _to_keysym(key_part)
    if keysym is None:
        return None
    return keysym, modifiers


def _to_keysym(name: str) -> int | None:
    """Map a key name to an X keysym."""
    lowered = name.lower()
    named = {
        "space": "space",
        "return": "Return",
        "enter": "Return",
        "kp_enter": "KP_Enter",
        "tab": "Tab",
        "escape": "Escape",
        "esc": "Escape",
        "backspace": "BackSpace",
        "delete": "Delete",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "page_up": "Prior",
        "pageup": "Prior",
        "prior": "Prior",
        "page_down": "Next",
        "pagedown": "Next",
        "next": "Next",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "menu": "Menu",
        "print": "Print",
    }
    if lowered in named:
        return XK.string_to_keysym(named[lowered])
    if len(lowered) == 1:
        return ord(lowered)
    if lowered.startswith("f") and lowered[1:].isdigit():
        return XK.string_to_keysym(f"F{lowered[1:]}")
    keysym = XK.string_to_keysym(name)
    if keysym:
        return keysym
    if len(name) == 1:
        return ord(name)
    return None


class HotkeyManager:
    """Grabs the configured shortcuts and dispatches the matching action."""

    def __init__(self, display: Any, root: Any):
        self._display = display
        self._root = root
        self._hotkeys: list[Hotkey] = []
        self._handler: Callable[[str], None] | None = None

    # -----------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------
    def configure(self, bindings: dict[str, str]) -> None:
        """Grab every shortcut in ``bindings``."""
        self.release()
        for action, spec in bindings.items():
            parsed = parse_spec(spec)
            if parsed is None:
                continue
            keysym, modifiers = parsed
            try:
                keycode = self._display.keysym_to_keycode(keysym)
            except Exception:
                continue
            if not keycode:
                continue
            hotkey = Hotkey(
                action=action,
                keysym=keysym,
                keycode=keycode,
                modifiers=modifiers,
                spec=spec,
            )
            if self._grab(hotkey):
                self._hotkeys.append(hotkey)

    def _grab(self, hotkey: Hotkey) -> bool:
        variants = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]
        grabbed = False
        for variant in variants:
            try:
                # owner_events is disabled on purpose: the shortcut has to
                # reach the window manager even while an application
                # holds the keyboard focus.
                self._root.grab_key(
                    hotkey.keycode,
                    hotkey.modifiers | variant,
                    False,
                    X.GrabModeAsync,
                    X.GrabModeAsync,
                )
                grabbed = True
            except Exception:
                continue
        return grabbed

    def release(self) -> None:
        """Release every shortcut currently grabbed."""
        for hotkey in self._hotkeys:
            for variant in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                try:
                    self._root.ungrab_key(
                        hotkey.keycode, hotkey.modifiers | variant, True
                    )
                except Exception:
                    continue
        self._hotkeys = []

    # -----------------------------------------------------------------
    # Dispatch
    # -----------------------------------------------------------------
    def set_handler(self, handler: Callable[[str], None]) -> None:
        """Register the callback invoked for a matched shortcut."""
        self._handler = handler

    def handle(self, keycode: int, state: int) -> str | None:
        """Return the action matching the key event, if any."""
        for hotkey in self._hotkeys:
            if hotkey.matches(keycode, state):
                if self._handler is not None:
                    try:
                        self._handler(hotkey.action)
                    except Exception:
                        pass
                return hotkey.action
        return None

    @property
    def shortcuts(self) -> list[Hotkey]:
        return list(self._hotkeys)
