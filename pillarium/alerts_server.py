"""UNIX socket used by ``pillarium-notify`` to raise alerts.

The socket accepts newline delimited JSON objects::

    {"level": "warning", "title": "Disk full", "message": "90% used"}

Only the owner of the socket may talk to it; the file is created with
``0600`` permissions.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import threading
from typing import Any, Callable

from . import paths

#: Largest request the server accepts.
MAX_REQUEST = 64 * 1024


class AlertSocketServer:
    """Accepts alert requests on a UNIX socket."""

    def __init__(self, handler: Callable[[dict], Any]):
        self._handler = handler
        self._path = paths.alert_socket_path()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------
    def start(self) -> bool:
        """Bind the socket and start serving in the background."""
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            if os.path.exists(self._path):
                os.unlink(self._path)
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(self._path)
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
            server.listen(8)
            server.settimeout(0.5)
        except OSError:
            return False

        self._socket = server
        self._thread = threading.Thread(target=self._serve, name="pillarium-alerts", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop serving and remove the socket file."""
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        try:
            if os.path.exists(self._path):
                os.unlink(self._path)
        except OSError:
            pass

    # -----------------------------------------------------------------
    # Serving
    # -----------------------------------------------------------------
    def _serve(self) -> None:
        while not self._stop.is_set():
            server = self._socket
            if server is None:
                break
            try:
                connection, _address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._handle(connection)
            except Exception:
                pass
            finally:
                try:
                    connection.close()
                except OSError:
                    pass

    def _handle(self, connection: socket.socket) -> None:
        connection.settimeout(2.0)
        buffer = b""
        try:
            while b"\n" not in buffer and len(buffer) < MAX_REQUEST:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                buffer += chunk
        except (socket.timeout, OSError):
            return
        for line in buffer.split(b"\n"):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            try:
                self._handler(payload)
            except Exception:
                continue
