"""Cadet-style widgets drawn on the software framebuffer (Renderer)."""

from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw

from . import theme
from .drawing import Renderer


def _center_y(row_h: int, text_h: int) -> int:
    return max(0, (row_h - text_h) // 2)


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------
class Button:
    def __init__(self, label: str, action: Optional[str] = None, hint: str = ""):
        self.label = label
        self.action = action
        self.hint = hint
        self.x = self.y = self.w = self.h = 0
        self.hover = False
        self.enabled = True

    def set_bounds(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, mx, my):
        return (self.x <= mx < self.x + self.w
                and self.y <= my < self.y + self.h)

    def render(self, r: Renderer):
        fill = theme.PANEL
        if not self.enabled:
            color = theme.TEXT_FAINT
        elif self.hover:
            fill = theme.ROW_HOVER
            color = theme.ACCENT_HOT
        else:
            color = theme.TEXT
        r.rect(self.x, self.y, self.w, self.h, fill)
        r.outline(self.x, self.y, self.w, self.h, theme.PANEL_LINE)
        th = r.text_h()
        if self.enabled and self.hover:
            r.text(self.x + self.w // 2 - r.text_w(self.label) // 2,
                   self.y + _center_y(self.h, th), self.label, color)
        else:
            r.text(self.x + self.w // 2 - r.text_w(self.label) // 2,
                   self.y + _center_y(self.h, th), self.label, color)


# ---------------------------------------------------------------------------
# TextBox
# ---------------------------------------------------------------------------
class TextBox:
    """Editable single-line text field."""

    def __init__(self, font=None, placeholder: str = ""):
        self.text = ""
        self.cursor = 0
        self.anchor: Optional[int] = None
        self.focus = False
        self.placeholder = placeholder
        self.x = self.y = self.w = self.h = 0
        self.offset = 0
        self._prefix_w_cache: dict = {}
        self.font = font

    def set_bounds(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self._ensure_visible()

    def contains(self, mx, my):
        return (self.x <= mx < self.x + self.w
                and self.y <= my < self.y + self.h)

    def set_text(self, text: str, move_end: bool = True):
        self.text = text
        self.cursor = len(text) if move_end else 0
        self.anchor = None
        self._prefix_w_cache.clear()
        self._ensure_visible()

    def _px(self, i: int) -> int:
        if i == 0:
            return 0
        if i in self._prefix_w_cache:
            return self._prefix_w_cache[i]
        if self.font is None:
            return 0
        w = self.font.getlength(self.text[:i])
        self._prefix_w_cache[i] = w
        return w

    def _char_at(self, mx) -> int:
        x = mx + self.offset
        best = 0
        for i in range(len(self.text) + 1):
            if abs(self._px(i) - x) <= abs(self._px(best) - x):
                best = i
        return best

    def _ensure_visible(self):
        caret = self._px(self.cursor)
        inner = self.w - theme.PAD * 2
        if caret - self.offset < 0:
            self.offset = max(0, caret - theme.PAD)
        elif caret - self.offset > inner:
            self.offset = caret - inner + theme.PAD

    def mouse_down(self, mx, my, shift: bool = False):
        if not self.contains(mx, my):
            return False
        self.focus = True
        pos = self._char_at(mx - self.x)
        if shift and self.anchor is not None:
            pass
        else:
            self.anchor = None
        self.cursor = pos
        self._ensure_visible()
        return True

    def mouse_drag(self, mx, my):
        if not self.contains(mx, my):
            return False
        self.cursor = self._char_at(mx - self.x)
        if self.anchor is None:
            self.anchor = self.cursor
        self._ensure_visible()
        return True

    def _delete_range(self):
        if self.anchor is not None and self.anchor != self.cursor:
            a, b = sorted((self.anchor, self.cursor))
            self.text = self.text[:a] + self.text[b:]
            self.cursor = a
            self.anchor = None
            self._prefix_w_cache.clear()
            return True
        return False

    def key(self, ksym, ch, modifiers) -> bool:
        if not self.focus:
            return False
        mods = modifiers
        ctrl = bool(mods & 0x4)
        if ksym in ("Home", "KP_Home"):
            if ctrl:
                self.offset = 0
            else:
                self.cursor = 0
                self.anchor = None
        elif ksym in ("End", "KP_End"):
            if ctrl:
                self.offset = 0
            else:
                self.cursor = len(self.text)
                self.anchor = None
        elif ksym in ("Left", "KP_Left"):
            if ctrl:
                i = self.cursor
                while i > 0 and self.text[i - 1] == " ":
                    i -= 1
                while i > 0 and self.text[i - 1] != " ":
                    i -= 1
                self.cursor = i
            else:
                self.cursor = max(0, self.cursor - 1)
            if not (mods & 0x1):
                self.anchor = None
        elif ksym in ("Right", "KP_Right"):
            if ctrl:
                i = self.cursor
                while i < len(self.text) and self.text[i] != " ":
                    i += 1
                while i < len(self.text) and self.text[i] == " ":
                    i += 1
                self.cursor = i
            else:
                self.cursor = min(len(self.text), self.cursor + 1)
            if not (mods & 0x1):
                self.anchor = None
        elif ksym in ("BackSpace",):
            if not self._delete_range():
                if self.cursor > 0:
                    self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                    self.cursor -= 1
                    self._prefix_w_cache.clear()
        elif ksym in ("Delete", "KP_Delete"):
            if not self._delete_range():
                if self.cursor < len(self.text):
                    self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
                    self._prefix_w_cache.clear()
        elif ksym in ("A", "a") and ctrl:
            self.cursor = len(self.text)
            self.anchor = 0
        elif ksym in ("C", "c") and ctrl:
            pass
        elif ksym in ("X", "x") and ctrl:
            pass
        elif ksym in ("V", "v") and ctrl:
            pass
        elif len(ch) > 0 and ch.isprintable():
            if not self._delete_range():
                pass
            self.text = self.text[:self.cursor] + ch + self.text[self.cursor:]
            self.cursor += 1
            self._prefix_w_cache.clear()
        else:
            return False
        self._ensure_visible()
        return True

    def selected_text(self) -> str:
        if self.anchor is not None and self.anchor != self.cursor:
            a, b = sorted((self.anchor, self.cursor))
            return self.text[a:b]
        return ""

    def replace_selection(self, new: str):
        if self.anchor is not None:
            a, b = sorted((self.anchor, self.cursor))
            self.text = self.text[:a] + new + self.text[b:]
            self.cursor = a + len(new)
            self.anchor = None
        else:
            self.text = self.text[:self.cursor] + new + self.text[self.cursor:]
            self.cursor += len(new)
        self._prefix_w_cache.clear()
        self._ensure_visible()

    def render(self, r: Renderer):
        r.rect(self.x, self.y, self.w, self.h, theme.BG)
        r.outline(self.x, self.y, self.w, self.h,
                  theme.ACCENT if self.focus else theme.PANEL_LINE, 1)
        inner_x = self.x + theme.PAD
        tw = self.w - theme.PAD * 2
        th = r.text_h(self.font)
        ty = self.y + _center_y(self.h, th)

        sel_a = min(self.anchor, self.cursor) if self.anchor is not None else None
        sel_b = max(self.anchor, self.cursor) if self.anchor is not None else None

        r.push_clip(self.x + theme.PAD, self.y, tw, self.h)
        if not self.text and not self.focus:
            r.text(inner_x, ty, self.placeholder, theme.TEXT_FAINT, self.font)
        else:
            if sel_a is not None and sel_b != sel_a:
                xa = inner_x - self.offset + self._px(sel_a)
                xb = inner_x - self.offset + self._px(sel_b)
                r.rect(xa, self.y + 2, xb - xa, self.h - 4, theme.SELECT_FOC)
            r.text(inner_x - self.offset, ty, self.text, theme.TEXT, self.font)
            if self.focus:
                cx = inner_x - self.offset + self._px(self.cursor)
                r.vline(cx, self.y + 3, self.h - 6, theme.ACCENT_HOT)
        r.pop_clip()


# ---------------------------------------------------------------------------
# ListView
# ---------------------------------------------------------------------------
class ListView:
    HEADER_H = 26

    def __init__(self):
        self.x = self.y = self.w = self.h = 0
        self.entries: List = []
        self.sel: List[int] = []
        self.anchor: Optional[int] = None
        self.hover: Optional[int] = None
        self.scroll = 0
        self.sort_key = "name"
        self.sort_reverse = False
        self.dirs_first = True
        self.visible_rows = 0
        self._last_click = 0.0
        self._last_click_index = -1

    @property
    def selected(self) -> Optional[int]:
        return self.anchor

    def select_one(self, idx: Optional[int]):
        self.sel = [idx] if idx is not None else []
        self.anchor = idx
        self.ensure_visible(idx)

    def toggle(self, idx: int):
        if idx in self.sel:
            self.sel = [i for i in self.sel if i != idx]
            if not self.sel and self.anchor == idx:
                self.anchor = None
        else:
            self.sel.append(idx)
            self.anchor = idx
            self.ensure_visible(idx)

    def select_range(self, idx: int):
        base = self.anchor if self.anchor is not None else idx
        a, b = sorted((base, idx))
        self.sel = list(range(a, b + 1))
        self.anchor = idx
        self.ensure_visible(idx)

    def select_all(self):
        self.sel = list(range(len(self.entries)))
        self.anchor = self.sel[-1] if self.sel else None

    def clear(self):
        self.sel = []
        self.anchor = None

    def select_entries(self) -> List:
        return [self.entries[i] for i in self.sel if 0 <= i < len(self.entries)]

    def set_bounds(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.visible_rows = max(0, (h - self.HEADER_H) // theme.ROW_H)

    @property
    def list_h(self) -> int:
        return self.h - self.HEADER_H

    @property
    def max_scroll(self) -> int:
        return max(0, len(self.entries) - self.visible_rows)

    def clamp_scroll(self):
        self.scroll = min(max(0, self.scroll), self.max_scroll)

    def ensure_visible(self, idx: int):
        if idx is None:
            return
        if idx < self.scroll:
            self.scroll = idx
        elif idx >= self.scroll + self.visible_rows:
            self.scroll = idx - self.visible_rows + 1
        self.clamp_scroll()

    def column_at(self, mx) -> str:
        name_w = int((self.w - theme.SCROLL_W) * theme.NAME_COL_W)
        size_w = 90
        if mx < self.x + name_w:
            return "name"
        if mx < self.x + name_w + size_w:
            return "size"
        return "time"

    def header_hit(self, my) -> bool:
        return self.y <= my < self.y + self.HEADER_H

    def row_at(self, my) -> Optional[int]:
        if my < self.y + self.HEADER_H or my >= self.y + self.h:
            return None
        i = self.scroll + (my - (self.y + self.HEADER_H)) // theme.ROW_H
        if 0 <= i < len(self.entries):
            return i
        return None

    def set_entries(self, entries: List):
        self.entries = entries
        self.sel = []
        self.anchor = None
        self.scroll = 0

    def columns(self, list_w: int):
        name_w = int(list_w * theme.NAME_COL_W)
        size_w = 90
        time_w = 150
        name_w = max(120, list_w - size_w - time_w)
        return name_w, size_w, time_w

    def render(self, r: Renderer, focused: bool):
        r.rect(self.x, self.y, self.w, self.h, theme.BG)
        name_w, size_w, time_w = self.columns(self.w - theme.SCROLL_W)
        th = r.text_h()
        text_h = th

        hx = self.x
        r.rect(hx, self.y, self.w - theme.SCROLL_W, self.HEADER_H, theme.PANEL)
        hdr_y = self.y + _center_y(self.HEADER_H, th)
        headers = [("name", "Name", name_w), ("size", "Size", size_w),
                   ("time", "Modified", time_w)]
        cx = hx + theme.ICON_PAD_X
        for key, label, w in headers:
            color = theme.ACCENT_HOT if self.sort_key == key else theme.TEXT
            r.text(cx, hdr_y, label, color)
            if self.sort_key == key:
                arrow = "▼" if self.sort_reverse else "▲"
                r.text(cx + r.text_w(label) + 6, hdr_y, arrow, color)
            cx += w
        r.hline(hx, self.y + self.HEADER_H - 1, self.w, theme.PANEL_LINE)

        r.push_clip(self.x, self.y + self.HEADER_H, self.w, self.list_h)
        for row in range(self.visible_rows):
            idx = self.scroll + row
            if idx >= len(self.entries):
                break
            e = self.entries[idx]
            ry = self.y + self.HEADER_H + row * theme.ROW_H
            if idx in self.sel:
                r.rect(self.x, ry, self.w, theme.ROW_H,
                       theme.SELECT_FOC if focused else theme.SELECT)
            elif idx == self.hover and idx not in self.sel:
                r.rect(self.x, ry, self.w, theme.ROW_H, theme.ROW_HOVER)
            elif row % 2 == 1:
                r.rect(self.x, ry, self.w, theme.ROW_H, theme.ROW_ALT)

            name_color = theme.TEXT
            if getattr(e, 'broken', False):
                name_color = theme.ERR_RED
            elif getattr(e, 'is_link', False):
                name_color = theme.LINK_COLOR
            elif getattr(e, 'is_dir', False):
                name_color = theme.DIR_COLOR
            if getattr(e, 'is_hidden', False):
                name_color = tuple(max(0, c - 70) for c in name_color)

            self._icon(r, self.x + 8, ry, e)
            name_x = self.x + theme.ICON_PAD_X + 18
            r.text(name_x, ry + _center_y(theme.ROW_H, text_h),
                   getattr(e, 'name', str(e))[:80], name_color)

            size_x = self.x + name_w + 4
            if not getattr(e, 'is_dir', False):
                display_size = getattr(e, 'display_size', '')
                r.text(size_x + size_w - r.text_w(display_size) - 12,
                       ry + _center_y(theme.ROW_H, text_h),
                       display_size, theme.TEXT_DIM)
            mtime = getattr(e, 'mtime', 0)
            r.text(self.x + name_w + size_w + 8,
                   ry + _center_y(theme.ROW_H, text_h),
                   self._format_time(mtime), theme.TEXT_DIM)
        r.pop_clip()

    def _icon(self, r: Renderer, x, y, e):
        c = theme.DIR_COLOR if getattr(e, 'is_dir', False) else theme.TEXT_DIM
        if getattr(e, 'broken', False):
            c = theme.ERR_RED
        if getattr(e, 'is_link', False):
            c = theme.LINK_COLOR
        s = theme.ROW_H - 10
        ox, oy = x, y + 5
        if getattr(e, 'is_dir', False):
            r.rect(ox, oy + 3, s, s - 3, c)
            r.rect(ox + 2, oy, s - 4, 3, c)
        else:
            r.rect(ox + 2, oy, s - 4, s, c)
            r.rect(ox + 2, oy, s - 4, 3, c)

    def _format_time(self, mtime):
        import datetime
        try:
            dt = datetime.datetime.fromtimestamp(mtime)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
class MenuItem:
    def __init__(self, label: str, action: str, enabled: bool = True,
                 shortcut: str = ""):
        self.label = label
        self.action = action
        self.enabled = enabled
        self.shortcut = shortcut


class Menu:
    def __init__(self, items: List[MenuItem], x: int, y: int):
        self.items = items
        self.x, self.y = x, y
        self.w = theme.MENU_W
        self.h = len(items) * theme.MENU_ITEM_H + 2
        self.index: Optional[int] = None

    def contains(self, mx, my) -> bool:
        return (self.x <= mx < self.x + self.w
                and self.y <= my < self.y + self.h)

    def item_at(self, mx, my) -> Optional[int]:
        if not self.contains(mx, my):
            return None
        i = (my - self.y - 1) // theme.MENU_ITEM_H
        return i if 0 <= i < len(self.items) else None

    def render(self, r: Renderer):
        r.rect(self.x, self.y, self.w, self.h, theme.PANEL)
        r.outline(self.x, self.y, self.w, self.h, theme.PANEL_LINE)
        th = r.text_h()
        for i, it in enumerate(self.items):
            iy = self.y + 1 + i * theme.MENU_ITEM_H
            if i == self.index and it.enabled:
                r.rect(self.x + 1, iy, self.w - 2, theme.MENU_ITEM_H, theme.SELECT)
            color = theme.TEXT if it.enabled else theme.TEXT_FAINT
            r.text(self.x + 12, iy + _center_y(theme.MENU_ITEM_H, th),
                   it.label, color)
            if it.shortcut:
                r.text(self.x + self.w - r.text_w(it.shortcut) - 12,
                       iy + _center_y(theme.MENU_ITEM_H, th),
                       it.shortcut, theme.TEXT_DIM)
        r.hline(self.x + 8, self.y + 1 + len(self.items) * theme.MENU_ITEM_H - 1,
                self.w - 16, theme.PANEL_LINE)


# ---------------------------------------------------------------------------
# Prompt dialog (modal overlay)
# ---------------------------------------------------------------------------
class Prompt:
    def __init__(self, title: str, initial: str, ok_label: str, action: str,
                 hint: str = "", cancel_label: str = "Cancel", font=None):
        self.title = title
        self.input = TextBox(font=font)
        self.input.set_text(initial)
        self.ok_label = ok_label
        self.cancel_label = cancel_label
        self.action = action
        self.hint = hint
        self.box = (0, 0, 0, 0)
        self.ok_btn = Button(ok_label, action)
        self.cancel_btn = Button(cancel_label, "cancel_prompt")

    def layout(self, r: Renderer, win_w: int, win_h: int):
        w = min(theme.MAX_DIALOG_W, win_w - 80)
        h = 128
        x = (win_w - w) // 2
        y = (win_h - h) // 2
        self.box = (x, y, w, h)
        self.input.set_bounds(x + 16, y + 46, w - 32, 30)
        self.ok_btn.set_bounds(x + w - 170, y + h - 38, 72, 28)
        self.cancel_btn.set_bounds(x + w - 90, y + h - 38, 72, 28)

    def render(self, r: Renderer, win_w: int, win_h: int):
        self.layout(r, win_w, win_h)
        x, y, w, h = self.box
        dim = Image.new("RGBA", (win_w, win_h), (0, 0, 0, 150))
        r.blit(dim, 0, 0)
        r.rect(x, y, w, h, theme.PANEL)
        r.outline(x, y, w, h, theme.ACCENT, 1)
        th = r.text_h()
        r.text(x + 16, y + 14, self.title, theme.TEXT, r.font_ui_b)
        if self.hint:
            r.text(x + 16, y + 88, self.hint, theme.TEXT_DIM)
        self.input.render(r)
        self.ok_btn.render(r)
        self.cancel_btn.render(r)