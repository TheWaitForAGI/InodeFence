"""#514 fixture case folders for replay (no run; folders read back with the replay loader)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from scripts.analysis import oracle_accuracy_real_cases as cases
from scripts.oracle_accuracy_fixtures import CASES

from inodefence.builder import build_tar
from inodefence.case_replay import load_replay_request

IMAGE = "sha256:" + "a" * 64
NODE_SETTINGS = {
    "sentinel_count": None,
    "sentinel_seed": None,
    "observer_integrity_policy": "stop",
    "profile": "full",
}


def _run(out: Path, *extra: str, version: str = "7.5.11", image: str = IMAGE) -> int:
    return cases.main(
        [
            "--target",
            "node-tar",
            "--version",
            version,
            "--image-id",
            image,
            "--run-settings",
            json.dumps(NODE_SETTINGS),
            "--out",
            str(out),
            *extra,
        ]
    )


def test_writes_one_replayable_folder_per_fixture(tmp_path: Path, capsys) -> None:
    assert _run(tmp_path) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["schema"] == cases.MANIFEST_SCHEMA
    rows = manifest["cases"]
    assert [row["fixture"] for row in rows] == list(cases.FIXTURES)
    for row in rows:
        folder = tmp_path / row["case_dir"]
        request = load_replay_request(folder)  # the replay driver's own loader accepts it
        expected = build_tar(CASES[row["fixture"]])
        assert request.tar_bytes == expected
        assert row["tar_sha256"] == sha256(expected).hexdigest() == request.tar_sha256
        assert request.case_id == CASES[row["fixture"]].case_id
        assert request.run_settings == NODE_SETTINGS
        assert request.image_id == IMAGE
        record = json.loads((folder / "case.json").read_text())
        assert (record["origin"], record["fixture"]) == ("fixture", row["fixture"])
        assert [record[k] for k in ("status", "c0", "c1", "c2")] == [None] * 4


def test_two_cells_share_one_manifest(tmp_path: Path) -> None:
    assert _run(tmp_path, "--fixtures", "F01", "F09") == 0
    assert _run(tmp_path, "--fixtures", "F01", version="7.5.2") == 0
    rows = json.loads((tmp_path / "manifest.json").read_text())["cases"]
    assert [(r["fixture"], r["version"]) for r in rows] == [
        ("F01", "7.5.11"),
        ("F09", "7.5.11"),
        ("F01", "7.5.2"),
    ]


@pytest.mark.parametrize(
    "extra",
    [
        ("--fixtures", "F15"),
        ("--fixtures", "F00"),
    ],
)
def test_unknown_fixtures_are_refused(tmp_path: Path, extra: tuple[str, ...]) -> None:
    assert _run(tmp_path, *extra) == 2


def test_inexact_image_id_is_refused(tmp_path: Path) -> None:
    assert _run(tmp_path, image="node-tar:7.5.11") == 2


def test_existing_cell_folder_is_never_overwritten(tmp_path: Path) -> None:
    assert _run(tmp_path, "--fixtures", "F01") == 0
    before = (tmp_path / "manifest.json").read_text()
    assert _run(tmp_path, "--fixtures", "F02") == 2
    assert (tmp_path / "manifest.json").read_text() == before


def test_out_inside_the_repository_is_refused(capsys) -> None:
    inside = cases.REPO_ROOT / "build" / "fixture-cases-test"
    assert _run(inside) == 2
    assert not inside.exists()
    assert "outside the repository" in capsys.readouterr().err


def test_settings_must_be_a_json_object(tmp_path: Path) -> None:
    common = ["--target", "node-tar", "--version", "7.5.11", "--image-id", IMAGE]
    assert cases.main([*common, "--run-settings", "[1]", "--out", str(tmp_path)]) == 2
    assert cases.main([*common, "--run-settings", "{", "--out", str(tmp_path)]) == 2


def test_a_fixture_listed_twice_for_one_cell_is_refused(tmp_path: Path) -> None:
    rows = cases.write_cases(
        tmp_path, target="node-tar", version="7.5.11", image_id=IMAGE, run_settings=NODE_SETTINGS
    )
    cases.write_manifest(tmp_path, rows)
    with pytest.raises(cases.Refused, match="already lists"):
        cases.write_manifest(tmp_path, rows)


@pytest.mark.parametrize(
    ("target", "version", "settings", "message"),
    [
        (
            "node-tar",
            "7.5.11",
            {k: v for k, v in NODE_SETTINGS.items() if k != "profile"},
            "profile",
        ),
        (
            "python-tarfile",
            "3.12.16",
            {"extraction_filter": "fully_trusted", "runtime_version": "3.12.16"},
            "not explored",
        ),
        (
            "python-tarfile",
            "3.12.16",
            {"extraction_filter": "data", "runtime_version": "3.12.10"},
            "runtime_version",
        ),
    ],
)
def test_a_folder_the_replay_check_refuses_is_exit_2(
    tmp_path: Path, capsys, target: str, version: str, settings: dict, message: str
) -> None:
    """The target's own replay_check runs on every written folder (no extraction)."""
    code = cases.main(
        [
            "--target",
            target,
            "--version",
            version,
            "--image-id",
            IMAGE,
            "--run-settings",
            json.dumps(settings),
            "--out",
            str(tmp_path),
            "--fixtures",
            "F01",
        ]
    )
    err = capsys.readouterr().err
    assert code == 2 and "replay would refuse" in err and message in err
    assert not (tmp_path / "manifest.json").exists()


def test_a_folder_the_replay_loader_refuses_is_exit_2(tmp_path: Path, capsys, monkeypatch) -> None:
    """If the written record disagreed with its input, the read-back catches it."""
    real = cases.case_record

    def wrong_hash(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = real(*args, **kwargs)
        record["tar_sha256"] = "0" * 64
        return record

    monkeypatch.setattr(cases, "case_record", wrong_hash)
    assert _run(tmp_path, "--fixtures", "F01") == 2
    assert "replay would refuse" in capsys.readouterr().err
    assert not (tmp_path / "manifest.json").exists()


def test_python_tarfile_data_cells_pass_the_replay_check(tmp_path: Path) -> None:
    settings = {"extraction_filter": "data", "runtime_version": "3.12.16"}
    rows = cases.write_cases(
        tmp_path, target="python-tarfile", version="3.12.16", image_id=IMAGE, run_settings=settings
    )
    assert len(rows) == 14 and {row["extraction_filter"] for row in rows} == {"data"}
