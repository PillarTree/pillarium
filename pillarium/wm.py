"""The composed Pillarium window manager.

The behaviour lives in focused mixin modules (theme, drawing,
decorations, icons, apps, config, launch, desktop, taskbar, menus,
search, wifi, bluetooth, audio, battery, clock, processes, core,
input); this module glues them into a single :class:`Pillarium` class
and drives construction.
"""

from .apps import AppMixin
from .alerts import AlertMixin
from .audio import AudioMixin
from .battery import BatteryMixin
from .bluetooth import BluetoothMixin
from .clock import ClockMixin
from .config import ConfigMixin
from .constants import (
    ALERT_BTN_H,
    ALERT_BTN_MIN_W,
    ALERT_MAX_H,
    ALERT_MIN_H,
    ALERT_PAD,
    ALERT_W,
    AUDIO_W,
    BATTERY_W,
    BLUETOOTH_W,
    BORDER,
    CLOCK_W,
    CUSTOM_WIDGET_W,
    ETH_W,
    MIN_WINDOW_H,
    MIN_WINDOW_W,
    MIXER_HEADER_H,
    MIXER_ROW_H,
    MIXER_SLIDER_X0,
    MIXER_W,
    NOTIFICATION_GAP,
    NOTIFICATION_H,
    NOTIFICATION_MAX_VISIBLE,
    NOTIFICATION_W,
    POWER_W,
    PROC_HEADER_H,
    PROC_ROW_H,
    PROC_W,
    RESIZE_GRIP,
    SEARCH_W,
    TITLEBAR_H,
    WIFI_W,
    WINDOW_BTN_SIZE,
)
from .core import CoreMixin
from .decorations import DecorationMixin
from .desktop import DesktopMixin
from .drawing import DrawingMixin
from .ethernet import EthernetMixin
from .icons import IconMixin
from .input import InputMixin
from .launch import LaunchMixin
from .menus import MenuMixin
from .notification import NotificationMixin
from .processes import ProcessMixin
from .search import SearchMixin
from .taskbar import TaskbarMixin
from .theme import ThemeMixin
from .wifi import WifiMixin


class Pillarium(
    ConfigMixin,
    ThemeMixin,
    DrawingMixin,
    DecorationMixin,
    IconMixin,
    AppMixin,
    LaunchMixin,
    DesktopMixin,
    TaskbarMixin,
    MenuMixin,
    SearchMixin,
    WifiMixin,
    EthernetMixin,
    BluetoothMixin,
    AudioMixin,
    BatteryMixin,
    ClockMixin,
    ProcessMixin,
    InputMixin,
    NotificationMixin,
    AlertMixin,
    CoreMixin,
):
    # -----------------------------------------------------------------
    # Geometry constants
    # -----------------------------------------------------------------
    TITLEBAR_H = TITLEBAR_H
    BORDER = BORDER
    POWER_W = POWER_W
    WIFI_W = WIFI_W
    BLUETOOTH_W = BLUETOOTH_W
    AUDIO_W = AUDIO_W
    ETH_W = ETH_W
    BATTERY_W = BATTERY_W
    CLOCK_W = CLOCK_W
    CUSTOM_WIDGET_W = CUSTOM_WIDGET_W
    WINDOW_BTN_SIZE = WINDOW_BTN_SIZE
    RESIZE_GRIP = RESIZE_GRIP
    MIN_WINDOW_W = MIN_WINDOW_W
    MIN_WINDOW_H = MIN_WINDOW_H
    SEARCH_W = SEARCH_W
    MIXER_W = MIXER_W
    MIXER_ROW_H = MIXER_ROW_H
    MIXER_HEADER_H = MIXER_HEADER_H
    MIXER_SLIDER_X0 = MIXER_SLIDER_X0
    PROC_W = PROC_W
    PROC_HEADER_H = PROC_HEADER_H
    PROC_ROW_H = PROC_ROW_H
    NOTIFICATION_W = NOTIFICATION_W
    NOTIFICATION_H = NOTIFICATION_H
    NOTIFICATION_GAP = NOTIFICATION_GAP
    NOTIFICATION_MAX_VISIBLE = NOTIFICATION_MAX_VISIBLE

    # Modal alert dialogs
    ALERT_W = ALERT_W
    ALERT_PAD = ALERT_PAD
    ALERT_MIN_H = ALERT_MIN_H
    ALERT_MAX_H = ALERT_MAX_H
    ALERT_BTN_H = ALERT_BTN_H
    ALERT_BTN_MIN_W = ALERT_BTN_MIN_W

    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def __init__(self):
        # Display, screen, hot‑keys, font, bookkeeping
        self._init_core()
        # Palettes (dark / light)
        self._init_theme()
        # Wallpaper + config.json (variable directory locations)
        self._init_config()
        # Application catalog + desktop-folder scan
        self._init_apps()
        # Desktop window + icon interaction state
        self._init_desktop()
        # Popup menu / confirmation-dialog state
        self._init_menus()
        # Search popup state
        self._init_search()
        # Wi‑Fi status + auth-dialog state
        self._init_wifi()
        # Ethernet status
        self._init_ethernet()
        # Bluetooth status
        self._init_bluetooth()
        # Audio status + mixer state
        self._init_audio()
        # Battery status
        self._init_battery()
        # Clock calendar panel state
        self._init_clock()
        # Process list panel state
        self._init_processes()
        # Task‑bar
        self._init_taskbar()
        # Notifications
        self._init_notifications()
        # Modal alert dialogs (startup / warning / error)
        self._init_alerts()
        # Banner + initial polls
        self._welcome()


__all__ = ["Pillarium"]
