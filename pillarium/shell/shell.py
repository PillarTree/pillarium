"""The shell: everything the user sees and interacts with.

The shell owns the desktop surface, the per-monitor taskbars, the window
decorations and every popup.  It translates user actions into calls on
the window manager and keeps the two layers in sync.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Callable

import customtkinter as ctk

from ..core.clients import Client
from ..core.monitors import Monitor
from ..theme.tokens import Theme
from .alerts import AlertManager, AlertSpec
from .base import TransientManager
from .decorations import DecorationManager
from .desktop import DesktopSurface
from .launcher import Launcher
from .menu import MenuItem, PopupMenu, build_items
from .notifications import NotificationCenter
from .panels import AudioMixer, CalendarPanel, ProcessPanel
from .settings import Settings, SettingsCallbacks
from .taskbar import Taskbar, TaskbarCallbacks
from .theme_editor import ThemeEditor
from .widgets import Themed


class Shell:
    """Coordinates the user interface and the window manager."""

    def __init__(self, app: Any):
        self.app = app
        self.root: ctk.CTk = app.root
        self.config = app.config
        self.theme_manager = app.theme_manager
        self.wm = app.wm
        self.theme: Theme = app.theme_manager.current
        self._themed = Themed(self.theme)

        self.transients = TransientManager()

        self.desktop = DesktopSurface(
            self.root,
            self.theme,
            on_launch=self.launch_desktop_item,
            on_select=self._on_desktop_select,
            on_context_menu=self.open_desktop_menu,
        )

        self.decorations = DecorationManager(self.root, self.theme)
        self._wire_decorations()

        self.launcher = Launcher(self.root, self.theme, self.launch_application)
        self.launcher.set_provider(self._application_entries)
        self.launcher.on_dismiss(self._on_launcher_dismissed)

        self.notification_center = NotificationCenter(
            self.root, self.theme, self.primary_monitor
        )
        self.alert_manager = AlertManager(
            self.root,
            self.theme,
            on_sound=self.app.play_alert_sound,
            on_focus=self.app.wm.focus_external,
            on_release=self.app.wm.restore_focus,
        )

        self.mixer = AudioMixer(
            self.root,
            self.theme,
            on_change=self.refresh_status,
            on_mute=self._mixer_mute,
            on_volume=self._mixer_volume,
        )
        self.process_panel = ProcessPanel(
            self.root, self.theme, self._kill_process, self.refresh_processes
        )
        self.calendar = CalendarPanel(self.root, self.theme, self.open_processes)

        self.taskbars: dict[str, Taskbar] = {}
        self._menu: PopupMenu | None = None
        self._settings: Settings | None = None
        self._theme_editor: ThemeEditor | None = None
        self._last_clock = ""
        self._quick_launch = list(self.config.quick_launch)

    # -----------------------------------------------------------------
    # Wiring
    # -----------------------------------------------------------------
    def _wire_decorations(self) -> None:
        self.decorations.on_activate_requested = self._activate_client
        self.decorations.on_close_requested = lambda cid: self.wm.close(cid)
        self.decorations.on_minimize_requested = lambda cid: self.wm.minimize(cid)
        self.decorations.on_maximize_requested = lambda cid: self.wm.toggle_maximize(cid)
        self.decorations.on_move_requested = lambda cid, x, y: self.wm.move_client(cid, x, y)
        self.decorations.on_resize_requested = lambda cid, w, h: self.wm.resize_client(cid, w, h)
        self.decorations.on_menu_requested = self.open_window_menu

    # -----------------------------------------------------------------
    # Monitors
    # -----------------------------------------------------------------
    def primary_monitor(self) -> Monitor:
        """The monitor the pointer is on, or the primary one."""
        return self.wm.monitors.pointer_monitor()

    def build_taskbars(self) -> None:
        """Create or update the taskbar of every monitor."""
        per_monitor = bool(self.config.opt("monitors", "taskbar_per_monitor", True))
        monitors = self.wm.monitors.monitors
        wanted = {monitor.name for monitor in monitors} if per_monitor else {
            self.wm.monitors.primary.name
        }

        for name in list(self.taskbars):
            if name not in wanted:
                taskbar = self.taskbars.pop(name)
                try:
                    taskbar.dismiss()
                    taskbar.destroy()
                except Exception:
                    pass

        for monitor in monitors:
            if monitor.name in self.taskbars:
                self.taskbars[monitor.name].update_monitor(monitor)
                continue
            taskbar = Taskbar(self.root, self.theme, monitor, self.config, _TaskbarBridge(self))
            self.taskbars[monitor.name] = taskbar
            taskbar.show()

        self.refresh_windows()
        self.refresh_desktops()
        self.refresh_status()

    # -----------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------
    def refresh_windows(self) -> None:
        """Update the window buttons of every taskbar.

        With several monitors each taskbar only lists the windows that
        live on its own monitor.
        """
        visible = [
            client
            for client in self.wm.clients.values()
            if client.desktop == self.wm.current_desktop
        ]
        visible.sort(
            key=lambda client: self.wm.order.index(client.id)
            if client.id in self.wm.order
            else 0
        )
        per_monitor = len(self.wm.monitors.monitors) > 1
        for name, taskbar in self.taskbars.items():
            if per_monitor:
                clients = [client for client in visible if client.monitor == name]
            else:
                clients = visible
            taskbar.set_windows(clients, self.wm.focused)

    def refresh_desktops(self) -> None:
        """Update the virtual desktop switcher."""
        for taskbar in self.taskbars.values():
            taskbar.set_desktops(
                self.wm.desktop_count, self.wm.current_desktop, self.wm.desktop_names
            )

    def refresh_status(self) -> None:
        """Update the status indicators of every taskbar."""
        state = self.app.status
        for taskbar in self.taskbars.values():
            taskbar.set_status(
                wifi=state.wifi_connected,
                bluetooth=state.bluetooth_powered,
                audio=not state.audio_muted,
                ethernet=state.ethernet_connected,
                battery=state.battery,
            )
            taskbar.set_audio_muted(state.audio_muted)

    def refresh_clock(self) -> None:
        """Update the clock of every taskbar."""
        now = time.strftime(self.config.time_format)
        date = time.strftime(self.config.date_format)
        text = f"{now}\n{date}"
        if text == self._last_clock:
            return
        self._last_clock = text
        for taskbar in self.taskbars.values():
            taskbar.set_clock(now, date)

    def refresh_quick_launch(self) -> None:
        """Rebuild the pinned application buttons."""
        self._quick_launch = list(self.config.quick_launch)
        running = self._is_app_running
        for taskbar in self.taskbars.values():
            taskbar.set_quick_launch(self._quick_launch, running)

    def refresh_processes(self) -> None:
        """Reload the process list."""
        processes = self.app.process_manager.list()
        self.process_panel.set_processes(processes)

    # -----------------------------------------------------------------
    # Applications
    # -----------------------------------------------------------------
    def _application_entries(self) -> list[dict]:
        """The corpus the launcher searches."""
        entries: list[dict] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for app in self.app.catalog.applications:
            key = (app.label.lower(), tuple(app.cmd))
            if key in seen:
                continue
            seen.add(key)
            entries.append(app.to_dict())
        for item in self.config.desktop_icons:
            key = (str(item.get("label", "")).lower(), tuple(item.get("cmd", [])))
            if key in seen:
                continue
            seen.add(key)
            entries.append(dict(item))
        if bool(self.config.opt("launcher", "include_quick_launch", True)):
            for item in self.config.quick_launch:
                key = (str(item.get("label", "")).lower(), tuple(item.get("cmd", [])))
                if key in seen:
                    continue
                seen.add(key)
                entries.append(dict(item))
        return entries

    def launch_application(self, entry: dict) -> None:
        """Start an application."""
        self.app.launcher.launch(entry.get("cmd") or [])

    def launch_desktop_item(self, item: dict) -> None:
        """Start an application from a desktop shortcut."""
        self.app.launcher.launch(item.get("cmd") or [])

    def _on_desktop_select(self, _index: int | None) -> None:
        self.transients.close_all()

    def _is_app_running(self, item: dict) -> bool:
        """Is the pinned application already running?"""
        cmd = item.get("cmd") or []
        if not cmd:
            return False
        label = str(item.get("label", "")).lower()
        basename = os.path.basename(cmd[0]).lower()
        for client in self.wm.clients.values():
            if label and label in client.title.lower():
                return True
            if client.matches_class(basename):
                return True
        return False

    # -----------------------------------------------------------------
    # Window actions
    # -----------------------------------------------------------------
    def _activate_client(self, client_id: int) -> None:
        client = self.wm.clients.get(client_id)
        if client is None:
            return
        if self.wm.focused == client_id and not client.minimized:
            self.wm.minimize(client_id)
            return
        if client.minimized:
            self.wm.restore_minimized(client_id)
            return
        self.wm.focus(client_id)

    def toggle_maximize(self, client_id: int) -> None:
        self.wm.toggle_maximize(client_id)

    # -----------------------------------------------------------------
    # Menus
    # -----------------------------------------------------------------
    def open_menu(self, items: list[Any], x: int, y: int, on_select: Callable[[Any], None]) -> None:
        """Show a popup menu at the given position."""
        self.close_menu()
        menu = PopupMenu(self.root, self.theme, build_items(items), on_select)
        self._menu = menu
        self.transients.register(menu)
        menu.show_at(x, y, self._screen_size())

    def close_menu(self) -> None:
        """Close the open popup menu."""
        if self._menu is not None:
            try:
                self._menu.dismiss()
            except Exception:
                pass
            self._menu = None
        self.transients.close_all()

    def _screen_size(self) -> tuple[int, int]:
        try:
            return self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        except Exception:
            return (1920, 1080)

    def _status_anchor(self, kind: str) -> tuple[int, int]:
        """Position on screen a status menu should be anchored to."""
        monitor = self.primary_monitor()
        taskbar = self.taskbars.get(monitor.name)
        if taskbar is None:
            return (monitor.x + 40, monitor.y + monitor.height - 220)
        return taskbar.anchor_for(kind)

    # -- window menu --------------------------------------------------
    def open_window_menu(self, client_id: int, x: int, y: int) -> None:
        """Right click menu of a managed window."""
        client = self.wm.clients.get(client_id)
        if client is None:
            return
        order = self.wm.order
        index = order.index(client_id) if client_id in order else 0
        items: list[Any] = [
            {
                "label": "Move Left",
                "action": ("move_left", None),
                "enabled": index > 0,
            },
            {
                "label": "Move Right",
                "action": ("move_right", None),
                "enabled": index < len(order) - 1,
            },
            {"label": "Restore" if client.minimized else "Minimize", "action": ("minimize", None)},
            {"label": "Restore" if client.maximized else "Maximize", "action": ("maximize", None)},
            {"label": "Move to Next Desktop", "action": ("next_desktop", None)},
            {"label": "Move to Previous Desktop", "action": ("previous_desktop", None)},
        ]
        monitors = self.wm.monitors.monitors
        if len(monitors) > 1:
            for monitor in monitors:
                if monitor.name == client.monitor:
                    continue
                items.append(
                    {
                        "label": f"Move to {monitor.name}",
                        "action": ("move_monitor", monitor.name),
                    }
                )
        items.append(
            {
                "label": "Remove from Quick Launch"
                if self._is_pinned(client)
                else "Add to Quick Launch",
                "action": ("toggle_pin", None),
            }
        )
        items.append(MenuItem.divider())
        items.append({"label": "Close Window", "action": ("close", None)})

        self.open_menu(items, x, y, lambda action: self._window_menu_action(client_id, action))

    def _is_pinned(self, client: Client) -> bool:
        for item in self.config.quick_launch:
            if str(item.get("label", "")).lower() == client.title.lower():
                return True
            cmd = item.get("cmd") or []
            if cmd and cmd[0].lower() == client.title.lower():
                return True
        return False

    def _window_menu_action(self, client_id: int, action: Any) -> None:
        if not isinstance(action, tuple) or not action:
            return
        kind, value = action[0], action[1] if len(action) > 1 else None
        order = self.wm.order
        index = order.index(client_id) if client_id in order else 0
        if kind == "move_left" and index > 0:
            order.insert(index - 1, order.pop(index))
        elif kind == "move_right" and index < len(order) - 1:
            order.insert(index + 1, order.pop(index))
        elif kind == "minimize":
            client = self.wm.clients.get(client_id)
            if client is not None and client.minimized:
                self.wm.restore_minimized(client_id)
            else:
                self.wm.minimize(client_id)
        elif kind == "maximize":
            client = self.wm.clients.get(client_id)
            if client is not None and client.maximized:
                self.wm.restore(client_id)
            else:
                self.wm.maximize(client_id)
        elif kind == "next_desktop":
            self.wm.move_to_desktop(client_id, (client.desktop + 1) % self.wm.desktop_count)
        elif kind == "previous_desktop":
            self.wm.move_to_desktop(
                client_id, (client.desktop - 1) % self.wm.desktop_count
            )
        elif kind == "move_monitor":
            monitor = self.wm.monitors.by_name(str(value))
            if monitor is not None:
                self.wm.move_client_to_monitor(client_id, monitor)
        elif kind == "toggle_pin":
            self._toggle_pin(client_id)
        elif kind == "close":
            self.wm.close(client_id)
        self.refresh_windows()

    def _toggle_pin(self, client_id: int) -> None:
        client = self.wm.clients.get(client_id)
        if client is None:
            return
        items = list(self.config.quick_launch)
        if self._is_pinned(client):
            items = [
                item
                for item in items
                if str(item.get("label", "")).lower() != client.title.lower()
            ]
        else:
            items.append(
                {
                    "cmd": [client.wm_class_name or client.title.lower()],
                    "label": client.title,
                }
            )
        self.config.quick_launch = items
        self.refresh_quick_launch()

    # -- desktop menu -------------------------------------------------
    def open_desktop_menu(self, x: int, y: int) -> None:
        """Right click menu of the desktop."""
        items: list[Any] = [
            {"label": "Change Wallpaper…", "action": ("wallpaper", None)},
            {"label": "Reset Default Wallpaper", "action": ("wallpaper_reset", None)},
            MenuItem.divider(),
            {"label": "Display Settings…", "action": ("settings", None)},
            {"label": "Theme Editor…", "action": ("theme_editor", None)},
            {"label": "Show Desktop", "action": ("show_desktop", None)},
        ]
        self.open_menu(items, x, y, self._desktop_menu_action)

    def _desktop_menu_action(self, action: Any) -> None:
        if not isinstance(action, tuple) or not action:
            return
        kind = action[0]
        if kind == "wallpaper":
            self.app.change_wallpaper()
        elif kind == "wallpaper_reset":
            self.app.reset_wallpaper()
        elif kind == "settings":
            self.open_settings()
        elif kind == "theme_editor":
            self.open_theme_editor()
        elif kind == "show_desktop":
            self.wm.switch_desktop((self.wm.current_desktop + 1) % self.wm.desktop_count)

    # -- power menu ----------------------------------------------------
    def open_power_menu(self, x: int, y: int) -> None:
        """The power menu."""
        items: list[Any] = [
            {"label": "Restart", "action": ("restart", None)},
            {"label": "Shut Down", "action": ("shutdown", None)},
            {"label": "Log Out", "action": ("logout", None)},
            MenuItem.divider(),
            {"label": "Cancel", "action": ("cancel", None)},
        ]
        self.open_menu(items, x, y, self._power_menu_action)

    def _power_menu_action(self, action: Any) -> None:
        if not isinstance(action, tuple) or not action:
            return
        kind = action[0]
        if kind == "cancel":
            return
        labels = {
            "restart": ("Restart System", "Are you sure you want to restart?"),
            "shutdown": ("Shut Down System", "Are you sure you want to shut down?"),
            "logout": ("Log Out", "Are you sure you want to log out?"),
        }
        if kind not in labels:
            return
        title, message = labels[kind]
        self.alert_manager.show(
            AlertSpec(
                level="warning",
                title=title,
                message=message,
                actions=[
                    (title.split()[0], lambda: self._perform_power(kind)),
                    ("Cancel", lambda: None),
                ],
                sound=False,
            )
        )

    def _perform_power(self, kind: str) -> None:
        if kind == "logout":
            self.app.quit()
            return
        commands = {
            "restart": [["systemctl", "reboot"], ["reboot"]],
            "shutdown": [["systemctl", "poweroff"], ["poweroff"], ["shutdown", "-h", "now"]],
        }
        for command in commands.get(kind, []):
            try:
                subprocess.Popen(command, start_new_session=True)
                return
            except (OSError, ValueError):
                continue

    # -- status menus --------------------------------------------------
    def open_status_menu(self, kind: str, x: int, y: int) -> None:
        """Show the menu belonging to a status indicator."""
        handlers = {
            "wifi": self._wifi_menu_items,
            "ethernet": self._ethernet_menu_items,
            "bluetooth": self._bluetooth_menu_items,
            "audio": self._audio_menu_items,
            "battery": self._battery_menu_items,
        }
        builder = handlers.get(kind)
        if builder is None:
            return
        items = builder()
        self.open_menu(items, x, y, lambda action: self._status_menu_action(kind, action))

    def _wifi_menu_items(self) -> list[Any]:
        state = self.app.status
        if not state.wifi_available:
            return [{"label": "Wi-Fi unavailable", "enabled": False}, {"label": "Cancel"}]
        items: list[Any] = [
            {
                "label": "Turn Wi-Fi Off" if state.wifi_enabled else "Turn Wi-Fi On",
                "action": ("toggle_radio", None),
            },
            {"label": "Rescan Networks", "action": ("rescan", None)},
        ]
        if state.wifi_enabled:
            for network in state.networks[:8]:
                if network.in_use:
                    items.append(
                        {"label": f"Disconnect: {network.ssid[:22]}", "action": ("disconnect", None)}
                    )
                else:
                    items.append(
                        {"label": f"Connect: {network.ssid[:22]}", "action": ("connect", network.ssid)}
                    )
        items.append({"label": "Cancel"})
        return items

    def _ethernet_menu_items(self) -> list[Any]:
        state = self.app.status
        if not state.ethernet_available:
            return [{"label": "Ethernet unavailable", "enabled": False}, {"label": "Cancel"}]
        items: list[Any] = []
        if state.ethernet_connected:
            name = state.ethernet_connection or state.ethernet_device or "Ethernet"
            items.append({"label": f"Connected: {name[:24]}", "enabled": False})
            items.append({"label": "Disconnect", "action": ("disconnect", None)})
        else:
            items.append({"label": "Connect Ethernet", "action": ("connect", None)})
        items.append({"label": "Cancel"})
        return items

    def _bluetooth_menu_items(self) -> list[Any]:
        state = self.app.status
        if not state.bluetooth_available:
            return [{"label": "Bluetooth unavailable", "enabled": False}, {"label": "Cancel"}]
        items: list[Any] = [
            {
                "label": "Turn Bluetooth Off" if state.bluetooth_powered else "Turn Bluetooth On",
                "action": ("toggle_power", None),
            },
            {
                "label": "Stop Scanning" if state.bluetooth_scanning else "Scan for Devices",
                "action": ("scan", None),
            },
        ]
        for device in state.bluetooth_devices[:8]:
            if device.connected:
                items.append(
                    {"label": f"Disconnect: {device.name[:22]}", "action": ("disconnect", device.mac)}
                )
            else:
                items.append(
                    {"label": f"Connect: {device.name[:22]}", "action": ("connect", device.mac)}
                )
        items.append({"label": "Cancel"})
        return items

    def _audio_menu_items(self) -> list[Any]:
        state = self.app.status
        if not state.audio_available:
            return [{"label": "Audio unavailable", "enabled": False}, {"label": "Cancel"}]
        items: list[Any] = [
            {
                "label": f"Unmute ({state.audio_volume}%)"
                if state.audio_muted
                else f"Mute ({state.audio_volume}%)",
                "action": ("mute", None),
            },
            {"label": "Volume +5%", "action": ("volume_up", None)},
            {"label": "Volume -5%", "action": ("volume_down", None)},
            {"label": "Open Audio Mixer", "action": ("mixer", None)},
        ]
        if state.audio_sink:
            items.append({"label": f"Output: {state.audio_sink[:28]}", "enabled": False})
        items.append({"label": "Cancel"})
        return items

    def _battery_menu_items(self) -> list[Any]:
        state = self.app.status
        if not state.battery.available:
            return [{"label": "No battery found", "enabled": False}, {"label": "Cancel"}]
        return [
            {"label": f"Battery: {state.battery.percent}%", "enabled": False},
            {"label": state.battery.label, "enabled": False},
            {"label": "Cancel"},
        ]

    def _status_menu_action(self, kind: str, action: Any) -> None:
        if not isinstance(action, tuple) or not action:
            return
        name = action[0]
        value = action[1] if len(action) > 1 else None
        if kind == "wifi":
            if name == "toggle_radio":
                self.app.network.set_wifi_radio(not self.app.status.wifi_enabled)
            elif name == "rescan":
                self.app.network.scan_wifi()
            elif name == "connect":
                self.app.network.connect_wifi(str(value))
            elif name == "disconnect":
                self.app.network.disconnect_wifi()
        elif kind == "ethernet":
            if name == "connect" and self.app.status.ethernet_device:
                self.app.network.connect_ethernet(self.app.status.ethernet_device)
            elif name == "disconnect" and self.app.status.ethernet_device:
                self.app.network.disconnect_ethernet(self.app.status.ethernet_device)
        elif kind == "bluetooth":
            if name == "toggle_power":
                self.app.bluetooth.set_power(not self.app.status.bluetooth_powered)
            elif name == "scan":
                self.app.bluetooth.set_scanning(not self.app.status.bluetooth_scanning)
            elif name == "connect":
                self.app.bluetooth.connect(str(value))
            elif name == "disconnect":
                self.app.bluetooth.disconnect(str(value))
        elif kind == "audio":
            if name == "mute":
                self.app.audio.toggle_mute()
            elif name == "volume_up":
                self.app.audio.nudge_volume(5)
            elif name == "volume_down":
                self.app.audio.nudge_volume(-5)
            elif name == "mixer":
                self.open_mixer()
        self.app.refresh_status()

    # -----------------------------------------------------------------
    # Panels
    # -----------------------------------------------------------------
    def open_launcher(self) -> None:
        """Show the application launcher."""
        monitor = self.primary_monitor()
        x = monitor.x + 24
        y = monitor.y + monitor.height - 460 - 60
        self._close_panels(exclude=self.launcher)
        self.launcher.open(x, y, self._screen_size())
        # The launcher has a text field, so it needs the keyboard focus.
        self._focus_input(self.launcher, self.launcher.search)
        for taskbar in self.taskbars.values():
            taskbar.set_launcher_active(True)

    def _focus_input(self, window: Any, widget: Any = None) -> None:
        """Give the keyboard to a window of the shell.

        The focus can only be moved once the window is mapped, so the
        assignment is repeated shortly after the window was shown.
        """

        def apply() -> None:
            xid = window.take_focus(widget)
            if xid:
                self.app.wm.focus_external(xid)

        apply()
        self.root.after(60, apply)

    def close_launcher(self) -> None:
        self.launcher.dismiss()
        self.app.wm.restore_focus()
        for taskbar in self.taskbars.values():
            taskbar.set_launcher_active(False)

    def _on_launcher_dismissed(self) -> None:
        """Give the keyboard back to the application when the launcher closes."""
        self.app.wm.restore_focus()
        for taskbar in self.taskbars.values():
            taskbar.set_launcher_active(False)

    def _close_panels(self, exclude: Any = None) -> None:
        """Hide every panel except ``exclude``.

        Only one popup may be visible at a time, otherwise they would
        overlap each other.
        """
        for window in (self.launcher, self.mixer, self.process_panel, self.calendar):
            if window is exclude:
                continue
            try:
                window.hide()
            except Exception:
                pass
        if exclude is not self.launcher:
            for taskbar in self.taskbars.values():
                taskbar.set_launcher_active(False)

    def open_mixer(self) -> None:
        """Show the audio mixer."""
        nodes = self.app.audio.nodes()
        self.mixer.set_nodes(nodes[0], nodes[1])
        monitor = self.primary_monitor()
        x = monitor.x + monitor.width - 420
        y = monitor.y + monitor.height - 520
        self._close_panels(exclude=self.mixer)
        self.mixer.place(x, y, 380, 460)
        self.mixer.show()

    def open_processes(self) -> None:
        """Show the process list."""
        self.refresh_processes()
        monitor = self.primary_monitor()
        x = monitor.x + 40
        y = monitor.y + 60
        self._close_panels(exclude=self.process_panel)
        self.process_panel.place(x, y, 460, 460)
        self.process_panel.show()

    def open_calendar(self) -> None:
        """Show the calendar."""
        monitor = self.primary_monitor()
        x = monitor.x + monitor.width - 340
        y = monitor.y + monitor.height - 460
        self._close_panels(exclude=self.calendar)
        self.calendar.place(x, y, 300, 320)
        self.calendar.show()

    def open_settings(self) -> None:
        """Show the settings window."""
        if self._settings is not None:
            try:
                self._settings.destroy()
            except Exception:
                pass
        self._close_panels()
        self._settings = Settings(
            self.root, self.theme, self.config, self.theme_manager, _SettingsBridge(self)
        )
        screen_w, screen_h = self._screen_size()
        self._settings.place(
            (screen_w - 620) // 2, (screen_h - 520) // 2, 620, 520
        )
        self._settings.show()

    def open_theme_editor(self) -> None:
        """Show the theme editor."""
        if self._theme_editor is not None:
            try:
                self._theme_editor.destroy()
            except Exception:
                pass
        self._theme_editor = ThemeEditor(
            self.root,
            self.theme,
            on_apply=self._apply_theme_preview,
            on_save=self._save_theme,
            on_delete=self._delete_theme,
            on_import=self.import_desktop_theme,
        )
        screen_w, screen_h = self._screen_size()
        self._theme_editor.place(
            (screen_w - 460) // 2, (screen_h - 520) // 2, 460, 520
        )
        self._theme_editor.show()

    def _apply_theme_preview(self, theme: Theme) -> None:
        self.app.apply_theme(theme, persist=False)

    def _save_theme(self, theme: Theme, name: str) -> None:
        theme.name = name
        self.theme_manager.save_user_theme(theme)
        self.theme_manager.reload()
        self.app.apply_theme(theme)

    def _delete_theme(self, name: str) -> None:
        self.theme_manager.delete_user_theme(name)
        self.theme_manager.reload()
        self.app.apply_theme(self.theme_manager.current)

    def import_desktop_theme(self) -> None:
        """Import the colours advertised by the desktop environment."""
        theme, preferences = self.theme_manager.import_freedesktop()
        if theme is None:
            self.show_alert(
                "warning",
                "No desktop preferences found",
                "The freedesktop.org settings portal did not report any colours.",
            )
            return
        self.app.apply_theme(theme)
        self.app.config.theme = theme.slug
        self.show_alert(
            "startup",
            "Theme imported",
            f"Imported {preferences.describe()} from {preferences.source}.",
        )

    # -----------------------------------------------------------------
    # Alerts and notifications
    # -----------------------------------------------------------------
    def show_alert(
        self,
        level: str,
        title: str,
        message: str = "",
        app: str = "",
        detail: str = "",
        actions: list[tuple[str, Callable[[], None]]] | None = None,
        timeout: float | None = None,
        sound: bool = True,
    ) -> None:
        """Show a modal alert."""
        self.alert_manager.show(
            AlertSpec(
                level=level,
                title=title,
                message=message,
                app=app,
                detail=detail,
                actions=actions or [],
                timeout=timeout,
                sound=sound,
            )
        )

    def notify(self, notification: Any) -> None:
        """Show a desktop notification."""
        if getattr(notification, "critical", False):
            self.show_alert(
                "error",
                notification.summary or "Notification",
                notification.body,
                app=notification.app_name,
            )
            return
        self.notification_center.show(notification)

    # -----------------------------------------------------------------
    # Mixer helpers
    # -----------------------------------------------------------------
    def _mixer_mute(self, node: Any) -> None:
        self.app.audio.toggle_node_mute(node)
        self.open_mixer()

    def _mixer_volume(self, node: Any, percent: int) -> None:
        self.app.audio.set_node_volume(node, percent)

    def _kill_process(self, pid: int) -> None:
        self.app.process_manager.terminate(pid)
        self.refresh_processes()

    # -----------------------------------------------------------------
    # Theme
    # -----------------------------------------------------------------
    def apply_theme(self, theme: Theme) -> None:
        """Re-colour every surface of the shell."""
        self.theme = theme
        self._themed = Themed(theme)
        self.desktop.apply_theme(theme)
        self.decorations.apply_theme(theme)
        self.launcher.apply_theme(theme)
        self.mixer.apply_theme(theme)
        self.process_panel.apply_theme(theme)
        self.calendar.apply_theme(theme)
        self.notification_center.apply_theme(theme)
        self.alert_manager.apply_theme(theme)
        for taskbar in self.taskbars.values():
            taskbar.apply_theme(theme)
        if self._settings is not None:
            self._settings.apply_theme(theme)
        if self._theme_editor is not None:
            self._theme_editor.apply_theme(theme)
        self.refresh_quick_launch()
        self.refresh_windows()
        self.refresh_status()

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------
    def shutdown(self) -> None:
        """Close every window the shell owns."""
        self.close_menu()
        self.notification_center.dismiss_all()
        self.alert_manager.close_all()
        for window in (
            self.launcher,
            self.mixer,
            self.process_panel,
            self.calendar,
        ):
            try:
                window.dismiss()
            except Exception:
                pass
        for taskbar in self.taskbars.values():
            try:
                taskbar.dismiss()
            except Exception:
                pass


class _TaskbarBridge(TaskbarCallbacks):
    """Routes taskbar events to the shell."""

    def __init__(self, shell: Shell):
        self.shell = shell

    def on_launcher(self) -> None:
        self.shell.open_launcher()

    def on_quick_launch(self, item: dict) -> None:
        self.shell.app.launcher.launch(item.get("cmd") or [])

    def on_window(self, client_id: int) -> None:
        self.shell._activate_client(client_id)

    def on_window_menu(self, client_id: int, x: int, y: int) -> None:
        self.shell.open_window_menu(client_id, x, y)

    def on_desktop(self, index: int) -> None:
        self.shell.wm.switch_desktop(index)

    def on_wifi(self) -> None:
        self.shell.open_status_menu("wifi", *self.shell._status_anchor("wifi"))

    def on_bluetooth(self) -> None:
        self.shell.open_status_menu("bluetooth", *self.shell._status_anchor("bluetooth"))

    def on_audio(self) -> None:
        self.shell.open_status_menu("audio", *self.shell._status_anchor("audio"))

    def on_ethernet(self) -> None:
        self.shell.open_status_menu("ethernet", *self.shell._status_anchor("ethernet"))

    def on_battery(self) -> None:
        self.shell.open_status_menu("battery", *self.shell._status_anchor("battery"))

    def on_clock(self) -> None:
        self.shell.open_calendar()

    def on_power(self) -> None:
        self.shell.open_power_menu(*self.shell._status_anchor("power"))


class _SettingsBridge(SettingsCallbacks):
    """Routes settings events to the shell."""

    def __init__(self, shell: Shell):
        self.shell = shell

    def on_theme_selected(self, name: str) -> None:
        theme = self.shell.theme_manager.get(name)
        if theme is not None:
            self.shell.app.apply_theme(theme)

    def on_theme_editor(self) -> None:
        self.shell.open_theme_editor()

    def on_import_theme(self) -> None:
        self.shell.import_desktop_theme()

    def on_desktops_changed(self, count: int, names: list[str]) -> None:
        self.shell.config.desktops = count
        self.shell.config.set("desktop_names", names)
        self.shell.app.apply_desktop_settings()

    def on_change_wallpaper(self) -> None:
        self.shell.app.change_wallpaper()

    def on_reset_wallpaper(self) -> None:
        self.shell.app.reset_wallpaper()

    def on_taskbar_option(self, key: str, value: Any) -> None:
        if key == "placement":
            self.shell.config.set_opt("monitors", "placement", value)
        else:
            self.shell.config.set_opt("taskbar", key, value)
        self.shell.app.apply_display_settings()

    def on_focus_option(self, key: str, value: Any) -> None:
        self.shell.config.set_opt("focus", key, value)
        self.shell.wm.refresh_event_mask()

    def on_add_launch(self) -> None:
        self.shell.app.prompt_add_launch()

    def on_launch_changed(self) -> None:
        self.shell.refresh_quick_launch()
