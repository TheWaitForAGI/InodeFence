"""Unit tests for the maintainer regression wrapper (no docker; cri.run_one is mocked).

Cover fixture assembly, C1/C2 derivation from synthetic raw observations, the PASS/FAIL/ERROR
summary, version validation, and that --dry-run runs no container.
"""

import io
import tarfile

import pytest
import scripts.regression_check as rc


def test_build_fixtures_assembles_hand_and_fn_placements() -> None:
    fixtures = rc.build_fixtures()
    names = [f.name for f in fixtures]
    assert names == [
        "toplevel_hardlink",
        "nested_hardlink",
        "toplevel_symlink_write",
        "nested_symlink_write",
        "dir_symlink_write",
    ]
    assert {f.kind for f in fixtures} == {"hand-hardlink", "fn-symlink"}
    # Every fixture is a parseable tar carrying a link/symlink entry to the external reference.
    for fixture in fixtures:
        with tarfile.open(fileobj=io.BytesIO(fixture.tar), mode="r:") as archive:
            members = archive.getmembers()
        assert members
        assert any(m.islnk() or m.issym() for m in members)


def test_c1_c2_from_hardlink_raw() -> None:
    raw = {
        "shared_identity": ["extract/link"],
        "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
        "reference_after": {"ino": "5", "nlink": 2, "size": 10, "type": "reg"},
    }
    assert rc.c1_from_raw(raw) is True
    assert rc.c2_from_raw(raw) is True


def test_c2_from_symlink_write_size_change() -> None:
    raw = {
        "shared_identity": [],
        "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
        "reference_after": {"ino": "9", "nlink": 1, "size": 20, "type": "reg"},
    }
    assert rc.c1_from_raw(raw) is False
    assert rc.c2_from_raw(raw) is True


def test_clean_raw_has_no_c1_or_c2() -> None:
    raw = {
        "declined": {"message": "declined"},
        "shared_identity": [],
        "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
        "reference_after": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
    }
    assert rc.c1_from_raw(raw) is False
    assert rc.c2_from_raw(raw) is False


def test_reference_vanished_is_c2() -> None:
    raw = {
        "shared_identity": [],
        "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
        "reference_after": {"error": "ENOENT"},
    }
    assert rc.c2_from_raw(raw) is True


def test_run_error_is_unknown_not_false() -> None:
    raw = {"_run_error": True, "_rc": 1}
    assert rc.c1_from_raw(raw) is None
    assert rc.c2_from_raw(raw) is None


def _row(name: str, c1_or_c2) -> dict:
    return {"fixture": name, "c1_or_c2": c1_or_c2}


def test_summarize_pass_fail_error() -> None:
    assert rc.summarize("7.5.3", [_row("a", False), _row("b", False)])["verdict"] == "PASS"
    fail = rc.summarize("7.5.2", [_row("a", False), _row("b", True)])
    assert fail["verdict"] == "FAIL"
    assert fail["breached_fixtures"] == ["b"]
    err = rc.summarize("7.5.2", [_row("a", None), _row("b", False)])
    assert err["verdict"] == "ERROR"
    assert err["errored_fixtures"] == ["a"]


def test_run_drives_every_fixture_through_run_one(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run_one(release: str, tar_b64: str) -> dict:
        calls.append(release)
        return {
            "shared_identity": [],
            "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
            "reference_after": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
        }

    monkeypatch.setattr(rc.cri, "run_one", fake_run_one)
    summary = rc.run("7.5.3")
    assert summary["verdict"] == "PASS"
    assert len(summary["fixtures"]) == 5
    assert calls == ["7.5.3"] * 5


def test_dry_run_executes_no_container(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> dict:
        raise AssertionError("run_one must not be called during --dry-run")

    monkeypatch.setattr(rc.cri, "run_one", forbidden)
    assert rc.main(["--tar-version", "7.5.2", "--dry-run"]) == 0


@pytest.mark.parametrize("version", ["", "CVE-2026-1", "7.x", "latest", "7.5.2-rc1"])
def test_invalid_versions_rejected(version: str) -> None:
    with pytest.raises(SystemExit):
        rc.main(["--tar-version", version, "--dry-run"])


def test_main_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    for verdict, code in (("PASS", 0), ("FAIL", 1), ("ERROR", 2)):
        monkeypatch.setattr(
            rc,
            "run",
            lambda _v, verdict=verdict: {
                "verdict": verdict,
                "breached_fixtures": [],
                "fixtures": [],
                "tar_version": _v,
            },
        )
        assert rc.main(["--tar-version", "7.5.2"]) == code
