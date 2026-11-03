"""Wireless and wired network state, driven by NetworkManager."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class WirelessNetwork:
    """A single visible Wi-Fi network."""

    ssid: str
    signal: int = 0
    in_use: bool = False
    secured: bool = False


@dataclass
class NetworkState:
    """Snapshot of the machine's connectivity."""

    wifi_available: bool = False
    wifi_enabled: bool = True
    wifi_connected: bool = False
    ssid: str | None = None
    signal: int = 0
    ethernet_available: bool = False
    ethernet_connected: bool = False
    ethernet_device: str | None = None
    ethernet_connection: str | None = None
    networks: list[WirelessNetwork] = field(default_factory=list)

    @property
    def connected(self) -> bool:
        return self.wifi_connected or self.ethernet_connected


class NetworkManagerClient:
    """Thin wrapper around the ``nmcli`` command line tool."""

    def __init__(self) -> None:
        self._nmcli = shutil.which("nmcli")

    @property
    def available(self) -> bool:
        return self._nmcli is not None

    # -----------------------------------------------------------------
    # Low level helpers
    # -----------------------------------------------------------------
    def _run(self, args: list[str], timeout: float = 4.0) -> str | None:
        if not self._nmcli:
            return None
        try:
            result = subprocess.run(
                [self._nmcli, *args],
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
    # Wi-Fi
    # -----------------------------------------------------------------
    def wifi_radio_enabled(self) -> bool:
        output = self._run(["radio", "wifi"])
        if output is None:
            return True
        return output.strip().lower() == "enabled"

    def set_wifi_radio(self, enabled: bool) -> bool:
        output = self._run(["radio", "wifi", "on" if enabled else "off"])
        return output is not None

    def wifi_device(self) -> str | None:
        output = self._run(["-t", "-f", "DEVICE,TYPE", "dev"])
        if not output:
            return None
        for line in output.splitlines():
            fields = line.split(":")
            if len(fields) >= 2 and fields[1].strip() == "wifi":
                return fields[0].strip()
        return None

    def scan_wifi(self) -> bool:
        return self._run(["dev", "wifi", "rescan"], timeout=8.0) is not None

    def list_wifi_networks(self) -> list[WirelessNetwork]:
        """Visible networks, strongest first with the active one on top."""
        output = self._run(["-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi"])
        if output is None:
            return []
        found: dict[str, WirelessNetwork] = {}
        for line in output.splitlines():
            if ":" not in line:
                continue
            parts = line.split(":")
            if len(parts) < 2:
                continue
            ssid = parts[0].strip()
            if not ssid:
                continue
            try:
                signal = int(parts[1].strip() or 0)
            except ValueError:
                signal = 0
            secured = len(parts) > 2 and bool(parts[2].strip())
            existing = found.get(ssid)
            if existing is None:
                found[ssid] = WirelessNetwork(ssid=ssid, signal=signal, secured=secured)
            else:
                existing.signal = max(existing.signal, signal)
                existing.secured = existing.secured or secured
        return sorted(found.values(), key=lambda net: (-net.signal, net.ssid.lower()))

    def active_wifi(self) -> tuple[bool, str | None, int]:
        """Return ``(connected, ssid, signal)`` for the active network."""
        output = self._run(["-t", "-f", "ACTIVE,SIGNAL,SSID", "dev", "wifi"])
        if output is None:
            return False, None, 0
        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) < 3:
                continue
            if parts[0].strip().lower() != "yes":
                continue
            try:
                signal = int(parts[1].strip() or 0)
            except ValueError:
                signal = 0
            return True, parts[2].strip() or None, signal
        return False, None, 0

    def connect_wifi(self, ssid: str, password: str | None = None) -> bool:
        args = ["dev", "wifi", "connect", ssid]
        if password:
            args.extend(["password", password])
        return self._run(args, timeout=25.0) is not None

    def disconnect_wifi(self) -> bool:
        device = self.wifi_device()
        if not device:
            return False
        return self._run(["dev", "disconnect", device], timeout=8.0) is not None

    # -----------------------------------------------------------------
    # Ethernet
    # -----------------------------------------------------------------
    def ethernet_devices(self) -> list[tuple[str, str, str | None]]:
        """Return ``(device, state, connection)`` tuples for wired NICs."""
        output = self._run(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"])
        if output is None:
            return []
        devices: list[tuple[str, str, str | None]] = []
        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) < 3 or parts[1].strip() != "ethernet":
                continue
            connection = parts[3].strip() if len(parts) > 3 and parts[3].strip() else None
            devices.append((parts[0].strip(), parts[2].strip(), connection))
        return devices

    def connect_ethernet(self, device: str) -> bool:
        return self._run(["dev", "connect", device], timeout=20.0) is not None

    def disconnect_ethernet(self, device: str) -> bool:
        return self._run(["dev", "disconnect", device], timeout=8.0) is not None

    # -----------------------------------------------------------------
    # Aggregated state
    # -----------------------------------------------------------------
    def poll(self) -> NetworkState:
        """Read the current connectivity state."""
        state = NetworkState()
        state.wifi_available = self.available
        if self.available:
            state.wifi_enabled = self.wifi_radio_enabled()
            connected, ssid, signal = self.active_wifi()
            state.wifi_connected = connected
            state.ssid = ssid
            state.signal = signal
            if state.wifi_enabled:
                state.networks = self.list_wifi_networks()

        devices = self.ethernet_devices()
        state.ethernet_available = bool(devices)
        if devices:
            connected = [device for device in devices if device[1] == "connected"]
            chosen = connected[0] if connected else devices[0]
            state.ethernet_device = chosen[0]
            state.ethernet_connection = chosen[2]
            state.ethernet_connected = chosen[1] == "connected"
        return state
