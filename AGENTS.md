# Repository Guidelines

## Project Structure & Module Organization

ShelfClip is a small Windows desktop app built mostly in a single file: `main.py`. That file contains the UI, drag-and-drop behavior, hotkey handling, settings dialog, tray integration, and animation logic. Runtime settings live in `settings.json`. Build and packaging files are at the repo root: `build.bat`, `build_installer.bat`, `ShelfClip.spec`, and `installer.iss`.

Generated output should not be edited directly: `dist/`, `build/`, `installer_output/`, and `__pycache__/` are build/runtime artifacts. `IMAGENS/` contains local design references and is ignored by Git. Use `CONTEXT.md` for implementation notes and known issues.

## Build, Test, and Development Commands

- `pip install -r requirements.txt`: install Python dependencies.
- `run_shelfclip.bat`: run the app in development mode.
- `python main.py`: direct dev launch without the batch wrapper.
- `build.bat`: generate `dist/ShelfClip.exe` with PyInstaller.
- `build_installer.bat`: build `installer_output/ShelfClip_Setup.exe` with Inno Setup. Run `build.bat` first.

There is no formal automated test suite yet. At minimum, validate syntax before shipping:

- `python -c "import ast, pathlib; ast.parse(pathlib.Path('main.py').read_text(encoding='utf-8'))"`

## Coding Style & Naming Conventions

Use 4-space indentation and keep changes consistent with the existing PyQt6 style. Prefer descriptive snake_case for functions, variables, and settings keys like `show_time`. Use PascalCase for Qt widget classes such as `ShelfWindow` and `SettingsDialog`.

Keep UI constants near the top of `main.py`. Prefer small, focused helper methods instead of spreading logic inline through event handlers.

## Testing Guidelines

Since testing is manual today, verify the full user flow after behavior changes:
- hotkey open/close
- drag-near-edge reveal
- side switching
- settings persistence in `settings.json`
- EXE build and installer build when packaging changes are touched

## Commit & Pull Request Guidelines

Current history uses short imperative commit messages, for example:
- `Initial ShelfClip app import`
- `Add README and update installer version`

Follow that style: concise, action-first, and specific. For pull requests, include a short summary, list of user-visible changes, and screenshots or screen recordings for UI adjustments. Mention packaging changes when `build.bat`, `installer.iss`, or version numbers are modified.
