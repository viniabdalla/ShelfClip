# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository

ShelfClip — a Yoink-inspired floating file shelf for Windows. Frosted-glass, always-on-top panel that auto-hides off-screen and appears only when dragging a file near the configured edge, or via a global hotkey.

**Stack:** Python 3.11 + PyQt6

## Running & Building

```bash
# Run (development) — use CMD or PowerShell, not git bash
python main.py

# Build .exe — run from CMD or double-click
build.bat
# Output: dist/ShelfClip.exe

# Build installer (requires Inno Setup 6) — run after build.bat
build_installer.bat
# Output: installer_output/ShelfClip_Setup.exe
```

**OneDrive build issue:** If `build.bat` throws a `PermissionError` on `build\ShelfClip\localpycs`, manually delete the `build/` folder in Explorer before retrying. OneDrive locks it between builds.

**`installer.iss` paths:** `SourceDir` and `OutputDir` are hardcoded absolute paths. If the OneDrive drive letter changes, update both lines in `installer.iss`.

Python is at `C:\Users\vinic\AppData\Local\Programs\Python\Python311\python.exe` — `python` may not resolve in git bash; use CMD or PowerShell.

There are no automated tests. Verification is always manual by running the app.

## Architecture (`main.py`)

Single-file app. Key classes:

| Symbol | Role |
|---|---|
| `ShelfWindow` | Main window — frameless, always-on-top, translucent. Owns item list, handles drop/paste/keyboard. Polls cursor every 80ms via `_poll_cursor()`. |
| `GlassCard` | Custom `QWidget` subclass used as the shelf panel and settings dialog panel. All background painting is done in `paintEvent` (no CSS background). Draws frosted-glass look: base fill + gradient highlight + border. |
| `ShelfItem` | One card per staged file — icon/thumbnail, filename, overlay × button. Supports Ctrl/Shift multi-select. Initiates `QDrag`; drags all selected items if self is selected. Auto-removes after successful external drop. |
| `HotkeyFilter` | `QAbstractNativeEventFilter` catching `WM_HOTKEY` (0x0312) from the thread queue, calls `ShelfWindow._toggle_shelf()`. |
| `SettingsDialog` | Frameless `QDialog` built on `GlassCard`. Edge, hotkey, show-time, dark mode, opacity, and monitor mode settings. |
| `HotkeyCapture` | `QPushButton` subclass that grabs the keyboard and records the next key combo pressed. |
| `DropHint` | Placeholder label shown when shelf is empty; highlights on drag-enter. |

**Key helpers:**
- `get_edge_screen(side)` — returns the `QScreen` at the far left/right of all monitors (used by Single Monitor mode only).
- `shelf_x / offscreen_x / near_edge / is_dragging` — position math and input state.
- `set_theme(dark, opacity)` — updates globals `THEME` (dict) and `OPACITY` (float). Called on startup and after settings save.

## Settings (`settings.json`)

```json
{
  "side": "right",
  "hotkey": "ctrl+y",
  "show_time": 4,
  "dark_mode": true,
  "opacity": 90,
  "monitor_mode": "single"
}
```

`opacity` is stored as an integer 20–100; `set_theme()` receives it divided by 100.

## Theme System

Two theme dicts `_DARK` / `_LIGHT` at the top of `main.py`. The global `THEME` dict and `OPACITY` float are updated by `set_theme(dark, opacity)`. All widgets read from `THEME` at style-set time. `ShelfWindow._apply_theme()` propagates a theme change to all live widgets without losing shelf contents.

`GlassCard.paintEvent` uses `THEME["bg"]` RGB + `OPACITY` for the alpha — at `OPACITY=1.0` the card is fully solid (alpha=255). The dimmed state (shelf hidden/idle) multiplies by 0.7.

## Monitor Modes

Two modes controlled by `settings["monitor_mode"]`:

- **`"single"`** (default) — shelf is anchored to one fixed screen edge. `_poll_cursor()` uses `get_edge_screen(side)`.
- **`"multi"`** — shelf tracks the cursor's current screen. `_poll_cursor()` delegates to `_poll_cursor_multi()`, which silently updates `_current_screen: QScreen | None` as the cursor moves between monitors. The shelf only appears when dragging near the configured edge of the current screen (same trigger as single mode). When the cursor moves to a new monitor, `_monitor_switch_timer` (400ms debounce) fires `_on_monitor_switch()`, which slides the shelf to the new screen only if it is currently visible.

The two code paths are split by a top-level `if/else` in `_poll_cursor` and `_toggle_side` — the single-monitor branch is preserved verbatim.

## Key Behaviors

- Shelf appears when `is_dragging()` (left mouse button held via `GetAsyncKeyState(0x01)`) AND cursor within 4px of the configured edge — or via hotkey.
- `RegisterHotKey` uses `hwnd=None` so `WM_HOTKEY` posts to the thread queue. **Do not use `winId()` for hotkey registration** — hard crash on hidden translucent windows.
- `_slide_in(screen=None)` and `_slide_out(screen=None, on_complete=None)` accept an optional target screen; defaults to `get_edge_screen(side)` when omitted.
- When shelf has items it never auto-hides. Auto-hide (1.2s timer) only fires when empty.
- Dropping back onto the shelf is a cancelled drag — `dropEvent` calls `e.ignore()` when all dropped URLs are already on shelf.
- Multi-select: `_selected` list + `_last_clicked` for Shift range-select; all selected URLs bundled into one `QDrag` with a count badge.
- Clipboard images saved as PNGs to `%TEMP%/shelfclip/`.

## PyQt6 Gotchas

- `QFileIconProvider` → `PyQt6.QtWidgets` (not `QtGui`)
- `QAction`, `QScreen` → `PyQt6.QtGui`
- `QAbstractNativeEventFilter` → `PyQt6.QtCore`
- `event.globalPosition().toPoint()` for mouse global pos (not `globalPos()`)
- `app.setQuitOnLastWindowClosed(False)` keeps app alive when window hides
- `QPropertyAnimation.DeletionPolicy.DeleteWhenStopped` prevents dangling animation objects — but the Python wrapper (`self._anim`) remains non-None after the C++ object is deleted. Always wrap `.state()` or any method call on `self._anim` in `try/except RuntimeError`.
- **Never call `winId()` on a hidden window with `WA_TranslucentBackground`** — immediate hard crash with no Python traceback
- `WA_TranslucentBackground` must NOT be set on child widgets — only on top-level windows. Setting it on a child causes a ghost outer border.
- Windows 11 DWM applies rounded corners to every window automatically. Disable with `DwmSetWindowAttribute(hwnd, 33, DWMWCP_DONOTROUND=1, 4)` in `showEvent` (window must be visible). Both `ShelfWindow` and `SettingsDialog` do this.

## Planning Docs

Design specs and implementation plans live in `docs/superpowers/`:
- `specs/` — feature design documents
- `plans/` — step-by-step implementation plans (checkbox format, used with subagent-driven development)
