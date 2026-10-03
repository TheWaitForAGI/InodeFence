from pathlib import Path

from scripts.check_docs import CANONICAL_DOCUMENTS, check_canonical_documents, check_document


def test_local_links_and_references(tmp_path: Path) -> None:
    (tmp_path / "target.md").touch()
    (tmp_path / "folder").mkdir()
    (tmp_path / "with space.md").touch()
    nested = tmp_path / "nested"
    nested.mkdir()
    document = nested / "README.md"
    document.write_text(
        "[file](../target.md#section) [dir](../folder/)\n"
        '[space](<../with space.md> "title") [encoded](../with%20space.md)\n'
        '[ref][ok] [ok][]\n[ok]: ../target.md "title"\n',
        encoding="utf-8",
    )
    assert check_document(document) == []


def test_missing_links_report_line_numbers(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text(
        "# Example\n[bad](missing.md)\n![image](missing.png)\n[link][missing]\n[ref]: absent.md\n",
        encoding="utf-8",
    )
    errors = check_document(document)
    assert len(errors) == 4
    assert ":2: missing link target missing.md" in errors[0]
    assert ":3: missing link target missing.png" in errors[1]
    assert ":4: undefined reference [missing]" in errors[2]
    assert ":5: missing link target absent.md" in errors[3]


def test_skip_external_anchors_and_code(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text(
        "[web](https://example.com) [web](http://example.com)\n"
        "[mail](mailto:team@example.com) [anchor](#section)\n"
        "```markdown\n[bad](missing.md)\n```\n"
        "~~~\n[bad](missing.md)\n~~~\n"
        "`[bad](missing.md)`\n    [bad](missing.md)\n",
        encoding="utf-8",
    )
    assert check_document(document) == []


def test_canonical_documents(tmp_path: Path) -> None:
    assert len(check_canonical_documents(tmp_path)) == len(CANONICAL_DOCUMENTS)
    for name in CANONICAL_DOCUMENTS:
        document = tmp_path / name
        document.parent.mkdir(parents=True, exist_ok=True)
        document.touch()
    assert check_canonical_documents(tmp_path) == []
    (tmp_path / "README.md").unlink()
    (tmp_path / "README.md").mkdir()
    assert check_canonical_documents(tmp_path) == ["Missing canonical document: README.md"]
