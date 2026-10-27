# ShelfClip: settings window, Ctrl+Y installer, Tailscale-shared shelf

Date: 2026-10-27. Branch: `omarchy`. Target: `main.py` (single file) + a new `install.sh`.

## Intent

Vini runs ShelfClip on several Omarchy machines on his Tailscale tailnet (today: `omarchy`,
`omarchy2`, `tropico-1`). He wants:

1. To change the few settings that matter without editing JSON: a gear button in the shelf.
2. One command to install/update ShelfClip on a machine, with Ctrl+Y as the default toggle.
3. A shared shelf: with the option on, whatever he puts in the shelf on one machine shows up on
   every other machine of his that has the option on, and removing it anywhere removes it
   everywhere. He moves files between his computers by dropping them on the edge.

Everything else about ShelfClip stays as it is (see `CLAUDE.md`).

## Goals

### 1. Gear button + settings window

- A gear button (`⚙`) in the panel header, right of `clear`, always visible (also on an empty
  shelf). Same flat style as `clear` (muted, accent on hover).
- Clicking it opens a small settings window **floating in the center of the monitor** the shelf
  is on. The shelf panel stays open behind it.
- Contents:
  - **show time**: slider, seconds (`show_time`), 1–30 s, step 1, value shown next to it.
  - **tile size**: slider, px (`tile_size`), 64–256, step 8, value shown next to it.
  - **share via Tailscale**: on/off switch (`share`, new key, default `false`).
  - Under the switch, when on: the machines currently online with sharing on
    (e.g. `online: omarchy2, tropico-1`), or `no other machine online`. Refreshed when the
    window opens and when a peer contacts us.
- **Not** exposed: `trigger_width`, `drag_action`, `margin`. They stay config-file/code defaults.
- Changes apply live and are saved immediately to `~/.config/shelfclip/config.json` (merge into
  the existing JSON, keep unknown keys). No save button, no restart.
- Closes with Esc, a `×` in its header, or clicking the gear again.
- Styled from the Omarchy palette like the shelf (square corners, 1px `line` border, monospace).

### 2. Installer + Ctrl+Y

New `install.sh` at the repo root, idempotent, run from a checkout (`./install.sh`):

- Check deps with `pacman -Q python-gobject gtk4 gtk4-layer-shell wl-clipboard` (and
  `tailscale`, only warn if missing). Print the `pacman -S` line for missing ones; don't sudo.
- Symlink `~/.local/bin/shelfclip` → `<checkout>/shelfclip`.
- `~/.config/hypr/autostart.lua`: ensure one `o.launch_on_start("~/.local/bin/shelfclip")` line
  (absolute path), add if missing.
- `~/.config/hypr/bindings.lua`: ensure the toggle bind is
  `o.bind("CTRL + Y", "ShelfClip toggle", "shelfclip toggle")` under a `-- ShelfClip file shelf.`
  comment. If an existing `"ShelfClip toggle"` bind uses another key (this machine has
  `SUPER + Y`), replace that line rather than adding a second one.
- Back up each Hypr file it changes (`<file>.bak.shelfclip-<timestamp>`) before editing.
- Restart the running instance (`shelfclip quit`, then start it detached) so the new code runs.
  Hyprland reloads the Lua config on save by itself; run `hyprctl reload` only if needed.
- README "Hyprland setup" section points to `./install.sh` and shows `CTRL + Y`.

### 3. Shared shelf over Tailscale

Behavior:

- Only machines with `share` on take part. Turning it off on a machine makes it leave: it stops
  listening and stops sending. Its own tiles stay local.
- Membership is automatic: every online machine of the **same Tailscale user** with sharing on.
  No pairing, no picking machines, works for any number of machines.
- **Add** on any machine (drop, paste, clipboard) → the file itself (not just the name) is sent to
  every sharing peer; it appears there as a normal tile that can be dragged out.
- **Remove** on any machine (× button, Delete key, `clear`, Esc, drag-out that unstages) → removed
  on every sharing peer.
- **No memory / no queue.** A machine that is off when something is added or removed doesn't get
  it later. But when a machine starts with `share` on, or `share` is switched on, it asks the
  online peers for their current shelf right away and shows it instantly; it also offers its
  own current items to them (union).
- **Nothing runs in the background except a listening socket.** No polling, no periodic
  heartbeat, no daemon. Peers are looked up (`tailscale status --json`) only at the moment
  something needs to be sent (add/remove/clear, startup, switch on, settings window opening).
  The listener is idle until a peer connects.
- No permissions beyond the switch: plain TCP between ShelfClip instances over the tailnet. No
  Taildrop (it needs operator rights and drops files in a download folder).

Mechanics (decided):

- Listener: TCP on the machine's Tailscale IPv4 only (from `tailscale ip -4`), fixed port
  `47811` (constant in `main.py`). Opened when `share` is on, closed when off. If Tailscale isn't
  up yet (e.g. at login), don't poll: try to open it again at the next event that needs the
  network (add/remove, `toggle`, settings window opening, switch flipped).
- Peer discovery: `tailscale status --json` → `Peer` entries with `Online: true` and the same
  `UserID` as `Self`. Try each on port 47811 with a short connect timeout (~1 s); a refused or
  timed-out connection just means "not sharing". Run in a worker thread; never block GTK.
- Incoming connections: accept only if the source IP is one of those same-user peers (re-check
  with `tailscale status --json` per connection). Otherwise close.
- Item identity: each staged item gets an id (uuid4) and an origin hostname when it is added.
  Messages refer to items by id. Paths are never shared; each machine has its own copy.
- Received files are written under `$XDG_RUNTIME_DIR/shelfclip/shared/<id>/<original name>`
  (keeps the original file name for drag-out). Deleted from disk when the item is removed.
  Staged local files are never deleted or moved by sharing.
- Loop prevention: an item received from a peer is not re-broadcast; a remove received from a
  peer is applied locally and not re-broadcast. Duplicate ids are ignored.
- Wire format: one request per connection, a JSON header line followed by raw bytes when the
  message carries a file. Messages: `add` (id, origin, name, is_dir, size + bytes), `remove`
  (ids), `clear`, `state` (request: reply with the list of current items, then the peer pulls
  each with `get` id → bytes). Version field in the header; ignore unknown versions.
- Directories are sent as a tar stream and unpacked on the receiver.
- The tile of an item that came from another machine shows a small badge with the origin
  hostname (top-left, accent background, tiny text).
- An incoming item opens the shelf on the focused monitor like any other added item.
- Transfers run in worker threads; the tile appears on the receiver when the file is complete.
  A failed send to one peer is logged and skipped, no retry.

## Non-goals

- No sync of settings between machines, only shelf items.
- No history, no offline queue, no persistence across restarts.
- No Windows/macOS support (the `windows-pyqt6` branch is unrelated).
- No encryption/auth layer of our own: the tailnet already authenticates and encrypts.
- No progress UI for big transfers in this iteration.

## Anti-goals

- Any always-on network activity (polling, heartbeats, keep-alive connections).
- Requiring `sudo`, `tailscale set --operator`, Taildrop, or any system service.
- Accepting files from a tailnet node that isn't one of Vini's (different Tailscale user).
- A shared shelf that deletes or moves the user's original files.
- The GTK main loop blocking on the network or on `tailscale` subprocess calls.

## Constraints

- Single-file app (`main.py`), GTK4 + gtk4-layer-shell, Python stdlib only (no pip deps).
- All existing gotchas in `CLAUDE.md` still apply (layer-shell preload, `_fit()` sizing, never
  fully transparent surfaces, tile width independent of content).
- `MAX_ITEMS` (30) applies to the shared shelf too; extra incoming items are ignored.
- All machines run this same code from this repo (`omarchy` branch). Deployment: push to
  GitHub; on each machine pull and run `./install.sh`.

## Left to the builder

- Exact slider widgets/CSS, label wording (English, lowercase like `clear` / `drop files`).
- How to live-apply `tile_size` (rebuild CSS, tile pixel sizes, thumbnails, collapsed strip
  height) without restarting.
- Thread/GLib plumbing (`GLib.idle_add` back to the main loop), socket code structure.
- Logging format.

## Calls made by Claude (check these)

- Settings window is a centered **layer-shell overlay**, not a regular Hyprland window: it lands
  in the center without adding a window rule to the Hypr config, but it can't be moved.
- Slider ranges: show time 1–30 s, tile size 64–256 px step 8.
- Port 47811; listener bound only to the Tailscale IP.
- Origin badge on tiles from other machines; peers list in the settings window.
- Turning `share` on merges both ways (your current tiles go to the peers too).
- Installer links `~/.local/bin/shelfclip` to the checkout it's run from. On this machine that
  moves the install from the clone in `~/.local/share/shelfclip` to the repo in `~/Projects`.
