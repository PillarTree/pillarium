"""The X11 window manager.

Pillarium is a full window manager: it takes over the X11 display,
redirects the root window's substructure and manages every application
window that maps itself.

The manager owns the *logical* state of every window - geometry, virtual
desktop, focus and stacking - while the *visual* decoration is produced
by the shell through the :class:`DecorationHost` interface.  The split
keeps the X11 bookkeeping independent from the toolkit.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Callable

from Xlib import X, Xatom, XK, display as xdisplay
from Xlib.error import BadAccess

try:
    from Xlib.ext import randr
except Exception:  # pragma: no cover - RandR is optional
    randr = None  # type: ignore[assignment]

from . import xerror
from .clients import Client
from .hotkeys import HotkeyManager
from .monitors import Monitor, MonitorManager

#: How often the ping watchdog runs (seconds).
PING_INTERVAL = 2.0
#: How long a client may stay silent before it is reported as hung.
PING_TIMEOUT = 6.0
#: How long an application may take to honour a close request (seconds).
CLOSE_GRACE = 2.0

DEFAULT_WIDTH = 820
DEFAULT_HEIGHT = 560
MIN_WIDTH = 320
MIN_HEIGHT = 240


class DecorationHost:
    """Interface the shell implements to draw managed windows.

    Every method is optional; the window manager checks for the ones it
    needs before calling them, which keeps the interface easy to fake in
    tests.
    """

    def create(self, client: Client) -> int:
        """Create the decoration for ``client``.

        Returns the X window id of the area the application window must
        be reparented into, or ``0`` when the shell cannot host it.
        """

    def destroy(self, client_id: int) -> None:
        """Tear down the decoration of a window."""

    def update(self, client: Client) -> None:
        """Refresh title and icon."""

    def set_geometry(self, client_id: int, x: int, y: int, width: int, height: int) -> None:
        """Move and resize the decoration."""

    def set_active(self, client_id: int | None) -> None:
        """Mark one window as focused (or none)."""

    def set_visible(self, client_id: int, visible: bool) -> None:
        """Show or hide the decoration."""

    def raise_client(self, client_id: int) -> None:
        """Bring the decoration to the front."""

    def get_geometry(self, client_id: int) -> tuple[int, int, int, int] | None:
        """Current geometry of the decoration."""


class WindowManager:
    """Owns the X11 display and the state of every managed window."""

    def __init__(
        self,
        host: DecorationHost | None = None,
        display: Any = None,
        config: Any = None,
        on_desktop_changed: Callable[[int], None] | None = None,
        on_hotkey: Callable[[str], None] | None = None,
        on_monitor_changed: Callable[[list[Monitor]], None] | None = None,
        on_client_changed: Callable[[], None] | None = None,
    ):
        self.host = host
        self.config = config
        self._on_desktop_changed = on_desktop_changed
        self._on_hotkey = on_hotkey
        self._on_monitor_changed = on_monitor_changed
        self._on_client_changed = on_client_changed

        # X errors must never take the session down.
        xerror.install()
        self.display = display if display is not None else xdisplay.Display()
        self.display.set_error_handler(self._ignore_error)
        self.screen = self.display.screen()
        self.root = self.screen.root

        self.clients: dict[int, Client] = {}
        self.order: list[int] = []
        self.focused: int | None = None
        self.current_desktop = 0
        self.desktop_count = 4
        self.desktop_names: list[str] = []

        self._atoms: dict[str, int] = {}
        self._containers: dict[int, Any] = {}
        # Windows whose unmap notifications have to be ignored, because
        # Pillarium caused the unmap itself.
        self._unmap_ignored_until: dict[int, float] = {}
        self._ping_tokens: dict[int, int] = {}
        self._ping_outstanding: dict[int, tuple[int, float]] = {}
        self._ping_sequence = 0
        self._last_ping_sweep = 0.0
        self._closing: dict[int, tuple[Any, float]] = {}
        self._take_over_error: Any = None
        self._closed = False

        self.monitors = MonitorManager(self.display)
        self.monitors.watch()
        self.monitors.on_change(self._monitor_layout_changed)

        self.hotkeys = HotkeyManager(self.display, self.root)
        self.hotkeys.set_handler(self._handle_hotkey)

        self._take_over()

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------
    def _ignore_error(self, error: Any, request: Any) -> None:
        """Swallow X errors from clients that disappear mid-request."""
        return None

    def _take_over(self) -> None:
        """Redirect the root window so we receive every map request."""
        mask = self._event_mask()
        self._take_over_error = None
        self.display.set_error_handler(self._capture_error)
        try:
            self.root.change_attributes(event_mask=mask)
            self.display.sync()
        finally:
            self.display.set_error_handler(self._ignore_error)
        if isinstance(self._take_over_error, BadAccess):
            print(
                "Pillarium needs to be the active X11 window manager.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    def _event_mask(self) -> int:
        """The events the window manager asks the root window for."""
        mask = (
            X.SubstructureRedirectMask
            | X.SubstructureNotifyMask
            | X.FocusChangeMask
            # Key events are only delivered to the root window when it
            # asks for them; without this the grabbed shortcuts would be
            # silently dropped by the X server.
            | X.KeyPressMask
        )
        if self.follows_mouse():
            # Pointer motion is only needed when the pointer should move
            # the focus.
            mask |= X.PointerMotionMask
        return mask

    def refresh_event_mask(self) -> None:
        """Apply the event mask again, for example after a settings change."""
        try:
            self.root.change_attributes(event_mask=self._event_mask())
        except Exception:
            pass

    def _capture_error(self, error: Any, request: Any) -> None:
        """Remember the first X error raised while taking over."""
        if self._take_over_error is None:
            self._take_over_error = error

    def atom(self, name: str) -> int:
        """Intern an atom, caching the result."""
        cached = self._atoms.get(name)
        if cached is None:
            cached = self.display.intern_atom(name)
            self._atoms[name] = cached
        return cached

    # -----------------------------------------------------------------
    # Virtual desktops
    # -----------------------------------------------------------------
    def configure_desktops(self, count: int, names: list[str] | None = None) -> None:
        """Set the number of virtual desktops and their names."""
        self.desktop_count = max(1, min(12, int(count)))
        self.desktop_names = list(names or [])
        for client in self.clients.values():
            client.desktop = min(client.desktop, self.desktop_count - 1)
        self._publish_desktops()

    def switch_desktop(self, index: int) -> None:
        """Show the windows of desktop ``index`` and hide the others."""
        index = max(0, min(self.desktop_count - 1, int(index)))
        if index == self.current_desktop:
            return
        self.current_desktop = index
        for client_id in list(self.order):
            client = self.clients.get(client_id)
            if client is None:
                continue
            visible = client.desktop == index and not client.minimized
            self._set_visible(client, visible)
        if self.focused is not None:
            focused = self.clients.get(self.focused)
            if focused is not None and focused.desktop != index:
                self.focused = None
                self._set_active(None)
        self._publish_desktops()
        self._notify_desktop_changed()

    def next_desktop(self) -> None:
        self.switch_desktop((self.current_desktop + 1) % self.desktop_count)

    def previous_desktop(self) -> None:
        self.switch_desktop((self.current_desktop - 1) % self.desktop_count)

    def move_to_desktop(self, client_id: int, index: int) -> None:
        """Move a window to another virtual desktop."""
        client = self.clients.get(client_id)
        if client is None:
            return
        index = max(0, min(self.desktop_count - 1, int(index)))
        client.desktop = index
        self._set_client_desktop_property(client)
        visible = index == self.current_desktop and not client.minimized
        self._set_visible(client, visible)
        self._publish_desktops()
        self._notify_clients_changed()

    def clients_on_desktop(self, index: int) -> list[Client]:
        """Every window that belongs to desktop ``index``."""
        return [client for client in self.clients.values() if client.desktop == index]

    def _notify_desktop_changed(self) -> None:
        if self._on_desktop_changed is not None:
            try:
                self._on_desktop_changed(self.current_desktop)
            except Exception:
                pass

    # -----------------------------------------------------------------
    # Client management
    # -----------------------------------------------------------------
    def manage(self, window: Any) -> Client | None:
        """Take over an application window and manage it."""
        if window.id in self.clients:
            return self.clients[window.id]
        if window.id in self._closing:
            # The window is being closed; it must not be adopted again
            # when the server remaps it after the reparenting.
            return None
        try:
            if window.get_attributes().override_redirect:
                return None
        except Exception:
            pass

        client = Client(id=window.id, window=window)
        client.title = self._read_title(window)
        client.wm_class = self._read_wm_class(window)
        client.icon_name = self._read_icon_name(window)
        client.desktop = self.current_desktop

        self.clients[client.id] = client
        self.order.append(client.id)

        monitor = self._target_monitor()
        client.monitor = monitor.name
        client.width = DEFAULT_WIDTH
        client.height = DEFAULT_HEIGHT
        client.x, client.y = self._cascade_position(monitor)

        try:
            window.change_attributes(
                event_mask=(
                    X.StructureNotifyMask
                    | X.PropertyChangeMask
                    | X.FocusChangeMask
                )
            )
        except Exception:
            pass

        if self.host is not None:
            try:
                client_area = int(self.host.create(client))
            except Exception as exc:
                print(f"Pillarium: decoration failed: {exc}", file=sys.stderr)
                client_area = 0
            if client_area:
                self._create_container(client, client_area)
            self._reparent(client)
        else:
            self._reparent(client)

        self._register_ping(client)
        self._set_client_desktop_property(client)
        self._apply_geometry(client)
        self._publish_client_list()
        self._notify_clients_changed()
        self.focus(client.id)
        return client

    def _create_container(self, client: Client, client_area_xid: int) -> None:
        """Create the X window the application is reparented into.

        The container is a child of the decoration's client area, which
        keeps the toolkit in charge of the frame while Pillarium stays in
        charge of the application window.
        """
        try:
            parent = self.display.create_resource_object("window", client_area_xid)
        except Exception:
            return
        try:
            container = parent.create_window(
                0,
                0,
                client.width,
                client.height,
                0,
                self.screen.root_depth,
                background_pixel=self.screen.black_pixel,
                event_mask=(X.ExposureMask | X.StructureNotifyMask),
            )
            container.map()
            self._containers[client.id] = container
        except Exception as exc:
            print(f"Pillarium: could not create client container: {exc}", file=sys.stderr)
            return
        self._wait_until_viewable(container)

    def _wait_until_viewable(self, window: Any, attempts: int = 25) -> bool:
        """Block until ``window`` is mapped.

        Reparenting a mapped window into a window that is not viewable
        makes the X server unmap it again, which the window manager
        would mistake for the application closing its window.
        """
        for _ in range(attempts):
            try:
                self.display.sync()
                if window.get_attributes().map_state == X.IsViewable:
                    return True
            except Exception:
                return False
            time.sleep(0.01)
        return False

    def _reparent(self, client: Client) -> None:
        """Move the application window into its container."""
        container = self._containers.get(client.id)
        if container is None:
            return
        try:
            # Reparenting a mapped window makes the X server unmap and
            # remap it, which produces an unmap notification that the
            # window manager has to ignore.
            try:
                mapped = client.window.get_attributes().map_state == X.IsViewable
            except Exception:
                mapped = False
            if mapped:
                self._ignore_unmaps(client.id)
            client.window.reparent(container, 0, 0)
            client.window.configure(width=client.width, height=client.height)
            client.window.map()
            container.configure(stack_mode=X.Above)
            self.display.flush()
        except Exception as exc:
            print(f"Pillarium: could not embed window {client.id}: {exc}", file=sys.stderr)
    def forget(self, client_id: int) -> None:
        """Stop managing a window."""
        client = self.clients.pop(client_id, None)
        if client is None:
            return
        if client_id in self.order:
            self.order.remove(client_id)
        self._unregister_ping(client_id)
        container = self._containers.pop(client_id, None)
        if container is not None:
            try:
                client.window.reparent(self.root, 0, 0)
            except Exception:
                pass
            try:
                container.destroy()
            except Exception:
                pass
        if self.host is not None:
            try:
                self.host.destroy(client_id)
            except Exception:
                pass
        if self.focused == client_id:
            self.focused = None
            self._set_active(None)
            self._focus_root()
        elif self.focused is not None:
            # Destroying a window takes the toolkit's focus with it and
            # leaves the X focus on the pointer.  Give the keyboard back
            # to the window that is still active.
            self.restore_focus()
        self._publish_client_list()
        self._notify_clients_changed()

    # -----------------------------------------------------------------
    # Geometry
    # -----------------------------------------------------------------
    def _target_monitor(self) -> Monitor:
        """Monitor a new window should open on."""
        policy = "pointer"
        if self.config is not None:
            policy = str(self.config.opt("monitors", "placement", "pointer"))
        if policy == "primary":
            return self.monitors.primary
        if policy == "focused":
            focused = self.clients.get(self.focused) if self.focused else None
            if focused is not None:
                monitor = self.monitors.by_name(focused.monitor)
                if monitor is not None:
                    return monitor
        return self.monitors.pointer_monitor()

    def _cascade_position(self, monitor: Monitor) -> tuple[int, int]:
        """Cascade new windows so they do not land exactly on top of each other."""
        offset = 28 * (len(self.order) % 8)
        taskbar = self._taskbar_height()
        area = self.monitors.work_area(monitor, taskbar)
        x = area[0] + 48 + offset
        y = area[1] + 32 + offset
        return self.monitors.clamp_to_monitor(
            monitor, x, y, DEFAULT_WIDTH, DEFAULT_HEIGHT
        )

    def _taskbar_height(self) -> int:
        if self.config is None:
            return 38
        try:
            return int(self.config.opt("taskbar", "height", 38))
        except (TypeError, ValueError):
            return 38

    def _apply_geometry(self, client: Client) -> None:
        """Push the window geometry to the decoration and the client."""
        if self.host is not None:
            try:
                self.host.set_geometry(client.id, client.x, client.y, client.width, client.height)
            except Exception:
                pass
        container = self._containers.get(client.id)
        if container is not None:
            try:
                container.configure(width=client.width, height=client.height)
            except Exception:
                pass
        try:
            client.window.configure(width=client.width, height=client.height)
        except Exception:
            pass
        self.display.flush()

    def move_client(self, client_id: int, x: int, y: int) -> None:
        """Move a window to an absolute position."""
        client = self.clients.get(client_id)
        if client is None:
            return
        monitor = self.monitors.by_name(client.monitor) or self.monitors.primary
        client.x, client.y = self.monitors.clamp_to_monitor(
            monitor, x, y, client.width, client.height
        )
        self._apply_geometry(client)

    def resize_client(self, client_id: int, width: int, height: int) -> None:
        """Resize a window's client area."""
        client = self.clients.get(client_id)
        if client is None:
            return
        client.width = max(MIN_WIDTH, int(width))
        client.height = max(MIN_HEIGHT, int(height))
        client.maximized = False
        client.restore_geometry = None
        self._apply_geometry(client)

    def maximize(self, client_id: int) -> None:
        """Maximise a window over its monitor."""
        client = self.clients.get(client_id)
        if client is None:
            return
        monitor = self.monitors.by_name(client.monitor) or self.monitors.primary
        if not client.maximized:
            client.restore_geometry = (client.x, client.y, client.width, client.height)
        taskbar = self._taskbar_height()
        position = "bottom"
        if self.config is not None:
            position = str(self.config.opt("taskbar", "position", "bottom"))
        area = self.monitors.work_area(monitor, taskbar, position)
        client.maximized = True
        client.minimized = False
        client.x, client.y = area[0], area[1]
        client.width = max(MIN_WIDTH, area[2])
        client.height = max(MIN_HEIGHT, area[3])
        self._set_visible(client, True)
        self._apply_geometry(client)

    def restore(self, client_id: int) -> None:
        """Undo a maximisation."""
        client = self.clients.get(client_id)
        if client is None:
            return
        if client.maximized and client.restore_geometry:
            client.x, client.y, client.width, client.height = client.restore_geometry
        client.maximized = False
        client.restore_geometry = None
        self._apply_geometry(client)

    def toggle_maximize(self, client_id: int) -> None:
        client = self.clients.get(client_id)
        if client is None:
            return
        if client.maximized:
            self.restore(client_id)
        else:
            self.maximize(client_id)

    def minimize(self, client_id: int) -> None:
        """Hide a window without destroying it."""
        client = self.clients.get(client_id)
        if client is None:
            return
        client.minimized = True
        self._set_visible(client, False)
        if self.focused == client_id:
            self.focused = None
            self._set_active(None)
            self.focus_next()
        self._notify_clients_changed()

    def restore_minimized(self, client_id: int) -> None:
        """Bring a minimised window back."""
        client = self.clients.get(client_id)
        if client is None:
            return
        client.minimized = False
        if client.desktop != self.current_desktop:
            self.move_to_desktop(client_id, self.current_desktop)
        self._set_visible(client, True)
        self._apply_geometry(client)
        self.focus(client_id)

    def close(self, client_id: int) -> None:
        """Ask a window to close.

        The application is asked politely through ``WM_DELETE_WINDOW``
        first; it is only killed when it refuses to go away.
        """
        client = self.clients.get(client_id)
        if client is None:
            return
        self._unregister_ping(client_id)
        if self._is_alive(client.window):
            try:
                from Xlib.protocol import event as xevent

                message = xevent.ClientMessage(
                    window=client.window,
                    client_type=self.atom("WM_PROTOCOLS"),
                    data=(32, [self.atom("WM_DELETE_WINDOW"), X.CurrentTime, 0, 0, 0]),
                )
                client.window.send_event(message, event_mask=0, propagate=False)
                self.display.flush()
            except Exception:
                pass
        self._closing[client_id] = (client.window, time.time() + CLOSE_GRACE)
        self.forget(client_id)

    @staticmethod
    def _is_alive(window: Any) -> bool:
        """Is the window still on the server?"""
        try:
            return window.get_attributes().map_state != X.IsUnmapped
        except Exception:
            return False

    def sweep_closing(self) -> list[int]:
        """Kill applications that ignored the close request."""
        if not self._closing:
            return []
        now = time.time()
        killed: list[int] = []
        for client_id, (window, deadline) in list(self._closing.items()):
            if now < deadline:
                continue
            self._closing.pop(client_id, None)
            try:
                if window.get_attributes().map_state != X.IsUnmapped:
                    window.kill_client()
                    killed.append(client_id)
            except Exception:
                continue
        return killed

    def _set_visible(self, client: Client, visible: bool) -> None:
        """Show or hide a window and its decoration."""
        if self.host is not None:
            try:
                self.host.set_visible(client.id, visible)
            except Exception:
                pass
        container = self._containers.get(client.id)
        if container is None:
            return
        try:
            if visible:
                client.window.map()
                container.map()
            else:
                self._ignore_unmaps(client.id)
                client.window.unmap()
                container.unmap()
            self.display.flush()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Focus and stacking
    # -----------------------------------------------------------------
    def focus(self, client_id: int | None) -> None:
        """Give the keyboard to a window."""
        client = self.clients.get(client_id) if client_id is not None else None
        if client is None or client.minimized or client.desktop != self.current_desktop:
            self.focused = None
            self._set_active(None)
            self._focus_root()
            return
        try:
            client.window.set_input_focus(X.RevertToParent, X.CurrentTime)
        except Exception:
            pass
        self.focused = client_id
        self._set_active(client_id)
        self.raise_client(client_id)
        self._publish_active_window()
        self._notify_clients_changed()

    def _focus_root(self) -> None:
        """Put the keyboard focus on the root window.

        Leaving the focus on the pointer would make the X server hand
        the keyboard to whatever the mouse happens to be over, which is
        not what a window manager should do.
        """
        try:
            self.root.set_input_focus(X.RevertToPointerRoot, X.CurrentTime)
            self.display.flush()
        except Exception:
            pass

    def focus_next(self, reverse: bool = False) -> None:
        """Focus the next window in the taskbar order."""
        candidates = [
            client_id
            for client_id in self.order
            if client_id in self.clients
            and not self.clients[client_id].minimized
            and self.clients[client_id].desktop == self.current_desktop
        ]
        if not candidates:
            self.focus(None)
            return
        if len(candidates) == 1:
            self.focus(candidates[0])
            return
        try:
            index = candidates.index(self.focused) if self.focused in candidates else -1
        except ValueError:
            index = -1
        step = -1 if reverse else 1
        self.focus(candidates[(index + step) % len(candidates)])

    def focus_external(self, xid: int) -> None:
        """Hand the X keyboard focus to a window Pillarium owns.

        The shell needs this so that text fields and dialogs receive
        key presses while the X focus would otherwise stay on the
        application window.
        """
        try:
            window = self.display.create_resource_object("window", int(xid))
            window.set_input_focus(X.RevertToParent, X.CurrentTime)
            self.display.flush()
        except Exception:
            pass

    def restore_focus(self) -> None:
        """Give the keyboard back to the focused application window."""
        client = self.clients.get(self.focused) if self.focused else None
        if client is None:
            # The focus was lost while a panel was open: fall back to
            # any window of the current desktop.
            candidates = [
                candidate
                for candidate in self.clients.values()
                if not candidate.minimized and candidate.desktop == self.current_desktop
            ]
            client = candidates[0] if candidates else None
        if client is None:
            self._focus_root()
            return
        try:
            client.window.set_input_focus(X.RevertToParent, X.CurrentTime)
            self.display.flush()
        except Exception:
            pass

    def follows_mouse(self) -> bool:
        """Should the window under the pointer take the focus?"""
        if self.config is None:
            return False
        return bool(self.config.opt("focus", "follows_mouse", False))

    def ensure_focus(self) -> None:
        """Keep the keyboard on a window instead of on the pointer.

        The focus can end up on the pointer - for example when the
        toolkit destroys a window - and the X server then hands the
        keyboard to whatever the mouse is over.  Whenever that happens
        the focus goes back to the active window.
        """
        if self.follows_mouse():
            return
        try:
            focus = self.display.get_input_focus()
        except Exception:
            return
        if focus.focus is not None:
            # The focus is on a real window, nothing to do.
            return
        self.restore_focus()

    def raise_client(self, client_id: int) -> None:
        """Bring a window to the front."""
        if self.host is not None:
            try:
                self.host.raise_client(client_id)
            except Exception:
                pass

    def _set_active(self, client_id: int | None) -> None:
        if self.host is not None:
            try:
                self.host.set_active(client_id)
            except Exception:
                pass

    def _notify_clients_changed(self) -> None:
        if self._on_client_changed is not None:
            try:
                self._on_client_changed()
            except Exception:
                pass

    # -----------------------------------------------------------------
    # Monitor changes
    # -----------------------------------------------------------------
    def _monitor_layout_changed(self, monitors: list[Monitor]) -> None:
        if self._on_monitor_changed is not None:
            try:
                self._on_monitor_changed(monitors)
            except Exception:
                pass

    def move_client_to_monitor(self, client_id: int, monitor: Monitor) -> None:
        """Move a window to another monitor."""
        client = self.clients.get(client_id)
        if client is None:
            return
        client.monitor = monitor.name
        client.x = monitor.x + 40
        client.y = monitor.y + 30
        client.maximized = False
        client.restore_geometry = None
        self._apply_geometry(client)
        self._notify_clients_changed()

    # -----------------------------------------------------------------
    # Property reading
    # -----------------------------------------------------------------
    def _read_title(self, window: Any) -> str:
        try:
            title = window.get_wm_name()
            if title:
                return str(title)
        except Exception:
            pass
        try:
            prop = window.get_full_property(self.atom("_NET_WM_NAME"), X.AnyPropertyType)
            if prop and prop.value:
                value = prop.value
                if isinstance(value, bytes):
                    return value.decode("utf-8", "replace")
                return str(value)
        except Exception:
            pass
        return "Window"

    def _read_wm_class(self, window: Any) -> list[str]:
        try:
            classes = window.get_wm_class()
        except Exception:
            return []
        if not classes:
            return []
        return [str(part).strip().lower() for part in classes if str(part).strip()]

    def _read_icon_name(self, window: Any) -> str | None:
        try:
            prop = window.get_full_property(self.atom("WM_ICON_NAME"), X.AnyPropertyType)
            if prop and prop.value:
                value = prop.value
                if isinstance(value, bytes):
                    return value.decode("utf-8", "replace")
                return str(value)
        except Exception:
            pass
        return None

    def refresh_client(self, client_id: int) -> None:
        """Re-read title and icon of a window."""
        client = self.clients.get(client_id)
        if client is None:
            return
        client.title = self._read_title(client.window)
        client.icon_name = self._read_icon_name(client.window)
        if self.host is not None:
            try:
                self.host.update(client)
            except Exception:
                pass
        self._notify_clients_changed()

    # -----------------------------------------------------------------
    # Event handling
    # -----------------------------------------------------------------
    def handle_event(self, event: Any) -> None:
        """Dispatch a single X event."""
        event_type = event.type
        if event_type == X.MapRequest:
            self.manage(event.window)
        elif event_type == X.DestroyNotify:
            self.forget(event.window.id)
        elif event_type == X.UnmapNotify:
            self._handle_unmap(event)
        elif event_type == X.ConfigureRequest:
            self._handle_configure_request(event)
        elif event_type == X.ClientMessage:
            self._handle_client_message(event)
        elif event_type == X.KeyPress:
            self._handle_key_press(event)
        elif event_type == X.PropertyNotify:
            self._handle_property_notify(event)
        elif event_type == X.MotionNotify:
            self._handle_motion(event)
        elif event_type == X.FocusIn:
            self._handle_focus_in(event)
        elif event_type == X.FocusOut:
            self._handle_focus_out(event)
        elif randr is not None and event_type == randr.ScreenChangeNotify:
            self.monitors.notify_changed()
        elif randr is not None and event_type == randr.CrtcChangeNotify:
            self.monitors.notify_changed()

    def _handle_focus_in(self, event: Any) -> None:
        """A client received the keyboard focus."""
        client_id = self._find_client_by_window(event.window)
        if client_id is None or client_id == self.focused:
            return
        client = self.clients.get(client_id)
        if client is None or client.minimized:
            return
        self.focused = client_id
        self._set_active(client_id)
        self.raise_client(client_id)
        self._publish_active_window()
        self._notify_clients_changed()

    def _handle_focus_out(self, event: Any) -> None:
        """The keyboard focus left a client."""
        if self.focused is None:
            return
        client_id = self._find_client_by_window(event.window)
        if client_id is not None and client_id != self.focused:
            return
        try:
            focus = self.display.get_input_focus()
            focused_window = focus.focus
        except Exception:
            return
        if focused_window is None:
            # The focus went back to the pointer.  The toolkit does that
            # when one of its windows is destroyed, and with the focus
            # on the pointer the X server hands the keyboard to whatever
            # the mouse happens to be over.  Take the focus back so that
            # moving the pointer never changes the focused window.
            if not self.follows_mouse():
                self.restore_focus()
            return
        focused_id = getattr(focused_window, "id", None)
        if focused_id is not None and focused_id in self.clients:
            return
        self.focused = None
        self._set_active(None)
        self._publish_active_window()
        self._notify_clients_changed()

    def focus_under_pointer(self) -> None:
        """Focus the window below the pointer.

        Only used when the focus follows the mouse is switched on.  The
        pointer is polled instead of watched, because the toolkit
        swallows the motion events before they reach the root window.
        """
        if not self.follows_mouse():
            return
        client_id = self._client_under_pointer()
        if client_id is not None and client_id != self.focused:
            self.focus(client_id)

    def _client_under_pointer(self) -> int | None:
        """The managed window below the pointer, if there is one.

        The server is asked which window is really under the pointer,
        because the window frames overlap each other and a plain
        geometry test cannot tell them apart.
        """
        window = self._window_under_pointer()
        if window is None:
            return None
        client_id = self._find_client_by_window(window)
        if client_id is None:
            return None
        client = self.clients.get(client_id)
        if client is None or client.minimized or client.desktop != self.current_desktop:
            return None
        return client_id

    def _window_under_pointer(self) -> Any:
        """The deepest window below the pointer."""
        try:
            pointer = self.root.query_pointer()
        except Exception:
            return None
        window = self._as_window(pointer.child)
        for _ in range(8):
            if window is None:
                return None
            try:
                child = window.query_pointer().child
            except Exception:
                break
            child = self._as_window(child)
            if child is None or child.id == window.id:
                break
            window = child
        return window

    def _as_window(self, value: Any) -> Any:
        """Turn a window id into a window object."""
        if value is None:
            return None
        if isinstance(value, int):
            if not value:
                return None
            try:
                return self.display.create_resource_object("window", value)
            except Exception:
                return None
        return value

    def _ignore_unmaps(self, client_id: int, seconds: float = 0.5) -> None:
        """Ignore the unmap notifications of a window for a moment.

        Unmapping a window produces two notifications: one for the
        window itself and one for its parent.  Both have to be ignored
        when Pillarium caused the unmap.
        """
        self._unmap_ignored_until[client_id] = time.time() + seconds

    def _handle_unmap(self, event: Any) -> None:
        client_id = event.window.id
        if time.time() < self._unmap_ignored_until.get(client_id, 0.0):
            return
        client = self.clients.get(client_id)
        if client is None:
            return
        if client.minimized:
            return
        self.forget(client_id)

    def _handle_configure_request(self, event: Any) -> None:
        client_id = event.window.id
        client = self.clients.get(client_id)
        if client is None:
            try:
                event.window.configure(
                    x=event.x, y=event.y, width=event.width, height=event.height
                )
                self.display.flush()
            except Exception:
                pass
            return
        if event.width and event.height:
            width = max(MIN_WIDTH, int(event.width))
            height = max(MIN_HEIGHT, int(event.height))
            if width != client.width or height != client.height:
                client.width = width
                client.height = height
                self._apply_geometry(client)

    def _handle_client_message(self, event: Any) -> None:
        try:
            client_type = event.client_type
            values = event.data
            if isinstance(values, (tuple, list)) and len(values) == 2 and isinstance(values[0], int):
                values = values[1]
            values = list(values)
        except Exception:
            return

        if client_type == self.atom("WM_PROTOCOLS"):
            # A reply to the _NET_WM_PING watchdog.
            self.handle_ping_reply(event)
        elif client_type == self.atom("_NET_ACTIVE_WINDOW"):
            target = self._find_client_by_window(event.window)
            if target is not None:
                self.focus(target)
        elif client_type == self.atom("_NET_CLOSE_WINDOW"):
            target = self._find_client_by_window(event.window)
            if target is not None:
                self.close(target)
        elif client_type == self.atom("_NET_CURRENT_DESKTOP"):
            if values:
                try:
                    self.switch_desktop(int(values[0]))
                except (TypeError, ValueError):
                    pass
        elif client_type == self.atom("_NET_WM_DESKTOP"):
            target = self._find_client_by_window(event.window)
            if target is not None and values:
                try:
                    self.move_to_desktop(target, int(values[0]))
                except (TypeError, ValueError):
                    pass
        elif client_type == self.atom("WM_CHANGE_STATE"):
            target = self._find_client_by_window(event.window)
            if target is not None and values and int(values[0]) == 3:
                self.minimize(target)

    def _handle_key_press(self, event: Any) -> None:
        try:
            keycode = int(event.detail)
            state = int(event.state)
        except Exception:
            return
        # Shortcuts are matched on the key code, so this must happen
        # before the key symbol is looked up.
        if self.hotkeys.handle(keycode, state) is not None:
            return
        try:
            keysym = self.display.keycode_to_keysym(keycode, 0)
        except Exception:
            return
        # Alt+Enter opens a terminal, mirroring the classic shortcut.
        if state & X.Mod1Mask and keysym == XK.string_to_keysym("Return"):
            if self._on_hotkey is not None:
                try:
                    self._on_hotkey("terminal")
                except Exception:
                    pass

    def _handle_property_notify(self, event: Any) -> None:
        try:
            atom_name = self.display.get_atom_name(event.atom)
            atom_name = atom_name.decode() if isinstance(atom_name, bytes) else str(atom_name)
        except Exception:
            return
        if atom_name in ("_NET_WM_NAME", "WM_NAME", "WM_ICON_NAME", "_NET_WM_ICON"):
            self.refresh_client(event.window.id)

    def _find_client_by_window(self, window: Any) -> int | None:
        """Find the managed client that owns ``window``."""
        try:
            window_id = window.id
        except AttributeError:
            return None
        if window_id in self.clients:
            return window_id
        try:
            parent = window.query_tree().parent
            while parent is not None and parent.id != self.root.id:
                if parent.id in self.clients:
                    return parent.id
                parent = parent.query_tree().parent
        except Exception:
            return None
        return None

    def _handle_hotkey(self, action: str) -> None:
        if self._on_hotkey is not None:
            try:
                self._on_hotkey(action)
            except Exception as exc:
                print(
                    f"Pillarium: shortcut {action!r} failed: {exc}",
                    file=sys.stderr,
                )

    # -----------------------------------------------------------------
    # Ping watchdog
    # -----------------------------------------------------------------
    def _register_ping(self, client: Client) -> None:
        """Remember whether a client answers ``_NET_WM_PING``."""
        try:
            prop = client.window.get_full_property(
                self.atom("WM_PROTOCOLS"), X.AnyPropertyType
            )
        except Exception:
            return
        if not prop or not prop.value:
            return
        ping_atom = self.atom("_NET_WM_PING")
        if any(int(value) == ping_atom for value in prop.value):
            client.ping_supported = True

    def _unregister_ping(self, client_id: int) -> None:
        client = self.clients.get(client_id)
        if client is not None:
            client.ping_supported = False
        self._ping_outstanding.pop(client_id, None)
        for token, owner in list(self._ping_tokens.items()):
            if owner == client_id:
                self._ping_tokens.pop(token, None)

    def _send_ping(self, client: Client) -> None:
        from Xlib.protocol import event as xevent

        for token, owner in list(self._ping_tokens.items()):
            if owner == client.id:
                self._ping_tokens.pop(token, None)
        self._ping_sequence = (self._ping_sequence + 1) % 0x7FFFFFFF
        token = self._ping_sequence or 1
        self._ping_tokens[token] = client.id
        self._ping_outstanding[client.id] = (token, time.time())
        if not self._is_alive(client.window):
            self._ping_outstanding.pop(client.id, None)
            return
        try:
            message = xevent.ClientMessage(
                window=client.window,
                client_type=self.atom("WM_PROTOCOLS"),
                data=(32, [self.atom("_NET_WM_PING"), token, 0, 0, 0]),
            )
            client.window.send_event(message, event_mask=0, propagate=False)
            self.display.flush()
        except Exception:
            pass

    def sweep_pings(self) -> list[int]:
        """Check for hung windows.  Returns the ids that stopped replying."""
        if not self.clients:
            return []
        self._last_ping_sweep = time.time()
        hung: list[int] = []
        now = time.time()
        for client in list(self.clients.values()):
            if not client.ping_supported or client.minimized or client.unresponsive:
                continue
            outstanding = self._ping_outstanding.get(client.id)
            if outstanding is None:
                self._send_ping(client)
                continue
            _token, sent = outstanding
            if now - sent > PING_TIMEOUT:
                client.unresponsive = True
                hung.append(client.id)
        return hung

    def handle_ping_reply(self, event: Any) -> None:
        """Process a ``_NET_WM_PING`` reply."""
        try:
            if event.client_type != self.atom("WM_PROTOCOLS"):
                return
            raw = event.data
            if isinstance(raw, (tuple, list)) and len(raw) == 2 and isinstance(raw[0], int):
                values = raw[1]
            else:
                values = raw
            values = list(values)
            if len(values) < 2 or int(values[0]) != int(self.atom("_NET_WM_PING")):
                return
            token = int(values[1])
        except Exception:
            return
        client_id = self._ping_tokens.pop(token, None)
        if client_id is None:
            return
        self._ping_outstanding.pop(client_id, None)
        client = self.clients.get(client_id)
        if client is not None:
            client.unresponsive = False

    # -----------------------------------------------------------------
    # EWMH
    # -----------------------------------------------------------------
    def _publish_desktops(self) -> None:
        """Publish the virtual desktop state on the root window."""
        try:
            self.root.change_property(
                self.atom("_NET_NUMBER_OF_DESKTOPS"),
                Xatom.CARDINAL,
                32,
                [self.desktop_count],
            )
            self.root.change_property(
                self.atom("_NET_CURRENT_DESKTOP"),
                Xatom.CARDINAL,
                32,
                [self.current_desktop],
            )
            names = []
            for index in range(self.desktop_count):
                label = (
                    self.desktop_names[index]
                    if index < len(self.desktop_names)
                    else f"Desktop {index + 1}"
                )
                names.append(label.encode("utf-8") + b"\x00")
            self.root.change_property(
                self.atom("_NET_DESKTOP_NAMES"),
                # UTF8_STRING shares its atom value with STRING; the
                # names are stored as one NUL separated string.
                Xatom.STRING,
                8,
                b"".join(names),
            )
        except Exception:
            pass

    def _publish_client_list(self) -> None:
        try:
            self.root.change_property(
                self.atom("_NET_CLIENT_LIST"),
                Xatom.WINDOW,
                32,
                [client_id for client_id in self.order if client_id in self.clients],
            )
        except Exception:
            pass

    def _publish_active_window(self) -> None:
        try:
            self.root.change_property(
                self.atom("_NET_ACTIVE_WINDOW"),
                Xatom.WINDOW,
                32,
                [self.focused or 0],
            )
        except Exception:
            pass

    def publish_supported(self) -> None:
        """Tell other applications which EWMH features Pillarium has."""
        supported = [
            "_NET_CLIENT_LIST",
            "_NET_CLIENT_LIST_STACKING",
            "_NET_CURRENT_DESKTOP",
            "_NET_DESKTOP_NAMES",
            "_NET_NUMBER_OF_DESKTOPS",
            "_NET_SUPPORTED",
            "_NET_WORKAREA",
            "_NET_ACTIVE_WINDOW",
            "_NET_CLOSE_WINDOW",
            "_NET_WM_NAME",
            "_NET_WM_DESKTOP",
            "_NET_WM_PID",
            "_NET_WM_STATE",
            "_NET_WM_WINDOW_TYPE",
        ]
        try:
            self.root.change_property(
                self.atom("_NET_SUPPORTED"),
                Xatom.ATOM,
                32,
                [self.atom(name) for name in supported],
            )
        except Exception:
            pass

    def publish_workarea(self) -> None:
        """Publish the usable area of every virtual desktop."""
        try:
            taskbar = self._taskbar_height()
            position = "bottom"
            if self.config is not None:
                position = str(self.config.opt("taskbar", "position", "bottom"))
            areas: list[int] = []
            for index in range(self.desktop_count):
                for monitor in self.monitors.monitors:
                    x, y, width, height = self.monitors.work_area(monitor, taskbar, position)
                    areas.extend([x, y, width, height])
            self.root.change_property(
                self.atom("_NET_WORKAREA"),
                Xatom.CARDINAL,
                32,
                areas,
            )
        except Exception:
            pass

    def _set_client_desktop_property(self, client: Client) -> None:
        try:
            client.window.change_property(
                self.atom("_NET_WM_DESKTOP"), Xatom.CARDINAL, 32, [client.desktop]
            )
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------
    def manage_existing(self) -> None:
        """Take over the windows that were already open."""
        try:
            children = self.root.query_tree().children
        except Exception:
            return
        for window in children:
            if window.id == self.root.id:
                continue
            try:
                if window.get_attributes().override_redirect:
                    continue
            except Exception:
                continue
            if os.environ.get("PILLARIUM_DEBUG"):
                print(
                    f"Pillarium: adopting existing window {hex(window.id)}",
                    file=sys.stderr,
                )
            self.manage(window)

    def shutdown(self) -> None:
        """Release everything Pillarium owns."""
        if self._closed:
            return
        self._closed = True
        try:
            self.hotkeys.release()
        except Exception:
            pass
        for client_id in list(self.clients):
            client = self.clients.get(client_id)
            if client is not None:
                try:
                    # Give the window back to the X server at the place
                    # the user last saw it, so nothing jumps to the
                    # top left corner when Pillarium exits.
                    client.window.reparent(self.root, client.x, client.y)
                    client.window.map()
                except Exception:
                    pass
        for container in list(self._containers.values()):
            try:
                container.destroy()
            except Exception:
                pass
        self._containers.clear()
        self.clients.clear()
        self.order.clear()
        try:
            self.display.flush()
            self.display.sync()
        except Exception:
            pass
        try:
            self.display.close()
        except Exception:
            pass
