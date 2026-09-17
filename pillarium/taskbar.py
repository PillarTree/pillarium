"""Task‑bar creation, hit‑testing and rendering."""

import os
import sys
from Xlib import X


class TaskbarMixin:
    def _init_taskbar(self):
        # Task‑bar state
        self.TASKBAR_H = 36
        self.taskbar_items = []  # ordered list of client ids
        self.taskbar_drag = None  # middle‑button reorder drag state
        self.clock_w = self.CLOCK_W  # dynamic clock badge width (grows to fit)
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
        except Exception as exc:
            print(f"Pillarium: taskbar.get_geometry failed: {exc}", file=sys.stderr)
            try:
                tb.destroy()
            except Exception:
                pass
            self.taskbar = self._create_taskbar()

    # -----------------------------------------------------------------
    # Determine what kind of item is under a task‑bar x‑coordinate
    # -----------------------------------------------------------------
    def _taskbar_hit_kind(self, x):
        right_zone_start = self.screen_w - self._taskbar_right_zone_w()
        if x < self.SEARCH_W:
            return "search"
        if x >= right_zone_start:
            (
                _custom_x,
                power_x,
                bluetooth_x,
                audio_x,
                ethernet_x,
                wifi_x,
                battery_x,
                clock_x,
            ) = self._taskbar_right_zone_slots()
            if x < power_x:
                return "widget"
            if power_x <= x < bluetooth_x:
                return "power"
            if bluetooth_x <= x < audio_x:
                return "bluetooth"
            if audio_x <= x < ethernet_x:
                return "audio"
            if ethernet_x <= x < wifi_x:
                return "ethernet"
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
    # Task‑bar item geometry (shared by hit‑testing and reordering)
    # -----------------------------------------------------------------
    def _taskbar_items_geometry(self):
        right_zone_start = self.screen_w - self._taskbar_right_zone_w()
        q_start = self.SEARCH_W
        q_width = self._taskbar_quick_launch_w()
        area_x = q_start + q_width
        items_area_w = max(96, right_zone_start - area_x)
        count = max(1, len(self.taskbar_items))
        item_w = max(96, items_area_w // count)
        return area_x, item_w

    def _taskbar_item_index_at(self, x):
        area_x, item_w = self._taskbar_items_geometry()
        idx = (x - area_x) // item_w
        if 0 <= idx < len(self.taskbar_items):
            return idx
        return None

    # -----------------------------------------------------------------
    # Precise task‑bar hit‑test (returns the client‑id under the x‑coordinate)
    # -----------------------------------------------------------------
    def _taskbar_item_at(self, x):
        idx = self._taskbar_item_index_at(x)
        if idx is not None:
            return self.taskbar_items[idx]
        return None

    def _taskbar_right_zone_w(self):
        return (
            self.POWER_W
            + self.BLUETOOTH_W
            + self.AUDIO_W
            + self.ETH_W
            + self.WIFI_W
            + self.BATTERY_W
            + getattr(self, "clock_w", self.CLOCK_W)
            + (len(self.custom_widgets) * self.CUSTOM_WIDGET_W)
        )

    def _taskbar_right_zone_slots(self):
        """Return the left x-coordinate of every right-zone badge.

        Order: (custom_widgets, power, bluetooth, audio, ethernet,
        wifi, battery, clock).  Shared by taskbar rendering, hit-testing
        and the global hot-key anchors so the layout stays in sync.
        """
        right_zone_start = self.screen_w - self._taskbar_right_zone_w()
        custom_x = right_zone_start
        power_x = custom_x + (len(self.custom_widgets) * self.CUSTOM_WIDGET_W)
        bluetooth_x = power_x + self.POWER_W
        audio_x = bluetooth_x + self.BLUETOOTH_W
        ethernet_x = audio_x + self.AUDIO_W
        wifi_x = ethernet_x + self.ETH_W
        battery_x = wifi_x + self.WIFI_W
        clock_x = battery_x + self.BATTERY_W
        return (
            custom_x,
            power_x,
            bluetooth_x,
            audio_x,
            ethernet_x,
            wifi_x,
            battery_x,
            clock_x,
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
        """Draw taskbar buttons with real icons, labels, and widgets (Cadet style)."""
        if not getattr(self, "taskbar", None):
            return

        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return

        try:
            tb = self.taskbar
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
                        else panel_rgb
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
                color_hex=text_hex,
            ):
                return self._draw_text_pixels(
                    tb,
                    int(x),
                    int(y),
                    str(value)[:max_chars],
                    color_hex,
                    background
                    or panel_hex,
                    padding=1,
                )

            # Search button (pill badge; highlighted while the launcher is open).
            search_img = Image.new(
                "RGB",
                (
                    self.SEARCH_W,
                    self.TASKBAR_H,
                ),
                panel_rgb,
            )
            sd = ImageDraw.Draw(search_img)
            search_open = getattr(self, "search_state", None) is not None
            sd.rounded_rectangle(
                (3, 5, self.SEARCH_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=select_rgb if search_open else panel_rgb,
                outline=accent_hot_rgb if search_open else text_rgb,
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
                outline=text_rgb,
                width=2,
            )
            sd.line(
                (
                    cx + 4,
                    cy + 4,
                    cx + 10,
                    cy + 10,
                ),
                fill=text_rgb,
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
                pill_fill = select_rgb if running else panel_rgb

                btn = Image.new(
                    "RGB",
                    (button_w, self.TASKBAR_H),
                    panel_rgb,
                )
                bd = ImageDraw.Draw(btn)
                bd.rounded_rectangle(
                    (2, 5, button_w - 2, self.TASKBAR_H - 5),
                    radius=13,
                    fill=pill_fill,
                    outline=accent_hot_rgb if running else text_rgb,
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
                        fill=accent_hot_rgb,
                    )
                put_pil(btn, x, 0)

                badge = self._make_icon_badge(
                    self._load_icon(item.get("icon"), 24),
                    item.get("label", "?"),
                    panel_hex,
                )
                try:
                    badge_rgb = self._composite_rgba(badge, pill_fill)
                    put_pil(
                        badge_rgb,
                        x + (button_w - badge_rgb.width) // 2,
                        5 + (26 - badge_rgb.height) // 2,
                        background=panel_rgb,
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
                        select_foc_rgb
                        if active
                        else panel_rgb
                    )
                    row_outline = accent_hot_rgb if active else text_dim_rgb

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
                        outline=row_outline,
                        width=1,
                    )
                    if active:
                        rd.rectangle(
                            (3, 3, width - 3, 5),
                            fill=accent_hot_rgb,
                        )
                    put_pil(row, x, 0)

                    badge = self._make_icon_badge(
                        self._resolve_taskbar_icon(data),
                        data.get("title", "?"),
                        panel_hex,
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
                            select_foc_hex
                            if active
                            else panel_hex
                        ),
                        color_hex=text_hex,
                    )

            # Custom widgets.
            custom_x = right_zone_start
            for idx, widget in enumerate(self.custom_widgets):
                x = custom_x + idx * self.CUSTOM_WIDGET_W
                value = widget.get("text") or widget.get("label", "Widget")
                draw_text(x + 6, 10, value, max_chars=12, color_hex=text_dim_hex)

            # Power icon (pill badge).
            (
                _custom_x,
                power_x,
                bluetooth_x,
                audio_x,
                ethernet_x,
                wifi_x,
                battery_x,
                clock_x,
            ) = self._taskbar_right_zone_slots()
            power_img = Image.new(
                "RGB", (self.POWER_W, self.TASKBAR_H), panel_rgb
            )
            pd = ImageDraw.Draw(power_img)
            pd.rounded_rectangle(
                (3, 5, self.POWER_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=panel_rgb,
                outline=text_dim_rgb,
                width=1,
            )
            px, py = self.POWER_W // 2, self.TASKBAR_H // 2
            pd.arc((px - 9, py - 9, px + 9, py + 9), 35, 325, fill=text_rgb, width=2)
            pd.line((px, py - 10, px, py + 1), fill=text_rgb, width=2)
            put_pil(power_img, power_x, 0)

            # Bluetooth icon (pill badge; accent when powered).
            bt_img = Image.new(
                "RGB", (self.BLUETOOTH_W, self.TASKBAR_H), panel_rgb
            )
            bd = ImageDraw.Draw(bt_img)
            bt_powered = self.bluetooth_status.get("powered", False)
            bd.rounded_rectangle(
                (3, 5, self.BLUETOOTH_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=select_rgb if bt_powered else panel_rgb,
                outline=accent_hot_rgb if bt_powered else text_dim_rgb,
                width=1,
            )
            bx, by = self.BLUETOOTH_W // 2, self.TASKBAR_H // 2
            # Stylized Bluetooth rune.
            bt_color = accent_hot_rgb if bt_powered else text_rgb
            bd.line((bx, by - 12, bx, by + 12), fill=bt_color, width=2)
            bd.line((bx, by - 12, bx + 7, by - 5), fill=bt_color, width=2)
            bd.line((bx + 7, by - 5, bx - 7, by + 7), fill=bt_color, width=2)
            bd.line((bx - 7, by - 7, bx + 7, by + 5), fill=bt_color, width=2)
            bd.line((bx + 7, by + 5, bx, by + 12), fill=bt_color, width=2)
            if not bt_powered:
                bd.line((4, 4, self.BLUETOOTH_W - 4, self.TASKBAR_H - 4), fill=text_dim_rgb, width=1)
            put_pil(bt_img, bluetooth_x, 0)

            # Audio icon (pill badge; accent when muted).
            audio_img = Image.new(
                "RGB", (self.AUDIO_W, self.TASKBAR_H), panel_rgb
            )
            ad = ImageDraw.Draw(audio_img)
            audio_muted = self.audio_status.get("muted")
            ad.rounded_rectangle(
                (3, 5, self.AUDIO_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=panel_rgb,
                outline=accent_hot_rgb if audio_muted else text_dim_rgb,
                width=1,
            )
            ax, ay = self.AUDIO_W // 2, self.TASKBAR_H // 2
            audio_color = accent_hot_rgb if audio_muted else text_rgb
            ad.polygon(
                [(ax - 11, ay - 4), (ax - 5, ay - 4), (ax + 1, ay - 10),
                 (ax + 1, ay + 10), (ax - 5, ay + 4), (ax - 11, ay + 4)],
                outline=audio_color,
            )
            if audio_muted:
                ad.line((ax - 13, ay - 11, ax + 12, ay + 11), fill=audio_color, width=2)
            else:
                ad.arc((ax - 7, ay - 9, ax + 11, ay + 9), 300, 60, fill=audio_color, width=2)
                ad.arc((ax - 4, ay - 6, ax + 7, ay + 6), 300, 60, fill=audio_color, width=2)
            put_pil(audio_img, audio_x, 0)

            # Ethernet icon (pill badge; accent when connected).
            eth_img = Image.new(
                "RGB", (self.ETH_W, self.TASKBAR_H), panel_rgb
            )
            ed = ImageDraw.Draw(eth_img)
            eth_connected = self.ethernet_status.get("connected", False)
            ed.rounded_rectangle(
                (3, 5, self.ETH_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=select_rgb if eth_connected else panel_rgb,
                outline=accent_hot_rgb if eth_connected else text_dim_rgb,
                width=1,
            )
            ex, ey = self.ETH_W // 2, self.TASKBAR_H // 2
            eth_color = accent_hot_rgb if eth_connected else text_rgb
            # Stylized RJ45 plug: body, cable and contact pins.
            ed.rectangle((ex - 9, ey - 6, ex + 3, ey + 6), outline=eth_color)
            ed.rectangle((ex + 3, ey - 3, ex + 8, ey + 3), outline=eth_color)
            for pin in range(4):
                pxx = ex - 7 + pin * 3
                ed.line((pxx, ey - 4, pxx, ey + 4), fill=eth_color, width=1)
            ed.line((ex - 12, ey, ex - 9, ey), fill=eth_color, width=2)
            if not eth_connected:
                ed.line(
                    (4, 4, self.ETH_W - 4, self.TASKBAR_H - 4),
                    fill=text_dim_rgb,
                    width=1,
                )
            put_pil(eth_img, ethernet_x, 0)

            # Wi-Fi icon (pill badge; accent when connected).
            wifi_img = Image.new(
                "RGB", (self.WIFI_W, self.TASKBAR_H), panel_rgb
            )
            wd = ImageDraw.Draw(wifi_img)
            wifi_connected = self.wifi_status.get("connected")
            wd.rounded_rectangle(
                (3, 5, self.WIFI_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=select_rgb if wifi_connected else panel_rgb,
                outline=accent_hot_rgb if wifi_connected else text_dim_rgb,
                width=1,
            )
            wx, wy = self.WIFI_W // 2, 22
            wifi_color = accent_hot_rgb if wifi_connected else text_rgb
            wd.arc((wx - 14, wy - 13, wx + 14, wy + 15), 215, 325, fill=wifi_color, width=2)
            wd.arc((wx - 9, wy - 8, wx + 9, wy + 10), 215, 325, fill=wifi_color, width=2)
            wd.ellipse((wx - 2, wy - 2, wx + 2, wy + 2), fill=wifi_color)
            put_pil(wifi_img, wifi_x, 0)

            # Battery icon (pill badge; accent when low or charging).
            battery_img = Image.new(
                "RGB", (self.BATTERY_W, self.TASKBAR_H), panel_rgb
            )
            bd = ImageDraw.Draw(battery_img)
            batt = self.battery_status
            batt_pct = batt.get("percent", 0)
            batt_available = batt.get("available", False)
            batt_low = batt_available and batt_pct <= 20
            batt_color = accent_hot_rgb if batt_low else text_rgb
            bd.rounded_rectangle(
                (3, 5, self.BATTERY_W - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=panel_rgb,
                outline=batt_color,
                width=1,
            )
            bx0, by0, bw, bh = 11, 13, 20, 10
            bd.rectangle(
                (bx0, by0, bx0 + bw, by0 + bh),
                outline=batt_color,
                width=1,
            )
            bd.rectangle(
                (bx0 + bw, by0 + 3, bx0 + bw + 2, by0 + bh - 3),
                fill=batt_color,
            )
            if batt_available:
                fill_w = int((bw - 2) * max(0.0, min(1.0, batt_pct / 100.0)))
                if fill_w > 0:
                    bd.rectangle(
                        (bx0 + 1, by0 + 1, bx0 + 1 + fill_w, by0 + bh - 1),
                        fill=batt_color,
                    )
                if batt.get("charging"):
                    bd.line(
                        (bx0 + 8, by0 - 2, bx0 + 13, by0 + 4),
                        fill=accent_hot_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 13, by0 + 4, bx0 + 9, by0 + 4),
                        fill=accent_hot_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 9, by0 + 4, bx0 + 12, by0 + 11),
                        fill=accent_hot_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 12, by0 + 11, bx0 + 7, by0 + 5),
                        fill=accent_hot_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 7, by0 + 5, bx0 + 11, by0 + 5),
                        fill=accent_hot_rgb,
                        width=2,
                    )
                    bd.line(
                        (bx0 + 11, by0 + 5, bx0 + 8, by0 - 2),
                        fill=accent_hot_rgb,
                        width=2,
                    )
            put_pil(battery_img, battery_x, 0)
            draw_text(
                battery_x + 36,
                10,
                f"{batt_pct}%" if batt_available else "n/a",
                max_chars=5,
                color_hex=text_dim_hex,
            )

            # Clock (pill badge).  Its width adapts to the active
            # time/date format so longer strings are never clipped.
            import datetime
            now = datetime.datetime.now()
            time_str = now.strftime(self.time_format)
            date_str = now.strftime(self.date_format)
            time_w = self._text_px_width(time_str)
            date_w = self._text_px_width(date_str)
            pad = 1
            self.clock_w = max(self.CLOCK_W, time_w + 16, date_w + 16)
            clock_img = Image.new(
                "RGB", (self.clock_w, self.TASKBAR_H), panel_rgb
            )
            cd = ImageDraw.Draw(clock_img)
            cd.rounded_rectangle(
                (3, 5, self.clock_w - 3, self.TASKBAR_H - 5),
                radius=13,
                fill=select_rgb,
                outline=text_dim_rgb,
                width=1,
            )
            put_pil(clock_img, clock_x, 0)

            # Center the clock text inside its pill badge.
            draw_text(
                clock_x + (self.clock_w - time_w) // 2 - pad,
                8,
                time_str,
                max_chars=32,
                background=select_hex,
                color_hex=text_hex,
            )

            # Draw date below time
            draw_text(
                clock_x + (self.clock_w - date_w) // 2 - pad,
                22,
                date_str,
                max_chars=32,
                background=select_hex,
                color_hex=text_dim_hex,
            )

            # Bottom separator.
            sep = Image.new(
                "RGB",
                (self.screen_w, 1),
                panel_line_rgb,
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
