"""Window-decoration drawing: titlebars, control buttons, icon badges."""

import sys


class DecorationMixin:
    def _redraw_window(self, window):
        """Redraw window decorations to match taskbar aesthetic (Cadet style)."""
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

                # Use Cadet theme colors
                panel_hex = self.current_palette.get("panel", "#2c313a")
                panel_line_hex = self.current_palette.get("panel_line", "#171a1f")
                text_hex = self.current_palette.get("text", "#d8dee9")
                text_dim_hex = self.current_palette.get("text_dim", "#8b93a3")
                accent_hex = self.current_palette.get("accent", "#5e81ac")
                accent_hot_hex = self.current_palette.get("accent_hot", "#81a1c1")
                select_hex = self.current_palette.get("select", "#4c566a")
                select_foc_hex = self.current_palette.get("select_foc", "#3b4659")

                panel_rgb = self._hex_to_rgb(panel_hex)
                panel_line_rgb = self._hex_to_rgb(panel_line_hex)
                text_rgb = self._hex_to_rgb(text_hex)
                text_dim_rgb = self._hex_to_rgb(text_dim_hex)
                accent_rgb = self._hex_to_rgb(accent_hex)
                accent_hot_rgb = self._hex_to_rgb(accent_hot_hex)
                select_rgb = self._hex_to_rgb(select_hex)
                select_foc_rgb = self._hex_to_rgb(select_foc_hex)

                # Focused windows use the SELECT_FOC color (like Cadet's focused selection)
                focused = frame_client_id == self.focused_client
                bar_hex = select_foc_hex if focused else panel_hex
                bar_rgb = select_foc_rgb if focused else panel_rgb
                bar_outline = accent_hot_rgb if focused else panel_line_rgb

                # Clear titlebar
                gc = self._gc(
                    titlebar,
                    self.colors["taskbar"],
                    self.colors["taskbar"],
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
                        self.colors["taskbar"],
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
                    text_hex,
                    bar_hex,
                    padding=1,
                )

                # Focused windows get an accent underline (Cadet style)
                if focused:
                    gc_accent = self._gc(
                        titlebar,
                        self.colors["accent"],
                        self.colors["taskbar"],
                    )
                    titlebar.fill_rectangle(
                        gc_accent, 0, self.TITLEBAR_H - 2, width, 2
                    )

                # Draw bottom separator line (like Cadet's PANEL_LINE)
                gc_line = self._gc(titlebar, self.colors["border"], self.colors["taskbar"])
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
        """Draw window control buttons with rounded badges matching the taskbar (Cadet style)."""
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return

        try:
            size = self.WINDOW_BTN_SIZE
            # Use Cadet theme colors
            panel_hex = self.current_palette.get("panel", "#2c313a")
            text_hex = self.current_palette.get("text", "#d8dee9")
            accent_hex = self.current_palette.get("accent", "#5e81ac")
            accent_hot_hex = self.current_palette.get("accent_hot", "#81a1c1")
            select_hex = self.current_palette.get("select", "#4c566a")

            if bg_hex is None:
                bg_hex = panel_hex

            panel_rgb = self._hex_to_rgb(panel_hex)
            text_rgb = self._hex_to_rgb(text_hex)
            accent_rgb = self._hex_to_rgb(accent_hex)
            accent_hot_rgb = self._hex_to_rgb(accent_hot_hex)
            select_rgb = self._hex_to_rgb(select_hex)
            bg_rgb = self._hex_to_rgb(bg_hex)

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
                    outline=text_rgb,
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
                    fill=select_rgb,
                    outline=text_rgb,
                    width=1,
                )
                if button_type == "maximize":
                    # Draw square (maximize)
                    offset = 4
                    draw.rectangle((offset, offset, size - offset - 1, size - offset - 1),
                                   outline=text_rgb, width=2)
                elif button_type == "minimize":
                    # Draw line (minimize)
                    offset = 4
                    draw.line((offset, size - offset - 1, size - offset - 1, size - offset - 1),
                              fill=text_rgb, width=2)

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
        """26x26 icon badge: real icon, or a letter fallback pill (Cadet style)."""
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

        # Use Cadet theme colors
        panel_hex = self.current_palette.get("panel", "#2c313a")
        text_hex = self.current_palette.get("text", "#d8dee9")
        select_hex = self.current_palette.get("select", "#4c566a")

        panel_rgb = self._hex_to_rgb(panel_hex)
        text_rgb = self._hex_to_rgb(text_hex)
        select_rgb = self._hex_to_rgb(select_hex)

        img = Image.new("RGBA", (26, 26), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (1, 1, 24, 24),
            radius=7,
            fill=tuple(select_rgb) + (255,),
            outline=tuple(text_rgb) + (255,),
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
            fill=tuple(text_rgb) + (255,),
            font=font,
        )
        return img
