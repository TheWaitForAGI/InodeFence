"""Generate or verify a SHA-256 manifest of a raw-evidence tree.

Raw evidence (``~/inodefence-evidence/``, per host) is never committed. A manifest
is the committed, checkable record that the raw bytes existed and were not altered:
one ``sha256sum``-format line per file (``<hex>  ./<relative-path>``), sorted by
path and relative to the evidence root. The format is byte-compatible with the mac
manifest ``experiments/summaries/raw-manifest-mac-20261103.sha256`` so a single
verifier reads both, and so ``sha256sum --check`` can read it from the evidence root.

Generate (walks the tree read-only and writes a manifest; never touches raw bytes):

    python scripts/make_raw_manifest.py --root ~/inodefence-evidence \\
        --host win --date 20261104

Verify (re-hash the tree against an existing manifest; read-only):

    python scripts/make_raw_manifest.py --verify \\
        experiments/summaries/raw-manifest-win-20261104.sha256 \\
        --root ~/inodefence-evidence

The verifier reports ok/mismatched/missing counts and exits non-zero if any file
fails or is absent. Extra files present in the tree but absent from the manifest are
reported as a warning (they do not fail verification on their own).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

#: ``<64 hex>`` then one space, then a text (`` ``) or binary (``*``) mode marker.
MANIFEST_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
_READ_CHUNK = 1 << 20


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_regular_files(root: Path, exclude_suffixes: tuple[str, ...] = ()) -> Iterator[Path]:
    """Yield every regular file under ``root`` (no symlinks), sorted by path.

    ``exclude_suffixes`` drops files whose name ends with any given suffix (e.g.
    ``.sha256``), so an evidence manifest does not checksum other manifests left in
    the tree. The default excludes nothing, preserving prior behavior.
    """
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        if exclude_suffixes and path.name.endswith(exclude_suffixes):
            continue
        yield path


def manifest_lines(root: Path, exclude_suffixes: tuple[str, ...] = ()) -> list[str]:
    """Build the sorted ``sha256sum``-format manifest lines for ``root``."""
    lines: list[str] = []
    for path in iter_regular_files(root, exclude_suffixes):
        relative = path.relative_to(root).as_posix()
        lines.append(f"{hash_file(path)}  ./{relative}\n")
    return lines


def parse_manifest(text: str) -> list[tuple[str, str]]:
    """Parse manifest text into ``(digest, relative-path)`` pairs.

    Accepts the ``sha256sum`` text (``  ``) and binary (`` *``) markers, and a
    leading ``./`` on the path. Blank lines are skipped; any other line raises.
    """
    entries: list[tuple[str, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        match = MANIFEST_LINE.match(raw)
        if match is None:
            raise ValueError(f"line {number}: not a sha256sum manifest line: {raw!r}")
        digest, name = match[1].lower(), match[2]
        entries.append((digest, name.removeprefix("./")))
    return entries


@dataclass(slots=True)
class VerifyResult:
    """Outcome of checking a manifest against a tree."""

    ok: int = 0
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.mismatched or self.missing)


def verify_manifest(
    manifest_path: Path, root: Path, exclude_suffixes: tuple[str, ...] = ()
) -> VerifyResult:
    """Re-hash ``root`` against ``manifest_path`` and report every discrepancy.

    ``exclude_suffixes`` is applied to the extra-file scan so files the manifest was
    built to skip (e.g. ``.sha256``) are not reported as extra.
    """
    entries = parse_manifest(manifest_path.read_text(encoding="utf-8"))
    result = VerifyResult()
    listed = {name for _, name in entries}
    for digest, name in entries:
        target = root / name
        if not target.is_file():
            result.missing.append(name)
        elif hash_file(target) == digest:
            result.ok += 1
        else:
            result.mismatched.append(name)
    for path in iter_regular_files(root, exclude_suffixes):
        name = path.relative_to(root).as_posix()
        if name not in listed:
            result.extra.append(name)
    return result


def default_output(host: str, date: str) -> Path:
    """Canonical committed location for a host/date manifest."""
    return Path("experiments/summaries") / f"raw-manifest-{host}-{date}.sha256"


def _generate(args: argparse.Namespace) -> int:
    root = args.root.expanduser()
    if not root.is_dir():
        print(f"root is not a directory: {root}", file=sys.stderr)
        return 2
    out = args.out or default_output(args.host, args.date)
    lines = manifest_lines(root, tuple(args.exclude_suffix))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {len(lines)} entries to {out} (root {root})")
    return 0


def _verify(args: argparse.Namespace) -> int:
    manifest_path = args.verify
    if not manifest_path.is_file():
        print(f"manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    root = args.root.expanduser() if args.root else manifest_path.parent
    if not root.is_dir():
        print(f"root is not a directory: {root}", file=sys.stderr)
        return 2
    result = verify_manifest(manifest_path, root, tuple(args.exclude_suffix))
    for name in result.mismatched:
        print(f"MISMATCH {name}", file=sys.stderr)
    for name in result.missing:
        print(f"MISSING  {name}", file=sys.stderr)
    for name in result.extra:
        print(f"EXTRA    {name} (in tree, not in manifest)", file=sys.stderr)
    status = "FAIL" if result.failed else "OK"
    print(
        f"verify {status}: {result.ok} ok, {len(result.mismatched)} mismatched, "
        f"{len(result.missing)} missing, {len(result.extra)} extra (root {root})"
    )
    return 1 if result.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        type=Path,
        metavar="MANIFEST",
        help="verify an existing manifest against --root instead of generating one",
    )
    parser.add_argument("--root", type=Path, help="evidence tree root to hash")
    parser.add_argument("--host", help="short host label for the generated file name (e.g. win)")
    parser.add_argument("--date", help="YYYYMMDD for the generated file name")
    parser.add_argument("--out", type=Path, help="override the generated manifest path")
    parser.add_argument(
        "--exclude-suffix",
        action="append",
        default=[],
        metavar="SUFFIX",
        help="skip files ending with SUFFIX (repeatable), e.g. --exclude-suffix .sha256",
    )
    args = parser.parse_args(argv)

    if args.verify is not None:
        return _verify(args)
    if args.root is None or args.host is None or args.date is None:
        parser.error("generate mode requires --root, --host and --date")
    return _generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
