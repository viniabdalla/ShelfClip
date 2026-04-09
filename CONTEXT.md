# ShelfClip — Project Context

Yoink-inspired floating file shelf for Windows. Single-file Python app (`main.py`) built with PyQt6.

## What it does

A semi-transparent, always-on-top panel that lives off-screen and slides in from the left or right edge when:
- The user drags a file near the configured edge (left mouse button held + cursor within 4px of edge), OR
- The global hotkey is pressed (default: `Ctrl+Y`)

Files dropped onto the shelf are staged there. The user can later drag them out to any target. The shelf auto-hides after 1.2s when empty.

## Current version: v1.6.0+

Features added after v1.6.0 (not yet tagged):
- Per-item overlay × button (top-right corner of each card) for individual removal
- Multi-select via Ctrl+click (toggle) and Shift+click (range)
- Multi-file drag: dragging a selected item bundles all selected files into one QDrag (count badge on cursor)
- Self-drop protection: dropping a shelf file back onto the shelf does nothing (file stays)
- "ShelfClip" label removed from shelf header

## File structure

```
YOINK WINDOWS/
├── main.py              # Entire application — all classes and logic
├── settings.json        # Runtime config: {"side": "right", "hotkey": "ctrl+y"}
├── build.bat            # Builds dist/ShelfClip.exe via PyInstaller
├── build_installer.bat  # Builds installer via Inno Setup (run AFTER build.bat)
├── installer.iss        # Inno Setup script
├── ShelfClip.bat        # Launcher shortcut
├── run_shelfclip.bat    # Dev runner
├── dist/                # PyInstaller output — ShelfClip.exe
├── installer_output/    # ShelfClip_Setup.exe
├── build/               # PyInstaller temp (delete before rebuilding on OneDrive)
└── IMAGENS/             # Design reference screenshots (not committed)
```

## Class overview

| Class | Responsibility |
|---|---|
| `ShelfWindow` | Root widget. Owns `items`, `_selected`, `_last_clicked`. Manages slide animations, cursor polling, hotkey, tray, settings, drag-drop acceptance. |
| `ShelfItem` | One card. Has `file_path`, `selected` flag, overlay × button. Handles Ctrl/Shift click via `ShelfWindow.handle_item_click()`. Builds multi-URL QDrag on mouseMoveEvent. |
| `HotkeyFilter` | Native event filter catching `WM_HOTKEY (0x0312)` at app level. |
| `SettingsDialog` | Frameless dialog for edge side + hotkey. Uses `HotkeyCapture`. |
| `HotkeyCapture` | QPushButton that grabs keyboard and records the next key combo pressed. |
| `DropHint` | Placeholder label shown when shelf is empty; highlights blue on drag-enter. |

## Key implementation details

### Hotkey registration
`RegisterHotKey(None, HOTKEY_ID, mod, vk)` — `hwnd=None` is intentional. Posts `WM_HOTKEY` to the thread message queue so `HotkeyFilter` can catch it via `installNativeEventFilter`. **Never pass `winId()`** — crashes immediately on hidden translucent windows with no Python traceback.

### Drag detection
`GetAsyncKeyState(0x01) & 0x8000` polls the left mouse button state every 80ms. The shelf slides in only when this is true AND the cursor is within 4px of the configured edge.

### Multi-select drag
`ShelfItem.mouseMoveEvent` checks if `self in shelf._selected and len(shelf._selected) > 1`. If so, all selected `file_path`s are bundled as `QUrl`s in one `QMimeData`. A count badge is painted on the drag pixmap. After a successful drop, all dragged items are removed via `shelf.remove_item()`.

### Self-drop protection
`ShelfWindow.dropEvent` filters incoming URLs. If all URLs are already tracked by existing shelf items, it calls `e.ignore()` instead of `acceptProposedAction()`. This makes `drag.exec()` return `IgnoreAction`, so `mouseMoveEvent` skips the removal step.

### Overlay × button
`ShelfItem._remove_btn` is a `QPushButton` child of the `QFrame` but NOT in the layout. Positioned via `resizeEvent` at `(self.width() - 12 - btn.width(), 3)` — top-right corner of the visual card, inset to stay within the rounded border.

### Animation
`QPropertyAnimation` on `pos`. Always created fresh per slide; `DeleteWhenStopped` prevents leaks. `_slide_out` connects `finished` to `self.hide()`.

### Auto-hide logic
`_collapse_timer` (1.2s, single-shot) fires `_slide_out`. Started on `leaveEvent` and cursor-poll when shelf is empty. Stopped immediately on `enterEvent`, drag-near-edge, or when a file is added.

## PyQt6 import locations (non-obvious)

- `QFileIconProvider` → `PyQt6.QtWidgets`
- `QAction`, `QScreen` → `PyQt6.QtGui`
- `QAbstractNativeEventFilter` → `PyQt6.QtCore`
- `event.globalPosition().toPoint()` for global mouse position (`.globalPos()` removed in PyQt6)

## Build notes

- Delete `build/` folder before rebuilding — OneDrive sync locks `build\ShelfClip\localpycs` causing `PermissionError [WinError 5]`
- `build_installer.bat` only runs Inno Setup — does NOT invoke PyInstaller. Must run `build.bat` first.
- Python: `C:\Users\vinic\AppData\Local\Programs\Python\Python311\python.exe`
- Use CMD or PowerShell for build scripts, not git bash

## Constants (top of main.py)

| Constant | Value | Purpose |
|---|---|---|
| `SHELF_WIDTH` | 135 | Fixed panel width in px |
| `ITEM_HEIGHT` | 58 | Fixed height per shelf card |
| `MAX_ITEMS` | 30 | Max staged files |
| `HOTKEY_ID` | 1 | Windows hotkey ID for RegisterHotKey |
| `TEMP_DIR` | `%TEMP%/shelfclip/` | Clipboard paste staging area |
| `SETTINGS_FILE` | `settings.json` (next to main.py) | Persisted user settings |

## Recent changes

- Added a header side-switch control for one-click switching between left and right shelf placement.
- Added `show_time` to `settings.json` so the shelf can auto-hide after N seconds when opened by the global hotkey.
- Simplified the settings UI so the show-time control is only a seconds input.

## Known unresolved issue

- The translucent outer rounded edges of the shelf still show a soft dark halo / fuzzy blend on Windows.
- Tried adding `Qt.WindowType.NoDropShadowWindowHint` to both `ShelfWindow` and `SettingsDialog`.
- Result: no visible fix. Revisit Windows composition / translucent edge rendering later instead of only tweaking stylesheet borders.
