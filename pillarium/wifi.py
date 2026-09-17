"""Wi‑Fi / NetworkManager widget and password dialog."""

import subprocess
import sys
from Xlib import X, XK


class WifiMixin:
    def _init_wifi(self):
        # Wi‑Fi password dialog state (None when closed)
        self.wifi_auth_state = None
        # Wi‑Fi status cache
        self.wifi_status = {
            "connected": False,
            "ssid": None,
            "signal": 0,
            "available": True,
        }
        self._last_wifi_poll = 0.0

    # -----------------------------------------------------------------
    # Wi‑Fi / NetworkManager widget
    # -----------------------------------------------------------------
    def _nmcli(self, args, timeout=3):
        try:
            result = subprocess.run(
                ["nmcli"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return None
            return result.stdout
        except Exception:
            return None

    def _poll_wifi_status(self):
        out = self._nmcli(["-t", "-f", "ACTIVE,SIGNAL,SSID", "dev", "wifi"], timeout=3)
        status = {"connected": False, "ssid": None, "signal": 0, "available": out is not None}
        if out:
            for line in out.splitlines():
                parts = line.split(":")
                if len(parts) >= 3 and parts[0] == "yes":
                    status["connected"] = True
                    try:
                        status["signal"] = int(parts[1])
                    except Exception:
                        status["signal"] = 0
                    status["ssid"] = parts[2] or None
                    break
        self.wifi_status = status

    def _wifi_scan(self):
        self._nmcli(["dev", "wifi", "rescan"], timeout=2)
        self._poll_wifi_status()
        self._redraw_taskbar()

    def _wifi_radio(self):
        out = self._nmcli(["radio", "wifi"], timeout=3)
        if not out:
            return None
        return out.strip().lower() == "enabled"

    def _wifi_device(self):
        out = self._nmcli(["-t", "-f", "DEVICE,TYPE", "dev"], timeout=3)
        if not out:
            return None
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "wifi":
                return parts[0]
        return None

    def _wifi_networks(self):
        out = self._nmcli(["-t", "-f", "SSID,SIGNAL,ACTIVE", "dev", "wifi"], timeout=3)
        networks = []
        if out:
            by_ssid = {}
            for line in out.splitlines():
                parts = line.split(":", 1)
                if len(parts) < 2 or not parts[0]:
                    continue
                ssid = parts[0]
                rest = parts[1].split(":")
                if len(rest) < 2:
                    continue
                try:
                    signal = int(rest[0])
                except Exception:
                    signal = 0
                in_use = rest[1] == "yes"
                prev = by_ssid.get(ssid)
                if prev is None or (in_use and not prev[1]):
                    by_ssid[ssid] = (signal, in_use)
            networks = sorted(by_ssid.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))
        return networks

    def _toggle_wifi_menu(self, anchor_x):
        if getattr(self, "active_menu", None) and self.active_menu.get("kind") == "wifi":
            self._close_active_menu()
            return
        self._poll_wifi_status()
        self._close_active_menu()
        self._close_wifi_auth()
        self._close_confirm_dialog()

        radio_on = self._wifi_radio()
        if not self.wifi_status.get("available") or radio_on is None:
            items = [
                {"label": "Wi-Fi unavailable", "action": ("wifi", ("noop", None))},
                {"label": "Cancel", "action": ("wifi", ("cancel", None))},
            ]
        else:
            items = [
                {
                    "label": "Turn Wi-Fi Off" if radio_on else "Turn Wi-Fi On",
                    "action": ("wifi", ("radio_off" if radio_on else "radio_on", None)),
                },
                {"label": "Rescan Networks", "action": ("wifi", ("rescan", None))},
            ]
            if radio_on:
                for ssid, (signal, in_use) in self._wifi_networks()[:8]:
                    items.append({
                        "label": (
                            ("Disconnect: " if in_use else "Connect: ") + ssid[:25]
                        ),
                        "action": (
                            "wifi",
                            ("disconnect", None) if in_use else ("connect", ssid),
                        ),
                    })
            items.append({"label": "Cancel", "action": ("wifi", ("cancel", None))})

        self._open_menu("wifi", items, anchor_x, self.WIFI_W)

    def _wifi_menu_action(self, payload):
        if not payload:
            return
        action, value = payload
        if action in ("cancel", "noop"):
            return
        if action == "rescan":
            self._wifi_scan()
        elif action in ("radio_on", "radio_off"):
            self._nmcli(["radio", "wifi", "on" if action == "radio_on" else "off"], timeout=3)
            self._poll_wifi_status()
            self._redraw_taskbar()
        elif action == "connect":
            if not value:
                return
            if self._nmcli(["dev", "wifi", "connect", value], timeout=15) is None:
                if self._wifi_network_requires_auth(value):
                    self._open_wifi_auth(value)
                else:
                    print(
                        f"Pillarium: could not connect to '{value}'",
                        file=sys.stderr,
                    )
            self._poll_wifi_status()
            self._redraw_taskbar()
        elif action == "disconnect":
            dev = self._wifi_device()
            if dev:
                self._nmcli(["dev", "disconnect", dev], timeout=5)
            self._poll_wifi_status()
            self._redraw_taskbar()

    # -----------------------------------------------------------------
    # Wi‑Fi password entry dialog
    # -----------------------------------------------------------------
    def _wifi_network_requires_auth(self, ssid):
        out = self._nmcli(["-t", "-f", "SSID,SECURITY", "dev", "wifi"], timeout=3)
        if not out:
            return False
        for line in out.splitlines():
            parts = line.split(":", 1)
            if len(parts) < 2 or not parts[0]:
                continue
            if parts[0] == ssid and parts[1].strip():
                return True
        return False

    def _open_wifi_auth(self, ssid):
        if getattr(self, "search_state", None):
            self._close_search()
        self._close_active_menu()
        width = 380
        height = 170
        x = max(0, (self.screen_w - width) // 2)
        y = max(0, (self.screen_h - self.TASKBAR_H - height) // 2)

        # Use Cadet theme colors
        panel_hex = self.current_palette.get("panel", "#2c313a")
        panel_line_hex = self.current_palette.get("panel_line", "#171a1f")
        panel_pixel = self._alloc_color(panel_hex, self.screen.black_pixel)
        panel_line_pixel = self._alloc_color(panel_line_hex, self.screen.black_pixel)

        win = self._create_window(
            self.root,
            x,
            y,
            width,
            height,
            panel_pixel,
            panel_line_pixel,
            override_redirect=True,
        )
        self._own_windows.add(win.id)
        win.change_attributes(
            background_pixel=panel_pixel,
            border_pixel=panel_line_pixel,
            event_mask=X.ButtonPressMask | X.ExposureMask | X.KeyPressMask,
        )
        win.map()
        try:
            win.configure(stack_mode=X.Above)
        except Exception:
            pass
        self.wifi_auth_state = {
            "ssid": ssid,
            "password": "",
            "window": win,
            "status": "",
            "error": False,
            "connecting": False,
            "width": width,
            "height": height,
            "connect_rect": None,
            "cancel_rect": None,
        }
        try:
            self.display.set_input_focus(win, X.RevertToParent, X.CurrentTime)
        except Exception:
            pass
        self._redraw_wifi_auth()
        self.display.flush()

    def _close_wifi_auth(self):
        st = getattr(self, "wifi_auth_state", None)
        if not st:
            return
        win = st.get("window")
        if win is not None:
            try:
                self._own_windows.discard(win.id)
                win.destroy()
            except Exception:
                pass
        self.wifi_auth_state = None
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

    def _redraw_wifi_auth(self):
        st = getattr(self, "wifi_auth_state", None)
        if not st or not st.get("window"):
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return

        win = st["window"]
        width = st["width"]
        height = st["height"]

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

        gc_bg = self._gc(win, self.colors["surface"], self.colors["surface"])
        win.fill_rectangle(gc_bg, 0, 0, width, height)

        # Draw border like Cadet
        gc_border = self._gc(win, self.colors["border"], self.colors["surface"])
        win.rectangle(gc_border, 0, 0, width, height)
        win.rectangle(gc_border, 0, 0, 1, height)
        win.rectangle(gc_border, width - 1, 0, 1, height)
        win.rectangle(gc_border, 0, height - 1, width, 1)

        self._draw_text_pixels(
            win,
            18,
            14,
            f"Connect to {st['ssid']}"[:40],
            text_hex,
            panel_hex,
            padding=1,
        )
        self._draw_text_pixels(
            win, 18, 46, "Password:", text_hex, panel_hex, padding=1
        )

        field_x = 18
        field_y = 62
        field_w = width - 36
        field_h = 30
        gc_field = self._gc(win, self.colors["border"], self.colors["surface"])
        win.fill_rectangle(gc_field, field_x, field_y, field_w, field_h)

        masked = "*" * len(st["password"])
        font = ImageFont.load_default()
        probe = Image.new("RGB", (1, 1))
        probe_draw = ImageDraw.Draw(probe)
        try:
            bb = probe_draw.textbbox((0, 0), masked, font=font)
            tw = bb[2] - bb[0]
        except Exception:
            tw = probe_draw.textsize(masked, font=font)
        self._draw_text_pixels(
            win,
            field_x + 6,
            field_y + 6,
            masked,
            text_hex,
            panel_hex,
            padding=1,
        )
        if not st.get("connecting"):
            gc_cursor = self._gc(win, self.colors["text"], self.colors["surface"])
            win.fill_rectangle(
                gc_cursor,
                field_x + 8 + tw,
                field_y + 7,
                1,
                field_h - 14,
            )

        if st.get("status"):
            self._draw_text_pixels(
                win,
                18,
                112,
                st["status"][:48],
                accent_hot_hex if st.get("error") else text_dim_hex,
                panel_hex,
                padding=1,
            )

        btn_y = height - 40
        connect_w, connect_h = 86, 28
        cancel_w, cancel_h = 76, 28
        connect_x = width - 18 - connect_w
        cancel_x = connect_x - 12 - cancel_w

        # Connect button - Cadet accent style
        connect_img = Image.new("RGB", (connect_w, connect_h), panel_rgb)
        cd = ImageDraw.Draw(connect_img)
        cd.rounded_rectangle(
            (0, 0, connect_w - 1, connect_h - 1),
            radius=6,
            fill=accent_rgb,
        )
        try:
            bb = cd.textbbox((0, 0), "Connect", font=font)
            lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            lw, lh = cd.textsize("Connect", font=font)
        cd.text(
            ((connect_w - lw) // 2, (connect_h - lh) // 2),
            "Connect",
            fill=panel_rgb,
            font=font,
        )
        gc = self._gc(win, self.colors["text"], self.colors["surface"])
        win.put_pil_image(gc, connect_x, btn_y, connect_img)

        # Cancel button - Cadet panel style with outline
        cancel_img = Image.new("RGB", (cancel_w, cancel_h), panel_rgb)
        xd = ImageDraw.Draw(cancel_img)
        xd.rounded_rectangle(
            (0, 0, cancel_w - 1, cancel_h - 1),
            radius=6,
            outline=text_dim_rgb,
            width=1,
        )
        try:
            bb = xd.textbbox((0, 0), "Cancel", font=font)
            lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            lw, lh = xd.textsize("Cancel", font=font)
        xd.text(
            ((cancel_w - lw) // 2, (cancel_h - lh) // 2),
            "Cancel",
            fill=text_rgb,
            font=font,
        )
        win.put_pil_image(gc, cancel_x, btn_y, cancel_img)

        st["connect_rect"] = (connect_x, btn_y, connect_x + connect_w, btn_y + connect_h)
        st["cancel_rect"] = (cancel_x, btn_y, cancel_x + cancel_w, btn_y + cancel_h)
        self.display.flush()

    def _handle_wifi_auth_keypress(self, event):
        st = self.wifi_auth_state
        if st is None:
            return
        shifted = bool(event.state & X.ShiftMask)
        try:
            keysym = self.display.keycode_to_keysym(event.detail, 1 if shifted else 0)
        except Exception:
            return
        if keysym == XK.XK_Escape:
            self._close_wifi_auth()
            return
        if keysym in (XK.XK_Return, XK.XK_KP_Enter):
            self._wifi_auth_submit()
            return
        if keysym == XK.XK_BackSpace:
            st["password"] = st["password"][:-1]
            self._redraw_wifi_auth()
            return
        if 0x20 <= keysym <= 0x7e:
            st["password"] += chr(keysym)
            self._redraw_wifi_auth()

    def _handle_wifi_auth_click(self, event):
        st = getattr(self, "wifi_auth_state", None)
        if not st:
            return
        cx0, cy0, cx1, cy1 = st.get("cancel_rect") or (0, 0, 0, 0)
        if cx0 <= event.event_x < cx1 and cy0 <= event.event_y < cy1:
            self._close_wifi_auth()
            return
        nx0, ny0, nx1, ny1 = st.get("connect_rect") or (0, 0, 0, 0)
        if nx0 <= event.event_x < nx1 and ny0 <= event.event_y < ny1:
            self._wifi_auth_submit()

    def _wifi_auth_submit(self):
        st = getattr(self, "wifi_auth_state", None)
        if not st or st.get("connecting"):
            return
        ssid = st["ssid"]
        pw = st["password"]
        if not pw:
            st["status"] = "Enter a password"
            st["error"] = True
            self._redraw_wifi_auth()
            return
        st["connecting"] = True
        st["status"] = "Connecting..."
        st["error"] = False
        self._redraw_wifi_auth()
        self.display.flush()
        result = self._nmcli(
            ["dev", "wifi", "connect", ssid, "password", pw], timeout=20
        )
        st["connecting"] = False
        if result is not None:
            self._close_wifi_auth()
            self._poll_wifi_status()
            self._redraw_taskbar()
        else:
            st["status"] = "Incorrect password or connection failed"
            st["error"] = True
            self._redraw_wifi_auth()
