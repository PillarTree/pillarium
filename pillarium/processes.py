"""Background-process list panel (ps + kill)."""

import subprocess
import sys
from Xlib import X

from .constants import PROC_HEADER_H, PROC_ROW_H, PROC_W


class ProcessMixin:
    def _init_processes(self):
        self.process_state = None
        self._last_process_poll = 0.0

    # -----------------------------------------------------------------
    # Process listing
    # -----------------------------------------------------------------
    def _get_process_rows(self, limit=80):
        rows = []
        try:
            out = subprocess.run(
                ["ps", "-eo", "pid,comm,pcpu,pmem", "--sort=-pcpu"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if out.returncode != 0:
                return rows
            for line in out.stdout.splitlines()[1 : limit + 1]:
                parts = line.split(None, 3)
                if len(parts) < 4:
                    continue
                try:
                    pid = int(parts[0])
                    cpu = float(parts[2])
                    mem = float(parts[3])
                except Exception:
                    continue
                rows.append({
                    "pid": pid,
                    "name": parts[1][:28],
                    "cpu": cpu,
                    "mem": mem,
                })
        except Exception:
            pass
        return rows

    def _refresh_processes(self):
        st = getattr(self, "process_state", None)
        if not st:
            return
        st["rows"] = self._get_process_rows()

    # -----------------------------------------------------------------
    # Process panel
    # -----------------------------------------------------------------
    def _toggle_processes(self):
        if getattr(self, "process_state", None):
            self._close_processes()
            return
        self._open_processes()

    def _open_processes(self):
        if getattr(self, "process_state", None):
            return
        self._close_active_menu()
        self._close_confirm_dialog()
        if getattr(self, "clock_state", None):
            self._close_clock_menu()

        st = {
            "window": None,
            "rows": [],
            "offset": 0,
            "x": 0,
            "y": 0,
            "width": self.PROC_W,
            "height": 0,
            "max_visible": 1,
        }
        self.process_state = st
        st["rows"] = self._get_process_rows()
        self._last_process_poll = 0.0

        max_visible = max(
            1, (self.screen_h - self.TASKBAR_H - 80) // self.PROC_ROW_H
        )
        st["max_visible"] = max_visible
        st["height"] = self.PROC_HEADER_H + max_visible * self.PROC_ROW_H
        x = max(0, self.screen_w - getattr(self, "clock_w", self.CLOCK_W) - self.PROC_W)
        y = max(0, self.screen_h - self.TASKBAR_H - st["height"])
        st["x"], st["y"] = x, y

        # Use Cadet theme colors
        panel_hex = self.current_palette.get("panel", "#2c313a")
        panel_line_hex = self.current_palette.get("panel_line", "#171a1f")
        panel_pixel = self._alloc_color(panel_hex, self.screen.black_pixel)
        panel_line_pixel = self._alloc_color(panel_line_hex, self.screen.black_pixel)

        win = self._create_window(
            self.root,
            x,
            y,
            self.PROC_W,
            st["height"],
            panel_pixel,
            panel_line_pixel,
            override_redirect=True,
        )
        self._own_windows.add(win.id)
        win.change_attributes(
            background_pixel=panel_pixel,
            border_pixel=panel_line_pixel,
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
        st["window"] = win
        try:
            self.display.set_input_focus(win, X.RevertToParent, X.CurrentTime)
        except Exception:
            pass
        self._redraw_processes()
        self._redraw_taskbar()
        self.display.flush()

    def _close_processes(self):
        st = getattr(self, "process_state", None)
        if not st:
            return
        win = st.get("window")
        if win is not None:
            try:
                self._own_windows.discard(win.id)
                win.destroy()
            except Exception:
                pass
        self.process_state = None
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

    def _redraw_processes(self):
        st = getattr(self, "process_state", None)
        if not st or not st.get("window"):
            return
        win = st["window"]
        w = st["width"]
        h = st["height"]
        rows = st["rows"]

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
        win.fill_rectangle(gc_bg, 0, 0, w, h)

        # Draw border like Cadet
        gc_border = self._gc(win, self.colors["border"], self.colors["surface"])
        win.rectangle(gc_border, 0, 0, w, h)
        win.rectangle(gc_border, 0, 0, 1, h)
        win.rectangle(gc_border, w - 1, 0, 1, h)
        win.rectangle(gc_border, 0, h - 1, w, 1)

        self._draw_text_pixels(
            win, 12, 12, "Processes", text_hex, panel_hex, padding=1
        )
        n = len(rows)
        max_vis = st["max_visible"]
        if n > max_vis:
            end = min(st["offset"] + max_vis, n)
            hint = f"{st['offset'] + 1}-{end}/{n}"
        else:
            hint = "Esc to close"
        self._draw_text_pixels(
            win, w - 140, 12, hint, text_dim_hex, panel_hex, padding=1
        )

        gc_line = self._gc(win, self.colors["border"], self.colors["surface"])
        win.fill_rectangle(gc_line, 0, self.PROC_HEADER_H - 1, w, 1)

        self._draw_text_pixels(
            win, 12, self.PROC_HEADER_H + 4, "CPU%", text_dim_hex, panel_hex, padding=1
        )
        self._draw_text_pixels(
            win, 62, self.PROC_HEADER_H + 4, "MEM%", text_dim_hex, panel_hex, padding=1
        )
        self._draw_text_pixels(
            win, 112, self.PROC_HEADER_H + 4, "PID", text_dim_hex, panel_hex, padding=1
        )
        self._draw_text_pixels(
            win, 160, self.PROC_HEADER_H + 4, "Command", text_dim_hex, panel_hex, padding=1
        )

        body_y0 = self.PROC_HEADER_H + 20
        for i in range(max_vis):
            ri = st["offset"] + i
            if ri >= len(rows):
                break
            row = rows[ri]
            y0 = body_y0 + i * self.PROC_ROW_H
            if y0 + self.PROC_ROW_H > h:
                break
            # Alternate row colors like Cadet
            if i % 2 == 1:
                gc_alt = self._gc(win, self.colors["surface"], self.colors["surface"])
                win.fill_rectangle(gc_alt, 0, y0, w, self.PROC_ROW_H)

            self._draw_text_pixels(
                win, 12, y0 + 5, f"{row['cpu']:5.1f}", text_hex, panel_hex, padding=1
            )
            self._draw_text_pixels(
                win, 62, y0 + 5, f"{row['mem']:4.1f}", text_hex, panel_hex, padding=1
            )
            self._draw_text_pixels(
                win, 112, y0 + 5, str(row["pid"]), text_hex, panel_hex, padding=1
            )
            self._draw_text_pixels(
                win, 160, y0 + 5, row["name"], text_hex, panel_hex, padding=1
            )
            win.fill_rectangle(gc_line, 0, y0 + self.PROC_ROW_H - 1, w, 1)

        self.display.flush()

    def _handle_process_click(self, event):
        st = getattr(self, "process_state", None)
        if not st:
            return
        if getattr(event, "detail", None) in (4, 5):
            n = len(st["rows"])
            max_vis = st["max_visible"]
            if n > max_vis:
                new_off = max(
                    0,
                    min(n - max_vis, st["offset"] + (-1 if event.detail == 4 else 1)),
                )
                if new_off != st["offset"]:
                    st["offset"] = new_off
                    self._redraw_processes()
            return
        if event.event_y < self.PROC_HEADER_H + 20:
            return
        idx = (
            st["offset"]
            + (event.event_y - self.PROC_HEADER_H - 20) // self.PROC_ROW_H
        )
        if idx >= len(st["rows"]):
            return
        row = st["rows"][idx]
        items = [
            {
                "label": f"Kill PID {row['pid']} ({row['name'][:14]})",
                "action": ("process", ("kill", row["pid"])),
            },
            {
                "label": "Cancel",
                "action": ("process", ("cancel", None)),
            },
        ]
        self._open_menu(
            "process", items, event.root_x, 0, anchor_y=event.root_y
        )

    def _process_menu_action(self, payload):
        if not payload:
            return
        action, value = payload
        if action in ("cancel", "noop"):
            return
        if action == "kill":
            pid = int(value)
            self._open_confirm_dialog(
                "Kill Process",
                f"Terminate PID {pid}?",
                "Kill",
                lambda: self._kill_process(pid),
            )

    def _kill_process(self, pid):
        try:
            subprocess.Popen(["kill", "-TERM", str(pid)])
        except Exception as exc:
            print(
                f"Pillarium: kill PID {pid} failed: {exc}",
                file=sys.stderr,
            )