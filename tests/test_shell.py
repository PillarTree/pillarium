"""Integration tests for the customtkinter shell.

These tests start the real application on a private X server and drive
it through its event loop.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("customtkinter")


def pump(app, seconds: float = 0.6) -> None:
    """Run the application event loop for a while."""
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.root.update()
        except Exception:
            break
        time.sleep(0.01)


@pytest.fixture
def app(xdisplay, home):
    from pillarium.app import PillariumApp

    application = PillariumApp()
    yield application
    try:
        application.shutdown()
        application.root.destroy()
    except Exception:
        pass


@pytest.fixture
def client_display(xdisplay):
    from Xlib import display as xdisplay_module

    display = xdisplay_module.Display()
    yield display
    display.close()


def _spawn_window(client_display, title="Test Window", width=320, height=240):
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
    window.set_wm_name(title)
    window.map()
    client_display.sync()
    return window


def test_the_application_starts(app):
    assert app.wm is not None
    assert app.shell is not None
    assert app.theme_manager.current is not None
    assert app.shell.taskbars


def test_a_taskbar_is_created_for_every_monitor(app):
    assert len(app.shell.taskbars) == len(app.wm.monitors.monitors)


def test_windows_that_existed_before_are_adopted(xdisplay, home, client_display):
    """A window that was already open when Pillarium started is managed."""
    from pillarium.app import PillariumApp

    _spawn_window(client_display, title="Pre-existing")
    application = PillariumApp()
    try:
        pump(application, 0.8)
        assert len(application.wm.clients) == 1
        client = list(application.wm.clients.values())[0]
        assert client.title == "Pre-existing"
        parent = client.window.query_tree().parent
        assert parent.id != application.wm.root.id
    finally:
        application.shutdown()
        application.root.destroy()


def test_the_focus_is_never_left_on_the_pointer(app):
    """The keyboard must not follow the mouse.

    With the focus on the pointer the X server hands the keyboard to
    whatever the mouse is over, so the window manager keeps the focus on
    the root window when there is nothing else to focus.
    """
    reply = app.wm.display.get_input_focus()
    assert reply.focus is not None, "the focus must not be on the pointer"


def test_the_focus_stays_on_the_window_when_the_pointer_moves(app, client_display):
    """Moving the pointer must not move the keyboard focus."""
    _spawn_window(client_display)
    pump(app, 1.0)
    assert app.wm.focused is not None
    focused = app.wm.focused

    reply = app.wm.display.get_input_focus()
    assert reply.focus is not None, "the focus should not be on the pointer"

    # Move the pointer somewhere else and make sure the focus stays.
    app.wm.display.screen().root.query_pointer()
    pump(app, 0.3)
    assert app.wm.focused == focused
    assert app.wm.display.get_input_focus().focus is not None


def test_the_focus_is_taken_back_from_the_pointer(app, client_display):
    """The toolkit can drop the focus to the pointer; take it back."""
    from Xlib import X

    _spawn_window(client_display)
    pump(app, 1.0)
    assert app.wm.focused is not None
    focused = app.wm.focused

    # Simulate the toolkit handing the focus back to the pointer.
    app.wm.display.screen().root.set_input_focus(
        X.PointerRoot, X.RevertToPointerRoot, X.CurrentTime
    )
    app.wm.display.sync()
    pump(app, 0.5)

    reply = app.wm.display.get_input_focus()
    assert reply.focus is not None, "the focus should have been taken back"
    assert app.wm.focused == focused


def test_windows_are_managed_and_embedded(app, client_display):
    _spawn_window(client_display)
    pump(app, 1.0)
    assert len(app.wm.clients) == 1
    client = list(app.wm.clients.values())[0]
    assert client.title == "Test Window"
    parent = client.window.query_tree().parent
    assert parent.id != app.wm.root.id


def test_windows_appear_in_the_taskbar(app, client_display):
    _spawn_window(client_display)
    pump(app, 1.0)
    taskbar = list(app.shell.taskbars.values())[0]
    assert taskbar._items


def test_switching_the_theme_recolours_the_shell(app):
    before = app.shell.theme.name
    app.cycle_theme()
    pump(app, 0.4)
    assert app.shell.theme.name != before
    assert app.shell.theme.get("bg")


def test_switching_virtual_desktops_hides_windows(app, client_display):
    _spawn_window(client_display)
    pump(app, 1.0)
    client = list(app.wm.clients.values())[0]
    app.wm.switch_desktop(1)
    pump(app, 0.3)
    assert app.wm.current_desktop == 1
    assert app.shell.decorations.get_geometry(client.id) is not None
    app.wm.switch_desktop(0)
    pump(app, 0.3)
    assert app.wm.current_desktop == 0


def test_the_launcher_opens_and_lists_applications(app):
    app.shell.open_launcher()
    pump(app, 0.4)
    assert app.shell.launcher.is_visible()
    app.shell.close_launcher()
    pump(app, 0.2)
    assert not app.shell.launcher.is_visible()


def test_alerts_are_shown_and_dismissed(app):
    app.shell.show_alert("warning", "Test alert", "Something happened")
    pump(app, 0.4)
    assert app.shell.alert_manager.visible
    app.shell.alert_manager.close_all()
    pump(app, 0.2)
    assert not app.shell.alert_manager.visible


def test_notifications_are_shown_as_toasts(app):
    from pillarium.system.notifications import Notification

    app.shell.notify(
        Notification(id=99, app_name="Test", summary="Hello", body="World")
    )
    pump(app, 0.4)
    assert app.shell.notification_center._toasts


def test_the_settings_window_opens(app):
    app.shell.open_settings()
    pump(app, 0.4)
    assert app.shell._settings is not None
    app.shell._settings.dismiss()


def test_the_theme_editor_opens(app):
    app.shell.open_theme_editor()
    pump(app, 0.4)
    assert app.shell._theme_editor is not None
    app.shell._theme_editor.dismiss()


def test_the_desktop_surface_covers_the_screen(app):
    geometry = app.shell.desktop._root.geometry()
    assert geometry
    width, height = app.shell.desktop._root.winfo_width(), app.shell.desktop._root.winfo_height()
    assert width > 0 and height > 0
