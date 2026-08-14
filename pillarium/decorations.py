"""Window-decoration drawing: titlebars, control buttons, icon badges."""

import sys


class DecorationMixin:
    def _redraw_window(self, window):
        """Redraw window decorations to match taskbar aesthetic."""
        # Find which frame this window belongs to
        frame_data = None
        frame_client_id = None
        for client_id, data in self.frames.items():
            if window.id in {data["frame"].id, data["titlebar"].id,
                             data["close_button"].id, data["maximize_button"].id,
                             data["minimize_button"].id}:
                frame_data = data
                frame_client_id = client_id
                break

        if not frame_data:
            return

        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return

        try:
            if window.id == frame_data["titlebar"].id:
                # Draw titlebar background and content
                titlebar = window
                width = frame_data.get("width", 760)

                bg_hex = self.current_palette.get("taskbar", "#071027")
                fg_hex = self.current_palette.get("text", "#e6eef8")
                border_hex = self.current_palette.get("border", "#0f172a")
                active_hex = self.current_palette.get("taskbar_active", "#1f2937")

                # Focused windows use the taskbar's "active item" colour,
                # matching how the taskbar highlights the focused window.
                focused = frame_client_id == self.focused_client
                bar_hex = active_hex if focused else bg_hex
                bar_color = "taskbar_active" if focused else "taskbar"

                bg_rgb = self._hex_to_rgb(bar_hex)
                fg_rgb = self._hex_to_rgb(fg_hex)
                border_rgb = self._hex_to_rgb(border_hex)

                # Clear titlebar
                gc = self._gc(
                    titlebar,
                    self.colors[bar_color],
                    self.colors[bar_color],
                )
                titlebar.fill_rectangle(gc, 0, 0, width, self.TITLEBAR_H)

                # App icon badge, matching the taskbar item badges
                badge = self._make_icon_badge(
                    self._resolve_taskbar_icon(frame_data),
                    frame_data.get("title", "?"),
                    bar_hex,
                )
                try:
                    badge_rgb = self._composite_rgba(badge, bar_hex)
                    gc_img = self._gc(
                        titlebar,
                        self.colors["text"],
                        self.colors[bar_color],
                    )
                    titlebar.put_pil_image(gc_img, 12, 5, badge_rgb)
                except Exception as exc:
                    print(
                        f"Pillarium: titlebar badge failed: {exc}",
                        file=sys.stderr,
                    )

                # Draw window title
                title = frame_data.get("title", "Window")
                self._draw_text_pixels(
                    titlebar,
                    44,
                    10,
                    title[:40],
                    fg_hex,
                    bar_hex,
                    padding=1,
                )

                # Focused windows get an accent underline, matching the
                # focused-item highlight used on the taskbar
                if focused:
                    gc_accent = self._gc(
                        titlebar,
                        self.colors["accent"],
                        self.colors[bar_color],
                    )
                    titlebar.fill_rectangle(
                        gc_accent, 0, self.TITLEBAR_H - 2, width, 2
                    )

                # Draw bottom separator line (like taskbar)
                gc_line = self._gc(titlebar, self.colors["border"], self.colors[bar_color])
                titlebar.fill_rectangle(gc_line, 0, self.TITLEBAR_H - 1, width, 1)

                # Keep the control buttons on the same background as the bar
                self._draw_window_button(frame_data["close_button"], "close", bar_hex)
                self._draw_window_button(frame_data["maximize_button"], "maximize", bar_hex)
                self._draw_window_button(frame_data["minimize_button"], "minimize", bar_hex)

            elif window.id == frame_data["close_button"].id:
                # Draw close button with X
                self._draw_window_button(window, "close")
            elif window.id == frame_data["maximize_button"].id:
                # Draw maximize button with square
                self._draw_window_button(window, "maximize")
            elif window.id == frame_data["minimize_button"].id:
                # Draw minimize button with line
                self._draw_window_button(window, "minimize")

        except Exception as exc:
            print(f"Pillarium: window redraw failed: {exc}", file=sys.stderr)

    def _draw_window_button(self, window, button_type, bg_hex=None):
        """Draw window control buttons with rounded badges matching the taskbar."""
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return

        try:
            size = self.WINDOW_BTN_SIZE
            if bg_hex is None:
                bg_hex = self.current_palette.get("taskbar", "#071027")
            fg_hex = self.current_palette.get("text", "#e6eef8")
            accent_hex = self.current_palette.get("accent", "#f43f5e")
            active_hex = self.current_palette.get("taskbar_active", "#1f2937")

            bg_rgb = self._hex_to_rgb(bg_hex)
            fg_rgb = self._hex_to_rgb(fg_hex)
            accent_rgb = self._hex_to_rgb(accent_hex)
            active_rgb = self._hex_to_rgb(active_hex)

            # Create button image
            img = Image.new("RGB", (size, size), bg_rgb)
            draw = ImageDraw.Draw(img)
            pad = 1
            radius = max(4, size // 3)

            if button_type == "close":
                draw.rounded_rectangle(
                    (pad, pad, size - 1 - pad, size - 1 - pad),
                    radius=radius,
                    fill=accent_rgb,
                    outline=fg_rgb,
                    width=1,
                )
                # Draw X in white so it reads on the accent badge
                offset = 5
                glyph = (255, 255, 255)
                draw.line((offset, offset, size - offset - 1, size - offset - 1),
                          fill=glyph, width=2)
                draw.line((size - offset - 1, offset, offset, size - offset - 1),
                          fill=glyph, width=2)
            else:
                draw.rounded_rectangle(
                    (pad, pad, size - 1 - pad, size - 1 - pad),
                    radius=radius,
                    fill=active_rgb,
                    outline=fg_rgb,
                    width=1,
                )
                if button_type == "maximize":
                    # Draw square (maximize)
                    offset = 4
                    draw.rectangle((offset, offset, size - offset - 1, size - offset - 1),
                                   outline=fg_rgb, width=2)
                elif button_type == "minimize":
                    # Draw line (minimize)
                    offset = 4
                    draw.line((offset, size - offset - 1, size - offset - 1, size - offset - 1),
                              fill=fg_rgb, width=2)

            # Convert and draw
            gc = self._gc(window, self.colors["text"], self.colors["taskbar"])
            window.put_pil_image(gc, 0, 0, img)

        except Exception as exc:
            print(f"Pillarium: button draw failed: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Shared badge / pill helpers (taskbar + titlebar design language)
    # -----------------------------------------------------------------
    def _composite_rgba(self, rgba_image, bg):
        """Composite an RGBA image onto a solid background colour."""
        from PIL import Image

        if isinstance(bg, str):
            bg_rgb = self._hex_to_rgb(bg)
        else:
            bg_rgb = tuple(bg)
        rgb = Image.new("RGB", rgba_image.size, bg_rgb)
        rgb.paste(rgba_image, (0, 0), rgba_image)
        return rgb

    def _make_icon_badge(self, icon, glyph, bg_hex):
        """26x26 icon badge: real icon, or a letter fallback pill."""
        from PIL import Image, ImageDraw, ImageFont

        if icon is not None:
            try:
                rgba = icon.convert("RGBA")
                rgba.thumbnail((22, 22), Image.LANCZOS)
                canvas = Image.new("RGBA", (26, 26), (0, 0, 0, 0))
                canvas.alpha_composite(
                    rgba,
                    ((26 - rgba.width) // 2, (26 - rgba.height) // 2),
                )
                return canvas
            except Exception:
                pass

        active_hex = self.current_palette.get("taskbar_active", "#1f2937")
        fg_hex = self.current_palette.get("text", "#e6eef8")
        img = Image.new("RGBA", (26, 26), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (1, 1, 24, 24),
            radius=7,
            fill=self._hex_to_rgb(active_hex) + (255,),
            outline=self._hex_to_rgb(fg_hex) + (255,),
            width=1,
        )
        font = ImageFont.load_default()
        letter = (str(glyph)[:1] or "?").upper()
        try:
            bb = draw.textbbox((0, 0), letter, font=font)
            gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            gw, gh = 8, 10
        draw.text(
            ((26 - gw) // 2, (26 - gh) // 2),
            letter,
            fill=self._hex_to_rgb(fg_hex) + (255,),
            font=font,
        )
        return img
