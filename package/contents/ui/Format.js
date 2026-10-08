/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

.pragma library

// Compact duration like "2d 4h", "3h 12m", "45m", "<1m".
function duration(ms) {
    if (ms === null || ms === undefined || ms < 0) return ""
    var m = Math.floor(ms / 60000)
    if (m < 1) return "<1m"
    var d = Math.floor(m / 1440)
    var h = Math.floor((m % 1440) / 60)
    var mm = m % 60
    if (d > 0) return d + "d " + h + "h"
    if (h > 0) return h + "h " + mm + "m"
    return mm + "m"
}

function tokens(n) {
    if (!n) return "0"
    if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e10 ? 0 : 1) + "B"
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M"
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "K"
    return String(n)
}

function percent(v) {
    return Math.round(v) + "%"
}
