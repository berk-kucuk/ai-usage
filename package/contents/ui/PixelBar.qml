/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import org.kde.kirigami as Kirigami

import "Palette.js" as Palette

// Segmented meter. `value` is 0..100 and picks the fill; `level` (also
// 0..100, defaults to value) picks the colour, so a "remaining" display can
// still turn red as the limit fills up.
Row {
    id: bar

    property real value: 0
    property real level: value
    property int segments: 10
    property int unit: 2
    property int segmentWidth: 2
    property int segmentHeight: 5
    property bool dimmed: false

    readonly property int filled: value <= 0 ? 0 : Math.max(1, Math.min(segments, Math.round(value / 100 * segments)))
    readonly property color fillColor: Palette.forLevel(level)

    spacing: unit

    Repeater {
        model: bar.segments
        Rectangle {
            width: bar.segmentWidth * bar.unit
            height: bar.segmentHeight * bar.unit
            antialiasing: false
            color: index < bar.filled
                   ? bar.fillColor
                   : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.16)
            opacity: bar.dimmed ? 0.45 : 1
        }
    }
}
