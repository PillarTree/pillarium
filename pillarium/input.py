"""Input handling: pointer buttons/motion, key presses, focus,
window lifecycle (close / minimise / restore / maximise)."""

import os
import sys
import time
from Xlib import X, XK
from Xlib import Xcursorfont as cursorfont
from Xlib.protocol import request


class InputMixin:
    # -----------------------------------------------------------------
    # ButtonPress handling (mouse clicks)
    # -----------------------------------------------------------------
    def _handle_button_press(self, event):
        target = event.window

        # -------------------------------------------------------------
        # If a popup menu (power/wifi) is open, route the click there
        # -------------------------------------------------------------
        active_menu = getattr(self, "active_menu", None)
        if active_menu:
            if target.id == active_menu["window"].id:
                self._handle_menu_click(event)
                return
            else:
                self._close_active_menu()
                # fall through so the click is also processed normally

        # -------------------------------------------------------------
        # If the confirmation dialog is open, route the click there
        # -------------------------------------------------------------
        confirm_state = getattr(self, "confirm_state", None)
        if confirm_state and confirm_state.get("window"):
            if target.id == confirm_state["window"].id:
                self._handle_confirm_click(event)
                return
            else:
                self._close_confirm_dialog()
                # fall through so the click is also processed normally

        # -------------------------------------------------------------
        # If the Wi‑Fi password dialog is open, route the click there
        # -------------------------------------------------------------
        wifi_auth = getattr(self, "wifi_auth_state", None)
        if wifi_auth and wifi_auth.get("window"):
            if target.id == wifi_auth["window"].id:
                self._handle_wifi_auth_click(event)
                return
            else:
                self._close_wifi_auth()
                # fall through so the click is also processed normally

        # -------------------------------------------------------------
        # If the search popup is open, route the click there or dismiss it
        # -------------------------------------------------------------
        search_state = getattr(self, "search_state", None)
        if search_state and search_state.get("window"):
            if target.id == search_state["window"].id:
                row_h = search_state["row_h"]
                # -------------------------------------------------
                # Mouse‑wheel scrolling inside the popup
                # -------------------------------------------------
                if getattr(event, "detail", None) in (4, 5):
                    self._search_scroll(-1 if event.detail == 4 else 1)
                    return
                # Scrollbar track / thumb clicks and drags
                sb_hit = self._search_scrollbar_hit(
                    event.event_x,
                    event.event_y,
                )
                if sb_hit == "thumb":
                    self.search_scroll_drag = {
                        "start_y": event.event_y,
                        "start_offset": search_state.get("offset", 0),
                    }
                    return
                if sb_hit == "track":
                    self._search_scroll_to_click(event.event_y)
                    return
                # -------------------------------------------------
                # Click inside the result list – launch the entry
                # -------------------------------------------------
                if event.event_y >= row_h:
                    for idx, (y0, y1, item) in enumerate(search_state.get("result_rects", [])):
                        if y0 <= event.event_y < y1:
                            search_state["selected"] = search_state.get("offset", 0) + idx
                            try:
                                self._launch_command(item.get("cmd"))
                            except Exception as e:
                                print(f"Pillarium: Search launch error: {e}", file=sys.stderr)
                            self._close_search()
                            return
                # Click elsewhere inside the popup – keep it open
                return
            else:
                self._close_search()
                # fall through to normal handling

        # -------------------------------------------------------------
        # If the audio mixer popup is open, route the click there or
        # dismiss it
        # -------------------------------------------------------------
        mixer_state = getattr(self, "mixer_state", None)
        if mixer_state and mixer_state.get("window"):
            if target.id == mixer_state["window"].id:
                self._handle_mixer_click(event)
                return
            else:
                self._close_mixer()
                # fall through so the click is also processed normally

        # -------------------------------------------------------------
        # If the clock calendar panel is open, route the click there or
        # dismiss it
        # -------------------------------------------------------------
        clock_state = getattr(self, "clock_state", None)
        if clock_state and clock_state.get("window"):
            if target.id == clock_state["window"].id:
                self._handle_clock_click(event)
                return
            else:
                self._close_clock_menu()
                # fall through so the click is also processed normally

        # -------------------------------------------------------------
        # If the process list panel is open, route the click there or
        # dismiss it
        # -------------------------------------------------------------
        process_state = getattr(self, "process_state", None)
        if process_state and process_state.get("window"):
            if target.id == process_state["window"].id:
                self._handle_process_click(event)
                return
            else:
                self._close_processes()
                # fall through so the click is also processed normally

        # -------------------------------------------------------------
        # Desktop icons (drawn on the dedicated desktop window)
        # -------------------------------------------------------------
        if target.id == self.desktop_win.id:
            idx = self._desktop_icon_at(event.event_x, event.event_y)
            now = time.time()
            last = self._desktop_last_click
            if idx is not None:
                if last.get("idx") == idx and (now - last.get("time", 0.0)) < 0.5:
                    cmd = self.desktop_icons[idx].get("cmd")
                    try:
                        self._launch_command(cmd)
                    except Exception as e:
                        print(
                            f"Pillarium: failed to launch desktop icon {cmd}: {e}",
                            file=sys.stderr,
                        )
                    self._desktop_selected = None
                else:
                    self._desktop_selected = idx
            else:
                self._desktop_selected = None
            self._desktop_last_click = {"idx": idx, "time": now}
            self._redraw_desktop_icons()
            return

        # -------------------------------------------------------------
        # Task‑bar clicks
        # -------------------------------------------------------------
        if getattr(self, "taskbar", None) and target.id == self.taskbar.id:
            right_zone_start = self.screen_w - self._taskbar_right_zone_w()

            # ---------------------------------------------------------
            # Search button (far left)
            # ---------------------------------------------------------
            if event.event_x < self.SEARCH_W:
                self._toggle_search()
                return

            # ---------------------------------------------------------
            # Right‑hand widgets / power / wifi / clock
            # ---------------------------------------------------------
            if event.event_x >= right_zone_start:
                custom_widgets_x = right_zone_start
                power_x = custom_widgets_x + (len(self.custom_widgets) * self.CUSTOM_WIDGET_W)
                bluetooth_x = power_x + self.POWER_W
                audio_x = bluetooth_x + self.BLUETOOTH_W
                wifi_x = audio_x + self.AUDIO_W
                battery_x = wifi_x + self.WIFI_W
                clock_x = battery_x + self.BATTERY_W
                if event.event_x < power_x:
                    widget_idx = (event.event_x - custom_widgets_x) // self.CUSTOM_WIDGET_W
                    self._custom_widget_action(widget_idx)
                elif power_x <= event.event_x < bluetooth_x:
                    self._toggle_power_menu(power_x)
                elif bluetooth_x <= event.event_x < audio_x:
                    self._toggle_bluetooth_menu(bluetooth_x)
                elif audio_x <= event.event_x < wifi_x:
                    self._toggle_audio_menu(audio_x)
                elif wifi_x <= event.event_x < battery_x:
                    self._toggle_wifi_menu(wifi_x)
                elif battery_x <= event.event_x < clock_x:
                    self._toggle_battery_menu(battery_x)
                else:
                    self._toggle_clock_menu(clock_x)
                return

            # ---------------------------------------------------------
            # Quick‑launch area (just right of the search button)
            # ---------------------------------------------------------
            q_start = self.SEARCH_W
            q_width = self._taskbar_quick_launch_w()
            if event.event_x < q_start + q_width:
                idx = (event.event_x - q_start) // 48
                if 0 <= idx < len(self.quick_launch):
                    cmd = self.quick_launch[idx]["cmd"]
                    try:
                        self._launch_command(cmd)
                    except Exception as e:
                        print(
                            f"Failed to launch quick‑launch {cmd}: {e}",
                            file=sys.stderr,
                        )
                return

            # ---------------------------------------------------------
            # Managed windows (task‑bar items)
            # ---------------------------------------------------------
            client_id = self._taskbar_item_at(event.event_x)
            if client_id is None:
                return
            if client_id in self.frames:
                data = self.frames[client_id]
                # Right‑click opens the window menu
                if getattr(event, "detail", None) == 3:
                    self._open_window_menu(client_id, event.root_x, event.root_y)
                    return
                # Left‑click – minimise / focus / restore
                if data.get("minimized"):
                    self._restore_window(client_id)
                else:
                    if self.focused_client == client_id:
                        self._minimize_window(client_id)
                    else:
                        try:
                            data["frame"].configure(stack_mode=X.Above)
                        except Exception:
                            pass
                        self._focus_window(client_id)
                self._redraw_taskbar()
            return

        # -------------------------------------------------------------
        # Clicks inside any managed client / frame hierarchy
        # -------------------------------------------------------------
        client_id = self._client_for_window(target)
        if client_id is not None and client_id in self.frames:
            data = self.frames[client_id]
            target_id = target.id

            # Any click on a part of the window focuses it
            self._focus_window(data["frame"])

            if target_id == data["resize_handle"].id:
                self.drag_state = {
                    "client_id": client_id,
                    "mode": "resize",
                    "start_x": event.root_x,
                    "start_y": event.root_y,
                    "start_width": data["width"],
                    "start_height": data["height"],
                }
                self._grab_pointer(cursorfont.bottom_right_corner)
                return
            if target_id == data["close_button"].id:
                self._close_window(client_id)
                return
            if target_id == data["maximize_button"].id:
                self._toggle_maximize(client_id)
                return
            if target_id == data["minimize_button"].id:
                self._minimize_window(client_id)
                return
            if target_id == data["titlebar"].id:
                if getattr(event, "detail", None) == 3:
                    self._open_window_menu(client_id, event.root_x, event.root_y)
                    return
                now = time.time()
                last = self._titlebar_last_click
                if (
                    last.get("client_id") == client_id
                    and (now - last.get("time", 0.0)) < 0.4
                ):
                    self._titlebar_last_click = {"client_id": None, "time": 0.0}
                    self._toggle_maximize(client_id)
                    return
                self._titlebar_last_click = {"client_id": client_id, "time": now}
                self.drag_state = {
                    "client_id": client_id,
                    "start_x": event.root_x,
                    "start_y": event.root_y,
                    "frame_x": data["x"],
                    "frame_y": data["y"],
                }
                self._grab_pointer(cursorfont.fleur)
                if os.environ.get("PILLARIUM_DEBUG"):
                    print(
                        f"DEBUG press titlebar client={client_id} root=({event.root_x},{event.root_y}) "
                        f"frame=({data['x']},{data['y']})",
                        file=sys.stderr,
                    )
                return
            return

    # -----------------------------------------------------------------
    # ButtonRelease (reset drag state)
    # -----------------------------------------------------------------
    def _handle_button_release(self, event):
        self._ungrab_pointer()
        self.drag_state = None
        self.search_scroll_drag = None
        self.mixer_drag = None

    # -----------------------------------------------------------------
    # MotionNotify (dragging or hover)
    # -----------------------------------------------------------------
    def _handle_motion(self, event):
        if getattr(self, "mixer_drag", None) and getattr(
            self, "mixer_state", None
        ):
            st = self.mixer_state
            local_x = event.root_x - st.get("x", 0)
            self._audio_set_node_volume(
                self.mixer_drag["node"],
                self._mixer_vol_from_x(local_x),
            )
            self._redraw_mixer()
            return

        if getattr(self, "search_scroll_drag", None) and getattr(
            self, "search_state", None
        ):
            self._search_scroll_drag(event.event_y)
            return

        if not self.drag_state:
            self._handle_hover_motion(event)
            return

        client_id = self.drag_state["client_id"]
        data = self.frames.get(client_id)
        if not data:
            self.drag_state = None
            return

        dx = event.root_x - self.drag_state["start_x"]
        dy = event.root_y - self.drag_state["start_y"]

        if os.environ.get("PILLARIUM_DEBUG"):
            print(
                f"DEBUG motion win={event.window.id} root=({event.root_x},{event.root_y}) "
                f"dx={dx} dy={dy} mode={self.drag_state.get('mode')}",
                file=sys.stderr,
            )

        if self.drag_state.get("mode") == "resize":
            # Resize from the lower‑right grip while keeping the top‑left corner fixed.
            max_width = max(self.MIN_WINDOW_W, self.screen_w - data["x"])
            max_height = max(
                self.MIN_WINDOW_H,
                self.screen_h - data["y"] - self.TASKBAR_H,
            )
            data["width"] = max(
                self.MIN_WINDOW_W,
                min(max_width, self.drag_state["start_width"] + dx),
            )
            data["height"] = max(
                self.MIN_WINDOW_H,
                min(max_height, self.drag_state["start_height"] + dy),
            )
            data["maximized"] = False
            data["restore_geom"] = None
        else:
            frame_h = data["height"] + self.TITLEBAR_H + (self.BORDER * 2)
            data["x"] = max(
                0, min(self.screen_w - data["width"], self.drag_state["frame_x"] + dx)
            )
            data["y"] = max(
                0,
                min(
                    max(0, self.screen_h - self.TASKBAR_H - frame_h),
                    self.drag_state["frame_y"] + dy,
                ),
            )

        self._place_frame(client_id)

    # -----------------------------------------------------------------
    # Pointer grab (keeps drag alive even when the cursor leaves the
    # titlebar / resize handle, and routes all motion to the WM)
    # -----------------------------------------------------------------
    def _ensure_cursor(self, cursor_shape):
        try:
            if not self._cursor_font:
                self._cursor_font = self.display.open_font("cursor")
            if cursor_shape not in self._cursors:
                self._cursors[cursor_shape] = self.display.create_glyph_cursor(
                    self._cursor_font,
                    self._cursor_font,
                    cursor_shape,
                    cursor_shape + 1,
                    (65535, 65535, 65535),
                    (0, 0, 0),
                )
        except Exception:
            pass
        return self._cursors.get(cursor_shape)

    def _grab_pointer(self, cursor_shape=None):
        try:
            cursor = (
                self._ensure_cursor(cursor_shape)
                if cursor_shape is not None
                else X.NONE
            )
            grab = request.GrabPointer(
                display=self.display.display,
                owner_events=False,
                grab_window=self.root,
                event_mask=(
                    X.ButtonPressMask
                    | X.ButtonReleaseMask
                    | X.PointerMotionMask
                ),
                pointer_mode=X.GrabModeAsync,
                keyboard_mode=X.GrabModeAsync,
                confine_to=X.NONE,
                cursor=cursor if cursor is not None else X.NONE,
                time=X.CurrentTime,
            )
            if getattr(grab, "status", X.GrabSuccess) != X.GrabSuccess:
                print(
                    f"Pillarium: pointer grab failed status={grab.status}",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(
                f"Pillarium: pointer grab error: {exc}",
                file=sys.stderr,
            )

    def _ungrab_pointer(self):
        try:
            self.display.ungrab_pointer(X.CurrentTime)
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Enter handling. Focus is click-to-focus, not focus-follows-mouse.
    # -----------------------------------------------------------------
    def _handle_enter(self, window):
        if window.id == self.desktop_win.id:
            self._set_window_cursor(self.desktop_win, cursorfont.left_ptr)
        elif getattr(self, "taskbar", None) and window.id == self.taskbar.id:
            self._set_window_cursor(self.taskbar, cursorfont.left_ptr)

    # -----------------------------------------------------------------
    # Leave handling (reset hover cursors)
    # -----------------------------------------------------------------
    def _handle_leave(self, window):
        if window.id == self.desktop_win.id:
            if getattr(self, "_desktop_hover", None) is not None:
                self._desktop_hover = None
                self._redraw_desktop_icons()
            self._set_window_cursor(self.desktop_win, cursorfont.left_ptr)
        elif getattr(self, "taskbar", None) and window.id == self.taskbar.id:
            self._set_window_cursor(self.taskbar, cursorfont.left_ptr)

    # -----------------------------------------------------------------
    # Hover motion (change cursor / highlight)
    # -----------------------------------------------------------------
    def _handle_hover_motion(self, event):
        # Desktop icons: hand cursor + hover highlight when over an icon
        if event.window.id == self.desktop_win.id:
            idx = self._desktop_icon_at(event.event_x, event.event_y)
            self._set_window_cursor(
                self.desktop_win,
                cursorfont.hand2 if idx is not None else cursorfont.left_ptr,
            )
            if idx != getattr(self, "_desktop_hover", None):
                self._desktop_hover = idx
                self._redraw_desktop_icons()
            return

        # Task‑bar: hand cursor over anything clickable, arrow over dead space
        if getattr(self, "taskbar", None) and event.window.id == self.taskbar.id:
            clickable = self._taskbar_hit_kind(event.event_x) is not None
            self._set_window_cursor(
                self.taskbar, cursorfont.hand2 if clickable else cursorfont.left_ptr
            )
            return

    # -----------------------------------------------------------------
    # Window hierarchy helpers
    # -----------------------------------------------------------------
    def _frame_window_ids(self, data):
        return {
            data["frame"].id,
            data["titlebar"].id,
            data["container"].id,
            data["client"].id,
            data["close_button"].id,
            data["minimize_button"].id,
            data["maximize_button"].id,
            data["resize_handle"].id,
        }

    def _client_for_window(self, window):
        """Map any window in a managed hierarchy to its client id."""
        try:
            win_id = window.id
        except Exception:
            return None

        for client_id, data in self.frames.items():
            if win_id in self._frame_window_ids(data):
                return client_id

        try:
            current = window
            for _ in range(64):
                qt = current.query_tree()
                parent = qt.parent
                if parent is None or parent.id == self.root.id:
                    break
                for client_id, data in self.frames.items():
                    if parent.id == data["client"].id:
                        return client_id
                    if parent.id in self._frame_window_ids(data):
                        return client_id
                current = parent
        except Exception:
            pass
        return None

    def _enable_subwindow_focus(self, window):
        """Ensure nested client subwindows notify the WM on click."""
        try:
            window.change_attributes(
                event_mask=(
                    X.ButtonPressMask
                    | X.ButtonReleaseMask
                    | X.StructureNotifyMask
                    | X.SubstructureNotifyMask
                )
            )
            for child in window.query_tree().children:
                self._enable_subwindow_focus(child)
        except Exception:
            pass

    def _watch_client_subwindows(self, client):
        try:
            for child in client.query_tree().children:
                self._enable_subwindow_focus(child)
        except Exception:
            pass

    def _handle_create_notify(self, event):
        client_id = self._client_for_window(event.parent)
        if client_id is not None:
            self._enable_subwindow_focus(event.window)

    # -----------------------------------------------------------------
    # KeyPress handling (global shortcuts, search keys, etc.)
    # -----------------------------------------------------------------
    def _handle_key_press(self, event):
        # Alt+Space is a root‑level grab, so it must be handled before normal client/key processing.
        if getattr(self, "key_search", None) and event.detail == self.key_search:
            mods = event.state & (X.Mod1Mask | X.ShiftMask | X.ControlMask)
            if (event.state & X.Mod1Mask) and not (event.state & (X.ShiftMask | X.ControlMask)):
                self._toggle_search()
                return

        # When the audio mixer popup has focus, Esc closes it.
        if getattr(self, "mixer_state", None):
            try:
                keysym = self.display.keycode_to_keysym(event.detail, 0)
            except Exception:
                keysym = None
            if keysym == XK.XK_Escape:
                self._close_mixer()
                return

        # When the clock calendar panel has focus, Esc closes it.
        if getattr(self, "clock_state", None):
            try:
                keysym = self.display.keycode_to_keysym(event.detail, 0)
            except Exception:
                keysym = None
            if keysym == XK.XK_Escape:
                self._close_clock_menu()
                return

        # When the process list panel has focus, Esc closes it.
        if getattr(self, "process_state", None):
            try:
                keysym = self.display.keycode_to_keysym(event.detail, 0)
            except Exception:
                keysym = None
            if keysym == XK.XK_Escape:
                self._close_processes()
                return

        # When the confirmation dialog has focus, all keys go there.
        if getattr(self, "confirm_state", None) is not None:
            self._handle_confirm_keypress(event)
            return

        # When the Wi‑Fi password dialog has focus, all typing goes there.
        if getattr(self, "wifi_auth_state", None) is not None:
            self._handle_wifi_auth_keypress(event)
            return

        # When the search popup has focus, all typing goes there.
        if getattr(self, "search_state", None) is not None:
            self._handle_search_keypress(event)
            return

        # Toggle dark mode (Alt+Shift+D)
        if (
            hasattr(self, "key_toggle_dark")
            and event.detail == self.key_toggle_dark
            and (event.state & (self.mod_mask | X.ShiftMask))
            == (self.mod_mask | X.ShiftMask)
        ):
            self.dark_mode = not self.dark_mode
            self._apply_palette()
            # Update theme on all windows
            for client_id, data in self.frames.items():
                data["frame"].change_attributes(
                    background_pixel=self.colors["surface"],
                    border_pixel=self.colors["border"],
                )
                data["titlebar"].change_attributes(
                    background_pixel=self.colors["titlebar"],
                    border_pixel=self.colors["border"],
                )
                data["container"].change_attributes(
                    background_pixel=self.colors["surface"],
                    border_pixel=self.colors["border"],
                )
                data["close_button"].change_attributes(
                    background_pixel=self.colors["accent"],
                    border_pixel=self.colors["border"],
                )
                data["minimize_button"].change_attributes(
                    background_pixel=self.colors["titlebar_alt"],
                    border_pixel=self.colors["border"],
                )
                data["maximize_button"].change_attributes(
                    background_pixel=self.colors["titlebar_alt"],
                    border_pixel=self.colors["border"],
                )
                self._redraw_window(data["titlebar"])
                self._redraw_window(data["frame"])
                self._redraw_window(data["close_button"])
                self._redraw_window(data["minimize_button"])
                self._redraw_window(data["maximize_button"])
                self._redraw_window(data["container"])
            self.taskbar.change_attributes(
                background_pixel=self.colors["taskbar"],
                border_pixel=self.colors["border"],
            )
            self._redraw_taskbar()
            self.display.flush()
            return

        # Alt+Space (again – might have been grabbed with modifiers)
        if (
            hasattr(self, "key_search")
            and self.key_search
            and event.detail == self.key_search
            and (event.state & self.mod_mask)
        ):
            self._toggle_search()
            return

        # Alt+Enter – launch a terminal
        if event.detail == self.key_terminal and (event.state & self.mod_mask):
            self._launch_terminal()
            return

        # Alt+q – open quick‑launch config editor
        if (
            hasattr(self, "key_quick_config")
            and self.key_quick_config
            and event.detail == self.key_quick_config
            and (event.state & self.mod_mask)
        ):
            try:
                self._open_quicklaunch_editor()
            except Exception as e:
                print(f"Could not open quick‑launch editor: {e}", file=sys.stderr)
            return

        # Alt+Shift+P – power menu
        if (
            hasattr(self, "key_power")
            and self.key_power
            and event.detail == self.key_power
            and (event.state & (self.mod_mask | X.ShiftMask))
            == (self.mod_mask | X.ShiftMask)
        ):
            anchor_x = self.screen_w - (
                self.BLUETOOTH_W + self.AUDIO_W + self.WIFI_W
                + self.BATTERY_W + self.CLOCK_W
                + self.POWER_W + len(self.custom_widgets) * self.CUSTOM_WIDGET_W
            )
            self._toggle_power_menu(anchor_x)
            return

        # Alt+Shift+W – Wi‑Fi menu
        if (
            hasattr(self, "key_wifi")
            and self.key_wifi
            and event.detail == self.key_wifi
            and (event.state & (self.mod_mask | X.ShiftMask))
            == (self.mod_mask | X.ShiftMask)
        ):
            anchor_x = self.screen_w - (
                self.WIFI_W + self.BATTERY_W + self.CLOCK_W
            )
            self._toggle_wifi_menu(anchor_x)
            return

        # Alt+Shift+B – Bluetooth menu
        if (
            hasattr(self, "key_bluetooth")
            and self.key_bluetooth
            and event.detail == self.key_bluetooth
            and (event.state & (self.mod_mask | X.ShiftMask))
            == (self.mod_mask | X.ShiftMask)
        ):
            anchor_x = self.screen_w - (
                self.BLUETOOTH_W + self.AUDIO_W + self.WIFI_W
                + self.BATTERY_W + self.CLOCK_W
            )
            self._toggle_bluetooth_menu(anchor_x)
            return

        # Alt+Shift+A – audio menu
        if (
            hasattr(self, "key_audio")
            and self.key_audio
            and event.detail == self.key_audio
            and (event.state & (self.mod_mask | X.ShiftMask))
            == (self.mod_mask | X.ShiftMask)
        ):
            anchor_x = self.screen_w - (
                self.AUDIO_W + self.WIFI_W + self.BATTERY_W + self.CLOCK_W
            )
            self._toggle_audio_menu(anchor_x)
            return

        # Alt+Shift+M – process list
        if (
            hasattr(self, "key_processes")
            and self.key_processes
            and event.detail == self.key_processes
            and (event.state & (self.mod_mask | X.ShiftMask))
            == (self.mod_mask | X.ShiftMask)
        ):
            self._toggle_processes()
            return

        # Alt+Shift+R – refresh desktop icons
        if (
            hasattr(self, "key_refresh_desktop")
            and self.key_refresh_desktop
            and event.detail == self.key_refresh_desktop
            and (event.state & (self.mod_mask | X.ShiftMask))
            == (self.mod_mask | X.ShiftMask)
        ):
            self._refresh_desktop_icons()
            return

        # Alt+F4 – close focused window
        if event.detail == self.key_quit and (event.state & self.mod_mask):
            if self.focused_client in self.frames:
                self._close_window(self.focused_client)
            return

    # -----------------------------------------------------------------
    # Focus handling (keyboard / mouse)
    # -----------------------------------------------------------------
    def _focus_window(self, window):
        """Activate a managed client by clicking it or one of its decorations."""
        client_id = None

        if isinstance(window, int):
            if window in self.frames:
                client_id = window
        else:
            try:
                window_id = window.id
            except Exception:
                window_id = None

            for cid, data in self.frames.items():
                if window_id in {
                    data["frame"].id,
                    data["titlebar"].id,
                    data["container"].id,
                    data["close_button"].id,
                    data["minimize_button"].id,
                    data["maximize_button"].id,
                    data["resize_handle"].id,
                    data["client"].id,
                }:
                    client_id = cid
                    break

        if client_id is None:
            return

        data = self.frames.get(client_id)
        if not data or data.get("minimized"):
            return

        old_client = self.focused_client
        self.focused_client = client_id

        try:
            if hasattr(data["frame"], "raise_window"):
                data["frame"].raise_window()
            else:
                data["frame"].configure(stack_mode=X.Above)
        except Exception:
            pass

        try:
            # Keyboard input must go to the actual application window.
            self.display.set_input_focus(
                data["client"],
                X.RevertToParent,
                X.CurrentTime,
            )
        except Exception as exc:
            print(
                f"Pillarium: could not focus client {client_id}: {exc}",
                file=sys.stderr,
            )

        if old_client in self.frames and old_client != client_id:
            try:
                self._redraw_window(self.frames[old_client]["titlebar"])
            except Exception:
                pass

        try:
            self._redraw_window(data["titlebar"])
        except Exception:
            pass

        self._redraw_taskbar()

        try:
            self._ensure_taskbar_on_top()
        except Exception:
            pass

        self.display.flush()

    # -----------------------------------------------------------------
    # Window lifecycle helpers (close / minimise / restore / maximise)
    # -----------------------------------------------------------------
    def _close_window(self, client_id):
        if client_id not in self.frames:
            return
        data = self.frames[client_id]
        try:
            data["client"].destroy()
        except Exception:
            pass
        self._forget_window(data["client"])

    def _minimize_window(self, client_id):
        data = self.frames.get(client_id)
        if not data or data.get("minimized"):
            return
        try:
            data["client"].unmap()
        except Exception:
            pass
        try:
            data["frame"].unmap()
        except Exception:
            pass
        data["minimized"] = True
        self._redraw_taskbar()
        self._redraw_desktop_icons()

    def _restore_window(self, client_id):
        data = self.frames.get(client_id)
        if not data or not data.get("minimized"):
            return
        try:
            self._reparent_client(data["client"], data["container"])
            data["frame"].map()
            # Ensure task‑bar stays on top after restoring
            try:
                self._ensure_taskbar_on_top()
            except Exception:
                pass
            data["minimized"] = False
            self._place_frame(client_id)
            self._redraw_taskbar()
        except Exception:
            pass

    def _toggle_maximize(self, client_id):
        data = self.frames.get(client_id)
        if not data:
            return
        if data.get("maximized"):
            geom = data.get("restore_geom")
            if geom:
                data["x"], data["y"], data["width"], data["height"] = geom
            data["maximized"] = False
        else:
            data["restore_geom"] = (
                data["x"],
                data["y"],
                data["width"],
                data["height"],
            )
            data["x"] = 0
            data["y"] = 0
            data["width"] = self.screen_w
            data["height"] = max(
                100,
                self.screen_h - self.TASKBAR_H - self.TITLEBAR_H - (self.BORDER * 2),
            )
            data["maximized"] = True
        self._place_frame(client_id)
        self._redraw_desktop_icons()

    # -----------------------------------------------------------------
    # Forget a client (when it is destroyed/unmapped)
    # -----------------------------------------------------------------
    def _forget_window(self, window):
        for client_id, data in list(self.frames.items()):
            if window.id in {
                data["client"].id,
                data["frame"].id,
                data["titlebar"].id,
                data["container"].id,
                data["close_button"].id,
                data["minimize_button"].id,
                data["maximize_button"].id,
            }:
                try:
                    data["frame"].destroy()
                except Exception:
                    pass
                self.frames.pop(client_id, None)
                if client_id in self.taskbar_items:
                    try:
                        self.taskbar_items.remove(client_id)
                    except Exception:
                        pass
                    self._redraw_taskbar()
                if self.focused_client == client_id:
                    self.focused_client = None
                self._redraw_desktop_icons()
                break

    # -----------------------------------------------------------------
    # Title reading (WM_NAME / _NET_WM_NAME)
    # -----------------------------------------------------------------
    def _read_title(self, client):
        try:
            wm_name = client.get_wm_name()
            if wm_name:
                return wm_name
            atom = self.display.intern_atom("_NET_WM_NAME")
            prop = client.get_full_property(atom, X.AnyPropertyType)
            if prop and prop.value:
                try:
                    return (
                        prop.value.decode("utf-8")
                        if isinstance(prop.value, bytes)
                        else str(prop.value)
                    )
                except Exception:
                    return str(prop.value)
        except Exception:
            pass
        return "Pillarium"

    # -----------------------------------------------------------------
    # Property change handling (title / icon updates)
    # -----------------------------------------------------------------
    def _handle_property_change(self, window, atom_name):
        for client_id, data in self.frames.items():
            if window.id == data["client"].id:
                if atom_name in ("WM_NAME", "_NET_WM_NAME"):
                    data["title"] = self._read_title(data["client"])
                    self._redraw_window(data["titlebar"])
                    self._redraw_taskbar()
                elif atom_name == "_NET_WM_ICON":
                    data["icon_image"] = self._read_icon_image(data["client"])
                    if "icon_cache" in data:
                        try:
                            data["icon_cache"].clear()
                        except Exception:
                            data["icon_cache"] = {}
                    self._redraw_window(data["titlebar"])
                    self._redraw_taskbar()
                break
