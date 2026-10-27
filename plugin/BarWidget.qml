import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Shelf icon for the bar, with the number of staged files. Left click opens or
// closes the shelf, right click opens its settings. Reads the state file the
// app keeps in $XDG_RUNTIME_DIR; when the file is missing the app isn't
// running and the icon is dimmed.
BarWidget {
  id: root
  moduleName: "viniabdalla.shelfclip"

  readonly property string repoDir: decodeURIComponent(String(Qt.resolvedUrl("..")).replace(/^file:\/\//, "").replace(/\/$/, ""))
  readonly property string launcher: repoDir + "/shelfclip"
  readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") || "/tmp"
  property int count: 0
  property bool running: false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function readState(text) {
    try {
      count = Math.max(0, parseInt(JSON.parse(text).count, 10) || 0)
      running = true
    } catch (e) {
      count = 0
      running = false
    }
  }

  FileView {
    id: state
    path: root.runtimeDir + "/shelfclip/state.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.readState(text())
    onLoadFailed: root.readState("")
  }

  // The app replaces the file atomically and deletes it on exit, which a
  // watch on a vanished inode can miss; a slow re-read keeps the icon honest.
  Timer {
    interval: 5000
    running: true
    repeat: true
    onTriggered: state.reload()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.count > 0 && !root.vertical ? " " + root.count : ""
    dimmed: !root.running
    tooltipText: !root.running ? "ShelfClip isn't running (click to start)"
      : (root.count === 1 ? "1 file on the shelf" : root.count + " files on the shelf")
        + "\nLeft click: open/close · Right click: settings"
    onPressed: function(mouseButton) {
      Util.execArgv([root.launcher, mouseButton === Qt.RightButton ? "settings" : "toggle"])
    }
  }
}
