# ShelfClip: Productivity Drag-and-Drop Utility

## Overview
ShelfClip is a Windows-based productivity utility inspired by macOS "shelf" apps. It acts as a temporary holding area for files, folders, and clipboard content, allowing users to move items between different applications without needing to hold down the mouse button or manage multiple windows simultaneously.

## Core Features
1. **The Floating Shelf**: A small, semi-transparent window that appears at the edge of the screen when a user starts dragging a file or when the clipboard contains data.
2. **Multi-Item Support**: Users can stack multiple different items (files, images, text snippets) on the shelf.
3. **Always-on-Top**: The shelf stays above all other windows during a drag operation.
4. **Drag-Out Functionality**: Once the user navigates to the destination folder or app, they can drag items from the shelf and drop them into the target.

## Input Methods
- **File Drag & Drop**: Dragging files from File Explorer onto the shelf.
- **Clipboard Integration (Ctrl + V)**: When the shelf window is active/focused, pressing `Ctrl + V` will grab whatever image or file is currently in the Windows Clipboard and add it to the shelf as a new item.
- **Web Content**: Support for dragging images or highlighted text from web browsers.

## User Interface (UI)
- **Minimalist Design**: A vertical or horizontal drawer-style interface.
- **Thumbnails**: Visual previews for images and icons for specific file types (PDF, Docx, etc.).
- **Clear All**: A small 'X' button to clear the shelf.

## Behavior
- The shelf should automatically hide when empty.
- It should support "Global Hotkeys" to show/hide the window manually.

## Current implementation notes
- The shelf now has a header side-switch button for fast left/right switching.
- The settings dialog now includes a `show_time` value in seconds for how long the shelf stays visible when opened by the hotkey.

## Visual issue to revisit
- The shelf window still shows a faint dark halo / fuzzy outer edge around the rounded translucent frame on Windows.
- A test using `Qt.WindowType.NoDropShadowWindowHint` did not solve it.
- Future investigation should focus on translucent window composition and edge rendering.
