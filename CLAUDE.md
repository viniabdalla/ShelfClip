# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository

ShelfClip — a minimal Yoink-style file shelf for Omarchy (Hyprland / Wayland). A collapsed edge strip on the right of each monitor opens into a panel in the top-right corner (under the bar) when a file is dragged onto it or `shelfclip toggle` runs; the panel grows downward as tiles are added.

**Stack:** Python 3 + GTK4 (PyGObject) + gtk4-layer-shell. Single file: `main.py`, plus a small Omarchy plugin (`manifest.json` + `plugin/`). `omarchy` is the default branch; the old Windows/PyQt6 app lives on the `windows-pyqt6` branch (and `main`). MIT licensed.

## Running

```bash
./shelfclip                  # start (or `python main.py`)
./shelfclip toggle|paste|clear|settings|reload-theme|quit   # control the running instance
./install.sh [--yes]         # link ~/.local/bin/shelfclip, restart; asks before autostart + Ctrl+Y (idempotent)
omarchy plugin validate .    # check manifest.json before pushing
python3 tests/test_share.py -v   # sharing tests (not `-m unittest`: main.py re-execs with LD_PRELOAD)
```

Deps are system packages (`python-gobject gtk4 gtk4-layer-shell wl-clipboard`), already on Omarchy, plus `tailscale` for sharing. Only the sharing layer has automated tests (`tests/test_share.py`, loopback only); verify the UI by running it. Useful checks:

```bash
hyprctl layers -j     # find namespace "shelfclip": x/y/w/h per monitor
grim -o DP-1 out.png  # screenshot a monitor
wl-copy --type text/uri-list <<< "file:///path/a"; ./shelfclip paste   # stage files without dragging
```

Real drag-and-drop can't be automated here; test it by hand.

## Architecture (`main.py`)

| Symbol | Role |
|---|---|
| `Shelf` | Shared model: `paths`, `meta` (path → `{id, origin}`), `selected`, `last_clicked`, plus `on_items` / `on_selection` / `on_removed` callbacks and `on_local_add` / `on_local_remove`, which fire only for changes made on this machine (`remote=False`) so sharing never echoes. `click()` holds the Ctrl/Shift selection logic. |
| `Tile` (`Gtk.Overlay`) | One staged file: thumbnail/icon, name, hover-only × button. Owns the `GestureClick` (selection) and `DragSource` (drag-out, single or whole selection). |
| `ShelfWindow` | One layer-shell window per monitor: `Gtk.Revealer(panel)` + a transparent edge `strip`. Owns the `DropTarget`, key handling and sizing (`_fit`). |
| `SettingsWindow` | Centered layer surface (no anchors, namespace `shelfclip-settings`, keyboard EXCLUSIVE): show time / tile size sliders, share switch, online peers. |
| Wire protocol (`send_add`, `send_remove`, `ask_hello`, `ask_state`, `fetch`, `serve_conn`, `Listener`) | GTK-free. One request per TCP connection: JSON header line, then raw bytes (tar stream for dirs) until the sender shuts down its side. |
| `Share` | Tailscale glue + protocol handler: listener on the Tailscale IPv4 port 47811 while `share` is on, peer lookup via `tailscale status --json` (same `UserID`, online), push on local add/remove, pull+offer on enable. Worker threads only; results go back through `GLib.idle_add`. |
| `ShelfApp` | `Gtk.Application` (`HANDLES_COMMAND_LINE`, single instance via D-Bus). Decides which window is open (`open_on`, `close_all`, `toggle`), thumbnails, `wl-paste` clipboard, theme reload. |
| `load_palette` / `build_css` | Read the active Omarchy theme's `colors.toml`, generate the CSS. |
| `state_path()` | `$XDG_RUNTIME_DIR/shelfclip/state.json` = `{"count": N}`, rewritten atomically on every item change, deleted in `do_shutdown`. Read by the bar widget. SIGTERM quits cleanly (`_on_sigterm`). |

Config lives in `~/.config/shelfclip/config.json` (`DEFAULTS` at the top of `main.py`); the settings window writes it through `save_config()` (merge, debounced 300 ms). `ShelfApp.set_option()` applies a key live; `tile_size` rebuilds the tiles (`ShelfWindow.apply_tile_size`, debounced 150 ms).

## Behavior

- Empty shelf: collapsed to an `trigger_width`-wide strip on the screen edge. Drag enters the strip → panel opens. Empty + pointer/drag left → closes after `COLLAPSE_MS`. `toggle` on an empty shelf auto-closes after `show_time`.
- Shelf with files: stays open; `toggle` still closes/opens it manually. Adding a file re-opens it on the focused monitor.
- Only the "active" monitor's window is expanded; the others stay collapsed. Panel height is capped to the monitor minus the bar; the tile list scrolls beyond that.
- Drop target accepts `COPY | MOVE`. Nautilus here offers **only MOVE** (`Gdk.Drop.get_actions()` == 2), so a COPY-only target silently rejects every drag. Accepting MOVE is safe for file drags: we only store the path, and the file manager doesn't delete the original (verified). `_on_drag_enter` returns COPY when offered, otherwise MOVE.
- Drag-out offers a single action, chosen in `Tile._on_prepare`: `cfg["drag_action"]` (default `move`), flipped when Ctrl is held at drag start. **Hyprland doesn't support modifier-based DnD action selection** (Ctrl=copy / Shift=move never reach the target; upstream limitation, seen on 0.51 and here on 0.56), so the offer itself has to decide. Ctrl at drag start is safe because a Ctrl+press no longer toggles the selection immediately: `_defer_toggle` applies it on release, and only if no drag started (otherwise it would unselect the tile being dragged out of a multi-selection).
- Drag-out removes the tile only if the drop finished (`dnd-finished`). The decision is deferred with `GLib.idle_add` because `dnd-finished` and `drag-end` can arrive in either order. Dropping a tile back on the shelf is rejected (`app.internal_drag`, `app.keep_after_drop`). **Hyprland reports `dnd-finished` even when nobody accepted the drop** (bare desktop, bar) and the source never learns the negotiated action, so `cursor_over_window()` (hyprctl cursorpos + clients on the visible workspaces, checked at `drop-performed`) decides whether the drop landed on a window; if not, the tile stays. A window that rejects the drop (e.g. a terminal that ignores files) still unstages the tile, since there is no signal for that.
- **Opening on drag uses `Gtk.DropControllerMotion` (`_on_drag_peek`), not `DropTarget.enter`.** The compositor does deliver drags to the edge strip, but a sweep across it lasts a few ms and `DropTarget` only emits `enter` after the drop's actions arrive, so it never fired. The raw `enter` (filtered to drags carrying `Gdk.FileList`) opens the panel immediately; `DropTarget` still handles the actual drop.
- Pressing an already-selected tile in a multi-selection keeps the selection (so the group can be dragged) and collapses it on release if no drag started.
- Clipboard uses `wl-paste`, not the GTK clipboard, so `shelfclip paste` works without keyboard focus. Images/text are saved under `$XDG_RUNTIME_DIR/shelfclip/`.
- Header: count, `clear` (only with files) and the ⚙ gear (always). The empty shelf doesn't auto-collapse while the settings window is open.

## Sharing (Tailscale)

- Spec: `docs/superpowers/specs/2026-10-27-settings-and-tailscale-share-design.md`. No polling, no heartbeat: the only background thing is the blocking `accept()` of the listener. Peers are looked up when something must be sent (add/remove/clear, startup with `share`, switch on, settings open, `toggle` retries the listener if Tailscale wasn't up).
- Items are identified by `meta[path]["id"]` (uuid hex), the same on every machine. Received files go to `$XDG_RUNTIME_DIR/shelfclip/shared/<id>/<name>` and are deleted 60 s after leaving the shelf (a COPY drop may still be reading). Local originals are never touched.
- `origin` is `None` for items staged here; `Share._wire()` fills in the Tailscale hostname only when the item is sent (the hostname is known once Tailscale has answered). Tiles show an `origin` badge when it isn't this host.
- `Listener` accepts only the machine's own IP and same-user peers (`Share._allow`, rechecked per connection). Receivers strip any path from a peer's file name and unpack tars with `filter="data"`.
- Machines run this same code; deploy = push, then `git pull && ./install.sh` on each checkout machine (or `omarchy plugin update viniabdalla.shelfclip` where it is installed as a plugin).

## Omarchy plugin

- Listed on the Omarchy plugin marketplace (plugins.omarchy.org, submissions via issues on `omacom/omarchy-plugin-marketplace`). `omarchy plugin add <repo>` clones the **default branch** into `~/.config/omarchy/plugins/viniabdalla.shelfclip`, so the whole repo is the plugin; the validator rejects any symlink in it.
- `manifest.json` (root): id `viniabdalla.shelfclip`, kinds `service` + `bar-widget`. Bump `version` on releases.
- `plugin/Service.qml` starts `../shelfclip` on load (single instance: a no-op if one already runs). The shell keeps services across rescans and destroys them only on disable/remove/shell exit; `onDestruction` waits 3 s, asks `omarchy-plugin-list` whether the plugin is still enabled, and otherwise `pkill -TERM`s only the `main.py` of this checkout.
- `plugin/BarWidget.qml` watches `state.json` (`FileView`, plus a 5 s re-read) and runs `shelfclip toggle` / `settings` via `Util.execArgv`.
- Testing: install a real **copy** (`rsync -a --exclude .git ./ ~/.config/omarchy/plugins/viniabdalla.shelfclip/`), not a symlink: Qt refuses a symlinked plugin dir whose name differs from the target only by case ("File name case mismatch", e.g. `viniabdalla.shelfclip` → `Shelfclip`). The shell also caches compiled QML by URL, so an edited entry point isn't reloaded until the shell restarts (`omarchy-restart-shell`). `omarchy-shell` IPC times out at 2 s, which `rescanPlugins` / `plugin enable` can exceed here: set `OMARCHY_SHELL_IPC_TIMEOUT=30s`. From a non-session shell also export `WAYLAND_DISPLAY=wayland-1` and `OMARCHY_PATH=/usr/share/omarchy`. Logs: `qs log -n -p /usr/share/omarchy/shell`.
- `install.sh` is the non-plugin path. Store rule: never edit user config without consent, so it asks (or needs `--yes`) before touching `autostart.lua` / `bindings.lua`.

## Wayland / layer-shell gotchas

- **`LD_PRELOAD` is required.** gtk4-layer-shell must load before libwayland-client. `_ensure_layer_shell_preload()` re-execs once. Strip `LD_PRELOAD` from child processes (`CLEAN_ENV`).
- **Layer surfaces don't shrink on their own.** `ShelfWindow._fit()` sets the default size explicitly: strip size when collapsed, panel natural size when open. Shrinking waits for the revealer's `child-revealed` so the slide-out isn't cut off.
- **Never make the strip fully transparent.** Hyprland reports/keeps a stale 200x200 geometry for a surface whose buffer is entirely alpha 0. `.strip` uses `rgba(0,0,0,0.01)`.
- Tile width must not depend on content: `Gtk.Label` uses `max_width_chars=1` (ellipsize instead of widening), thumbnails are square-cropped `Gtk.Image` with fixed `pixel_size` (a `Gtk.Picture` reports its intrinsic size and widens the tile).
- `exclusive_zone = 0` makes the compositor place the panel below the bar automatically; the right margin is 0 so the strip touches the true screen edge (a margin would leave a dead pixel band that can't receive drags).
- `Gdk.Texture.new_for_pixbuf` is deprecated; thumbnails use `Gdk.MemoryTexture`.

## Theme

`~/.local/state/omarchy/current/theme/colors.toml` (keys `bg fg accent muted selection lighter_bg red`, with fallbacks to `background/foreground/color*`). `omarchy-theme-set` replaces `current/theme` then rewrites `theme.name`; `ShelfApp` watches the `current/` directory and reloads the CSS after a 400ms debounce. Look matches the user's Hyprland: square corners, no blur, no shadow, 2px gaps.

## Planning Docs

`docs/superpowers/` holds design specs and plans. Those dated before 2026-10 are from the Windows era (multi-monitor mode etc.), describe the PyQt6 app and are kept for history. `specs/2026-10-27-settings-and-tailscale-share-design.md` and its plan cover the settings window, `install.sh` and the shared shelf.
