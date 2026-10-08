/*
    SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
    SPDX-License-Identifier: GPL-3.0-or-later
*/

.pragma library

// Claude spark: twelve tapered rays of uneven length around a solid centre.
// [angle in degrees, length as a fraction of the radius]
var RAYS = [
    [-90, 1.00], [-60, 0.80], [-31, 0.94], [0, 0.82], [30, 1.00], [61, 0.78],
    [90, 0.92], [119, 0.86], [150, 1.00], [180, 0.80], [210, 0.93], [240, 0.84]
]
var ROOT_HALF_WIDTH = 0.12
var TIP_HALF_WIDTH = 0.055

// The same mark hand-fitted to a 13x13 grid for the pixel theme.
var SPRITE = [
    "0000001000000",
    "0001001001000",
    "0000101010000",
    "0000101010010",
    "0011011101100",
    "0000111110000",
    "1111111111111",
    "0000111110000",
    "0011011101100",
    "0100101010010",
    "0000101010000",
    "0001001001000",
    "0000001000000"
]

function f(n) {
    return Math.round(n * 100) / 100
}

// SVG path data for the vector mark inside a size x size box.
function svgPath(size) {
    var c = size / 2
    var R = size / 2
    var d = ""
    for (var i = 0; i < RAYS.length; i++) {
        var t = RAYS[i][0] * Math.PI / 180
        var L = RAYS[i][1] * (R - TIP_HALF_WIDTH * R)
        var ux = Math.cos(t), uy = Math.sin(t)
        var px = -uy, py = ux
        var w0 = ROOT_HALF_WIDTH * R, w1 = TIP_HALF_WIDTH * R
        var tx = c + ux * L, ty = c + uy * L
        d += "M" + f(c + px * w0) + " " + f(c + py * w0)
        d += " L" + f(tx + px * w1) + " " + f(ty + py * w1)
        d += " A" + f(w1) + " " + f(w1) + " 0 0 0 " + f(tx - px * w1) + " " + f(ty - py * w1)
        d += " L" + f(c - px * w0) + " " + f(c - py * w0) + " Z "
    }
    return d
}
