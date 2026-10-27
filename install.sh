#!/usr/bin/env bash
# Install or update ShelfClip from this checkout. Safe to run again after every `git pull`.
#   - links ~/.local/bin/shelfclip to this checkout
#   - starts it with Hyprland (autostart) and binds Ctrl+Y to `shelfclip toggle`
#   - restarts the running instance so the new code is live
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BIN="$HOME/.local/bin/shelfclip"
HYPR="$HOME/.config/hypr"
STAMP="$(date +%Y%m%d-%H%M%S)"

# deps (system packages; we never sudo for you)
missing=()
for pkg in python-gobject gtk4 gtk4-layer-shell wl-clipboard; do
    pacman -Q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
    echo "Missing packages. Install them, then run this again:"
    echo "  sudo pacman -S ${missing[*]}"
    exit 1
fi
command -v tailscale >/dev/null || echo "note: tailscale not found; sharing the shelf won't work."

# launcher
mkdir -p "$(dirname "$BIN")"
ln -sfn "$REPO/shelfclip" "$BIN"
echo "linked $BIN -> $REPO/shelfclip"

backup() { [[ -f "$1.bak.shelfclip-$STAMP" ]] || cp "$1" "$1.bak.shelfclip-$STAMP"; }

# Omarchy configs are Lua (autostart.lua / bindings.lua); older installs use .conf.
if [[ -f "$HYPR/bindings.lua" ]]; then
    AUTOSTART="$HYPR/autostart.lua"
    START_LINE="o.launch_on_start(\"$BIN\")"
    BINDINGS="$HYPR/bindings.lua"
    BIND_LINE='o.bind("CTRL + Y", "ShelfClip toggle", "shelfclip toggle")'
    BIND_MATCH='"ShelfClip toggle"'
    COMMENT='--'
else
    AUTOSTART="$HYPR/autostart.conf"
    START_LINE="exec-once = $BIN"
    BINDINGS="$HYPR/bindings.conf"
    BIND_LINE='bindd = CTRL, Y, ShelfClip toggle, exec, shelfclip toggle'
    BIND_MATCH='ShelfClip toggle'
    COMMENT='#'
fi
touch "$AUTOSTART" "$BINDINGS"

# autostart: one uncommented line launching shelfclip
if grep -v "^[[:space:]]*$COMMENT" "$AUTOSTART" | grep -q 'shelfclip'; then
    echo "autostart: already there ($AUTOSTART)"
else
    backup "$AUTOSTART"
    printf '\n%s ShelfClip file shelf.\n%s\n' "$COMMENT" "$START_LINE" >>"$AUTOSTART"
    echo "autostart: added to $AUTOSTART"
fi

# Ctrl+Y: replace any existing ShelfClip toggle bind (e.g. SUPER + Y), else add one
if grep -qxF "$BIND_LINE" "$BINDINGS"; then
    echo "keybind: Ctrl+Y already set ($BINDINGS)"
elif grep -v "^[[:space:]]*$COMMENT" "$BINDINGS" | grep -qF "$BIND_MATCH"; then
    backup "$BINDINGS"
    tmp="$(mktemp)"
    awk -v match_="$BIND_MATCH" -v line="$BIND_LINE" -v c="$COMMENT" '
        index($0, match_) && $0 !~ "^[[:space:]]*" c && !done { print line; done = 1; next }
        index($0, match_) && $0 !~ "^[[:space:]]*" c { next }
        { print }' "$BINDINGS" >"$tmp"
    cat "$tmp" >"$BINDINGS" && rm -f "$tmp"
    echo "keybind: switched ShelfClip toggle to Ctrl+Y in $BINDINGS"
else
    backup "$BINDINGS"
    printf '\n%s ShelfClip file shelf.\n%s\n' "$COMMENT" "$BIND_LINE" >>"$BINDINGS"
    echo "keybind: added Ctrl+Y to $BINDINGS"
fi

# restart the running instance (same app id, whichever copy it was started from)
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    if gdbus introspect --session --dest dev.shelfclip.ShelfClip --object-path / >/dev/null 2>&1; then
        "$BIN" quit || true
        sleep 1
    fi
    setsid -f "$BIN" >/dev/null 2>&1
    echo "ShelfClip (re)started. Ctrl+Y opens it; the gear in its header opens the settings."
fi
