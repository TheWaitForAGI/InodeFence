"""The paper-artifacts regenerator verifies committed outputs honestly by policy."""

from pathlib import Path

from scripts.regenerate_paper_artifacts import (
    Artifact,
    regenerate_artifacts,
    verify_artifacts,
)


def _write(repo: Path, rel: str, data: bytes) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _table(output: str) -> Artifact:
    return Artifact(output, "table", None, "", ("src.json",), "exists", "hand-maintained")


def _figure(output: str, generator: str | None = None) -> Artifact:
    return Artifact(output, "figure", generator, "matplotlib-ephemeral", ("src",), "size", "png")


def test_table_exists_and_missing(tmp_path: Path) -> None:
    art = _table("paper/tables/t.md")
    _write(tmp_path, art.output, b"# table\n")
    [row] = verify_artifacts((art,), tmp_path)
    assert row.status == "EXISTS"
    # missing committed table with a required (None) generator -> MISSING (failure)
    missing = _table("paper/tables/gone.md")
    [row2] = verify_artifacts((missing,), tmp_path)
    assert row2.status == "MISSING"


def test_figure_is_size_only(tmp_path: Path) -> None:
    art = _figure("paper/figures/f.png", generator="paper/figures/gen.py")
    _write(tmp_path, art.output, b"\x89PNG\r\n" + b"x" * 100)
    _write(tmp_path, art.generator, b"# gen\n")  # type: ignore[arg-type]
    [row] = verify_artifacts((art,), tmp_path)
    assert row.status == "SIZE-ONLY"
    assert "byte-compare N/A" in row.detail


def test_optional_artifact_skips_when_generator_absent(tmp_path: Path) -> None:
    # Generator declared but not in the tree and no committed output -> SKIP, not MISSING.
    art = _figure("paper/figures/pending.png", generator="paper/figures/absent.py")
    [row] = verify_artifacts((art,), tmp_path)
    assert row.status == "SKIP"


def test_byte_policy_match_and_mismatch(tmp_path: Path) -> None:
    art = Artifact(
        "paper/tables/gen.md",
        "table",
        "scripts/gen_table.py",
        "project",
        ("src",),
        "byte",
        "generated",
        out_flag=True,
    )
    _write(tmp_path, art.output, b"ROW A\nROW B\n")
    _write(tmp_path, art.generator, b"# gen\n")  # type: ignore[arg-type]

    def runner(_a: Artifact, _root: Path, dest: Path) -> None:
        dest.write_bytes(b"ROW A\nROW B\n")  # reproduces committed bytes

    [row] = verify_artifacts((art,), tmp_path, runner=runner)
    assert row.status == "BYTE-MATCH"

    def bad_runner(_a: Artifact, _root: Path, dest: Path) -> None:
        dest.write_bytes(b"DIFFERENT\n")

    [row2] = verify_artifacts((art,), tmp_path, runner=bad_runner)
    assert row2.status == "BYTE-MISMATCH"


def test_regenerate_skips_handmaintained_and_absent(tmp_path: Path) -> None:
    rows = regenerate_artifacts(
        (_table("paper/tables/t.md"), _figure("paper/figures/x.png", "paper/figures/absent.py")),
        tmp_path,
    )
    assert [r.status for r in rows] == ["SKIP", "SKIP"]
    assert "hand-maintained" in rows[0].detail
