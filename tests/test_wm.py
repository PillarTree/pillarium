"""Integration tests for the X11 window manager.

These tests need a real X server; the ``xdisplay`` fixture starts a
private Xvfb when ``$DISPLAY`` is not usable.
"""

from __future__ import annotations

import pytest
from Xlib import X

from pillarium.core.clients import Client
from pillarium.core.wm import WindowManager


class FakeHost:
    """Records what the window manager asks the shell to do."""

    def __init__(self, display):
        self.display = display
        self.created = []
        self.destroyed = []
        self.geometry = {}
        self.active = None
        self.visible = {}
        self.raised = []

    def create(self, client: Client) -> int:
        self.created.append(client.id)
        parent = self.display.screen().root
        window = parent.create_window(
            0,
            0,
            client.width,
            client.height,
            0,
            self.display.screen().root_depth,
            event_mask=X.StructureNotifyMask,
        )
        window.map()
        self.display.sync()
        return int(window.id)

    def destroy(self, client_id: int) -> None:
        self.destroyed.append(client_id)

    def update(self, client: Client) -> None:
        pass

    def set_geometry(self, client_id, x, y, width, height) -> None:
        self.geometry[client_id] = (x, y, width, height)

    def set_active(self, client_id) -> None:
        self.active = client_id

    def set_visible(self, client_id, visible: bool) -> None:
        self.visible[client_id] = visible

    def raise_client(self, client_id) -> None:
        self.raised.append(client_id)

    def get_geometry(self, client_id):
        return self.geometry.get(client_id)


@pytest.fixture
def wm(xdisplay, home):
    from Xlib import display as xdisplay_module

    display = xdisplay_module.Display()
    manager = WindowManager(display=display)
    manager.host = FakeHost(display)
    yield manager
    # The manager closes the display connection as part of its shutdown.
    manager.shutdown()


@pytest.fixture
def client_display(xdisplay):
    """A second connection, so test windows look like foreign clients."""
    from Xlib import display as xdisplay_module

    display = xdisplay_module.Display()
    yield display
    display.close()


def _make_window(wm, client_display, width=300, height=200):
    """Create a window on a second connection, like a real application."""
    root = client_display.screen().root
    window = root.create_window(
        0,
        0,
        width,
        height,
        0,
        client_display.screen().root_depth,
        background_pixel=client_display.screen().white_pixel,
    )
    window.map()
    client_display.sync()
    wm.display.sync()
    return window


def test_a_mapped_window_is_managed(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    assert client is not None
    assert client.id == window.id
    assert client.id in wm.clients
    assert client.id in wm.host.created
    assert client.title
    assert wm.host.geometry[client.id][2:] == (client.width, client.height)


def test_managed_windows_are_embedded(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.display.sync()
    parent = client.window.query_tree().parent
    assert parent.id != wm.root.id


def test_closing_a_window_forgets_it(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.close(client.id)
    assert client.id not in wm.clients
    assert client.id in wm.host.destroyed


def test_windows_move_and_resize(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.move_client(client.id, 200, 150)
    assert (client.x, client.y) == (200, 150)
    wm.resize_client(client.id, 640, 480)
    assert (client.width, client.height) == (640, 480)


def test_resizing_keeps_a_minimum_size(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.resize_client(client.id, 10, 10)
    assert client.width >= 320
    assert client.height >= 240


def test_maximising_uses_the_monitor(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.maximize(client.id)
    assert client.maximized
    monitor = wm.monitors.primary
    assert client.width == monitor.width
    wm.restore(client.id)
    assert not client.maximized


def test_minimising_hides_a_window(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.minimize(client.id)
    assert client.minimized
    assert wm.host.visible[client.id] is False
    wm.restore_minimized(client.id)
    assert not client.minimized


def test_virtual_desktops_hide_other_windows(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.configure_desktops(3, [])
    assert client.desktop == 0
    wm.switch_desktop(1)
    assert wm.current_desktop == 1
    assert wm.host.visible[client.id] is False
    wm.switch_desktop(0)
    assert wm.host.visible[client.id] is True


def test_windows_can_be_moved_between_desktops(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.configure_desktops(3, [])
    wm.move_to_desktop(client.id, 2)
    assert client.desktop == 2
    assert wm.clients_on_desktop(2) == [client]


def test_ewmh_properties_are_published(wm):
    wm.configure_desktops(4, ["One", "Two", "Three", "Four"])
    wm.publish_supported()
    wm.publish_workarea()
    number = wm.root.get_full_property(wm.atom("_NET_NUMBER_OF_DESKTOPS"), X.AnyPropertyType)
    assert number and int(number.value[0]) == 4
    current = wm.root.get_full_property(wm.atom("_NET_CURRENT_DESKTOP"), X.AnyPropertyType)
    assert current and int(current.value[0]) == 0
    names = wm.root.get_full_property(wm.atom("_NET_DESKTOP_NAMES"), X.AnyPropertyType)
    value = names.value
    if isinstance(value, tuple):
        value = value[1]
    assert b"One" in value
    assert b"Four" in value


def test_the_active_window_is_published(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    wm.focus(client.id)
    active = wm.root.get_full_property(wm.atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
    assert active and int(active.value[0]) == client.id


def test_the_client_list_is_published(wm, client_display):
    window = _make_window(wm, client_display)
    client = wm.manage(window)
    listing = wm.root.get_full_property(wm.atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
    assert listing and int(listing.value[0]) == client.id


def test_focus_cycles_through_the_windows(wm, client_display):
    first = wm.manage(_make_window(wm, client_display))
    second = wm.manage(_make_window(wm, client_display))
    wm.focus(first.id)
    wm.focus_next()
    assert wm.focused == second.id
    wm.focus_next(reverse=True)
    assert wm.focused == first.id


def test_hotkeys_are_grabbed(wm):
    from pillarium.config import Config

    wm.hotkeys.configure(Config().hotkeys)
    assert len(wm.hotkeys.shortcuts) > 5
    assert wm.hotkeys.handle(
        wm.hotkeys.shortcuts[0].keycode, wm.hotkeys.shortcuts[0].modifiers
    ) == wm.hotkeys.shortcuts[0].action


def test_monitors_are_detected(wm):
    assert wm.monitors.count >= 1
    monitor = wm.monitors.primary
    assert monitor.width > 0 and monitor.height > 0
    assert wm.monitors.at(monitor.x + 5, monitor.y + 5) is monitor


def test_the_pointer_position_is_read_from_the_server(wm):
    """The pointer position must come from the server, not a guess."""
    wm.root.warp_pointer(120, 240)
    wm.display.sync()
    assert wm.monitors.pointer_position() == (120, 240)


def test_the_monitor_under_the_pointer_is_found(wm):
    wm.root.warp_pointer(7, 9)
    wm.display.sync()
    position = wm.monitors.pointer_position()
    assert wm.monitors.at(*position) is wm.monitors.at(*position)
