#!/usr/bin/env bash
# Build the Pillarium .deb package (Cadet packaging system).
# Usage: ./build_deb.sh
set -euo pipefail

cd "$(dirname "$0")"

VER="1.0.7"
REL="1"
PKG="pillarium_${VER}-${REL}_all"
STAGE="debian/${PKG}"
OUT="pillarium_${VER}-${REL}.deb"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN"
mkdir -p "$STAGE/usr/bin"
mkdir -p "$STAGE/usr/lib/python3/dist-packages"
mkdir -p "$STAGE/usr/share/pillarium"
mkdir -p "$STAGE/usr/share/xsessions"
mkdir -p "$STAGE/usr/share/doc/pillarium"
mkdir -p "$STAGE/usr/share/man/man1"
mkdir -p "$STAGE/usr/share/icons/hicolor/48x48/apps"
mkdir -p "$STAGE/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$STAGE/usr/share/pixmaps"
mkdir -p "$STAGE/etc/lightdm/lightdm.conf.d"

# --- Python package ------------------------------------------------------
cp -r pillarium "$STAGE/usr/lib/python3/dist-packages/pillarium"
find "$STAGE/usr/lib/python3/dist-packages/pillarium" -name '__pycache__' \
    -type d -exec rm -rf {} + 2>/dev/null || true

# --- launcher ------------------------------------------------------------
cat > "$STAGE/usr/bin/pillarium" <<'EOF'
#!/bin/sh
set -e
PILLARIUM_HOME="${PILLARIUM_HOME:-$HOME/.pillarium}"
export PILLARIUM_HOME
mkdir -p "$PILLARIUM_HOME"
[ -f "$PILLARIUM_HOME/config.json" ] \
    || cp /usr/share/pillarium/config.json "$PILLARIUM_HOME/" 2>/dev/null || true
[ -f "$PILLARIUM_HOME/pillarium_wallpaper.png" ] \
    || cp /usr/share/pillarium/pillarium_wallpaper.png "$PILLARIUM_HOME/" 2>/dev/null || true
if command -v picom >/dev/null 2>&1; then
    picom -b --config /usr/share/pillarium/picom.conf >/dev/null 2>&1 &
fi
exec python3 /usr/share/pillarium/pillarium_x11.py
EOF
chmod 755 "$STAGE/usr/bin/pillarium"

# --- alert CLI launcher --------------------------------------------------
cat > "$STAGE/usr/bin/pillarium-notify" <<'EOF'
#!/bin/sh
# Raise a Pillarium alert dialog from scripts, apps or the command line.
# Usage: pillarium-notify [--error|--warning|--startup] [-t TITLE] MESSAGE
exec python3 -m pillarium.alerts_cli "$@"
EOF
chmod 755 "$STAGE/usr/bin/pillarium-notify"

# --- runtime data --------------------------------------------------------
cp pillarium_x11.py "$STAGE/usr/share/pillarium/pillarium_x11.py"
cp config.json "$STAGE/usr/share/pillarium/config.json"
cp pillarium_wallpaper.png "$STAGE/usr/share/pillarium/pillarium_wallpaper.png"
cp picom-conf.conf "$STAGE/usr/share/pillarium/picom.conf"

# --- lightdm session + drop-in config ------------------------------------
cat > "$STAGE/usr/share/xsessions/pillarium.desktop" <<'EOF'
[Desktop Entry]
Name=Pillarium Window Manager
Comment=A minimalist X11 window manager
Exec=pillarium
TryExec=python3
Type=Application
DesktopNames=pillarium
EOF
cat > "$STAGE/etc/lightdm/lightdm.conf.d/50-pillarium.conf" <<'EOF'
[Seat:*]
greeter=lightdm-gtk-greeter
user-session=pillarium
EOF
printf '%s\n' "/etc/lightdm/lightdm.conf.d/50-pillarium.conf" \
    > "$STAGE/DEBIAN/conffiles"

# --- icon ----------------------------------------------------------------
STAGE="$STAGE" python3 - <<'PYEOF'
import os
from PIL import Image, ImageDraw

def make_icon(size):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(s * 0.08)
    r = max(4, int(s * 0.12))
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=r,
                        fill=(44, 49, 58, 255))
    def fx(v): return int(v * s)
    # window body + title bar (blue), two "window control" dots
    d.rounded_rectangle([fx(0.24), fx(0.34), fx(0.76), fx(0.66)],
                        radius=fx(0.04), fill=(94, 129, 172, 255))
    d.rectangle([fx(0.24), fx(0.34), fx(0.76), fx(0.43)], fill=(129, 161, 193, 255))
    for cx in (0.33, 0.40, 0.47):
        d.ellipse([fx(cx), fx(0.375), fx(cx + 0.04), fx(0.415)],
                  fill=(44, 49, 58, 255))
    return img

for s in (48, 128):
    p = os.path.join(os.environ["STAGE"],
                     f"usr/share/icons/hicolor/{s}x{s}/apps/pillarium.png")
    make_icon(s).save(p)
make_icon(48).save(os.path.join(os.environ["STAGE"],
                                "usr/share/pixmaps/pillarium.png"))
PYEOF

# --- man page ------------------------------------------------------------
cat > "$STAGE/usr/share/man/man1/pillarium.1" <<'EOF'
.TH PILLARIUM 1 "September 2026" "Pillarium 1.0.7" "User Commands"
.SH NAME
pillarium \- lightweight X11 window manager / desktop environment
.SH SYNOPSIS
.B pillarium
.SH DESCRIPTION
.B pillarium
is a minimalistic window manager written in pure Python on top of
python\-xlib. It provides an application menu, desktop icons, wallpaper,
a taskbar and window decorations.
.SH ENVIRONMENT
.TP
.B PILLARIUM_HOME
Directory holding config.json and the wallpaper.  Defaults to
.I ~/.pillarium
when unset.
.SH FILES
.TP
.I /usr/share/xsessions/pillarium.desktop
LightDM session entry.
.TP
.I /etc/lightdm/lightdm.conf.d/50-pillarium.conf
Selects the Pillarium session as the user session.
.SH SEE ALSO
.BR pillarium-notify (1)
.SH AUTHOR
Pillarium Developers.
EOF
gzip -9 -n -f "$STAGE/usr/share/man/man1/pillarium.1"

# --- pillarium-notify man page -------------------------------------------
cat > "$STAGE/usr/share/man/man1/pillarium-notify.1" <<'EOF'
.TH PILLARIUM-NOTIFY 1 "September 2026" "Pillarium 1.0.7" "User Commands"
.SH NAME
pillarium-notify \- raise an alert dialog in a running Pillarium session
.SH SYNOPSIS
.B pillarium-notify
.RI [ level ]
.RI [ \-t " title" ]
.RI [ \-a " app" ]
.RI [ \-d " detail" ]
.RI [ \-\-timeout " seconds" ]
.RI [ \-\-no-sound ]
.I message
.SH DESCRIPTION
.B pillarium-notify
connects to the running Pillarium window manager and asks it to display a
modal alert dialog.  It is the command-line front end to Pillarium's alert
system and is also used by applications to report warnings and errors.
.PP
The alert
.I level
is one of
.BR \-\-error ,
.BR \-\-warning
or
.BR \-\-startup .
If omitted, the level defaults to
.BR warning .
.SH OPTIONS
.TP
.B \-\-error
Show an error alert (red).
.TP
.B \-\-warning
Show a warning alert (amber).
.TP
.B \-\-startup
Show a startup alert (blue).
.TP
.BI \-t ", " \-\-title " title"
Override the dialog title.
.TP
.BI \-a ", " \-\-app " app"
Name of the application raising the alert.
.TP
.BI \-d ", " \-\-detail " detail"
Extra detail line shown under the message.
.TP
.BI \-\-timeout " seconds"
Auto-dismiss after this many seconds (0 keeps it open).
.TP
.B \-\-no-sound
Do not play the alert chime.
.SH EXIT STATUS
Returns 0 on success and a non-zero status if no Pillarium alert socket
is available.
.SH AUTHOR
Pillarium Developers.
EOF
gzip -9 -n -f "$STAGE/usr/share/man/man1/pillarium-notify.1"

# --- docs ----------------------------------------------------------------
cat > "$STAGE/usr/share/doc/pillarium/README" <<'EOF'
Pillarium - a lightweight X11 window manager / desktop environment
=================================================================

Written in pure Python on top of python-xlib.  Features application
menus, bluetooth support, desktop icons, wallpaper and a taskbar.

Launch with:  pillarium

Pillarium shows modal alert dialogs for startup, warning and error
events.  Unresponsive applications (missing _NET_WM_PING replies) and
critical D-Bus notifications raise error alerts; scripts and other
programs can raise alerts with:

    pillarium-notify --warning -t "Disk full" "/home is 100% full"

Each alert plays a chime from /usr/lib/python3/dist-packages/pillarium/
sounds (Ogg Vorbis).  Sound and volume can be tuned in the "alerts"
section of config.json.

The first launch copies /usr/share/pillarium/{config.json,
pillarium_wallpaper.png} into ~/.pillarium for easy user tweaking.

Runtime paths can be overridden with PILLARIUM_HOME, PILLARIUM_CONFIG
and PILLARIUM_WALLPAPER (see the pillarium.paths module).
EOF
cp debian/copyright "$STAGE/usr/share/doc/pillarium/copyright"
cp debian/changelog "$STAGE/usr/share/doc/pillarium/changelog.Debian"
gzip -9 -n -f "$STAGE/usr/share/doc/pillarium/changelog.Debian"

# --- control -------------------------------------------------------------
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/usr/bin/pillarium"
chmod 755 "$STAGE/usr/bin/pillarium-notify"

INSTALLED=$(du -sk "$STAGE" | awk '{print $1}')
cat > "$STAGE/DEBIAN/control" <<EOF
Package: pillarium
Version: ${VER}-${REL}
Section: x11
Priority: optional
Architecture: all
Maintainer: Pillarium Developers <pillarium@users.noreply.github.com>
Installed-Size: ${INSTALLED}
Depends: python3 (>= 3.9), python3-xlib, python3-pil, python3-cairosvg, picom, lightdm-gtk-greeter
Recommends: python3-dbus, pipewire-bin | pulseaudio-utils, vorbis-tools
Description: lightweight X11 window manager / desktop environment
 A minimalistic window manager written in pure Python on top of
 python-xlib. Features application menus, bluetooth support, desktop
 icons, wallpaper, and a taskbar.
 .
 Modal alert dialogs report startup, warning and error events, with
 optional chimes; unresponsive applications and critical D-Bus
 notifications raise error alerts, and the pillarium-notify utility
 lets scripts raise alerts from the command line.
 .
 The window manager source is installed as the 'pillarium' Python package
 under /usr/lib/python3/dist-packages; the 'pillarium' command starts
 the compositor and the window manager.  Runtime data (config, wallpaper)
 is copied to ~/.pillarium on first launch.
EOF

# --- build ---------------------------------------------------------------
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
rm -rf "$STAGE"
echo "Built: $OUT"