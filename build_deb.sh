#!/usr/bin/env bash
# Build the Pillarium .deb package (Cadet packaging system).
# Usage: ./build_deb.sh
set -euo pipefail

cd "$(dirname "$0")"

VER="2.0.0"
REL="3"
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
find "$STAGE/usr/lib/python3/dist-packages/pillarium" -name '*.pyc' -delete 2>/dev/null || true

# --- vendored user interface toolkit --------------------------------------
# customtkinter is not in every distribution archive (it was dropped from
# Debian and Ubuntu), so Pillarium ships it.  A version installed with
# pip still takes precedence, because user site directories come first
# on the Python path.
if [ -d vendor ]; then
    cp -r vendor/customtkinter "$STAGE/usr/lib/python3/dist-packages/customtkinter"
    cp -r vendor/darkdetect "$STAGE/usr/lib/python3/dist-packages/darkdetect"
    mkdir -p "$STAGE/usr/share/doc/pillarium/vendor"
    cp vendor/LICENSE.* "$STAGE/usr/share/doc/pillarium/vendor/" 2>/dev/null || true
    cp vendor/README.md "$STAGE/usr/share/doc/pillarium/vendor/README" 2>/dev/null || true
    find "$STAGE/usr/lib/python3/dist-packages/customtkinter" -name '__pycache__' \
        -type d -exec rm -rf {} + 2>/dev/null || true
    find "$STAGE/usr/lib/python3/dist-packages/darkdetect" -name '__pycache__' \
        -type d -exec rm -rf {} + 2>/dev/null || true
    find "$STAGE/usr/lib/python3/dist-packages" -name '.DS_Store' -delete 2>/dev/null || true
fi

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
exec /usr/bin/python3 -m pillarium >>"$PILLARIUM_HOME/pillarium.log" 2>&1
EOF
chmod 755 "$STAGE/usr/bin/pillarium"

# --- alert CLI launcher --------------------------------------------------
cat > "$STAGE/usr/bin/pillarium-notify" <<'EOF'
#!/bin/sh
# Raise a Pillarium alert dialog from scripts, apps or the command line.
# Usage: pillarium-notify [--error|--warning|--startup] [-t TITLE] MESSAGE
exec /usr/bin/python3 -m pillarium.alerts_cli "$@"
EOF
chmod 755 "$STAGE/usr/bin/pillarium-notify"

# --- runtime data --------------------------------------------------------
cp pillarium/defaults/config.json "$STAGE/usr/share/pillarium/config.json"
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
.TH PILLARIUM 1 "October 2026" "Pillarium 2.0.0" "User Commands"
.SH NAME
pillarium \- lightweight X11 window manager / desktop environment
.SH SYNOPSIS
.B pillarium
.SH DESCRIPTION
.B pillarium
is a minimalistic window manager written in pure Python on top of
python\-xlib, with a customtkinter user interface.  It provides
application menus, desktop icons, wallpaper, per\-monitor taskbars,
virtual desktops, a themeable desktop and window decorations.
.SH ENVIRONMENT
.TP
.B PILLARIUM_HOME
Directory holding config.json, the themes and the log.  Defaults to
.I ~/.pillarium
when unset.
.TP
.B PILLARIUM_CONFIG
Absolute path of the configuration file.
.TP
.B PILLARIUM_THEMES
Directory holding user authored theme files.
.TP
.B PILLARIUM_WALLPAPER
Absolute path of the default wallpaper image.
.TP
.B PILLARIUM_DESKTOP
Desktop folder scanned for icons.
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
.TH PILLARIUM-NOTIFY 1 "October 2026" "Pillarium 2.0.0" "User Commands"
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
cp README.md "$STAGE/usr/share/doc/pillarium/README"
gzip -9 -n -f "$STAGE/usr/share/doc/pillarium/README"
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
Depends: python3 (>= 3.9), python3-xlib, python3-pil, python3-pil.imagetk,
         python3-cairosvg, python3-packaging, picom, lightdm-gtk-greeter
Recommends: python3-dbus, pipewire-bin | pulseaudio-utils, vorbis-tools
Description: lightweight X11 window manager / desktop environment
 A minimalistic window manager written in pure Python on top of
 python-xlib, with a customtkinter user interface.  Features application
 menus, bluetooth support, desktop icons, wallpaper, per-monitor taskbars
 and virtual desktops.
 .
 The customtkinter user interface toolkit is bundled with the package,
 so Pillarium installs on distributions that do not carry it.
 .
 Themes are token based: the Dark, Light and Retro palettes ship with
 Pillarium, users can author their own in ~/.pillarium/themes and the
 colours of the running desktop can be imported through the
 freedesktop.org settings portal.
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
