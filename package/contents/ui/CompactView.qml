/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

import "Format.js" as Format

MouseArea {
    id: compact

    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
    readonly property bool rings: root.theme === 2
    readonly property var groups: root.panelGroups
    readonly property bool showIcon: Plasmoid.configuration.showIcon
    readonly property bool showPercent: Plasmoid.configuration.showPercent
    readonly property int segments: Math.max(3, Plasmoid.configuration.panelSegments)

    readonly property int maxRows: {
        let n = 1
        for (const g of groups) n = Math.max(n, g.limits.length)
        return n
    }

    // Font pixels needed to stack each provider's limits on their own lines.
    readonly property int stackedHeight: Math.max(maxRows * 5 + (maxRows - 1) * 2 + 2, 9)

    // 0 = auto, 1 = stacked, 2 = side by side. Auto stacks only when the
    // panel is thick enough to keep the text readable (3px per font pixel);
    // thin panels get one row. Rings always sit side by side.
    readonly property bool inline: {
        if (vertical || maxRows < 2) return false
        if (rings) return true
        const mode = Plasmoid.configuration.panelLayout
        if (mode === 1) return false
        if (mode === 2) return true
        return Math.floor(height / stackedHeight) < 3
    }

    // Base size unit in screen pixels (one font pixel in the pixel theme),
    // chosen so everything fits the panel thickness.
    readonly property int unit: {
        if (vertical)
            return Math.max(1, Math.floor(width / 16))
        return Math.max(1, Math.floor(height / (inline || rings || maxRows < 2 ? 9 : stackedHeight)))
    }
    // System-font themes stop growing past a comfortable panel text size.
    readonly property real fontSize: Math.min(unit * 5.2, 16)
    readonly property real logoSize: Math.min(height - 2, unit * 8, root.theme === 0 ? 999 : 22)

    function cellsFor(limits) {
        const out = []
        limits.forEach((l, i) => {
            if (inline && i > 0) out.push({ kind: "gap", limit: l })
            out.push({ kind: "label", limit: l })
            out.push({ kind: "meter", limit: l })
            if (showPercent) out.push({ kind: "pct", limit: l })
        })
        return out
    }
    readonly property int cellsPerRow: showPercent ? 3 : 2

    Layout.minimumWidth: vertical ? -1 : content.implicitWidth + unit * 2
    Layout.preferredWidth: Layout.minimumWidth
    Layout.minimumHeight: vertical ? content.implicitHeight + unit * 2 : -1
    Layout.preferredHeight: Layout.minimumHeight

    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
    hoverEnabled: true
    onClicked: mouse => {
        if (mouse.button === Qt.MiddleButton)
            root.refresh()
        else
            root.expanded = !root.expanded
    }

    // Widest percentage, so numbers don't shift the layout as they change.
    UText {
        id: pctProbe
        visible: false
        text: "100%"
        unit: compact.unit
        fontSize: compact.fontSize
        bold: root.theme !== 0
    }

    Loader {
        id: content
        anchors.centerIn: parent
        sourceComponent: compact.vertical ? verticalLayout : horizontalLayout
    }

    Component {
        id: meterCell
        Item {
            id: mc
            property var limit
            implicitWidth: meter.item ? meter.item.implicitWidth : 0
            implicitHeight: meter.item ? meter.item.implicitHeight : 0
            Loader {
                id: meter
                anchors.centerIn: parent
                active: !!mc.limit
                sourceComponent: compact.rings ? ringMeter : barMeter
            }
            Component {
                id: ringMeter
                Ring {
                    size: Math.min(compact.unit * 7, 26)
                    value: root.shownValue(mc.limit)
                    level: mc.limit.used
                    accent: mc.limit.accent || ""
                    dimmed: false
                }
            }
            Component {
                id: barMeter
                UBar {
                    width: implicitWidth
                    value: root.shownValue(mc.limit)
                    level: mc.limit.used
                    segments: compact.segments
                    unit: compact.unit
                    segmentWidth: 1
                    accent: mc.limit.accent || ""
                    dimmed: false
                }
            }
        }
    }

    Component {
        id: gapCell
        Item { property var limit; implicitWidth: compact.unit; implicitHeight: 1 }
    }

    Component {
        id: labelCell
        UText {
            property var limit
            text: limit ? limit.short : ""
            unit: compact.unit
            fontSize: compact.fontSize
            opacity: 0.75
        }
    }

    Component {
        id: pctCell
        Item {
            id: pc
            property var limit
            implicitWidth: pctProbe.implicitWidth
            implicitHeight: pctProbe.implicitHeight
            UText {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: pc.limit ? Format.percent(root.shownValue(pc.limit)) : ""
                unit: compact.unit
                fontSize: compact.fontSize
                bold: root.theme !== 0
            }
        }
    }

    Component {
        id: horizontalLayout
        Row {
            spacing: compact.unit * 5

            // Nothing detected yet: a dim generic mark keeps the widget clickable.
            ProviderLogo {
                visible: compact.groups.length === 0
                provider: "generic"
                size: compact.logoSize
                anchors.verticalCenter: parent.verticalCenter
                opacity: 0.5
            }

            Repeater {
                model: compact.groups
                Row {
                    id: group
                    required property var modelData
                    readonly property bool stale: modelData.provider.stale
                    spacing: compact.unit * 2
                    anchors.verticalCenter: parent.verticalCenter
                    opacity: stale ? 0.55 : 1

                    ProviderLogo {
                        visible: compact.showIcon || group.modelData.limits.length === 0
                        provider: group.modelData.provider.id
                        size: compact.logoSize
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Grid {
                        visible: group.modelData.limits.length > 0
                        anchors.verticalCenter: parent.verticalCenter
                        columns: compact.inline ? Math.max(1, cells.length) : compact.cellsPerRow
                        rowSpacing: compact.unit * 2
                        columnSpacing: compact.unit * 2
                        verticalItemAlignment: Grid.AlignVCenter
                        readonly property var cells: compact.cellsFor(group.modelData.limits)

                        Repeater {
                            model: parent.cells
                            Loader {
                                required property var modelData
                                sourceComponent: {
                                    switch (modelData.kind) {
                                    case "gap": return gapCell
                                    case "label": return labelCell
                                    case "meter": return meterCell
                                    default: return pctCell
                                    }
                                }
                                onLoaded: item.limit = modelData.limit
                            }
                        }
                    }

                    // Providers without plan limits (API keys) show today's tokens.
                    UText {
                        visible: group.modelData.limits.length === 0
                        anchors.verticalCenter: parent.verticalCenter
                        text: group.modelData.provider.tokens_today ? Format.tokens(group.modelData.provider.tokens_today.total) : ""
                        unit: compact.unit
                        fontSize: compact.fontSize
                    }
                }
            }
        }
    }

    Component {
        id: verticalLayout
        Column {
            spacing: compact.unit * 4

            ProviderLogo {
                visible: compact.groups.length === 0
                provider: "generic"
                size: Math.min(compact.width - 2, compact.unit * 9)
                anchors.horizontalCenter: parent.horizontalCenter
                opacity: 0.5
            }

            Repeater {
                model: compact.groups
                Column {
                    id: vgroup
                    required property var modelData
                    spacing: compact.unit * 2
                    anchors.horizontalCenter: parent.horizontalCenter
                    opacity: modelData.provider.stale ? 0.55 : 1

                    ProviderLogo {
                        provider: vgroup.modelData.provider.id
                        size: Math.min(compact.width - 2, compact.unit * 9)
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Repeater {
                        model: vgroup.modelData.limits
                        Column {
                            id: vrow
                            required property var modelData
                            spacing: compact.unit
                            anchors.horizontalCenter: parent.horizontalCenter

                            UText {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: vrow.modelData.short
                                unit: compact.unit
                                fontSize: compact.fontSize
                                opacity: 0.75
                            }
                            Loader {
                                anchors.horizontalCenter: parent.horizontalCenter
                                sourceComponent: meterCell
                                onLoaded: item.limit = vrow.modelData
                            }
                            UText {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: Math.round(root.shownValue(vrow.modelData)) + (compact.showPercent ? "%" : "")
                                unit: compact.unit
                                fontSize: compact.fontSize
                                bold: root.theme !== 0
                            }
                        }
                    }

                    UText {
                        visible: vgroup.modelData.limits.length === 0
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: vgroup.modelData.provider.tokens_today ? Format.tokens(vgroup.modelData.provider.tokens_today.total) : ""
                        unit: compact.unit
                        fontSize: compact.fontSize
                    }
                }
            }
        }
    }
}
