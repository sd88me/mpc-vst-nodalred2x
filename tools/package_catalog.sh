#!/usr/bin/env bash
# The release zips, from the release build (build/sdk/"sd88me - VST - NodalRed2x", made by ./build-sdk.sh):
#   dist/NodalRed2x-<ver>-mpc-aarch64.zip   install.sh / uninstall.sh (MPC.settings) for 64-bit MPCs, made by mpc-vst-plugins' tools/release.py;
#                                      it upgrades a 0.1.0 install in place
#   dist/NodalRed2x-<ver>-mpc-sdk.zip       the plugin folder for "VST2 Plugins" (tools/sdk_zip.py)
#   dist/NodalRed2x-<ver>-SHA256SUMS.txt
# As in 0.1.0 the .so is nodalred2x.so at the folder root (plugin.json names it, so the plugin finds its folder and nodalred2x/ beside it).
# User data, kept on upgrade and uninstall: nodalred2x/roms (your ROM), nodalred2x/banks (your sound sets), nodalred2x/favourites.dat,  No ROM or sound set is ever packed.
# MPC_VST: mpc-vst-plugins with tools/release.py and tools/sdk_zip.py.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins-postlaunch}"
[ -f "$MPC_VST/tools/release.py" ] && [ -f "$MPC_VST/tools/sdk_zip.py" ] || { echo "need mpc-vst-plugins with tools/sdk_zip.py (MPC_VST)" >&2; exit 1; }
DIR="sd88me - VST - NodalRed2x"; SRC="$here/build/sdk/$DIR"
[ -f "$SRC/VST/nodalred2x-arm64.so" ] || { echo "missing $SRC: run ./build-sdk.sh first" >&2; exit 1; }
VER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$SRC/plugin.json")
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m["uid"]=="NodR" and "Beta" not in m["name"] else "not the release identity")' "$SRC/plugin.json"
out="$here/dist"; mkdir -p "$out"
st="$here/build/catalog/aarch64"; rm -rf "$st"; mkdir -p "$st/$DIR" "$st/extra"
cp -r "$SRC/Plugin Skins" "$SRC/version.xml" "$st/$DIR/"
python3 - "$SRC/plugin.json" "$st/$DIR/plugin.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m.pop("file32", None)
m["file64"] = "nodalred2x.so"
json.dump(m, open(sys.argv[2], "w"), indent=2)
PY
cp "$SRC/VST/nodalred2x-arm64.so" "$st/nodalred2x.so"
cp -r "$here/release/nodalred2x/." "$st/extra/"; cp "$here/LICENSE" "$here/CREDITS.md" "$st/extra/"
# nothing of the user's may ride along: only the placeholders
if find "$st" -type f | grep -v -E 'PUT_(NORDLEAD2X_ROM|SOUND_SETS)_HERE\.txt$' | grep -i -E '/(roms|banks)/|\.(bin|syx|mid)$|favourites'; then
  echo "refusing: user files in the package" >&2; exit 1
fi
printf '<PLUGIN name="NodalRed2x" descriptiveName="NodalRed2x" format="VST" category="Synth" manufacturer="sd88me" version="%s" file="nodalred2x.so" uid="4e6f6452" isInstrument="1" fileTime="0" infoUpdateTime="0" numInputs="0" numOutputs="2" isShell="0"/>\n' "$VER" > "$st/entry.xml"
python3 "$MPC_VST/tools/release.py" --so "$st/nodalred2x.so" --skin "$st/$DIR" --entry "$st/entry.xml" --version "$VER" --extra "$st/extra:nodalred2x" \
  --user-data nodalred2x/roms --user-data nodalred2x/banks --user-data nodalred2x/favourites.dat \
  --user-files "$here/release/userfiles.json" \
  --repo sd88me/mpc-vst-nodalred2x --license GPL-3.0-only --id nodalred2x \
  --requires "64-bit MPC (Live III and others) and your own Nord Lead 2x ROM" \
  --about "Clavia Nord Lead 2x emulation (gearmulator) with a native MPC panel, a starter bank plus your own sound sets, RANDOM and named favourites." \
  -o "$st/dist"
z=$(ls "$st/dist"/*.zip); cp "$z" "$out/NodalRed2x-$VER-mpc-aarch64.zip"
python3 "$here/tools/scrub_zip.py" "$out/NodalRed2x-$VER-mpc-aarch64.zip"
python3 "$MPC_VST/tools/catalog_check.py" "$out/NodalRed2x-$VER-mpc-aarch64.zip" --catalog --require-portable --expect-id nodalred2x --expect-repo sd88me/mpc-vst-nodalred2x
python3 "$MPC_VST/tools/sdk_zip.py" "$out/NodalRed2x-$VER-mpc-sdk.zip" "$out/NodalRed2x-$VER-mpc-aarch64.zip"
for f in "$out/NodalRed2x-$VER-mpc-aarch64.zip" "$out/NodalRed2x-$VER-mpc-sdk.zip"; do   # last guard: no ROM-like file in either zip
  if python3 -I -m zipfile -l "$f" | grep -i -E '\.(bin|syx|rom)\b|\.mid\b|favourites' | grep -v PUT_; then echo "refusing: a user or ROM-like file in $f" >&2; exit 1; fi
done
(cd "$out" && sha256sum "NodalRed2x-$VER-mpc-aarch64.zip" "NodalRed2x-$VER-mpc-sdk.zip" > "NodalRed2x-$VER-SHA256SUMS.txt")
ls -la "$out"/NodalRed2x-"$VER"-*
