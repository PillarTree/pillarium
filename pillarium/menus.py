"""Popup menus, power menu, confirmation dialog and window context menu."""

import subprocess
import sys
from Xlib import X, XK


class MenuMixin:
    def _init_menus(self):
        # Popup menu state (power / wifi) and hover tracking
        self.active_menu = None
        self._desktop_hover = None
        # Confirmation dialog state (None when closed)
        self.confirm_state = None

    # -----------------------------------------------------------------
    # Popup menu handling (power / wifi / window)
    # -----------------------------------------------------------------
    def _open_menu(self, kind, items, anchor_x, anchor_w, anchor_y=None, client_id=None):
        row_h = 30
        width = 210
        height = row_h * len(items)
        x = max(0, min(self.screen_w - width, anchor_x + anchor_w - width))
        if anchor_y is None:
            y = max(0, self.screen_h - self.TASKBAR_H - height)
        else:
            y = max(0, min(self.screen_h - self.TASKBAR_H - height, anchor_y))
        win = self._create_window(
            self.root,
            x,
            y,
            width,
            height,
            self.colors["surface"],
            self.colors["border"],
            override_redirect=True,
        )
        self._own_windows.add(win.id)
        win.change_attributes(
            background_pixel=self.colors["surface"],
            border_pixel=self.colors["border"],
            event_mask=X.ButtonPressMask | X.ExposureMask,
        )
        win.map()
        try:
            win.configure(stack_mode=X.Above)
        except Exception:
            pass
        self.active_menu = {
            "kind": kind,
            "window": win,
            "items": items,
            "row_h": row_h,
            "width": width,
            "height": height,
            "client_id": client_id,
        }
        self._redraw_menu()
        self._redraw_taskbar()
        self.display.flush()

    def _redraw_menu(self):
        m = getattr(self, "active_menu", None)
        if not m:
            return
        win = m["window"]
        row_h = m["row_h"]
        width = m["width"]

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

        gc_bg = self._gc(win, self.colors["surface"], self.colors["surface"])
        win.fill_rectangle(gc_bg, 0, 0, width, m["height"])

        # Draw border like Cadet's PANEL_LINE
        gc_border = self._gc(win, self.colors["border"], self.colors["surface"])
        win.rectangle(gc_border, 0, 0, width, m["height"])
        win.rectangle(gc_border, 0, 0, 1, m["height"])
        win.rectangle(gc_border, width - 1, 0, 1, m["height"])
        win.rectangle(gc_border, 0, m["height"] - 1, width, 1)

        for idx, it in enumerate(m["items"]):
            y0 = idx * row_h
            it["y0"] = y0
            it["y1"] = y0 + row_h
            label = it["label"][:26]

            # Highlight selected item like Cadet's SELECT
            if it.get("enabled", True) and idx == getattr(self, "_menu_hover_idx", -1):
                gc_sel = self._gc(win, self.colors["taskbar_active"], self.colors["taskbar_active"])
                win.fill_rectangle(gc_sel, 1, y0, width - 2, row_h)

            text_color = text_hex if it.get("enabled", True) else text_dim_hex
            if not self._draw_text_pixels(
                win,
                14,
                y0 + 8,
                label,
                text_color,
                panel_hex,
            ):
                gc = self._gc(win, self.colors["text"], self.colors["surface"])
                win.draw_text(gc, 14, y0 + (row_h // 2) + 5, label)
            if idx < len(m["items"]) - 1:
                gc_line = self._gc(win, self.colors["border"], self.colors["surface"])
                win.rectangle(gc_line, 0, y0 + row_h - 1, width, 1)
        self.display.flush()

    def _close_active_menu(self):
        m = getattr(self, "active_menu", None)
        if not m:
            return
        try:
            m["window"].destroy()
        except Exception:
            pass
        self._own_windows.discard(m["window"].id)
        self.active_menu = None
        try:
            self._redraw_taskbar()
            self.display.flush()
        except Exception:
            pass

    def _handle_menu_click(self, event):
        m = getattr(self, "active_menu", None)
        if not m:
            return
        clicked = None
        for it in m["items"]:
            if it.get("y0") is not None and it["y0"] <= event.event_y < it["y1"]:
                clicked = it
                break
        self._close_active_menu()
        if clicked and clicked.get("action"):
            self._dispatch_menu_action(clicked["action"])

    def _dispatch_menu_action(self, action):
        kind, payload = action
        if kind == "power":
            self._power_action(payload)
        elif kind == "wifi":
            self._wifi_menu_action(payload)
        elif kind == "ethernet":
            self._ethernet_menu_action(payload)
        elif kind == "bluetooth":
            self._bluetooth_menu_action(payload)
        elif kind == "audio":
            self._audio_menu_action(payload)
        elif kind == "battery":
            self._battery_menu_action(payload)
        elif kind == "process":
            self._process_menu_action(payload)
        elif kind == "window":
            self._window_menu_action(payload)
        elif kind == "widget":
            self._custom_widget_action(payload)
        elif kind == "desktop":
            self._desktop_menu_action(payload)

    # -----------------------------------------------------------------
    # Desktop context menu (wallpaper options)
    # -----------------------------------------------------------------
    def _toggle_desktop_menu(self, anchor_x, anchor_y):
        if (
            getattr(self, "active_menu", None)
            and self.active_menu.get("kind") == "desktop"
        ):
            self._close_active_menu()
            return
        self._close_active_menu()
        items = [
            {"label": "Change Wallpaper...", "action": ("desktop", "wallpaper_change")},
            {"label": "Reset Default Wallpaper", "action": ("desktop", "wallpaper_default")},
        ]
        self._open_menu("desktop", items, anchor_x, 0, anchor_y=anchor_y)

    def _desktop_menu_action(self, payload):
        if payload == "wallpaper_change":
            self._change_wallpaper()
        elif payload == "wallpaper_default":
            self._reset_default_wallpaper()

    # -----------------------------------------------------------------
    # Power menu
    # -----------------------------------------------------------------
    def _toggle_power_menu(self, anchor_x):
        if getattr(self, "active_menu", None) and self.active_menu.get("kind") == "power":
            self._close_active_menu()
            return
        self._close_active_menu()
        self._close_confirm_dialog()
        items = [
            {"label": "Restart", "action": ("power", "restart")},
            {"label": "Shut Down", "action": ("power", "shutdown")},
            {"label": "Log Out", "action": ("power", "logout")},
            {"label": "Cancel", "action": ("power", "cancel")},
        ]
        self._open_menu("power", items, anchor_x, self.POWER_W)

    def _power_action(self, action):
        if action == "cancel":
            return
        if action == "restart":
            self._open_confirm_dialog(
                "Restart System",
                "Are you sure you want to restart?",
                "Restart",
                lambda: self._power_do("restart"),
            )
        elif action == "shutdown":
            self._open_confirm_dialog(
                "Shut Down System",
                "Are you sure you want to shut down?",
                "Shut Down",
                lambda: self._power_do("shutdown"),
            )
        elif action == "logout":
            self._open_confirm_dialog(
                "Log Out",
                "Are you sure you want to log out?",
                "Log Out",
                lambda: self._power_do("logout"),
            )

    def _power_do(self, action):
        if action == "restart":
            for cmd in (["systemctl", "reboot"], ["reboot"]):
                try:
                    subprocess.Popen(cmd)
                    return
                except Exception:
                    continue
        elif action == "shutdown":
            for cmd in (
                ["systemctl", "poweroff"],
                ["poweroff"],
                ["shutdown", "-h", "now"],
            ):
                try:
                    subprocess.Popen(cmd)
                    return
                except Exception:
                    continue
        elif action == "logout":
            raise SystemExit(0)

    # -----------------------------------------------------------------
    # Confirmation dialog (reused by the power menu)
    # -----------------------------------------------------------------
    def _open_confirm_dialog(self, title, message, confirm_label, callback):
        if getattr(self, "search_state", None):
            self._close_search()
        if getattr(self, "wifi_auth_state", None):
            self._close_wifi_auth()
        self._close_active_menu()
        width = 360
        height = 150
        x = max(0, (self.screen_w - width) // 2)
        y = max(0, (self.screen_h - self.TASKBAR_H - height) // 2)
        win = self._create_window(
            self.root,
            x,
            y,
            width,
            height,
            self.colors["surface"],
            self.colors["border"],
            override_redirect=True,
        )
        self._own_windows.add(win.id)
        win.change_attributes(
            background_pixel=self.colors["surface"],
            border_pixel=self.colors["border"],
            event_mask=X.ButtonPressMask | X.ExposureMask | X.KeyPressMask,
        )
        win.map()
        try:
            win.configure(stack_mode=X.Above)
        except Exception:
            pass
        self.confirm_state = {
            "title": title,
            "message": message,
            "confirm_label": confirm_label,
            "callback": callback,
            "window": win,
            "width": width,
            "height": height,
            "confirm_rect": None,
            "cancel_rect": None,
        }
        try:
            self.display.set_input_focus(win, X.RevertToParent, X.CurrentTime)
        except Exception:
            pass
        self._redraw_confirm_dialog()
        self.display.flush()

    def _close_confirm_dialog(self):
        st = getattr(self, "confirm_state", None)
        if not st:
            return
        win = st.get("window")
        if win is not None:
            try:
                self._own_windows.discard(win.id)
                win.destroy()
            except Exception:
                pass
        self.confirm_state = None
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

    def _redraw_confirm_dialog(self):
        st = getattr(self, "confirm_state", None)
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
        accent_hex = self.current_palette.get("accent", "#5e81ac")
        accent_hot_hex = self.current_palette.get("accent_hot", "#81a1c1")
        select_hex = self.current_palette.get("select", "#4c566a")

        panel_rgb = self._hex_to_rgb(panel_hex)
        panel_line_rgb = self._hex_to_rgb(panel_line_hex)
        text_rgb = self._hex_to_rgb(text_hex)
        text_dim_rgb = self._hex_to_rgb(text_dim_hex)
        accent_rgb = self._hex_to_rgb(accent_hex)
        accent_hot_rgb = self._hex_to_rgb(accent_hot_hex)
        select_rgb = self._hex_to_rgb(select_hex)

        gc_bg = self._gc(win, self.colors["surface"], self.colors["surface"])
        win.fill_rectangle(gc_bg, 0, 0, width, height)

        # Draw border like Cadet
        gc_border = self._gc(win, self.colors["border"], self.colors["surface"])
        win.rectangle(gc_border, 0, 0, width, height)
        win.rectangle(gc_border, 0, 0, 1, height)
        win.rectangle(gc_border, width - 1, 0, 1, height)
        win.rectangle(gc_border, 0, height - 1, width, 1)

        self._draw_text_pixels(
            win, 18, 16, st["title"][:40], text_hex, panel_hex, padding=1
        )
        self._draw_text_pixels(
            win, 18, 52, st["message"][:52], text_dim_hex, panel_hex, padding=1
        )

        btn_y = height - 40
        confirm_w, confirm_h = 96, 28
        cancel_w, cancel_h = 76, 28
        confirm_x = width - 18 - confirm_w
        cancel_x = confirm_x - 12 - cancel_w

        # Confirm button - Cadet accent style
        confirm_img = Image.new("RGB", (confirm_w, confirm_h), panel_rgb)
        cd = ImageDraw.Draw(confirm_img)
        cd.rounded_rectangle(
            (0, 0, confirm_w - 1, confirm_h - 1),
            radius=6,
            fill=accent_rgb,
        )
        font = ImageFont.load_default()
        try:
            bb = cd.textbbox((0, 0), st["confirm_label"], font=font)
            lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            lw, lh = cd.textsize(st["confirm_label"], font=font)
        cd.text(
            ((confirm_w - lw) // 2, (confirm_h - lh) // 2),
            st["confirm_label"],
            fill=(255, 255, 255),
            font=font,
        )
        gc = self._gc(win, self.colors["text"], self.colors["surface"])
        win.put_pil_image(gc, confirm_x, btn_y, confirm_img)

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

        st["confirm_rect"] = (
            confirm_x,
            btn_y,
            confirm_x + confirm_w,
            btn_y + confirm_h,
        )
        st["cancel_rect"] = (cancel_x, btn_y, cancel_x + cancel_w, btn_y + cancel_h)
        self.display.flush()

    def _handle_confirm_keypress(self, event):
        st = self.confirm_state
        if st is None:
            return
        try:
            keysym = self.display.keycode_to_keysym(event.detail, 0)
        except Exception:
            return
        if keysym == XK.XK_Escape:
            self._close_confirm_dialog()
        elif keysym in (XK.XK_Return, XK.XK_KP_Enter):
            self._confirm_dialog_confirm()

    def _handle_confirm_click(self, event):
        st = getattr(self, "confirm_state", None)
        if not st:
            return
        cx0, cy0, cx1, cy1 = st.get("cancel_rect") or (0, 0, 0, 0)
        if cx0 <= event.event_x < cx1 and cy0 <= event.event_y < cy1:
            self._close_confirm_dialog()
            return
        nx0, ny0, nx1, ny1 = st.get("confirm_rect") or (0, 0, 0, 0)
        if nx0 <= event.event_x < nx1 and ny0 <= event.event_y < ny1:
            self._confirm_dialog_confirm()

    def _confirm_dialog_confirm(self):
        st = getattr(self, "confirm_state", None)
        if not st:
            return
        cb = st.get("callback")
        self._close_confirm_dialog()
        if cb:
            try:
                cb()
            except Exception as exc:
                print(f"Pillarium: confirm action failed: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Window context menu
    # -----------------------------------------------------------------
    def _is_pinned(self, data):
        label = data.get("title", "app")
        cmd_guess = [label.lower()]
        for item in self.quick_launch:
            if item.get("label") == label or item.get("cmd") == cmd_guess:
                return True
        return False

    def _open_window_menu(self, client_id, anchor_x, anchor_y):
        data = self.frames.get(client_id)
        if not data:
            return
        if (
            getattr(self, "active_menu", None)
            and self.active_menu.get("kind") == "window"
            and self.active_menu.get("client_id") == client_id
        ):
            self._close_active_menu()
            return
        self._close_active_menu()
        pinned = self._is_pinned(data)
        try:
            tb_idx = self.taskbar_items.index(client_id)
        except ValueError:
            tb_idx = -1
        items = [
            {"label": "Move Left", "enabled": tb_idx > 0, "action": ("window", ("move_left", client_id))},
            {"label": "Move Right", "enabled": 0 <= tb_idx < len(self.taskbar_items) - 1, "action": ("window", ("move_right", client_id))},
            {"label": "Restore" if data.get("minimized") else "Minimize", "action": ("window", ("minimize_toggle", client_id))},
            {"label": "Restore" if data.get("maximized") else "Maximize", "action": ("window", ("maximize", client_id))},
            {"label": "Remove from Quick Launch" if pinned else "Add to Quick Launch", "action": ("window", ("pin_toggle", client_id))},
            {"label": "Close Window", "action": ("window", ("close", client_id))},
        ]
        self._open_menu("window", items, anchor_x, 0, anchor_y=anchor_y, client_id=client_id)

    def _window_menu_action(self, payload):
        op, client_id = payload
        data = self.frames.get(client_id)
        if not data:
            return
        if op == "minimize_toggle":
            if data.get("minimized"):
                self._restore_window(client_id)
            else:
                self._minimize_window(client_id)
        elif op == "move_left":
            if client_id in self.taskbar_items:
                i = self.taskbar_items.index(client_id)
                if i > 0:
                    self.taskbar_items[i - 1], self.taskbar_items[i] = (
                        self.taskbar_items[i],
                        self.taskbar_items[i - 1],
                    )
                    self._redraw_taskbar()
        elif op == "move_right":
            if client_id in self.taskbar_items:
                i = self.taskbar_items.index(client_id)
                if i < len(self.taskbar_items) - 1:
                    self.taskbar_items[i], self.taskbar_items[i + 1] = (
                        self.taskbar_items[i + 1],
                        self.taskbar_items[i],
                    )
                    self._redraw_taskbar()
        elif op == "maximize":
            self._toggle_maximize(client_id)
        elif op == "close":
            self._close_window(client_id)
        elif op == "pin_toggle":
            label = data.get("title", "app")
            cmd_guess = [label.lower()]
            found = None
            for qi, item in enumerate(self.quick_launch):
                if item.get("label") == label or item.get("cmd") == cmd_guess:
                    found = qi
                    break
            if found is None:
                self.quick_launch.append({"cmd": cmd_guess, "label": label})
            else:
                try:
                    self.quick_launch.pop(found)
                except Exception:
                    pass
            self._save_config()
            self._redraw_taskbar()
