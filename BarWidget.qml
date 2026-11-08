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

    implicitWidth: 22
    implicitHeight: bar && bar.barSize ? bar.barSize : 26

    Item {
        anchors.centerIn: parent
        width: 13
        height: 14
        // Option A: three staggered dim columns, each with a bright 3x3 tip.
        Rectangle { x: 0; y: 0; width: 3; height: 6; color: Qt.darker("#3fe0a4", 1.4) }
        Rectangle { x: 0; y: 6; width: 3; height: 3; color: Qt.lighter("#3fe0a4", 1.35) }
        Rectangle { x: 5; y: 4; width: 3; height: 7; color: Qt.darker("#3fe0a4", 1.4) }
        Rectangle { x: 5; y: 11; width: 3; height: 3; color: Qt.lighter("#3fe0a4", 1.35) }
        Rectangle { x: 10; y: 2; width: 3; height: 6; color: Qt.darker("#3fe0a4", 1.4) }
        Rectangle { x: 10; y: 8; width: 3; height: 3; color: Qt.lighter("#3fe0a4", 1.35) }
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
