"""Audio / PipeWire / PulseAudio support and the built-in mixer."""

import re
import shutil
import subprocess
import sys
from Xlib import X


class AudioMixin:
    def _init_audio(self):
        self.audio_status = {
            "available": False,
            "volume": 0,
            "muted": False,
            "sink": None,
        }
        self._last_audio_poll = 0.0
        # Built-in audio mixer state
        self.mixer_state = None
        self.mixer_drag = None
        self._last_mixer_poll = 0.0

    def _audio_command(self):
        if shutil.which("wpctl"):
            return "wpctl"
        if shutil.which("pactl"):
            return "pactl"
        return None

    def _audio_run(self, args, timeout=3):
        tool = self._audio_command()
        if not tool:
            return None
        try:
            return subprocess.run(
                [tool] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception as exc:
            print(f"Pillarium: audio command failed: {exc}", file=sys.stderr)
            return None

    def _poll_audio_status(self):
        tool = self._audio_command()
        if not tool:
            self.audio_status = {
                "available": False,
                "volume": 0,
                "muted": False,
                "sink": None,
            }
            return

        volume = 0
        muted = False
        sink_name = None

        if tool == "wpctl":
            result = self._audio_run(["get-volume", "@DEFAULT_AUDIO_SINK@"])
            if result is not None and result.returncode == 0:
                match = re.search(r"([0-9]*\.?[0-9]+)", result.stdout)
                if match:
                    volume = max(0, min(150, round(float(match.group(1)) * 100)))
                muted = "[MUTED]" in result.stdout.upper()

            status = self._audio_run(["status"])
            if status is not None and status.returncode == 0:
                for line in status.stdout.splitlines():
                    if "Audio Sink" in line or "Default Audio Sink" in line:
                        sink_name = line.strip()[:56]

        else:
            result = self._audio_run(["get-sink-volume", "@DEFAULT_SINK@"])
            if result is not None and result.returncode == 0:
                match = re.search(r"(\d+)%", result.stdout)
                if match:
                    volume = int(match.group(1))

            result = self._audio_run(["get-sink-mute", "@DEFAULT_SINK@"])
            if result is not None and result.returncode == 0:
                muted = "yes" in result.stdout.lower()

            result = self._audio_run(["get-default-sink"])
            if result is not None and result.returncode == 0:
                sink_name = result.stdout.strip()[:56]

        self.audio_status = {
            "available": True,
            "volume": volume,
            "muted": muted,
            "sink": sink_name,
        }

    def _audio_action(self, action):
        tool = self._audio_command()
        if not tool:
            return

        if action == "mute":
            if tool == "wpctl":
                self._audio_run(["set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
            else:
                self._audio_run(["set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        elif action in ("volume_up", "volume_down"):
            amount = "5%+" if action == "volume_up" else "5%-"
            if tool == "wpctl":
                self._audio_run(["set-volume", "@DEFAULT_AUDIO_SINK@", amount])
            else:
                self._audio_run(["set-sink-volume", "@DEFAULT_SINK@", amount])
        elif action == "open_mixer":
            self._open_mixer()

        self._poll_audio_status()
        self._redraw_taskbar()

    def _toggle_audio_menu(self, anchor_x):
        if (
            getattr(self, "active_menu", None)
            and self.active_menu.get("kind") == "audio"
        ):
            self._close_active_menu()
            return

        self._poll_audio_status()
        self._close_active_menu()

        if not self.audio_status.get("available"):
            items = [
                {
                    "label": "Audio unavailable",
                    "action": ("audio", ("noop", None)),
                },
                {
                    "label": "Cancel",
                    "action": ("audio", ("cancel", None)),
                },
            ]
        else:
            vol = self.audio_status.get("volume", 0)
            muted = self.audio_status.get("muted", False)
            items = [
                {
                    "label": (
                        f"Unmute ({vol}%)"
                        if muted
                        else f"Mute ({vol}%)"
                    ),
                    "action": ("audio", ("mute", None)),
                },
                {
                    "label": "Volume +5%",
                    "action": ("audio", ("volume_up", None)),
                },
                {
                    "label": "Volume -5%",
                    "action": ("audio", ("volume_down", None)),
                },
            ]
            sink = self.audio_status.get("sink")
            if sink:
                items.append({
                    "label": f"Output: {sink}",
                    "action": ("audio", ("noop", None)),
                })
            items.append({
                "label": "Open Audio Mixer",
                "action": ("audio", ("open_mixer", None)),
            })
            items.append({
                "label": "Cancel",
                "action": ("audio", ("cancel", None)),
            })

        self._open_menu(
            "audio",
            items,
            anchor_x,
            self.AUDIO_W,
        )

    def _audio_menu_action(self, payload):
        if not payload:
            return
        action, value = payload
        if action in ("cancel", "noop"):
            return
        self._audio_action(action)

    # -----------------------------------------------------------------
    # Built-in audio mixer
    # -----------------------------------------------------------------
    def _audio_get_nodes(self):
        """Return {sinks, streams, default_sink} for the active backend."""
        tool = self._audio_command()
        if not tool:
            return {"sinks": [], "streams": [], "default_sink": None}
        if tool == "wpctl":
            return self._wpctl_nodes()
        return self._pactl_nodes()

    def _wpctl_nodes(self):
        sinks = []
        streams = []
        default_sink = None
        status = self._audio_run(["status"])
        if status is None or status.returncode != 0:
            return {"sinks": sinks, "streams": streams, "default_sink": None}

        section = None
        node_re = re.compile(
            r"^\s*(?:[│├└| ])*(\*?)\s*(\d+)\.\s+(.+?)\s*\[(.*)\]\s*$"
        )
        for line in status.stdout.splitlines():
            stripped = line.strip()
            if "Streams:" in stripped:
                section = "streams"
                continue
            if "Sinks:" in stripped:
                section = "sinks"
                continue
            if (
                "Sources:" in stripped
                or "Sink endpoints" in stripped
                or "Source endpoints" in stripped
            ):
                section = None
                continue
            if section is None:
                continue
            m = node_re.match(line)
            if not m:
                if not stripped or not line.startswith((" ", "\t")):
                    section = None
                continue
            if "vol:" not in m.group(4):
                continue
            node_id = m.group(2)
            vol_m = re.search(r"vol:\s*([0-9]*\.?[0-9]+)", m.group(4))
            volume = (
                max(0, min(150, round(float(vol_m.group(1)) * 100)))
                if vol_m
                else 0
            )
            muted = "MUTED" in m.group(4).upper()
            entry = {
                "id": node_id,
                "name": m.group(3).strip(),
                "volume": volume,
                "muted": muted,
                "default": bool(m.group(1)),
                "is_stream": section == "streams",
            }
            if section == "streams":
                streams.append(entry)
            else:
                sinks.append(entry)
                if entry["default"]:
                    default_sink = entry
        return {
            "sinks": sinks,
            "streams": streams,
            "default_sink": default_sink,
        }

    def _pactl_nodes(self):
        sinks = []
        streams = []
        default_sink = None

        out = self._audio_run(["list", "sinks"])
        if out is not None and out.returncode == 0:
            cur = None
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.startswith("Sink #"):
                    if cur:
                        sinks.append(cur)
                    cur = {
                        "id": line.split("#", 1)[1].strip(),
                        "name": "",
                        "volume": 0,
                        "muted": False,
                        "default": False,
                        "is_stream": False,
                    }
                elif cur is not None:
                    low = line.lower()
                    if low.startswith("name:"):
                        cur["name"] = line.split(":", 1)[1].strip()
                    elif low.startswith("mute:"):
                        cur["muted"] = (
                            line.split(":", 1)[1].strip().lower() == "yes"
                        )
                    elif low.startswith("volume:"):
                        m = re.search(r"(\d+)%", line)
                        if m:
                            cur["volume"] = min(150, int(m.group(1)))
            if cur:
                sinks.append(cur)

        d = self._audio_run(["get-default-sink"])
        if d is not None and d.returncode == 0:
            default_sink = d.stdout.strip()
        for s in sinks:
            if s["name"] == default_sink:
                s["default"] = True

        out = self._audio_run(["list", "sink-inputs"])
        if out is not None and out.returncode == 0:
            cur = None
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.startswith("Sink Input #"):
                    if cur:
                        streams.append(cur)
                    cur = {
                        "id": line.split("#", 1)[1].strip(),
                        "name": "Unknown application",
                        "volume": 0,
                        "muted": False,
                        "is_stream": True,
                    }
                elif cur is not None:
                    low = line.lower()
                    if low.startswith("application.name"):
                        cur["name"] = (
                            line.split("=", 1)[1].strip().strip('"')
                        )
                    elif low.startswith("mute:"):
                        cur["muted"] = (
                            line.split(":", 1)[1].strip().lower() == "yes"
                        )
                    elif low.startswith("volume:"):
                        m = re.search(r"(\d+)%", line)
                        if m:
                            cur["volume"] = min(150, int(m.group(1)))
            if cur:
                streams.append(cur)

        for entry in sinks + streams:
            name = entry["name"]
            if not name:
                entry["name"] = f"Node {entry['id']}"
            elif "." in name:
                short = name.rsplit(".", 1)[-1]
                if 0 < len(short) < len(name):
                    entry["name"] = short.replace("-", " ").title()

        return {
            "sinks": sinks,
            "streams": streams,
            "default_sink": default_sink,
        }

    def _audio_set_node_volume(self, node, percent):
        tool = self._audio_command()
        if not tool:
            return
        pct = max(0, min(150, int(percent)))
        if tool == "wpctl":
            self._audio_run(["set-volume", node["id"], f"{pct / 100.0:.2f}"])
        else:
            sub = "set-sink-input-volume" if node.get("is_stream") else "set-sink-volume"
            self._audio_run([sub, node["id"], f"{pct}%"])
        node["volume"] = pct

    def _audio_toggle_node_mute(self, node):
        tool = self._audio_command()
        if not tool:
            return
        if tool == "wpctl":
            self._audio_run(["set-mute", node["id"], "toggle"])
        else:
            sub = "set-sink-input-mute" if node.get("is_stream") else "set-sink-mute"
            self._audio_run([sub, node["id"], "toggle"])

    def _build_mixer_rows(self):
        st = self.mixer_state
        rows = []
        if st["sinks"]:
            rows.append({"type": "header", "label": "Output Devices"})
            for s in st["sinks"]:
                rows.append({"type": "sink", "node": s})
        if st["streams"]:
            rows.append({"type": "header", "label": "Applications"})
            for s in st["streams"]:
                rows.append({"type": "stream", "node": s})
        if not rows:
            rows.append({"type": "header", "label": "No audio found"})
        return rows

    def _refresh_mixer_nodes(self):
        st = getattr(self, "mixer_state", None)
        if not st:
            return
        nodes = self._audio_get_nodes()
        st["sinks"] = nodes["sinks"]
        st["streams"] = nodes["streams"]
        st["default_sink"] = nodes["default_sink"]
        st["rows"] = self._build_mixer_rows()

    def _open_mixer(self):
        if getattr(self, "mixer_state", None):
            self._close_mixer()
            return
        self._close_active_menu()
        self._poll_audio_status()

        st = {
            "window": None,
            "sinks": [],
            "streams": [],
            "default_sink": None,
            "rows": [],
            "offset": 0,
            "x": 0,
            "y": 0,
            "width": self.MIXER_W,
            "height": 0,
        }
        self.mixer_state = st
        self._refresh_mixer_nodes()

        max_visible = max(
            1, (self.screen_h - self.TASKBAR_H - 80) // self.MIXER_ROW_H
        )
        st["max_visible"] = max_visible
        height = self.MIXER_HEADER_H + max_visible * self.MIXER_ROW_H
        st["height"] = height

        anchor_x = self.screen_w - (
            self.AUDIO_W + self.ETH_W + self.WIFI_W + self.BATTERY_W
            + getattr(self, "clock_w", self.CLOCK_W)
        )
        x = max(
            0,
            min(
                self.screen_w - self.MIXER_W,
                anchor_x + self.AUDIO_W - self.MIXER_W,
            ),
        )
        y = max(0, self.screen_h - self.TASKBAR_H - height)
        st["x"] = x
        st["y"] = y

        # Use Cadet theme colors
        panel_hex = self.current_palette.get("panel", "#2c313a")
        panel_line_hex = self.current_palette.get("panel_line", "#171a1f")
        panel_pixel = self._alloc_color(panel_hex, self.screen.black_pixel)
        panel_line_pixel = self._alloc_color(panel_line_hex, self.screen.black_pixel)

        win = self._create_window(
            self.root,
            x,
            y,
            self.MIXER_W,
            height,
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
        self._redraw_mixer()
        self._redraw_taskbar()
        self.display.flush()

    def _close_mixer(self):
        st = getattr(self, "mixer_state", None)
        if not st:
            return
        win = st.get("window")
        if win is not None:
            try:
                self._own_windows.discard(win.id)
                win.destroy()
            except Exception:
                pass
        self.mixer_state = None
        self.mixer_drag = None
        try:
            self._ungrab_pointer()
        except Exception:
            pass
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

    def _mixer_scroll(self, delta):
        st = getattr(self, "mixer_state", None)
        if not st:
            return
        max_vis = st["max_visible"]
        n = len(st["rows"])
        if n <= max_vis:
            return
        new_off = max(0, min(n - max_vis, st["offset"] + delta))
        if new_off != st["offset"]:
            st["offset"] = new_off
            self._redraw_mixer()

    def _mixer_vol_from_x(self, x):
        st = self.mixer_state
        if not st:
            return 0
        x0 = self.MIXER_SLIDER_X0
        x1 = st["width"] - 20
        frac = (x - x0) / max(1, x1 - x0)
        frac = max(0.0, min(1.0, frac))
        return int(round(frac * 100))

    def _handle_mixer_click(self, event):
        st = getattr(self, "mixer_state", None)
        if not st:
            return
        if getattr(event, "detail", None) in (4, 5):
            self._mixer_scroll(-1 if event.detail == 4 else 1)
            return
        if event.event_y < self.MIXER_HEADER_H:
            return
        idx = st["offset"] + (event.event_y - self.MIXER_HEADER_H) // self.MIXER_ROW_H
        if idx >= len(st["rows"]):
            return
        row = st["rows"][idx]
        if row.get("type") == "header":
            return
        node = row["node"]
        if event.event_x < self.MIXER_SLIDER_X0:
            self._audio_toggle_node_mute(node)
            self._refresh_mixer_nodes()
            self._redraw_mixer()
            return
        self._audio_set_node_volume(node, self._mixer_vol_from_x(event.event_x))
        self.mixer_drag = {"node": node}
        self._grab_pointer()
        self._redraw_mixer()

    def _draw_mixer_speaker(self, win, x, y, size, color_hex, bg_hex, muted):
        try:
            from PIL import Image, ImageDraw

            # Use Cadet theme colors
            panel_hex = self.current_palette.get("panel", "#2c313a")
            accent_hex = self.current_palette.get("accent", "#5e81ac")
            accent_hot_hex = self.current_palette.get("accent_hot", "#81a1c1")

            panel_rgb = self._hex_to_rgb(panel_hex)
            accent_rgb = self._hex_to_rgb(accent_hex)
            accent_hot_rgb = self._hex_to_rgb(accent_hot_hex)

            img = Image.new("RGB", (size, size), self._hex_to_rgb(bg_hex))
            d = ImageDraw.Draw(img)
            col = self._hex_to_rgb(color_hex)
            cy = size // 2
            d.polygon(
                [(2, cy - 4), (6, cy - 4), (11, cy - 9), (11, cy + 9),
                 (6, cy + 4), (2, cy + 4)],
                outline=col,
            )
            d.arc((1, cy - 6, 12, cy + 6), 300, 60, fill=col, width=1)
            if muted:
                d.line((0, 0, size - 1, size - 1), fill=accent_hot_rgb, width=2)
            gc = self._gc(win, self.colors["text"], self.colors["surface"])
            win.put_pil_image(gc, x, y, img)
        except Exception:
            pass

    def _redraw_mixer(self):
        st = getattr(self, "mixer_state", None)
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
            win, 12, 12, "Audio Mixer", text_hex, panel_hex, padding=1
        )
        n = len(rows)
        if n > st["max_visible"]:
            end = min(st["offset"] + st["max_visible"], n)
            hint = f"{st['offset'] + 1}-{end}/{n}"
        else:
            hint = "Esc to close"
        self._draw_text_pixels(
            win, w - 130, 12, hint, text_dim_hex, panel_hex, padding=1
        )

        gc_line = self._gc(win, self.colors["border"], self.colors["surface"])
        win.fill_rectangle(gc_line, 0, self.MIXER_HEADER_H - 1, w, 1)

        for i in range(st["max_visible"]):
            ri = st["offset"] + i
            if ri >= len(rows):
                break
            row = rows[ri]
            y0 = self.MIXER_HEADER_H + i * self.MIXER_ROW_H
            if row["type"] == "header":
                self._draw_text_pixels(
                    win,
                    12,
                    y0 + 10,
                    row["label"],
                    text_dim_hex,
                    panel_hex,
                    padding=1,
                )
                continue
            node = row["node"]
            cy = y0 + self.MIXER_ROW_H // 2
            icon_hex = (
                accent_hot_hex
                if node.get("muted")
                else text_hex
            )
            self._draw_mixer_speaker(
                win, 10, cy - 9, 20, icon_hex, panel_hex, node.get("muted")
            )
            label = str(node.get("name", "?"))[:24]
            self._draw_text_pixels(
                win, 36, y0 + 11, label, text_hex, panel_hex, padding=1
            )
            track_x0 = self.MIXER_SLIDER_X0
            track_x1 = w - 20
            track_y = cy - 2
            gc_track = self._gc(
                win, self.colors["border"], self.colors["surface"]
            )
            win.fill_rectangle(
                gc_track, track_x0, track_y, track_x1 - track_x0, 4
            )
            frac = max(0.0, min(1.0, node.get("volume", 0) / 150.0))
            fill_x = track_x0 + int((track_x1 - track_x0) * frac)
            if fill_x > track_x0:
                fill_px = (
                    self.colors["titlebar_alt"]
                    if node.get("muted")
                    else self.colors["accent"]
                )
                gc_fill = self._gc(win, fill_px, self.colors["surface"])
                win.fill_rectangle(
                    gc_fill, track_x0, track_y, fill_x - track_x0, 4
                )
            thumb_x = max(track_x0, min(track_x1, fill_x))
            gc_thumb = self._gc(
                win, self.colors["text"], self.colors["surface"]
            )
            win.fill_rectangle(gc_thumb, thumb_x - 4, cy - 8, 8, 16)

        self.display.flush()
