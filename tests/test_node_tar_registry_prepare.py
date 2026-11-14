"""node-tar registry preparation (exploratory): every failure leaves no image (no docker here)."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.node_tar_registry_prepare as reg
import scripts.run_node_tar_target as nt
import scripts.run_target as rt

from inodefence.target_result import (
    EXPLORATORY_LABEL,
    LABEL,
    Preparation,
    TargetResultError,
    from_json_dict,
    load_target_result,
)

V = "7.5.23"
IMAGE = "inodefence-node-tar-registry:7.5.23-t"
CLOSURE = {
    "@isaacs/fs-minipass": "4.0.1",
    "chownr": "3.0.0",
    "minipass": "7.1.3",
    "minizlib": "3.1.0",
    "yallist": "5.0.0",
}


def _integrity(spec: str) -> str:
    return "sha512-" + base64.b64encode(spec.encode()).decode()


def _lock(extra: dict[str, dict[str, Any]] | None = None, version: str = V) -> dict[str, Any]:
    packages: dict[str, Any] = {
        "": {"name": "inodefence-node-benchmark", "dependencies": {"tar": version}}
    }
    for name, ver in {**CLOSURE, "tar": version}.items():
        packages[f"node_modules/{name}"] = {
            "version": ver,
            "resolved": f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{ver}.tgz",
            "integrity": _integrity(f"{name}@{ver}"),
        }
    for key, entry in (extra or {}).items():
        packages[key] = {**packages.get(key, {}), **entry}
    return {"name": "inodefence-node-benchmark", "lockfileVersion": 3, "packages": packages}


class FakeDocker:
    """docker + npm-in-container stand-in. ``fail`` names the step that breaks."""

    def __init__(self, *, fail: str = "", lock: dict[str, Any] | None = None, installed: str = V):
        self.fail = fail
        self.lock = lock or _lock()
        self.installed = installed
        self.images: set[str] = set()
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        args = cmd[1:]

        def done(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, code, out, err)

        if self.fail == "docker":
            raise FileNotFoundError("docker")
        verb = args[0]
        if verb == "image":
            return done(0 if args[-1] in self.images else 1)
        if verb == "run" and "sh" in args:  # npm in the pinned node container
            env = dict(a.split("=", 1) for i, a in enumerate(args) if args[i - 1] == "-e")
            if self.fail == "network":
                return done(1, err="npm ERR! network ENOTFOUND registry.npmjs.org")
            if "SPECS" in env:
                lines = []
                for spec in env["SPECS"].split():
                    if self.fail == "missing" and spec == f"tar@{V}":
                        return done(0, "")  # npm view of an unknown version prints nothing
                    value = _integrity(spec) if self.fail != "integrity" else "sha512-WRONG"
                    lines.append(f"{spec} {value}")
                return done(0, "\n".join(lines) + "\n")
            return done(0, json.dumps(self.lock, indent=2) + "\n")
        if verb == "build":
            if self.fail == "build":
                return done(1, err="npm ci failed")
            self.images.add(args[args.index("-t") + 1])
            return done(0, "sha256:x")
        if verb == "run":  # offline version check
            assert args[1:4] == ["--rm", "--network", "none"]
            return done(0, self.installed + "\n")
        if verb == "tag":
            self.images.add(args[2])
            return done()
        if verb == "rmi":
            self.images.discard(args[-1])
            return done()
        raise AssertionError(args)

    def verbs(self) -> list[str]:
        return [c[1] for c in self.calls]


def _prepare(docker: FakeDocker, version: str = V, image: str = IMAGE) -> str:
    return reg.prepare(version, image, runner=docker, log=lambda line: None)


# ---- inputs refused before any docker/npm call ----


@pytest.mark.parametrize(
    "version",
    [
        "7.5",
        "latest",
        "^7.5.0",
        "7.5.x",
        "git+https://example.invalid/tar.git",
        "./tar",
        "7.5.23; rm -rf /",
        "npm:tar@7.5.23",
        "7.5.23 --registry=http://x",
    ],
)
def test_non_exact_versions_never_reach_docker(version: str) -> None:
    docker = FakeDocker()
    with pytest.raises(reg.RegistryPrepareError, match="exact X.Y.Z"):
        _prepare(docker, version)
    assert docker.calls == []


@pytest.mark.parametrize(
    "image", ["evil.example/x:1; rm", "Inodefence:1", "x", f"{IMAGE}-unverified"]
)
def test_odd_image_reference_is_refused(image: str) -> None:
    docker = FakeDocker()
    with pytest.raises(reg.RegistryPrepareError, match="image reference"):
        _prepare(docker, image=image)
    assert docker.calls == []


# ---- success, reuse, and every failure leaves IMAGE absent ----


def test_success_checks_before_tagging_and_cleans_staging() -> None:
    docker = FakeDocker()
    sha = _prepare(docker)
    assert len(sha) == 64
    assert docker.images == {IMAGE}  # staging removed, nothing else created
    verbs = docker.verbs()
    assert verbs.index("build") < verbs.index("tag")
    check = next(c for c in docker.calls if c[1] == "run" and "--network" in c)
    assert verbs.index("tag") > docker.calls.index(check)
    build = next(c for c in docker.calls if c[1] == "build")
    assert build[build.index("-t") + 1] == f"{IMAGE}-unverified"
    assert str(reg.REPO_ROOT) not in build[-1]  # context is a temp dir outside the repository
    assert any("--ignore-scripts" in " ".join(c) for c in docker.calls)


def test_existing_image_is_not_rebuilt() -> None:
    docker = FakeDocker()
    docker.images.add(IMAGE)
    _prepare(docker)
    assert docker.verbs() == ["image"]


@pytest.mark.parametrize(
    ("fail", "message"),
    [
        ("missing", "registry has no integrity"),
        ("network", "npm step failed"),
        ("integrity", "integrity differs"),
        ("build", "build failed"),
        ("docker", "docker image failed"),
    ],
)
def test_failures_leave_no_image(fail: str, message: str) -> None:
    docker = FakeDocker(fail=fail)
    with pytest.raises(reg.RegistryPrepareError, match=message):
        _prepare(docker)
    assert IMAGE not in docker.images
    assert "tag" not in docker.verbs()


def test_installed_version_mismatch_leaves_no_image_and_no_staging() -> None:
    docker = FakeDocker(installed="7.5.22")
    with pytest.raises(reg.RegistryPrepareError, match="expected 7.5.23"):
        _prepare(docker)
    assert docker.images == set()


@pytest.mark.parametrize(
    ("lock", "message"),
    [
        (_lock({"node_modules/evil-pkg": {"version": "1.0.0"}}), "evil-pkg@1.0.0.*promote"),
        (
            _lock({"node_modules/chownr": {"resolved": "https://mirror.example/chownr.tgz"}}),
            "not resolved from",
        ),
        (_lock({"node_modules/minipass": {"hasInstallScript": True}}), "install script"),
        (_lock({"node_modules/tar": {"version": "7.5.22"}}), "resolves tar"),
        (_lock({"": {"dependencies": {"tar": "^7.5.0"}}}), "exactly tar@"),
    ],
)
def test_lock_checks_fail_closed_before_build(lock: dict[str, Any], message: str) -> None:
    docker = FakeDocker(lock=lock)
    with pytest.raises(reg.RegistryPrepareError, match=message):
        _prepare(docker)
    assert "build" not in docker.verbs() and docker.images == set()


def test_rerun_after_interruption_does_not_use_staging_image() -> None:
    docker = FakeDocker()
    docker.images.add(f"{IMAGE}-unverified")  # left behind by an interrupted earlier run
    _prepare(docker)  # the real tag is absent, so preparation starts over and re-checks
    assert "build" in docker.verbs() and docker.images == {IMAGE}


def test_allowed_packages_come_from_committed_locks() -> None:
    assert set(CLOSURE) | {"tar"} <= reg.allowed_packages()


def test_node_image_is_the_dockerfile_pin() -> None:
    assert reg.node_image().startswith("node:22.22.0-bookworm-slim@sha256:")


# ---- adapter: verified path unchanged, unregistered = exploratory ----


def test_committed_versions_keep_the_verified_cell() -> None:
    (cell,) = nt.ADAPTER.cells(["7.5.2"], [])
    assert (cell.image_ref, cell.exploratory) == ("inodefence-node-tar-effect:7.5.2", False)
    assert (
        nt.ADAPTER.describe is not None and nt.ADAPTER.describe(cell, Path("/nonexistent")) is None
    )


def test_unregistered_exact_version_is_an_exploratory_registry_cell() -> None:
    (cell,) = nt.ADAPTER.cells(["9.9.9"], [])
    assert (cell.image_ref, cell.exploratory) == ("inodefence-node-tar-registry:9.9.9", True)
    step = nt.ADAPTER.prepare(cell)
    assert step.commands is not None
    assert step.commands[0][1:3] == ("-m", "scripts.node_tar_registry_prepare")


def test_unregistered_without_permission_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        rt.main(["--target", "node-tar", "--version", "9.9.9", "--dry-run"])
    assert stop.value.code == rt.SETUP_ERROR
    assert "ALLOW_REGISTRY_PREPARE=1" in capsys.readouterr().err


def test_dry_run_contacts_no_registry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: None)
    monkeypatch.setattr(reg, "prepare", lambda *a, **k: pytest.fail("dry-run must not prepare"))
    argv = ["--target", "node-tar", "--version", "9.9.9", "--allow-registry-prepare", "--dry-run"]
    assert rt.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)["cells"]["node-tar-9.9.9-exploratory"]
    assert plan["exploratory"] is True
    assert "scripts.node_tar_registry_prepare" in plan["image_plan"]["commands"][0]


def _fake_evidence(installed: str = "9.9.9"):
    lock = b'{"lockfileVersion": 3}\n'

    def evidence(image: str, runner: Any = None) -> dict[str, Any]:
        import hashlib

        return {
            "installed_version": installed,
            "lock": lock,
            "lock_sha256": hashlib.sha256(lock).hexdigest(),
            "worker_sha256": "a" * 64,
        }

    return evidence


def _clean(version: str) -> dict[str, Any]:
    ref = {"ino": "5", "nlink": 1, "size": 10, "type": "reg"}
    return {
        "declined": None,
        "shared_identity": [],
        "reference_before": ref,
        "reference_after": ref,
    }


def test_exploratory_run_is_labelled_and_records_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:reg")
    monkeypatch.setattr(rt, "engine_provenance", lambda image: rt.Provenance(None, True, image))
    monkeypatch.setattr(nt.cri, "run_one", lambda v, t, image=None: _clean(v))
    monkeypatch.setattr(nt.registry, "image_evidence", _fake_evidence())
    argv = ["--target", "node-tar", "--version", "9.9.9", "--allow-registry-prepare"]
    assert rt.main([*argv, "--out", str(tmp_path)]) == 0
    cell = tmp_path / "node-tar-9.9.9-exploratory"
    result = load_target_result(cell / "result.json")
    assert result.label == EXPLORATORY_LABEL
    assert result.preparation is not None and result.preparation.method == "registry"
    assert (cell / "preparation" / "package-lock.json").is_file()
    assert "(exploratory demo run)" in capsys.readouterr().out
    assert "exploratory demo run" in (cell / "summary.md").read_text(encoding="utf-8")


def test_installed_mismatch_at_describe_gives_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:reg")
    monkeypatch.setattr(rt, "engine_provenance", lambda image: rt.Provenance(None, True, image))
    monkeypatch.setattr(nt.cri, "run_one", lambda v, t, image=None: _clean(v))
    monkeypatch.setattr(nt.registry, "image_evidence", _fake_evidence(installed="9.9.8"))
    argv = ["--target", "node-tar", "--version", "9.9.9", "--allow-registry-prepare"]
    assert rt.main([*argv, "--out", str(tmp_path)]) == rt.SETUP_ERROR
    assert not (tmp_path / "node-tar-9.9.9-exploratory" / "result.json").exists()


# ---- result format: optional field, label pairing, old files still read ----


def _result_dict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, exploratory: bool) -> dict:
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:x")
    monkeypatch.setattr(rt, "engine_provenance", lambda image: rt.Provenance(None, True, image))
    monkeypatch.setattr(nt.cri, "run_one", lambda v, t, image=None: _clean(v))
    monkeypatch.setattr(nt.registry, "image_evidence", _fake_evidence())
    cell = "node-tar-9.9.9-exploratory" if exploratory else "node-tar-7.5.3"
    version = "9.9.9" if exploratory else "7.5.3"
    argv = ["--target", "node-tar", "--version", version, "--allow-registry-prepare"]
    rt.main([*argv, "--out", str(tmp_path)])
    return json.loads((tmp_path / cell / "result.json").read_text())


def test_verified_result_has_no_preparation_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _result_dict(tmp_path, monkeypatch, exploratory=False)
    assert "preparation" not in data and data["label"] == LABEL


def test_label_must_match_preparation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _result_dict(tmp_path, monkeypatch, exploratory=True)
    assert from_json_dict(data).preparation is not None
    with pytest.raises(TargetResultError, match="label"):
        from_json_dict({**data, "label": LABEL})
    stripped = {k: v for k, v in data.items() if k != "preparation"}
    with pytest.raises(TargetResultError, match="label"):
        from_json_dict(stripped)
    with pytest.raises(TargetResultError, match="preparation keys"):
        from_json_dict({**data, "preparation": {**data["preparation"], "extra": 1}})


def test_preparation_installed_must_equal_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _result_dict(tmp_path, monkeypatch, exploratory=True)
    bad = {**data, "preparation": {**data["preparation"], "installed_version": "9.9.8"}}
    with pytest.raises(TargetResultError, match="installed"):
        from_json_dict(bad)
    assert isinstance(from_json_dict(data).preparation, Preparation)


# ---- the five separation rules between verified and exploratory ----


def test_rule1_registry_result_is_never_tagged_with_a_verified_name() -> None:
    for image in ("inodefence-node-tar-effect:7.5.23", "inodefence-node-tar-effect:7.5.23-r"):
        docker = FakeDocker()
        with pytest.raises(reg.RegistryPrepareError, match="tagged only as"):
            _prepare(docker, image=image)
        assert docker.calls == []
    (cell,) = nt.ADAPTER.cells(["7.5.23"], [])
    assert cell.image_ref is not None and cell.image_ref.startswith(reg.REGISTRY_REPOSITORY + ":")


def test_rule2_committed_lock_always_takes_the_verified_path() -> None:
    (cell,) = nt.ADAPTER.cells(["7.5.3"], [])  # even when --allow-registry-prepare is given
    assert not cell.exploratory and cell.image_ref == "inodefence-node-tar-effect:7.5.3"
    step = nt.ADAPTER.prepare(cell)
    assert step.commands is not None and "node_tar_registry_prepare" not in " ".join(
        " ".join(c) for c in step.commands
    )
    docker = FakeDocker()
    with pytest.raises(reg.RegistryPrepareError, match="committed lock"):
        _prepare(docker, version="7.5.3", image="inodefence-node-tar-registry:7.5.3")
    assert docker.calls == []


def test_rule2_exploratory_image_is_never_reused_as_verified(tmp_path: Path) -> None:
    # Once a lock for 9.9.9 is committed, its cell asks for the verified name only, so an older
    # inodefence-node-tar-registry:9.9.9 image can never stand in for it.
    (versions := tmp_path / "9.9.9").mkdir()
    (versions / "package-lock.json").write_text("{}")
    original = nt.node_tar_image.VERSIONS_DIR
    try:
        nt.node_tar_image.VERSIONS_DIR = tmp_path
        (cell,) = nt.ADAPTER.cells(["9.9.9"], [])
    finally:
        nt.node_tar_image.VERSIONS_DIR = original
    assert (cell.image_ref, cell.exploratory) == ("inodefence-node-tar-effect:9.9.9", False)


def test_rule3_preparation_shows_in_folder_terminal_file_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _result_dict(tmp_path, monkeypatch, exploratory=True)
    cell = tmp_path / "node-tar-9.9.9-exploratory"
    assert data["label"] == EXPLORATORY_LABEL and data["preparation"]["method"] == "registry"
    summary = (cell / "summary.md").read_text(encoding="utf-8")
    assert "임시 생성 lock" in summary and "SHA-256" in summary
    assert data["preparation"]["lock_sha256"] in summary
    assert "(exploratory demo run)" in capsys.readouterr().out


def test_rule4_verified_and_exploratory_never_share_one_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = ["--target", "node-tar", "--version", "7.5.3", "--version", "9.9.9"]
    with pytest.raises(SystemExit) as stop:
        rt.main([*argv, "--allow-registry-prepare", "--dry-run"])
    assert stop.value.code == rt.SETUP_ERROR
    assert "separately" in capsys.readouterr().err


def test_rule4_reproducibility_wording_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _result_dict(tmp_path, monkeypatch, exploratory=True)
    summary = (tmp_path / "node-tar-9.9.9-exploratory" / "summary.md").read_text("utf-8")
    assert "저장된 lock" in summary and "레지스트리 자체가 바뀌었거나" in summary
    assert "커밋된 lock으로 같은" in summary  # contrasted with the verified path


def test_rule5_no_automatic_promotion(tmp_path: Path) -> None:
    before = sorted(p.name for p in reg.VERSIONS_DIR.iterdir())
    docker = FakeDocker()
    _prepare(docker)
    assert sorted(p.name for p in reg.VERSIONS_DIR.iterdir()) == before
    build = next(c for c in docker.calls if c[1] == "build")
    assert not build[-1].startswith(str(reg.REPO_ROOT))
    # the only writes go into the temporary build context (no path into tools/ or locks/)
    source = Path(reg.__file__).read_text(encoding="utf-8")
    assert source.count(".write_") == 2 and "benchmarks/locks" not in source


# ---- containers: no mounts; leftovers from an interrupted run are never used ----


def test_npm_and_check_containers_mount_nothing() -> None:
    docker = FakeDocker()
    _prepare(docker)
    for call in docker.calls:
        if call[1] == "run":
            assert not {"-v", "--volume", "--mount"} & set(call)


def test_each_run_uses_a_fresh_build_context() -> None:
    contexts = []
    for _ in range(2):
        docker = FakeDocker()
        _prepare(docker)
        contexts.append(next(c for c in docker.calls if c[1] == "build")[-1])
    assert contexts[0] != contexts[1]
    assert not any(Path(c).exists() for c in contexts)  # removed after the build


def test_future_version_with_a_new_dependency_is_refused_on_purpose() -> None:
    lock = _lock({"node_modules/brand-new-dep": {"version": "0.1.0"}}, version=V)
    docker = FakeDocker(lock=lock)
    with pytest.raises(reg.RegistryPrepareError, match="brand-new-dep@0.1.0.*committed-lock"):
        _prepare(docker)
    assert docker.images == set()
