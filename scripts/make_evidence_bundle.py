"""Bundle a raw-evidence tree into one compressed archive, for off-host backup.

External backup is not done yet and *where* a bundle goes is a human gate. This tool
only builds the bundle locally and never uploads or transmits anything. It:

  * writes a deterministic ``tar`` archive of the raw tree (stdlib compression: gz by
    default, or xz/bz2), with normalized member metadata and a gzip timestamp of 0 so
    the same inputs always yield the same bytes,
  * embeds the raw tree's SHA-256 manifest inside the archive as
    ``.evidence-manifest.sha256`` (same format as ``make_raw_manifest.py``), so the
    bundle is self-describing,
  * computes the bundle file's own SHA-256 and writes it to a ``<bundle>.sha256`` sidecar,
  * ``--verify`` re-hashes every file *inside* the bundle against the embedded manifest.

Raw originals are only read, never modified. The bundle lands outside the repository
(default ``~/inodefence-evidence-bundles/``).

    python -m scripts.make_evidence_bundle --root ~/inodefence-evidence --host win
    python -m scripts.make_evidence_bundle --verify ~/inodefence-evidence-bundles/win-....tar.gz
"""

from __future__ import annotations

import argparse
import gzip
import io
import sys
import tarfile
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from pathlib import Path

from scripts.make_raw_manifest import iter_regular_files, manifest_lines, parse_manifest

#: Reserved archive member holding the embedded manifest (not a raw file).
MANIFEST_MEMBER = ".evidence-manifest.sha256"
_SUFFIX = {"gz": ".tar.gz", "xz": ".tar.xz", "bz2": ".tar.bz2"}
_READ_CHUNK = 1 << 20


def manifest_bytes(root: Path) -> bytes:
    """The raw tree's SHA-256 manifest, as bytes, for embedding in the bundle."""
    return "".join(manifest_lines(root)).encode("utf-8")


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    """Add one member with fully normalized metadata (deterministic output)."""
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    tar.addfile(info, io.BytesIO(data))


def _write_tar(tar: tarfile.TarFile, root: Path) -> None:
    for path in iter_regular_files(root):
        _add_bytes(tar, path.relative_to(root).as_posix(), path.read_bytes())
    _add_bytes(tar, MANIFEST_MEMBER, manifest_bytes(root))


@dataclass(frozen=True, slots=True)
class BundleResult:
    path: Path
    sha256: str
    size: int
    file_count: int


def create_bundle(root: Path, out_path: Path, fmt: str = "gz") -> BundleResult:
    """Write a deterministic compressed bundle of ``root`` to ``out_path``."""
    if fmt not in _SUFFIX:
        raise ValueError(f"unsupported format: {fmt} (use one of {sorted(_SUFFIX)})")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    file_count = sum(1 for _ in iter_regular_files(root))
    if fmt == "gz":
        # tarfile's "w:gz" stamps the current time (and the file name) into the gzip
        # header; wrapping a GzipFile with mtime=0 and an empty stored name keeps the
        # bundle bytes reproducible regardless of the output path.
        with out_path.open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w:") as tar:
                    _write_tar(tar, root)
    elif fmt == "xz":
        with tarfile.open(out_path, "w:xz") as tar:
            _write_tar(tar, root)
    else:
        with tarfile.open(out_path, "w:bz2") as tar:
            _write_tar(tar, root)

    digest = sha256()
    with out_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    bundle_sha = digest.hexdigest()
    out_path.with_name(out_path.name + ".sha256").write_text(
        f"{bundle_sha}  {out_path.name}\n", encoding="utf-8"
    )
    return BundleResult(out_path, bundle_sha, out_path.stat().st_size, file_count)


@dataclass(slots=True)
class VerifyResult:
    ok: int = 0
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.mismatched or self.missing)


def verify_bundle(bundle_path: Path) -> VerifyResult:
    """Re-hash every file inside the bundle against its embedded manifest."""
    result = VerifyResult()
    with tarfile.open(bundle_path, "r:*") as tar:
        if MANIFEST_MEMBER not in tar.getnames():
            raise ValueError(f"{bundle_path}: no embedded {MANIFEST_MEMBER}")
        manifest_fh = tar.extractfile(MANIFEST_MEMBER)
        if manifest_fh is None:
            raise ValueError(f"{bundle_path}: {MANIFEST_MEMBER} is not a file")
        with closing(manifest_fh):
            entries = parse_manifest(manifest_fh.read().decode("utf-8"))
        listed = {name for _, name in entries}
        members = {m.name: m for m in tar.getmembers()}
        for digest, name in entries:
            member = members.get(name)
            if member is None or not member.isfile():
                result.missing.append(name)
                continue
            data_fh = tar.extractfile(member)
            if data_fh is None:
                result.missing.append(name)
                continue
            with closing(data_fh):
                if sha256(data_fh.read()).hexdigest() == digest:
                    result.ok += 1
                else:
                    result.mismatched.append(name)
        for member in tar.getmembers():
            if member.isfile() and member.name != MANIFEST_MEMBER and member.name not in listed:
                result.extra.append(member.name)
    return result


def default_output(root: Path, host: str, fmt: str, today: str) -> Path:
    return Path.home() / "inodefence-evidence-bundles" / f"{host}-{today}{_SUFFIX[fmt]}"


def _generate(args: argparse.Namespace) -> int:
    root = args.root.expanduser()
    if not root.is_dir():
        print(f"root is not a directory: {root}", file=sys.stderr)
        return 2
    today = args.date or date.today().strftime("%Y%m%d")
    out = args.out.expanduser() if args.out else default_output(root, args.host, args.format, today)
    result = create_bundle(root, out, args.format)
    print(
        f"wrote bundle {result.path} ({result.file_count} files, {result.size} bytes)\n"
        f"bundle sha256 {result.sha256}\n"
        f"sidecar {result.path.name}.sha256 ; NOT uploaded (backup location is a human gate)"
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    bundle = args.verify.expanduser()
    if not bundle.is_file():
        print(f"bundle not found: {bundle}", file=sys.stderr)
        return 2
    result = verify_bundle(bundle)
    for name in result.mismatched:
        print(f"MISMATCH {name}", file=sys.stderr)
    for name in result.missing:
        print(f"MISSING  {name}", file=sys.stderr)
    for name in result.extra:
        print(f"EXTRA    {name} (in bundle, not in embedded manifest)", file=sys.stderr)
    status = "FAIL" if result.failed else "OK"
    print(
        f"verify {status}: {result.ok} ok, {len(result.mismatched)} mismatched, "
        f"{len(result.missing)} missing, {len(result.extra)} extra ({bundle})"
    )
    return 1 if result.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, metavar="BUNDLE", help="verify an existing bundle")
    parser.add_argument("--root", type=Path, help="raw evidence tree to bundle")
    parser.add_argument("--host", help="short host label for the bundle file name")
    parser.add_argument("--date", help="YYYYMMDD for the bundle file name (default: today)")
    parser.add_argument(
        "--format", choices=sorted(_SUFFIX), default="gz", help="stdlib compression"
    )
    parser.add_argument("--out", type=Path, help="override the bundle output path")
    args = parser.parse_args(argv)

    if args.verify is not None:
        return _verify(args)
    if args.root is None or args.host is None:
        parser.error("generate mode requires --root and --host")
    return _generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
