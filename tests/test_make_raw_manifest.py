"""The raw-evidence manifest tool generates and verifies ``sha256sum``-format lists.

The verifier must also read the committed mac manifest format so one tool covers
every host's raw tree.
"""

from hashlib import sha256
from pathlib import Path

from scripts.make_raw_manifest import (
    default_output,
    main,
    manifest_lines,
    parse_manifest,
    verify_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MAC_MANIFEST = REPO_ROOT / "experiments/summaries/raw-manifest-mac-20261103.sha256"


def _tree(base: Path) -> Path:
    """Build a small evidence tree under ``base/tree`` and return that root.

    The manifest is kept outside the hashed root so it is never a tree member.
    """
    root = base / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "a.json").write_text("alpha", encoding="utf-8")
    (root / "sub" / "b.json").write_text("beta", encoding="utf-8")
    return root


def test_manifest_lines_are_sorted_prefixed_and_hash_the_bytes(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    lines = manifest_lines(root)
    assert lines == [
        f"{sha256(b'alpha').hexdigest()}  ./a.json\n",
        f"{sha256(b'beta').hexdigest()}  ./sub/b.json\n",
    ]


def test_verify_roundtrip_passes(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    manifest = tmp_path / "m.sha256"
    manifest.write_text("".join(manifest_lines(root)), encoding="utf-8")
    result = verify_manifest(manifest, root)
    assert not result.failed
    assert result.ok == 2
    assert result.mismatched == [] and result.missing == [] and result.extra == []


def test_verify_detects_mismatch_and_missing(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    manifest = tmp_path / "m.sha256"
    manifest.write_text("".join(manifest_lines(root)), encoding="utf-8")
    (root / "a.json").write_text("tampered", encoding="utf-8")
    (root / "sub" / "b.json").unlink()
    result = verify_manifest(manifest, root)
    assert result.failed
    assert result.mismatched == ["a.json"]
    assert result.missing == ["sub/b.json"]


def test_verify_reports_extra_without_failing(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    manifest = tmp_path / "m.sha256"
    manifest.write_text("".join(manifest_lines(root)), encoding="utf-8")
    (root / "c.json").write_text("gamma", encoding="utf-8")
    result = verify_manifest(manifest, root)
    assert not result.failed
    assert result.extra == ["c.json"]


def test_parse_manifest_tolerates_binary_marker_and_strips_dot_slash() -> None:
    digest = sha256(b"x").hexdigest()
    text = f"{digest}  ./p/one.json\n{digest} *two.json\n\n"
    assert parse_manifest(text) == [(digest, "p/one.json"), (digest, "two.json")]


def test_verify_reads_the_committed_mac_manifest_format() -> None:
    entries = parse_manifest(MAC_MANIFEST.read_text(encoding="utf-8"))
    assert len(entries) == 1614
    assert all(len(digest) == 64 and int(digest, 16) >= 0 for digest, _ in entries)
    assert all(not name.startswith("./") for _, name in entries)


def test_main_generate_then_verify(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    out = tmp_path / "gen.sha256"
    argv = ["--root", str(root), "--host", "test", "--date", "20260101", "--out", str(out)]
    assert main(argv) == 0
    assert out.is_file()
    assert main(["--verify", str(out), "--root", str(root)]) == 0


def test_default_output_path() -> None:
    assert default_output("win", "20261104") == Path(
        "experiments/summaries/raw-manifest-win-20261104.sha256"
    )


def test_exclude_suffix_skips_matching_files_in_generate_and_verify(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "note.sha256").write_text("deadbeef  ./x\n", encoding="utf-8")
    # Default includes the sidecar; excluding .sha256 drops it from the manifest.
    assert any(name.endswith("note.sha256") for name in "".join(manifest_lines(root)).split())
    lines = manifest_lines(root, (".sha256",))
    assert all("note.sha256" not in line for line in lines)
    assert len(lines) == 2
    # verify with the same exclusion does not flag the sidecar as extra.
    manifest = tmp_path / "m.sha256"
    manifest.write_text("".join(lines), encoding="utf-8")
    result = verify_manifest(manifest, root, (".sha256",))
    assert not result.failed and result.extra == []
