/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as Plasma5Support

import "Brands.js" as Brands
import "Format.js" as Format

PlasmoidItem {
    id: root

    // Latest collector output (see contents/code/collector.py).
    property var usage: null
    property double now: Date.now()

    readonly property bool loading: usage === null
    readonly property bool showRemaining: Plasmoid.configuration.displayRemaining
    // 0 = pixel, 1 = modern, 2 = rings
    readonly property int theme: Plasmoid.configuration.theme

    readonly property var hiddenProviders: String(Plasmoid.configuration.hiddenProviders).split(",").filter(s => s)

    // Detected providers the user hasn't hidden, in collector order.
    readonly property var providers: usage && usage.providers
                                     ? usage.providers.filter(p => hiddenProviders.indexOf(p.id) === -1)
                                     : []

    // What the panel shows for each provider: the limit kinds the user picked
    // (e.g. 5-hour + weekly), falling back to the most used limit for
    // providers that only have other windows (Gemini daily, Copilot monthly).
    readonly property var panelKinds: String(Plasmoid.configuration.panelKinds).split(",").filter(s => s)
    readonly property var panelGroups: {
        const out = []
        const max = Math.max(1, Plasmoid.configuration.panelMaxPerProvider)
        for (const p of providers) {
            const lims = p.limits || []
            let pick = []
            for (const k of panelKinds)
                for (const l of lims)
                    if (l.kind === k && pick.length < max && pick.indexOf(l) === -1) pick.push(l)
            if (pick.length === 0 && lims.length > 0)
                pick = [lims.slice().sort((a, b) => b.used - a.used)[0]]
            const accent = Brands.get(p.id).color
            pick = pick.map(l => Object.assign({ accent: accent }, l))
            if (pick.length > 0 || (p.tokens_today && Plasmoid.configuration.showTokenOnlyProviders))
                out.push({ provider: p, limits: pick })
        }
        return out
    }

    readonly property string collectorPath: decodeURIComponent(Qt.resolvedUrl("../code/collector.py").toString().replace(/^file:\/\//, ""))
    readonly property string collectorCommand: "python3 '" + collectorPath.replace(/'/g, "'\\''") + "'"

    function shownValue(limit) {
        return showRemaining ? 100 - limit.used : limit.used
    }

    function resetText(limit) {
        if (!limit.resets_at) return ""
        return Format.duration(limit.resets_at - now)
    }

    function refresh() {
        executable.connectSource(collectorCommand)
    }

    Plasmoid.icon: "ai-usage"
    Plasmoid.status: !loading && providers.length === 0 ? PlasmaCore.Types.PassiveStatus : PlasmaCore.Types.ActiveStatus

    toolTipMainText: i18n("AI Usage")
    toolTipSubText: {
        if (loading) return i18n("Loading…")
        if (providers.length === 0) return i18n("No coding agents detected")
        return providers.map(p => {
            const parts = (p.limits || []).slice(0, 3).map(l => l.short + " " + Math.round(l.used) + "%")
            if (parts.length === 0 && p.tokens_today)
                parts.push(i18n("%1 tokens today", Format.tokens(p.tokens_today.total)))
            return p.name + (p.plan ? " (" + p.plan + ")" : "") + (parts.length ? ": " + parts.join(" · ") : "")
        }).join("\n")
    }

    // Bars in panels, the full card when placed on the desktop.
    preferredRepresentation: Plasmoid.formFactor === PlasmaCore.Types.Horizontal || Plasmoid.formFactor === PlasmaCore.Types.Vertical
                             ? compactRepresentation : fullRepresentation
    compactRepresentation: CompactView {}
    fullRepresentation: FullView {}

    Plasma5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source)
            const out = String(data["stdout"] || "").trim()
            if (!out) return
            try {
                root.usage = JSON.parse(out)
            } catch (e) {
                console.warn("ai-usage: bad collector output", e)
            }
        }
    }

    Timer {
        interval: Math.max(15, Plasmoid.configuration.refreshSeconds) * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: root.now = Date.now()
    }

    onExpandedChanged: if (root.expanded) root.refresh()

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Refresh")
            icon.name: "view-refresh"
            onTriggered: root.refresh()
        }
    ]
}
