# Pillarium 2.0

A lightweight X11 window manager and desktop environment.

Pillarium 2.0 is a complete rewrite of the 1.x code base.  The window
manager still talks to the X server directly through `python-xlib`, but
the whole user interface — the desktop, the taskbars, the window
decorations, the launcher, the panels and the dialogs — is now built with
[customtkinter](https://github.com/tomchen88/customtkinter).

## What is new in 2.0

* **A customtkinter user interface.**  Every surface Pillarium draws is
  a real widget, so themes, fonts and accessibility come for free.
* **A theme engine.**  Colours are tokens, not constants.  Three
  built-in palettes (Dark, Light, Retro) ship with Pillarium, and
  user themes are plain JSON files in `$PILLARIUM_HOME/themes`.
* **A theme editor.**  Pick any colour token, preview it live and save
  the result as your own theme.
* **freedesktop.org theme import.**  Pillarium reads the colour scheme
  and accent colour of the running desktop through the
  `org.freedesktop.portal.Settings` portal (with GNOME and KDE
  fallbacks) and turns them into a Pillarium palette.
* **Virtual desktops.**  Up to twelve workspaces, each with its own set
  of windows, a switcher in the taskbar and keyboard shortcuts.
* **Multi-monitor support.**  Every monitor gets its own taskbar, new
  windows open on the monitor under the pointer, and windows can be
  moved between monitors from the window menu.  Hotplug is handled
  through RandR.

## Requirements

* Python 3.9 or newer
* `python-xlib`, `Pillow`, `cairosvg`, `packaging`
* `customtkinter`
* `dbus-python` (optional, for desktop notifications)

```sh
pip install -r requirements.txt
```

The Debian package ships `customtkinter` and `darkdetect` itself (see
`vendor/`), because those two are not in every distribution archive and
Pillarium should install anywhere.

## Running

```sh
python3 -m pillarium            # start the window manager
python3 -m pillarium.alerts_cli # raise an alert from a script
```

To install the whole desktop session (LightDM entry, compositor
configuration and the `pillarium` command) build the Debian package:

```sh
./build_deb.sh
```

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Alt+Space` | Open the application launcher |
| `Alt+Tab` / `Alt+Shift+Tab` | Cycle through the open windows |
| `Alt+F4` | Close the focused window |
| `Alt+Return` | Open a terminal |
| `Alt+Shift+D` | Cycle through the themes |
| `Alt+Shift+P` | Power menu |
| `Alt+Shift+W` | Wi-Fi menu |
| `Alt+Shift+E` | Ethernet menu |
| `Alt+Shift+B` | Bluetooth menu |
| `Alt+Shift+A` | Audio menu |
| `Alt+Shift+M` | Process manager |
| `Alt+Shift+R` | Rescan the desktop folder |
| `Ctrl+Alt+Left` / `Ctrl+Alt+Right` | Previous / next virtual desktop |
| `Ctrl+Alt+1` … `Ctrl+Alt+4` | Jump to a virtual desktop |

The keyboard focus stays on the window you are working in; moving the
pointer over another window does not move the focus.  The classic
"focus follows mouse" behaviour can be switched on in the settings
(`focus.follows_mouse` in `config.json`).

Shortcuts can be changed in the `hotkeys` section of `config.json`.

## Configuration

Everything lives under `$PILLARIUM_HOME` (by default
`~/.pillarium`):

| File | Purpose |
| --- | --- |
| `config.json` | Settings, quick launch entries, wallpapers |
| `themes/*.json` | User authored themes |
| `pillarium.log` | Session log and crash traces |

The environment variables `PILLARIUM_HOME`, `PILLARIUM_CONFIG`,
`PILLARIUM_THEMES`, `PILLARIUM_WALLPAPER` and `PILLARIUM_DESKTOP`
override the individual locations.

## Layout of the source

```
pillarium/
├── app.py          the application: wiring, main loop, polling
├── config.py       the configuration model
├── core/           the X11 layer
│   ├── wm.py         window management, EWMH, virtual desktops
│   ├── monitors.py   RandR monitor discovery
│   ├── hotkeys.py    keyboard shortcuts
│   └── clients.py    the managed window model
├── shell/          the customtkinter user interface
│   ├── shell.py      the coordinator
│   ├── desktop.py    wallpaper and desktop icons
│   ├── taskbar.py    per monitor taskbars
│   ├── decorations.py window frames
│   ├── launcher.py   application search
│   ├── menu.py       popup menus
│   ├── panels.py     mixer, process manager, calendar
│   ├── notifications.py toasts
│   ├── alerts.py     modal dialogs
│   ├── settings.py   the settings window
│   └── theme_editor.py the theme editor
├── system/         everything that talks to the operating system
├── theme/          the theme engine and the freedesktop.org import
└── util/           images, glyphs and other helpers
```

## Tests

```sh
python3 -m pytest tests/
```

The tests that need an X server start a private Xvfb automatically.

## License

MIT, see `debian/copyright`.
