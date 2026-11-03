"""The settings window.

Sections are grouped in a tab view: appearance (themes), desktops,
wallpaper, taskbar and the pinned quick-launch applications.
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from ..theme.tokens import Theme
from .base import ShellWindow
from .widgets import Themed, button, label, option_menu

SETTINGS_WIDTH = 620
SETTINGS_HEIGHT = 520


class Settings(ShellWindow):
    """Pillarium's settings dialog."""

    def __init__(
        self,
        master: ctk.CTk,
        theme: Theme,
        config: Any,
        theme_manager: Any,
        callbacks: "SettingsCallbacks",
    ):
        super().__init__(master, theme, fg_token="surface")
        self._config = config
        self._theme_manager = theme_manager
        self._callbacks = callbacks
        self._themed = Themed(theme)

        self.container = ctk.CTkFrame(
            self,
            fg_color=theme.get("surface"),
            corner_radius=self._themed.radius(),
            border_width=1,
            border_color=theme.get("border"),
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        header = ctk.CTkFrame(self.container, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", padx=16, pady=(14, 4))
        label(header, self._themed, "Pillarium Settings", weight="bold", size=15).pack(
            side="left"
        )
        button(header, self._themed, "Close", self.dismiss, width=70, height=26).pack(
            side="right"
        )

        self.tabs = ctk.CTkTabview(self.container, fg_color="transparent")
        self.tabs.pack(fill="both", expand=True, padx=12, pady=8)

        self.appearance_tab = self.tabs.add("Appearance")
        self.desktops_tab = self.tabs.add("Desktops")
        self.wallpaper_tab = self.tabs.add("Wallpaper")
        self.taskbar_tab = self.tabs.add("Taskbar")
        self.launch_tab = self.tabs.add("Applications")

        self._build_appearance()
        self._build_desktops()
        self._build_wallpaper()
        self._build_taskbar()
        self._build_launch()

        self.bind_escape()

    # -----------------------------------------------------------------
    # Appearance
    # -----------------------------------------------------------------
    def _build_appearance(self) -> None:
        tab = self.appearance_tab
        label(tab, self._themed, "Theme", weight="bold").pack(anchor="w", padx=16, pady=(12, 4))

        self.theme_list = option_menu(
            tab,
            self._themed,
            self._theme_manager.names(),
            self._on_theme_selected,
            width=220,
        )
        self.theme_list.pack(anchor="w", padx=16, pady=4)

        row = ctk.CTkFrame(tab, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=16, pady=8)
        button(
            row, self._themed, "Open theme editor", self._callbacks.on_theme_editor, width=160
        ).pack(side="left")
        button(
            row,
            self._themed,
            "Import from desktop",
            self._callbacks.on_import_theme,
            width=160,
        ).pack(side="left", padx=8)

        self.freedesktop_status = label(
            tab, self._themed, "", color_token="text_dim", size=11
        )
        self.freedesktop_status.pack(anchor="w", padx=16, pady=(0, 6))

    def _on_theme_selected(self, name: str) -> None:
        self._callbacks.on_theme_selected(name)

    # -----------------------------------------------------------------
    # Desktops
    # -----------------------------------------------------------------
    def _build_desktops(self) -> None:
        tab = self.desktops_tab
        label(tab, self._themed, "Virtual desktops", weight="bold").pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        label(
            tab,
            self._themed,
            "Number of virtual desktops",
            color_token="text_dim",
            size=11,
        ).pack(anchor="w", padx=16)

        self.desktop_count = ctk.CTkSlider(
            tab,
            from_=1,
            to=12,
            width=280,
            height=16,
            fg_color=self._theme.get("surface_alt"),
            progress_color=self._theme.get("accent"),
            button_color=self._theme.get("accent"),
            command=self._on_desktop_count,
        )
        self.desktop_count.set(self._config.desktops)
        self.desktop_count.pack(anchor="w", padx=16, pady=6)

        self.desktop_count_label = label(
            tab, self._themed, f"{self._config.desktops} desktops", color_token="text_dim", size=11
        )
        self.desktop_count_label.pack(anchor="w", padx=16, pady=(0, 8))

        label(tab, self._themed, "Desktop names (one per line)", color_token="text_dim", size=11).pack(
            anchor="w", padx=16, pady=(4, 2)
        )
        self.desktop_names = ctk.CTkTextbox(
            tab,
            width=320,
            height=110,
            fg_color=self._theme.get("surface_alt"),
            text_color=self._theme.get("text"),
            border_color=self._theme.get("border_strong"),
            font=self._themed.font(),
        )
        self.desktop_names.pack(anchor="w", padx=16, pady=4)
        self.desktop_names.insert("1.0", "\n".join(self._config.desktop_names))

        button(
            tab, self._themed, "Apply desktop settings", self._apply_desktops, width=180
        ).pack(anchor="w", padx=16, pady=10)

    def _on_desktop_count(self, value: float) -> None:
        self.desktop_count_label.configure(text=f"{int(value)} desktops")

    def _apply_desktops(self) -> None:
        count = int(self.desktop_count.get())
        names = [
            line.strip()
            for line in self.desktop_names.get("1.0", "end").splitlines()
            if line.strip()
        ]
        self._callbacks.on_desktops_changed(count, names)

    # -----------------------------------------------------------------
    # Wallpaper
    # -----------------------------------------------------------------
    def _build_wallpaper(self) -> None:
        tab = self.wallpaper_tab
        label(tab, self._themed, "Wallpaper", weight="bold").pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        self.wallpaper_path_label = label(
            tab, self._themed, self._config.wallpaper or "(default)", color_token="text_dim", size=11
        )
        self.wallpaper_path_label.pack(anchor="w", padx=16, pady=4)

        row = ctk.CTkFrame(tab, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=16, pady=8)
        button(
            row, self._themed, "Change wallpaper…", self._callbacks.on_change_wallpaper, width=170
        ).pack(side="left")
        button(
            row, self._themed, "Reset", self._callbacks.on_reset_wallpaper, width=90
        ).pack(side="left", padx=8)

    # -----------------------------------------------------------------
    # Taskbar
    # -----------------------------------------------------------------
    def _build_taskbar(self) -> None:
        tab = self.taskbar_tab
        label(tab, self._themed, "Taskbar", weight="bold").pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        label(tab, self._themed, "Position", color_token="text_dim", size=11).pack(
            anchor="w", padx=16
        )
        self.position_box = option_menu(
            tab,
            self._themed,
            ["bottom", "top", "left", "right"],
            self._on_position,
            width=160,
        )
        self.position_box.set(str(self._config.opt("taskbar", "position", "bottom")))
        self.position_box.pack(anchor="w", padx=16, pady=4)

        self.monitors_box = option_menu(
            tab,
            self._themed,
            ["pointer", "primary", "focused"],
            self._on_placement,
            width=160,
        )
        self.monitors_box.set(str(self._config.opt("monitors", "placement", "pointer")))
        self.monitors_box.pack(anchor="w", padx=16, pady=4)
        label(
            tab, self._themed, "New windows open on the…", color_token="text_dim", size=11
        ).pack(anchor="w", padx=16, pady=(4, 8))

        self.per_monitor = ctk.CTkSwitch(
            tab,
            text="Show a taskbar on every monitor",
            font=self._themed.font(),
            text_color=self._theme.get("text"),
            progress_color=self._theme.get("accent"),
            button_color=self._theme.get("panel_hover"),
            button_hover_color=self._theme.get("accent_hover"),
            command=self._on_per_monitor,
        )
        self.per_monitor.select() if self._config.opt(
            "monitors", "taskbar_per_monitor", True
        ) else self.per_monitor.deselect()
        self.per_monitor.pack(anchor="w", padx=16, pady=4)

        self.follows_mouse = ctk.CTkSwitch(
            tab,
            text="Move the focus with the mouse",
            font=self._themed.font(),
            text_color=self._theme.get("text"),
            progress_color=self._theme.get("accent"),
            button_color=self._theme.get("panel_hover"),
            button_hover_color=self._theme.get("accent_hover"),
            command=self._on_follows_mouse,
        )
        if self._config.opt("focus", "follows_mouse", False):
            self.follows_mouse.select()
        else:
            self.follows_mouse.deselect()
        self.follows_mouse.pack(anchor="w", padx=16, pady=4)

    def _on_position(self, value: str) -> None:
        self._callbacks.on_taskbar_option("position", value)

    def _on_placement(self, value: str) -> None:
        self._callbacks.on_taskbar_option("placement", value)

    def _on_per_monitor(self) -> None:
        self._callbacks.on_taskbar_option(
            "taskbar_per_monitor", bool(self.per_monitor.get())
        )

    def _on_follows_mouse(self) -> None:
        self._callbacks.on_focus_option("follows_mouse", bool(self.follows_mouse.get()))

    # -----------------------------------------------------------------
    # Quick launch
    # -----------------------------------------------------------------
    def _build_launch(self) -> None:
        tab = self.launch_tab
        label(tab, self._themed, "Pinned applications", weight="bold").pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        self.launch_list = ctk.CTkScrollableFrame(
            tab,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=self._theme.get("border_strong"),
            scrollbar_button_hover_color=self._theme.get("accent"),
            height=280,
        )
        self.launch_list.pack(fill="both", expand=True, padx=12, pady=6)
        self._refresh_launch_list()

        row = ctk.CTkFrame(tab, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=16, pady=8)
        button(row, self._themed, "Add application…", self._callbacks.on_add_launch, width=170).pack(
            side="left"
        )
        button(row, self._themed, "Remove selected", self._remove_launch, width=150).pack(
            side="left", padx=8
        )
        self.launch_selected: int | None = None

    def _refresh_launch_list(self) -> None:
        for child in self.launch_list.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        for index, item in enumerate(self._config.quick_launch):
            row = ctk.CTkFrame(self.launch_list, fg_color="transparent", corner_radius=0)
            row.pack(fill="x", padx=4, pady=2)
            button(
                row,
                self._themed,
                "Select",
                lambda idx=index: self._select_launch(idx),
                width=70,
                height=24,
            ).pack(side="left")
            label(row, self._themed, str(item.get("label", ""))[:24]).pack(side="left", padx=8)
            label(
                row,
                self._themed,
                " ".join(item.get("cmd", []))[:40],
                color_token="text_faint",
                size=11,
                mono=True,
            ).pack(side="left")

    def _select_launch(self, index: int) -> None:
        self.launch_selected = index

    def _remove_launch(self) -> None:
        if self.launch_selected is None:
            return
        items = self._config.quick_launch
        if 0 <= self.launch_selected < len(items):
            del items[self.launch_selected]
            self._config.quick_launch = items
            self.launch_selected = None
            self._refresh_launch_list()
            self._callbacks.on_launch_changed()

    def apply_theme(self, theme: Theme) -> None:
        super().apply_theme(theme)
        self._themed = Themed(theme)
        self.container.configure(fg_color=theme.get("surface"))
        self._refresh_launch_list()


class SettingsCallbacks:
    """Interface the settings window uses to talk back to the shell."""

    def on_theme_selected(self, name: str) -> None:
        """A different theme was picked."""

    def on_theme_editor(self) -> None:
        """The theme editor should be opened."""

    def on_import_theme(self) -> None:
        """The desktop theme should be imported."""

    def on_desktops_changed(self, count: int, names: list[str]) -> None:
        """The virtual desktop configuration changed."""

    def on_change_wallpaper(self) -> None:
        """A new wallpaper should be picked."""

    def on_reset_wallpaper(self) -> None:
        """The wallpaper should be reset to the default."""

    def on_taskbar_option(self, key: str, value: Any) -> None:
        """A taskbar or monitor option changed."""

    def on_focus_option(self, key: str, value: Any) -> None:
        """A focus option changed."""

    def on_add_launch(self) -> None:
        """An application should be pinned."""

    def on_launch_changed(self) -> None:
        """The pinned applications changed."""
