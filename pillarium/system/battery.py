"""Battery status read straight from ``/sys/class/power_supply``."""

from __future__ import annotations

import os
from dataclasses import dataclass

POWER_SUPPLY_ROOT = "/sys/class/power_supply"


@dataclass
class BatteryState:
    """Snapshot of the machine's battery."""

    available: bool = False
    percent: int = 0
    charging: bool = False
    state: str = "unknown"

    @property
    def low(self) -> bool:
        return self.available and not self.charging and self.percent <= 20

    @property
    def label(self) -> str:
        if not self.available:
            return "No battery"
        if self.state == "charging":
            return "Charging"
        if self.state == "full":
            return "Fully charged"
        if self.state == "discharging":
            return "Discharging"
        return "Battery"


class BatteryMonitor:
    """Reads the aggregate state of every battery in the system."""

    @staticmethod
    def poll() -> BatteryState:
        """Average every battery and derive the charging state."""
        state = BatteryState()
        percentages: list[int] = []
        states: list[str] = []
        try:
            entries = os.listdir(POWER_SUPPLY_ROOT)
        except OSError:
            return state

        for entry in entries:
            base = os.path.join(POWER_SUPPLY_ROOT, entry)
            try:
                with open(os.path.join(base, "type"), "r", encoding="utf-8") as handle:
                    if handle.read().strip() != "battery":
                        continue
            except OSError:
                continue
            try:
                with open(os.path.join(base, "capacity"), "r", encoding="utf-8") as handle:
                    percentages.append(int(handle.read().strip()))
            except (OSError, ValueError):
                pass
            try:
                with open(os.path.join(base, "status"), "r", encoding="utf-8") as handle:
                    states.append(handle.read().strip().lower())
            except OSError:
                pass

        if not percentages:
            return state

        state.available = True
        state.percent = sum(percentages) // len(percentages)
        if "charging" in states:
            state.state = "charging"
        elif "full" in states:
            state.state = "full"
        elif "discharging" in states:
            state.state = "discharging"
        else:
            state.state = "unknown"
        state.charging = state.state in ("charging", "full")
        return state
