import QtQuick
import Quickshell

// Runs ShelfClip (the GTK app next to this folder) while the plugin is enabled.
// The shelf is its own process: a shell reload destroys and recreates this
// service, and restarting the shelf then would drop its staged files. So on
// destruction we only stop it after checking the plugin really was disabled
// (or removed), and only the copy started from this checkout.
Item {
  id: root
  width: 0
  height: 0
  visible: false

  property var shell: null
  property var manifest: null

  readonly property string pluginId: "viniabdalla.shelfclip"
  readonly property string repoDir: decodeURIComponent(String(Qt.resolvedUrl("..")).replace(/^file:\/\//, "").replace(/\/$/, ""))
  readonly property string launcher: repoDir + "/shelfclip"

  // Single instance over D-Bus: if ShelfClip already runs (autostart, another
  // checkout), this exits at once and leaves that one alone.
  Component.onCompleted: Quickshell.execDetached([launcher])

  Component.onDestruction: Quickshell.execDetached(["sh", "-c",
    "sleep 3; omarchy-plugin-list --json 2>/dev/null"
    + " | jq -e --arg id \"$1\" 'any(.[]; .id == $id and .enabled)' >/dev/null"
    + " || pkill -TERM -f -- \"$2/main.py\"",
    "shelfclip-stop", pluginId, repoDir])
}
