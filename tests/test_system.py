"""Tests for the operating system integration layer."""

from __future__ import annotations

from pillarium.system.apps import ApplicationCatalog
from pillarium.system.battery import BatteryMonitor
from pillarium.system.launcher import Launcher
from pillarium.system.notifications import Notification
from pillarium.system.processes import ProcessManager
from pillarium.system.wallpaper import WallpaperManager
from pillarium.util import glyphs, images


def test_desktop_entries_are_parsed(tmp_path):
    entry = tmp_path / "demo.desktop"
    entry.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Demo App\n"
        "Exec=demo --flag %U\n"
        "Icon=demo\n"
        "StartupWMClass=Demo\n",
        encoding="utf-8",
    )
    app = ApplicationCatalog.parse_desktop_entry(str(entry))
    assert app is not None
    assert app.label == "Demo App"
    assert app.cmd == ["demo", "--flag"]
    assert app.icon == "demo"
    assert app.startup_wm_class == "Demo"


def test_hidden_desktop_entries_are_ignored(tmp_path):
    entry = tmp_path / "hidden.desktop"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Hidden\nExec=hidden\nHidden=true\n",
        encoding="utf-8",
    )
    assert ApplicationCatalog.parse_desktop_entry(str(entry)) is None


def test_desktop_entries_without_an_exec_are_ignored(tmp_path):
    entry = tmp_path / "broken.desktop"
    entry.write_text("[Desktop Entry]\nType=Application\nName=Broken\n", encoding="utf-8")
    assert ApplicationCatalog.parse_desktop_entry(str(entry)) is None


def test_the_process_list_is_readable():
    processes = ProcessManager().list(limit=5)
    assert processes
    assert processes[0].pid > 0
    assert len(processes) <= 5


def test_the_battery_state_is_valid():
    state = BatteryMonitor.poll()
    assert 0 <= state.percent <= 100
    assert state.state in ("charging", "full", "discharging", "unknown")


def test_glyphs_are_drawn():
    for factory in (
        glyphs.launcher_icon,
        glyphs.wifi_icon,
        glyphs.speaker_icon,
        glyphs.bluetooth_icon,
        glyphs.ethernet_icon,
        glyphs.battery_icon,
        glyphs.power_icon,
        glyphs.monitor_icon,
        glyphs.grid_icon,
    ):
        image = factory(20, "#ffffff")
        assert image.size == (20, 20)
        assert image.getbbox() is not None


def test_letter_badges_show_the_first_letter():
    badge = images.letter_badge("F", 24, "#5e81ac", "#ffffff")
    assert badge.size == (24, 24)


def test_wallpapers_are_cropped_to_the_screen(tmp_path):
    from PIL import Image

    source = tmp_path / "wall.png"
    Image.new("RGB", (400, 200), (10, 20, 30)).save(source)
    wallpaper = WallpaperManager.load(str(source))
    assert wallpaper.valid
    fitted = WallpaperManager.fit(wallpaper.image, 800, 600)
    assert fitted.size == (800, 600)


def test_missing_wallpapers_are_handled(tmp_path):
    wallpaper = WallpaperManager.load(str(tmp_path / "missing.png"))
    assert not wallpaper.valid


def test_notifications_expose_their_urgency():
    note = Notification(id=1, summary="hi", hints={"urgency": 2})
    assert note.critical
    note = Notification(id=2, summary="hi", hints={"urgency": 0})
    assert not note.critical


def test_the_launcher_enriches_icons_with_the_catalogue(tmp_path):
    catalogue = ApplicationCatalog()
    catalogue.applications = [
        type(
            "App",
            (),
            {
                "label": "Demo",
                "cmd": ["demo"],
                "icon": "demo-icon",
                "desktop_file": "/usr/share/applications/demo.desktop",
                "startup_wm_class": "Demo",
            },
        )()
    ]
    launcher = Launcher(catalogue)
    items = [{"cmd": ["demo"], "label": "Demo"}]
    assert launcher.enrich(items) is True
    assert items[0]["icon"] == "demo-icon"
    assert launcher.enrich(items) is False
