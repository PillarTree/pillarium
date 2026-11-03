"""Wallpaper loading and selection.

The desktop surface draws the wallpaper itself, so the only work here is
decoding the image, cropping it to the size of a monitor and remembering
the user's choice in ``config.json``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageOps

from .. import paths

#: File types offered by the wallpaper picker.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg", ".gif", ".tif", ".tiff")


@dataclass
class Wallpaper:
    """A wallpaper image together with the file it came from."""

    path: str
    image: Image.Image | None = None

    @property
    def valid(self) -> bool:
        return self.image is not None


class WallpaperManager:
    """Loads wallpapers and keeps the per-monitor selection in sync."""

    def __init__(self, config: Any = None):
        self._config = config

    # -----------------------------------------------------------------
    # Loading
    # -----------------------------------------------------------------
    @staticmethod
    def load(path: str | None) -> Wallpaper:
        """Decode ``path`` into a PIL image, or return an empty wallpaper."""
        if not path or not os.path.isfile(path):
            return Wallpaper(path=path or "")
        try:
            if path.lower().endswith(".svg"):
                image = _rasterise_svg(path)
            else:
                image = Image.open(path)
                image = ImageOps.exif_transpose(image)
            return Wallpaper(path=path, image=image.convert("RGB"))
        except Exception:
            return Wallpaper(path=path)

    @staticmethod
    def fit(image: Image.Image, width: int, height: int) -> Image.Image:
        """Cover-crop ``image`` to exactly ``width`` x ``height``."""
        if width <= 0 or height <= 0:
            return image
        ratio = max(width / image.width, height / image.height)
        resized = image.resize(
            (max(1, int(image.width * ratio + 0.5)), max(1, int(image.height * ratio + 0.5))),
            Image.LANCZOS,
        )
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        return resized.crop((left, top, left + width, top + height))

    # -----------------------------------------------------------------
    # Selection
    # -----------------------------------------------------------------
    def current_path(self, monitor: str | None = None) -> str:
        """Wallpaper for ``monitor``, falling back to the global setting."""
        if monitor and self._config is not None:
            per_monitor = self._config.get("wallpapers")
            if isinstance(per_monitor, dict) and per_monitor.get(monitor):
                return str(per_monitor[monitor])
        if self._config is not None:
            configured = self._config.wallpaper
            if configured:
                return configured
        return paths.wallpaper_path()

    def set_path(self, path: str, monitor: str | None = None) -> None:
        """Remember ``path`` as the wallpaper (optionally for one monitor)."""
        if self._config is None:
            return
        if monitor:
            per_monitor = dict(self._config.get("wallpapers") or {})
            per_monitor[monitor] = path
            self._config.set("wallpapers", per_monitor)
        else:
            self._config.wallpaper = path

    def pick_file(self, start_dir: str | None = None) -> str | None:
        """Ask the user for an image using whichever picker is installed."""
        start = start_dir or os.path.expanduser("~")
        pattern = " ".join(f"*{extension}" for extension in IMAGE_EXTENSIONS)
        candidates = (
            ["zenity", "--file-selection", "--title=Choose a wallpaper image"],
            ["kdialog", "--getopenfilename", start, f"Image Files ({pattern})"],
            ["yad", "--file", "--title=Choose a wallpaper image"],
        )
        for command in candidates:
            if not shutil.which(command[0]):
                continue
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True, timeout=120
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode != 0:
                continue
            chosen = result.stdout.strip()
            if chosen and os.path.isfile(chosen):
                return chosen
        return None

    def import_file(self, source: str) -> str | None:
        """Copy ``source`` into the Pillarium home and return the new path."""
        extension = os.path.splitext(source)[1].lower() or ".png"
        destination = os.path.join(paths.home_dir(), f"user_wallpaper{extension}")
        try:
            os.makedirs(paths.home_dir(), exist_ok=True)
            shutil.copyfile(source, destination)
        except OSError:
            return None
        return destination

    def default_path(self) -> str:
        """Path of the shipped wallpaper."""
        return paths.wallpaper_path()


def _rasterise_svg(path: str) -> Image.Image:
    """Rasterise an SVG using cairosvg, falling back to a plain surface."""
    try:
        import cairosvg
        from io import BytesIO

        data = cairosvg.svg2png(url=path, output_width=1920, output_height=1080)
        return Image.open(BytesIO(data))
    except Exception:
        return Image.new("RGB", (1920, 1080), (32, 36, 44))
