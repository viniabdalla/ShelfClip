#!/usr/bin/env python3
"""
ShelfClip - Yoink-like floating file shelf for Windows
Appears only when dragging near the configured edge, or via global hotkey.
"""

import sys
import os
import json
import ctypes
import ctypes.wintypes
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QDialog,
    QRadioButton, QButtonGroup, QSizePolicy, QSpinBox,
    QSystemTrayIcon, QMenu, QFileIconProvider
)
from PyQt6.QtCore import (
    Qt, QMimeData, QUrl, QPoint, QRect, QTimer, QSize,
    QPropertyAnimation, QEasingCurve, QFileInfo,
    QAbstractNativeEventFilter
)
from PyQt6.QtGui import (
    QDrag, QPixmap, QIcon, QColor, QPainter,
    QFont, QImage, QGuiApplication, QCursor, QAction, QScreen,
    QKeySequence
)


# ── Constants ─────────────────────────────────────────────────────────────────
SHELF_WIDTH   = 135
ITEM_HEIGHT   = 58
MAX_ITEMS     = 30
HOTKEY_ID     = 1
TEMP_DIR      = Path(tempfile.gettempdir()) / "shelfclip"
TEMP_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = Path(__file__).parent / "settings.json"

BG_HOVER_COLOR = "rgba(22, 22, 35, 245)"
ITEM_BG        = "rgba(255, 255, 255, 12)"
ITEM_BG_HOVER  = "rgba(255, 255, 255, 22)"
ACCENT         = "#5b9cf6"
TEXT_PRIMARY   = "rgba(255, 255, 255, 220)"
TEXT_SECONDARY = "rgba(255, 255, 255, 100)"
BORDER         = "rgba(255, 255, 255, 25)"
BORDER_HOVER   = "rgba(255, 255, 255, 45)"
SWITCH_BG      = "#4f97f2"
SWITCH_KNOB    = "#f6f7fb"


# ── Settings ──────────────────────────────────────────────────────────────────
def load_settings() -> dict:
    defaults = {"side": "right", "hotkey": "ctrl+y", "show_time": 4}
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            defaults.update(data)
        except Exception:
            pass
    return defaults


def save_settings(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))


# ── Multi-monitor helpers ─────────────────────────────────────────────────────
def get_edge_screen(side: str) -> QScreen:
    screens = QGuiApplication.screens()
    if side == "right":
        return max(screens, key=lambda s: s.geometry().right())
    return min(screens, key=lambda s: s.geometry().left())


def shelf_x(side: str, screen: QScreen) -> int:
    if side == "right":
        return screen.geometry().right() - SHELF_WIDTH - 2
    return screen.geometry().left() + 2


def offscreen_x(side: str, screen: QScreen) -> int:
    if side == "right":
        return screen.geometry().right() + 4
    return screen.geometry().left() - SHELF_WIDTH - 4


def near_edge(side: str, screen: QScreen, cursor: QPoint) -> bool:
    if side == "right":
        return cursor.x() >= screen.geometry().right() - 4
    return cursor.x() <= screen.geometry().left() + 4


def is_dragging() -> bool:
    """True if the left mouse button is currently held down (user is dragging)."""
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)


# ── Hotkey parsing ────────────────────────────────────────────────────────────
def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Parse 'ctrl+y' -> (win_modifiers, vk_code) for RegisterHotKey."""
    parts = [p.strip().lower() for p in hotkey_str.split('+')]
    mod, vk = 0, 0
    mod_map = {'ctrl': 0x0002, 'alt': 0x0001, 'shift': 0x0004, 'win': 0x0008}
    for part in parts:
        if part in mod_map:
            mod |= mod_map[part]
        elif len(part) == 1 and part.isalpha():
            vk = ord(part.upper())
        elif len(part) == 1 and part.isdigit():
            vk = ord(part)
        elif part.startswith('f') and part[1:].isdigit():
            fn = int(part[1:])
            if 1 <= fn <= 12:
                vk = 0x6F + fn
    return mod, vk


# ── Tray icon ─────────────────────────────────────────────────────────────────
def make_tray_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(91, 156, 246))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 24, 24, 6, 6)
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    p.end()
    return QIcon(px)


def make_side_switch_icon(side: str) -> QIcon:
    px = QPixmap(34, 20)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(SWITCH_BG))
    p.drawRoundedRect(0, 0, 34, 20, 10, 10)

    knob_x = 2 if side == "left" else 16
    p.setBrush(QColor(0, 0, 0, 40))
    p.drawEllipse(knob_x, 3, 16, 16)
    p.setBrush(QColor(SWITCH_KNOB))
    p.drawEllipse(knob_x, 2, 16, 16)
    p.end()
    return QIcon(px)


# ── Hotkey capture widget ─────────────────────────────────────────────────────
class HotkeyCapture(QPushButton):
    """Button that records a key combination when clicked."""

    def __init__(self, hotkey_str: str, parent=None):
        super().__init__(parent)
        self.hotkey = hotkey_str
        self._listening = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._update_display()
        self.clicked.connect(self._start_listening)

    def _start_listening(self):
        self._listening = True
        self.setText("Press shortcut...")
        self.grabKeyboard()

    def keyPressEvent(self, e):
        if not self._listening:
            super().keyPressEvent(e)
            return
        key = e.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift,
                   Qt.Key.Key_Meta, Qt.Key.Key_unknown):
            return
        parts = []
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        key_str = QKeySequence(key).toString().lower()
        if key_str:
            parts.append(key_str)
            self.hotkey = "+".join(parts)
        self._listening = False
        self.releaseKeyboard()
        self._update_display()

    def focusOutEvent(self, e):
        if self._listening:
            self._listening = False
            self.releaseKeyboard()
            self._update_display()
        super().focusOutEvent(e)

    def _update_display(self):
        self.setText(self.hotkey.upper().replace("+", " + "))


# ── Settings dialog ───────────────────────────────────────────────────────────
class SettingsDialog(QDialog):

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.settings = dict(current_settings)
        self._build_ui()
        self.setWindowTitle("ShelfClip Settings")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(260)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card {
                background: rgba(22, 22, 35, 250);
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,40);
            }
        """)
        root.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Settings")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_SECONDARY}; background: rgba(255,255,255,15);
                border-radius: 11px; font-size: 15px; font-weight: bold; border: none;
            }}
            QPushButton:hover {{ background: rgba(220,60,60,200); color: white; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER};")
        layout.addWidget(sep)

        # ── Edge side ────────────────────────────────────────────────────
        side_lbl = QLabel("Snap to edge")
        side_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(side_lbl)

        self._btn_group = QButtonGroup(self)
        for label, value in [("Right edge", "right"), ("Left edge", "left")]:
            rb = QRadioButton(label)
            rb.setProperty("value", value)
            rb.setChecked(self.settings.get("side") == value)
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: {TEXT_PRIMARY}; font-size: 11px;
                    background: transparent; border: none; spacing: 8px;
                }}
                QRadioButton::indicator {{
                    width: 14px; height: 14px; border-radius: 7px;
                    border: 2px solid rgba(255,255,255,80); background: transparent;
                }}
                QRadioButton::indicator:checked {{
                    background: {ACCENT}; border-color: {ACCENT};
                }}
            """)
            self._btn_group.addButton(rb)
            layout.addWidget(rb)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {BORDER};")
        layout.addWidget(sep2)

        # ── Global hotkey ─────────────────────────────────────────────────
        hotkey_lbl = QLabel("Toggle shortcut  (click to change)")
        hotkey_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(hotkey_lbl)

        self._hotkey_capture = HotkeyCapture(
            self.settings.get("hotkey", "ctrl+y")
        )
        self._hotkey_capture.setFixedHeight(30)
        self._hotkey_capture.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,12);
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,22);
                border-color: {ACCENT};
            }}
        """)
        layout.addWidget(self._hotkey_capture)

        show_time_lbl = QLabel("Show time after shortcut")
        show_time_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(show_time_lbl)

        self._show_time_spin = QSpinBox()
        self._show_time_spin.setRange(1, 30)
        self._show_time_spin.setValue(int(self.settings.get("show_time", 4)))
        self._show_time_spin.setSuffix(" s")
        self._show_time_spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self._show_time_spin.setFixedHeight(30)
        self._show_time_spin.setStyleSheet(f"""
            QSpinBox {{
                background: rgba(255,255,255,12);
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-size: 11px;
                padding: 0 8px;
            }}
            QSpinBox:hover {{
                background: rgba(255,255,255,22);
                border-color: {ACCENT};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 18px;
                border: none;
                background: transparent;
            }}
        """)
        layout.addWidget(self._show_time_spin)

        layout.addSpacing(4)

        # Save button
        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(32)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: white;
                border: none; border-radius: 8px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #4a8ce0; }}
        """)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _save(self):
        for btn in self._btn_group.buttons():
            if btn.isChecked():
                self.settings["side"] = btn.property("value")
                break
        self.settings["hotkey"] = self._hotkey_capture.hotkey
        self.settings["show_time"] = self._show_time_spin.value()
        self.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dp = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "_dp"):
            self.move(e.globalPosition().toPoint() - self._dp)
        super().mouseMoveEvent(e)


# ── Single shelf item ─────────────────────────────────────────────────────────
class ShelfItem(QFrame):

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.selected = False
        self._drag_start: QPoint | None = None
        self._build_ui()

    def _build_ui(self):
        self.setFixedHeight(ITEM_HEIGHT)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self._set_style(hovered=False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        provider = QFileIconProvider()
        info = QFileInfo(self.file_path)
        icon = provider.icon(info)

        icon_label = QLabel()
        icon_label.setFixedSize(38, 38)
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")

        ext = Path(self.file_path).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
            thumb = QPixmap(self.file_path).scaled(
                38, 38,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon_label.setPixmap(thumb)
        else:
            icon_label.setPixmap(icon.pixmap(36, 36))
        layout.addWidget(icon_label)

        name = Path(self.file_path).name
        name_label = QLabel()
        name_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 11px; "
            "background: transparent; border: none;"
        )
        name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        name_label.setToolTip(self.file_path)
        fm = name_label.fontMetrics()
        name_label.setText(fm.elidedText(name, Qt.TextElideMode.ElideMiddle, 55))
        layout.addWidget(name_label, 1)

        # Overlay × button at the top-right corner of the card
        btn = QPushButton("×", self)
        btn.setFixedSize(16, 16)
        btn.setStyleSheet("""
            QPushButton {
                color: rgba(255,255,255,140); background: rgba(30,30,50,210);
                border-radius: 8px; font-size: 13px; font-weight: bold;
                border: 1px solid rgba(255,255,255,35);
                padding: 0px 0px 3px 0px; margin: 0px; text-align: center;
            }
            QPushButton:hover { background: rgba(220,60,60,220); color: white;
                border-color: rgba(220,60,60,220); }
        """)
        btn.clicked.connect(self._request_remove)
        self._remove_btn = btn
        btn.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, '_remove_btn'):
            btn = self._remove_btn
            btn.move(self.width() - 12 - btn.width(), 3)

    def _set_style(self, hovered: bool):
        if self.selected:
            bg = "rgba(91,156,246,70)" if not hovered else "rgba(91,156,246,100)"
            border = "border: 1px solid rgba(91,156,246,180);"
        else:
            bg = ITEM_BG_HOVER if hovered else ITEM_BG
            border = ""
        self.setStyleSheet(f"""
            QFrame {{ background-color: {bg}; border-radius: 10px; margin: 1px 6px; {border} }}
        """)

    def enterEvent(self, e):
        self._set_style(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._set_style(False)
        super().leaveEvent(e)

    def _get_shelf(self):
        parent = self.parent()
        while parent:
            if isinstance(parent, ShelfWindow):
                return parent
            parent = parent.parent()
        return None

    def _request_remove(self):
        shelf = self._get_shelf()
        if shelf:
            shelf.remove_item(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.pos()
            shelf = self._get_shelf()
            if shelf:
                shelf.handle_item_click(self, e.modifiers())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if (e.buttons() & Qt.MouseButton.LeftButton and
                self._drag_start is not None and
                (e.pos() - self._drag_start).manhattanLength() > 8):
            shelf = self._get_shelf()
            # Determine which files to drag
            if shelf and self in shelf._selected and len(shelf._selected) > 1:
                drag_items = list(shelf._selected)
            else:
                drag_items = [self]

            drag = QDrag(self)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(i.file_path) for i in drag_items])
            drag.setMimeData(mime)

            # Build drag pixmap
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(self.file_path))
            if len(drag_items) == 1:
                drag.setPixmap(icon.pixmap(48, 48))
                drag.setHotSpot(QPoint(24, 24))
            else:
                px = QPixmap(58, 58)
                px.fill(Qt.GlobalColor.transparent)
                p = QPainter(px)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.drawPixmap(0, 8, icon.pixmap(44, 44))
                p.setBrush(QColor(91, 156, 246))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(34, 0, 22, 22)
                p.setPen(QColor(255, 255, 255))
                p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                p.drawText(QRect(34, 0, 22, 22), Qt.AlignmentFlag.AlignCenter,
                           str(len(drag_items)))
                p.end()
                drag.setPixmap(px)
                drag.setHotSpot(QPoint(22, 30))

            result = drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
            if result != Qt.DropAction.IgnoreAction:
                if shelf:
                    for item in drag_items:
                        shelf.remove_item(item)
                else:
                    self._request_remove()
        super().mouseMoveEvent(e)


# ── Empty-shelf drop hint ─────────────────────────────────────────────────────
class DropHint(QLabel):
    def __init__(self):
        super().__init__()
        self.setText("Drop files here\nor press Ctrl+V")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(100)
        self._set_style(active=False)

    def _set_style(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                color: {ACCENT}; font-size: 12px;
                border: 2px dashed {ACCENT}; border-radius: 12px;
                margin: 14px 10px; background: rgba(91,156,246,15);
            """)
        else:
            self.setStyleSheet(f"""
                color: {TEXT_SECONDARY}; font-size: 12px;
                border: 2px dashed rgba(255,255,255,40); border-radius: 12px;
                margin: 14px 10px; background: transparent;
            """)

    def set_active(self, v: bool):
        self._set_style(v)


# ── Global hotkey event filter ────────────────────────────────────────────────
class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:  # WM_HOTKEY
                self._callback()
                return True, 0
        return False, 0


# ── Main shelf window ─────────────────────────────────────────────────────────
class ShelfWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.items: list[ShelfItem] = []
        self._selected: list[ShelfItem] = []
        self._last_clicked: ShelfItem | None = None
        self._is_shown = False
        self._anim = None
        self._settings = load_settings()
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._slide_out)
        self._setup_window()
        self._build_ui()
        self._setup_tray()
        self._position_on_screen()
        self._setup_cursor_watch()
        self._register_hotkey()

    # ── Window setup ──────────────────────────────────────────────────────
    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFixedWidth(SHELF_WIDTH)

    def _position_on_screen(self):
        side = self._settings["side"]
        screen = get_edge_screen(side)
        h = 240
        self.setFixedHeight(h)
        y = screen.availableGeometry().center().y() - h // 2
        self.move(offscreen_x(side, screen), y)
        self.hide()

    # ── Global hotkey (Windows RegisterHotKey) ────────────────────────────
    def _register_hotkey(self):
        mod, vk = parse_hotkey(self._settings.get("hotkey", "ctrl+y"))
        if vk:
            ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mod, vk)
            self._hotkey_filter = HotkeyFilter(self._toggle_shelf)
            QApplication.instance().installNativeEventFilter(self._hotkey_filter)

    def _unregister_hotkey(self):
        ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        if hasattr(self, "_hotkey_filter"):
            QApplication.instance().removeNativeEventFilter(self._hotkey_filter)

    def _toggle_shelf(self):
        if self._is_shown:
            self._collapse_timer.stop()
            self._slide_out()
        else:
            self._slide_in()
            self._collapse_timer.start(int(self._settings.get("show_time", 4)) * 1000)

    # ── Cursor polling ────────────────────────────────────────────────────
    def _setup_cursor_watch(self):
        self._poll = QTimer(self)
        self._poll.setInterval(80)
        self._poll.timeout.connect(self._poll_cursor)
        self._poll.start()

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

    # ── Slide animations ──────────────────────────────────────────────────
    def _slide_in(self):
        self._is_shown = True
        side = self._settings["side"]
        screen = get_edge_screen(side)
        y = screen.availableGeometry().center().y() - self.height() // 2
        start = QPoint(offscreen_x(side, screen), y)
        end   = QPoint(shelf_x(side, screen), y)
        self.move(start)
        self.show()
        self._set_card_style(dimmed=False)
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(180)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

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

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame(self)
        self._card.setObjectName("card")
        root.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 8, 0, 10)
        card_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(10, 4, 8, 6)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        header.addWidget(self._count_lbl)

        self._side_switch = QPushButton()
        self._side_switch.setFixedSize(34, 20)
        self._side_switch.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._side_switch.setToolTip("Switch shelf side")
        self._side_switch.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self._side_switch.clicked.connect(self._toggle_side)
        header.addWidget(self._side_switch)

        header.addStretch()

        gear_btn = QPushButton("⚙")
        gear_btn.setFixedSize(20, 20)
        gear_btn.setStyleSheet(f"""
            QPushButton {{ color: {TEXT_SECONDARY}; background: transparent;
                border: none; font-size: 13px; }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; }}
        """)
        gear_btn.clicked.connect(self._open_settings)
        header.addWidget(gear_btn)

        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(20, 20)
        clear_btn.setStyleSheet(f"""
            QPushButton {{ color: {TEXT_SECONDARY}; background: transparent;
                border: none; font-size: 11px; }}
            QPushButton:hover {{ color: rgba(220,80,80,230); }}
        """)
        clear_btn.clicked.connect(self.clear_all)
        header.addWidget(clear_btn)
        card_layout.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER}; margin: 0 8px;")
        card_layout.addWidget(sep)
        card_layout.addSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: rgba(255,255,255,8); width: 4px;
                margin: 4px 2px; border-radius: 2px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,55);
                border-radius: 2px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self._items_widget = QWidget()
        self._items_widget.setStyleSheet("background: transparent;")
        self._items_layout = QVBoxLayout(self._items_widget)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(3)
        self._items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._drop_hint = DropHint()
        self._items_layout.addWidget(self._drop_hint)

        scroll.setWidget(self._items_widget)
        card_layout.addWidget(scroll)

        foot = QLabel("Drag files in  •  Ctrl+V to paste")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 9px; "
            "background: transparent; border: none; padding: 4px;"
        )
        card_layout.addWidget(foot)

        self._set_card_style(dimmed=True)
        self._refresh_side_switch()

    def _set_card_style(self, dimmed: bool):
        bg = "rgba(18,18,28,160)" if dimmed else BG_HOVER_COLOR
        border = BORDER if dimmed else BORDER_HOVER
        self._card.setStyleSheet(f"""
            QFrame#card {{ background-color: {bg}; border-radius: 16px;
                border: 1px solid {border}; }}
        """)

    # ── Settings ──────────────────────────────────────────────────────────
    def _refresh_side_switch(self):
        if not hasattr(self, "_side_switch"):
            return
        self._side_switch.setIcon(make_side_switch_icon(self._settings["side"]))
        self._side_switch.setIconSize(QSize(34, 20))

    def _toggle_side(self):
        self._settings["side"] = "left" if self._settings["side"] == "right" else "right"
        save_settings(self._settings)
        self._collapse_timer.stop()
        self._is_shown = False
        self.hide()
        self._position_on_screen()
        self._refresh_side_switch()
        self._slide_in()

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self)
        dlg.move(
            self.x() - dlg.width() - 8 if self._settings["side"] == "right"
            else self.x() + self.width() + 8,
            self.y() + self.height() // 2 - 120
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._unregister_hotkey()
            self._settings = dlg.settings
            save_settings(self._settings)
            self._is_shown = False
            self.hide()
            self._position_on_screen()
            self._register_hotkey()
            self._refresh_side_switch()

    # ── Tray ──────────────────────────────────────────────────────────────
    def _setup_tray(self):
        self._tray = QSystemTrayIcon(make_tray_icon(), self)
        self._tray.setToolTip("ShelfClip")
        menu = QMenu()
        settings_act = QAction("Settings", self)
        settings_act.triggered.connect(self._open_settings)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(QApplication.instance().quit)
        menu.addAction(settings_act)
        menu.addSeparator()
        menu.addAction(quit_act)
        self._tray.setContextMenu(menu)
        self._tray.show()

    # ── Mouse / keyboard events ───────────────────────────────────────────
    def enterEvent(self, e):
        self._collapse_timer.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self.items:
            self._collapse_timer.start(1200)
        super().leaveEvent(e)

    def keyPressEvent(self, e):
        if (e.key() == Qt.Key.Key_V and
                e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._paste_from_clipboard()
        elif e.key() == Qt.Key.Key_Escape:
            self.clear_all()
        super().keyPressEvent(e)

    def _paste_from_clipboard(self):
        cb = QGuiApplication.clipboard()
        mime = cb.mimeData()
        if mime.hasImage():
            img: QImage = cb.image()
            if not img.isNull():
                idx = len(list(TEMP_DIR.glob("clipboard_*.png")))
                path = TEMP_DIR / f"clipboard_{idx:04d}.png"
                img.save(str(path))
                self.add_file(str(path))
                return
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self.add_file(url.toLocalFile())
            return
        if mime.hasText():
            text = mime.text().strip()
            if text:
                idx = len(list(TEMP_DIR.glob("clipboard_text_*.txt")))
                path = TEMP_DIR / f"clipboard_text_{idx:04d}.txt"
                path.write_text(text, encoding="utf-8")
                self.add_file(str(path))

    # ── Drag-and-drop accept ──────────────────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drop_hint.set_active(True)
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._drop_hint.set_active(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        self._drop_hint.set_active(False)
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        new_files = [u for u in urls
                     if not any(i.file_path == u.toLocalFile() for i in self.items)]
        if new_files:
            for u in new_files:
                self.add_file(u.toLocalFile())
            e.acceptProposedAction()
        else:
            e.ignore()

    # ── Selection ─────────────────────────────────────────────────────────
    def _clear_selection(self):
        for item in self._selected:
            item.selected = False
            item._set_style(False)
        self._selected.clear()

    def handle_item_click(self, item: ShelfItem, modifiers):
        ctrl  = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if ctrl:
            if item in self._selected:
                self._selected.remove(item)
                item.selected = False
            else:
                self._selected.append(item)
                item.selected = True
            item._set_style(False)
            self._last_clicked = item

        elif shift and self._last_clicked and self._last_clicked in self.items:
            i1 = self.items.index(self._last_clicked)
            i2 = self.items.index(item)
            self._clear_selection()
            for it in self.items[min(i1, i2): max(i1, i2) + 1]:
                it.selected = True
                self._selected.append(it)
                it._set_style(False)

        else:
            self._clear_selection()
            item.selected = True
            self._selected = [item]
            item._set_style(False)
            self._last_clicked = item

    # ── Item management ───────────────────────────────────────────────────
    def add_file(self, file_path: str):
        if any(i.file_path == file_path for i in self.items):
            return
        if len(self.items) >= MAX_ITEMS:
            return
        self._drop_hint.hide()
        item = ShelfItem(file_path)
        self.items.append(item)
        self._items_layout.addWidget(item)
        self._update_count()
        self._collapse_timer.stop()
        if not self._is_shown:
            self._slide_in()

    def remove_item(self, item: ShelfItem):
        if item in self.items:
            self.items.remove(item)
            self._items_layout.removeWidget(item)
            item.deleteLater()
        if item in self._selected:
            self._selected.remove(item)
        if self._last_clicked is item:
            self._last_clicked = None
        if not self.items:
            self._drop_hint.show()
        self._update_count()

    def clear_all(self):
        for item in self.items[:]:
            self._items_layout.removeWidget(item)
            item.deleteLater()
        self.items.clear()
        self._selected.clear()
        self._last_clicked = None
        self._drop_hint.show()
        self._update_count()

    def _update_count(self):
        n = len(self.items)
        self._count_lbl.setText(f"{n} item{'s' if n != 1 else ''}" if n else "")

    def closeEvent(self, e):
        self._unregister_hotkey()
        super().closeEvent(e)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ShelfClip")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(make_tray_icon())
    win = ShelfWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
