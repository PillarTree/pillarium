"""Ethernet (wired) NetworkManager widget and menu."""

import sys


class EthernetMixin:
    def _init_ethernet(self):
        # Ethernet status cache
        self.ethernet_status = {
            "available": True,
            "connected": False,
            "device": None,
            "connection": None,
            "state": "unavailable",
        }
        self._last_ethernet_poll = 0.0

    # -----------------------------------------------------------------
    # Ethernet / NetworkManager polling
    # -----------------------------------------------------------------
    def _ethernet_devices(self):
        """Return a list of (device, state, connection) for wired NICs."""
        out = self._nmcli(
            ["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"], timeout=3
        )
        devices = []
        if not out:
            return devices
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 3:
                continue
            device, dev_type, state = parts[0], parts[1], parts[2]
            connection = parts[3] if len(parts) >= 4 and parts[3] else None
            if dev_type != "ethernet" or not device:
                continue
            devices.append((device, state, connection))
        return devices

    def _poll_ethernet_status(self):
        devices = self._ethernet_devices()
        status = {
            "available": bool(devices),
            "connected": False,
            "device": None,
            "connection": None,
            "state": "unavailable",
        }
        if devices:
            # Prefer a connected device if there is one.
            chosen = next(
                (d for d in devices if d[1] == "connected"),
                devices[0],
            )
            status["device"] = chosen[0]
            status["state"] = chosen[1]
            status["connection"] = chosen[2]
            status["connected"] = chosen[1] == "connected"
        self.ethernet_status = status

    def _ethernet_connect(self, device):
        if not device:
            return
        result = self._nmcli(["dev", "connect", device], timeout=15)
        if result is None:
            print(
                f"Pillarium: could not connect ethernet device '{device}'",
                file=sys.stderr,
            )
        self._poll_ethernet_status()
        self._redraw_taskbar()

    def _ethernet_disconnect(self, device):
        if not device:
            return
        self._nmcli(["dev", "disconnect", device], timeout=5)
        self._poll_ethernet_status()
        self._redraw_taskbar()

    # -----------------------------------------------------------------
    # Ethernet menu
    # -----------------------------------------------------------------
    def _toggle_ethernet_menu(self, anchor_x):
        if (
            getattr(self, "active_menu", None)
            and self.active_menu.get("kind") == "ethernet"
        ):
            self._close_active_menu()
            return
        self._poll_ethernet_status()
        self._close_active_menu()
        self._close_wifi_auth()
        self._close_confirm_dialog()

        status = self.ethernet_status
        items = []
        if not status.get("available"):
            items.append(
                {"label": "Ethernet unavailable", "action": ("ethernet", ("noop", None))}
            )
        elif status.get("connected"):
            conn = status.get("connection") or status.get("device") or "Ethernet"
            items.append(
                {"label": f"Connected: {conn[:24]}", "action": ("ethernet", ("noop", None))}
            )
            items.append(
                {
                    "label": "Disconnect",
                    "action": ("ethernet", ("disconnect", status.get("device"))),
                }
            )
        else:
            device = status.get("device")
            label = "Connect Ethernet" if device else "No wired device"
            items.append(
                {"label": label, "action": ("ethernet", ("connect", device))}
            )
        items.append({"label": "Cancel", "action": ("ethernet", ("cancel", None))})

        self._open_menu("ethernet", items, anchor_x, self.ETH_W)

    def _ethernet_menu_action(self, payload):
        if not payload:
            return
        action, value = payload
        if action in ("cancel", "noop"):
            return
        if action == "connect":
            self._ethernet_connect(value)
        elif action == "disconnect":
            self._ethernet_disconnect(value)
