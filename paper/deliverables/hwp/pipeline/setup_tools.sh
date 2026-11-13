#!/usr/bin/env bash
# Build the tool directory the report pipeline needs, outside the repository.
#
# usage: setup_tools.sh <tooldir>
#
# 1. claw-hwp (MIT, https://github.com/DoHyun468/claw-hwp) at the pinned commit, scripts only,
#    with claw-hwp-image.patch applied (large images through the regular FAT, cell.before_para,
#    picture geometry). The upstream file is checked against its git blob id before patching.
# 2. @rhwp/core 0.9.0 from npm with the pinned integrity hash (independent renderer; the bundled
#    0.7.x does not draw pictures inside cells).
# 3. A Python venv with cairosvg 2.9.1 for the approximate PDF.
# Nothing in the repository or the system is changed. Network access: codeload.github.com,
# registry.npmjs.org, PyPI.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="$(realpath -m "$1")"
UPSTREAM_REPO=DoHyun468/claw-hwp
UPSTREAM_COMMIT=eadf86fb713b5f9152fdf61520c6b60363a74222
CELL_PATCH_BLOB=82af912a3c9ccaa89f077dc6c18fcd4a95237bef
RHWP_VERSION=0.9.0
RHWP_INTEGRITY='sha512-dEe9gtEM5QXAoJjX+fwgbN5KIo0a6X/wgwEg0LDcq9oY1ga5lD5vNkediFSSX4Xxs8VfFk//dbk71aMQ8J1uAQ=='

mkdir -p "$dest"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

echo "== claw-hwp $UPSTREAM_COMMIT"
curl -fsSL "https://codeload.github.com/$UPSTREAM_REPO/tar.gz/$UPSTREAM_COMMIT" -o "$tmp/claw.tgz"
mkdir "$tmp/claw" && tar -xzf "$tmp/claw.tgz" -C "$tmp/claw" --strip-components=1
src="$tmp/claw/plugins/claw-hwp/skills/hwp/scripts/cell-patch.js"
blob=$(python3 -I -c 'import hashlib,sys; d=open(sys.argv[1],"rb").read(); print(hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest())' "$src")
[ "$blob" = "$CELL_PATCH_BLOB" ] || { echo "upstream cell-patch.js blob $blob != $CELL_PATCH_BLOB" >&2; exit 1; }
(cd "$tmp/claw" && patch -p1 --no-backup-if-mismatch < "$here/claw-hwp-image.patch")
rm -rf "$dest/claw-hwp"; mkdir -p "$dest/claw-hwp"
cp -r "$tmp/claw/plugins/claw-hwp/skills/hwp/scripts" "$dest/claw-hwp/scripts"
cp "$tmp/claw/LICENSE" "$dest/claw-hwp/LICENSE" 2>/dev/null || cp "$tmp/claw/plugins/claw-hwp/LICENSE" "$dest/claw-hwp/LICENSE"
echo "$UPSTREAM_COMMIT + claw-hwp-image.patch" > "$dest/claw-hwp/VERSION"

echo "== @rhwp/core $RHWP_VERSION"
mkdir -p "$dest/rhwp"
(cd "$dest/rhwp" && npm pack --silent "@rhwp/core@$RHWP_VERSION" > /dev/null)
got=$(node -e 'const c=require("crypto"),f=require("fs");console.log("sha512-"+c.createHash("sha512").update(f.readFileSync(process.argv[1])).digest("base64"))' "$dest/rhwp/rhwp-core-$RHWP_VERSION.tgz")
[ "$got" = "$RHWP_INTEGRITY" ] || { echo "@rhwp/core integrity mismatch" >&2; exit 1; }
rm -rf "$dest/rhwp/core" && mkdir "$dest/rhwp/core"
tar -xzf "$dest/rhwp/rhwp-core-$RHWP_VERSION.tgz" -C "$dest/rhwp/core" --strip-components=1

echo "== python venv (cairosvg)"
python3 -m venv "$dest/venv"
"$dest/venv/bin/pip" install -q cairosvg==2.9.1 olefile==0.47

echo "tools ready in $dest"
