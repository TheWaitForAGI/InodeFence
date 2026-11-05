"""The paper-artifacts regenerator verifies committed outputs honestly by policy."""

import tempfile
from pathlib import Path

import scripts.regenerate_paper_artifacts as regen
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


def test_regenerate_apply_gate(tmp_path: Path) -> None:
    # Without --apply: out_flag generators stage to a temp dir (committed untouched);
    # non-out_flag (figure) generators are skipped. With --apply they would write in place.
    (tmp_path / "g.py").write_text(
        "import argparse\n"
        "p=argparse.ArgumentParser(); p.add_argument('--out'); a=p.parse_args()\n"
        "open(a.out,'w').write('TABLE')\n",
        encoding="utf-8",
    )
    (tmp_path / "f.py").write_text("open('fig.out','w').write('F')\n", encoding="utf-8")
    table = Artifact("out/t.md", "table", "g.py", "project", ("s",), "byte", "", out_flag=True)
    fig = Artifact("out/f.png", "figure", "f.py", "project", ("s",), "size", "")
    stage = tmp_path / "stage"
    rows = regenerate_artifacts((table, fig), tmp_path, apply=False, stage_dir=stage)
    st = {r.output: r.status for r in rows}
    assert st["out/t.md"] == "STAGED"
    assert st["out/f.png"] == "SKIP"
    assert (stage / "t.md").read_text(encoding="utf-8") == "TABLE"
    assert not (tmp_path / "out" / "t.md").exists()  # committed path untouched


_OUT_GENERATOR = (
    "import argparse\n"
    "p=argparse.ArgumentParser(); p.add_argument('--out'); a=p.parse_args()\n"
    "open(a.out,'w').write('TABLE')\n"
)


def _out_table_repo(tmp_path: Path) -> tuple[Path, Artifact]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "g.py").write_text(_OUT_GENERATOR, encoding="utf-8")
    table = Artifact("out/t.md", "table", "g.py", "project", ("s",), "byte", "", out_flag=True)
    return repo, table


def test_regenerate_default_stage_is_outside_repo(tmp_path: Path, monkeypatch) -> None:
    # No stage_dir: stage into a fresh temp dir outside the repo, never the old in-repo
    # <repo>/.paper-artifacts-stage (an untracked dir that dirtied the checkout).
    repo, table = _out_table_repo(tmp_path)
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    [row] = regenerate_artifacts((table,), repo, apply=False)
    assert row.status == "STAGED"
    staged = Path(row.detail.split("(staged ", 1)[1].rstrip(")"))
    assert staged.read_text(encoding="utf-8") == "TABLE"
    assert staged.is_relative_to(temp_root) and not staged.is_relative_to(repo)
    assert sorted(p.name for p in repo.iterdir()) == ["g.py"]  # checkout untouched


def test_main_regenerate_removes_stage_unless_keep(tmp_path: Path, monkeypatch) -> None:
    repo, table = _out_table_repo(tmp_path)
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    monkeypatch.setattr(regen, "_repo_root", lambda: repo)
    monkeypatch.setattr(regen, "ARTIFACTS", (table,))

    assert regen.main(["--regenerate"]) == 0
    assert list(temp_root.iterdir()) == []  # removed on success
    assert sorted(p.name for p in repo.iterdir()) == ["g.py"]

    assert regen.main(["--regenerate", "--keep-stage"]) == 0
    [kept] = list(temp_root.iterdir())
    assert (kept / "t.md").read_text(encoding="utf-8") == "TABLE"
    assert sorted(p.name for p in repo.iterdir()) == ["g.py"]
