"""Core window-manager logic: display setup, main loop, event
dispatch, window management and frame placement."""

import os
import sys
import time
from Xlib import X, XK
from Xlib.display import Display
from Xlib.error import BadAccess, ConnectionClosedError


class CoreMixin:
    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def _init_core(self):
        self.display = Display()

        def error_handler(err, request):
            return None

        self.display.set_error_handler(error_handler)
        self.screen = self.display.screen()
        self.root = self.screen.root

        try:
            self.root.change_attributes(
                event_mask=(
                    X.SubstructureRedirectMask
                    | X.SubstructureNotifyMask
                    | X.EnterWindowMask
                    | X.LeaveWindowMask
                    | X.ButtonPressMask
                    | X.ButtonReleaseMask
                    | X.PointerMotionMask
                    | X.FocusChangeMask
                    | X.ExposureMask
                )
            )
        except BadAccess as exc:
            print(
                "Pillarium needs to run as the active X11 window manager.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc

        self.screen_w = self.screen.width_in_pixels
        self.screen_h = self.screen.height_in_pixels
        self.frames = {}
        self.focused_client = None
        self.drag_state = None
        self.next_x = 48
        self.next_y = 48
        self.alt_tab_state = None

        # -----------------------------------------------------------------
        # Internal bookkeeping
        # -----------------------------------------------------------------
        self._own_windows = set()
        self._cursors = {}
        self._cursor_font = None
        self._window_cursor_state = {}

        self._init_ping()
        self._grab_hotkeys()
        self._init_font()

    # -----------------------------------------------------------------
    # Global hot‑keys
    # -----------------------------------------------------------------
    def _grab_hotkeys(self):
        self.mod_mask = X.Mod1Mask
        self.key_terminal = self.display.keysym_to_keycode(
            XK.string_to_keysym("Return")
        )
        self.key_quit = self.display.keysym_to_keycode(XK.string_to_keysym("F4"))
        self.root.grab_key(
            self.key_terminal,
            self.mod_mask,
            True,
            X.GrabModeAsync,
            X.GrabModeAsync,
        )
        self.root.grab_key(
            self.key_quit,
            self.mod_mask,
            True,
            X.GrabModeAsync,
            X.GrabModeAsync,
        )
        # Alt+Space – launcher / search
        self.key_search = self.display.keysym_to_keycode(
            XK.string_to_keysym("space")
        )
        try:
            for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                self.root.grab_key(
                    self.key_search,
                    self.mod_mask | extra,
                    True,
                    X.GrabModeAsync,
                    X.GrabModeAsync,
                )
        except Exception as exc:
            print(f"Pillarium: Alt+Space grab failed: {exc}", file=sys.stderr)
            self.key_search = None

        # Alt+Shift+D – toggle dark mode
        self.key_toggle_dark = self.display.keysym_to_keycode(
            XK.string_to_keysym("D")
        )
        try:
            self.root.grab_key(
                self.key_toggle_dark,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            pass

        # Alt+q – quick-launch config editor
        self.key_quick_config = self.display.keysym_to_keycode(
            XK.string_to_keysym("q")
        )
        try:
            self.root.grab_key(
                self.key_quick_config,
                self.mod_mask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_quick_config = None

        # Alt+Shift+P – power menu
        self.key_power = self.display.keysym_to_keycode(
            XK.string_to_keysym("p")
        )
        try:
            self.root.grab_key(
                self.key_power,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_power = None

        # Alt+Shift+W – wifi menu
        self.key_wifi = self.display.keysym_to_keycode(
            XK.string_to_keysym("w")
        )
        try:
            self.root.grab_key(
                self.key_wifi,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_wifi = None

        # Alt+Shift+B – bluetooth menu
        self.key_bluetooth = self.display.keysym_to_keycode(
            XK.string_to_keysym("b")
        )
        try:
            self.root.grab_key(
                self.key_bluetooth,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_bluetooth = None

        # Alt+Shift+A – audio menu
        self.key_audio = self.display.keysym_to_keycode(
            XK.string_to_keysym("a")
        )
        try:
            self.root.grab_key(
                self.key_audio,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_audio = None

        # Alt+Shift+R – refresh desktop icons
        self.key_refresh_desktop = self.display.keysym_to_keycode(
            XK.string_to_keysym("r")
        )
        try:
            self.root.grab_key(
                self.key_refresh_desktop,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_refresh_desktop = None

        # Alt+Shift+M – process list
        self.key_processes = self.display.keysym_to_keycode(
            XK.string_to_keysym("m")
        )
        try:
            self.root.grab_key(
                self.key_processes,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_processes = None

        # Alt+Shift+E – ethernet menu
        self.key_ethernet = self.display.keysym_to_keycode(
            XK.string_to_keysym("e")
        )
        try:
            self.root.grab_key(
                self.key_ethernet,
                self.mod_mask | X.ShiftMask,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        except Exception:
            self.key_ethernet = None

        # Alt+Tab / Alt+Shift+Tab – cycle windows.  The passive grab keeps
        # delivering repeats while Alt is held so each press advances the
        # focus to the next window (Shift reverses direction).
        self.key_tab = self.display.keysym_to_keycode(
            XK.string_to_keysym("Tab")
        )
        try:
            for combo in (self.mod_mask, self.mod_mask | X.ShiftMask):
                for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                    self.root.grab_key(
                        self.key_tab,
                        combo | extra,
                        True,
                        X.GrabModeAsync,
                        X.GrabModeAsync,
                    )
        except Exception as exc:
            print(f"Pillarium: Alt+Tab grab failed: {exc}", file=sys.stderr)
            self.key_tab = None

    # -----------------------------------------------------------------
    # Generic window creation helper (supports override_redirect)
    # -----------------------------------------------------------------
    def _create_window(
        self,
        parent,
        x,
        y,
        width,
        height,
        background_pixel,
        border_pixel,
        override_redirect=False,
    ):
        kwargs = dict(
            x=x,
            y=y,
            width=width,
            height=height,
            border_width=0,
            depth=0,
            window_class=X.InputOutput,
            visual=0,
            background_pixel=background_pixel,
            border_pixel=border_pixel,
            event_mask=0,
        )
        if override_redirect:
            kwargs["override_redirect"] = True
        return parent.create_window(**kwargs)

    # -----------------------------------------------------------------
    # Startup banner + initial polls
    # -----------------------------------------------------------------
    def _welcome(self):
        print("Pillarium X11 window manager is running.")
        print(
            "-> Alt+Enter opens xterm, Alt+F4 closes the focused window. Alt+Shift+D toggles dark mode."
        )
        print(
            "-> Alt+Shift+P opens the power menu, Alt+Shift+W opens the wifi menu."
        )
        print(
            "-> Alt+Shift+E opens the ethernet menu, Alt+Shift+B opens the Bluetooth menu, Alt+Shift+A opens the audio menu."
        )
        print("-> Alt+Shift+M opens the process list.")
        print("-> Alt+Tab cycles through open windows (Alt+Shift+Tab reverses).")
        print("-> Click the clock for a calendar, the battery for its status.")
        print("-> Alt+Shift+R rescans the Desktop folder for icons.")
        print(
            "-> Alt+Space or the left taskbar button opens the application launcher/search."
        )
        print("-> Double-click a desktop icon to launch it.")
        print(
            "-> Titlebar: drag to move, double-click to maximise, right-click for a menu."
        )
        print(
            "-> Drag the lower-right corner of a window to resize it."
        )
        print(
            "-> Right-click a taskbar item for Minimise/Maximise/Close/Quick‑Launch options."
        )
        print(
            "-> Middle-drag a taskbar item to reorder it (or use Move Left/Right in its menu)."
        )
        print(
            "-> Right-click the desktop to change the wallpaper."
        )

        self._poll_wifi_status()
        self._poll_ethernet_status()
        self._poll_bluetooth_status()
        self._poll_audio_status()
        self._poll_battery_status()
        self._redraw_desktop_icons()
        self.display.flush()

        # Welcome alert window (paired with the startup chime).
        try:
            self.alert_startup()
        except Exception as exc:
            print(f"Pillarium: startup alert failed: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------
    def run(self):
        # Ensure task‑bar is stacked above any existing windows after initial manage
        self._manage_existing_windows()
        try:
            self.taskbar.configure(stack_mode=X.Above)
            self.taskbar.map()
            self._redraw_taskbar()
        except Exception:
            pass
        self._last_taskbar_verify = time.time()
        self._last_desktop_icon_refresh = time.time()
        while True:
            self._process_events()
            # Update clock once per second
            try:
                import datetime

                now = datetime.datetime.now().strftime(self.time_format + ":%S")
                if now != self._last_clock:
                    self._last_clock = now
                    self._redraw_taskbar()
            except Exception:
                pass
            # Wi‑Fi / Bluetooth / Audio / Battery polls
            try:
                current_time = time.time()
                changed = False
                if current_time - self._last_wifi_poll > 5.0:
                    self._last_wifi_poll = current_time
                    self._poll_wifi_status()
                    changed = True
                if current_time - self._last_ethernet_poll > 5.0:
                    self._last_ethernet_poll = current_time
                    self._poll_ethernet_status()
                    changed = True
                if current_time - self._last_bluetooth_poll > 5.0:
                    self._last_bluetooth_poll = current_time
                    self._poll_bluetooth_status()
                    changed = True
                if current_time - self._last_audio_poll > 2.0:
                    self._last_audio_poll = current_time
                    self._poll_audio_status()
                    changed = True
                if current_time - self._last_battery_poll > 5.0:
                    self._last_battery_poll = current_time
                    self._poll_battery_status()
                    changed = True
                if changed:
                    self._redraw_taskbar()
            except Exception as exc:
                print(
                    f"Pillarium: wifi poll failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Custom widgets poll
            try:
                if self._poll_custom_widgets():
                    self._redraw_taskbar()
            except Exception as exc:
                print(
                    f"Pillarium: custom widget poll failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Audio mixer refresh poll
            try:
                if (
                    getattr(self, "mixer_state", None)
                    and time.time() - self._last_mixer_poll > 1.0
                ):
                    self._last_mixer_poll = time.time()
                    self._refresh_mixer_nodes()
                    self._redraw_mixer()
            except Exception as exc:
                print(
                    f"Pillarium: mixer poll failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Process list refresh poll
            try:
                if (
                    getattr(self, "process_state", None)
                    and time.time() - self._last_process_poll > 2.0
                ):
                    self._last_process_poll = time.time()
                    self._refresh_processes()
                    self._redraw_processes()
            except Exception as exc:
                print(
                    f"Pillarium: process poll failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Verify task‑bar geometry every second
            try:
                current_time = time.time()
                if current_time - self._last_taskbar_verify > 1.0:
                    self._last_taskbar_verify = current_time
                    self._verify_taskbar()
            except Exception as exc:
                print(
                    f"Pillarium: taskbar verify failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Refresh desktop icons regularly
            try:
                current_time = time.time()
                if current_time - self._last_desktop_icon_refresh > 2.0:
                    self._last_desktop_icon_refresh = current_time
                    self._redraw_desktop_icons()
            except Exception as exc:
                print(
                    f"Pillarium: desktop icon refresh failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Reload config.json when an external tool (e.g. Planet Control
            # Center) rewrites it, so settings apply on the fly.
            try:
                if current_time - self._last_config_check > 2.0:
                    self._last_config_check = current_time
                    if self._maybe_reload_config():
                        if self._apply_reloaded_config():
                            self._redraw_taskbar()
                            self._redraw_desktop_icons()
            except Exception as exc:
                print(
                    f"Pillarium: config reload failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Modal alerts (auto-dismiss + queued dialogs)
            try:
                self._tick_alerts()
            except Exception as exc:
                print(
                    f"Pillarium: alert tick failed in run loop: {exc}",
                    file=sys.stderr,
                )
            # Unresponsive-window detection (_NET_WM_PING)
            try:
                current_time = time.time()
                if current_time - self._last_ping_sweep > self.PING_INTERVAL:
                    self._last_ping_sweep = current_time
                    self._ping_sweep()
            except Exception as exc:
                print(
                    f"Pillarium: ping sweep failed in run loop: {exc}",
                    file=sys.stderr,
                )
            time.sleep(0.01)

    # -----------------------------------------------------------------
    # Event processing
    # -----------------------------------------------------------------
    def _process_events(self):
        try:
            while self.display.pending_events() > 0:
                event = self.display.next_event()
                self._handle_event(event)
        except ConnectionClosedError:
            raise SystemExit(0)

    def _handle_event(self, event):
        if event.type == X.MapRequest:
            self._manage_window(event.window)
        elif event.type == X.DestroyNotify:
            self._forget_window(event.window)
        elif event.type == X.UnmapNotify:
            # An unmap we initiated ourselves (minimise) must not forget
            # the window – it is still alive, just hidden.
            client_id = self._client_for_window(event.window)
            data = (
                self.frames.get(client_id)
                if client_id is not None
                else None
            )
            if not (data and data.get("minimized")):
                self._forget_window(event.window)
        elif event.type == X.ConfigureRequest:
            self._handle_configure_request(event)
        elif event.type == X.ButtonPress:
            self._handle_button_press(event)
        elif event.type == X.ButtonRelease:
            self._handle_button_release(event)
        elif event.type == X.MotionNotify:
            self._handle_motion(event)
        elif event.type == X.KeyPress:
            self._handle_key_press(event)
        elif event.type == X.ClientMessage:
            self._handle_client_message(event)
        elif event.type == X.Expose:
            self._handle_expose(event.window)
        elif event.type == X.EnterNotify:
            self._handle_enter(event.window)
        elif event.type == X.LeaveNotify:
            self._handle_leave(event.window)
        elif event.type == X.FocusIn:
            # _focus_window() explicitly controls activation on click.
            pass
        elif event.type == X.PropertyNotify:
            try:
                atom_name = self.display.get_atom_name(event.atom)
            except Exception:
                atom_name = None
            if atom_name in ("_NET_WM_ICON", "WM_NAME", "_NET_WM_NAME"):
                self._handle_property_change(event.window, atom_name)

    # -----------------------------------------------------------------
    # Expose handling (redraw)
    # -----------------------------------------------------------------
    def _handle_expose(self, window):
        if window.id == self.desktop_win.id:
            self._redraw_desktop_icons()
            return
        alert_state = getattr(self, "alert_state", None)
        if (
            alert_state
            and alert_state.get("window")
            and window.id == alert_state["window"].id
        ):
            self._redraw_alert()
            return
        active_menu = getattr(self, "active_menu", None)
        if active_menu and window.id == active_menu["window"].id:
            self._redraw_menu()
            return
        search_state = getattr(self, "search_state", None)
        if (
            search_state
            and search_state.get("window")
            and window.id == search_state["window"].id
        ):
            self._redraw_search()
            return
        confirm_state = getattr(self, "confirm_state", None)
        if (
            confirm_state
            and confirm_state.get("window")
            and window.id == confirm_state["window"].id
        ):
            self._redraw_confirm_dialog()
            return
        wifi_auth = getattr(self, "wifi_auth_state", None)
        if (
            wifi_auth
            and wifi_auth.get("window")
            and window.id == wifi_auth["window"].id
        ):
            self._redraw_wifi_auth()
            return
        mixer_state = getattr(self, "mixer_state", None)
        if (
            mixer_state
            and mixer_state.get("window")
            and window.id == mixer_state["window"].id
        ):
            self._redraw_mixer()
            return
        clock_state = getattr(self, "clock_state", None)
        if (
            clock_state
            and clock_state.get("window")
            and window.id == clock_state["window"].id
        ):
            self._redraw_clock_menu()
            return
        format_menu_state = getattr(self, "_format_menu_state", None)
        if (
            format_menu_state
            and format_menu_state.get("window")
            and window.id == format_menu_state["window"].id
        ):
            self._redraw_format_menu()
            return
        process_state = getattr(self, "process_state", None)
        if (
            process_state
            and process_state.get("window")
            and window.id == process_state["window"].id
        ):
            self._redraw_processes()
            return
        if getattr(self, "taskbar", None) and window.id == self.taskbar.id:
            self._redraw_taskbar()
            return
        for n in getattr(self, "active_notifications", []):
            if n.window and window.id == n.window.id:
                self._draw_notification(n)
                return
        self._redraw_window(window)

    # -----------------------------------------------------------------
    # Existing windows (when the WM starts)
    # -----------------------------------------------------------------
    def _manage_existing_windows(self):
        for child in self.root.query_tree().children:
            if child.id != self.root.id:
                self._manage_window(child)

    # -----------------------------------------------------------------
    # Manage a new client window
    # -----------------------------------------------------------------
    def _manage_window(self, client):
        if client.id in self.frames or client.id == self.root.id:
            return
        if client.id in self._own_windows:
            return
        try:
            if client.get_attributes().override_redirect:
                return
        except Exception:
            pass

        width = 760
        height = 520
        x = self.next_x
        y = self.next_y
        self.next_x = min(self.next_x + 28, max(24, self.screen_w - 220))
        self.next_y = min(self.next_y + 28, max(24, self.screen_h - self.TASKBAR_H - 220))

        # -----------------------------------------------------------------
        # Frame window (the outer decoration)
        # -----------------------------------------------------------------
        frame = self._create_window(
            self.root,
            x,
            y,
            width,
            height + self.TITLEBAR_H + (self.BORDER * 2),
            self.colors["surface"],
            self.colors["border"],
        )
        frame.change_attributes(
            background_pixel=self.colors["surface"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.SubstructureNotifyMask
                | X.StructureNotifyMask
                | X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.PointerMotionMask
                | X.EnterWindowMask
                | X.ExposureMask
            ),
        )
        frame.map()
        # Ensure the task‑bar stays above
        try:
            self._ensure_taskbar_on_top()
        except Exception:
            pass

        # -----------------------------------------------------------------
        # Title‑bar (styled to match taskbar)
        # -----------------------------------------------------------------
        from Xlib import Xcursorfont as cursorfont

        titlebar = self._create_window(
            frame,
            0,
            0,
            width,
            self.TITLEBAR_H,
            self.colors["taskbar"],
            self.colors["border"],
        )
        titlebar.change_attributes(
            background_pixel=self.colors["taskbar"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.PointerMotionMask
                | X.ExposureMask
                | X.EnterWindowMask
            ),
        )
        self._set_window_cursor(titlebar, cursorfont.fleur)

        # -----------------------------------------------------------------
        # Title‑bar buttons (close / maximise / minimise)
        # -----------------------------------------------------------------
        btn = self.WINDOW_BTN_SIZE
        close_x, maximize_x, minimize_x = self._window_button_positions(width)

        close_button = self._create_window(
            titlebar,
            close_x,
            8,
            btn,
            btn,
            self.colors["taskbar"],
            self.colors["border"],
        )
        close_button.change_attributes(
            background_pixel=self.colors["accent"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ButtonPressMask | X.ButtonReleaseMask | X.ExposureMask
            ),
        )
        self._set_window_cursor(close_button, cursorfont.hand2)

        maximize_button = self._create_window(
            titlebar,
            maximize_x,
            8,
            btn,
            btn,
            self.colors["taskbar"],
            self.colors["border"],
        )
        maximize_button.change_attributes(
            background_pixel=self.colors["taskbar_active"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ButtonPressMask | X.ButtonReleaseMask | X.ExposureMask
            ),
        )
        self._set_window_cursor(maximize_button, cursorfont.hand2)

        minimize_button = self._create_window(
            titlebar,
            minimize_x,
            8,
            btn,
            btn,
            self.colors["taskbar"],
            self.colors["border"],
        )
        minimize_button.change_attributes(
            background_pixel=self.colors["taskbar_active"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ButtonPressMask | X.ButtonReleaseMask | X.ExposureMask
            ),
        )
        self._set_window_cursor(minimize_button, cursorfont.hand2)

        # -----------------------------------------------------------------
        # Container (where the client lives)
        # -----------------------------------------------------------------
        container = self._create_window(
            frame,
            self.BORDER,
            self.TITLEBAR_H + self.BORDER,
            width - (self.BORDER * 2),
            height - (self.BORDER * 2),
            self.colors["surface"],
            self.colors["border"],
            # <-- container now receives clicks so that a click on the client
            #     (or empty space inside the frame) can give focus.
            # -----------------------------------------------------------------
        )
        container.change_attributes(
            background_pixel=self.colors["surface"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask    # <-- click inside container focuses
                | X.ButtonReleaseMask
                | X.PointerMotionMask
            ),
        )

        # -----------------------------------------------------------------
        # Resize grip (lower‑right corner)
        # -----------------------------------------------------------------
        resize_handle = self._create_window(
            frame,
            max(0, width - self.RESIZE_GRIP),
            max(
                self.TITLEBAR_H + self.BORDER,
                height + self.TITLEBAR_H + self.BORDER - self.RESIZE_GRIP,
            ),
            self.RESIZE_GRIP,
            self.RESIZE_GRIP,
            self.colors["border"],
            self.colors["border"],
        )
        resize_handle.change_attributes(
            background_pixel=self.colors["border"],
            border_pixel=self.colors["border"],
            event_mask=(
                X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.PointerMotionMask
                | X.ExposureMask
            ),
        )
        self._set_window_cursor(resize_handle, cursorfont.bottom_right_corner)

        # -----------------------------------------------------------------
        # Try to read an icon image from the client
        # -----------------------------------------------------------------
        icon_image = self._read_icon_image(client)
        wm_class = self._read_window_class(client)

        # -----------------------------------------------------------------
        # Store all per‑client data
        # -----------------------------------------------------------------
        self.frames[client.id] = {
            "client": client,
            "frame": frame,
            "titlebar": titlebar,
            "close_button": close_button,
            "minimize_button": minimize_button,
            "maximize_button": maximize_button,
            "container": container,
            "resize_handle": resize_handle,
            "title": self._read_title(client),
            "wm_class": wm_class,
            "icon_image": icon_image,
            "icon_cache": {},
            "minimized": False,
            "maximized": False,
            "restore_geom": None,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }

        # Show in task‑bar
        self.taskbar_items.append(client.id)
        # Track whether the client answers _NET_WM_PING (liveness)
        self._register_ping(client)

        self._reparent_client(client, container)
        self._place_frame(client.id)
        print(
            f"Pillarium: managed window client={client.id} title={self.frames[client.id]['title']} pos=({x},{y}) size=({width}x{height})",
            file=sys.stderr,
        )
        self._redraw_window(titlebar)
        self._redraw_window(close_button)
        self._redraw_taskbar()
        self._focus_window(frame)
        self.display.flush()

    # -----------------------------------------------------------------
    # Re‑parent the client into the container
    # -----------------------------------------------------------------
    def _reparent_client(self, client, container):
        try:
            client.unmap()
            client.reparent(container, 0, 0)
            # Include PropertyChangeMask so we can detect _NET_WM_ICON updates
            client.change_attributes(
                event_mask=(
                    X.StructureNotifyMask
                    | X.SubstructureNotifyMask
                    | X.EnterWindowMask
                    | X.PropertyChangeMask
                    | X.ButtonPressMask
                    | X.ButtonReleaseMask
                    | X.PointerMotionMask
                    | X.FocusChangeMask
                )
            )
            client.map()
            self.display.flush()
            print(
                f"Pillarium: reparented and mapped client {client.id}",
                file=sys.stderr,
            )
            # Passive grabs on the client: clicks on the client or its
            # subwindows (owned by the application) are delivered to us
            # first, so we can focus the window. owner_events=False plus
            # pointer_mode=GrabModeSync freezes the pointer at the press;
            # calling XAllowEvents(ReplayPointer) in the button handler
            # then releases the grab and reprocesses the event, so the
            # application still receives the click (async grabs swallow
            # the event and replay is a no-op).
            for btn in (1, 2, 3):
                try:
                    client.grab_button(
                        btn,
                        X.AnyModifier,
                        False,
                        X.ButtonPressMask,
                        X.GrabModeSync,
                        X.GrabModeAsync,
                        X.NONE,
                        X.NONE,
                    )
                except Exception:
                    pass
            # Ensure task‑bar stays on top after mapping a new client
            try:
                self._ensure_taskbar_on_top()
            except Exception as exc:
                print(
                    f"Pillarium: _reparent_client ensure_taskbar_on_top failed: {exc}",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"Could not embed window {client.id}: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Title‑bar button positions
    # -----------------------------------------------------------------
    def _window_button_positions(self, width):
        btn = self.WINDOW_BTN_SIZE
        gap = 6
        margin = 8
        close_x = width - margin - btn
        maximize_x = close_x - gap - btn
        minimize_x = maximize_x - gap - btn
        return close_x, maximize_x, minimize_x

    # -----------------------------------------------------------------
    # Place / resize a frame (called after move/resize)
    # -----------------------------------------------------------------
    def _place_frame(self, client_id):
        frame_data = self.frames.get(client_id)
        if not frame_data:
            return

        frame = frame_data.get("frame")
        titlebar = frame_data.get("titlebar")
        close_button = frame_data.get("close_button")
        minimize_button = frame_data.get("minimize_button")
        maximize_button = frame_data.get("maximize_button")
        container = frame_data.get("container")
        resize_handle = frame_data.get("resize_handle")
        if not all(
            [
                frame,
                titlebar,
                close_button,
                minimize_button,
                maximize_button,
                container,
                resize_handle,
            ]
        ):
            return

        width = frame_data.get("width", 760)
        height = frame_data.get("height", 520)
        x = frame_data.get("x", 48)
        y = frame_data.get("y", 48)

        btn = self.WINDOW_BTN_SIZE
        close_x, maximize_x, minimize_x = self._window_button_positions(width)

        frame.configure(
            x=x,
            y=y,
            width=width,
            height=height + self.TITLEBAR_H + (self.BORDER * 2),
        )
        titlebar.configure(x=0, y=0, width=width, height=self.TITLEBAR_H)
        close_button.configure(x=close_x, y=8, width=btn, height=btn)
        maximize_button.configure(x=maximize_x, y=8, width=btn, height=btn)
        minimize_button.configure(x=minimize_x, y=8, width=btn, height=btn)
        container.configure(
            x=self.BORDER,
            y=self.TITLEBAR_H + self.BORDER,
            width=width - (self.BORDER * 2),
            height=height - (self.BORDER * 2),
        )
        resize_handle.configure(
            x=max(0, width - self.RESIZE_GRIP),
            y=max(
                self.TITLEBAR_H + self.BORDER,
                height + self.TITLEBAR_H + self.BORDER - self.RESIZE_GRIP,
            ),
            width=self.RESIZE_GRIP,
            height=self.RESIZE_GRIP,
        )
        # Resize the client itself when the WM frame changes size
        try:
            frame_data["client"].configure(
                x=0,
                y=0,
                width=max(1, width - (self.BORDER * 2)),
                height=max(1, height - (self.BORDER * 2)),
            )
        except Exception as exc:
            print(
                f"Pillarium: client resize failed for {client_id}: {exc}",
                file=sys.stderr,
            )
        frame.map_sub_windows()
        frame.map()
        if os.environ.get("PILLARIUM_DEBUG"):
            print(
                f"Pillarium: frame mapped for client {client_id} at {x},{y} size={width}x{height}",
                file=sys.stderr,
            )
        # Re‑stack task‑bar after mapping frames
        try:
            self._ensure_taskbar_on_top()
        except Exception as exc:
            print(
                f"Pillarium: _place_frame ensure_taskbar_on_top failed: {exc}",
                file=sys.stderr,
            )
        titlebar.map()
        close_button.map()
        maximize_button.map()
        minimize_button.map()
        container.map()
        resize_handle.map()
        self._redraw_window(frame)
        self._redraw_window(titlebar)
        self._redraw_window(close_button)
        self._redraw_window(maximize_button)
        self._redraw_window(minimize_button)
        self._redraw_window(container)
        self._redraw_window(resize_handle)
        self.display.flush()
        self.display.sync()

    # -----------------------------------------------------------------
    # ConfigureRequest handling (client‑initiated size changes)
    # -----------------------------------------------------------------
    def _handle_configure_request(self, event):
        if event.window.id in self.frames:
            data = self.frames[event.window.id]
            data["width"] = max(self.MIN_WINDOW_W, event.width)
            data["height"] = max(self.MIN_WINDOW_H, event.height)
            self._place_frame(event.window.id)
            return

        try:
            event.window.configure(
                x=event.x,
                y=event.y,
                width=event.width,
                height=event.height,
            )
            self.display.flush()
        except Exception as exc:
            print(f"Configure request failed: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Unresponsive-window detection (_NET_WM_PING)
    # -----------------------------------------------------------------
    PING_INTERVAL = 2.0
    PING_TIMEOUT = 6.0

    def _init_ping(self):
        self._atom_cache = {}
        self._ping_supported = set()
        self._ping_outstanding = {}
        self._ping_tokens = {}
        self._ping_token_seq = 0
        self._unresponsive = set()
        self._last_ping_sweep = 0.0

    def _atom(self, name):
        cache = getattr(self, "_atom_cache", None)
        if cache is None:
            cache = self._atom_cache = {}
        if name not in cache:
            cache[name] = self.display.intern_atom(name)
        return cache[name]

    def _client_supports_ping(self, client):
        try:
            prop = client.get_full_property(
                self._atom("WM_PROTOCOLS"), X.AnyPropertyType
            )
            if not prop or not prop.value:
                return False
            ping_atom = int(self._atom("_NET_WM_PING"))
            return ping_atom in [int(value) for value in prop.value]
        except Exception:
            return False

    def _register_ping(self, client):
        try:
            if self._client_supports_ping(client):
                self._ping_supported.add(client.id)
        except Exception:
            pass

    def _unregister_ping(self, client_id):
        self._ping_supported.discard(client_id)
        self._ping_outstanding.pop(client_id, None)
        self._unresponsive.discard(client_id)
        for token, cid in list(self._ping_tokens.items()):
            if cid == client_id:
                self._ping_tokens.pop(token, None)

    def _send_ping(self, client_id):
        data = self.frames.get(client_id)
        if not data:
            return
        client = data["client"]
        for old_token, cid in list(self._ping_tokens.items()):
            if cid == client_id:
                self._ping_tokens.pop(old_token, None)
        self._ping_token_seq = (self._ping_token_seq + 1) % 0x7FFFFFFF
        token = self._ping_token_seq or 1
        self._ping_tokens[token] = client_id
        self._ping_outstanding[client_id] = (token, time.time())
        try:
            from Xlib.protocol import event as xevent

            message = xevent.ClientMessage(
                window=client,
                client_type=self._atom("WM_PROTOCOLS"),
                data=(32, [self._atom("_NET_WM_PING"), token, 0, 0, 0]),
            )
            client.send_event(message, event_mask=0, propagate=False)
            self.display.flush()
        except Exception:
            pass

    def _ping_sweep(self):
        if not getattr(self, "frames", None):
            return
        now = time.time()
        for client_id in list(self._ping_supported):
            if client_id not in self.frames:
                self._unregister_ping(client_id)
                continue
            if self.frames[client_id].get("minimized"):
                continue
            outstanding = self._ping_outstanding.get(client_id)
            if client_id in self._unresponsive:
                continue
            if outstanding:
                _token, sent = outstanding
                if now - sent > self.PING_TIMEOUT:
                    self._unresponsive.add(client_id)
                    self._alert_unresponsive(client_id)
                elif now - sent > self.PING_TIMEOUT * 2:
                    self._send_ping(client_id)
            else:
                self._send_ping(client_id)

    def _handle_client_message(self, event):
        try:
            if event.client_type != self._atom("WM_PROTOCOLS"):
                return
            raw = event.data
            if raw is None:
                return
            # python-xlib exposes ClientMessage.data as a (format, values)
            # tuple (see rq.PropertyData.parse_binary_value), so unwrap it
            # before reading the atom/token.  Treating the tuple itself as
            # the value list meant data[0] was always the literal 32 and no
            # ping reply ever matched.
            if (
                isinstance(raw, (tuple, list))
                and len(raw) == 2
                and isinstance(raw[0], int)
            ):
                values = raw[1]
            else:
                values = raw
            values = list(values)
            if len(values) < 2 or int(values[0]) != int(self._atom("_NET_WM_PING")):
                return
            token = int(values[1])
        except Exception:
            return
        client_id = self._ping_tokens.pop(token, None)
        if client_id is None:
            return
        self._ping_outstanding.pop(client_id, None)
        self._unresponsive.discard(client_id)

    def _alert_unresponsive(self, client_id):
        data = self.frames.get(client_id) or {}
        title = data.get("title") or "Application"
        self.show_alert(
            "error",
            f"{title} is not responding",
            f'The window "{title}" has stopped responding.',
            app=data.get("wm_class") or "",
            actions=[
                ("Wait", lambda cid=client_id: self._wait_for_client(cid)),
                (
                    "Force Quit",
                    lambda cid=client_id: self._force_kill_client(cid),
                ),
            ],
        )

    def _wait_for_client(self, client_id):
        self._unresponsive.discard(client_id)
        self._ping_outstanding.pop(client_id, None)

    def _force_kill_client(self, client_id):
        data = self.frames.get(client_id)
        if not data:
            return
        self._unregister_ping(client_id)
        try:
            data["client"].kill_client()
        except Exception:
            pass
        try:
            data["client"].destroy()
        except Exception:
            pass
        try:
            self._forget_window(data["client"])
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Shutdown / cleanup
    # -----------------------------------------------------------------
    def _shutdown(self):
        """Tear down everything Pillarium owns.

        Called when the WM exits (log out, SystemExit, SIGTERM/SIGINT).
        Without this the external wallpaper backend keeps running after
        the main window is gone, and popups/dialog windows can be left
        behind on screen.
        """
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True

        # -----------------------------------------------------------------
        # Wallpaper backend (e.g. ImageMagick `display -window root`).
        # It is a separate process in its own session, so it must be
        # terminated explicitly or it outlives the window manager.
        # -----------------------------------------------------------------
        proc = getattr(self, "_wallpaper_process", None)
        if proc is not None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
            except Exception:
                pass
            self._wallpaper_process = None

        # -----------------------------------------------------------------
        # Close transient popups / dialogs first.
        # -----------------------------------------------------------------
        for closer in (
            "_close_active_menu",
            "_close_search",
            "_close_confirm_dialog",
            "_close_wifi_auth",
            "_close_mixer",
            "_close_clock_menu",
            "_close_format_menu",
            "_close_processes",
            "_close_all_notifications",
            "_close_all_alerts",
        ):
            fn = getattr(self, closer, None)
            if fn is None:
                continue
            try:
                fn()
            except Exception:
                pass

        # -----------------------------------------------------------------
        # Destroy every managed client's frame and the client itself, so
        # no orphaned decoration windows remain when the WM disappears.
        # -----------------------------------------------------------------
        for client_id, data in list(self.frames.items()):
            try:
                data["client"].destroy()
            except Exception:
                pass
            try:
                data["frame"].destroy()
            except Exception:
                pass
        self.frames.clear()
        self.taskbar_items.clear()

        # -----------------------------------------------------------------
        # Destroy Pillarium's own windows (taskbar, desktop, ...).
        # -----------------------------------------------------------------
        own = getattr(self, "taskbar", None)
        if own is not None:
            try:
                own.destroy()
            except Exception:
                pass
            self.taskbar = None
        desktop = getattr(self, "desktop_win", None)
        if desktop is not None:
            try:
                desktop.destroy()
            except Exception:
                pass
            self.desktop_win = None

        # Stop the alert notification socket.
        try:
            self._stop_alert_socket()
        except Exception:
            pass

        try:
            self.display.flush()
            self.display.sync()
        except Exception:
            pass
        print("Pillarium: shutdown complete.", file=sys.stderr)
