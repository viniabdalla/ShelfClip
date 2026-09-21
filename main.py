#!/usr/bin/env python3
"""ShelfClip — a Yoink-style file shelf for Omarchy (Hyprland / Wayland).

A minimal panel pinned to the top-right corner, just under the bar. It stays
collapsed to a thin invisible strip on the screen edge until a file is dragged
onto that strip (or `shelfclip toggle` is run), then grows downward as files
are staged. Colors come from the active Omarchy theme.
"""
import os
import sys


def _ensure_layer_shell_preload():
    """gtk4-layer-shell must be loaded before libwayland-client, which Python's
    GTK import pulls in first. Re-exec once with LD_PRELOAD so `python main.py`
    just works."""
    lib = next((p for p in ("/usr/lib/libgtk4-layer-shell.so",
                            "/usr/lib64/libgtk4-layer-shell.so",
                            "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so")
                if os.path.exists(p)), None)
    if lib and lib not in os.environ.get("LD_PRELOAD", ""):
        env = dict(os.environ)
        env["LD_PRELOAD"] = f"{lib} {env.get('LD_PRELOAD', '')}".strip()
        os.execve(sys.executable, [sys.executable, *sys.argv], env)


_ensure_layer_shell_preload()

import json  # noqa: E402
import mimetypes  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import tomllib  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import (  # noqa: E402
    Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, Gtk4LayerShell as LS, Pango,
)

APP_ID = "dev.shelfclip.ShelfClip"
MAX_ITEMS = 30
COLLAPSE_MS = 1200          # empty shelf hides this long after the pointer leaves
BAR_FALLBACK = 26           # top reserved area if hyprctl can't tell us
THEME_DIR = Path.home() / ".local/state/omarchy/current"
CONFIG_FILE = Path.home() / ".config/shelfclip/config.json"
DEFAULTS = {
    "show_time": 5,         # seconds a hotkey-opened, empty shelf stays visible
    "tile_size": 120,       # px, tiles are square
    "trigger_width": 24,    # px, drag hot-zone on the screen edge while collapsed
    "margin": 2,            # px, gap under the bar and to the edge when open
    "drag_action": "move",  # what dragging a tile out does: "move" or "copy"; Ctrl at drag start flips it
}

# Children of ours (hyprctl, wl-paste) must not inherit the layer-shell preload.
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "LD_PRELOAD"}


# ── Config & theme ───────────────────────────────────────────────────────────
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text()))
    except (OSError, ValueError):
        pass
    if cfg["drag_action"] not in ("copy", "move"):
        cfg["drag_action"] = DEFAULTS["drag_action"]
    return cfg


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a: str, b: str, t: float) -> str:
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def _rgba(h: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(h)
    return f"rgba({r},{g},{b},{alpha})"


def load_palette() -> dict:
    try:
        c = tomllib.loads((THEME_DIR / "theme/colors.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError):
        c = {}
    bg = c.get("bg") or c.get("background") or "#1C1E26"
    fg = c.get("fg") or c.get("foreground") or "#CBCED0"
    return {
        "bg": bg,
        "fg": fg,
        "accent": c.get("accent") or c.get("color4") or "#26BBD9",
        "muted": c.get("muted") or c.get("color8") or "#6F6F70",
        "line": c.get("selection") or _mix(bg, fg, 0.12),
        "raised": c.get("lighter_bg") or _mix(bg, fg, 0.06),
        "red": c.get("red") or c.get("color1") or "#E95678",
    }


def build_css(p: dict, size: int) -> str:
    return f"""
window.shelf {{ background: transparent; font-family: monospace; }}
/* Not fully transparent on purpose: Hyprland keeps a stale, oversized geometry
   for a surface whose buffer is entirely alpha 0. 1% is invisible but real. */
.strip {{ background: rgba(0,0,0,0.01); }}
.panel {{ background: {p['bg']}; border: 1px solid {p['line']}; }}
.panel.drop-active {{ border-color: {p['accent']}; }}
.header {{ padding: 4px 8px 0 8px; color: {p['muted']}; font-size: 10px; }}
.header button, .tile .remove {{
    background: none; border: none; box-shadow: none; outline: none;
    padding: 0; min-width: 0; min-height: 0; border-radius: 0;
    text-shadow: none; -gtk-icon-shadow: none;
}}
.header button {{ color: {p['muted']}; font-size: 10px; }}
.header button:hover {{ color: {p['red']}; }}
.tile {{ background: {p['raised']}; border: 2px solid transparent; border-radius: 0; }}
.tile:hover {{ border-color: {p['muted']}; }}
.tile.selected {{ border-color: {p['accent']}; }}
.tile .name {{
    background: {_rgba(p['bg'], 0.88)}; color: {p['fg']};
    font-size: 10px; padding: 3px 6px;
}}
.tile .remove {{
    opacity: 0; background: {_rgba(p['bg'], 0.88)}; color: {p['fg']};
    min-width: 18px; min-height: 18px; font-size: 13px;
}}
.tile:hover .remove {{ opacity: 1; }}
.tile .remove:hover {{ background: {p['red']}; color: {p['bg']}; }}
.hint {{
    border: 1px dashed {p['muted']}; color: {p['muted']};
    font-size: 11px; margin: 4px;
}}
.badge {{
    background: {p['accent']}; color: {p['bg']}; font-weight: bold;
    font-size: 11px; padding: 1px 6px;
}}
"""


# ── Helpers ──────────────────────────────────────────────────────────────────
def hypr_monitors() -> list:
    try:
        out = subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True,
                             text=True, timeout=1, env=CLEAN_ENV)
        return json.loads(out.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def cursor_over_window() -> bool:
    """True if the pointer is over a mapped window. A drop on the bare desktop, the bar or the
    shelf itself hands the file to nobody, yet Hyprland still reports the drag as finished."""
    def query(*args):
        out = subprocess.run(["hyprctl", "-j", *args], capture_output=True, text=True,
                             timeout=1, env=CLEAN_ENV)
        return json.loads(out.stdout)
    try:
        pos = query("cursorpos")
        visible = set()
        for m in query("monitors"):
            visible.add(m["activeWorkspace"]["id"])
            if m.get("specialWorkspace", {}).get("id"):
                visible.add(m["specialWorkspace"]["id"])
        for c in query("clients"):
            if not c.get("mapped") or c.get("hidden") or c["workspace"]["id"] not in visible:
                continue
            (x, y), (w, h) = c["at"], c["size"]
            if x <= pos["x"] < x + w and y <= pos["y"] < y + h:
                return True
        return False
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return True                        # can't tell: behave as if it landed on a window


def temp_path(prefix: str, ext: str) -> Path:
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()) / "shelfclip"
    base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path, n = base / f"{prefix}-{stamp}{ext}", 1
    while path.exists():
        path = base / f"{prefix}-{stamp}-{n}{ext}"
        n += 1
    return path


def uris_to_paths(text: str) -> list:
    paths = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("file://"):
            p = Gio.File.new_for_uri(line).get_path()
            if p:
                paths.append(p)
    return paths


# ── Model ────────────────────────────────────────────────────────────────────
class Shelf:
    """Staged paths and selection, shared by every monitor's window."""

    def __init__(self):
        self.paths: list = []
        self.selected: list = []
        self.last_clicked = None
        self.on_items: list = []
        self.on_selection: list = []

    def _emit(self, callbacks):
        for cb in list(callbacks):
            cb()

    def add(self, path: str) -> bool:
        if path in self.paths or len(self.paths) >= MAX_ITEMS or not os.path.exists(path):
            return False
        self.paths.append(path)
        self._emit(self.on_items)
        return True

    def remove(self, paths):
        gone = [p for p in paths if p in self.paths]
        if not gone:
            return
        self.paths = [p for p in self.paths if p not in gone]
        self.selected = [p for p in self.selected if p not in gone]
        if self.last_clicked in gone:
            self.last_clicked = None
        self._emit(self.on_items)
        self._emit(self.on_selection)

    def clear(self):
        self.remove(list(self.paths))

    def click(self, path: str, ctrl=False, shift=False):
        if ctrl:
            if path in self.selected:
                self.selected.remove(path)
            else:
                self.selected.append(path)
            self.last_clicked = path
        elif shift and self.last_clicked in self.paths:
            i1, i2 = self.paths.index(self.last_clicked), self.paths.index(path)
            self.selected = self.paths[min(i1, i2):max(i1, i2) + 1]
        else:
            self.selected = [path]
            self.last_clicked = path
        self._emit(self.on_selection)

    def select_all(self):
        self.selected = list(self.paths)
        self._emit(self.on_selection)


# ── Tile ─────────────────────────────────────────────────────────────────────
class Tile(Gtk.Overlay):
    """One staged file: thumbnail/icon, name, hover-only remove button."""

    def __init__(self, win, path: str):
        super().__init__()
        self.win, self.path = win, path
        self.size = win.app.cfg["tile_size"]
        self._drag_paths: list = []
        self._drag_ok = False
        self._drop_on_window = True
        self._defer_collapse = False
        self._defer_toggle = False
        self._ctrl_at_press = False
        self.add_css_class("tile")
        self.set_size_request(self.size, self.size)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_cursor_from_name("grab")
        self.set_tooltip_text(path)

        self._build_body()

        # max_width_chars=1: a long name must ellipsize, not widen the tile.
        name = Gtk.Label(label=Path(path).name, xalign=0, max_width_chars=1,
                         ellipsize=Pango.EllipsizeMode.MIDDLE,
                         halign=Gtk.Align.FILL, valign=Gtk.Align.END)
        name.add_css_class("name")
        self.add_overlay(name)

        rm = Gtk.Button(label="×", halign=Gtk.Align.END, valign=Gtk.Align.START,
                        focusable=False, focus_on_click=False)
        rm.add_css_class("remove")
        rm.connect("clicked", lambda _b: win.app.shelf.remove([path]))
        self.add_overlay(rm)

        click = Gtk.GestureClick(button=1)
        click.connect("pressed", self._on_pressed)
        click.connect("released", self._on_released)
        self.add_controller(click)

        src = Gtk.DragSource(actions=Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        src.connect("prepare", self._on_prepare)
        src.connect("drag-begin", self._on_drag_begin)
        src.connect("drag-end", self._on_drag_end)
        self.add_controller(src)

    def _build_body(self):
        try:
            info = Gio.File.new_for_path(self.path).query_info(
                "standard::content-type,standard::icon", Gio.FileQueryInfoFlags.NONE, None)
            ctype, icon = info.get_content_type() or "", info.get_icon()
        except GLib.Error:
            ctype, icon = "", None

        self._icon = Gtk.Image(pixel_size=48, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        if icon is not None:
            self._icon.set_from_gicon(icon)
        else:
            self._icon.set_from_icon_name("text-x-generic")
        self.set_child(self._icon)

        if ctype.startswith("image/"):
            self.win.app.load_thumbnail(self.path, self._set_thumbnail)

    def _set_thumbnail(self, texture):
        if texture is None:
            return
        # Gtk.Image with a fixed pixel_size: a Picture's intrinsic size would widen the tile.
        self.set_child(Gtk.Image(paintable=texture, pixel_size=self.size - 4))  # minus the 2px border

    def set_selected(self, on: bool):
        (self.add_css_class if on else self.remove_css_class)("selected")

    # Selection: like a file manager, pressing on a member of a multi-selection
    # keeps it (so it can be dragged as a group) and collapses on release.
    def _on_pressed(self, gesture, _n, _x, _y):
        state = gesture.get_current_event_state()
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        self._ctrl_at_press = ctrl
        shelf = self.win.app.shelf
        if not ctrl and not shift and self.path in shelf.selected and len(shelf.selected) > 1:
            self._defer_collapse = True
            return
        if ctrl and not shift:
            # Ctrl also means "copy" when a drag starts, and a Ctrl-drag must not unselect the
            # tile it is dragging: toggle on release, and only if no drag started.
            self._defer_toggle = True
            return
        shelf.click(self.path, ctrl, shift)

    def _on_released(self, *_):
        shelf = self.win.app.shelf
        if self._defer_collapse:
            self._defer_collapse = False
            shelf.click(self.path)
        elif self._defer_toggle:
            self._defer_toggle = False
            shelf.click(self.path, ctrl=True)

    # Drag-out
    def _on_prepare(self, src, _x, _y):
        self._defer_collapse = False
        self._defer_toggle = False
        selected = self.win.app.shelf.selected
        self._drag_paths = (list(selected) if self.path in selected and len(selected) > 1
                            else [self.path])
        # Hyprland ignores Ctrl/Shift during a drag, so the copy/move choice is made here, by
        # what we offer: the configured default, flipped by Ctrl held when the drag starts.
        ctrl = self._ctrl_at_press or bool(src.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK)
        move = (self.win.app.cfg["drag_action"] == "move") != ctrl
        src.set_actions(Gdk.DragAction.MOVE if move else Gdk.DragAction.COPY)
        files = Gdk.FileList.new_from_array([Gio.File.new_for_path(p) for p in self._drag_paths])
        return Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.FileList, files))

    def _on_drag_begin(self, _src, drag):
        app = self.win.app
        app.internal_drag = True
        app.keep_after_drop = False
        self._drag_ok = False
        self._drop_on_window = True

        def finished(_d):
            self._drag_ok = True
        drag.connect("dnd-finished", finished)
        drag.connect("drop-performed",
                     lambda _d: setattr(self, "_drop_on_window", cursor_over_window()))

        overlay = Gtk.Overlay(opacity=0.9)
        pic = Gtk.Picture.new_for_paintable(Gtk.WidgetPaintable.new(self))
        pic.set_size_request(self.size, self.size)
        overlay.set_child(pic)
        if len(self._drag_paths) > 1:
            badge = Gtk.Label(label=str(len(self._drag_paths)),
                              halign=Gtk.Align.END, valign=Gtk.Align.START)
            badge.add_css_class("badge")
            overlay.add_overlay(badge)
        Gtk.DragIcon.get_for_drag(drag).set_child(overlay)
        if hasattr(drag, "set_hotspot"):
            drag.set_hotspot(self.size // 2, self.size // 2)

    def _on_drag_end(self, _src, _drag, delete_data):
        app, paths = self.win.app, self._drag_paths

        def finalize():
            app.internal_drag = False
            # A finished drop on a window hands the file off: unstage it. Dropped back on the
            # shelf or on the bare desktop (which accepts nothing on Omarchy) the tile stays.
            if (self._drag_ok or delete_data) and self._drop_on_window and not app.keep_after_drop:
                app.shelf.remove(paths)
            return False
        # dnd-finished and drag-end can arrive in either order; decide after both.
        GLib.idle_add(finalize)


# ── Per-monitor window ───────────────────────────────────────────────────────
class ShelfWindow(Gtk.ApplicationWindow):
    def __init__(self, app, monitor):
        super().__init__(application=app, title="ShelfClip")
        self.app, self.monitor = app, monitor
        self.is_open = False
        self.hover = False
        self.tiles: dict = {}
        cfg = app.cfg
        size = cfg["tile_size"]

        self.add_css_class("shelf")
        LS.init_for_window(self)
        LS.set_namespace(self, "shelfclip")
        LS.set_layer(self, LS.Layer.OVERLAY)
        LS.set_anchor(self, LS.Edge.TOP, True)
        LS.set_anchor(self, LS.Edge.RIGHT, True)
        LS.set_margin(self, LS.Edge.TOP, cfg["margin"])
        LS.set_exclusive_zone(self, 0)          # sit below the bar, don't push windows
        LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)
        LS.set_monitor(self, monitor)

        # panel: header + scrolling tile column (+ empty-state hint)
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.panel.add_css_class("panel")

        self.header = Gtk.Box(spacing=8)
        self.header.add_css_class("header")
        self.count = Gtk.Label(xalign=0, hexpand=True)
        clear = Gtk.Button(label="clear", focusable=False, focus_on_click=False)
        clear.connect("clicked", lambda _b: app.shelf.clear())
        self.header.append(self.count)
        self.header.append(clear)
        self.panel.append(self.header)

        self.column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                              margin_top=4, margin_bottom=4, margin_start=4, margin_end=4)
        self.scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height=True, propagate_natural_width=True, child=self.column)
        self.panel.append(self.scroller)

        self.hint = Gtk.Label(label="drop files")
        self.hint.add_css_class("hint")
        self.hint.set_size_request(size, size)
        self.panel.append(self.hint)

        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
                                     transition_duration=140, child=self.panel)
        self.revealer.connect("notify::child-revealed", self._on_revealed)
        # Transparent hot zone on the very screen edge; receives the drag that opens the shelf.
        self.strip = Gtk.Box()
        self.strip.add_css_class("strip")
        self.strip.set_size_request(cfg["trigger_width"], size + 16)

        root = Gtk.Box()
        root.append(self.revealer)
        root.append(self.strip)
        self.set_child(root)

        # File managers here offer only MOVE; a COPY-only target is rejected outright.
        # We never touch the files, we just remember their paths.
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        drop.connect("enter", self._on_drag_enter)
        drop.connect("leave", self._on_drag_leave)
        drop.connect("drop", self._on_drop)
        root.add_controller(drop)

        # DropTarget only emits `enter` once the drop's actions have arrived, which a quick
        # sweep across the edge never allows. This one reacts to the raw crossing.
        peek = Gtk.DropControllerMotion()
        peek.connect("enter", self._on_drag_peek)
        peek.connect("leave", lambda _c: self._on_drag_leave(None))
        root.add_controller(peek)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_pointer_enter)
        motion.connect("leave", self._on_pointer_leave)
        root.add_controller(motion)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        app.shelf.on_items.append(self.sync_items)
        app.shelf.on_selection.append(self.sync_selection)
        self.sync_items()
        self._fit()

    def do_close_request(self):
        self.app.shelf.on_items.remove(self.sync_items)
        self.app.shelf.on_selection.remove(self.sync_selection)
        return False

    # ── open / close ─────────────────────────────────────────────────────
    def set_open(self, on: bool):
        cfg = self.app.cfg
        self.is_open = on
        if on:
            self._update_limits()
        # Open: shrink the hot zone to the gap that lines up with Hyprland's gaps_out.
        self.strip.set_size_request(cfg["margin"] if on else cfg["trigger_width"],
                                    -1 if on else cfg["tile_size"] + 16)
        self.revealer.set_reveal_child(on)
        if on:
            self._fit()                    # grow now; shrinking waits for the slide-out

    def _on_revealed(self, revealer, _pspec):
        if not revealer.get_child_revealed():
            self._fit()

    def _fit(self):
        """A layer surface never shrinks by itself, and an oversized transparent
        surface would swallow clicks meant for the windows below. Pin the window
        to the strip when collapsed, or to the panel's natural size when open."""
        cfg = self.app.cfg
        if self.is_open:
            width = self.panel.measure(Gtk.Orientation.HORIZONTAL, -1)[1] + cfg["margin"]
            height = self.panel.measure(Gtk.Orientation.VERTICAL, width - cfg["margin"])[1]
        else:
            width, height = cfg["trigger_width"], cfg["tile_size"] + 16
        self.set_default_size(width, height)

    def _update_limits(self):
        geo = self.monitor.get_geometry()
        top = BAR_FALLBACK
        for m in hypr_monitors():
            if m.get("name") == self.monitor.get_connector():
                top = m.get("reserved", [0, BAR_FALLBACK])[1]
        chrome = 2 * self.app.cfg["margin"] + 2 + 24          # margins, border, header
        self.scroller.set_max_content_height(max(geo.height - top - chrome - 8, 100))

    # ── model → view ─────────────────────────────────────────────────────
    def sync_items(self):
        shelf = self.app.shelf
        for path in [p for p in self.tiles if p not in shelf.paths]:
            self.column.remove(self.tiles.pop(path))
        for path in shelf.paths:
            if path not in self.tiles:
                tile = Tile(self, path)
                self.tiles[path] = tile
                self.column.append(tile)
        n = len(shelf.paths)
        self.count.set_text(f"{n} item{'s' if n != 1 else ''}")
        self.header.set_visible(n > 0)
        self.scroller.set_visible(n > 0)
        self.hint.set_visible(n == 0)
        self.sync_selection()
        if self.is_open:
            GLib.idle_add(lambda: self._fit() or False)   # after the new tiles are laid out

    def sync_selection(self):
        selected = self.app.shelf.selected
        for path, tile in self.tiles.items():
            tile.set_selected(path in selected)

    # ── drag in ──────────────────────────────────────────────────────────
    def _on_drag_peek(self, ctrl, _x, _y):
        drop = ctrl.get_drop()
        if (self.app.internal_drag or drop is None
                or not drop.get_formats().contain_gtype(Gdk.FileList)):
            return
        self.app.open_on(self)

    def _on_drag_enter(self, dt, _x, _y):
        if self.app.internal_drag:
            return 0                      # our own tile dragged back: not a drop target
        self.panel.add_css_class("drop-active")
        self.app.open_on(self)
        drop = dt.get_current_drop()
        offered = drop.get_actions() if drop else Gdk.DragAction.COPY
        return Gdk.DragAction.COPY if offered & Gdk.DragAction.COPY else Gdk.DragAction.MOVE

    def _on_drag_leave(self, _dt):
        self.panel.remove_css_class("drop-active")
        self.app.maybe_collapse_soon()

    def _on_drop(self, _dt, value, _x, _y):
        self.panel.remove_css_class("drop-active")
        if self.app.internal_drag:
            self.app.keep_after_drop = True
            return False
        added = False
        for f in value.get_files():
            p = f.get_path()
            if p:
                added = self.app.shelf.add(p) or added
        return added                       # False → cancelled drop (already staged / non-local)

    # ── pointer / keyboard ───────────────────────────────────────────────
    def _on_pointer_enter(self, *_):
        self.hover = True
        self.app.cancel_collapse()

    def _on_pointer_leave(self, *_):
        self.hover = False
        self.app.maybe_collapse_soon()

    def _on_key(self, _ctrl, keyval, _code, state):
        shelf = self.app.shelf
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self.app.paste()
        elif ctrl and keyval in (Gdk.KEY_a, Gdk.KEY_A):
            shelf.select_all()
        elif keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            shelf.remove(list(shelf.selected))
        elif keyval == Gdk.KEY_Escape:
            shelf.clear()
        else:
            return False
        return True


# ── Application ──────────────────────────────────────────────────────────────
class ShelfApp(Gtk.Application):
    COMMANDS = ("toggle", "paste", "clear", "reload-theme", "quit")

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.cfg = load_config()
        self.shelf = Shelf()
        self.windows: dict = {}
        self.active = None                 # window currently expanded
        self.internal_drag = False
        self.keep_after_drop = False
        self._collapse_id = 0
        self._theme_id = 0
        self._css = Gtk.CssProvider()
        self._thumbs: dict = {}

    # lifecycle
    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self._css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.reload_theme()
        monitors = Gdk.Display.get_default().get_monitors()
        monitors.connect("items-changed", lambda *_: self.sync_windows())
        self.sync_windows()
        self.shelf.on_items.append(self._on_items_changed)
        try:                                # follow `omarchy theme set` live
            self._theme_mon = Gio.File.new_for_path(str(THEME_DIR)).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None)
            self._theme_mon.connect("changed", self._on_theme_event)
        except GLib.Error:
            pass

    def do_activate(self):
        pass

    def do_command_line(self, cmd):
        args = cmd.get_arguments()[1:]
        if not args:
            return 0
        name = args[0]
        if name == "toggle":
            self.toggle()
        elif name == "paste":
            self.paste()
        elif name == "clear":
            self.shelf.clear()
        elif name == "reload-theme":
            self.reload_theme()
        elif name == "quit":
            self.quit()
        else:
            cmd.printerr(f"usage: shelfclip [{'|'.join(self.COMMANDS)}]\n")
            return 2
        return 0

    # windows
    def sync_windows(self):
        current = {m.get_connector(): m for m in Gdk.Display.get_default().get_monitors()}
        for name in [n for n in self.windows if n not in current]:
            win = self.windows.pop(name)
            if win is self.active:
                self.active = None
            win.close()
        for name, monitor in current.items():
            if name not in self.windows:
                win = ShelfWindow(self, monitor)
                self.windows[name] = win
                win.present()

    def focused_window(self):
        name = next((m["name"] for m in hypr_monitors() if m.get("focused")), None)
        return self.windows.get(name) or next(iter(self.windows.values()), None)

    # open / close policy: an empty shelf hides again, one holding files stays put
    def open_on(self, win, seconds=None):
        self.cancel_collapse()
        if self.active is not None and self.active is not win:
            self.active.set_open(False)
        self.active = win
        if not win.is_open:
            win.set_open(True)
        if seconds and not self.shelf.paths:
            self._collapse_id = GLib.timeout_add(int(seconds * 1000), self._collapse)

    def close_all(self):
        self.cancel_collapse()
        for win in self.windows.values():
            win.set_open(False)
        self.active = None

    def toggle(self):
        if self.active is not None and self.active.is_open:
            self.close_all()
        else:
            win = self.focused_window()
            if win:
                self.open_on(win, self.cfg["show_time"])

    def cancel_collapse(self):
        if self._collapse_id:
            GLib.source_remove(self._collapse_id)
            self._collapse_id = 0

    def maybe_collapse_soon(self):
        if self.shelf.paths or self.internal_drag:
            return
        self.cancel_collapse()
        self._collapse_id = GLib.timeout_add(COLLAPSE_MS, self._collapse)

    def _collapse(self):
        self._collapse_id = 0
        hovered = self.active is not None and self.active.hover
        if not self.shelf.paths and not hovered:
            self.close_all()
        return False

    def _on_items_changed(self):
        if self.shelf.paths:
            if self.active is None or not self.active.is_open:
                win = self.focused_window()
                if win:
                    self.open_on(win)
        else:
            self.maybe_collapse_soon()

    # thumbnails (decoded off the main thread, cached)
    @staticmethod
    def _square_pixbuf(path: str, size: int):
        """Decode scaled to cover a size×size square, center-cropped."""
        info = GdkPixbuf.Pixbuf.get_file_info(path)
        if not info or not info[1] or not info[2]:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
        _fmt, w, h = info
        scale = size / min(w, h)
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            path, max(size, round(w * scale)), max(size, round(h * scale)), False)
        x, y = (pb.get_width() - size) // 2, (pb.get_height() - size) // 2
        return pb.new_subpixbuf(x, y, size, size)

    def load_thumbnail(self, path: str, callback):
        if path in self._thumbs:
            callback(self._thumbs[path])
            return
        size = self.cfg["tile_size"] * 2

        def work():
            try:
                pixbuf = self._square_pixbuf(path, size)
            except GLib.Error:
                pixbuf = None

            def done():
                texture = None
                if pixbuf:
                    fmt = (Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha()
                           else Gdk.MemoryFormat.R8G8B8)
                    texture = Gdk.MemoryTexture.new(
                        pixbuf.get_width(), pixbuf.get_height(), fmt,
                        pixbuf.read_pixel_bytes(), pixbuf.get_rowstride())
                self._thumbs[path] = texture
                callback(texture)
                return False
            GLib.idle_add(done)
        threading.Thread(target=work, daemon=True).start()

    # clipboard (wl-paste works without keyboard focus, unlike the GTK clipboard)
    def paste(self):
        def run(args, text=False):
            return subprocess.run(["wl-paste", *args], capture_output=True, text=text,
                                  timeout=3, env=CLEAN_ENV).stdout
        try:
            types = run(["--list-types"], text=True).split()
            paths = []
            if "text/uri-list" in types:
                paths = uris_to_paths(run(["-t", "text/uri-list"], text=True))
            elif "x-special/gnome-copied-files" in types:
                paths = uris_to_paths(run(["-t", "x-special/gnome-copied-files"], text=True))
            elif (mime := next((t for t in types if t.startswith("image/")), None)):
                ext = mimetypes.guess_extension(mime) or ".png"
                path = temp_path("clipboard", ext)
                path.write_bytes(run(["-t", mime]))
                paths = [str(path)]
            elif any(t.startswith("text/plain") or t in ("UTF8_STRING", "STRING") for t in types):
                text = run(["--no-newline"], text=True).strip()
                if text:
                    path = temp_path("clipboard", ".txt")
                    path.write_text(text, encoding="utf-8")
                    paths = [str(path)]
        except (OSError, subprocess.SubprocessError):
            return
        for p in paths:
            self.shelf.add(p)

    # theme
    def reload_theme(self):
        css = build_css(load_palette(), self.cfg["tile_size"])
        if hasattr(self._css, "load_from_string"):
            self._css.load_from_string(css)
        else:
            self._css.load_from_data(css.encode())

    def _on_theme_event(self, *_):
        if self._theme_id:
            GLib.source_remove(self._theme_id)

        def reload():                      # debounce: the theme is rewritten in several steps
            self._theme_id = 0
            self.reload_theme()
            return False
        self._theme_id = GLib.timeout_add(400, reload)


def main():
    sys.exit(ShelfApp().run(sys.argv))


if __name__ == "__main__":
    main()
