import QtQuick
import Quickshell

// One square glyph on the Omarchy bar. Click opens the local editor.
Item {
    id: root
    property var shell: null
    property string omarchyPath: ""
    property var manifest: null
    property var pluginRegistry: null
    property var barWidgetRegistry: null
    property var bar: null
    property string moduleName: "jade-rain"
    property var settings: null
    property string fixedEdge: "start"

    implicitWidth: 18
    implicitHeight: bar && bar.barSize ? bar.barSize : 26

    Item {
        anchors.centerIn: parent
        width: 8
        height: 14
        Rectangle { x: 0; y: 5; width: 1; height: 9; color: "#3fe0a4" }
        Rectangle { x: 3; y: 0; width: 1; height: 14; color: "#3fe0a4" }
        Rectangle { x: 6; y: 4; width: 1; height: 10; color: "#3fe0a4" }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onEntered: if (bar && bar.showTooltip) bar.showTooltip(root, "Jade Rain Matrix")
        onExited: if (bar && bar.hideTooltip) bar.hideTooltip(root)
        onClicked: root.openEditor()
    }

    function binaryPath() {
        var url = Qt.resolvedUrl("bin/jade-rain").toString()
        if (url.indexOf("file://") === 0)
            url = decodeURIComponent(url.substring(7))
        return url.length ? url : "jade-rain"
    }

    function shellQuote(value) {
        return "'" + value.split("'").join("'\\''") + "'"
    }

    function openEditor() {
        var binary = binaryPath()
        if (bar && bar.run) {
            bar.run(shellQuote(binary) + " edit")
            return
        }
        Quickshell.execDetached([binary, "edit"])
    }
}
