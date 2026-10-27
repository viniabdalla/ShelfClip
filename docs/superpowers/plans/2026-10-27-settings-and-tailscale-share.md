# Settings window, Ctrl+Y installer and Tailscale-shared shelf Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gear button + centered settings window with sliders, a Tailscale-shared shelf, and an idempotent `install.sh` that binds Ctrl+Y.

**Architecture:** Everything stays in `main.py`. A pure wire-protocol layer (module functions over sockets, no GTK) is wrapped by a `Share` class that owns the listener thread and talks to `ShelfApp` only through `GLib.idle_add`. `Shelf` gains per-item metadata (id, origin) and local-change hooks so sharing never echoes remote changes.

**Tech Stack:** Python 3.14 stdlib (`socket`, `threading`, `tarfile`, `uuid`, `unittest`), GTK4 + gtk4-layer-shell, `tailscale` CLI.

**Spec:** `docs/superpowers/specs/2026-10-27-settings-and-tailscale-share-design.md`

## Global Constraints

- Single file app `main.py`; stdlib only; GTK main loop never blocks on network or `tailscale`.
- Port `47811`; listener bound to the Tailscale IPv4 only; open only while `share` is true.
- No polling/heartbeat; network only on add/remove/clear, startup, switch on, settings open.
- Accept connections only from peers with the same Tailscale `UserID` (and our own IP, for local tests).
- Sliders: `show_time` 1–30 step 1; `tile_size` 64–256 step 8. New config key `share` (default `false`).
- `trigger_width`, `drag_action`, `margin` are not shown in the settings window.
- Shared files live in `$XDG_RUNTIME_DIR/shelfclip/shared/<id>/<name>`; original files are never touched.
- Hotkey `CTRL + Y` → `shelfclip toggle`, set by `install.sh`.

## Review Focus

- Peer offline / Tailscale down: sends fail fast (1 s connect timeout) and silently; UI stays responsive. → Task 3 test `test_send_to_dead_port_returns_false`.
- Same item arriving twice (startup sync + push): ignored by id, no duplicate tile. → Task 3 test `test_add_skip_when_known`.
- Directory staged: travels as tar, unpacked safely (`filter="data"`). → Task 3 test `test_dir_roundtrip`.
- Remote remove of a received item while dragging it out: file deleted only after a delay (60 s) so a COPY drop can finish reading. → Task 4 (manual).
- Settings open on an empty shelf: shelf must not auto-collapse behind it. → Task 2 (manual).

---

### Task 1: Item metadata and config saving

**Files:** Modify `main.py` (`DEFAULTS`, `load_config`, `Shelf`).

**Interfaces:**
- Produces: `save_config(changes: dict) -> None` (merge into JSON file, mkdir parents).
- `Shelf.meta: dict[path] -> {"id": str, "origin": str|None}`.
- `Shelf.add(path, item_id=None, origin=None, remote=False) -> bool`; `Shelf.remove(paths, remote=False)`; `Shelf.clear(remote=False)`.
- `Shelf.on_local_add: list[cb(path)]`, `Shelf.on_local_remove: list[cb(ids: list[str], cleared: bool)]` — fired only when `remote` is false.
- `Shelf.path_for(item_id) -> str|None`.

- [ ] Implement; `python -c` smoke via `./shelfclip` start + `wl-copy` paste still stages files.
- [ ] Commit `feat: item ids/origin and config saving`.

### Task 2: Gear button, settings window, live apply

**Files:** Modify `main.py` (`build_css`, `ShelfWindow` header/`sync_items`, new `SettingsWindow`, `ShelfApp`).

**Interfaces:**
- Consumes: `save_config`.
- Produces: `ShelfApp.toggle_settings(win)`, `ShelfApp.settings` (window or None), `ShelfApp.set_option(key, value)` (updates `cfg`, saves debounced 300 ms, applies), `ShelfWindow.apply_tile_size()`.
- `SettingsWindow(app, monitor)`: layer-shell OVERLAY, namespace `shelfclip-settings`, no anchors (centered), keyboard EXCLUSIVE, Esc/× close; `set_peers(names: list[str]|None)` (None → "checking…").

- [ ] Header always visible; `clear` hidden when empty; `⚙` button (class `gear`, accent on hover) after `clear`.
- [ ] `_collapse` does nothing while settings is open; closing settings calls `maybe_collapse_soon()`.
- [ ] Tile size applies debounced 150 ms: clear `_thumbs`, rebuild tiles, hint + strip sizes, `_fit()`.
- [ ] Verify: `hyprctl layers -j` shows `shelfclip-settings` centered; sliders change `config.json`; tiles resize live.
- [ ] Commit `feat: settings window with sliders and share switch`.

### Task 3: Wire protocol (pure, tested)

**Files:** Modify `main.py` (new section `# ── Sharing ──`); Create `tests/test_share.py`.

**Interfaces (module functions):**
- `PORT = 47811`, `PROTO = 1`.
- `send_add(ip, port, item: dict, path: str) -> bool` — item has `id, origin, name, dir`; header line, wait `go`/`skip`, stream file bytes (or tar `w|` for dirs), shut down write.
- `send_remove(ip, port, ids, cleared) -> bool`, `ask_hello(ip, port) -> str|None` (peer hostname), `ask_state(ip, port) -> list[dict]|None`, `fetch(ip, port, item_id, dest_dir) -> str|None` (returns local path).
- `serve_conn(conn, handler)` — reads one header, dispatches to `handler.on_add(item, conn_file, dest_dir) / on_remove / on_hello / on_state / on_get`; `receive_body(fileobj, dest_dir, name, is_dir) -> str`.
- Tests use a stub handler on `127.0.0.1` with a thread-run listener.

- [ ] Write tests: `test_file_roundtrip`, `test_dir_roundtrip`, `test_add_skip_when_known`, `test_remove`, `test_state_and_fetch`, `test_send_to_dead_port_returns_false`.
- [ ] Run `python3 -m unittest tests/test_share.py -v` → fail, implement, pass.
- [ ] Commit `feat: shelf sharing wire protocol`.

### Task 4: Share class wired into the app

**Files:** Modify `main.py` (`Share`, `ShelfApp`, `Tile`, `build_css`).

**Interfaces:**
- `tailscale_status() -> dict|None`; `same_user_peers(status) -> list[tuple[host, ip]]`.
- `Share(app)`: `enable()`, `disable()`, `ensure_listener() -> bool`, `push_add(path)`, `push_remove(ids, cleared)`, `sync()` (state pull + push own), `probe(callback)` (hello to peers → names).
- Received items: `shelf.add(path, id, origin, remote=True)` via `GLib.idle_add`; removed shared files deleted 60 s later.
- `Tile` shows origin badge (class `origin`) when `meta.origin` is set.

- [ ] Hook `on_local_add/on_local_remove` → push; startup with `share` → `enable()` + `sync()`; switch → enable/sync or disable; `toggle` and settings open → `ensure_listener()`.
- [ ] Verify locally with a peer script hitting our own Tailscale IP: add → tile with badge appears; remove → tile gone; `state` lists local items.
- [ ] Commit `feat: share the shelf over Tailscale`.

### Task 5: Installer and docs

**Files:** Create `install.sh`; Modify `README.md`, `CLAUDE.md`.

- [ ] `install.sh`: deps check (`pacman -Q`), symlink `~/.local/bin/shelfclip`, autostart line, replace/insert `o.bind("CTRL + Y", "ShelfClip toggle", "shelfclip toggle")`, timestamped backups, restart instance. Idempotent (second run changes nothing).
- [ ] Run it here twice; `grep` shows one bind with `CTRL + Y`, one autostart line; `readlink ~/.local/bin/shelfclip` → repo.
- [ ] README (install, settings, sharing) and CLAUDE.md (architecture rows, sharing gotchas) updated.
- [ ] Commit `feat: install.sh with Ctrl+Y` and push.
