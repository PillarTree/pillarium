"""Bluetooth / BlueZ support."""

import shutil
import subprocess
import sys


class BluetoothMixin:
    def _init_bluetooth(self):
        self.bluetooth_status = {
            "available": False,
            "powered": False,
            "scanning": False,
            "devices": [],
        }
        self._last_bluetooth_poll = 0.0

    def _bluetoothctl(self, args, timeout=4):
        try:
            result = subprocess.run(
                ["bluetoothctl"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result
        except Exception as exc:
            print(f"Pillarium: bluetoothctl failed: {exc}", file=sys.stderr)
            return None

    def _poll_bluetooth_status(self):
        if not shutil.which("bluetoothctl"):
            self.bluetooth_status = {
                "available": False,
                "powered": False,
                "scanning": False,
                "devices": [],
            }
            return

        show = self._bluetoothctl(["show"])
        if show is None:
            return

        powered = False
        discovering = False
        for line in show.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("powered:"):
                powered = line.split(":", 1)[1].strip().lower() == "yes"
            elif line.lower().startswith("discovering:"):
                discovering = line.split(":", 1)[1].strip().lower() == "yes"

        devices = []
        paired = self._bluetoothctl(["devices"], timeout=5)
        if paired is not None:
            for line in paired.stdout.splitlines():
                parts = line.strip().split(maxsplit=2)
                if len(parts) >= 3 and parts[0] == "Device":
                    mac, name = parts[1], parts[2]
                    info = self._bluetoothctl(["info", mac], timeout=3)
                    connected = False
                    if info is not None:
                        for info_line in info.stdout.splitlines():
                            s = info_line.strip().lower()
                            if s.startswith("connected:"):
                                connected = s.split(":", 1)[1].strip() == "yes"
                                break
                    devices.append({
                        "mac": mac,
                        "name": name,
                        "connected": connected,
                    })

        self.bluetooth_status = {
            "available": True,
            "powered": powered,
            "scanning": discovering,
            "devices": devices,
        }

    def _bluetooth_action(self, action, payload=None):
        if not shutil.which("bluetoothctl"):
            return
        if action == "power_on":
            self._bluetoothctl(["power", "on"])
        elif action == "power_off":
            self._bluetoothctl(["power", "off"])
        elif action == "scan":
            if self.bluetooth_status.get("scanning"):
                self._bluetoothctl(["scan", "off"])
            else:
                self._bluetoothctl(["power", "on"])
                self._bluetoothctl(["scan", "on"])
        elif action == "connect" and payload:
            self._bluetoothctl(["connect", payload])
        elif action == "disconnect" and payload:
            self._bluetoothctl(["disconnect", payload])
        self._poll_bluetooth_status()
        self._redraw_taskbar()

    def _toggle_bluetooth_menu(self, anchor_x):
        if (
            getattr(self, "active_menu", None)
            and self.active_menu.get("kind") == "bluetooth"
        ):
            self._close_active_menu()
            return

        self._poll_bluetooth_status()
        self._close_active_menu()

        if not self.bluetooth_status.get("available"):
            items = [
                {
                    "label": "Bluetooth unavailable",
                    "action": ("bluetooth", ("noop", None)),
                },
                {
                    "label": "Cancel",
                    "action": ("bluetooth", ("cancel", None)),
                },
            ]
        else:
            items = [
                {
                    "label": (
                        "Turn Bluetooth Off"
                        if self.bluetooth_status.get("powered")
                        else "Turn Bluetooth On"
                    ),
                    "action": (
                        "bluetooth",
                        (
                            "power_off"
                            if self.bluetooth_status.get("powered")
                            else "power_on",
                            None,
                        ),
                    ),
                },
                {
                    "label": (
                        "Stop Scanning"
                        if self.bluetooth_status.get("scanning")
                        else "Scan for Devices"
                    ),
                    "action": ("bluetooth", ("scan", None)),
                },
            ]

            for dev in self.bluetooth_status.get("devices", [])[:8]:
                items.append({
                    "label": (
                        ("Disconnect: " if dev["connected"] else "Connect: ")
                        + dev["name"][:25]
                    ),
                    "action": (
                        "bluetooth",
                        (
                            "disconnect" if dev["connected"] else "connect",
                            dev["mac"],
                        ),
                    ),
                })

            items.append({
                "label": "Cancel",
                "action": ("bluetooth", ("cancel", None)),
            })

        self._open_menu(
            "bluetooth",
            items,
            anchor_x,
            self.BLUETOOTH_W,
        )

    def _bluetooth_menu_action(self, payload):
        if not payload:
            return
        action, value = payload
        if action == "cancel" or action == "noop":
            return
        self._bluetooth_action(action, value)
