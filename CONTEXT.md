# ShelfClip — Project Context

Yoink-style floating file shelf. Originally a Windows PyQt6 app (branch `windows-pyqt6`); now a GTK4 app for Omarchy (Hyprland / Wayland). See `CLAUDE.md` for architecture and gotchas, `README.md` for usage.

## What changed in the Omarchy port

| Windows (PyQt6) | Omarchy (GTK4 + layer-shell) |
|---|---|
| Frameless always-on-top translucent window, DWM tweaks | `gtk4-layer-shell` overlay surface anchored top-right, `exclusive_zone = 0` |
| Slides in from left/right edge with `QPropertyAnimation` | Collapses to an edge strip; `Gtk.Revealer` slides the panel out of it |
| `GetAsyncKeyState` polled every 80 ms to detect a drag near the edge | Thin always-mapped `Gtk.DropTarget` on the edge (Wayland can't read the mouse button globally) |
| `RegisterHotKey` / `WM_HOTKEY` | Hyprland `bind` running `shelfclip toggle` (`Gio.Application` single instance) |
| Glass card, settings dialog, dark/light + opacity | Flat panel styled from the active Omarchy theme, `config.json` only |
| Single/multi monitor modes | One window per monitor, the one you drag to (or focus) opens |
| Vertical list of 58 px rows | 120 px square tiles growing downward |
| `QDrag` with URLs | `Gtk.DragSource` with `Gdk.FileList`; group drag for multi-select |
| Clipboard via `QGuiApplication.clipboard()` | `wl-paste` (works without keyboard focus) |

## Design intent

Minimal, matches Omarchy's look: square corners, no blur/shadow, theme colors, monospace font. The shelf lives where the user pointed in their sketch: top-right corner, right under the bar, growing downward.

## Known limitations

- The collapsed edge strip (24 px wide, 136 px tall by default) swallows clicks on those pixels.
- Ctrl+V / Delete / Esc only work while the panel has keyboard focus (click it first). `shelfclip paste` works from anywhere.
- Non-file drags (text, browser images/URLs) are not accepted.
- Copy vs move can't be switched with Ctrl/Shift mid-drag (Hyprland doesn't implement it); it is decided at drag start (`drag_action`, default move; Ctrl flips it).
