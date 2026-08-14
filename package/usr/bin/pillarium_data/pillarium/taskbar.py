"""Task‑bar creation, hit‑testing and rendering."""

import os
import sys
from Xlib import X


class TaskbarMixin:
    def _init_taskbar(self):
        # Task‑bar state
        self.TASKBAR_H = 36
        self.taskbar_items = []  # ordered list of client ids
        self._gc_cache = {}
        self._last_clock = None
        self.taskbar = self._create_taskbar()

    # -----------------------------------------------------------------
    # Task‑bar creation
    # -----------------------------------------------------------------
    def _create_taskbar(self):
        tb = self._create_window(
            self.root,
            0,
            self.screen_h - self.TASKBAR_H,
            self.screen_w,
            self.TASKBAR_H,
            self.colors["taskbar"],
            self.colors["border"],
            override_redirect=self.taskbar_override,
        )
        self._own_windows.add(tb.id)
        tb.change_attributes(
            background_pixel=self.colors["taskbar"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ButtonPressMask
                | X.ExposureMask
                | X.PointerMotionMask
                | X.EnterWindowMask
                | X.LeaveWindowMask
            ),
        )
        try:
            tb.map()
        except Exception as exc:
            print(f"Pillarium: taskbar.map failed: {exc}", file=sys.stderr)
        try:
            tb.configure(stack_mode=X.Above)
        except Exception as exc:
            print(
                f"Pillarium: taskbar.configure(stack_mode=Above) failed: {exc}",
                file=sys.stderr,
            )
        self.taskbar = tb
        print(
            f"Pillarium: taskbar created at y={self.screen_h - self.TASKBAR_H}, override_redirect={self.taskbar_override}",
            file=sys.stderr,
        )
        self._redraw_taskbar()
        try:
            self.display.flush()
        except Exception as exc:
            print(
                f"Pillarium: display.flush failed after taskbar creation: {exc}",
                file=sys.stderr,
            )
        return tb

    # -----------------------------------------------------------------
    # Verify task‑bar geometry (re‑create if something went wrong)
    # -----------------------------------------------------------------
    def _verify_taskbar(self):
        tb = getattr(self, "taskbar", None)
        if tb is None:
            print(
                "Pillarium: no taskbar found during verify, recreating",
                file=sys.stderr,
            )
            self.taskbar = self._create_taskbar()
            return
        try:
            geom = tb.get_geometry()
            width = getattr(geom, "width", None)
            height = getattr(geom, "height", None)
            y = getattr(geom, "y", None)
            if (
                width != self.screen_w
                or height != self.TASKBAR_H
                or y != self.screen_h - self.TASKBAR_H
            ):
                print(
                    f"Pillarium: taskbar geometry invalid width={width} height={height} y={y}, recreating",
                    file=sys.stderr,
                )
                try:
                    tb.destroy()
                except Exception:
                    pass
                self.taskbar = self._create_taskbar()
                return
        except Exception as exc:
            print(f"Pillarium: taskbar.get_geometry failed: {exc}", file=sys.stderr)
            try:
                tb.destroy()
            except Exception:
                pass
            self.taskbar = self._create_taskbar()
            return
        try:
            tb.configure(
                x=0,
                y=self.screen_h - self.TASKBAR_H,
                width=self.screen_w,
                height=self.TASKBAR_H,
                stack_mode=X.Above,
            )
            print("Pillarium: taskbar reconfigured for verify", file=sys.stderr)
        except Exception as exc:
            print(
                f"Pillarium: taskbar configure during verify failed: {exc}",
                file=sys.stderr,
            )
        try:
            if hasattr(tb, "raise_window"):
                tb.raise_window()
                print(
                    "Pillarium: taskbar raise_window during verify succeeded",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(
                f"Pillarium: taskbar raise_window during verify failed: {exc}",
                file=sys.stderr,
            )
        try:
            tb.map()
            print("Pillarium: taskbar mapped during verify", file=sys.stderr)
        except Exception as exc:
            print(
                f"Pillarium: taskbar map during verify failed: {exc}",
                file=sys.stderr,
            )
        self._ensure_taskbar_on_top()

    # -----------------------------------------------------------------
    # Determine what kind of item is under a task‑bar x‑coordinate
    # -----------------------------------------------------------------
    def _taskbar_hit_kind(self, x):
        right_zone_start = self.screen_w - self._taskbar_right_zone_w()
        if x < self.SEARCH_W:
            return "search"
        if x >= right_zone_start:
            custom_widgets_x = right_zone_start
            power_x = custom_widgets_x + (len(self.custom_widgets) * self.CUSTOM_WIDGET_W)
            bluetooth_x = power_x + self.POWER_W
            audio_x = bluetooth_x + self.BLUETOOTH_W
            wifi_x = audio_x + self.AUDIO_W
            battery_x = wifi_x + self.WIFI_W
            clock_x = battery_x + self.BATTERY_W
            if x < power_x:
                return "widget"
            if power_x <= x < bluetooth_x:
                return "power"
            if bluetooth_x <= x < audio_x:
                return "bluetooth"
            if audio_x <= x < wifi_x:
                return "audio"
            if wifi_x <= x < battery_x:
                return "wifi"
            if battery_x <= x < clock_x:
                return "battery"
            return "clock"
        q_start = self.SEARCH_W
        q_width = self._taskbar_quick_launch_w()
        if x < q_start + q_width:
            idx = (x - q_start) // 48
            return "quick_launch" if 0 <= idx < len(self.quick_launch) else None
        area_x = q_start + q_width
        items_area_w = max(96, right_zone_start - area_x)
        count = max(1, len(self.taskbar_items))
        item_w = max(96, items_area_w // count)
        idx = (x - area_x) // item_w
        return "item" if 0 <= idx < len(self.taskbar_items) else None

    # -----------------------------------------------------------------
    # Precise task‑bar hit‑test (returns the client‑id under the x‑coordinate)
    # -----------------------------------------------------------------
    def _taskbar_item_at(self, x):
        right_zone_start = self.screen_w - self._taskbar_right_zone_w()
        q_start = self.SEARCH_W
        q_width = self._taskbar_quick_launch_w()
        area_x = q_start + q_width
        items_area_w = max(96, right_zone_start - area_x)
        count = max(1, len(self.taskbar_items))
        item_w = max(96, items_area_w // count)
        idx = (x - area_x) // item_w
        if 0 <= idx < len(self.taskbar_items):
            return self.taskbar_items[idx]
        return None

    def _taskbar_right_zone_w(self):
        return (
            self.POWER_W
            + self.BLUETOOTH_W
            + self.AUDIO_W
            + self.WIFI_W
            + self.BATTERY_W
            + self.CLOCK_W
            + (len(self.custom_widgets) * self.CUSTOM_WIDGET_W)
        )

    def _taskbar_quick_launch_w(self):
        return len(self.quick_launch) * 48

    def _is_app_running(self, item):
        """True when a quick-launch item matches an open taskbar window."""
        label = str(item.get("label", "")).strip().lower()
        cmd0 = os.path.basename(str((item.get("cmd") or [""])[0])).lower()
        for client_id in self.taskbar_items:
            data = self.frames.get(client_id)
            if not data:
                continue
            if str(data.get("title", "")).strip().lower() == label:
                return True
            if cmd0 and cmd0 in set(data.get("wm_class", [])):
                return True
        return False

    def _redraw_taskbar(self):
        """Draw taskbar buttons with real icons, labels, and widgets."""
        if not getattr(self, "taskbar", None):
            return

        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return

        try:
            tb = self.taskbar
            bg_hex = self.current_palette.get(
                "taskbar", "#071027"
            )
            active_hex = self.current_palette.get(
                "taskbar_active", "#1f2937"
            )
            fg_hex = self.current_palette.get(
                "text", "#e6eef8"
            )
            border_hex = self.current_palette.get(
                "border", "#0f172a"
            )
            accent_hex = self.current_palette.get(
                "accent", "#f43f5e"
            )

            bg_rgb = self._hex_to_rgb(bg_hex)
            active_rgb = self._hex_to_rgb(active_hex)
            fg_rgb = self._hex_to_rgb(fg_hex)
            border_rgb = self._hex_to_rgb(border_hex)
            accent_rgb = self._hex_to_rgb(accent_hex)

            gc = self._gc(
                tb,
                self.colors["taskbar"],
                self.colors["taskbar"],
            )
            tb.fill_rectangle(
                gc,
                0,
                0,
                self.screen_w,
                self.TASKBAR_H,
            )

            def put_pil(img, x, y, background=None):
                try:
                    rgba = img.convert("RGBA")
                    bg = (
                        background
                        if background is not None
                        else bg_rgb
                    )
                    rgb = Image.new(
                        "RGB",
                        rgba.size,
                        bg,
                    )
                    rgb.paste(
                        rgba,
                        (0, 0),
                        rgba,
                    )
                    gc_img = self._gc(
                        tb,
                        self.colors["text"],
                        self.colors["taskbar"],
                    )
                    tb.put_pil_image(
                        gc_img,
                        int(x),
                        int(y),
                        rgb,
                    )
                    return True
                except Exception:
                    return False

            def draw_text(
                x,
                y,
                value,
                max_chars=32,
                background=None,
            ):
                return self._draw_text_pixels(
                    tb,
                    int(x),
                    int(y),
                    str(value)[:max_chars],
                    fg_hex,
                    background
                    or bg_hex,
                    padding=1,
                )

            # Search button (pill badge; highlighted while the launcher is open).
            search_img = Image.new(
                "RGB",
                (
                    self.SEARCH_W,
                    self.TASKBAR_H,
                ),
                bg_rgb,
            )
            sd = ImageDraw.Draw(search_img)
            search_open = getattr(self, "search_state", None) is not None
            sd.rounded_rectangle(
                (3, 5, self.SEARCH_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=active_rgb if search_open else bg_rgb,
                outline=accent_rgb if search_open else fg_rgb,
                width=1,
            )
            cx, cy = 15, 15
            sd.ellipse(
                (
                    cx - 6,
                    cy - 6,
                    cx + 5,
                    cy + 5,
                ),
                outline=fg_rgb,
                width=2,
            )
            sd.line(
                (
                    cx + 4,
                    cy + 4,
                    cx + 10,
                    cy + 10,
                ),
                fill=fg_rgb,
                width=2,
            )
            put_pil(search_img, 0, 0)

            # Quick launch (pill buttons matching the open-application items).
            q_start = self.SEARCH_W
            q_width = self._taskbar_quick_launch_w()
            button_w = 48

            for i, item in enumerate(
                self.quick_launch
            ):
                x = q_start + i * button_w

                running = self._is_app_running(item)
                pill_fill = active_rgb if running else bg_rgb

                btn = Image.new(
                    "RGB",
                    (button_w, self.TASKBAR_H),
                    bg_rgb,
                )
                bd = ImageDraw.Draw(btn)
                bd.rounded_rectangle(
                    (2, 5, button_w - 2, self.TASKBAR_H - 5),
                    radius=13,
                    fill=pill_fill,
                    outline=accent_rgb if running else fg_rgb,
                    width=1,
                )
                if running:
                    bd.ellipse(
                        (
                            button_w // 2 - 2,
                            self.TASKBAR_H - 5,
                            button_w // 2 + 2,
                            self.TASKBAR_H - 1,
                        ),
                        fill=accent_rgb,
                    )
                put_pil(btn, x, 0)

                badge = self._make_icon_badge(
                    self._load_icon(item.get("icon"), 24),
                    item.get("label", "?"),
                    bg_hex,
                )
                try:
                    badge_rgb = self._composite_rgba(badge, pill_fill)
                    put_pil(
                        badge_rgb,
                        x + (button_w - badge_rgb.width) // 2,
                        5 + (26 - badge_rgb.height) // 2,
                        background=bg_rgb,
                    )
                except Exception as exc:
                    print(
                        "Pillarium: quick launch badge "
                        f"render failed: {exc}",
                        file=sys.stderr,
                    )

            # Managed windows.
            area_x = q_start + q_width
            right_zone_start = (
                self.screen_w - self._taskbar_right_zone_w()
            )
            items_area_w = max(
                0,
                right_zone_start - area_x,
            )

            if self.taskbar_items:
                item_w = max(
                    96,
                    items_area_w
                    // len(self.taskbar_items),
                )

                for i, client_id in enumerate(
                    self.taskbar_items
                ):
                    data = self.frames.get(
                        client_id
                    )
                    if not data:
                        continue

                    x = area_x + i * item_w
                    width = min(
                        item_w,
                        right_zone_start - x,
                    )
                    if width <= 0:
                        continue

                    active = (
                        self.focused_client
                        == client_id
                    )
                    row_rgb = (
                        active_rgb
                        if active
                        else bg_rgb
                    )

                    row = Image.new(
                        "RGB",
                        (width, self.TASKBAR_H),
                        row_rgb,
                    )
                    rd = ImageDraw.Draw(row)
                    rd.rounded_rectangle(
                        (3, 5, width - 3, self.TASKBAR_H - 5),
                        radius=13,
                        fill=row_rgb,
                        outline=accent_rgb if active else fg_rgb,
                        width=1,
                    )
                    if active:
                        rd.rectangle(
                            (3, 3, width - 3, 5),
                            fill=accent_rgb,
                        )
                    put_pil(row, x, 0)

                    badge = self._make_icon_badge(
                        self._resolve_taskbar_icon(data),
                        data.get("title", "?"),
                        bg_hex,
                    )
                    try:
                        badge_rgb = self._composite_rgba(
                            badge, row_rgb
                        )
                        put_pil(
                            badge_rgb,
                            x + 6,
                            5,
                            background=row_rgb,
                        )
                    except Exception as exc:
                        print(
                            "Pillarium: taskbar icon "
                            f"render failed for {client_id}: {exc}",
                            file=sys.stderr,
                        )

                    text_x = x + 38
                    max_chars = max(
                        8,
                        int(
                            max(
                                40,
                                width
                                - (text_x - x)
                                - 6,
                            )
                            / 7
                        ),
                    )
                    draw_text(
                        text_x,
                        10,
                        data.get(
                            "title",
                            "Window",
                        ),
                        max_chars=max_chars,
                        background=(
                            active_hex
                            if active
                            else bg_hex
                        ),
                    )

            # Custom widgets.
            custom_x = right_zone_start
            for idx, widget in enumerate(self.custom_widgets):
                x = custom_x + idx * self.CUSTOM_WIDGET_W
                value = widget.get("text") or widget.get("label", "Widget")
                draw_text(x + 6, 10, value, max_chars=12)

            # Power icon (pill badge).
            power_x = right_zone_start + (
                len(self.custom_widgets) * self.CUSTOM_WIDGET_W
            )
            power_img = Image.new(
                "RGB", (self.POWER_W, self.TASKBAR_H), bg_rgb
            )
            pd = ImageDraw.Draw(power_img)
            pd.rounded_rectangle(
                (3, 5, self.POWER_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=bg_rgb,
                outline=fg_rgb,
                width=1,
            )
            px, py = self.POWER_W // 2, self.TASKBAR_H // 2
            pd.arc((px - 9, py - 9, px + 9, py + 9), 35, 325, fill=fg_rgb, width=2)
            pd.line((px, py - 10, px, py + 1), fill=fg_rgb, width=2)
            put_pil(power_img, power_x, 0)

            # Bluetooth icon (pill badge; accent when powered).
            bluetooth_x = power_x + self.POWER_W
            bt_img = Image.new(
                "RGB", (self.BLUETOOTH_W, self.TASKBAR_H), bg_rgb
            )
            bd = ImageDraw.Draw(bt_img)
            bt_powered = self.bluetooth_status.get("powered", False)
            bd.rounded_rectangle(
                (3, 5, self.BLUETOOTH_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=active_rgb if bt_powered else bg_rgb,
                outline=accent_rgb if bt_powered else fg_rgb,
                width=1,
            )
            bx, by = self.BLUETOOTH_W // 2, self.TASKBAR_H // 2
            # Stylized Bluetooth rune.
            bd.line((bx, by - 12, bx, by + 12), fill=fg_rgb, width=2)
            bd.line((bx, by - 12, bx + 7, by - 5), fill=fg_rgb, width=2)
            bd.line((bx + 7, by - 5, bx - 7, by + 7), fill=fg_rgb, width=2)
            bd.line((bx - 7, by - 7, bx + 7, by + 5), fill=fg_rgb, width=2)
            bd.line((bx + 7, by + 5, bx, by + 12), fill=fg_rgb, width=2)
            if not bt_powered:
                bd.line((4, 4, self.BLUETOOTH_W - 4, self.TASKBAR_H - 4), fill=fg_rgb, width=1)
            put_pil(bt_img, bluetooth_x, 0)

            # Audio icon (pill badge; accent when muted).
            audio_x = bluetooth_x + self.BLUETOOTH_W
            audio_img = Image.new(
                "RGB", (self.AUDIO_W, self.TASKBAR_H), bg_rgb
            )
            ad = ImageDraw.Draw(audio_img)
            audio_muted = self.audio_status.get("muted")
            ad.rounded_rectangle(
                (3, 5, self.AUDIO_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=bg_rgb,
                outline=accent_rgb if audio_muted else fg_rgb,
                width=1,
            )
            ax, ay = self.AUDIO_W // 2, self.TASKBAR_H // 2
            ad.polygon(
                [(ax - 11, ay - 4), (ax - 5, ay - 4), (ax + 1, ay - 10),
                 (ax + 1, ay + 10), (ax - 5, ay + 4), (ax - 11, ay + 4)],
                outline=fg_rgb,
            )
            if audio_muted:
                ad.line((ax - 13, ay - 11, ax + 12, ay + 11), fill=fg_rgb, width=2)
            else:
                ad.arc((ax - 7, ay - 9, ax + 11, ay + 9), 300, 60, fill=fg_rgb, width=2)
                ad.arc((ax - 4, ay - 6, ax + 7, ay + 6), 300, 60, fill=fg_rgb, width=2)
            put_pil(audio_img, audio_x, 0)

            # Wi-Fi icon (pill badge; accent when connected).
            wifi_x = audio_x + self.AUDIO_W
            wifi_img = Image.new(
                "RGB", (self.WIFI_W, self.TASKBAR_H), bg_rgb
            )
            wd = ImageDraw.Draw(wifi_img)
            wifi_connected = self.wifi_status.get("connected")
            wd.rounded_rectangle(
                (3, 5, self.WIFI_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=active_rgb if wifi_connected else bg_rgb,
                outline=accent_rgb if wifi_connected else fg_rgb,
                width=1,
            )
            wx, wy = self.WIFI_W // 2, 22
            wd.arc((wx - 14, wy - 13, wx + 14, wy + 15), 215, 325, fill=fg_rgb, width=2)
            wd.arc((wx - 9, wy - 8, wx + 9, wy + 10), 215, 325, fill=fg_rgb, width=2)
            wd.ellipse((wx - 2, wy - 2, wx + 2, wy + 2), fill=fg_rgb)
            put_pil(wifi_img, wifi_x, 0)

            # Battery icon (pill badge; accent when low or charging).
            battery_x = wifi_x + self.WIFI_W
            battery_img = Image.new(
                "RGB", (self.BATTERY_W, self.TASKBAR_H), bg_rgb
            )
            bd = ImageDraw.Draw(battery_img)
            batt = self.battery_status
            batt_pct = batt.get("percent", 0)
            batt_available = batt.get("available", False)
            batt_low = batt_available and batt_pct <= 20
            batt_hex = accent_hex if batt_low else fg_rgb
            bd.rounded_rectangle(
                (3, 5, self.BATTERY_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=bg_rgb,
                outline=batt_hex,
                width=1,
            )
            bx0, by0, bw, bh = 11, 13, 20, 10
            bd.rectangle(
                (bx0, by0, bx0 + bw, by0 + bh),
                outline=batt_hex,
                width=1,
            )
            bd.rectangle(
                (bx0 + bw, by0 + 3, bx0 + bw + 2, by0 + bh - 3),
                fill=batt_hex,
            )
            if batt_available:
                fill_w = int((bw - 2) * max(0.0, min(1.0, batt_pct / 100.0)))
                if fill_w > 0:
                    bd.rectangle(
                        (bx0 + 1, by0 + 1, bx0 + 1 + fill_w, by0 + bh - 1),
                        fill=batt_hex,
                    )
                if batt.get("charging"):
                    bd.line(
                        (bx0 + 8, by0 - 2, bx0 + 13, by0 + 4),
                        fill=accent_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 13, by0 + 4, bx0 + 9, by0 + 4),
                        fill=accent_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 9, by0 + 4, bx0 + 12, by0 + 11),
                        fill=accent_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 12, by0 + 11, bx0 + 7, by0 + 5),
                        fill=accent_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 7, by0 + 5, bx0 + 11, by0 + 5),
                        fill=accent_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 11, by0 + 5, bx0 + 8, by0 - 2),
                        fill=accent_rgb,
                        width=2,
                    )
            put_pil(battery_img, battery_x, 0)
            draw_text(
                battery_x + 36,
                10,
                f"{batt_pct}%" if batt_available else "n/a",
                max_chars=5,
            )

            # Clock (pill badge).
            import datetime
            clock_x = battery_x + self.BATTERY_W
            clock_img = Image.new(
                "RGB", (self.CLOCK_W, self.TASKBAR_H), bg_rgb
            )
            cd = ImageDraw.Draw(clock_img)
            cd.rounded_rectangle(
                (3, 5, self.CLOCK_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=active_rgb,
                outline=fg_rgb,
                width=1,
            )
            put_pil(clock_img, clock_x, 0)

            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M")
            date_str = now.strftime("%m/%d")

            # Center the clock text inside its pill badge.
            time_w = self._text_px_width(time_str)
            date_w = self._text_px_width(date_str)
            pad = 1

            # Draw time
            draw_text(
                clock_x + (self.CLOCK_W - time_w) // 2 - pad,
                8,
                time_str,
                max_chars=5,
                background=active_hex,
            )

            # Draw date below time
            draw_text(
                clock_x + (self.CLOCK_W - date_w) // 2 - pad,
                22,
                date_str,
                max_chars=5,
                background=active_hex,
            )

            # Bottom separator.
            sep = Image.new(
                "RGB",
                (self.screen_w, 1),
                border_rgb,
            )
            put_pil(
                sep,
                0,
                self.TASKBAR_H - 1,
            )

            self.display.flush()

        except Exception as exc:
            print(
                f"Pillarium: taskbar redraw failed: {exc}",
                file=sys.stderr,
            )

    def _ensure_taskbar_on_top(self):
        if getattr(self, "taskbar", None):
            try:
                self.taskbar.configure(stack_mode=X.Above)
            except Exception:
                pass
