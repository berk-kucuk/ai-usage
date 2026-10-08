/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

import "Brands.js" as Brands
import "Format.js" as Format
import "Palette.js" as Palette

Item {
    id: full

    readonly property bool pixel: root.theme === 0
    readonly property bool rings: root.theme === 2

    // Pixel theme: logical px per font pixel (Plasma scales these on HiDPI).
    readonly property int u: 2
    // Other themes: font sizes derived from the system font.
    readonly property real fs: Math.round(fm.height * 0.75)

    readonly property color dim: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.6)
    readonly property int gap: pixel ? u * 6 : Kirigami.Units.largeSpacing

    Layout.preferredWidth: pixel ? u * 150 : Kirigami.Units.gridUnit * 18
    Layout.minimumWidth: pixel ? u * 120 : Kirigami.Units.gridUnit * 15
    Layout.preferredHeight: Math.min(body.implicitHeight + gap * 2, Kirigami.Units.gridUnit * 36)
    Layout.minimumHeight: Math.min(body.implicitHeight + gap * 2, Kirigami.Units.gridUnit * 14)

    FontMetrics {
        id: fm
        font: Kirigami.Theme.defaultFont
    }

    function ago(ms) {
        if (!ms) return ""
        const d = root.now - ms
        return d < 60000 ? i18n("just now") : i18n("%1 ago", Format.duration(d))
    }

    function limitTitle(l) {
        return l.label + (root.showRemaining ? " · " + i18n("left") : "")
    }

    function sourceText(p) {
        if (!p.updated_at) return ""
        const age = ago(p.updated_at)
        if (p.estimated) return i18n("estimated")
        return p.stale ? i18n("old · %1", age) : age
    }

    component Divider: Item {
        Layout.fillWidth: true
        implicitHeight: full.pixel ? full.u : 1
        PixelRule {
            visible: full.pixel
            anchors.fill: parent
            u: full.u
        }
        Rectangle {
            visible: !full.pixel
            anchors.fill: parent
            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.12)
        }
    }

    // Small, normal and large text in both renderings.
    component Small: UText { unit: full.u; fontSize: full.fs * 0.9; color: full.dim }
    component Normal: UText { unit: full.u; fontSize: full.fs }
    component Large: UText { unit: full.u + 1; fontSize: full.fs * 1.5; bold: true }

    QQC2.ScrollView {
        anchors.fill: parent
        anchors.margins: full.gap
        contentWidth: availableWidth
        QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

        ColumnLayout {
            id: body
            width: parent.width
            spacing: full.gap

            // ── nothing detected ─────────────────────────────────
            Normal {
                visible: root.loading || root.providers.length === 0
                color: full.dim
                text: root.loading ? i18n("Loading…") : i18n("No coding agents detected")
            }

            Repeater {
                model: root.providers

                ColumnLayout {
                    id: section
                    required property var modelData
                    required property int index
                    readonly property var p: modelData
                    readonly property string accent: Brands.get(modelData.id).color
                    Layout.fillWidth: true
                    spacing: full.pixel ? full.u * 3 : Kirigami.Units.smallSpacing

                    Divider { visible: section.index > 0 }

                    // header: logo, name, plan, data age
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: full.pixel ? full.u * 3 : Kirigami.Units.smallSpacing * 2

                        ProviderLogo { provider: section.p.id; size: full.pixel ? 26 : full.fs * 1.6 }
                        UText { text: section.p.name; unit: full.u + 1; fontSize: full.fs * 1.15; bold: true }
                        Rectangle {
                            visible: !!section.p.plan
                            readonly property color brand: Brands.get(section.p.id).color || Kirigami.Theme.textColor
                            radius: full.pixel ? 0 : height / 2
                            color: full.pixel ? brand : Qt.rgba(brand.r, brand.g, brand.b, 0.18)
                            implicitWidth: planText.width + (full.pixel ? full.u * 4 : Kirigami.Units.largeSpacing * 1.5)
                            implicitHeight: planText.height + (full.pixel ? full.u * 4 : Kirigami.Units.smallSpacing)
                            UText {
                                id: planText
                                anchors.centerIn: parent
                                text: section.p.plan || ""
                                unit: full.u
                                fontSize: full.fs * 0.8
                                bold: true
                                color: full.pixel ? "#1a1c2c" : parent.brand
                            }
                        }
                        Item { Layout.fillWidth: true }
                        Small {
                            text: full.sourceText(section.p)
                            color: section.p.stale ? Palette.ORANGE : full.dim
                        }
                    }

                    // limits as bars (pixel / modern)
                    Repeater {
                        model: full.rings ? [] : section.p.limits
                        ColumnLayout {
                            id: limitRow
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: full.pixel ? full.u * 2 : 2

                            RowLayout {
                                Layout.fillWidth: true
                                Normal { text: full.limitTitle(limitRow.modelData); color: full.dim }
                                Item { Layout.fillWidth: true }
                                Small {
                                    visible: !!limitRow.modelData.resets_at
                                    text: limitRow.modelData.resets_at ? root.resetText(limitRow.modelData) : ""
                                }
                                Large {
                                    text: Format.percent(root.shownValue(limitRow.modelData))
                                    color: Palette.forLevel(limitRow.modelData.used, root.theme, section.accent)
                                    opacity: section.p.stale ? 0.5 : 1
                                }
                            }

                            Item {
                                id: barBox
                                Layout.fillWidth: true
                                implicitHeight: meter.implicitHeight
                                UBar {
                                    id: meter
                                    width: barBox.width
                                    unit: full.u
                                    segments: 24
                                    // pixel theme: stretch the segments to fill the width
                                    segmentWidth: Math.max(1, Math.floor((barBox.width / full.u + 1) / segments) - 1)
                                    segmentHeight: full.pixel ? 4 : 4
                                    value: root.shownValue(limitRow.modelData)
                                    level: limitRow.modelData.used
                                    accent: section.accent
                                    dimmed: section.p.stale
                                }
                            }
                        }
                    }

                    // limits as rings
                    Flow {
                        visible: full.rings && section.p.limits.length > 0
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing

                        Repeater {
                            model: full.rings ? section.p.limits : []
                            Column {
                                id: ringCell
                                required property var modelData
                                spacing: 2
                                width: Kirigami.Units.gridUnit * 4.5

                                Ring {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    size: Kirigami.Units.gridUnit * 3.6
                                    thickness: Math.max(4, Math.round(size * 0.1))
                                    value: root.shownValue(ringCell.modelData)
                                    level: ringCell.modelData.used
                                    accent: section.accent
                                    dimmed: section.p.stale

                                    Large {
                                        anchors.centerIn: parent
                                        text: Format.percent(root.shownValue(ringCell.modelData))
                                        fontSize: full.fs * 1.15
                                        color: Palette.forLevel(ringCell.modelData.used, root.theme, section.accent)
                                    }
                                }
                                Normal {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: ringCell.modelData.label
                                    width: Math.min(implicitWidth, parent.width)
                                }
                                Small {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    visible: text !== ""
                                    text: root.resetText(ringCell.modelData)
                                }
                            }
                        }
                    }

                    Small {
                        visible: !!(section.p.extra && (section.p.extra.used !== null && section.p.extra.used !== undefined || section.p.extra.text))
                        text: {
                            const e = section.p.extra
                            if (!e) return ""
                            return e.label + " " + (e.text ? e.text : Format.percent(e.used))
                        }
                    }

                    // today's tokens (and cost when the tool records it)
                    RowLayout {
                        visible: !!section.p.tokens_today
                        Layout.fillWidth: true
                        readonly property var t: section.p.tokens_today || ({})
                        Small { text: i18n("Today") }
                        Item { Layout.fillWidth: true }
                        Small {
                            text: i18n("%1 tokens", Format.tokens(parent.t.total))
                                  + (parent.t.cost ? " · $" + Number(parent.t.cost).toFixed(2) : "")
                            color: Kirigami.Theme.textColor
                        }
                    }

                    // signed in but nothing to show yet
                    Small {
                        visible: section.p.limits.length === 0 && !section.p.tokens_today
                        text: section.p.plan === "API" ? i18n("API key — no plan limits") : i18n("No usage yet")
                    }

                    // detected apps (Claude: Desktop / Code, others: CLI)
                    Row {
                        visible: (section.p.apps || []).length > 1
                        spacing: full.pixel ? full.u * 4 : Kirigami.Units.largeSpacing
                        Repeater {
                            model: section.p.apps || []
                            Row {
                                required property var modelData
                                spacing: full.pixel ? full.u * 2 : Kirigami.Units.smallSpacing
                                Rectangle {
                                    readonly property int d: full.pixel ? full.u * 2 : 6
                                    width: d
                                    height: d
                                    radius: full.pixel ? 0 : d / 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: modelData.running ? (full.pixel ? Palette.GREEN : "#3fb950") : full.dim
                                }
                                Small { text: modelData.name }
                            }
                        }
                    }
                }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.MiddleButton
        onClicked: root.refresh()
    }
}
