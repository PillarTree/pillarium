"""Notification daemon and display for Pillarium.

Implements the freedesktop.org Desktop Notifications Specification
(org.freedesktop.Notifications) via D-Bus and displays notifications
as popup toasts in the window manager.
"""

import os
import sys
import time
import threading
from collections import deque
from Xlib import X

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except Exception:
    DBUS_AVAILABLE = False


class Notification:
    """Represents a single notification."""
    def __init__(self, app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout):
        self.id = replaces_id if replaces_id > 0 else int(time.time() * 1000) % 1000000
        self.app_name = app_name or "Unknown"
        self.app_icon = app_icon or ""
        self.summary = summary or ""
        self.body = body or ""
        self.actions = actions or []
        self.hints = hints or {}
        self.expire_timeout = expire_timeout if expire_timeout > 0 else 5000
        self.timestamp = time.time()
        self.window = None
        self.closed = False

    def __repr__(self):
        return f"Notification(id={self.id}, app={self.app_name}, summary={self.summary[:30]})"


class NotificationMixin:
    """Mixin that provides notification daemon and display functionality."""

    def _init_notifications(self):
        """Initialize notification system."""
        self.notifications = deque(maxlen=100)
        self.active_notifications = []
        self._notification_id_counter = 0
        self._dbus_thread = None
        self._dbus_loop = None
        self._notification_service = None

        if DBUS_AVAILABLE:
            self._start_dbus_daemon()
        else:
            print("Pillarium: dbus-python not available, notifications disabled", file=sys.stderr)

    def _start_dbus_daemon(self):
        """Start the D-Bus notification daemon in a separate thread."""
        def run_dbus():
            try:
                dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
                self._dbus_loop = GLib.MainLoop()
                session_bus = dbus.SessionBus()
                name = dbus.service.BusName("org.freedesktop.Notifications", session_bus, do_not_queue=True)
                self._notification_service = NotificationService(self, session_bus, "/org/freedesktop/Notifications")
                print("Pillarium: Notification daemon registered on D-Bus", file=sys.stderr)
                self._dbus_loop.run()
            except Exception as exc:
                print(f"Pillarium: D-Bus notification daemon failed: {exc}", file=sys.stderr)

        self._dbus_thread = threading.Thread(target=run_dbus, daemon=True)
        self._dbus_thread.start()

    def notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout):
        """D-Bus method: Notify - creates and shows a notification."""
        notification = Notification(app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout)

        # Critical-urgency notifications are promoted to a modal error
        # window (with its own chime) so they cannot be missed.  Normal
        # and low notifications keep the unobtrusive toast behaviour.
        urgency = self._notification_urgency(hints)
        if urgency >= 2 and getattr(self, "alerts_enabled", True):
            try:
                self.show_alert(
                    "error",
                    summary or app_name or "Application error",
                    body or summary or "",
                    app=app_name,
                )
                self.notifications.append(notification)
                return notification.id
            except Exception:
                pass

        self._show_notification(notification)
        return notification.id

    @staticmethod
    def _notification_urgency(hints):
        """Extract the desktop-notification urgency (0=low, 2=critical)."""
        try:
            if hints:
                raw = hints.get("urgency")
                if raw is not None:
                    return int(raw)
        except Exception:
            pass
        return 1

    def close_notification(self, notification_id):
        """D-Bus method: CloseNotification - closes a specific notification."""
        for n in self.active_notifications:
            if n.id == notification_id:
                self._close_notification_window(n)
                break

    def get_capabilities(self):
        """D-Bus method: GetCapabilities - returns supported capabilities."""
        return ["body", "actions", "icon-static", "icon-multi", "persistence"]

    def get_server_information(self):
        """D-Bus method: GetServerInformation - returns server info."""
        return ("Pillarium", "Pillarium", "1.0.3", "1.2")

    def _show_notification(self, notification):
        """Display a notification as a popup window."""
        self.notifications.append(notification)
        self.active_notifications.append(notification)

        if not getattr(self, "display", None):
            return

        try:
            x = self.screen_w - self.NOTIFICATION_W - self.NOTIFICATION_GAP
            y = self.screen_h - self.TASKBAR_H - self.NOTIFICATION_GAP
            for i, active in enumerate(self.active_notifications[:-1]):
                y -= self.NOTIFICATION_H + self.NOTIFICATION_GAP

            win = self._create_window(
                self.root,
                x, y,
                self.NOTIFICATION_W, self.NOTIFICATION_H,
                self.colors["surface"],
                self.colors["border"],
                override_redirect=True,
            )
            win.change_attributes(
                background_pixel=self.colors["surface"],
                border_pixel=self.colors["border"],
                event_mask=X.ExposureMask | X.ButtonPressMask | X.ButtonReleaseMask,
            )
            win.map()
            self._own_windows.add(win.id)
            notification.window = win

            self._draw_notification(notification)
            self.display.flush()

            if notification.expire_timeout > 0:
                GLib.timeout_add(notification.expire_timeout, self._auto_close_notification, notification)

        except Exception as exc:
            print(f"Pillarium: failed to show notification: {exc}", file=sys.stderr)

    def _auto_close_notification(self, notification):
        """Auto-close notification after timeout."""
        if notification in self.active_notifications:
            self._close_notification_window(notification)
        return False

    def _close_all_notifications(self):
        """Close every active notification window (used on shutdown)."""
        for notification in list(getattr(self, "active_notifications", [])):
            try:
                self._close_notification_window(notification)
            except Exception:
                pass

    def _close_notification_window(self, notification):
        """Close and clean up a notification window."""
        if notification.closed:
            return
        notification.closed = True
        if notification.window:
            try:
                notification.window.destroy()
            except Exception:
                pass
            try:
                self._own_windows.discard(notification.window.id)
            except Exception:
                pass
        if notification in self.active_notifications:
            self.active_notifications.remove(notification)
        self._reposition_notifications()
        try:
            self.display.flush()
        except Exception:
            pass

    def _reposition_notifications(self):
        """Reposition remaining notifications after one is closed."""
        if not getattr(self, "display", None):
            return
        y = self.screen_h - self.TASKBAR_H - self.NOTIFICATION_GAP
        for n in self.active_notifications:
            if n.window:
                try:
                    n.window.configure(y=y)
                    y -= self.NOTIFICATION_H + self.NOTIFICATION_GAP
                except Exception:
                    pass

    def _draw_notification(self, notification):
        """Draw notification content using PIL."""
        if not notification.window:
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return

        try:
            panel_hex = self.current_palette.get("panel", "#2c313a")
            text_hex = self.current_palette.get("text", "#d8dee9")
            text_dim_hex = self.current_palette.get("text_dim", "#8b93a3")
            accent_hex = self.current_palette.get("accent", "#5e81ac")
            border_hex = self.current_palette.get("border", "#3b4252")

            panel_rgb = self._hex_to_rgb(panel_hex)
            text_rgb = self._hex_to_rgb(text_hex)
            text_dim_rgb = self._hex_to_rgb(text_dim_hex)
            accent_rgb = self._hex_to_rgb(accent_hex)
            border_rgb = self._hex_to_rgb(border_hex)

            img = Image.new("RGB", (self.NOTIFICATION_W, self.NOTIFICATION_H), panel_rgb)
            draw = ImageDraw.Draw(img)

            draw.rounded_rectangle(
                (0, 0, self.NOTIFICATION_W - 1, self.NOTIFICATION_H - 1),
                radius=8,
                fill=panel_rgb,
                outline=border_rgb,
                width=2,
            )

            draw.rectangle(
                (2, 2, 6, self.NOTIFICATION_H - 2),
                fill=accent_rgb,
            )

            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
            except Exception:
                font = ImageFont.load_default()
                font_small = ImageFont.load_default()

            draw.text((16, 10), notification.app_name, font=font, fill=text_dim_rgb)
            draw.text((16, 30), notification.summary, font=font, fill=text_rgb)

            if notification.body:
                lines = self._wrap_text(notification.body, font_small, self.NOTIFICATION_W - 32)
                y = 52
                for line in lines[:3]:
                    draw.text((16, y), line, font=font_small, fill=text_dim_rgb)
                    y += 18

            if notification.app_icon:
                try:
                    icon_img = self._load_icon(notification.app_icon, 48)
                    if icon_img:
                        icon_img = icon_img.resize((48, 48), Image.Resampling.LANCZOS)
                        img.paste(icon_img, (self.NOTIFICATION_W - 60, 16), icon_img.convert("RGBA") if icon_img.mode == "RGBA" else None)
                except Exception:
                    pass

            gc = self._gc(notification.window, self.colors["text"], self.colors["surface"])
            notification.window.put_pil_image(gc, 0, 0, img.convert("RGB"))
            self.display.flush()

        except Exception as exc:
            print(f"Pillarium: notification draw failed: {exc}", file=sys.stderr)

    def _wrap_text(self, text, font, max_width):
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current = []
        for word in words:
            test = " ".join(current + [word])
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] <= max_width:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))
        return lines

    def _handle_notification_click(self, window, button):
        """Handle click on notification window."""
        for n in self.active_notifications:
            if n.window and n.window.id == window.id:
                if n.actions:
                    self._execute_notification_action(n, 0)
                self._close_notification_window(n)
                break

    def _execute_notification_action(self, notification, action_index):
        """Execute a notification action."""
        if action_index < len(notification.actions):
            action = notification.actions[action_index]
            print(f"Pillarium: notification action: {action}", file=sys.stderr)


if DBUS_AVAILABLE:
    class NotificationService(dbus.service.Object):
        """D-Bus service implementing org.freedesktop.Notifications."""

        def __init__(self, wm, bus, path):
            self.wm = wm
            super().__init__(bus, path)

        @dbus.service.method("org.freedesktop.Notifications", in_signature="susssasa{sv}i", out_signature="u")
        def Notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout):
            return self.wm.notify(app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout)

        @dbus.service.method("org.freedesktop.Notifications", in_signature="u", out_signature="")
        def CloseNotification(self, notification_id):
            self.wm.close_notification(notification_id)

        @dbus.service.method("org.freedesktop.Notifications", in_signature="", out_signature="as")
        def GetCapabilities(self):
            return self.wm.get_capabilities()

        @dbus.service.method("org.freedesktop.Notifications", in_signature="", out_signature="ssss")
        def GetServerInformation(self):
            return self.wm.get_server_information()

        @dbus.service.signal("org.freedesktop.Notifications", signature="uu")
        def NotificationClosed(self, notification_id, reason):
            pass

        @dbus.service.signal("org.freedesktop.Notifications", signature="us")
        def ActionInvoked(self, notification_id, action_key):
            pass