"""Modal alert windows for Pillarium (startup / warning / error).

An alert is a centred, level-coloured dialog that stays on screen until
it is dismissed, paired with a short chime.  Alerts can be raised:

* internally (the startup banner, an unresponsive application detected
  through ``_NET_WM_PING``, a critical D-Bus notification);
* through the public :meth:`show_alert` API;
* from the command line with the ``pillarium-notify`` helper, which
  talks to the running window manager over a small UNIX socket.

Only one alert is shown at a time; anything raised while a dialog is
open is queued and presented afterwards.
"""

import json
import os
import socket
import sys
import threading
import time
from collections import deque

from Xlib import X, XK

from . import paths
from .sound import SoundPlayer

LEVELS = ("startup", "warning", "error")

_STYLES = {
    "startup": {"color": "accent", "glyph": "i", "timeout": 6.0},
    "warning": {"color": "warn_yellow", "glyph": "!", "timeout": 0.0},
    "error": {"color": "err_red", "glyph": "!", "timeout": 0.0},
}

_LEVEL_ALIASES = {
    "info": "startup",
    "information": "startup",
    "notice": "startup",
    "startup": "startup",
    "warn": "warning",
    "warning": "warning",
    "err": "error",
    "error": "error",
    "critical": "error",
    "fatal": "error",
}


class AlertMixin:
    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def _init_alerts(self):
        cfg = getattr(self, "_alerts_cfg", {}) or {}

        self.alerts_enabled = bool(cfg.get("enabled", True))
        self.alert_levels = {
            "startup": bool(cfg.get("startup", True)),
            "warning": bool(cfg.get("warning", True)),
            "error": bool(cfg.get("error", True)),
        }
        self.alert_timeouts = {
            "startup": float(cfg.get("startup_timeout", 6.0)),
            "warning": float(cfg.get("warning_timeout", 0.0)),
            "error": float(cfg.get("error_timeout", 0.0)),
        }

        self.alert_state = None
        self._alert_queue = deque()
        self._alert_recent = {}
        self._alert_sequence = 0

        self._sounds = SoundPlayer()
        self._sounds.enabled = bool(cfg.get("sound", True))
        try:
            self._sounds.volume = float(cfg.get("volume", 0.6))
        except Exception:
            self._sounds.volume = 0.6

        self._alert_socket = None
        self._alert_socket_path = None
        self._alerts_stopping = False
        self._start_alert_socket()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def show_alert(
        self,
        level,
        title,
        message="",
        app=None,
        detail="",
        actions=None,
        timeout=None,
        sound=None,
        dedupe=True,
    ):
        """Queue an alert window.

        ``level`` is one of ``startup``, ``warning`` or ``error``
        (common aliases such as ``info``/``critical`` are accepted).
        ``actions`` is an optional list of ``(label, callback)`` pairs;
        the first action is the default (activated by Enter).
        Returns the alert id, or None when it was suppressed.
        """
        if not getattr(self, "alerts_enabled", True):
            return None

        level = _LEVEL_ALIASES.get(str(level).lower(), "error")
        if not self.alert_levels.get(level, True):
            return None

        key = (level, str(title), str(message), str(app or ""))
        now = time.time()
        if dedupe:
            last = self._alert_recent.get(key)
            if last is not None and now - last < 3.0:
                return None
        self._alert_recent[key] = now
        if len(self._alert_recent) > 64:
            for stale in [k for k, t in self._alert_recent.items() if now - t > 30.0]:
                self._alert_recent.pop(stale, None)

        if timeout is None:
            timeout = self.alert_timeouts.get(level, 0.0)

        self._alert_sequence += 1
        spec = {
            "id": self._alert_sequence,
            "level": level,
            "title": str(title) if title else "Pillarium",
            "message": str(message or ""),
            "app": str(app) if app else "",
            "detail": str(detail or ""),
            "actions": list(actions) if actions else [],
            "timeout": float(timeout or 0.0),
            "sound": bool(sound) if sound is not None else bool(self._sounds.enabled),
            "window": None,
            "width": self.ALERT_W,
            "height": 0,
            "lines": [],
            "buttons": [],
            "button_rects": [],
            "expire_at": None,
            "created": now,
        }
        self._alert_queue.append(spec)
        return spec["id"]

    def alert_startup(self, message=None, title="Pillarium", **kwargs):
        if message is None:
            message = (
                "The Pillarium window manager is ready. "
                "Alt+Space opens the launcher, Alt+Tab cycles windows, "
                "Alt+Shift+P opens the power menu."
            )
        return self.show_alert("startup", title, message, **kwargs)

    def alert_warning(self, title, message="", **kwargs):
        return self.show_alert("warning", title, message, **kwargs)

    def alert_error(self, title, message="", **kwargs):
        return self.show_alert("error", title, message, **kwargs)

    # -----------------------------------------------------------------
    # Presentation
    # -----------------------------------------------------------------
    def _present_next_alert(self):
        if self.alert_state or not self._alert_queue:
            return
        if not getattr(self, "display", None):
            return
        spec = self._alert_queue.popleft()
        try:
            self._build_alert_window(spec)
        except Exception as exc:
            print(f"Pillarium: failed to show alert: {exc}", file=sys.stderr)
            return
        self.alert_state = spec
        if spec["sound"]:
            try:
                self._sounds.play(spec["level"], paths.home_dir())
            except Exception:
                pass
        if spec["timeout"] > 0:
            spec["expire_at"] = time.time() + spec["timeout"]

    def _build_alert_window(self, spec):
        from PIL import ImageFont  # noqa: F401  (validates Pillow)

        width = self.ALERT_W
        inner = width - (2 * self.ALERT_PAD) - 8
        body_font = self._alert_font(bold=False, size=12)

        lines = []

        def add_wrapped(text):
            if not text:
                return
            if body_font is None:
                while text:
                    lines.append(text[:70])
                    text = text[70:]
                return
            lines.extend(self._wrap_text(text, body_font, inner))

        add_wrapped(spec["message"])
        detail = spec["detail"]
        if not detail and spec["app"]:
            detail = f"Application: {spec['app']}"
        add_wrapped(detail)
        spec["lines"] = lines[:10]

        text_h = len(spec["lines"]) * 18
        height = self.ALERT_PAD + 42 + text_h + 62
        height = max(self.ALERT_MIN_H, min(self.ALERT_MAX_H, height))
        spec["height"] = height

        if spec["actions"]:
            spec["buttons"] = [
                (str(label), cb, index == 0)
                for index, (label, cb) in enumerate(spec["actions"])
            ]
        else:
            spec["buttons"] = [("OK", None, True)]

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
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.KeyPressMask
                | X.KeyReleaseMask
            ),
        )
        win.map()
        try:
            win.configure(stack_mode=X.Above)
        except Exception:
            pass
        spec["window"] = win

        try:
            self.display.set_input_focus(win, X.RevertToParent, X.CurrentTime)
        except Exception:
            pass

        self._redraw_alert(spec)
        try:
            self.display.flush()
        except Exception:
            pass

    def _alert_level_color(self, level):
        style = _STYLES.get(level, _STYLES["error"])
        palette = getattr(self, "current_palette", {}) or {}
        return palette.get(style["color"], palette.get("accent", "#5e81ac"))

    def _alert_font(self, bold=False, size=12):
        try:
            from PIL import ImageFont
        except Exception:
            return None
        candidates = []
        if bold:
            candidates.append(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            )
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
        )
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        try:
            return ImageFont.load_default(size)
        except Exception:
            try:
                return ImageFont.load_default()
            except Exception:
                return None

    def _alert_text_width(self, text, font):
        try:
            from PIL import Image, ImageDraw

            probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            try:
                bb = probe.textbbox((0, 0), text, font=font)
                return bb[2] - bb[0]
            except Exception:
                return probe.textsize(text, font=font)[0]
        except Exception:
            return len(str(text)) * 7

    def _redraw_alert(self, spec=None):
        if spec is None:
            spec = self.alert_state
        if not spec or not spec.get("window"):
            return
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return

        win = spec["window"]
        width = spec["width"]
        height = spec["height"]
        palette = getattr(self, "current_palette", {}) or {}

        surface_hex = palette.get("surface", "#23272e")
        panel_hex = palette.get("panel", surface_hex)
        text_hex = palette.get("text", "#d8dee9")
        text_dim_hex = palette.get("text_dim", "#8b93a3")
        border_hex = palette.get("border", "#171a1f")
        accent_hex = self._alert_level_color(spec["level"])

        surface_rgb = self._hex_to_rgb(surface_hex)
        panel_rgb = self._hex_to_rgb(panel_hex)
        text_rgb = self._hex_to_rgb(text_hex)
        text_dim_rgb = self._hex_to_rgb(text_dim_hex)
        border_rgb = self._hex_to_rgb(border_hex)
        accent_rgb = self._hex_to_rgb(accent_hex)

        img = Image.new("RGB", (width, height), surface_rgb)
        draw = ImageDraw.Draw(img)

        # Outer border
        draw.rectangle((0, 0, width - 1, height - 1), outline=border_rgb, width=2)
        # Header strip
        draw.rectangle((2, 2, width - 3, 40), fill=panel_rgb)
        # Left accent bar
        draw.rectangle((2, 2, 7, height - 3), fill=accent_rgb)

        title_font = self._alert_font(bold=True, size=15)
        body_font = self._alert_font(bold=False, size=12)
        if body_font is None:
            try:
                from PIL import ImageFont

                body_font = ImageFont.load_default()
            except Exception:
                pass

        # Level glyph in a coloured disc
        gcx, gcy, gr = 30, 21, 12
        draw.ellipse(
            (gcx - gr, gcy - gr, gcx + gr, gcy + gr), fill=accent_rgb
        )
        glyph = _STYLES.get(spec["level"], _STYLES["error"])["glyph"]
        if title_font is not None:
            try:
                bb = draw.textbbox((0, 0), glyph, font=title_font)
                gw, gh = bb[2] - bb[0], bb[3] - bb[1]
            except Exception:
                bb, gw, gh = (0, 0, 0, 0), 6, 10
            draw.text(
                (gcx - gw // 2 - bb[0], gcy - gh // 2 - bb[1]),
                glyph,
                fill=(255, 255, 255),
                font=title_font,
            )

        if title_font is not None:
            draw.text((52, 12), spec["title"][:60], font=title_font, fill=text_rgb)

        y = 52
        for line in spec["lines"]:
            draw.text(
                (self.ALERT_PAD + 4, y), line, font=body_font, fill=text_dim_rgb
            )
            y += 18

        # Buttons, laid out right-aligned along the bottom.
        buttons = spec.get("buttons", [])
        gap = 10
        bh = self.ALERT_BTN_H
        widths = [
            max(self.ALERT_BTN_MIN_W, self._alert_text_width(label, body_font) + 30)
            for label, _cb, _default in buttons
        ]
        total_w = sum(widths) + gap * max(0, len(buttons) - 1)
        bx = width - self.ALERT_PAD - total_w
        by = height - self.ALERT_PAD - bh
        rects = []
        for (label, cb, default), bw in zip(buttons, widths):
            fill = accent_rgb if default else panel_rgb
            if default:
                draw.rounded_rectangle(
                    (bx, by, bx + bw - 1, by + bh - 1), radius=6, fill=fill
                )
                label_rgb = (255, 255, 255)
            else:
                draw.rounded_rectangle(
                    (bx, by, bx + bw - 1, by + bh - 1),
                    radius=6,
                    fill=fill,
                    outline=text_dim_rgb,
                    width=1,
                )
                label_rgb = text_rgb
            lw = self._alert_text_width(label, body_font)
            draw.text(
                (bx + (bw - lw) // 2, by + (bh - 14) // 2),
                label,
                font=body_font,
                fill=label_rgb,
            )
            rects.append((bx, by, bx + bw, by + bh, label, cb))
            bx += bw + gap
        spec["button_rects"] = rects

        try:
            gc = self._gc(win, self.colors["text"], self.colors["surface"])
            win.put_pil_image(gc, 0, 0, img)
        except Exception:
            pass
        try:
            self.display.flush()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Dismissal / input
    # -----------------------------------------------------------------
    def _activate_alert_button(self, callback):
        self._close_alert()
        if callback is not None:
            try:
                callback()
            except Exception as exc:
                print(f"Pillarium: alert action failed: {exc}", file=sys.stderr)

    def _close_alert(self):
        spec = self.alert_state
        if not spec:
            return
        self.alert_state = None
        win = spec.get("window")
        if win is not None:
            try:
                self._own_windows.discard(win.id)
            except Exception:
                pass
            try:
                win.destroy()
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
        try:
            self.display.flush()
        except Exception:
            pass

    def _close_all_alerts(self):
        try:
            self._alert_queue.clear()
        except Exception:
            pass
        if self.alert_state:
            self._close_alert()

    def _handle_alert_click(self, event):
        spec = self.alert_state
        if not spec:
            return
        for x0, y0, x1, y1, _label, cb in spec.get("button_rects", []):
            if x0 <= event.event_x < x1 and y0 <= event.event_y < y1:
                self._activate_alert_button(cb)
                return

    def _handle_alert_keypress(self, event):
        spec = self.alert_state
        if not spec:
            return
        try:
            keysym = self.display.keycode_to_keysym(event.detail, 0)
        except Exception:
            return
        if keysym == XK.XK_Escape:
            self._close_alert()
            return
        if keysym in (XK.XK_Return, XK.XK_KP_Enter, XK.XK_space):
            buttons = spec.get("buttons") or []
            if not buttons:
                self._close_alert()
                return
            default = next(
                (b for b in buttons if b[2]), buttons[0]
            )
            self._activate_alert_button(default[1])

    def _tick_alerts(self):
        spec = self.alert_state
        if spec and spec.get("expire_at") and time.time() >= spec["expire_at"]:
            self._close_alert()
        if not self.alert_state and self._alert_queue:
            self._present_next_alert()

    # -----------------------------------------------------------------
    # UNIX-socket transport used by the `pillarium-notify` command
    # -----------------------------------------------------------------
    def _start_alert_socket(self):
        try:
            home = paths.home_dir()
            os.makedirs(home, exist_ok=True)
            path = os.path.join(home, "pillarium-alerts.sock")
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            srv.listen(8)
            srv.settimeout(1.0)
            self._alert_socket = srv
            self._alert_socket_path = path
            thread = threading.Thread(
                target=self._serve_alert_socket,
                args=(srv,),
                daemon=True,
                name="pillarium-alerts",
            )
            thread.start()
            print(
                f"Pillarium: alert socket listening on {path}", file=sys.stderr
            )
        except Exception as exc:
            print(
                f"Pillarium: alert socket unavailable: {exc}", file=sys.stderr
            )
            self._alert_socket = None

    def _serve_alert_socket(self, srv):
        while not self._alerts_stopping:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue
            try:
                conn.settimeout(1.0)
                chunks = []
                while True:
                    try:
                        data = conn.recv(65536)
                    except socket.timeout:
                        break
                    if not data:
                        break
                    chunks.append(data)
                raw = b"".join(chunks)
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    self._dispatch_alert_payload(payload)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def _dispatch_alert_payload(self, payload):
        if not isinstance(payload, dict):
            return
        self.show_alert(
            payload.get("level", "warning"),
            payload.get("title", ""),
            payload.get("message", ""),
            app=payload.get("app"),
            detail=payload.get("detail", ""),
            timeout=payload.get("timeout"),
            sound=payload.get("sound"),
            dedupe=bool(payload.get("dedupe", True)),
        )

    def _stop_alert_socket(self):
        self._alerts_stopping = True
        srv = self._alert_socket
        self._alert_socket = None
        if srv is not None:
            try:
                srv.close()
            except Exception:
                pass
        path = self._alert_socket_path
        self._alert_socket_path = None
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
