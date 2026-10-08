/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

.pragma library

var CLAUDE = "#d97757"

// Pixel theme: Sweetie 16 inspired.
var GREEN = "#38b764"
var YELLOW = "#ffcd75"
var ORANGE = "#ef7d57"
var RED = "#e43b44"

// Modern / ring themes: Claude coral until the limit gets tight.
var AMBER = "#f0a04b"
var CRIMSON = "#e5484d"

// `accent` is the provider's brand colour, used by the modern / ring themes
// while the limit is comfortable.
function forLevel(used, theme, accent) {
    if (theme === 1 || theme === 2) {
        if (used >= 90) return CRIMSON
        if (used >= 75) return AMBER
        return accent ? accent : CLAUDE
    }
    if (used >= 90) return RED
    if (used >= 75) return ORANGE
    if (used >= 50) return YELLOW
    return GREEN
}
