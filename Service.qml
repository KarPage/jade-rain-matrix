import QtQuick

// Catalog entry so Omarchy can install this folder as a plugin.
// The wallpaper is produced by the jade-rain-matrix command. This service does not
// draw, watch the theme, or open a network connection.
Item {
    id: root
    visible: false

    property var shell: null
    property string omarchyPath: ""
    property var manifest: null
    property var pluginRegistry: null
    property var barWidgetRegistry: null
}
