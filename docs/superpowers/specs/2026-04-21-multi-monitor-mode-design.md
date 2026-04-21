# ShelfClip — Multi-Monitor Mode Design

**Date:** 2026-04-21
**Status:** Approved

---

## Overview

ShelfClip currently operates in **Single Monitor mode**: the shelf is anchored to a fixed edge of one specific monitor and appears only when a file is dragged near that edge. This mode is stable and must remain completely untouched.

This spec adds **Multi-Monitor mode**: the shelf follows the mouse cursor across monitors in real time (with a short debounce delay), always appearing on the monitor the user is currently working on. The two modes are additive — Single Monitor is the default, Multi-Monitor is opt-in via Settings.

---

## Settings

### New key: `monitor_mode`

Added to `settings.json` with default value `"single"`.

| Value | Behaviour |
|---|---|
| `"single"` | Current anchor behaviour — no changes |
| `"multi"` | New follow-cursor behaviour |

### Settings dialog

A new **Monitor mode** section with two radio buttons:
- `Single Monitor` — anchored to one fixed edge (current behaviour)
- `Multi-Monitor` — shelf follows cursor across screens

The existing `"side"` key (`"left"` / `"right"`) is shared between both modes and means "which edge of the screen" in both cases.

---

## Architecture

### Approach: Parallel poll branch (Option A)

The existing `_poll_cursor` method is split with a top-level `if/else` on `monitor_mode`. The single-monitor branch is wrapped verbatim — zero logical changes. The multi-monitor branch delegates to a new `_poll_cursor_multi()` method.

`_toggle_side()` gets the same `if/else` split: single-monitor repositions to the globally anchored screen (current), multi-monitor repositions to the edge of `_current_screen`.

No new classes, no subclassing, no strategy objects. Two new instance variables, one new method, two small forks in existing methods.

---

## New Instance Variables

| Variable | Type | Purpose |
|---|---|---|
| `_current_screen` | `QScreen \| None` | The screen the shelf is currently displayed on in multi-monitor mode. `None` until first drag-show. |
| `_monitor_switch_timer` | `QTimer` | One-shot 400ms debounce timer. Fires after cursor has been on a new screen for 400ms, triggering the slide transition. |

Both are initialised in `__init__` alongside existing timers.

---

## Multi-Monitor Poll Logic (`_poll_cursor_multi`)

Called every 80ms tick (same interval as current poll) when `monitor_mode == "multi"`.

```
1. If not is_dragging():
       If shelf is empty and not collapse_timer active → start 1.2s collapse timer
       Return

2. Detect which QScreen the cursor is currently on.

3. If _current_screen is None (first drag):
       Set _current_screen = cursor's screen
       Slide in on that screen's configured edge

4. If cursor's screen == _current_screen:
       Check if cursor is near_edge(side, _current_screen)
       If yes and not shown → slide in
       (collapse timer logic unchanged)
       Return

5. If cursor's screen != _current_screen:
       Restart _monitor_switch_timer (400ms debounce)
       Return

6. When _monitor_switch_timer fires (_on_monitor_switch):
       slide_out() → on completion:
           _current_screen = new screen
           reposition window to side edge of new screen
           slide_in()
```

The 400ms debounce prevents the shelf from jumping when the cursor briefly crosses a monitor boundary in transit.

---

## Switch Button in Multi-Monitor Mode

`_toggle_side()` currently:
1. Flips `side` between `"left"` / `"right"`
2. Saves settings
3. Repositions to `get_edge_screen(side)` — the globally anchored screen

In multi-monitor mode, step 3 becomes: reposition to the left or right edge of **`_current_screen`** — wherever the shelf is sitting right now.

Single-monitor path is unchanged inside an `if monitor_mode == "single":` guard.

---

## Behaviour Summary

| Scenario | Single Monitor | Multi-Monitor |
|---|---|---|
| Drag near configured edge | Shelf appears | Shelf appears on cursor's monitor |
| Drag to different monitor | Nothing | Shelf follows after 400ms |
| Hotkey toggle | Works as before | Shows on `_current_screen` if set; falls back to cursor's current screen if shelf has never been shown yet |
| Switch button | Flips edge on anchor screen | Flips edge on current monitor |
| No drag, shelf empty | Auto-hides after 1.2s | Auto-hides after 1.2s |
| Shelf has items | Never auto-hides | Never auto-hides |

---

## What Does NOT Change

- `_poll_cursor` single-monitor branch — verbatim preserved
- `_slide_in` / `_slide_out` — no changes
- `get_edge_screen()` — still used by single-monitor path
- `near_edge()` — reused by multi-monitor path
- `is_dragging()` — unchanged
- All existing settings keys — unchanged
- Glass UI, opacity, dark mode — unaffected

---

## Files Changed

| File | Change |
|---|---|
| `main.py` | Add `_current_screen`, `_monitor_switch_timer`; split `_poll_cursor`; add `_poll_cursor_multi`, `_on_monitor_switch`; split `_toggle_side`; update `load_settings` default; add radio buttons to `SettingsDialog` |
| `settings.json` | New key `monitor_mode: "single"` |
