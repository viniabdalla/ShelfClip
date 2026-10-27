# ShelfClip

A minimal, Yoink-style file shelf for [Omarchy](https://omarchy.org) (Hyprland / Wayland).

It sits collapsed on the right screen edge, just under the bar. Drag a file to that edge and a small panel opens in the top-right corner; drop the file and it stays staged there. Every new file adds a tile and the panel grows downward. Drag tiles back out into any app or folder when you need them.

The Windows / PyQt6 version lives on the `windows-pyqt6` branch.

## Features

- Drag-in from the edge, or open with a keybind
- Tiles with image thumbnails or file icons, growing downward from the corner
- One panel per monitor; it opens on the monitor you dragged to (or the focused one for the keybind)
- Multi-select (Ctrl+click, Shift+click, Ctrl+A) and multi-file drag-out
- Paste files, images or text from the clipboard
- Colors follow the active Omarchy theme and update live when you switch themes
- Settings window (the ⚙ in the panel header): show time and tile size sliders, live
- Shared shelf over Tailscale: what you stage on one of your machines shows up on the others

## Requirements

Arch / Omarchy, no pip install:

```bash
pacman -S python-gobject gtk4 gtk4-layer-shell wl-clipboard
```

## Install

```bash
git clone -b omarchy https://github.com/viniabdalla/ShelfClip.git && cd ShelfClip
./install.sh
```

`install.sh` links `~/.local/bin/shelfclip` to the checkout, adds ShelfClip to Hyprland's autostart, binds **Ctrl+Y** to `shelfclip toggle` (replacing an older ShelfClip bind such as Super+Y), backs up any Hypr file it edits, and restarts the running instance. Run it again after every `git pull`; a second run changes nothing.

## Run

```bash
./shelfclip            # start the shelf
./shelfclip toggle     # open/close it (empty shelves auto-hide after show_time seconds)
./shelfclip paste      # stage whatever is on the clipboard
./shelfclip clear      # remove everything from the shelf
./shelfclip settings   # open the settings window
./shelfclip reload-theme
./shelfclip quit
```

`shelfclip <command>` talks to the running instance, or starts one if none is running.

### Hyprland setup by hand

`install.sh` does this for you. To do it by hand, add to `~/.config/hypr/autostart.lua` and `~/.config/hypr/bindings.lua`:

```lua
-- autostart.lua
o.launch_on_start("/path/to/Shelfclip/shelfclip")

-- bindings.lua
o.bind("CTRL + Y", "ShelfClip toggle", "/path/to/Shelfclip/shelfclip toggle")
o.bind("SUPER + SHIFT + Y", "ShelfClip paste", "/path/to/Shelfclip/shelfclip paste")  -- optional
```

Heads-up: a global `CTRL + Y` takes the key away from every app (it is "redo" in many of them). Pick a `SUPER + ...` combo if that bothers you.

## Usage

| Action | How |
|---|---|
| Stage files | Drag them onto the right screen edge (top-right, under the bar) and drop |
| Take files out | Drag a tile into any app or folder; it **moves** the file and leaves the shelf once the drop succeeds. Hold **Ctrl when you start the drag** to copy instead |
| Select | Click; Ctrl+click toggles; Shift+click selects a range; Ctrl+A selects all |
| Remove | Hover a tile and click ×, or select and press Delete; `clear` removes all |
| Paste | `shelfclip paste` anywhere, or Ctrl+V while the panel has focus (click it first) |
| Empty the shelf | Esc while the panel has focus |

Dropping a tile back onto the shelf, or on the bare desktop / the bar (which accept nothing), leaves it where it is: a tile only goes away when the drop lands on a window.

## Settings

Click ⚙ in the panel header (or run `shelfclip settings`). A small window opens in the center of the monitor; Esc or × closes it. Changes apply right away and are saved.

- **show time**: how long an empty shelf opened with Ctrl+Y stays up (1–30 s)
- **tile size**: tile edge in px (64–256)
- **share via tailscale**: mirror the shelf with your other machines (below)

## Shared shelf (Tailscale)

Turn on **share via tailscale** on each machine. From then on, every one of your machines that is online on your tailnet with sharing on holds the same shelf:

- a file staged on one shows up on the others (the file itself is copied, with a badge naming the machine it came from);
- removing a tile anywhere (×, Delete, `clear`, Esc, dragging it out) removes it everywhere;
- a machine that comes online (or turns sharing on) picks up what the others have right away. There is no history: what happened while it was off is not replayed.

ShelfClip instances talk directly over TCP port 47811 on the Tailscale address only, and accept nobody but machines of the same Tailscale user. Nothing polls in the background: peers are looked up only when something is added or removed. No Taildrop, no extra permissions. Received copies live in `$XDG_RUNTIME_DIR/shelfclip/shared/` and are deleted a minute after they leave the shelf; your original files are never touched.

## Config file

`~/.config/shelfclip/config.json`, written by the settings window; missing keys use the defaults:

```json
{
  "show_time": 5,
  "tile_size": 120,
  "share": false,
  "trigger_width": 1,
  "margin": 2,
  "drag_action": "move"
}
```

`trigger_width`, `margin` and `drag_action` are only in the file, not in the settings window. 
`trigger_width` is the invisible drag hot zone on the screen edge while the shelf is collapsed (minimum 1). `margin` is the gap to the bar and screen edge when open (matches Hyprland's `gaps_out`). `drag_action` (`"move"` or `"copy"`) is what dragging a tile out does by default; Ctrl at the start of the drag flips it.

## Notes

- Wayland can't read the mouse button globally, so instead of polling for a drag the shelf keeps a thin drop target on the screen edge. It intercepts clicks on those few pixels while collapsed (1 px by default, the last pixel column of the screen).
- The shelf opens the moment a file drag touches the edge and stays open ~1.2 s after the pointer leaves, so a quick flick is enough. Between two side-by-side monitors the edge isn't a wall, so the outer edge of the rightmost monitor is the easiest target.
- Hyprland ignores Ctrl/Shift during a drag (it doesn't implement modifier-based copy/move/link), so the choice is made when the drag starts, by what the shelf offers to the file manager.
- Wayland has no global hotkeys for clients; the keybind is a Hyprland `bind` that runs `shelfclip toggle`.
- `main.py` re-executes itself once with `LD_PRELOAD` set to gtk4-layer-shell, which is required when it is used from Python.
