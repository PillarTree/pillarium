"""Battery widget and popup menu (/sys/class/power_supply)."""

import os
import sys
from Xlib import X


class BatteryMixin:
    def _init_battery(self):
        self.battery_status = {
            "available": False,
            "percent": 0,
            "charging": False,
            "state": "unknown",
        }
        self._last_battery_poll = 0.0

    # -----------------------------------------------------------------
    # Battery status polling
    # -----------------------------------------------------------------
    def _poll_battery_status(self):
        status = {
            "available": False,
            "percent": 0,
            "charging": False,
            "state": "unknown",
        }
        try:
            batteries = []
            for name in sorted(os.listdir("/sys/class/power_supply")):
                base = f"/sys/class/power_supply/{name}"
                try:
                    with open(f"{base}/type") as f:
                        if f.read().strip().lower() != "battery":
                            continue
                except Exception:
                    continue
                percent = None
                try:
                    with open(f"{base}/capacity") as f:
                        percent = int(f.read().strip())
                except Exception:
                    pass
                state = "unknown"
                try:
                    with open(f"{base}/status") as f:
                        state = f.read().strip().lower()
                except Exception:
                    pass
                batteries.append({"percent": percent, "state": state})
            if not batteries:
                self.battery_status = status
                return
            pcts = [
                b["percent"] for b in batteries if b["percent"] is not None
            ]
            states = [b["state"] for b in batteries]
            if "charging" in states:
                state = "charging"
            elif "full" in states:
                state = "full"
            elif "discharging" in states:
                state = "discharging"
            else:
                state = "unknown"
            status = {
                "available": True,
                "percent": int(sum(pcts) / len(pcts)) if pcts else 0,
                "charging": any(s in ("charging", "full") for s in states),
                "state": state,
            }
        except Exception:
            pass
        self.battery_status = status

    # -----------------------------------------------------------------
    # Battery popup menu
    # -----------------------------------------------------------------
    def _toggle_battery_menu(self, anchor_x):
        if (
            getattr(self, "active_menu", None)
            and self.active_menu.get("kind") == "battery"
        ):
            self._close_active_menu()
            return
        self._poll_battery_status()
        self._close_active_menu()
        self._close_confirm_dialog()

        st = self.battery_status
        if not st.get("available"):
            items = [
                {
                    "label": "No battery found",
                    "action": ("battery", ("noop", None)),
                },
                {
                    "label": "Cancel",
                    "action": ("battery", ("cancel", None)),
                },
            ]
        else:
            state_label = {
                "charging": "Charging",
                "discharging": "Discharging",
                "full": "Fully Charged",
            }.get(st.get("state"), "Battery")
            items = [
                {
                    "label": f"Battery: {st.get('percent', 0)}%",
                    "action": ("battery", ("noop", None)),
                },
                {
                    "label": state_label,
                    "action": ("battery", ("noop", None)),
                },
                {
                    "label": "Cancel",
                    "action": ("battery", ("cancel", None)),
                },
            ]
        self._open_menu("battery", items, anchor_x, self.BATTERY_W)

    def _battery_menu_action(self, payload):
        if not payload:
            return
        action, _value = payload
        if action in ("cancel", "noop"):
            return
