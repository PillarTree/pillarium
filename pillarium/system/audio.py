"""Audio control for PipeWire (``wpctl``) and PulseAudio (``pactl``)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class AudioNode:
    """A sink or a playing stream."""

    id: str
    name: str = ""
    volume: int = 0
    muted: bool = False
    is_default: bool = False
    is_stream: bool = False


@dataclass
class AudioState:
    """Snapshot of the audio subsystem."""

    available: bool = False
    volume: int = 0
    muted: bool = False
    sink: str | None = None
    sinks: list[AudioNode] = field(default_factory=list)
    streams: list[AudioNode] = field(default_factory=list)
    default_sink: AudioNode | None = None


class AudioClient:
    """Reads and writes the audio state through the available backend."""

    def __init__(self) -> None:
        self._wpctl = shutil.which("wpctl")
        self._pactl = shutil.which("pactl")

    @property
    def backend(self) -> str | None:
        """Name of the backend in use, or ``None`` when neither exists."""
        if self._wpctl:
            return "wpctl"
        if self._pactl:
            return "pactl"
        return None

    @property
    def available(self) -> bool:
        return self.backend is not None

    def _run(self, args: list[str], timeout: float = 4.0) -> str | None:
        tool = self._wpctl if self._wpctl else self._pactl
        if not tool:
            return None
        try:
            result = subprocess.run(
                [tool, *args], capture_output=True, text=True, timeout=timeout
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout

    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------
    def poll(self) -> AudioState:
        """Read the default sink volume, mute state and node list."""
        state = AudioState()
        if not self.available:
            return state
        state.available = True

        if self._wpctl:
            volume_output = self._run(["get-volume", "@DEFAULT_AUDIO_SINK@"]) or ""
            match = re.search(r"([0-9]*\.?[0-9]+)", volume_output)
            if match:
                try:
                    state.volume = max(0, min(150, int(round(float(match.group(1)) * 100))))
                except ValueError:
                    state.volume = 0
            state.muted = "[MUTED]" in volume_output
            status = self._run(["status"]) or ""
            for line in status.splitlines():
                if "Audio Sink" in line:
                    state.sink = line.strip()[:56]
                    break
        else:
            volume_output = self._run(["get-sink-volume", "@DEFAULT_SINK@"]) or ""
            match = re.search(r"(\d+)%", volume_output)
            if match:
                state.volume = max(0, min(150, int(match.group(1))))
            mute_output = self._run(["get-sink-mute", "@DEFAULT_SINK@"]) or ""
            state.muted = "yes" in mute_output.lower()
            state.sink = (self._run(["get-default-sink"]) or "").strip()[:56] or None

        nodes = self.nodes()
        state.sinks = nodes[0]
        state.streams = nodes[1]
        for sink in state.sinks:
            if sink.is_default:
                state.default_sink = sink
                break
        return state

    # -----------------------------------------------------------------
    # Nodes
    # -----------------------------------------------------------------
    def nodes(self) -> tuple[list[AudioNode], list[AudioNode]]:
        """Return ``(sinks, streams)``."""
        if self._wpctl:
            return self._wpctl_nodes()
        if self._pactl:
            return self._pactl_nodes()
        return [], []

    def _wpctl_nodes(self) -> tuple[list[AudioNode], list[AudioNode]]:
        status = self._run(["status"]) or ""
        sinks: list[AudioNode] = []
        streams: list[AudioNode] = []
        section = ""
        pattern = re.compile(r"^\s*(?:[│├└| ]*)(\*?)\s*(\d+)\.\s+(.+?)\s*\[(.*)\]\s*$")
        for line in status.splitlines():
            stripped = line.strip()
            if stripped.startswith("Streams:"):
                section = "streams"
                continue
            if stripped.startswith("Sinks:"):
                section = "sinks"
                continue
            if stripped.startswith("Sources:"):
                section = "sources"
                continue
            if not section:
                continue
            match = pattern.match(line)
            if not match:
                continue
            marker, index, name, meta = match.groups()
            if "vol:" not in meta:
                continue
            volume = 0
            volume_match = re.search(r"vol:([0-9.]+)", meta)
            if volume_match:
                try:
                    volume = max(0, min(150, int(round(float(volume_match.group(1)) * 100))))
                except ValueError:
                    volume = 0
            node = AudioNode(
                id=index,
                name=name.strip(),
                volume=volume,
                muted="MUTED" in meta,
                is_default=marker == "*",
                is_stream=section == "streams",
            )
            if section == "streams":
                streams.append(node)
            elif section == "sinks":
                sinks.append(node)
        return sinks, streams

    def _pactl_nodes(self) -> tuple[list[AudioNode], list[AudioNode]]:
        sinks: list[AudioNode] = []
        streams: list[AudioNode] = []
        default_name = (self._run(["get-default-sink"]) or "").strip()

        for block, is_stream in (
            (self._run(["list", "sinks"]) or "", False),
            (self._run(["list", "sink-inputs"]) or "", True),
        ):
            current: AudioNode | None = None
            for line in block.splitlines():
                if line.startswith("Sink #") or line.startswith("Sink Input #"):
                    identifier = line.split("#", 1)[1].strip()
                    current = AudioNode(id=identifier, is_stream=is_stream)
                    continue
                if current is None:
                    continue
                if line.startswith("Name:"):
                    current.name = line.split(":", 1)[1].strip()
                elif line.startswith("Mute:"):
                    current.muted = line.split(":", 1)[1].strip().lower() == "yes"
                elif line.startswith("Volume:"):
                    match = re.search(r"(\d+)%", line)
                    if match:
                        current.volume = max(0, min(150, int(match.group(1))))
                elif "application.name" in line:
                    match = re.search(r'=\s*"([^"]+)"', line)
                    if match and match.group(1):
                        current.name = match.group(1)
                elif not line.strip():
                    if current.name:
                        current.name = _pretty_node_name(current.name)
                        if not is_stream and current.name == default_name:
                            current.is_default = True
                        if is_stream:
                            streams.append(current)
                        else:
                            sinks.append(current)
                    current = None
            if current is not None and current.name:
                current.name = _pretty_node_name(current.name)
                if not is_stream and current.name == default_name:
                    current.is_default = True
                if is_stream:
                    streams.append(current)
                else:
                    sinks.append(current)
        return sinks, streams

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------
    def set_volume(self, percent: int) -> bool:
        percent = max(0, min(150, int(percent)))
        if self._wpctl:
            return self._run(["set-volume", "@DEFAULT_AUDIO_SINK@", f"{percent / 100:.2f}"]) is not None
        if self._pactl:
            return self._run(["set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"]) is not None
        return False

    def nudge_volume(self, delta: int) -> bool:
        if self._wpctl:
            sign = "+" if delta >= 0 else "-"
            return self._run(["set-volume", "@DEFAULT_AUDIO_SINK@", f"{abs(delta)}%{sign}"]) is not None
        if self._pactl:
            sign = "+" if delta >= 0 else "-"
            return self._run(["set-sink-volume", "@DEFAULT_SINK@", f"{abs(delta)}%{sign}"]) is not None
        return False

    def toggle_mute(self) -> bool:
        if self._wpctl:
            return self._run(["set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]) is not None
        if self._pactl:
            return self._run(["set-sink-mute", "@DEFAULT_SINK@", "toggle"]) is not None
        return False

    def set_node_volume(self, node: AudioNode, percent: int) -> bool:
        percent = max(0, min(150, int(percent)))
        node.volume = percent
        if self._wpctl:
            return self._run(["set-volume", node.id, f"{percent / 100:.2f}"]) is not None
        if self._pactl:
            command = "set-sink-input-volume" if node.is_stream else "set-sink-volume"
            return self._run([command, node.id, f"{percent}%"]) is not None
        return False

    def toggle_node_mute(self, node: AudioNode) -> bool:
        node.muted = not node.muted
        if self._wpctl:
            return self._run(["set-mute", node.id, "toggle"]) is not None
        if self._pactl:
            command = "set-sink-input-mute" if node.is_stream else "set-sink-mute"
            return self._run([command, node.id, "toggle"]) is not None
        return False


def _pretty_node_name(name: str) -> str:
    """Turn ``alsa_output.pci-0000_00_1f.3.analog-stereo`` into a label."""
    if not name:
        return name
    if "." in name:
        name = name.split(".")[-1]
    return name.replace("_", " ").replace("-", " ").title()
