"""PR 3: an unanswered image question is never "absent", and an existing result is refused (3).

No daemon is touched: ``health.lookup_image`` / the adapters are faked.
"""

from __future__ import annotations

import pytest

import inodefence.drivers.run_target as rt
from inodefence.drivers import explore_result
from inodefence.drivers.runtime import health
from inodefence.drivers.runtime.health import ImageLookup, ImageState


def _lookup(monkeypatch, answer: ImageLookup) -> None:
    monkeypatch.setattr(health, "lookup_image", lambda ref, **kw: answer)


def test_image_id_raises_instead_of_returning_none_when_docker_is_silent(monkeypatch) -> None:
    _lookup(monkeypatch, ImageLookup(ImageState.UNKNOWN, detail="did not answer within 30s"))
    with pytest.raises(rt.ImageStateUnknown, match="Nothing was prepared or run"):
        rt.image_id("inodefence-x:1")
    assert issubclass(rt.ImageStateUnknown, ValueError)  # every driver's setup path (exit 3)
    _lookup(monkeypatch, ImageLookup(ImageState.ABSENT))
    assert rt.image_id("inodefence-x:1") is None
    _lookup(monkeypatch, ImageLookup(ImageState.PRESENT, "sha256:abc"))
    assert rt.image_id("inodefence-x:1") == "sha256:abc"


class _Adapter:
    verify_existing = None

    def __init__(self) -> None:
        self.prepared: list = []

    def prepare(self, cell):
        self.prepared.append(cell)
        return rt.PrepareStep(cell.image_ref, (("true",),), "build")


def _cell():
    return type("Cell", (), {"image_ref": "inodefence-x:1"})()


def test_resolve_images_never_prepares_on_silence(monkeypatch) -> None:
    _lookup(monkeypatch, ImageLookup(ImageState.UNKNOWN, detail="did not answer within 30s"))
    adapter = _Adapter()
    ready, errors = rt.resolve_images(adapter, [_cell()], auto_prepare=True)  # type: ignore[arg-type]
    assert ready == {} and not adapter.prepared
    assert "could not tell whether image inodefence-x:1 is on this host" in errors["inodefence-x:1"]
    assert "missing image" not in errors["inodefence-x:1"]


def test_resolve_images_still_prepares_an_absent_image(monkeypatch) -> None:
    answers = iter([ImageLookup(ImageState.ABSENT), ImageLookup(ImageState.PRESENT, "sha256:new")])
    monkeypatch.setattr(health, "lookup_image", lambda ref, **kw: next(answers))
    monkeypatch.setattr(rt.subprocess, "run", lambda *a, **k: type("D", (), {"returncode": 0}))
    adapter = _Adapter()
    ready, errors = rt.resolve_images(adapter, [_cell()], auto_prepare=True)  # type: ignore[arg-type]
    assert ready == {"inodefence-x:1": "sha256:new"} and errors == {} and adapter.prepared


def test_dry_run_image_plan_says_unknown(monkeypatch) -> None:
    _lookup(monkeypatch, ImageLookup(ImageState.UNKNOWN, detail="no answer"))
    plan = rt.image_status(_Adapter(), _cell(), docker_ok=True)  # type: ignore[arg-type]
    assert plan["action"] == "unknown" and "could not tell" in plan["reason"]


def test_docker_problem_names_a_stalled_daemon(monkeypatch) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda name: "/usr/bin/docker")

    def stall(*args, **kwargs):
        raise rt.subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(rt.subprocess, "run", stall)
    problem = rt.docker_problem()
    assert problem is not None and "did not answer" in problem and "nothing was started" in problem


def test_existing_result_is_a_setup_refusal_naming_the_kept_report(tmp_path) -> None:
    out = tmp_path / "x-result"
    out.mkdir()
    (out / "result.json").write_text("{}")
    report = tmp_path / "inodefence-effect-explore-x.json"
    with pytest.raises(explore_result.ResultExistsError) as caught:
        explore_result.write_result(out, None, {}, report=report)  # type: ignore[arg-type]
    error = caught.value
    assert isinstance(error, FileExistsError) and isinstance(error, ValueError)
    assert "nothing was overwritten" in str(error) and str(report) in str(error)
    assert (out / "result.json").read_text() == "{}"


def test_existing_outputs_refusal_before_a_run(tmp_path) -> None:
    report = tmp_path / "r.json"
    result = tmp_path / "r-result" / "result.json"
    assert explore_result.existing_outputs(report, result) == []
    explore_result.refuse_existing(report, result)  # nothing there: no refusal, nothing written
    assert not report.exists() and not result.parent.exists()
    report.write_text("{}")
    assert explore_result.existing_outputs(report, result) == [report]
    with pytest.raises(explore_result.ResultExistsError, match="nothing was run or overwritten"):
        explore_result.refuse_existing(report, result)


def test_docker_not_found_advice_names_the_calling_command(monkeypatch) -> None:
    monkeypatch.setattr(rt.shutil, "which", lambda name: None)
    verify = rt.docker_problem()
    assert verify == (
        "docker not found on PATH; install Docker (Linux: Docker Engine; Windows: Docker "
        "Desktop with WSL integration) and run target-run on that host "
        "(the Dev Container has no docker)"
    )  # verify's wording, byte for byte
    explore = rt.docker_advice_for(verify, "inodefence explore")
    assert explore == verify.replace("run target-run", "run inodefence explore")
    assert rt.docker_advice_for(None, "x") is None


def test_explore_preflight_does_not_tell_the_user_to_run_target_run(monkeypatch, capsys, tmp_path):
    import inodefence.drivers.run_target_explore as rte

    monkeypatch.setattr(rt.shutil, "which", lambda name: None)
    monkeypatch.setenv("INODEFENCE_PROG", "inodefence explore")
    argv = ["--version", "7.5.2", "--auto-prepare", "--out", str(tmp_path / "out")]
    assert rte.main(argv) == 3
    err = capsys.readouterr().err
    assert "TARGET-EXPLORE SETUP: docker not found on PATH" in err
    assert "run inodefence explore on that host" in err and "target-run" not in err
    monkeypatch.delenv("INODEFENCE_PROG")
    assert rte.main(argv) == 3
    assert "run target-explore on that host" in capsys.readouterr().err
