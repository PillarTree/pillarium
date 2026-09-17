#!/usr/bin/env python3
"""Test script to send a test notification via D-Bus."""

import sys
import dbus

def send_test_notification():
    """Send a test notification to the Pillarium notification daemon."""
    try:
        session_bus = dbus.SessionBus()
        notifications = session_bus.get_object(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications"
        )
        interface = dbus.Interface(notifications, "org.freedesktop.Notifications")

        # Send notification
        nid = interface.Notify(
            "Test App",           # app_name
            0,                    # replaces_id
            "dialog-information", # app_icon
            "Test Notification",  # summary
            "This is a test notification from Pillarium!",  # body
            [],                   # actions
            {},                   # hints
            5000                  # expire_timeout (ms)
        )
        print(f"Notification sent with ID: {nid}")

        # Get server info
        info = interface.GetServerInformation()
        print(f"Server info: {info}")

        # Get capabilities
        caps = interface.GetCapabilities()
        print(f"Capabilities: {caps}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    send_test_notification()