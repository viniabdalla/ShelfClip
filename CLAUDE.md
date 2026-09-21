# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository

ShelfClip — a minimal Yoink-style file shelf for Omarchy (Hyprland / Wayland). A collapsed edge strip on the right of each monitor opens into a panel in the top-right corner (under the bar) when a file is dragged onto it or `shelfclip toggle` runs; the panel grows downward as tiles are added.

**Stack:** Python 3 + GTK4 (PyGObject) + gtk4-layer-shell. Single file: `main.py`. The old Windows/PyQt6 app lives on the `windows-pyqt6` branch (and `main`).

## Running

```bash
./shelfclip                  # start (or `python main.py`)
./shelfclip toggle|paste|clear|reload-theme|quit   # control the running instance
```

Deps are system packages (`python-gobject gtk4 gtk4-layer-shell wl-clipboard`), already on Omarchy. There are no automated tests; verify by running it. Useful checks:

```bash
hyprctl layers -j     # find namespace "shelfclip": x/y/w/h per monitor
grim -o DP-1 out.png  # screenshot a monitor
wl-copy --type text/uri-list <<< "file:///path/a"; ./shelfclip paste   # stage files without dragging
```

Real drag-and-drop can't be automated here; test it by hand.

## Architecture (`main.py`)

| Symbol | Role |
|---|---|
| `Shelf` | Shared model: `paths`, `selected`, `last_clicked`, plus `on_items` / `on_selection` callback lists. `click()` holds the Ctrl/Shift selection logic. |
| `Tile` (`Gtk.Overlay`) | One staged file: thumbnail/icon, name, hover-only × button. Owns the `GestureClick` (selection) and `DragSource` (drag-out, single or whole selection). |
| `ShelfWindow` | One layer-shell window per monitor: `Gtk.Revealer(panel)` + a transparent edge `strip`. Owns the `DropTarget`, key handling and sizing (`_fit`). |
| `ShelfApp` | `Gtk.Application` (`HANDLES_COMMAND_LINE`, single instance via D-Bus). Decides which window is open (`open_on`, `close_all`, `toggle`), thumbnails, `wl-paste` clipboard, theme reload. |
| `load_palette` / `build_css` | Read the active Omarchy theme's `colors.toml`, generate the CSS. |

Config lives in `~/.config/shelfclip/config.json` (`DEFAULTS` at the top of `main.py`).

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

`docs/superpowers/` holds design specs and plans from the Windows era (multi-monitor mode etc.). They describe the PyQt6 app and are kept for history.
