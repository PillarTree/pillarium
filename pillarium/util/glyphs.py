"""Vector-ish status glyphs drawn with Pillow.

The taskbar shows a lot of small status indicators.  Drawing them with
Pillow instead of relying on Unicode symbols keeps them consistent on
every font and lets them react to the current state (connected,
muted, charging, ...).
"""

from __future__ import annotations

from PIL import Image, ImageDraw

Color = tuple[int, int, int, int]


def _rgba(color: str, alpha: int = 255) -> Color:
    text = str(color).lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) >= 6:
        try:
            return (
                int(text[0:2], 16),
                int(text[2:4], 16),
                int(text[4:6], 16),
                alpha,
            )
        except ValueError:
            pass
    return 255, 255, 255, alpha


def _canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def launcher_icon(size: int = 20, color: str = "#ffffff") -> Image.Image:
    """A four tile grid used for the application launcher button."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    margin = size * 0.14
    gap = size * 0.1
    cell = (size - margin * 2 - gap) / 2
    for row in range(2):
        for column in range(2):
            x = margin + column * (cell + gap)
            y = margin + row * (cell + gap)
            draw.rounded_rectangle(
                (x, y, x + cell, y + cell), radius=max(1, size * 0.08), fill=fill
            )
    return image


def wifi_icon(size: int = 20, color: str = "#ffffff", connected: bool = True) -> Image.Image:
    """Three arcs above a dot; a strike-through when disconnected."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    width = max(1, int(size * 0.1))
    for index, ratio in enumerate((0.85, 0.6, 0.35)):
        radius = size * ratio / 2
        centre_x = size / 2
        centre_y = size * 0.86
        box = (centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius)
        draw.arc(box, start=200, end=340, fill=fill, width=width)
    dot = size * 0.1
    draw.ellipse(
        (size / 2 - dot, size * 0.82 - dot, size / 2 + dot, size * 0.82 + dot), fill=fill
    )
    if not connected:
        draw.line((size * 0.08, size * 0.92, size * 0.92, size * 0.08), fill=fill, width=width)
    return image


def speaker_icon(size: int = 20, color: str = "#ffffff", muted: bool = False) -> Image.Image:
    """A speaker cone with sound waves, or a crossed-out speaker."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    body = [
        (size * 0.16, size * 0.38),
        (size * 0.32, size * 0.38),
        (size * 0.52, size * 0.2),
        (size * 0.52, size * 0.8),
        (size * 0.32, size * 0.62),
        (size * 0.16, size * 0.62),
    ]
    draw.polygon(body, fill=fill)
    if muted:
        draw.line((size * 0.6, size * 0.3, size * 0.88, size * 0.7), fill=fill, width=max(1, size // 12))
        draw.line((size * 0.88, size * 0.3, size * 0.6, size * 0.7), fill=fill, width=max(1, size // 12))
    else:
        width = max(1, int(size * 0.08))
        for ratio in (0.62, 0.82):
            box = (
                size * 0.52 - size * ratio * 0.4,
                size * 0.5 - size * ratio * 0.55,
                size * 0.52 + size * ratio * 0.4,
                size * 0.5 + size * ratio * 0.55,
            )
            draw.arc(box, start=300, end=60, fill=fill, width=width)
    return image


def bluetooth_icon(size: int = 20, color: str = "#ffffff", enabled: bool = True) -> Image.Image:
    """The Bluetooth rune."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    width = max(1, int(size * 0.09))
    centre = size / 2
    draw.line((centre, size * 0.12, centre, size * 0.88), fill=fill, width=width)
    draw.line((centre, size * 0.12, size * 0.72, size * 0.36), fill=fill, width=width)
    draw.line((centre, size * 0.88, size * 0.72, size * 0.64), fill=fill, width=width)
    draw.line((centre, size * 0.12, size * 0.28, size * 0.36), fill=fill, width=width)
    draw.line((centre, size * 0.88, size * 0.28, size * 0.64), fill=fill, width=width)
    if not enabled:
        draw.line((size * 0.1, size * 0.9, size * 0.9, size * 0.1), fill=fill, width=width)
    return image


def ethernet_icon(size: int = 20, color: str = "#ffffff", connected: bool = True) -> Image.Image:
    """A small network port."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    width = max(1, int(size * 0.08))
    draw.rectangle(
        (size * 0.18, size * 0.3, size * 0.82, size * 0.72), outline=fill, width=width
    )
    draw.line((size * 0.3, size * 0.72, size * 0.45, size * 0.9), fill=fill, width=width)
    draw.line((size * 0.7, size * 0.72, size * 0.55, size * 0.9), fill=fill, width=width)
    if not connected:
        draw.line((size * 0.12, size * 0.88, size * 0.88, size * 0.12), fill=fill, width=width)
    return image


def battery_icon(
    size: int = 20,
    color: str = "#ffffff",
    percent: int = 50,
    charging: bool = False,
) -> Image.Image:
    """A battery with a fill level and an optional charging bolt."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    width = max(1, int(size * 0.08))
    body = (size * 0.12, size * 0.28, size * 0.78, size * 0.72)
    draw.rounded_rectangle(body, radius=size * 0.08, outline=fill, width=width)
    draw.rectangle(
        (size * 0.8, size * 0.42, size * 0.9, size * 0.58), fill=fill
    )
    level = max(0, min(100, int(percent)))
    if level > 0:
        inner_width = (body[2] - body[0] - width * 2) * (level / 100)
        draw.rectangle(
            (body[0] + width, body[1] + width, body[0] + width + inner_width, body[3] - width),
            fill=fill,
        )
    if charging:
        bolt = [
            (size * 0.55, size * 0.18),
            (size * 0.38, size * 0.5),
            (size * 0.48, size * 0.5),
            (size * 0.42, size * 0.82),
            (size * 0.62, size * 0.46),
            (size * 0.5, size * 0.46),
        ]
        draw.polygon(bolt, fill=fill)
    return image


def power_icon(size: int = 20, color: str = "#ffffff") -> Image.Image:
    """The power symbol."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    width = max(1, int(size * 0.09))
    box = (size * 0.24, size * 0.24, size * 0.76, size * 0.8)
    draw.arc(box, start=-60, end=240, fill=fill, width=width)
    draw.line((size * 0.5, size * 0.1, size * 0.5, size * 0.42), fill=fill, width=width)
    return image


def monitor_icon(size: int = 20, color: str = "#ffffff") -> Image.Image:
    """A display with a stand."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    width = max(1, int(size * 0.08))
    draw.rounded_rectangle(
        (size * 0.12, size * 0.2, size * 0.88, size * 0.68),
        radius=size * 0.08,
        outline=fill,
        width=width,
    )
    draw.line((size * 0.5, size * 0.68, size * 0.5, size * 0.82), fill=fill, width=width)
    draw.line((size * 0.3, size * 0.86, size * 0.7, size * 0.86), fill=fill, width=width)
    return image


def grid_icon(size: int = 20, color: str = "#ffffff") -> Image.Image:
    """Two rows of squares, used for the desktop switcher."""
    image, draw = _canvas(size)
    fill = _rgba(color)
    margin = size * 0.12
    gap = size * 0.08
    cell = (size - margin * 2 - gap) / 2
    for row in range(2):
        for column in range(2):
            x = margin + column * (cell + gap)
            y = margin + row * (cell + gap)
            draw.rectangle((x, y, x + cell, y + cell), outline=fill, width=max(1, size // 14))
    return image
