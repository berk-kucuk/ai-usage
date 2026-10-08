# SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
# SPDX-License-Identifier: GPL-3.0-or-later
# Maintainer: berkkucukk <berkkucukk@proton.me>

pkgname=plasma6-applets-ai-usage
_appletid=com.github.berkkucukk.aiusage
pkgver=2.0.0
pkgrel=1
pkgdesc="KDE Plasma 6 widget showing plan limits for AI coding agents (Claude, Codex, Gemini CLI, Copilot, OpenCode)"
arch=('any')
license=('GPL-3.0-or-later')
depends=('plasma-workspace' 'python' 'libplasma' 'kirigami' 'kcmutils' 'plasma5support')
conflicts=('plasma6-applets-claude-pixel-usage')
replaces=('plasma6-applets-claude-pixel-usage')
source=()

# Built from the local checkout this PKGBUILD lives in.
package() {
    local src="$startdir/package"
    local dest="$pkgdir/usr/share/plasma/plasmoids/$_appletid"

    install -Dm644 "$src/metadata.json" "$dest/metadata.json"
    find "$src/contents" -type f | while read -r f; do
        install -Dm644 "$f" "$dest/${f#"$src/"}"
    done
    chmod 755 "$dest/contents/code/collector.py"

    install -Dm644 "$startdir/icons/ai-usage.svg" \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/ai-usage.svg"
    install -Dm644 "$startdir/README.md" "$pkgdir/usr/share/doc/$pkgname/README.md"
}
