/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import org.kde.plasma.plasmoid
import QtQuick.Shapes
import org.kde.kirigami as Kirigami

import "Palette.js" as Palette

// Circular gauge for the ring theme.
Item {
    id: ring

    property real value: 0
    property real level: value
    property real size: 24
    property real thickness: Math.max(2, Math.round(size * 0.14))
    property bool dimmed: false
    property string accent: ""

    readonly property real radius: (size - thickness) / 2
    property real sweep: 360 * Math.max(0, Math.min(100, value)) / 100

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size
    opacity: dimmed ? 0.5 : 1

    Behavior on sweep { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.14)
            strokeWidth: ring.thickness
            PathAngleArc {
                centerX: ring.size / 2
                centerY: ring.size / 2
                radiusX: ring.radius
                radiusY: ring.radius
                startAngle: 0
                sweepAngle: 360
            }
        }

        ShapePath {
            fillColor: "transparent"
            strokeColor: ring.sweep > 0 ? Palette.forLevel(ring.level, Plasmoid.configuration.theme, ring.accent) : "transparent"
            strokeWidth: ring.thickness
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: ring.size / 2
                centerY: ring.size / 2
                radiusX: ring.radius
                radiusY: ring.radius
                startAngle: -90
                sweepAngle: ring.sweep
            }
        }
    }
}
