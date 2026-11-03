"""Shared test fixtures for the Pillarium test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point Pillarium at a throw-away home directory."""
    directory = tmp_path / "home"
    directory.mkdir()
    monkeypatch.setenv("PILLARIUM_HOME", str(directory))
    monkeypatch.setenv("PILLARIUM_CONFIG", str(directory / "config.json"))
    monkeypatch.setenv("PILLARIUM_THEMES", str(directory / "themes"))
    return directory


@pytest.fixture
def config(home):
    """A configuration backed by the temporary home."""
    from pillarium.config import Config

    return Config.load()


def _display_available() -> bool:
    return bool(os.environ.get("DISPLAY")) and os.path.exists(
        os.path.join("/tmp/.X11-unix", f"X{os.environ.get('DISPLAY', '').lstrip(':')}")
    )


@pytest.fixture(scope="session")
def xdisplay():
    """An X display to run the window manager tests on.

    Uses ``$DISPLAY`` when it is set, otherwise starts a private Xvfb.
    """
    if os.environ.get("PILLARIUM_TEST_DISPLAY"):
        os.environ["DISPLAY"] = os.environ["PILLARIUM_TEST_DISPLAY"]
        yield os.environ["DISPLAY"]
        return
    if _display_available() and os.environ.get("PILLARIUM_TEST_USE_CURRENT_DISPLAY"):
        yield os.environ["DISPLAY"]
        return
    if not shutil.which("Xvfb"):
        pytest.skip("Xvfb is not installed")
    number = 90 + (os.getpid() % 8)
    display = f":{number}"
    process = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x800x24", "+extension", "RANDR"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = 20
    while deadline > 0:
        if os.path.exists(f"/tmp/.X11-unix/X{number}"):
            break
        import time

        time.sleep(0.2)
        deadline -= 1
    else:
        process.terminate()
        pytest.skip("Xvfb did not start")
    previous = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = display
    yield display
    if previous is None:
        os.environ.pop("DISPLAY", None)
    else:
        os.environ["DISPLAY"] = previous
    process.terminate()
    process.wait(timeout=5)
