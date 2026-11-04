"""The evidence bundle tool packs a raw tree deterministically and verifies it."""

import io
import tarfile
from hashlib import sha256
from pathlib import Path

import pytest
from scripts.make_evidence_bundle import (
    MANIFEST_MEMBER,
    create_bundle,
    default_output,
    main,
    manifest_bytes,
    verify_bundle,
)
from scripts.make_raw_manifest import manifest_lines


def _tree(base: Path) -> Path:
    root = base / "raw"
    (root / "sub").mkdir(parents=True)
    (root / "a.json").write_text("alpha", encoding="utf-8")
    (root / "sub" / "b.json").write_text("beta", encoding="utf-8")
    return root


def _build_manual_bundle(path: Path, manifest_text: str, files: dict[str, bytes]) -> None:
    """Write a bundle with an arbitrary manifest/body pair to exercise verify paths."""
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        manifest = manifest_text.encode("utf-8")
        info = tarfile.TarInfo(MANIFEST_MEMBER)
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))


def test_manifest_bytes_match_make_raw_manifest(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert manifest_bytes(root) == "".join(manifest_lines(root)).encode("utf-8")


def test_create_then_verify_roundtrip(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    out = tmp_path / "bundle.tar.gz"
    result = create_bundle(root, out, "gz")
    assert result.file_count == 2
    assert out.is_file()
    sidecar = out.with_name(out.name + ".sha256")
    assert sidecar.read_text(encoding="utf-8") == f"{result.sha256}  {out.name}\n"
    assert sha256(out.read_bytes()).hexdigest() == result.sha256
    verify = verify_bundle(out)
    assert not verify.failed and verify.ok == 2 and verify.extra == []


def test_bundle_bytes_are_deterministic(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    one = create_bundle(root, tmp_path / "one.tar.gz", "gz")
    two = create_bundle(root, tmp_path / "two.tar.gz", "gz")
    assert one.sha256 == two.sha256


@pytest.mark.parametrize("fmt", ["gz", "xz", "bz2"])
def test_all_stdlib_formats_roundtrip(tmp_path: Path, fmt: str) -> None:
    root = _tree(tmp_path)
    out = tmp_path / f"bundle.{fmt}"
    create_bundle(root, out, fmt)
    assert not verify_bundle(out).failed


def test_verify_detects_mismatch_missing_and_extra(tmp_path: Path) -> None:
    digest = sha256(b"alpha").hexdigest()
    wrong = sha256(b"nope").hexdigest()
    manifest = f"{digest}  ./a.json\n{digest}  ./gone.json\n"
    bundle = tmp_path / "bad.tar.gz"
    # a.json present but hashes to a different value; gone.json absent; extra.json unlisted.
    _build_manual_bundle(
        bundle,
        manifest.replace(digest, wrong, 1),
        {"a.json": b"alpha", "extra.json": b"x"},
    )
    result = verify_bundle(bundle)
    assert result.failed
    assert result.mismatched == ["a.json"]
    assert result.missing == ["gone.json"]
    assert result.extra == ["extra.json"]


def test_verify_requires_embedded_manifest(tmp_path: Path) -> None:
    bundle = tmp_path / "nomanifest.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        info = tarfile.TarInfo("a.json")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="no embedded"):
        verify_bundle(bundle)


def test_unsupported_format_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported format"):
        create_bundle(_tree(tmp_path), tmp_path / "b.tar.zst", "zst")


def test_default_output_is_outside_repo_in_bundles_dir() -> None:
    out = default_output(Path("/x/raw"), "win", "gz", "20261104")
    assert out == Path.home() / "inodefence-evidence-bundles" / "win-20261104.tar.gz"


def test_main_generate_and_verify(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    out = tmp_path / "m.tar.gz"
    assert main(["--root", str(root), "--host", "t", "--out", str(out)]) == 0
    assert main(["--verify", str(out)]) == 0
