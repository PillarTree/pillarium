"""Clock widget menu: calendar panel."""

import calendar
import datetime
import sys
from Xlib import X

CAL_W = 280
CAL_HEADER_H = 40
CAL_WEEK_H = 24
CAL_DAY_H = 32
CAL_FOOTER_H = 44
CAL_CELL_X0 = 14
CAL_CELL_W = 36


class ClockMixin:
    def _init_clock(self):
        self.clock_state = None

    # -----------------------------------------------------------------
    # Calendar panel (the clock's menu)
    # -----------------------------------------------------------------
    def _toggle_clock_menu(self, anchor_x):
        if getattr(self, "clock_state", None):
            self._close_clock_menu()
            return
        self._close_active_menu()
        self._close_confirm_dialog()
        self._close_processes()

        today = datetime.date.today()
        height = CAL_HEADER_H + CAL_WEEK_H + 6 * CAL_DAY_H + CAL_FOOTER_H
        x = max(
            0,
            min(self.screen_w - CAL_W, anchor_x + self.CLOCK_W - CAL_W),
        )
        y = max(0, self.screen_h - self.TASKBAR_H - height)
        win = self._create_window(
            self.root,
            x,
            y,
            CAL_W,
            height,
            self.colors["surface"],
            self.colors["border"],
            override_redirect=True,
        )
        self._own_windows.add(win.id)
        win.change_attributes(
            background_pixel=self.colors["surface"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.KeyPressMask
            ),
        )
        win.map()
        try:
            win.configure(stack_mode=X.Above)
        except Exception:
            pass
        self.clock_state = {
            "window": win,
            "x": x,
            "y": y,
            "width": CAL_W,
            "height": height,
            "year": today.year,
            "month": today.month,
            "selected": today.day,
            "header_h": CAL_HEADER_H,
            "week_h": CAL_WEEK_H,
            "day_h": CAL_DAY_H,
            "cell_x0": CAL_CELL_X0,
            "cell_w": CAL_CELL_W,
            "prev_rect": None,
            "next_rect": None,
            "open_rect": None,
        }
        try:
            self.display.set_input_focus(win, X.RevertToParent, X.CurrentTime)
        except Exception:
            pass
        self._redraw_clock_menu()
        self._redraw_taskbar()
        self.display.flush()

    def _close_clock_menu(self):
        st = getattr(self, "clock_state", None)
        if not st:
            return
        win = st.get("window")
        if win is not None:
            try:
                self._own_windows.discard(win.id)
                win.destroy()
            except Exception:
                pass
        self.clock_state = None
        try:
            if self.focused_client in self.frames:
                self.display.set_input_focus(
                    self.frames[self.focused_client]["client"],
                    X.RevertToParent,
                    X.CurrentTime,
                )
            else:
                self.display.set_input_focus(
                    self.root, X.RevertToParent, X.CurrentTime
                )
        except Exception:
            pass
        self._redraw_taskbar()
        self.display.flush()

    def _cal_arrow(self, surface_rgb, text_rgb, right=False):
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return None
        img = Image.new("RGB", (24, 24), surface_rgb)
        d = ImageDraw.Draw(img)
        if right:
            d.polygon([(9, 6), (9, 18), (18, 12)], fill=text_rgb)
        else:
            d.polygon([(15, 6), (15, 18), (6, 12)], fill=text_rgb)
        return img

    def _redraw_clock_menu(self):
        st = getattr(self, "clock_state", None)
        if not st or not st.get("window"):
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return

        win = st["window"]
        w = st["width"]
        h = st["height"]
        surface_hex = self.current_palette.get("surface", "#000000")
        text_hex = self.current_palette.get("text", "#ffffff")
        dim_hex = self.current_palette.get("titlebar_alt", "#888888")
        accent_hex = self.current_palette.get("accent", "#f43f5e")
        surface_rgb = self._hex_to_rgb(surface_hex)
        text_rgb = self._hex_to_rgb(text_hex)
        dim_rgb = self._hex_to_rgb(dim_hex)
        accent_rgb = self._hex_to_rgb(accent_hex)

        gc_bg = self._gc(win, self.colors["surface"], self.colors["surface"])
        win.fill_rectangle(gc_bg, 0, 0, w, h)

        year, month = st["year"], st["month"]
        self._draw_text_pixels(
            win,
            14,
            12,
            f"{calendar.month_name[month]} {year}"[:24],
            text_hex,
            surface_hex,
            padding=1,
        )

        gc = self._gc(win, self.colors["text"], self.colors["surface"])
        prev_arrow = self._cal_arrow(surface_rgb, text_rgb, right=False)
        next_arrow = self._cal_arrow(surface_rgb, text_rgb, right=True)
        prev_x0, prev_y0 = w - 64, 8
        next_x0, next_y0 = w - 36, 8
        if prev_arrow is not None:
            win.put_pil_image(gc, prev_x0, prev_y0, prev_arrow)
        if next_arrow is not None:
            win.put_pil_image(gc, next_x0, next_y0, next_arrow)
        st["prev_rect"] = (prev_x0, prev_y0, prev_x0 + 24, prev_y0 + 24)
        st["next_rect"] = (next_x0, next_y0, next_x0 + 24, next_y0 + 24)

        week_start_y = st["header_h"]
        gc_line = self._gc(win, self.colors["border"], self.colors["surface"])
        win.fill_rectangle(gc_line, 0, week_start_y + st["week_h"] - 1, w, 1)
        for col in range(7):
            cx = st["cell_x0"] + col * st["cell_w"]
            self._draw_text_pixels(
                win,
                cx + 15,
                week_start_y + 6,
                ["S", "M", "T", "W", "T", "F", "S"][col],
                dim_hex,
                surface_hex,
                padding=1,
            )

        weeks = calendar.monthcalendar(year, month)
        today = datetime.date.today()
        grid_y0 = week_start_y + st["week_h"]
        font = ImageFont.load_default()
        for row in range(6):
            for col in range(7):
                day = weeks[row][col] if row < len(weeks) else 0
                if not day:
                    continue
                cx = st["cell_x0"] + col * st["cell_w"]
                cy = grid_y0 + row * st["day_h"]
                is_today = (
                    day == today.day
                    and month == today.month
                    and year == today.year
                )
                is_selected = (
                    day == st.get("selected")
                    and month == st["month"]
                    and year == st["year"]
                )
                cell = Image.new(
                    "RGB",
                    (st["cell_w"] - 4, st["day_h"] - 4),
                    surface_rgb,
                )
                cd = ImageDraw.Draw(cell)
                if is_today:
                    cd.rounded_rectangle(
                        (2, 2, st["cell_w"] - 6, st["day_h"] - 6),
                        radius=8,
                        fill=accent_rgb,
                    )
                    txt_fill = surface_rgb
                elif is_selected:
                    cd.rounded_rectangle(
                        (2, 2, st["cell_w"] - 6, st["day_h"] - 6),
                        radius=8,
                        outline=accent_rgb,
                        width=1,
                    )
                    txt_fill = text_rgb
                else:
                    txt_fill = text_rgb
                try:
                    bb = cd.textbbox((0, 0), str(day), font=font)
                    tw, th = bb[2] - bb[0], bb[3] - bb[1]
                except Exception:
                    tw, th = cd.textsize(str(day), font=font)
                cd.text(
                    ((st["cell_w"] - 4 - tw) // 2, (st["day_h"] - 4 - th) // 2),
                    str(day),
                    fill=txt_fill,
                    font=font,
                )
                win.put_pil_image(gc, cx + 2, cy + 2, cell)

        footer_y = h - CAL_FOOTER_H
        win.fill_rectangle(gc_line, 0, footer_y, w, 1)
        btn_w, btn_h = 176, 28
        btn_x, btn_y = 14, footer_y + (CAL_FOOTER_H - btn_h) // 2
        btn_img = Image.new("RGB", (btn_w, btn_h), surface_rgb)
        bd = ImageDraw.Draw(btn_img)
        bd.rounded_rectangle(
            (0, 0, btn_w - 1, btn_h - 1),
            radius=6,
            fill=accent_rgb,
        )
        try:
            bb = bd.textbbox((0, 0), "Open Process Manager", font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            tw, th = bd.textsize("Open Process Manager", font=font)
        bd.text(
            ((btn_w - tw) // 2, (btn_h - th) // 2),
            "Open Process Manager",
            fill=surface_rgb,
            font=font,
        )
        win.put_pil_image(gc, btn_x, btn_y, btn_img)
        st["open_rect"] = (btn_x, btn_y, btn_x + btn_w, btn_y + btn_h)
        self._draw_text_pixels(
            win,
            w - 92,
            footer_y + 15,
            "Esc to close",
            dim_hex,
            surface_hex,
            padding=1,
        )
        self.display.flush()

    def _cal_navigate(self, delta):
        st = getattr(self, "clock_state", None)
        if not st:
            return
        month = st["month"] + delta
        year = st["year"]
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        st["month"], st["year"] = month, year
        self._redraw_clock_menu()

    def _handle_clock_click(self, event):
        st = getattr(self, "clock_state", None)
        if not st:
            return
        if getattr(event, "detail", None) in (4, 5):
            self._cal_navigate(-1 if event.detail == 4 else 1)
            return
        x, y = event.event_x, event.event_y
        px0, py0, px1, py1 = st.get("prev_rect") or (0, 0, 0, 0)
        if px0 <= x < px1 and py0 <= y < py1:
            self._cal_navigate(-1)
            return
        nx0, ny0, nx1, ny1 = st.get("next_rect") or (0, 0, 0, 0)
        if nx0 <= x < nx1 and ny0 <= y < ny1:
            self._cal_navigate(1)
            return
        fx0, fy0, fx1, fy1 = st.get("open_rect") or (0, 0, 0, 0)
        if fx0 <= x < fx1 and fy0 <= y < fy1:
            self._close_clock_menu()
            self._open_processes()
            return
        grid_y0 = st["header_h"] + st["week_h"]
        if grid_y0 <= y < grid_y0 + 6 * st["day_h"]:
            col = (x - st["cell_x0"]) // st["cell_w"]
            row = (y - grid_y0) // st["day_h"]
            if 0 <= col < 7 and 0 <= row < 6:
                weeks = calendar.monthcalendar(st["year"], st["month"])
                if row < len(weeks):
                    day = weeks[row][col]
                    if day:
                        st["selected"] = day
                        self._redraw_clock_menu()