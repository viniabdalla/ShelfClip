# ShelfClip

ShelfClip is a Yoink-inspired floating file shelf for Windows, built as a single-file PyQt6 app.

It stays off-screen until you need it, then slides in from the left or right edge when:
- you drag a file near the configured screen edge
- you press the global shortcut

Dropped files stay staged on the shelf so you can drag them out later into another app or folder.

## Features

- Floating always-on-top shelf
- Left or right edge placement
- One-click header side switcher
- Global hotkey toggle
- Configurable `show_time` for hotkey-triggered visibility
- Multi-select with `Ctrl+click` and `Shift+click`
- Multi-file drag-out from current selection
- Per-item remove button
- Clipboard paste support for images, files, and text via `Ctrl+V`
- Self-drop protection to avoid removing items when dropped back on the shelf

## Project files

- `main.py`: app logic and UI
- `settings.json`: runtime settings
- `build.bat`: builds `dist/ShelfClip.exe`
- `build_installer.bat`: builds installer with Inno Setup
- `installer.iss`: installer script
- `CONTEXT.md`: implementation notes and project context

## Requirements

- Windows
- Python 3.11+ or 3.12
- PyQt6
- Inno Setup 6 if you want to build the installer

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run in development

Use:

```powershell
run_shelfclip.bat
```

Or:

```powershell
python main.py
```

## Build the EXE

Run:

```powershell
build.bat
```

Output:
- `dist/ShelfClip.exe`

## Build the installer

First build the EXE, then run:

```powershell
build_installer.bat
```

Output:
- `installer_output/ShelfClip_Setup.exe`

## Current settings

`settings.json` supports:

```json
{
  "side": "left",
  "hotkey": "ctrl+y",
  "show_time": 4
}
```

## Known issue

The translucent outer rounded edge of the shelf still shows a faint halo / fuzzy blend on Windows. A test using `Qt.WindowType.NoDropShadowWindowHint` did not resolve it, so that issue remains open for future investigation.
