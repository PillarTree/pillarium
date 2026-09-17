"""Drawing essentials shared across all Pillarium components (matching Cadet's Renderer)."""

import sys
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from . import theme

try:
    import numpy as _np
except Exception:
    _np = None


class Renderer:
    """Owns the framebuffer and exposes drawing primitives (matching Cadet)."""

    def __init__(self, width: int, height: int, font_ui, font_ui_b, font_mono):
        self.width = width
        self.height = height
        self.font_ui = font_ui
        self.font_ui_b = font_ui_b
        self.font_mono = font_mono
        self.img = Image.new("RGB", (width, height), theme.BG)
        self._draw = ImageDraw.Draw(self.img)
        self._clip = (0, 0, width, height)
        self._saved_clips: list = []
        self._text_cache: dict = {}

    # -- frame lifecycle ----------------------------------------------------
    def begin_frame(self):
        self.img.paste(theme.BG, (0, 0, self.width, self.height))
        self._draw = ImageDraw.Draw(self.img)
        self._clip = (0, 0, self.width, self.height)
        self._saved_clips = []

    def pixel_bytes(self) -> bytes:
        if _np is not None:
            rgb = self.img.tobytes()
            arr = _np.frombuffer(rgb, dtype=_np.uint8)
            arr = arr.reshape(self.height, self.width, 3)
            out = _np.zeros((self.height, self.width, 4), dtype=_np.uint8)
            out[:, :, 0] = arr[:, :, 2]   # B
            out[:, :, 1] = arr[:, :, 1]   # G
            out[:, :, 2] = arr[:, :, 0]   # R
            return out.tobytes()
        rgb = self.img.tobytes()
        out = bytearray(len(rgb) * 4 // 3)
        o = 0
        for i in range(0, len(rgb), 3):
            out[o] = rgb[i + 2]     # B
            out[o + 1] = rgb[i + 1] # G
            out[o + 2] = rgb[i]     # R
            o += 4
        return bytes(out)

    # -- clipping -----------------------------------------------------------
    def push_clip(self, x, y, w, h):
        cx, cy, cw, ch = self._clip
        x = max(cx, x)
        y = max(cy, y)
        x2 = min(cx + cw, x + w)
        y2 = min(cy + ch, y + h)
        self._saved_clips.append(self._clip)
        self._clip = (x, y, max(0, x2 - x), max(0, y2 - y))

    def pop_clip(self):
        if self._saved_clips:
            self._clip = self._saved_clips.pop()

    def _intersect(self, x, y, w, h):
        cx, cy, cw, ch = self._clip
        x = max(cx, x)
        y = max(cy, y)
        x2 = min(cx + cw, x + w)
        y2 = min(cy + ch, y + h)
        return x, y, max(0, x2 - x), max(0, y2 - y)

    # -- primitives ---------------------------------------------------------
    def rect(self, x, y, w, h, fill):
        x, y, w, h = self._intersect(x, y, w, h)
        if w <= 0 or h <= 0:
            return
        self._draw.rectangle([x, y, x + w - 1, y + h - 1], fill=fill)

    def outline(self, x, y, w, h, color, width=1):
        x0, y0, w0, h0 = self._intersect(x, y, w, h)
        if w0 <= 0 or h0 <= 0:
            return
        self._draw.rectangle([x0, y0, x0 + w0 - 1, y0 + h0 - 1],
                             outline=color, width=width)

    def hline(self, x, y, w, color):
        x, y, w, h = self._intersect(x, y, w, 1)
        if w <= 0:
            return
        self._draw.line([(x, y), (x + w - 1, y)], fill=color)

    def vline(self, x, y, h, color):
        x, y, w, h = self._intersect(x, y, 1, h)
        if h <= 0:
            return
        self._draw.line([(x, y), (x, y + h - 1)], fill=color)

    def text(self, x, y, s, color=theme.TEXT, font=None, anchor="la"):
        if not s:
            return
        if font is None:
            font = self.font_ui
        rgb, mask = self._text_tile(s, font, color)
        tw, th = mask.size
        if anchor == "ra":
            x -= tw
        elif anchor == "ma":
            x -= tw // 2
        x0, y0, w, h = self._intersect(x, y, tw, th)
        if w <= 0 or h <= 0:
            return
        box = (x0 - x, y0 - y, x0 - x + w, y0 - y + h)
        self.img.paste(rgb.crop(box), (x0, y0), mask.crop(box))

    def text_w(self, s, font=None) -> int:
        if not s:
            return 0
        if font is None:
            font = self.font_ui
        return font.getbbox(s)[2]

    def text_h(self, font=None) -> int:
        if font is None:
            font = self.font_ui
        a, d = font.getmetrics()
        return a + d

    def blit(self, img: Image.Image, x, y):
        x0, y0, w, h = self._intersect(x, y, img.width, img.height)
        if w <= 0 or h <= 0:
            return
        box = (x0 - x, y0 - y, x0 - x + w, y0 - y + h)
        region = img.crop(box)
        if img.mode in ("RGBA", "LA"):
            self.img.paste(region, (x0, y0), region)
        else:
            self.img.paste(region, (x0, y0))

    # -- text cache ---------------------------------------------------------
    def _text_tile(self, s, font, color):
        key = (s, id(font), color)
        item = self._text_cache.get(key)
        if item is None:
            mask = _render_tile(s, font, color)
            rgb = Image.new("RGB", mask.size, color)
            item = (rgb, mask)
            if len(self._text_cache) > 4000:
                self._text_cache.clear()
            self._text_cache[key] = item
        return item

    def clear_cache(self):
        self._text_cache.clear()

    # -- rounded rectangle --------------------------------------------------
    def rounded_rect(self, x, y, w, h, radius, fill, outline=None, outline_width=1):
        x, y, w, h = self._intersect(x, y, w, h)
        if w <= 0 or h <= 0:
            return
        r = min(radius, w // 2, h // 2)
        self._draw.rounded_rectangle([x, y, x + w - 1, y + h - 1],
                                     radius=r, fill=fill, outline=outline, width=outline_width)


def _render_tile(s, font, color):
    bbox = font.getbbox(s)
    w = max(1, bbox[2] - bbox[0])
    h = max(1, bbox[3] - bbox[1])
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    d.text((-bbox[0], -bbox[1]), s, font=font, fill=255)
    return img


# ---------------------------------------------------------------------------
# Legacy DrawingMixin for X11 window operations (kept for compatibility)
# ---------------------------------------------------------------------------
class DrawingMixin:
    def _init_font(self):
        self.font = None
        try:
            self.font = self.display.open_font("fixed")
            print(
                "Pillarium: loaded X core font 'fixed'",
                file=sys.stderr,
            )
        except Exception as exc:
            self.font = None
            print(
                f"Pillarium: could not load X core font 'fixed' ({exc}); "
                f"text drawn with draw_text may not render (desktop icon "
                f"labels fall back to Pillow-rendered bitmaps automatically)",
                file=sys.stderr,
            )

    def _gc(self, window, fg, bg):
        if not hasattr(self, "_gc_cache"):
            self._gc_cache = {}
        key = (window.id, fg, bg)
        if key not in self._gc_cache:
            self._gc_cache[key] = window.create_gc(foreground=fg, background=bg)
        return self._gc_cache[key]

    def _set_window_cursor(self, window, cursor_shape):
        try:
            if not self._cursor_font:
                self._cursor_font = self.display.open_font("cursor")
            if cursor_shape not in self._cursors:
                self._cursors[cursor_shape] = self.display.create_glyph_cursor(
                    self._cursor_font, self._cursor_font,
                    cursor_shape, cursor_shape + 1,
                    (65535, 65535, 65535), (0, 0, 0)
                )
            window.change_attributes(cursor=self._cursors[cursor_shape])
        except Exception:
            pass

    def _text_px_width(self, text):
        try:
            from PIL import Image, ImageDraw, ImageFont

            font = ImageFont.load_default()
            probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            try:
                bb = probe.textbbox((0, 0), text, font=font)
                return bb[2] - bb[0]
            except Exception:
                return probe.textsize(text, font=font)[0]
        except Exception:
            return len(str(text)) * 6

    def _draw_text_pixels(self, window, x, y, text, fg_hex, bg_hex, padding=2):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return False
        try:
            font = ImageFont.load_default()
            probe = Image.new("RGB", (1, 1))
            probe_draw = ImageDraw.Draw(probe)
            try:
                bbox = probe_draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = probe_draw.textsize(text, font=font)
            w = max(1, tw + padding * 2)
            h = max(1, th + padding * 2)
            bg_rgb = self._hex_to_rgb(bg_hex)
            fg_rgb = self._hex_to_rgb(fg_hex)
            img = Image.new("RGB", (w, h), bg_rgb)
            draw = ImageDraw.Draw(img)
            draw.text((padding, padding), text, fill=fg_rgb, font=font)
            gc = self._gc(
                window,
                self.colors.get("text", self.screen.white_pixel),
                self.colors.get("surface", self.screen.white_pixel),
            )
            window.put_pil_image(gc, x, y, img)
            return True
        except Exception:
            return False

    def _load_fonts(self):
        def load(path, size):
            if path and __import__("os").path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    pass
            return ImageFont.load_default(size)

        self.font_ui = load(theme.FONT_UI, 13)
        self.font_ui_b = load(theme.FONT_UI_B, 13) or self.font_ui
        self.font_mono = load(theme.FONT_MONO, 13)

    def _create_renderer(self, width, height):
        """Create a Cadet-style Renderer for the given dimensions."""
        self._load_fonts()
        return Renderer(width, height, self.font_ui, self.font_ui_b, self.font_mono)

    def _composite_rgba(self, rgba_img, bg_rgb):
        """Composite an RGBA image over a solid background color."""
        rgb = Image.new("RGB", rgba_img.size, bg_rgb)
        rgb.paste(rgba_img, (0, 0), rgba_img)
        return rgb

    def _make_icon_badge(self, icon, label, bg_hex):
        """Create a badge with icon and label (matching Cadet style)."""
        from PIL import ImageDraw, ImageFont

        bg_rgb = self._hex_to_rgb(bg_hex)
        badge_w = 32
        badge_h = 26
        badge = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)

        if icon:
            icon_rgba = icon.convert("RGBA")
            icon_rgba = icon_rgba.resize((24, 24), Image.LANCZOS)
            badge.paste(icon_rgba, (4, 1), icon_rgba)
        else:
            draw.rounded_rectangle(
                (2, 2, 30, 24), radius=6,
                fill=self._hex_to_rgb(self.current_palette.get("accent", "#3b82f6")),
                outline=self._hex_to_rgb(self.current_palette.get("text", "#ffffff")),
                width=1,
            )
            font = ImageFont.load_default()
            glyph = str(label)[:1].upper() if label else "?"
            try:
                bb = draw.textbbox((0, 0), glyph, font=font)
                gw, gh = bb[2] - bb[0], bb[3] - bb[1]
            except Exception:
                gw, gh = 8, 10
            draw.text(
                ((badge_w - gw) // 2, (badge_h - gh) // 2),
                glyph,
                fill=self._hex_to_rgb(self.current_palette.get("text", "#ffffff")),
                font=font,
            )
        return badge