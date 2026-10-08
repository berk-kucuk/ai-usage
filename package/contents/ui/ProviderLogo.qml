/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import QtQuick.Shapes
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

import "Brands.js" as Brands

// Provider mark: 13x13 sprite with whole-pixel cells in the pixel theme,
// a vector path otherwise.
Item {
    id: logo

    property string provider: "generic"
    property real size: 16
    property bool pixel: Plasmoid.configuration.theme === 0

    readonly property var brand: Brands.get(provider)
    readonly property color color: brand.color || Kirigami.Theme.textColor
    readonly property int cell: Math.max(1, Math.round(size / 13))

    implicitWidth: pixel ? cell * 13 : size
    implicitHeight: implicitWidth
    width: implicitWidth
    height: implicitHeight

    Grid {
        visible: logo.pixel
        columns: 13
        Repeater {
            model: logo.pixel ? logo.brand.sprite.join("").split("") : []
            Rectangle {
                required property string modelData
                width: logo.cell
                height: logo.cell
                antialiasing: false
                color: modelData === "1" ? logo.color : "transparent"
            }
        }
    }

    Shape {
        visible: !logo.pixel
        width: 24
        height: 24
        scale: logo.size / 24
        transformOrigin: Item.TopLeft
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: logo.brand.stroke ? "transparent" : logo.color
            strokeColor: logo.brand.stroke ? logo.color : "transparent"
            strokeWidth: logo.brand.stroke || 0
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            fillRule: logo.brand.evenOdd ? ShapePath.OddEvenFill : ShapePath.WindingFill
            PathSvg { path: logo.pixel ? "" : logo.brand.path }
        }
    }
}
