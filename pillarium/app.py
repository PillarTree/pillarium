"""The Pillarium application.

:class:`PillariumApp` owns the customtkinter root window, the X11
window manager, the shell and every background service.  It also runs
the main loop, which pumps X11 events from Tk's event loop and drives the
periodic polls (clock, network, battery, audio, notifications).
"""

from __future__ import annotations

import select
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import customtkinter as ctk

from . import paths
from .config import Config
from .core import xerror
from .core.wm import WindowManager
from .shell.shell import Shell
from .system.apps import ApplicationCatalog
from .system.audio import AudioClient
from .system.battery import BatteryMonitor, BatteryState
from .system.bluetooth import BluetoothClient, BluetoothDevice
from .system.launcher import Launcher
from .system.network import NetworkManagerClient, WirelessNetwork
from .system.notifications import NotificationService
from .system.processes import ProcessManager
from .system.sound import SoundPlayer
from .system.wallpaper import WallpaperManager
from .theme.manager import ThemeManager
from .theme.tokens import Theme

#: How often the X11 event queue is drained (milliseconds).
X_POLL_INTERVAL = 12
#: How often the system status is refreshed (seconds).
STATUS_INTERVAL = 4.0
#: How often the clock is refreshed (seconds).
CLOCK_INTERVAL = 1.0


@dataclass
class Status:
    """A snapshot of everything the taskbar shows."""

    wifi_available: bool = False
    wifi_enabled: bool = True
    wifi_connected: bool = False
    wifi_networks: list[WirelessNetwork] = field(default_factory=list)
    bluetooth_available: bool = False
    bluetooth_powered: bool = False
    bluetooth_scanning: bool = False
    bluetooth_devices: list[BluetoothDevice] = field(default_factory=list)
    audio_available: bool = False
    audio_volume: int = 0
    audio_muted: bool = False
    audio_sink: str | None = None
    ethernet_available: bool = False
    ethernet_connected: bool = False
    ethernet_device: str | None = None
    ethernet_connection: str | None = None
    battery: BatteryState = field(default_factory=BatteryState)


class PillariumApp:
    """The running Pillarium session."""

    def __init__(self) -> None:
        paths.ensure_dirs()
        paths.install_default_config()
        # No X error may take the session down, not even one raised by
        # the toolkit's own connection.
        xerror.install()
        self.config = Config.load()
        self.theme_manager = ThemeManager()
        self.theme_manager.set_theme(self.config.theme)

        ctk.set_appearance_mode(self.theme_manager.current.mode)

        self.root = ctk.CTk()
        self.root.title("Pillarium")

        self.catalog = ApplicationCatalog()
        self.launcher = Launcher(self.catalog)
        self.network = NetworkManagerClient()
        self.bluetooth = BluetoothClient()
        self.audio = AudioClient()
        self.battery = BatteryMonitor()
        self.process_manager = ProcessManager()
        self.sounds = SoundPlayer()
        self.wallpapers = WallpaperManager(self.config)
        self.status = Status()

        self.wm = WindowManager(
            display=None,
            config=self.config,
            on_desktop_changed=self._on_desktop_changed,
            on_hotkey=self._on_hotkey,
            on_monitor_changed=self._on_monitor_changed,
            on_client_changed=self._on_client_changed,
        )
        self.wm.host = None  # set once the shell exists

        self.shell = Shell(self)
        self.wm.host = self.shell.decorations
        self.wm.hotkeys.configure(self.config.hotkeys)
        self.wm.publish_supported()
        self.wm.configure_desktops(self.config.desktops, self.config.desktop_names)

        self.notification_service = NotificationService(
            on_notify=self._on_notification, on_close=self._on_notification_closed
        )
        self._running = True
        self._last_status_poll = 0.0
        self._last_clock_poll = 0.0
        self._last_config_poll = 0.0
        self._pump_count = 0

        self._apply_appearance()
        self.shell.build_taskbars()
        self._load_wallpaper()
        self.shell.desktop.set_icons(self.config.desktop_icons)
        self.refresh_status(force=True)
        self.shell.refresh_clock()
        self.shell.refresh_quick_launch()
        self.catalog.scan()
        self.wm.manage_existing()

        self.notification_service.start()
        self._start_alert_socket()

        # The event loop starts as soon as the session is up so that
        # windows are picked up even before the main loop is entered.
        self.root.after(X_POLL_INTERVAL, self._pump_x)
        self.root.after(int(CLOCK_INTERVAL * 1000), self._tick)
        self._print_banner()

    # -----------------------------------------------------------------
    # Startup banner
    # -----------------------------------------------------------------
    def _print_banner(self) -> None:
        """Print a short summary of the session and its shortcuts."""
        monitors = self.wm.monitors.monitors
        lines = [
            "Pillarium 2.0 is running.",
            f"-> {len(monitors)} monitor(s): "
            + ", ".join(f"{monitor.name} {monitor.width}x{monitor.height}" for monitor in monitors),
            f"-> {self.wm.desktop_count} virtual desktop(s), "
            f"currently on {self.config.desktop_label(self.wm.current_desktop)}.",
            f"-> Theme: {self.theme_manager.current.name}.",
            "-> Alt+Space opens the launcher, Alt+Tab cycles the windows,",
            "   Alt+Shift+D cycles the themes, Alt+Shift+P opens the power menu.",
            "-> Ctrl+Alt+Left/Right switches the virtual desktop,",
            "   Alt+F4 closes the focused window.",
        ]
        for line in lines:
            print(line, file=sys.stderr)

    # -----------------------------------------------------------------
    # Appearance
    # -----------------------------------------------------------------
    def _apply_appearance(self) -> None:
        theme = self.theme_manager.current
        ctk.set_appearance_mode(theme.mode)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.shell.desktop.apply_geometry(screen_w, screen_h)
        self.shell.apply_theme(theme)

    def apply_theme(self, theme: Theme, persist: bool = True) -> None:
        """Activate a theme and refresh every surface."""
        self.theme_manager.activate(theme)
        if persist:
            self.config.theme = theme.slug
        self._apply_appearance()
        self.shell.refresh_windows()
        self.shell.refresh_status()
        self.shell.refresh_clock()

    def cycle_theme(self) -> None:
        """Move to the next built-in theme."""
        theme = self.theme_manager.cycle()
        self.apply_theme(theme)

    def import_desktop_theme(self) -> None:
        """Import the colours advertised by the desktop environment."""
        self.shell.import_desktop_theme()

    # -----------------------------------------------------------------
    # Wallpaper
    # -----------------------------------------------------------------
    def _load_wallpaper(self) -> None:
        path = self.wallpapers.current_path()
        wallpaper = self.wallpapers.load(path)
        if wallpaper.valid:
            monitor = self.wm.monitors.primary
            image = self.wallpapers.fit(wallpaper.image, monitor.width, monitor.height)
            self.shell.desktop.set_wallpaper(image)
        else:
            self.shell.desktop.set_wallpaper(None)

    def change_wallpaper(self) -> None:
        """Ask the user for a new wallpaper."""
        chosen = self.wallpapers.pick_file()
        if not chosen:
            return
        imported = self.wallpapers.import_file(chosen)
        if imported is None:
            return
        self.wallpapers.set_path(imported)
        self._load_wallpaper()

    def reset_wallpaper(self) -> None:
        """Restore the shipped wallpaper."""
        self.wallpapers.set_path("")
        self._load_wallpaper()

    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------
    def refresh_status(self, force: bool = False) -> None:
        """Refresh the system status shown in the taskbar."""
        network = self.network.poll()
        self.status.wifi_available = network.wifi_available
        self.status.wifi_enabled = network.wifi_enabled
        self.status.wifi_connected = network.wifi_connected
        self.status.wifi_networks = network.networks
        self.status.ethernet_available = network.ethernet_available
        self.status.ethernet_connected = network.ethernet_connected
        self.status.ethernet_device = network.ethernet_device
        self.status.ethernet_connection = network.ethernet_connection

        bluetooth = self.bluetooth.poll()
        self.status.bluetooth_available = bluetooth.available
        self.status.bluetooth_powered = bluetooth.powered
        self.status.bluetooth_scanning = bluetooth.scanning
        self.status.bluetooth_devices = bluetooth.devices

        audio = self.audio.poll()
        self.status.audio_available = audio.available
        self.status.audio_volume = audio.volume
        self.status.audio_muted = audio.muted
        self.status.audio_sink = audio.sink

        self.status.battery = self.battery.poll()
        self.shell.refresh_status()

    def play_alert_sound(self, level: str) -> None:
        """Play the chime belonging to an alert level."""
        self.sounds.play(level)

    # -----------------------------------------------------------------
    # Notifications
    # -----------------------------------------------------------------
    def _on_notification(self, notification: Any) -> None:
        self.root.after(0, lambda: self.shell.notify(notification))

    def _on_notification_closed(self, notification_id: int) -> None:
        self.root.after(
            0, lambda: self.shell.notification_center.dismiss_by_id(notification_id)
        )

    # -----------------------------------------------------------------
    # Alert socket
    # -----------------------------------------------------------------
    def _start_alert_socket(self) -> None:
        """Listen for ``pillarium-notify`` requests."""
        try:
            from .alerts_server import AlertSocketServer

            self._alert_server = AlertSocketServer(self._handle_alert_payload)
            self._alert_server.start()
        except Exception as exc:
            print(f"Pillarium: alert socket unavailable: {exc}", file=sys.stderr)
            self._alert_server = None

    def _handle_alert_payload(self, payload: dict) -> None:
        """Handle a request coming from the ``pillarium-notify`` command."""
        level = str(payload.get("level", "warning"))
        spec = {
            "level": level,
            "title": str(payload.get("title", "Pillarium")),
            "message": str(payload.get("message", "")),
            "app": str(payload.get("app", "")),
            "detail": str(payload.get("detail", "")),
            "timeout": payload.get("timeout"),
            "sound": bool(payload.get("sound", True)),
        }

        def show() -> None:
            self.shell.show_alert(
                spec["level"],
                spec["title"],
                spec["message"],
                app=spec["app"],
                detail=spec["detail"],
                timeout=spec["timeout"],
                sound=spec["sound"],
            )

        self.root.after(0, show)

    # -----------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------
    def _on_desktop_changed(self, index: int) -> None:
        self.shell.refresh_desktops()
        self.shell.refresh_windows()

    def _on_client_changed(self) -> None:
        self.shell.refresh_windows()

    def _on_monitor_changed(self, monitors: list[Any]) -> None:
        self.shell.build_taskbars()
        self.wm.publish_workarea()
        self._load_wallpaper()

    def _on_hotkey(self, action: str) -> None:
        """Handle a keyboard shortcut."""
        if action == "launcher":
            self.shell.open_launcher()
        elif action == "cycle_windows":
            self.wm.focus_next()
        elif action == "close_window":
            if self.wm.focused is not None:
                self.wm.close(self.wm.focused)
        elif action == "terminal":
            self.launcher.launch_terminal()
        elif action == "theme_cycle":
            self.cycle_theme()
        elif action == "power_menu":
            self.shell.open_power_menu(*self.shell._status_anchor("power"))
        elif action == "wifi_menu":
            self.shell.open_status_menu("wifi", *self.shell._status_anchor("wifi"))
        elif action == "ethernet_menu":
            self.shell.open_status_menu("ethernet", *self.shell._status_anchor("ethernet"))
        elif action == "bluetooth_menu":
            self.shell.open_status_menu("bluetooth", *self.shell._status_anchor("bluetooth"))
        elif action == "audio_menu":
            self.shell.open_status_menu("audio", *self.shell._status_anchor("audio"))
        elif action == "processes":
            self.shell.open_processes()
        elif action == "refresh_desktop":
            self._refresh_desktop_icons()
        elif action == "edit_quick_launch":
            self._open_config_editor()
        elif action == "next_desktop":
            self.wm.next_desktop()
        elif action == "previous_desktop":
            self.wm.previous_desktop()
        elif action == "show_desktop":
            self.wm.next_desktop()
        elif action.startswith("desktop_"):
            try:
                index = int(action.split("_", 1)[1]) - 1
            except (IndexError, ValueError):
                return
            self.wm.switch_desktop(index)

    def _refresh_desktop_icons(self) -> None:
        icons = self.catalog.scan_desktop_folder()
        if icons:
            self.config.desktop_icons = icons
            self.shell.desktop.refresh_icons(icons)

    def _open_config_editor(self) -> None:
        import subprocess

        try:
            subprocess.Popen(
                ["xdg-open", paths.config_path()],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
        try:
            subprocess.Popen(["xterm", "-e", "nano", paths.config_path()])
        except Exception as exc:
            print(f"Pillarium: could not open the config editor: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Settings helpers
    # -----------------------------------------------------------------
    def apply_desktop_settings(self) -> None:
        """Apply the virtual desktop configuration."""
        self.wm.configure_desktops(self.config.desktops, self.config.desktop_names)
        self.shell.refresh_desktops()
        self.shell.refresh_windows()

    def apply_display_settings(self) -> None:
        """Apply taskbar and monitor options."""
        self.shell.build_taskbars()
        self.wm.publish_workarea()

    def prompt_add_launch(self) -> None:
        """Ask the user which application to pin to the taskbar."""
        self.catalog.scan()
        entries = self.catalog.applications
        if not entries:
            self.shell.show_alert("warning", "No applications", "No applications were found.")
            return

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Pin application")
        dialog.geometry("420x320+0+0")
        labels = [app.label for app in entries]
        box = ctk.CTkOptionMenu(dialog, values=labels, width=380)
        box.pack(padx=16, pady=16)
        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(
            actions,
            text="Cancel",
            command=dialog.destroy,
            width=100,
        ).pack(side="right")
        ctk.CTkButton(
            actions,
            text="Pin",
            width=100,
            command=lambda: self._pin_application(dialog, box.get(), entries),
        ).pack(side="right", padx=(0, 8))

    def _pin_application(self, dialog: Any, label: str, entries: list[Any]) -> None:
        for app in entries:
            if app.label == label:
                items = list(self.config.quick_launch)
                items.append(
                    {
                        "cmd": list(app.cmd),
                        "label": app.label,
                        "icon": app.icon,
                        "desktop_file": app.desktop_file,
                    }
                )
                self.config.quick_launch = items
                self.shell.refresh_quick_launch()
                break
        try:
            dialog.destroy()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------
    def run(self) -> None:
        """Run the Pillarium session until the user logs out."""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def _pump_x(self) -> None:
        """Drain the X11 event queue."""
        if not self._running:
            return
        self._pump_count += 1
        try:
            display = self.wm.display
            if display.pending_events() == 0:
                select.select([display.fileno()], [], [], 0.0)
            while display.pending_events() > 0:
                event = display.next_event()
                if event.type == 0:
                    continue
                self.wm.handle_event(event)
        except Exception as exc:
            print(f"Pillarium: event loop error: {exc}", file=sys.stderr)
        if self.wm.follows_mouse():
            self.wm.focus_under_pointer()
        elif self._pump_count % 8 == 0:
            # Make sure the keyboard never ends up on the pointer.
            self.wm.ensure_focus()
        if self._running:
            self.root.after(X_POLL_INTERVAL, self._pump_x)

    def _tick(self) -> None:
        """Periodic maintenance."""
        if not self._running:
            return
        now = time.time()
        try:
            if now - self._last_status_poll > STATUS_INTERVAL:
                self._last_status_poll = now
                self.refresh_status()
            if now - self._last_clock_poll > CLOCK_INTERVAL:
                self._last_clock_poll = now
                self.shell.refresh_clock()
            if now - self._last_config_poll > 2.0:
                self._last_config_poll = now
                self._reload_config_if_changed()
            self.shell.notification_center.tick()
            self.shell.alert_manager.tick()
            self._check_ping()
            self.wm.sweep_closing()
        except Exception as exc:
            print(f"Pillarium: periodic task failed: {exc}", file=sys.stderr)
        if self._running:
            self.root.after(int(CLOCK_INTERVAL * 1000), self._tick)

    def _check_ping(self) -> None:
        """Look for hung applications."""
        for client_id in self.wm.sweep_pings():
            client = self.wm.clients.get(client_id)
            if client is None:
                continue
            title = client.title or "Application"
            self.shell.show_alert(
                "error",
                f"{title} is not responding",
                f'The window "{title}" has stopped responding.',
                app=client.wm_class_name,
                actions=[
                    ("Wait", lambda cid=client_id: self._clear_unresponsive(cid)),
                    ("Force Quit", lambda cid=client_id: self.wm.close(cid)),
                ],
            )

    def _clear_unresponsive(self, client_id: int) -> None:
        client = self.wm.clients.get(client_id)
        if client is not None:
            client.unresponsive = False
            self.wm._ping_outstanding.pop(client_id, None)

    def _reload_config_if_changed(self) -> None:
        """Pick up changes written to config.json by another program."""
        if not self.config.poll_external_changes():
            return
        self.wm.configure_desktops(self.config.desktops, self.config.desktop_names)
        self.wm.hotkeys.configure(self.config.hotkeys)
        self.wm.refresh_event_mask()
        theme = self.theme_manager.get(self.config.theme)
        if theme is not None:
            self.apply_theme(theme, persist=False)
        self.shell.refresh_quick_launch()
        self.shell.refresh_windows()

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------
    def quit(self) -> None:
        """Stop Pillarium."""
        self._running = False
        try:
            self.root.quit()
        except Exception:
            pass

    def shutdown(self) -> None:
        """Release every resource Pillarium owns."""
        self._running = False
        try:
            self.shell.shutdown()
        except Exception:
            pass
        try:
            self.notification_service.stop()
        except Exception:
            pass
        if getattr(self, "_alert_server", None) is not None:
            try:
                self._alert_server.stop()
            except Exception:
                pass
        try:
            self.wm.shutdown()
        except Exception:
            pass
        print("Pillarium: shutdown complete.", file=sys.stderr)
