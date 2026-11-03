"""Process listing and termination."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class ProcessInfo:
    """A single row of the process table."""

    pid: int
    name: str
    cpu: float
    memory: float


class ProcessManager:
    """Reads the system process table and terminates processes."""

    def list(self, limit: int = 200) -> list[ProcessInfo]:
        """Return the busiest processes, highest CPU first."""
        try:
            result = subprocess.run(
                ["ps", "-eo", "pid,comm,pcpu,pmem", "--sort=-pcpu"],
                capture_output=True,
                text=True,
                timeout=4,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0:
            return []

        processes: list[ProcessInfo] = []
        for line in result.stdout.splitlines()[1:]:
            fields = line.split(None, 3)
            if len(fields) < 3:
                continue
            try:
                pid = int(fields[0])
                cpu = float(fields[2])
            except ValueError:
                continue
            try:
                memory = float(fields[3]) if len(fields) > 3 else 0.0
            except ValueError:
                memory = 0.0
            name = fields[1][:28] if len(fields) > 1 else "?"
            processes.append(ProcessInfo(pid=pid, name=name, cpu=cpu, memory=memory))
            if len(processes) >= limit:
                break
        return processes

    @staticmethod
    def terminate(pid: int) -> bool:
        """Ask a process to exit.  Returns ``True`` when the signal was sent."""
        try:
            subprocess.Popen(["kill", "-TERM", str(pid)])
        except (OSError, ValueError):
            return False
        return True

    @staticmethod
    def kill(pid: int) -> bool:
        """Forcefully kill a process."""
        try:
            subprocess.Popen(["kill", "-KILL", str(pid)])
        except (OSError, ValueError):
            return False
        return True
