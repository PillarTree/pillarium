"""Image helpers: icon lookup, badges and customtkinter image conversion."""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

ICON_EXTENSIONS = (".png", ".svg", ".xpm", ".jpg", ".jpeg", ".webp")
ICON_THEMES = ("hicolor", "Adwaita", "breeze", "Papirus", "gnome")


def icon_search_dirs() -> list[str]:
    """Directories that may contain icon themes."""
    candidates = [
        os.path.join(os.path.expanduser("~"), ".local", "share", "icons"),
        os.path.join(os.path.expanduser("~"), ".icons"),
        os.path.join("/usr", "share", "icons"),
        os.path.join("/usr", "local", "share", "icons"),
        os.path.join("/usr", "share", "pixmaps"),
    ]
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for entry in data_dirs.split(":"):
        if entry:
            candidates.append(os.path.join(entry, "icons"))
    seen: set[str] = set()
    result: list[str] = []
    for path in candidates:
        resolved = os.path.abspath(os.path.expanduser(path))
        if resolved in seen or not os.path.isdir(resolved):
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _size_key(path: str) -> tuple[int, str]:
    """Sort key preferring themes whose nominal size is close to 48 px."""
    parts = path.split(os.sep)
    best = 9999
    for part in parts:
        if "x" in part:
            digits = part.split("x")
            if len(digits) == 2 and digits[0].isdigit() and digits[1].isdigit():
                best = min(best, abs(int(digits[0]) - 48))
    return (best, path)


@lru_cache(maxsize=1)
def icon_index() -> dict[str, list[str]]:
    """Map icon names to the files that provide them.

    The index is built once and cached: walking the icon themes for
    every single icon is far too slow for a launcher that shows
    hundreds of applications.
    """
    index: dict[str, list[str]] = {}
    for base in icon_search_dirs():
        for root, dirnames, filenames in os.walk(base):
            dirnames[:] = [item for item in dirnames if item not in (".git", "cache", "caches")]
            for filename in filenames:
                stem, extension = os.path.splitext(filename)
                if extension.lower() not in ICON_EXTENSIONS:
                    continue
                index.setdefault(stem.lower(), []).append(os.path.join(root, filename))
    return index


def find_icon_file(name: str | None) -> str | None:
    """Resolve an icon name to a file on disk."""
    if not name:
        return None
    if os.path.isabs(name):
        return name if os.path.isfile(name) else None
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    candidates = icon_index().get(stem)
    if not candidates:
        return None
    candidates = sorted(candidates, key=_size_key)
    return candidates[0]


@lru_cache(maxsize=256)
def _rasterise_cached(path: str, size: int) -> Image.Image | None:
    return rasterise(path, size)


def rasterise(path: str, size: int) -> Image.Image | None:
    """Load an icon file and scale it to ``size`` pixels."""
    try:
        if path.lower().endswith(".svg"):
            return _rasterise_svg(path, size)
        image = Image.open(path)
        image = image.convert("RGBA")
        image.thumbnail((size, size), Image.LANCZOS)
        return image
    except Exception:
        return None


def _rasterise_svg(path: str, size: int) -> Image.Image | None:
    try:
        import cairosvg
        from io import BytesIO

        data = cairosvg.svg2png(url=path, output_width=size, output_height=size)
        return Image.open(BytesIO(data)).convert("RGBA")
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["rsvg-convert", "-w", str(size), "-h", str(size), path],
            capture_output=True,
            timeout=6,
        )
        if result.returncode == 0 and result.stdout:
            from io import BytesIO

            return Image.open(BytesIO(result.stdout)).convert("RGBA")
    except (OSError, subprocess.SubprocessError):
        pass
    return None


@lru_cache(maxsize=512)
def load_icon(name: str | None, size: int = 32) -> Image.Image | None:
    """Resolve an icon name or path into a PIL image.

    The result is cached, so repeated taskbar repaints are cheap.
    """
    if not name:
        return None
    if os.path.isabs(name):
        if not os.path.isfile(name):
            return None
        return _rasterise_cached(name, size)
    path = find_icon_file(name)
    if path is None:
        return None
    return _rasterise_cached(path, size)


def letter_badge(
    letter: str,
    size: int = 26,
    background: str = "#5e81ac",
    foreground: str = "#ffffff",
    radius_ratio: float = 0.28,
) -> Image.Image:
    """Rounded badge showing the first letter of a label."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = max(3, int(size * radius_ratio))
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=radius,
        fill=_rgba(background),
    )
    glyph = (letter or "?").strip()[:1].upper() or "?"
    try:
        font = ImageFont.load_default()
        left, top, right, bottom = draw.textbbox((0, 0), glyph, font=font)
        width, height = right - left, bottom - top
    except Exception:
        width, height = 8, 10
    draw.text(
        ((size - width) / 2 - left, (size - height) / 2 - top),
        glyph,
        fill=_rgba(foreground),
        font=font,
    )
    return image


def _rgba(color: str) -> tuple[int, int, int, int]:
    text = color.lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) >= 6:
        try:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255
        except ValueError:
            pass
    return 255, 255, 255, 255


def compose(image: Image.Image, size: int, background: str | None = None) -> Image.Image:
    """Centre ``image`` on a square canvas of ``size`` pixels."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if background:
        canvas = Image.new("RGBA", (size, size), _rgba(background))
    if image is None:
        return canvas
    copy = image.convert("RGBA")
    copy.thumbnail((size, size), Image.LANCZOS)
    canvas.alpha_composite(copy, ((size - copy.width) // 2, (size - copy.height) // 2))
    return canvas


def to_ctk_image(image: Image.Image):
    """Convert a PIL image into a ``CTkImage``."""
    import customtkinter

    return customtkinter.CTkImage(
        light_image=image, dark_image=image, size=image.size
    )


def has_gio() -> bool:
    """Is a GIO based file chooser available?"""
    return shutil.which("gdbus") is not None and shutil.which("dbus-send") is not None
