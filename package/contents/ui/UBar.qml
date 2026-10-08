/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

import "Palette.js" as Palette

// Theme-aware meter: segmented in the pixel theme, a rounded bar otherwise.
// Setting `width` stretches the rounded bar; the pixel bar sizes itself
// from segments/segmentWidth.
Item {
    id: b

    property real value: 0
    property real level: value
    property int segments: 10
    property int unit: 2
    property int segmentWidth: 2
    property int segmentHeight: 5
    property bool dimmed: false
    property string accent: ""
    readonly property bool pixel: Plasmoid.configuration.theme === 0

    implicitWidth: pixel ? pixelBar.implicitWidth : (segments * (segmentWidth + 1) - 1) * unit
    implicitHeight: pixel ? pixelBar.implicitHeight : Math.max(3, Math.round(segmentHeight * unit * 0.55))

    PixelBar {
        id: pixelBar
        visible: b.pixel
        value: b.value
        level: b.level
        segments: b.pixel ? b.segments : 0
        unit: b.unit
        segmentWidth: b.segmentWidth
        segmentHeight: b.segmentHeight
        dimmed: b.dimmed
    }

    Rectangle {
        id: track
        visible: !b.pixel
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: b.implicitHeight
        radius: height / 2
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.14)
        opacity: b.dimmed ? 0.5 : 1

        Rectangle {
            height: parent.height
            radius: parent.radius
            width: b.value <= 0 ? 0 : Math.max(height, parent.width * Math.min(100, b.value) / 100)
            color: Palette.forLevel(b.level, Plasmoid.configuration.theme, b.accent)
            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
        }
    }
}
