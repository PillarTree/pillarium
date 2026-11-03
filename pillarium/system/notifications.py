"""freedesktop.org desktop notification service.

Pillarium claims ``org.freedesktop.Notifications`` on the session bus so
applications can raise toasts.  The service runs on its own thread with
its own GLib main loop, which keeps the D-Bus traffic away from the UI
thread; notifications are handed to the shell through a callback.

When ``dbus-python`` is unavailable the service degrades to a no-op and
Pillarium simply shows no toasts.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:  # pragma: no cover - depends on the host system
    import dbus
    import dbus.mainloop.glib
    import dbus.service
    from dbus.mainloop.glib import GLib

    DBUS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the host system
    dbus = None  # type: ignore[assignment]
    DBUS_AVAILABLE = False

BUS_NAME = "org.freedesktop.Notifications"
OBJECT_PATH = "/org/freedesktop/Notifications"
INTERFACE = "org.freedesktop.Notifications"

#: Capabilities reported to senders.
CAPABILITIES = ["body", "actions", "icon-static", "icon-multi", "persistence"]


@dataclass
class Notification:
    """A notification raised by an application."""

    id: int
    app_name: str = "Unknown"
    app_icon: str = ""
    summary: str = ""
    body: str = ""
    actions: list[str] = field(default_factory=list)
    hints: dict[str, Any] = field(default_factory=dict)
    expire_timeout: int = 5000
    timestamp: float = field(default_factory=time.time)

    @property
    def urgency(self) -> int:
        """Urgency hint: 0 low, 1 normal, 2 critical."""
        try:
            return int(self.hints.get("urgency", 1))
        except (TypeError, ValueError):
            return 1

    @property
    def critical(self) -> bool:
        return self.urgency >= 2

    @property
    def action_labels(self) -> list[str]:
        """Action identifiers, one per pair of (key, label) entries."""
        return [self.actions[index] for index in range(1, len(self.actions), 2)]


class NotificationService:
    """Owns the D-Bus notification daemon."""

    def __init__(
        self,
        on_notify: Callable[[Notification], None] | None = None,
        on_close: Callable[[int], None] | None = None,
    ):
        self._on_notify = on_notify
        self._on_close = on_close
        self._counter = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loop: Any = None
        self._service: Any = None
        self._running = False

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------
    @property
    def available(self) -> bool:
        return DBUS_AVAILABLE

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Claim the bus name and start serving.  Returns ``True`` on success."""
        if not DBUS_AVAILABLE or self._running:
            return False
        self._thread = threading.Thread(target=self._serve, name="pillarium-notify", daemon=True)
        self._thread.start()
        # Give the thread a moment to claim the name so the caller can
        # report a meaningful result.
        for _ in range(50):
            if self._running or not self._thread.is_alive():
                break
            time.sleep(0.02)
        return self._running

    def stop(self) -> None:
        """Stop serving and release the bus name."""
        self._running = False
        loop = self._loop
        if loop is not None:
            try:
                GLib.idle_add(loop.quit)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -----------------------------------------------------------------
    # Notification creation
    # -----------------------------------------------------------------
    def _next_id(self, replaces_id: int = 0) -> int:
        with self._lock:
            if replaces_id > 0:
                self._counter = max(self._counter, replaces_id)
            self._counter += 1
            return self._counter

    def notify(
        self,
        app_name: str = "",
        replaces_id: int = 0,
        app_icon: str = "",
        summary: str = "",
        body: str = "",
        actions: list[str] | None = None,
        hints: dict[str, Any] | None = None,
        expire_timeout: int = -1,
    ) -> int:
        """Create a notification and hand it to the shell."""
        notification = Notification(
            id=self._next_id(replaces_id),
            app_name=app_name or "Unknown",
            app_icon=app_icon or "",
            summary=summary or "",
            body=body or "",
            actions=list(actions or []),
            hints=dict(hints or {}),
            expire_timeout=expire_timeout if expire_timeout and expire_timeout > 0 else 5000,
        )
        if self._on_notify is not None:
            try:
                self._on_notify(notification)
            except Exception:
                pass
        return notification.id

    def close(self, notification_id: int) -> None:
        """Tell the shell that a notification was dismissed."""
        if self._on_close is not None:
            try:
                self._on_close(notification_id)
            except Exception:
                pass

    # ----------------------------------------------------------------
    # D-Bus plumbing
    # ----------------------------------------------------------------
    def _serve(self) -> None:  # pragma: no cover - requires a session bus
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            bus_name = dbus.service.BusName(BUS_NAME, bus)
            self._service = _DBusNotificationObject(bus_name, OBJECT_PATH, self)
            self._loop = GLib.MainLoop()
            self._running = True
            self._loop.run()
        except Exception:
            self._running = False
        finally:
            self._loop = None
            self._service = None


if DBUS_AVAILABLE:  # pragma: no cover - requires a session bus

    class _DBusNotificationObject(dbus.service.Object):  # type: ignore[misc]
        """The D-Bus object implementing ``org.freedesktop.Notifications``."""

        def __init__(self, bus_name: Any, object_path: str, owner: NotificationService):
            super().__init__(bus_name, object_path)
            self._owner = owner

        @dbus.service.method(INTERFACE, in_signature="susssasa{sv}i", out_signature="u")
        def Notify(
            self,
            app_name: str,
            replaces_id: int,
            app_icon: str,
            summary: str,
            body: str,
            actions: list[str],
            hints: dict[str, Any],
            expire_timeout: int,
        ) -> int:
            return self._owner.notify(
                app_name=app_name,
                replaces_id=replaces_id,
                app_icon=app_icon,
                summary=summary,
                body=body,
                actions=list(actions),
                hints=dict(hints),
                expire_timeout=expire_timeout,
            )

        @dbus.service.method(INTERFACE, in_signature="u", out_signature="")
        def CloseNotification(self, notification_id: int) -> None:
            self._owner.close(notification_id)

        @dbus.service.method(INTERFACE, in_signature="", out_signature="as")
        def GetCapabilities(self) -> list[str]:
            return list(CAPABILITIES)

        @dbus.service.method(INTERFACE, in_signature="", out_signature="ssss")
        def GetServerInformation(self) -> tuple[str, str, str, str]:
            from .. import __version__

            return ("Pillarium", "Pillarium", __version__, "1.2")

        @dbus.service.signal(INTERFACE, signature="uu")
        def NotificationClosed(self, notification_id: int, reason: int) -> None:
            pass

        @dbus.service.signal(INTERFACE, signature="us")
        def ActionInvoked(self, notification_id: int, action_key: str) -> None:
            pass

else:  # pragma: no cover - dbus is optional

    class _DBusNotificationObject:  # type: ignore[no-redef]
        """Placeholder used when dbus-python is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("dbus-python is not available")
