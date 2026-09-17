"""Desktop window and icon drawing."""

import sys
from Xlib import X, Xatom


class DesktopMixin:
    # -----------------------------------------------------------------
    # Desktop window (so compositors can see the icons)
    # -----------------------------------------------------------------
    def _create_desktop_window(self):
        win = self.root.create_window(
            x=0,
            y=0,
            width=self.screen_w,
            height=self.screen_h,
            border_width=0,
            depth=0,
            window_class=X.InputOutput,
            visual=0,
            background_pixmap=0,
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.PointerMotionMask
                | X.EnterWindowMask
                | X.LeaveWindowMask
            ),
        )
        self._own_windows.add(win.id)

        # Tell EWMH‑aware compositors this is the desktop layer.
        try:
            net_wm_type = self.display.intern_atom("_NET_WM_WINDOW_TYPE")
            net_wm_type_desktop = self.display.intern_atom(
                "_NET_WM_WINDOW_TYPE_DESKTOP"
            )
            win.change_property(
                net_wm_type, Xatom.ATOM, 32, [net_wm_type_desktop]
            )
        except Exception as exc:
            print(
                f"Pillarium: could not set desktop window type hint: {exc}",
                file=sys.stderr,
            )

        try:
            win.map()
            win.configure(stack_mode=X.Below)
        except Exception as exc:
            print(
                f"Pillarium: desktop window map/stack failed: {exc}",
                file=sys.stderr,
            )

        try:
            self._apply_wallpaper_to_desktop(win)
        except Exception as exc:
            print(
                f"Pillarium: desktop wallpaper apply failed: {exc}",
                file=sys.stderr,
            )

        self.display.flush()
        return win

    def _init_desktop(self):
        # Desktop window (so compositors can see the icons)
        self.desktop_win = self._create_desktop_window()

        # Desktop‑icon interaction state
        self.desktop_icon_size = 64
        self.desktop_icon_gap = 24
        self.desktop_icon_start = (24, 24)
        self._desktop_selected = None
        self._desktop_last_click = {"idx": None, "time": 0.0}
        self._titlebar_last_click = {"client_id": None, "time": 0.0}

    def _desktop_cell_rects(self):
        cell_w = self.desktop_icon_size + self.desktop_icon_gap
        cell_h = self.desktop_icon_size + self.desktop_icon_gap + 18
        start_x, start_y = self.desktop_icon_start
        usable_h = max(cell_h, self.screen_h - self.TASKBAR_H - start_y)
        rows_per_col = max(1, usable_h // cell_h)
        rects = []
        for idx in range(len(self.desktop_icons)):
            col = idx // rows_per_col
            row = idx % rows_per_col
            x = start_x + col * cell_w
            y = start_y + row * cell_h
            rects.append((x, y, self.desktop_icon_size, self.desktop_icon_size))
        return rects

    def _desktop_icon_at(self, px, py):
        for idx, (x, y, w, h) in enumerate(self._desktop_cell_rects()):
            if x <= px <= x + w and (y - 4) <= py <= (y + h + 20):
                return idx
        return None

    def _put_desktop_rgba(self, window, x, y, image):
        try:
            px = image.convert("RGBA").load()
            if not hasattr(self, "_desktop_icon_color_cache"):
                self._desktop_icon_color_cache = {}
            for yy in range(image.height):
                for xx in range(image.width):
                    r, g, b, a = px[xx, yy]
                    if a < 32:
                        continue
                    key = (r, g, b)
                    pixel = self._desktop_icon_color_cache.get(key)
                    if pixel is None:
                        pixel = self._alloc_color(
                            f"#{r:02x}{g:02x}{b:02x}",
                            self.colors["text"],
                        )
                        self._desktop_icon_color_cache[key] = pixel
                    gc = self._gc(window, pixel, self.colors["surface"])
                    window.fill_rectangle(gc, x + xx, y + yy, 1, 1)
            return True
        except Exception as exc:
            print(
                f"Pillarium: desktop icon pixel renderer failed: {exc}",
                file=sys.stderr,
            )
            return False

    def _draw_desktop_icon_fallback(self, window, x, y, size, label, selected=False, hovered=False):
        try:
            from PIL import Image, ImageDraw, ImageFont

            # Use Cadet theme colors
            panel_hex = self.current_palette.get("panel", "#2c313a")
            panel_line_hex = self.current_palette.get("panel_line", "#171a1f")
            text_hex = self.current_palette.get("text", "#d8dee9")
            text_dim_hex = self.current_palette.get("text_dim", "#8b93a3")
            text_faint_hex = self.current_palette.get("text_faint", "#646c7a")
            accent_hex = self.current_palette.get("accent", "#5e81ac")
            accent_hot_hex = self.current_palette.get("accent_hot", "#81a1c1")
            select_hex = self.current_palette.get("select", "#4c566a")
            select_foc_hex = self.current_palette.get("select_foc", "#3b4659")
            row_hover_hex = self.current_palette.get("row_hover", "#343b47")
            row_alt_hex = self.current_palette.get("row_alt", "#262b33")

            panel_rgb = self._hex_to_rgb(panel_hex)
            panel_line_rgb = self._hex_to_rgb(panel_line_hex)
            text_rgb = self._hex_to_rgb(text_hex)
            text_dim_rgb = self._hex_to_rgb(text_dim_hex)
            accent_rgb = self._hex_to_rgb(accent_hex)
            accent_hot_rgb = self._hex_to_rgb(accent_hot_hex)
            select_rgb = self._hex_to_rgb(select_hex)
            select_foc_rgb = self._hex_to_rgb(select_foc_hex)
            row_hover_rgb = self._hex_to_rgb(row_hover_hex)
            row_alt_rgb = self._hex_to_rgb(row_alt_hex)

            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            # Cadet-style icon background
            bg_color = select_foc_rgb if selected else (row_hover_rgb if hovered else panel_rgb)
            outline_color = accent_hot_rgb if selected else (text_dim_rgb if hovered else panel_line_rgb)
            draw.rounded_rectangle(
                (1, 1, size - 2, size - 2),
                radius=14,
                fill=bg_color + (235,),
                outline=outline_color,
                width=3 if (selected or hovered) else 2,
            )
            font = ImageFont.load_default()
            glyph = (label[:1] or "?").upper()
            try:
                bb = draw.textbbox((0, 0), glyph, font=font)
                gw, gh = bb[2] - bb[0], bb[3] - bb[1]
            except Exception:
                gw, gh = 8, 10
            draw.text(
                ((size - gw) // 2, (size - gh) // 2),
                glyph,
                fill=(255, 255, 255, 255),
                font=font,
            )
            return self._put_desktop_rgba(window, x, y, img)
        except Exception:
            return False

    def _redraw_desktop_icons(self):
        try:
            from PIL import Image, ImageDraw
        except Exception as exc:
            print(
                f"Pillarium: Pillow unavailable for desktop icons: {exc}",
                file=sys.stderr,
            )
            return
        try:
            # Use Cadet theme colors
            panel_hex = self.current_palette.get("panel", "#2c313a")
            panel_line_hex = self.current_palette.get("panel_line", "#171a1f")
            text_hex = self.current_palette.get("text", "#d8dee9")
            text_dim_hex = self.current_palette.get("text_dim", "#8b93a3")
            accent_hex = self.current_palette.get("accent", "#5e81ac")
            accent_hot_hex = self.current_palette.get("accent_hot", "#81a1c1")
            select_hex = self.current_palette.get("select", "#4c566a")
            select_foc_hex = self.current_palette.get("select_foc", "#3b4659")
            row_hover_hex = self.current_palette.get("row_hover", "#343b47")
            row_alt_hex = self.current_palette.get("row_alt", "#262b33")

            panel_rgb = self._hex_to_rgb(panel_hex)
            panel_line_rgb = self._hex_to_rgb(panel_line_hex)
            text_rgb = self._hex_to_rgb(text_hex)
            text_dim_rgb = self._hex_to_rgb(text_dim_hex)
            accent_rgb = self._hex_to_rgb(accent_hex)
            accent_hot_rgb = self._hex_to_rgb(accent_hot_hex)
            select_rgb = self._hex_to_rgb(select_hex)
            select_foc_rgb = self._hex_to_rgb(select_foc_hex)
            row_hover_rgb = self._hex_to_rgb(row_hover_hex)
            row_alt_rgb = self._hex_to_rgb(row_alt_hex)

            try:
                self.desktop_win.clear_area(0, 0, self.screen_w, self.screen_h)
            except Exception:
                pass

            for idx, (x, y, w, h) in enumerate(self._desktop_cell_rects()):
                item = self.desktop_icons[idx]
                selected = self._desktop_selected == idx
                hovered = getattr(self, "_desktop_hover", None) == idx
                size = w + (6 if hovered else 0)
                bx = x - (size - w) // 2
                by = y - (size - w) // 2
                icon = self._load_icon(item.get("icon"), size)

                if icon is not None:
                    # Use Cadet panel color for icon background
                    canvas = Image.new("RGB", (size, size), panel_rgb)
                    rgba = icon.convert("RGBA")
                    canvas.paste(rgba, ((size - rgba.width) // 2, (size - rgba.height) // 2), rgba)
                    gc = self._gc(
                        self.desktop_win,
                        self.colors["text"],
                        self.colors["surface"],
                    )
                    try:
                        self.desktop_win.put_pil_image(gc, bx, by, canvas)
                    except Exception as exc:
                        self._draw_desktop_icon_fallback(
                            self.desktop_win, bx, by, size, item.get("label", "?"), selected, hovered
                        )
                else:
                    self._draw_desktop_icon_fallback(
                        self.desktop_win, bx, by, size, item.get("label", "?"), selected, hovered
                    )

                label = str(item.get("label", "?"))[:14]
                self._draw_text_pixels(
                    self.desktop_win,
                    x - 4,
                    y + h + 2,
                    label,
                    text_hex,
                    panel_hex,
                    padding=1,
                )
            self.display.flush()
        except Exception as exc:
            print(f"Pillarium: desktop icon redraw failed: {exc}", file=sys.stderr)
