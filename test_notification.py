#!/usr/bin/env python3
"""Send a test notification to a running Pillarium session.

The notification is delivered over the freedesktop.org notification bus,
so Pillarium has to be running in the same session.
"""

import sys

try:
    import dbus
except ImportError:
    print("This test needs dbus-python (python3-dbus).", file=sys.stderr)
    raise SystemExit(1)


def send_test_notification() -> int:
    """Send a notification and print what the server reports."""
    try:
        session_bus = dbus.SessionBus()
        notifications = session_bus.get_object(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
        )
        interface = dbus.Interface(notifications, "org.freedesktop.Notifications")

        nid = interface.Notify(
            "Test App",           # app_name
            0,                    # replaces_id
            "dialog-information",  # app_icon
            "Test Notification",   # summary
            "This is a test notification from Pillarium 2.0!",  # body
            [],                   # actions
            {},                   # hints
            5000,                 # expire_timeout (ms)
        )
        print(f"Notification sent with ID: {nid}")
        print(f"Server info: {interface.GetServerInformation()}")
        print(f"Capabilities: {interface.GetCapabilities()}")
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(send_test_notification())
