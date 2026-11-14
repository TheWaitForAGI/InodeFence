"""decompress registry preparation (exploratory): fail-closed, kept apart from verified."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.decompress_registry_prepare as reg
import scripts.npm_registry as npm
import scripts.run_decompress_target as dt
import scripts.run_target as rt

from inodefence.target_result import EXPLORATORY_LABEL, LABEL

FORK = "@xhmikosr/decompress"
V = "11.2.0"
SPEC = f"{FORK}@{V}"
IMAGE = "inodefence-decompress-registry:xhmikosr-decompress-11.2.0-t"
CLOSURE = {"@xhmikosr/decompress-tar": "8.0.1", "tar-stream": "3.1.7"}


def _integrity(spec: str) -> str:
    return "sha512-" + base64.b64encode(spec.encode()).decode()


def _entry(name: str, version: str) -> dict[str, str]:
    return {
        "version": version,
        "resolved": f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{version}.tgz",
        "integrity": _integrity(f"{name}@{version}"),
    }


def _lock(package: str = FORK, version: str = V, extra: dict | None = None) -> dict[str, Any]:
    packages: dict[str, Any] = {"": {"dependencies": {package: version}}}
    for name, ver in {**CLOSURE, package: version}.items():
        packages[f"node_modules/{name}"] = _entry(name, ver)
    for key, entry in (extra or {}).items():
        packages[key] = {**packages.get(key, {}), **entry}
    return {"lockfileVersion": 3, "packages": packages}


class FakeDocker:
    """docker + npm stand-in; ``fail`` names the step that breaks."""

    def __init__(
        self,
        *,
        fail: str = "",
        lock: dict | None = None,
        installed: tuple[str, str] = (FORK, V),
    ):
        self.fail, self.lock, self.installed = fail, lock or _lock(), installed
        self.latest = V
        self.images: set[str] = set()
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        args = cmd[1:]

        def done(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, code, out, err)

        verb = args[0]
        if verb == "image":
            return done(0 if args[-1] in self.images else 1)
        if verb == "run" and "sh" in args:
            env = dict(a.split("=", 1) for i, a in enumerate(args) if args[i - 1] == "-e")
            if self.fail == "network":
                return done(1, err="npm error code ENOTFOUND\n")
            if "dist-tags.latest" in args[-1]:
                return done(0, self.latest + "\n")
            if "SPECS" in env:
                if self.fail == "missing":
                    return done(1, err="npm error code E404\nnpm error 404 No match found\n")
                lines = [
                    f"{s} {_integrity(s) if self.fail != 'integrity' else 'sha512-X'}"
                    for s in env["SPECS"].split()
                ]
                return done(0, "\n".join(lines) + "\n")
            return done(0, json.dumps(self.lock) + "\n")
        if verb == "build":
            if self.fail == "build":
                return done(1, err="npm ci failed")
            self.images.add(args[args.index("-t") + 1])
            return done()
        if verb == "run":  # offline checks: all with --network none and --pull never
            assert "--network" in args and args[args.index("--network") + 1] == "none"
            assert "--pull" in args and args[args.index("--pull") + 1] == "never"
            program = args[-1]
            if "worker-check" in program:
                return done(0, json.dumps(self.worker_report()) + "\n")
            if "shared_identity" in program:
                if self.fail == "harness":
                    return done(3, err="FATAL decompress is not a function\n")
                tree = {"a.txt": {}, "b.txt": {}}
                raw = {
                    "package": FORK,
                    "package_version": V,
                    "declined": None,
                    "extract_tree": tree,
                }
                return done(0, json.dumps(raw) + "\n")
            return done(0, f"{self.installed[0]} {self.installed[1]}\n")
        if verb == "tag":
            self.images.add(args[2])
            return done()
        if verb == "rmi":
            self.images.discard(args[-1])
            return done()
        raise AssertionError(args)

    def worker_report(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "present": self.fail != "worker-missing",
            "worker_sha256": "d" * 64,
            "identify_status": 0,
            "identity": {"decompress_module": FORK, "decompress_version": V},
            "frame_status": 0,
            "frame": {"schema_version": 1, "attempts": 1, "hardlinks": 1},
            "extracted": True,
            "link_created": True,
        }
        if self.fail == "worker-identity":
            report["identity"] = {"decompress_module": "decompress", "decompress_version": "4.2.1"}
        if self.fail == "worker-api":  # e.g. a new major fork API the worker cannot drive
            report["frame_status"] = 1
            report["frame"] = None
            report["frame_stderr"] = "TypeError: decompress is not a function"
        if self.fail == "worker-crash":
            report["frame_status"] = 3
            report["frame_stderr"] = "harness IO failure"
        if self.fail == "link-refused":  # package resolves the link elsewhere and refuses: still ok
            report["frame_status"] = 2
            report["link_created"] = False
        if self.fail == "worker-blind":  # extracts, but the frame channel sees no operation
            report["frame"] = {"schema_version": 1, "attempts": 0, "hardlinks": 0}
        return report

    def verbs(self) -> list[str]:
        return [c[1] for c in self.calls]


def _prepare(docker: FakeDocker, spec: str = SPEC, image: str = IMAGE) -> str:
    return reg.prepare(spec, image, runner=docker, log=lambda line: None)


# ---- target identity: two packages, exact versions or latest ----


@pytest.mark.parametrize(
    "spec",
    [
        "tar@7.5.23",
        "@someone/decompress@1.0.0",
        "decompress@4.2",
        "decompress@^4.2.0",
        "decompress@next",
        "decompress@4.2.1; rm -rf /",
        "decompress",
    ],
)
def test_other_packages_and_versions_never_reach_docker(spec: str) -> None:
    docker = FakeDocker()
    with pytest.raises(reg.RegistryPrepareError):
        _prepare(docker, spec)
    assert docker.calls == []


def test_both_packages_and_latest_are_accepted_as_specs() -> None:
    assert reg.split_spec("decompress@4.2.0") == ("decompress", "4.2.0")
    assert reg.split_spec(f"{FORK}@latest") == (FORK, "latest")


# ---- success, reuse, failures leave no image ----


def test_success_checks_before_tagging_and_cleans_staging() -> None:
    docker = FakeDocker()
    assert len(_prepare(docker)) == 64
    assert docker.images == {IMAGE}
    build = next(c for c in docker.calls if c[1] == "build")
    assert "ROLE=registry" in build and build[build.index("-t") + 1] == f"{IMAGE}-unverified"
    assert not build[-1].startswith(str(reg.REPO_ROOT))
    assert docker.verbs().index("build") < docker.verbs().index("tag")


def test_existing_image_is_not_rebuilt() -> None:
    docker = FakeDocker()
    docker.images.add(IMAGE)
    _prepare(docker)
    assert docker.verbs() == ["image"]


@pytest.mark.parametrize(
    ("fail", "message"),
    [
        ("missing", "version not found"),
        ("network", "registry unreachable"),
        ("integrity", "integrity differs"),
        ("build", "build failed"),
        ("harness", "harness incompatible"),
        ("worker-missing", "worker incompatible.*worker.cjs is missing"),
        ("worker-identity", "worker incompatible.*identifies decompress@4.2.1"),
        ("worker-api", "worker incompatible.*not a function"),
        ("worker-crash", "worker incompatible.*exit 3"),
        ("worker-blind", "worker incompatible.*observed no hard link"),
    ],
)
def test_failures_leave_no_image(fail: str, message: str) -> None:
    docker = FakeDocker(fail=fail)
    with pytest.raises(reg.RegistryPrepareError, match=message):
        _prepare(docker)
    assert IMAGE not in docker.images and f"{IMAGE}-unverified" not in docker.images


def test_installed_package_mismatch_leaves_no_image() -> None:
    docker = FakeDocker(installed=("decompress", V))
    with pytest.raises(reg.RegistryPrepareError, match="installed, expected"):
        _prepare(docker)
    assert docker.images == set()


def test_non_registry_source_is_refused_before_build() -> None:
    lock = _lock(extra={"node_modules/tar-stream": {"resolved": "https://mirror.example/x.tgz"}})
    docker = FakeDocker(lock=lock)
    with pytest.raises(reg.RegistryPrepareError, match="not resolved from"):
        _prepare(docker)
    assert "build" not in docker.verbs()


def test_new_dependency_is_recorded_not_refused() -> None:
    lock = _lock(extra={"node_modules/brand-new": _entry("brand-new", "1.0.0")})
    lines: list[str] = []
    docker = FakeDocker(lock=lock)
    reg.prepare(SPEC, IMAGE, runner=docker, log=lines.append)
    assert docker.images == {IMAGE}
    assert any("new dependency" in line and "brand-new@1.0.0" in line for line in lines)


def test_containers_mount_nothing_and_npm_uses_the_dockerfile_node() -> None:
    docker = FakeDocker()
    _prepare(docker)
    for call in docker.calls:
        assert not {"-v", "--volume", "--mount"} & set(call)
    npm_calls = [c for c in docker.calls if c[1] == "run" and "sh" in c]
    assert all(npm.node_image(reg.DOCKERFILE) in c for c in npm_calls)
    assert any("--ignore-scripts" in c[-1] for c in npm_calls if "package-lock-only" in c[-1])


# ---- separation rules (verified vs exploratory) ----


def test_rule1_registry_image_is_never_a_verified_name() -> None:
    for image in ("inodefence-decompress:11.2.0", "inodefence-decompress:4.2.1"):
        docker = FakeDocker()
        with pytest.raises(reg.RegistryPrepareError, match="tagged only as"):
            _prepare(docker, image=image)
        assert docker.calls == []
    (cell,) = dt.ADAPTER.cells([SPEC], [])
    assert cell.image_ref is not None
    assert cell.image_ref.startswith(reg.REGISTRY_REPOSITORY + ":")


def test_rule2_committed_recipe_always_takes_the_verified_path() -> None:
    for spec, image in (("decompress@4.2.1", "4.2.1"), (f"{FORK}@11.1.4", "11.1.4")):
        (cell,) = dt.ADAPTER.cells([spec], [])
        assert not cell.exploratory and cell.image_ref == f"inodefence-decompress:{image}"
    docker = FakeDocker()
    with pytest.raises(reg.RegistryPrepareError, match="committed recipe"):
        _prepare(docker, f"{FORK}@11.1.4", image=f"{reg.REGISTRY_REPOSITORY}:x")
    assert docker.calls == []


def test_rule3_and_4_exploratory_result_is_labelled_and_never_mixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _exploratory_result(tmp_path, monkeypatch)
    assert data["label"] == EXPLORATORY_LABEL
    prep = data["preparation"]
    assert (prep["method"], prep["requested_version"], prep["installed_version"]) == (
        "registry",
        SPEC,
        SPEC,
    )
    assert prep["producer_check"].startswith("decompress worker identify+frame ok")
    cell = tmp_path / "decompress-xhmikosr-decompress-11.2.0-exploratory"
    summary = (cell / "summary.md").read_text("utf-8")
    assert "임시 생성 lock" in summary and "탐색 경로(worker) 오프라인 호환 확인" in summary
    assert (cell / "preparation" / "package-lock.json").is_file()
    assert "(exploratory demo run)" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:
        argv = ["--target", "decompress", "--version", "decompress@4.2.1", "--version", SPEC]
        rt.main([*argv, "--dry-run"])
    assert stop.value.code == rt.SETUP_ERROR


def test_rule5_no_automatic_promotion() -> None:
    before = sorted(p.name for p in reg.TOOLS_DIR.iterdir())
    _prepare(FakeDocker())
    assert sorted(p.name for p in reg.TOOLS_DIR.iterdir()) == before
    source = Path(reg.__file__).read_text(encoding="utf-8")
    assert source.count(".write_") == 2 and "benchmarks/locks" not in source


def test_verified_cells_are_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:x")
    monkeypatch.setattr(rt, "engine_provenance", lambda image: rt.Provenance(None, True, image))
    monkeypatch.setattr(dt, "run_one", lambda p, v, t, image=None: _clean(p, v))
    argv = ["--target", "decompress", "--version", f"{FORK}@11.1.4", "--out", str(tmp_path)]
    assert rt.main(argv) == 0
    data = json.loads(
        (tmp_path / "decompress-xhmikosr-decompress-11.1.4" / "result.json").read_text()
    )
    assert data["label"] == LABEL and "preparation" not in data


# ---- latest, adapter wiring ----


def test_latest_resolves_per_package_and_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def resolve(package: str, runner: Any = None) -> str:
        seen.append(package)
        return V

    monkeypatch.setattr(dt.registry, "resolve_latest", resolve)
    data = _exploratory_result(tmp_path, monkeypatch, spec=f"{FORK}@latest")
    assert seen == [FORK]
    assert data["axes"]["target_version"] == SPEC
    assert data["preparation"]["requested_spec"] == f"{FORK}@latest"
    assert data["preparation"]["resolved_at"]
    assert f"RESOLVE decompress {FORK}@latest -> {SPEC}" in capsys.readouterr().out
    dt._RESOLVED.clear()


def test_latest_dry_run_does_not_resolve(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(dt.registry, "resolve_latest", lambda *a: pytest.fail("no lookup"))
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    assert rt.main(["--target", "decompress", "--version", "decompress@latest", "--dry-run"]) == 0
    (name,) = json.loads(capsys.readouterr().out)["cells"]
    assert "resolved at run time" in name


def test_unknown_package_and_no_auto_prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ValueError, match="not this target"):
        dt.ADAPTER.cells(["@someone/decompress@1.0.0"], [])
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: None)
    argv = ["--target", "decompress", "--version", SPEC, "--out", str(tmp_path)]
    assert rt.main(argv) == rt.SETUP_ERROR
    assert "AUTO_PREPARE=1" in capsys.readouterr().err


def test_prepare_step_calls_the_registry_module() -> None:
    (cell,) = dt.ADAPTER.cells([SPEC], [])
    step = dt.ADAPTER.prepare(cell)
    assert step.commands is not None
    assert step.commands[0][1:3] == ("-m", "scripts.decompress_registry_prepare")


def test_generic_npm_helper_names_no_target() -> None:
    text = Path(npm.__file__).read_text(encoding="utf-8")
    for name in ("node-tar", "decompress", "tarfile", "oras", "xhmikosr"):
        assert name not in text


# ---- helpers ----


def _clean(package: str, version: str) -> dict[str, Any]:
    ref = {"ino": "5", "nlink": 1, "size": 10, "type": "reg"}
    return {
        "package": package,
        "package_version": version,
        "declined": None,
        "shared_identity": [],
        "reference_before": ref,
        "reference_after": ref,
    }


def _exploratory_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spec: str = SPEC
) -> dict[str, Any]:
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:reg")
    monkeypatch.setattr(rt, "engine_provenance", lambda image: rt.Provenance(None, True, image))
    monkeypatch.setattr(dt, "run_one", lambda p, v, t, image=None: _clean(p, v))
    lock = json.dumps(_lock()).encode()

    def evidence(image: str, runner: Any = None) -> dict[str, Any]:
        import hashlib

        return {
            "package": FORK,
            "installed_version": V,
            "lock": lock,
            "lock_sha256": hashlib.sha256(lock).hexdigest(),
            "worker_sha256": "d" * 64,
        }

    monkeypatch.setattr(dt.registry, "image_evidence", evidence)
    monkeypatch.setattr(
        dt.registry,
        "worker_check",
        lambda *a: {
            "ok": True,
            "reason": "decompress worker identify+frame ok (1 attempts, 1 hard link)",
            "worker_sha256": "d" * 64,
        },
    )
    argv = ["--target", "decompress", "--version", spec, "--out", str(tmp_path)]
    assert rt.main(argv) == 0
    cell = tmp_path / "decompress-xhmikosr-decompress-11.2.0-exploratory"
    return json.loads((cell / "result.json").read_text())


def test_package_that_refuses_the_internal_link_is_still_worker_compatible() -> None:
    lines: list[str] = []
    docker = FakeDocker(fail="link-refused")
    reg.prepare(SPEC, IMAGE, runner=docker, log=lines.append)
    assert docker.images == {IMAGE}
    assert any("internal link not created (exit 2)" in line for line in lines)
