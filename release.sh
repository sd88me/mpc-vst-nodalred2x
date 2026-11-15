#!/usr/bin/env bash
# Build the release zip (no ROMs in it) and check it against the plugin catalog's rules.
#   ./release.sh <version>            e.g. ./release.sh 0.2.3   -> dist/NodalRed2x-<version>-mpc-aarch64.zip
# Then publish it: gh release create v<version> dist/NodalRed2x-<version>-mpc-aarch64.zip --title "NodalRed2x <version>" --notes-file <notes>
# MPC_VST: checkout of mpc-vst-plugins (default ~/mpc-vst-plugins), on a branch with the skin tool's `vy=` (PR #550 or newer main).
set -euo pipefail
cd "$(dirname "$0")"
VER="${1:?usage: ./release.sh <version>}"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins}"
[ -n "${SKIP_BUILD:-}" ] || ./build.sh all
rm -rf "dist/NodalRed2x-$VER-mpc-aarch64.zip"
EXTRA="$(mktemp -d)"; trap 'rm -rf "$EXTRA"' EXIT
cp -r release/nodalred2x/. "$EXTRA/"; cp LICENSE CREDITS.md "$EXTRA/"        # the installed plugin folder carries its licence and credits
python3 "$MPC_VST/tools/release.py" --so vst/build/aarch64/nodalred2x.so --skin "vst/build/skin/sd88me - VST - NodalRed2x" \
  --entry vst/build/pluginlist-entry.xml --version "$VER" --extra "$EXTRA:nodalred2x" \
  --repo sd88me/mpc-vst-nodalred2x --license GPL-3.0-only --id nodalred2x --user-data nodalred2x/roms --user-data nodalred2x/banks --requires "your own Nord Lead 2x ROM" -o dist
python3 "$MPC_VST/tools/catalog_check.py" "dist/NodalRed2x-$VER-mpc-aarch64.zip" --catalog --expect-id nodalred2x --expect-repo sd88me/mpc-vst-nodalred2x
# the package must carry no ROM: refuse anything that looks like one
if python3 -I -m zipfile -l "dist/NodalRed2x-$VER-mpc-aarch64.zip" | grep -i -E '\.(bin|mid|syx|rom)\b' | grep -v "PUT_"; then
  echo "refusing: a ROM-like file is in the zip" >&2; exit 1
fi
echo "ok: dist/NodalRed2x-$VER-mpc-aarch64.zip"
