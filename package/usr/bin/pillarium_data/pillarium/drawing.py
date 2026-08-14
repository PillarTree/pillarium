"""Drawing essentials shared across all Pillarium components."""

import sys


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
