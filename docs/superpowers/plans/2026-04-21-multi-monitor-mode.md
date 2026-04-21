# Multi-Monitor Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in Multi-Monitor mode where the shelf follows the mouse cursor across monitors while dragging, while leaving Single Monitor mode completely untouched.

**Architecture:** A top-level `if/else` on `monitor_mode` in `_poll_cursor` separates the two paths. The single-monitor branch is wrapped verbatim. Multi-monitor logic lives in a new `_poll_cursor_multi()` method. `_slide_in` and `_slide_out` gain an optional `screen` parameter so multi-monitor can target any screen.

**Tech Stack:** Python 3.11, PyQt6 — `QGuiApplication.screenAt()`, `QTimer`, `QPropertyAnimation`

---

## File Map

| File | What changes |
|---|---|
| `main.py` | All code changes — 6 targeted edits |
| `settings.json` | Gets `monitor_mode: "single"` on next save |

---

### Task 1: Add `monitor_mode` default to `load_settings`

**Files:**
- Modify: `main.py` — `load_settings()` function

- [ ] **Step 1: Edit `load_settings`**

Find this line in `load_settings`:
```python
    defaults = {"side": "right", "hotkey": "ctrl+y", "show_time": 4, "dark_mode": True, "opacity": 90}
```
Replace with:
```python
    defaults = {"side": "right", "hotkey": "ctrl+y", "show_time": 4, "dark_mode": True, "opacity": 90, "monitor_mode": "single"}
```

- [ ] **Step 2: Verify by running the app and opening Settings**

```
python "YOINK WINDOWS/main.py"
```
Open Settings (⚙ button). App should launch without errors. Close it.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add monitor_mode setting (default single)"
```

---

### Task 2: Add optional `screen` parameter to `_slide_in` and `_slide_out`

**Files:**
- Modify: `main.py` — `_slide_in()` and `_slide_out()` methods in `ShelfWindow`

This is required so `_poll_cursor_multi` can target any screen, not just the globally-anchored one. Both methods default to their existing behaviour when `screen=None`.

- [ ] **Step 1: Update `_slide_in`**

Find:
```python
    def _slide_in(self):
        self._is_shown = True
        side = self._settings["side"]
        screen = get_edge_screen(side)
        y = screen.availableGeometry().center().y() - self.height() // 2
        start = QPoint(offscreen_x(side, screen), y)
        end   = QPoint(shelf_x(side, screen), y)
        self.move(start)
        self.show()
        self._card.set_dimmed(False)
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(180)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim
```

Replace with:
```python
    def _slide_in(self, screen: QScreen | None = None):
        self._is_shown = True
        side = self._settings["side"]
        if screen is None:
            screen = get_edge_screen(side)
        y = screen.availableGeometry().center().y() - self.height() // 2
        start = QPoint(offscreen_x(side, screen), y)
        end   = QPoint(shelf_x(side, screen), y)
        self.move(start)
        self.show()
        self._card.set_dimmed(False)
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(180)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim
```

- [ ] **Step 2: Update `_slide_out`**

Find:
```python
    def _slide_out(self):
        self._is_shown = False
        side = self._settings["side"]
        screen = get_edge_screen(side)
        y = self.pos().y()
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(180)
        anim.setStartValue(self.pos())
        anim.setEndValue(QPoint(offscreen_x(side, screen), y))
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim
```

Replace with:
```python
    def _slide_out(self, screen: QScreen | None = None, on_complete=None):
        self._is_shown = False
        side = self._settings["side"]
        if screen is None:
            screen = get_edge_screen(side)
        y = self.pos().y()
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(180)
        anim.setStartValue(self.pos())
        anim.setEndValue(QPoint(offscreen_x(side, screen), y))
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        if on_complete:
            anim.finished.connect(on_complete)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim
```

- [ ] **Step 3: Verify single-monitor mode still works**

```
python "YOINK WINDOWS/main.py"
```
Drag a file near the screen edge — shelf should appear and dismiss as before. No behaviour change expected.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: add optional screen param to _slide_in/_slide_out"
```

---

### Task 3: Add `_current_screen` and `_monitor_switch_timer` to `ShelfWindow.__init__`

**Files:**
- Modify: `main.py` — `ShelfWindow.__init__`

- [ ] **Step 1: Add the two new instance variables**

Find this block in `ShelfWindow.__init__`:
```python
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._slide_out)
```

Replace with:
```python
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._slide_out)

        self._current_screen: QScreen | None = None
        self._monitor_switch_timer = QTimer(self)
        self._monitor_switch_timer.setSingleShot(True)
        self._monitor_switch_timer.setInterval(400)
        self._monitor_switch_timer.timeout.connect(self._on_monitor_switch)
```

- [ ] **Step 2: Verify the app starts without errors**

```
python "YOINK WINDOWS/main.py"
```
Expected: app launches normally, tray icon appears.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add _current_screen and _monitor_switch_timer to ShelfWindow"
```

---

### Task 4: Split `_poll_cursor` and add `_poll_cursor_multi` + `_on_monitor_switch`

**Files:**
- Modify: `main.py` — `_poll_cursor()` method in `ShelfWindow`
- Add: `_poll_cursor_multi()` and `_on_monitor_switch()` methods

- [ ] **Step 1: Wrap the existing `_poll_cursor` body in a `single` guard**

Find:
```python
    def _poll_cursor(self):
        side = self._settings["side"]
        screen = get_edge_screen(side)
        cursor = QCursor.pos()
        dragging_near_edge = near_edge(side, screen, cursor) and is_dragging()
        over_win = self._is_shown and self.geometry().contains(cursor)

        if dragging_near_edge or over_win:
            self._collapse_timer.stop()
            if not self._is_shown:
                self._slide_in()
        else:
            if self._is_shown and not self.items and not self._collapse_timer.isActive():
                self._collapse_timer.start(1200)
```

Replace with:
```python
    def _poll_cursor(self):
        if self._settings.get("monitor_mode", "single") == "single":
            side = self._settings["side"]
            screen = get_edge_screen(side)
            cursor = QCursor.pos()
            dragging_near_edge = near_edge(side, screen, cursor) and is_dragging()
            over_win = self._is_shown and self.geometry().contains(cursor)

            if dragging_near_edge or over_win:
                self._collapse_timer.stop()
                if not self._is_shown:
                    self._slide_in()
            else:
                if self._is_shown and not self.items and not self._collapse_timer.isActive():
                    self._collapse_timer.start(1200)
        else:
            self._poll_cursor_multi()
```

- [ ] **Step 2: Add `_poll_cursor_multi` and `_on_monitor_switch` after `_poll_cursor`**

Insert the following two methods immediately after the `_poll_cursor` method:

```python
    def _poll_cursor_multi(self):
        """Multi-monitor poll: shelf follows cursor across screens while dragging."""
        side = self._settings["side"]
        cursor = QCursor.pos()
        over_win = self._is_shown and self.geometry().contains(cursor)
        dragging = is_dragging()

        if not dragging and not over_win:
            if self._is_shown and not self.items and not self._collapse_timer.isActive():
                self._collapse_timer.start(1200)
            return

        cursor_screen = QGuiApplication.screenAt(cursor)
        if cursor_screen is None:
            return

        # First drag ever — initialise and show
        if self._current_screen is None:
            self._current_screen = cursor_screen
            self._collapse_timer.stop()
            if not self._is_shown:
                self._slide_in(screen=self._current_screen)
            return

        # Same screen — standard near-edge / over-window logic
        if cursor_screen == self._current_screen:
            self._monitor_switch_timer.stop()
            near = near_edge(side, self._current_screen, cursor)
            if (dragging and near) or over_win:
                self._collapse_timer.stop()
                if not self._is_shown:
                    self._slide_in(screen=self._current_screen)
            else:
                if self._is_shown and not self.items and not self._collapse_timer.isActive():
                    self._collapse_timer.start(1200)
            return

        # Cursor on a different screen — start/restart the 400ms debounce
        if not self._monitor_switch_timer.isActive():
            self._monitor_switch_timer.start()

    def _on_monitor_switch(self):
        """Called 400ms after the cursor has been on a new screen — slide the shelf over."""
        new_screen = QGuiApplication.screenAt(QCursor.pos())
        if new_screen is None or new_screen == self._current_screen:
            return

        old_screen = self._current_screen
        self._current_screen = new_screen

        def after_out():
            self._slide_in(screen=new_screen)

        if self._is_shown:
            self._slide_out(screen=old_screen, on_complete=after_out)
        else:
            self._slide_in(screen=new_screen)
```

- [ ] **Step 3: Update `_toggle_shelf` so the hotkey works correctly in multi-monitor mode**

Find:
```python
    def _toggle_shelf(self):
        if self._is_shown:
            self._collapse_timer.stop()
            self._slide_out()
        else:
            self._slide_in()
            self._collapse_timer.start(int(self._settings.get("show_time", 4)) * 1000)
```

Replace with:
```python
    def _toggle_shelf(self):
        if self._is_shown:
            self._collapse_timer.stop()
            self._slide_out()
        else:
            if self._settings.get("monitor_mode", "single") == "multi":
                screen = (self._current_screen
                          or QGuiApplication.screenAt(QCursor.pos())
                          or get_edge_screen(self._settings["side"]))
                self._slide_in(screen=screen)
            else:
                self._slide_in()
            self._collapse_timer.start(int(self._settings.get("show_time", 4)) * 1000)
```

- [ ] **Step 4: Verify single-monitor mode is unaffected**

```
python "YOINK WINDOWS/main.py"
```
Settings → confirm `monitor_mode` is still `"single"`. Drag near edge — shelf appears. No change expected.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: add _poll_cursor_multi and _on_monitor_switch for multi-monitor mode"
```

---

### Task 5: Update `_toggle_side` for multi-monitor mode

**Files:**
- Modify: `main.py` — `_toggle_side()` method in `ShelfWindow`

In multi-monitor mode, the switch button should flip left/right on `_current_screen`, not jump to the globally anchored screen.

- [ ] **Step 1: Split `_toggle_side`**

Find:
```python
    def _toggle_side(self):
        self._settings["side"] = "left" if self._settings["side"] == "right" else "right"
        save_settings(self._settings)
        self._collapse_timer.stop()
        self._is_shown = False
        self.hide()
        self._position_on_screen()
        self._refresh_side_switch()
        self._slide_in()
```

Replace with:
```python
    def _toggle_side(self):
        self._settings["side"] = "left" if self._settings["side"] == "right" else "right"
        save_settings(self._settings)
        self._collapse_timer.stop()
        self._is_shown = False
        self.hide()

        if self._settings.get("monitor_mode", "single") == "single":
            self._position_on_screen()
            self._refresh_side_switch()
            self._slide_in()
        else:
            side = self._settings["side"]
            screen = (self._current_screen
                      or QGuiApplication.screenAt(QCursor.pos())
                      or get_edge_screen(side))
            y = screen.availableGeometry().center().y() - self.height() // 2
            self.move(offscreen_x(side, screen), y)
            self._refresh_side_switch()
            self._slide_in(screen=screen)
```

- [ ] **Step 2: Verify single-monitor switch button still works**

```
python "YOINK WINDOWS/main.py"
```
Click the switch toggle — shelf should flip to the other edge of the anchored monitor, exactly as before.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: update _toggle_side to respect monitor_mode"
```

---

### Task 6: Add Monitor mode selector to `SettingsDialog`

**Files:**
- Modify: `main.py` — `SettingsDialog._build_ui()` and `SettingsDialog._save()`

Add a **Monitor mode** section with two radio buttons, placed after the dark mode row and before the opacity slider.

- [ ] **Step 1: Add the Monitor mode section in `_build_ui`**

Find this block (the separator before the dark mode row):
```python
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setFixedHeight(1)
        sep3.setStyleSheet(f"background: {T['border']};")
        layout.addWidget(sep3)

        # ── Dark mode ─────────────────────────────────────────────────────
```

Replace with:
```python
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setFixedHeight(1)
        sep3.setStyleSheet(f"background: {T['border']};")
        layout.addWidget(sep3)

        # ── Monitor mode ──────────────────────────────────────────────────
        mon_lbl = QLabel("Monitor mode")
        mon_lbl.setStyleSheet(
            f"color: {T['text_secondary']}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(mon_lbl)

        self._mon_group = QButtonGroup(self)
        for label, value in [("Single Monitor", "single"), ("Multi-Monitor", "multi")]:
            rb = QRadioButton(label)
            rb.setProperty("value", value)
            rb.setChecked(self.settings.get("monitor_mode", "single") == value)
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: {T['text_primary']}; font-size: 11px;
                    background: transparent; border: none; spacing: 8px;
                }}
                QRadioButton::indicator {{
                    width: 14px; height: 14px; border-radius: 7px;
                    border: 2px solid {T['border_hover']}; background: transparent;
                }}
                QRadioButton::indicator:checked {{
                    background: {T['accent']}; border-color: {T['accent']};
                }}
            """)
            self._mon_group.addButton(rb)
            layout.addWidget(rb)

        sep_mon = QFrame()
        sep_mon.setFrameShape(QFrame.Shape.HLine)
        sep_mon.setFixedHeight(1)
        sep_mon.setStyleSheet(f"background: {T['border']};")
        layout.addWidget(sep_mon)

        # ── Dark mode ─────────────────────────────────────────────────────
```

- [ ] **Step 2: Save `monitor_mode` in `_save`**

Find:
```python
        self.settings["dark_mode"] = self._dark_check.isChecked()
        self.settings["opacity"] = self._opacity_slider.value()
        self.accept()
```

Replace with:
```python
        self.settings["dark_mode"] = self._dark_check.isChecked()
        self.settings["opacity"] = self._opacity_slider.value()
        for btn in self._mon_group.buttons():
            if btn.isChecked():
                self.settings["monitor_mode"] = btn.property("value")
                break
        self.accept()
```

- [ ] **Step 3: Verify the Settings dialog shows the new section**

```
python "YOINK WINDOWS/main.py"
```
Open Settings — you should see a **Monitor mode** section with `Single Monitor` selected by default. Select `Multi-Monitor` and click Save. Reopen Settings — `Multi-Monitor` should still be selected.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: add Monitor mode selector to SettingsDialog"
```

---

### Task 7: End-to-end manual verification

No code changes — verification only.

- [ ] **Single Monitor mode (regression check)**

  1. Open Settings → confirm `Single Monitor` is selected → Save
  2. Drag a file near the configured screen edge → shelf appears
  3. Drop file on shelf → shelf stays visible with item
  4. Click switch toggle → shelf flips to opposite edge on the same monitor
  5. Use hotkey (default Ctrl+Y) → shelf appears / disappears

- [ ] **Multi-Monitor mode (new behaviour)**

  1. Connect a second monitor
  2. Open Settings → select `Multi-Monitor` → Save
  3. Pick up a file and drag it — shelf should appear on the monitor the cursor is on
  4. Drag cursor to the other monitor — wait ~400ms — shelf should slide out of the first monitor and slide into the second
  5. Move cursor quickly back to the first monitor — shelf should NOT jump (debounce prevents it)
  6. With shelf on monitor 2, click the switch toggle — shelf should flip left/right on monitor 2, not on monitor 1
  7. Release the file without dropping (press Escape) — shelf should auto-hide after 1.2s if empty

- [ ] **Final commit**

```bash
git add main.py settings.json
git commit -m "feat: multi-monitor mode — shelf follows cursor across screens while dragging"
git push
```
