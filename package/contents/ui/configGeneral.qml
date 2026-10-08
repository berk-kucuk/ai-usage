/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page

    property alias cfg_theme: themeBox.currentIndex
    property alias cfg_refreshSeconds: refresh.value
    property string cfg_hiddenProviders
    property string cfg_panelKinds
    property alias cfg_panelMaxPerProvider: maxPerProvider.value
    property alias cfg_showTokenOnlyProviders: showTokenOnly.checked
    property alias cfg_panelSegments: segments.value
    property alias cfg_panelLayout: layoutBox.currentIndex
    property alias cfg_showIcon: showIcon.checked
    property alias cfg_showPercent: showPercent.checked
    property alias cfg_displayRemaining: displayRemaining.checked

    readonly property var providerChoices: [
        { id: "claude", text: "Claude (Code, Desktop)" },
        { id: "codex", text: "Codex" },
        { id: "gemini", text: "Gemini CLI" },
        { id: "copilot", text: "GitHub Copilot" },
        { id: "opencode", text: "OpenCode" }
    ]

    readonly property var kindChoices: [
        { id: "session", text: i18n("Session (5-hour)") },
        { id: "daily", text: i18n("Daily") },
        { id: "weekly", text: i18n("Weekly") },
        { id: "monthly", text: i18n("Monthly") }
    ]

    function listHas(list, id) {
        return list.split(",").indexOf(id) !== -1
    }

    function listSet(list, id, on, order) {
        let ids = list.split(",").filter(s => s && s !== id)
        if (on) ids.push(id)
        if (order)
            ids.sort((a, b) => order.findIndex(c => c.id === a) - order.findIndex(c => c.id === b))
        return ids.join(",")
    }

    Kirigami.FormLayout {
        QQC2.ComboBox {
            id: themeBox
            Kirigami.FormData.label: i18n("Theme:")
            model: [i18n("Pixel"), i18n("Modern"), i18n("Rings")]
        }

        Item { Kirigami.FormData.isSection: true }

        Repeater {
            model: page.providerChoices
            QQC2.CheckBox {
                required property var modelData
                required property int index
                Kirigami.FormData.label: index === 0 ? i18n("Show when detected:") : ""
                text: modelData.text
                checked: !page.listHas(page.cfg_hiddenProviders, modelData.id)
                onToggled: page.cfg_hiddenProviders = page.listSet(page.cfg_hiddenProviders, modelData.id, !checked)
            }
        }

        QQC2.CheckBox {
            id: showTokenOnly
            text: i18n("Show token totals for agents without plan limits")
        }

        Item { Kirigami.FormData.isSection: true }

        Repeater {
            model: page.kindChoices
            QQC2.CheckBox {
                required property var modelData
                required property int index
                Kirigami.FormData.label: index === 0 ? i18n("Limits in panel:") : ""
                text: modelData.text
                checked: page.listHas(page.cfg_panelKinds, modelData.id)
                onToggled: page.cfg_panelKinds = page.listSet(page.cfg_panelKinds, modelData.id, checked, page.kindChoices)
            }
        }

        QQC2.SpinBox {
            id: maxPerProvider
            Kirigami.FormData.label: i18n("Limits per agent:")
            from: 1
            to: 3
        }

        QQC2.ComboBox {
            id: layoutBox
            Kirigami.FormData.label: i18n("Panel layout:")
            model: [
                i18n("Automatic (side by side on thin panels)"),
                i18n("Stacked"),
                i18n("Side by side")
            ]
        }

        QQC2.SpinBox {
            id: segments
            Kirigami.FormData.label: i18n("Panel bar segments:")
            from: 3
            to: 20
        }

        QQC2.CheckBox {
            id: showIcon
            Kirigami.FormData.label: i18n("Panel:")
            text: i18n("Show agent icons")
        }

        QQC2.CheckBox {
            id: showPercent
            text: i18n("Show percentage")
        }

        QQC2.CheckBox {
            id: displayRemaining
            text: i18n("Show remaining instead of used")
        }

        Item { Kirigami.FormData.isSection: true }

        QQC2.SpinBox {
            id: refresh
            Kirigami.FormData.label: i18n("Refresh every:")
            from: 15
            to: 3600
            stepSize: 15
            textFromValue: (v) => i18np("%1 second", "%1 seconds", v)
            valueFromText: (t) => parseInt(t)
        }
    }
}
