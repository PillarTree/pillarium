"""Application launcher / search popup."""

import sys
from Xlib import X, XK


class SearchMixin:
    def _init_search(self):
        # Search popup state (None when closed)
        self.search_state = None
        self.search_scroll_drag = None

    # -----------------------------------------------------------------
    # Search (application launcher)
    # -----------------------------------------------------------------
    def _toggle_search(self):
        if getattr(self, "search_state", None):
            self._close_search()
            return
        self._close_active_menu()
        self._close_wifi_auth()
        self._close_confirm_dialog()
        self._refresh_applications()
        self.search_state = {
            "query": "",
            "results": [],
            "selected": 0,
            "window": None,
            "row_h": 42,
            "width": 420,
            "height": 42,
            "max_results": 2000,
            "offset": 0,
            "max_visible": 8,
        }
        self._update_search_results()
        self._open_search_window()

    def _open_search_window(self):
        st = self.search_state
        row_h = st["row_h"]
        width = st["width"]
        max_results = st["max_results"]
        max_visible = min(max_results, (self.screen_h // row_h) - 1)
        st["max_visible"] = max_visible
        height = row_h * (1 + max_visible)
        x = 8
        y = max(0, self.screen_h - self.TASKBAR_H - height)

        # Use Cadet theme colors for window
        panel_hex = self.current_palette.get("panel", "#2c313a")
        panel_line_hex = self.current_palette.get("panel_line", "#171a1f")
        panel_pixel = self._alloc_color(panel_hex, self.screen.black_pixel)
        panel_line_pixel = self._alloc_color(panel_line_hex, self.screen.black_pixel)

        win = self.root.create_window(
            x=x,
            y=y,
            width=width,
            height=height,
            border_width=1,
            depth=0,
            window_class=X.InputOutput,
            visual=0,
            background_pixel=panel_pixel,
            border_pixel=panel_line_pixel,
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.KeyPressMask
                | X.PointerMotionMask
            ),
        )
        self._own_windows.add(win.id)
        win.map()
        try:
            win.configure(stack_mode=X.Above)
        except Exception:
            pass
        st["window"] = win
        st["height"] = height
        try:
            self.display.set_input_focus(win, X.RevertToParent, X.CurrentTime)
        except Exception:
            pass
        self._redraw_taskbar()
        self._redraw_search()
        self.display.flush()

    def _close_search(self):
        st = getattr(self, "search_state", None)
        if not st:
            return
        win = st.get("window")
        if win is not None:
            try:
                self._own_windows.discard(win.id)
                win.destroy()
            except Exception:
                pass
        self.search_state = None
        try:
            if self.focused_client in self.frames:
                self.display.set_input_focus(
                    self.frames[self.focused_client]["client"],
                    X.RevertToParent,
                    X.CurrentTime,
                )
            else:
                self.display.set_input_focus(self.root, X.RevertToParent, X.CurrentTime)
        except Exception:
            pass
        self._redraw_taskbar()
        self.display.flush()

    def _search_scroll(self, delta):
        st = self.search_state
        if not st:
            return
        max_vis = st["max_visible"]
        n_res = len(st["results"])
        if n_res <= max_vis:
            return
        new_off = max(0, min(n_res - max_vis, st["offset"] + delta))
        if new_off != st["offset"]:
            st["offset"] = new_off
            if st["selected"] < new_off:
                st["selected"] = new_off
            elif st["selected"] >= new_off + max_vis:
                st["selected"] = new_off + max_vis - 1
            self._redraw_search()

    def _search_set_offset(self, offset):
        st = getattr(self, "search_state", None)
        if not st:
            return
        max_vis = st["max_visible"]
        n_res = len(st["results"])
        if n_res <= max_vis:
            st["offset"] = 0
            return
        new_off = max(0, min(n_res - max_vis, int(offset)))
        if new_off != st["offset"]:
            st["offset"] = new_off
            if st["selected"] < new_off:
                st["selected"] = new_off
            elif st["selected"] >= new_off + max_vis:
                st["selected"] = new_off + max_vis - 1
            self._redraw_search()

    def _search_scrollbar_hit(self, x, y):
        st = getattr(self, "search_state", None)
        if not st:
            return None
        sb = st.get("scrollbar")
        if not sb:
            return None
        track_x, track_y, track_w, track_h = sb["track"]
        hit_w = max(12, track_w + 4)
        hit_x = track_x - (hit_w - track_w) // 2
        if not (hit_x <= x < hit_x + hit_w and track_y <= y < track_y + track_h):
            return None
        thumb_x, thumb_y, thumb_w, thumb_h = sb["thumb"]
        if thumb_y <= y < thumb_y + thumb_h:
            return "thumb"
        return "track"

    def _search_scroll_to_click(self, y):
        st = getattr(self, "search_state", None)
        if not st:
            return
        sb = st.get("scrollbar")
        if not sb:
            return
        track_x, track_y, track_w, track_h = sb["track"]
        thumb_x, thumb_y, thumb_w, thumb_h = sb["thumb"]
        total = sb["total"]
        visible = sb["visible"]
        max_offset = max(1, total - visible)
        rel = (y - track_y - (thumb_h / 2.0)) / max(1, track_h - thumb_h)
        rel = max(0.0, min(1.0, rel))
        self._search_set_offset(int(rel * max_offset))

    def _search_scroll_drag(self, y):
        st = getattr(self, "search_state", None)
        drag = getattr(self, "search_scroll_drag", None)
        if not st or not drag:
            return
        sb = st.get("scrollbar")
        if not sb:
            return
        track_x, track_y, track_w, track_h = sb["track"]
        thumb_x, thumb_y, thumb_w, thumb_h = sb["thumb"]
        total = sb["total"]
        visible = sb["visible"]
        max_offset = max(1, total - visible)
        dy = y - drag["start_y"]
        scroll_range = max(1, track_h - thumb_h)
        delta = int((dy / float(scroll_range)) * max_offset)
        self._search_set_offset(drag["start_offset"] + delta)

    def _update_search_results(self):
        st = getattr(self, "search_state", None)
        if st is None:
            return
        query = st["query"].strip().lower()
        candidates = []
        seen = set()

        for item in getattr(self, "applications", []):
            key = (item.get("label", "").strip().lower(), tuple(item.get("cmd", [])))
            if key not in seen:
                seen.add(key)
                candidates.append(item)
        for item in self.desktop_icons + self.quick_launch:
            key = (item.get("label", "").strip().lower(), tuple(item.get("cmd", [])))
            if key not in seen:
                seen.add(key)
                candidates.append(item)

        if query:
            def fuzzy_score(item):
                label = item.get("label", "").lower()
                cmd_str = " ".join(item.get("cmd", [])).lower()

                # Exact match gets highest priority
                if label == query:
                    return (0, 0, label)
                if cmd_str == query:
                    return (0, 1, label)

                # Start of label gets high priority
                if label.startswith(query):
                    return (1, len(label), label)
                if cmd_str.startswith(query):
                    return (1, len(cmd_str) + 100, label)

                # Word boundary match
                words = label.split()
                for i, word in enumerate(words):
                    if word.startswith(query):
                        return (2, i * 10 + len(word), label)

                # Substring match
                if query in label:
                    return (3, label.find(query), label)
                if query in cmd_str:
                    return (3, cmd_str.find(query) + 1000, label)

                # Character-based fuzzy match
                query_chars = list(query)
                label_chars = list(label)
                q_idx = 0
                l_idx = 0
                matches = 0
                while q_idx < len(query_chars) and l_idx < len(label_chars):
                    if query_chars[q_idx] == label_chars[l_idx]:
                        matches += 1
                        q_idx += 1
                    l_idx += 1

                if matches >= min(3, len(query_chars)):
                    return (4, len(label) - matches, label)

                return (5, len(label), label)

            # Filter and score candidates
            results = []
            for c in candidates:
                label = c.get("label", "").lower()
                cmd_str = " ".join(c.get("cmd", [])).lower()

                # Check if query matches at all
                if (query in label or query in cmd_str or
                        any(query in word for word in label.split())):
                    results.append(c)
                else:
                    # Try character-based fuzzy match
                    query_chars = list(query)
                    label_chars = list(label)
                    q_idx = 0
                    l_idx = 0
                    matches = 0
                    while q_idx < len(query_chars) and l_idx < len(label_chars):
                        if query_chars[q_idx] == label_chars[l_idx]:
                            matches += 1
                            q_idx += 1
                        l_idx += 1
                    if matches >= min(3, len(query_chars)):
                        results.append(c)

            results.sort(key=fuzzy_score)
        else:
            results = candidates

        st["results"] = results[: st.get("max_results", 2000)]
        st["selected"] = min(st.get("selected", 0), max(0, len(st["results"]) - 1))
        st["offset"] = 0

    def _redraw_search(self):
        st = getattr(self, "search_state", None)
        if not st or not st.get("window"):
            return

        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return

        win = st["window"]
        row_h = st["row_h"]
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

        query_display = (
            st["query"] if st["query"] else "Search applications..."
        )
        fg_hex = text_hex if st["query"] else text_faint_hex

        self._draw_text_pixels(
            win,
            14,
            8,
            query_display[:46],
            fg_hex,
            panel_hex,
            padding=1,
        )

        gc_line = self._gc(
            win,
            self.colors["border"],
            self.colors["surface"],
        )
        win.fill_rectangle(gc_line, 0, row_h - 1, width, 1)

        start = st["offset"]
        end = start + st["max_visible"]
        visible = st["results"][start:end]
        st["result_rects"] = []

        content_right = width - 12

        for i, item in enumerate(visible):
            absolute_idx = start + i
            y0 = row_h + i * row_h
            y1 = y0 + row_h
            st["result_rects"].append((y0, y1, item))

            selected = absolute_idx == st.get("selected", 0)
            row_bg_hex = select_foc_hex if selected else panel_hex
            row_bg = (
                self.colors["taskbar_active"]
                if selected
                else self.colors["surface"]
            )

            if selected:
                gc_sel = self._gc(win, row_bg, row_bg)
                win.fill_rectangle(
                    gc_sel,
                    1,
                    y0,
                    max(1, content_right - 1),
                    row_h,
                )

            icon = self._load_icon(item.get("icon"), 28)
            if icon is not None:
                try:
                    icon_rgba = icon.convert("RGBA")
                    icon_rgb = Image.new(
                        "RGB",
                        icon_rgba.size,
                        panel_rgb,
                    )
                    icon_rgb.paste(
                        icon_rgba,
                        (0, 0),
                        icon_rgba,
                    )
                    gc = self._gc(
                        win,
                        self.colors["text"],
                        self.colors["surface"],
                    )
                    win.put_pil_image(
                        gc,
                        8,
                        y0 + 7,
                        icon_rgb,
                    )
                except Exception:
                    icon = None

            if icon is None:
                badge = Image.new(
                    "RGB",
                    (28, 28),
                    panel_rgb,
                )
                bd = ImageDraw.Draw(badge)
                bd.rounded_rectangle(
                    (1, 1, 26, 26),
                    radius=6,
                    fill=select_rgb,
                    outline=text_rgb,
                    width=1,
                )
                glyph = (
                    str(item.get("label", "?"))[:1]
                    or "?"
                ).upper()
                font = ImageFont.load_default()
                try:
                    bb = bd.textbbox(
                        (0, 0),
                        glyph,
                        font=font,
                    )
                    gw, gh = (
                        bb[2] - bb[0],
                        bb[3] - bb[1],
                    )
                except Exception:
                    gw, gh = 8, 10

                bd.text(
                    (
                        (28 - gw) // 2,
                        (28 - gh) // 2,
                    ),
                    glyph,
                    fill=text_rgb,
                    font=font,
                )
                gc = self._gc(
                    win,
                    self.colors["text"],
                    self.colors["surface"],
                )
                win.put_pil_image(
                    gc,
                    8,
                    y0 + 7,
                    badge,
                )

            self._draw_text_pixels(
                win,
                46,
                y0 + 10,
                item.get("label", "?")[:38],
                text_hex,
                row_bg_hex,
                padding=1,
            )

        if not st["results"]:
            msg = (
                "No applications found"
                if not st["query"]
                else "No matches"
            )
            self._draw_text_pixels(
                win,
                14,
                row_h + 10,
                msg,
                text_faint_hex,
                panel_hex,
                padding=1,
            )

        # Draw a visible scrollbar when the result list exceeds the viewport.
        total = len(st["results"])
        visible_rows = st["max_visible"]
        if total > visible_rows:
            track_x = width - 8
            track_y = row_h + 2
            track_h = max(10, height - row_h - 4)

            gc_track = self._gc(
                win,
                self.colors["border"],
                self.colors["surface"],
            )
            win.fill_rectangle(
                gc_track,
                track_x,
                track_y,
                4,
                track_h,
            )

            thumb_h = max(
                12,
                int(
                    track_h
                    * (visible_rows / float(total))
                ),
            )
            max_offset = max(
                1, total - visible_rows
            )
            thumb_y = track_y + int(
                (track_h - thumb_h)
                * (
                    st["offset"]
                    / float(max_offset)
                )
            )

            gc_thumb = self._gc(
                win,
                self.colors["accent"],
                self.colors["surface"],
            )
            win.fill_rectangle(
                gc_thumb,
                track_x,
                thumb_y,
                4,
                thumb_h,
            )

            st["scrollbar"] = {
                "track": (track_x, track_y, 4, track_h),
                "thumb": (track_x, thumb_y, 4, thumb_h),
                "total": total,
                "visible": visible_rows,
            }

            self._draw_text_pixels(
                win,
                max(220, width - 120),
                8,
                f"{start + 1}-{min(end, total)}/{total}",
                text_dim_hex,
                panel_hex,
                padding=1,
            )
        else:
            st["scrollbar"] = None

        self.display.flush()

    def _launch_top_search_result(self):
        st = getattr(self, "search_state", None)
        if not st or not st.get("results"):
            return
        item = st["results"][st.get("selected", 0)]
        self._close_search()
        try:
            self._launch_command(item.get("cmd"))
        except Exception as e:
            print(f"Pillarium: Search launch error: {e}", file=sys.stderr)

    def _handle_search_keypress(self, event):
        st = self.search_state
        if st is None:
            return
        shifted = bool(event.state & X.ShiftMask)
        try:
            keysym = self.display.keycode_to_keysym(event.detail, 1 if shifted else 0)
        except Exception:
            return

        if keysym == XK.XK_Escape:
            self._close_search()
            return
        if keysym in (XK.XK_Return, XK.XK_KP_Enter):
            self._launch_top_search_result()
            return
        if keysym in (XK.XK_Up, XK.XK_KP_Up):
            if st["results"]:
                new_sel = max(0, st["selected"] - 1)
                st["selected"] = new_sel
                if new_sel < st["offset"]:
                    st["offset"] = new_sel
                self._redraw_search()
            return
        if keysym in (XK.XK_Down, XK.XK_KP_Down):
            if st["results"]:
                new_sel = min(len(st["results"]) - 1, st["selected"] + 1)
                st["selected"] = new_sel
                if new_sel >= st["offset"] + st["max_visible"]:
                    st["offset"] = new_sel - st["max_visible"] + 1
                self._redraw_search()
            return
        if keysym in (XK.XK_Page_Up, XK.XK_KP_Page_Up):
            self._search_scroll(-max(1, st["max_visible"] - 1))
            return

        if keysym in (XK.XK_Page_Down, XK.XK_KP_Page_Down):
            self._search_scroll(max(1, st["max_visible"] - 1))
            return

        if keysym in (XK.XK_Home, XK.XK_KP_Home):
            if st["results"]:
                st["selected"] = 0
                st["offset"] = 0
                self._redraw_search()
            return

        if keysym in (XK.XK_End, XK.XK_KP_End):
            if st["results"]:
                st["selected"] = len(st["results"]) - 1
                st["offset"] = max(
                    0,
                    len(st["results"]) - st["max_visible"],
                )
                self._redraw_search()
            return

        if keysym == XK.XK_BackSpace:
            st["query"] = st["query"][:-1]
            st["selected"] = 0
            st["offset"] = 0
            self._update_search_results()
            self._redraw_search()
            return
        if 0x20 <= keysym <= 0x7e:
            st["query"] += chr(keysym)
            st["selected"] = 0
            st["offset"] = 0
            self._update_search_results()
            self._redraw_search()
            return
