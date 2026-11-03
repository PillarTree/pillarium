"""Bluetooth state and control via ``bluetoothctl``."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class BluetoothDevice:
    """A paired or discovered Bluetooth device."""

    mac: str
    name: str = ""
    connected: bool = False


@dataclass
class BluetoothState:
    """Snapshot of the Bluetooth adapter."""

    available: bool = False
    powered: bool = False
    scanning: bool = False
    devices: list[BluetoothDevice] = field(default_factory=list)


class BluetoothClient:
    """Small wrapper around the ``bluetoothctl`` command line tool."""

    def __init__(self) -> None:
        self._tool = shutil.which("bluetoothctl")

    @property
    def available(self) -> bool:
        return self._tool is not None

    def _run(self, args: list[str], timeout: float = 6.0) -> str | None:
        if not self._tool:
            return None
        try:
            result = subprocess.run(
                [self._tool, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------
    def set_power(self, enabled: bool) -> bool:
        return self._run(["power", "on" if enabled else "off"]) is not None

    def set_scanning(self, enabled: bool) -> bool:
        return self._run(["scan", "on" if enabled else "off"], timeout=12.0) is not None

    def connect(self, mac: str) -> bool:
        return self._run(["connect", mac], timeout=15.0) is not None

    def disconnect(self, mac: str) -> bool:
        return self._run(["disconnect", mac], timeout=12.0) is not None

    # -----------------------------------------------------------------
    # State
    # -----------------------------------------------------------------
    def poll(self) -> BluetoothState:
        """Read the adapter state and the list of known devices."""
        state = BluetoothState()
        if not self.available:
            return state
        state.available = True

        show = self._run(["show"]) or ""
        for line in show.splitlines():
            if line.startswith("Powered:"):
                state.powered = line.split(":", 1)[1].strip().lower() == "yes"
            elif line.startswith("Discovering:"):
                state.scanning = line.split(":", 1)[1].strip().lower() == "yes"

        devices = self._run(["devices"]) or ""
        for line in devices.splitlines():
            line = line.strip()
            if not line.startswith("Device"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            mac = parts[1]
            name = parts[2] if len(parts) > 2 else mac
            connected = False
            info = self._run(["info", mac], timeout=4.0) or ""
            for info_line in info.splitlines():
                if info_line.startswith("Connected:"):
                    connected = info_line.split(":", 1)[1].strip().lower() == "yes"
                    break
            state.devices.append(BluetoothDevice(mac=mac, name=name, connected=connected))
        return state
