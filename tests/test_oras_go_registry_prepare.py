"""oras-go Go-proxy preparation (exploratory): every failure leaves no image (no docker here)."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.oras_go_registry_prepare as prep
import scripts.run_oras_go_target as rog
import scripts.run_target as rt

from inodefence.target_result import EXPLORATORY_LABEL, LABEL, load_target_result

V = "2.6.0"
IMAGE = "inodefence-oras-go-registry:2.6.0-t"
SHA = "a" * 64
DEPS = {
    "github.com/opencontainers/go-digest": "v1.0.0",
    "github.com/opencontainers/image-spec": "v1.1.1",
    "golang.org/x/sync": "v0.14.0",
}


def _h1(text: str) -> str:
    return "h1:" + base64.b64encode(text.encode()).decode()


def _gosum(version: str = V, extra: dict[str, str] | None = None) -> str:
    lines = []
    for module, ver in {**DEPS, prep.MODULE: f"v{version}", **(extra or {})}.items():
        lines.append(f"{module} {ver} {_h1(module + ver)}")
        lines.append(f"{module} {ver}/go.mod {_h1(module + ver + 'mod')}")
    return "\n".join(sorted(lines)) + "\n"


def _gomod(version: str = V, go: str = "1.25.14") -> str:
    return f"module worker\n\ngo {go}\n\nrequire (\n\toras.land/oras-go/v2 v{version}\n)\n"


def _generated(gomod: str, gosum: str, tamper: str = "", go: str = "go1.25.14") -> str:
    out = [
        f"GOMOD {base64.b64encode(gomod.encode()).decode()}",
        f"GOSUM {base64.b64encode(gosum.encode()).decode()}",
        f"GOVERSION {go}",
        "BASEGO go1.25.14",
    ]
    modules = sorted(
        {
            f"{line.split()[0]}@{line.split()[1].removesuffix('/go.mod')}"
            for line in gosum.splitlines()
        }
    )
    for spec in modules:
        module, version = spec.split("@")
        body = "\n".join(
            line for line in gosum.splitlines() if line.startswith(f"{module} {version}")
        )
        if spec == tamper:
            body = body.replace("h1:", "h1:X", 1)
        body = f"123\n{body}\n\ngo.sum database tree\n— sum.golang.org Az3g==\n"
        out.append(f"LOOKUP {spec} {base64.b64encode(body.encode()).decode()}")
    return "\n".join(out) + "\n"


class FakeDocker:
    """docker + go-in-container stand-in. ``fail`` names the step that breaks."""

    def __init__(self, *, fail: str = "", version: str = V, installed: str = V) -> None:
        self.fail = fail
        self.version = version
        self.installed = installed
        self.latest = "v2.7.0"
        self.gomod = _gomod(version)
        self.gosum = _gosum(version)
        self.tamper = ""
        self.needs_go = ""  # e.g. "1.26.0": the module requires a newer Go than the base
        self.built_go = ""  # what the built worker reports (default: the toolchain in use)
        self.images: dict[str, dict[str, str]] = {}
        self.dockerfiles: list[str] = []
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        self.calls.append(cmd)
        args = cmd[1:]

        def done(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[Any]:
            return subprocess.CompletedProcess(cmd, code, out, err)

        verb = args[0]
        if verb == "image":
            ref = args[-1]
            if ref not in self.images:
                return done(1, err="No such image")
            if "{{.Id}}" in args:
                return done(0, "sha256:" + SHA)
            if "{{json .Config.Labels}}" in args:
                return done(0, json.dumps(self.images[ref]))
            return done(0)
        if verb == "run" and "sh" in args:  # go in the pinned golang container
            env = dict(a.split("=", 1) for i, a in enumerate(args) if args[i - 1] == "-e")
            self.envs.append(env)
            if self.fail == "network":
                return done(1, err="go: dial tcp: lookup proxy.golang.org: no such host")
            if self.fail == "env":
                return done(7, err="INODEFENCE-ENV checksum verification would be skipped: x")
            if "V" not in env:
                return done(0, self.latest + "\n")
            if self.fail == "missing":
                return done(
                    1,
                    err="go: oras.land/oras-go/v2@v9.9.9: invalid version: unknown revision v9.9.9",
                )
            if self.fail == "checksum":
                return done(
                    1,
                    err="verifying oras.land/oras-go/v2@v2.6.0: checksum mismatch\nSECURITY ERROR",
                )
            tc = env.get("TC")
            if self.needs_go and tc is None:
                return done(
                    1,
                    err=f"go: x@v{self.version} requires go >= {self.needs_go} "
                    "(running go 1.25.14; GOTOOLCHAIN=local)",
                )
            if tc is not None and self.fail == "toolchain-download":
                return done(9, err=f"go: download {tc}: golang.org/toolchain: 404 Not Found")
            if tc is not None and self.fail == "toolchain-checksum":
                return done(9, err=f"go: download {tc}: verifying module: checksum mismatch")
            if self.needs_go:
                gomod = _gomod(self.version, self.needs_go)
                return done(0, _generated(gomod, self.gosum, self.tamper, tc or "go1.25.14"))
            if self.fail == "toolchain":
                return done(
                    1,
                    err="go: x@v2.7.0 requires go >= 1.26.0 (running go 1.25.14)",
                )
            return done(0, _generated(self.gomod, self.gosum, self.tamper))
        if verb == "build":
            if self.fail == "compile":
                return done(
                    1,
                    err="#9 ./main.go:93:20: undefined: file.AnnotationUnpack\n"
                    "#9 ./main.go:93:20: undefined: file.AnnotationUnpack\nERROR: failed",
                )
            dockerfile = Path(args[args.index("-f") + 1])
            self.dockerfiles.append(dockerfile.read_text(encoding="utf-8"))
            labels = dict(args[i + 1].split("=", 1) for i, a in enumerate(args) if a == "--label")
            self.images[args[args.index("-t") + 1]] = labels
            return done()
        if verb == "run" and args[-1] == "identify":
            installed = "v" + self.installed
            go = self.built_go or (f"go{self.needs_go}" if self.needs_go else "go1.25.14")
            meta = {"oras_go_version": installed, "go_version": go, "worker_sha256": SHA}
            return done(0, json.dumps(meta))
        if verb == "create":
            return done(0, "cid123\n")
        if verb == "cp":
            assert isinstance(kwargs.get("input"), bytes)
            return done(0)
        if verb == "start":
            if self.fail == "frame":
                return done(3, err="unknown subcommand: frame")
            frame = {
                "format": "inodefence-boundary-attempt-v1",
                "schema_version": 1,
                "extractor": f"{prep.MODULE}@v{self.installed}",
                "extraction_root_absolute": "/work/extract",
                "attempts": [
                    {
                        "created_path": "extract/d/ok.txt",
                        "operation": "regular",
                        "aliases_external_object": False,
                    }
                ],
            }
            return done(0, json.dumps(frame) + "\n")
        if verb == "rm":
            return done()
        if verb == "tag":
            self.images[args[2]] = self.images[args[1]]
            return done()
        if verb == "rmi":
            self.images.pop(args[-1], None)
            return done()
        raise AssertionError(cmd)


def _probe(ok: bool = True):
    def probe(tag: str, tar_b64: str, sentinel_b64: str, image: str | None = None) -> dict:
        if not ok:
            return {"_run_error": True}
        return {"declined": None, "extract_tree": {"d": {}, "d/ok.txt": {}}, "shared_identity": []}

    return probe


def _prepare(fake: FakeDocker, version: str = V, image: str = IMAGE, probe_ok: bool = True) -> str:
    return prep.prepare(version, image, runner=fake, probe=_probe(probe_ok), log=lambda _: None)


# ---- input checks happen before any docker call ----


@pytest.mark.parametrize(
    "version",
    [
        "latest",
        "v2.6.0",
        "2.6",
        "^2.6.0",
        "2.6.x",
        "2.6.0-rc.1",
        "v2.6.1-0.20240101000000-abcdef123456",
        "https://example.com/x",
        "../x",
        "2.6.0;id",
    ],
)
def test_non_exact_versions_never_reach_docker(version: str) -> None:
    fake = FakeDocker()
    with pytest.raises(prep.RegistryPrepareError, match="exact X.Y.Z"):
        _prepare(fake, version)
    assert fake.calls == []


@pytest.mark.parametrize(
    "image", ["inodefence-oras-go:2.6.0", "inodefence-oras-go-registry:2.6.0-unverified", "x"]
)
def test_verified_or_odd_image_name_is_refused(image: str) -> None:
    fake = FakeDocker()
    with pytest.raises(prep.RegistryPrepareError):
        _prepare(fake, image=image)
    assert fake.calls == []


@pytest.mark.parametrize("version", ["2.6.1", "2.6.2"])
def test_committed_versions_never_take_the_proxy_path(version: str) -> None:
    fake = FakeDocker()
    with pytest.raises(prep.RegistryPrepareError, match="committed go.mod/go.sum"):
        _prepare(fake, version, f"{prep.REGISTRY_REPOSITORY}:{version}")
    assert fake.calls == []


# ---- the happy path and reuse ----


def test_success_checks_before_tagging_and_cleans_staging() -> None:
    fake = FakeDocker()
    sha = _prepare(fake)
    assert len(sha) == 64
    assert IMAGE in fake.images and f"{IMAGE}-unverified" not in fake.images
    verbs = [c[1] for c in fake.calls]
    assert verbs.index("build") < verbs.index("create") < verbs.index("tag") < verbs.index("rmi")
    labels = fake.images[IMAGE]
    assert base64.b64decode(labels[prep.LABEL_PREFIX + "gosum"]).decode() == fake.gosum
    build = next(c for c in fake.calls if c[1] == "build")
    assert build[build.index("--build-arg") + 1] == "ROLE=registry"
    assert build[build.index("-f") + 1] == str(prep.DOCKERFILE)
    assert not str(build[-1]).startswith(str(prep.REPO_ROOT))  # temporary context


def test_existing_image_is_not_rebuilt() -> None:
    fake = FakeDocker()
    fake.images[IMAGE] = {}
    assert _prepare(fake) == ""
    assert [c[1] for c in fake.calls] == ["image"]


def test_generated_files_are_never_written_into_the_repository() -> None:
    before = sorted(p.relative_to(prep.TOOLS_DIR) for p in prep.TOOLS_DIR.rglob("*"))
    _prepare(FakeDocker())
    assert sorted(p.relative_to(prep.TOOLS_DIR) for p in prep.TOOLS_DIR.rglob("*")) == before


# ---- fail-closed: every failure leaves no image and no staging tag ----


@pytest.mark.parametrize(
    ("fail", "message"),
    [
        ("network", "module proxy unreachable"),
        ("missing", "version not found on https://proxy.golang.org"),
        ("checksum", "checksum mismatch against sum.golang.org"),
        ("toolchain", "toolchain too old"),
        ("env", "refused: INODEFENCE-ENV"),
        ("compile", r"worker incompatible \(compile error\): ./main.go:93:20: undefined"),
        ("frame", r"worker incompatible \(frame\)"),
    ],
)
def test_failures_leave_no_image(fail: str, message: str) -> None:
    fake = FakeDocker(fail=fail)
    with pytest.raises(prep.RegistryPrepareError, match=message):
        _prepare(fake)
    assert IMAGE not in fake.images and f"{IMAGE}-unverified" not in fake.images


def test_compile_error_lines_are_deduplicated() -> None:
    reason = prep.build_failure("./main.go:1:2: a\n./main.go:1:2: a\nmain.go:3:4: b\n")
    assert reason == "worker incompatible (compile error): ./main.go:1:2: a; main.go:3:4: b"


def test_installed_version_mismatch_leaves_no_image() -> None:
    fake = FakeDocker(installed="2.6.1")
    with pytest.raises(prep.RegistryPrepareError, match="reports oras-go 'v2.6.1'"):
        _prepare(fake)
    assert IMAGE not in fake.images and f"{IMAGE}-unverified" not in fake.images


def test_probe_incompatibility_leaves_no_image() -> None:
    fake = FakeDocker()
    with pytest.raises(prep.RegistryPrepareError, match=r"worker incompatible \(probe\)"):
        _prepare(fake, probe_ok=False)
    assert IMAGE not in fake.images


def test_sumdb_lookup_mismatch_fails_before_build() -> None:
    fake = FakeDocker()
    fake.tamper = f"{prep.MODULE}@v{V}"
    with pytest.raises(prep.RegistryPrepareError, match="checksum mismatch against sum.golang.org"):
        _prepare(fake)
    assert "build" not in [c[1] for c in fake.calls]


def test_gomod_pinning_another_version_fails_before_build() -> None:
    fake = FakeDocker()
    fake.gomod = _gomod("2.6.1")
    with pytest.raises(prep.RegistryPrepareError, match="pins oras-go '2.6.1'"):
        _prepare(fake)
    assert "build" not in [c[1] for c in fake.calls]


def test_docker_missing_is_a_prepare_error() -> None:
    def runner(*a: Any, **k: Any) -> Any:
        raise FileNotFoundError("docker")

    with pytest.raises(prep.RegistryPrepareError, match="docker image failed"):
        prep.prepare(V, IMAGE, runner=runner, log=lambda _: None)


# ---- checksum verification is never switched off ----


def test_go_container_keeps_checksum_verification_on() -> None:
    fake = FakeDocker()
    _prepare(fake)
    forbidden = {"GONOSUMDB", "GONOSUMCHECK", "GONOVERIFY", "GOPRIVATE", "GOINSECURE", "GOFLAGS"}
    for env in fake.envs:
        assert not forbidden & set(env) and "GOPROXY" not in env and "GOSUMDB" not in env
    for script in (prep._RESOLVE_SCRIPT, prep._GENERATE_SCRIPT):
        assert "export GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org" in script
        assert "direct" not in script and "GOSUMDB=off" not in script and "-insecure" not in script


def test_containers_mount_nothing() -> None:
    fake = FakeDocker()
    _prepare(fake)
    for call in fake.calls:
        assert "-v" not in call and "--volume" not in call and "--mount" not in call
    checks = [c for c in fake.calls if c[1] in ("create",) or c[-1] == "identify"]
    assert checks and all(
        "--network" in c and c[c.index("--network") + 1] == "none" for c in checks
    )


def test_go_image_is_the_dockerfile_pin() -> None:
    assert prep.go_image().startswith("golang:1.25-bookworm@sha256:")


# ---- new modules are recorded, not refused ----


def test_new_module_is_recorded_not_refused() -> None:
    fake = FakeDocker()
    fake.gosum = _gosum(extra={"example.com/new": "v0.1.0"})
    logs: list[str] = []
    prep.prepare(V, IMAGE, runner=fake, probe=_probe(), log=logs.append)
    assert IMAGE in fake.images
    assert any("new module" in line and "example.com/new@v0.1.0" in line for line in logs)
    found = prep.new_modules(fake.gosum.encode(), prep.committed_modules())
    assert found == [
        {"name": "example.com/new", "version": "v0.1.0", "integrity": _h1("example.com/newv0.1.0")}
    ]


def test_committed_modules_come_from_committed_gosum() -> None:
    assert {prep.MODULE, "golang.org/x/sync"} <= prep.committed_modules()


# ---- latest ----


def test_latest_resolves_to_exact() -> None:
    assert prep.resolve_latest(FakeDocker(), "golang:x") == "2.7.0"


@pytest.mark.parametrize("seen", ["v2.7.0-rc.1", "v2.6.1-0.2024-abc", "2.7.0", ""])
def test_latest_rejects_non_release(seen: str) -> None:
    fake = FakeDocker()
    fake.latest = seen
    with pytest.raises(prep.RegistryPrepareError, match="not an exact release"):
        prep.resolve_latest(fake, "golang:x")


def test_latest_proxy_failure_is_reported() -> None:
    with pytest.raises(prep.RegistryPrepareError, match="unreachable"):
        prep.resolve_latest(FakeDocker(fail="network"), "golang:x")


# ---- the adapter: path selection, labels, preparation record ----


def test_committed_versions_keep_the_verified_cells_unchanged() -> None:
    cells = rog.ADAPTER.cells(["2.6.1", "2.6.2"], [])
    assert [(c.dirname, c.image_ref, c.exploratory) for c in cells] == [
        ("oras-go-2.6.1", "inodefence-oras-go:2.6.1", False),
        ("oras-go-2.6.2", "inodefence-oras-go:2.6.2", False),
    ]
    step = rog.ADAPTER.prepare(cells[0])
    assert step.commands is not None and "ROLE=affected" in step.commands[0]


def test_uncommitted_exact_version_is_an_exploratory_proxy_cell() -> None:
    (cell,) = rog.ADAPTER.cells(["2.6.4"], [])
    assert cell.exploratory and cell.image_ref == "inodefence-oras-go-registry:2.6.4"
    assert cell.dirname == "oras-go-2.6.4-exploratory"
    step = rog.ADAPTER.prepare(cell)
    assert step.commands is not None
    assert step.commands[0][1:] == (
        "-m",
        "scripts.oras_go_registry_prepare",
        "--version",
        "2.6.4",
        "--image",
        "inodefence-oras-go-registry:2.6.4",
    )


@pytest.mark.parametrize("version", ["v2.6.1", "2.6.x", "^2.6", "https://x/y", "a;b", "beta"])
def test_other_tags_are_refused(version: str) -> None:
    with pytest.raises(ValueError, match="dotted numeric"):
        rog.ADAPTER.cells([version], [])


def test_no_separate_permission_flag_exists() -> None:
    source = Path(rog.__file__).read_text(encoding="utf-8") + Path(prep.__file__).read_text(
        encoding="utf-8"
    )
    assert "ALLOW" not in source and "--allow" not in source


def test_latest_dry_run_does_not_resolve(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(prep, "resolve_latest", lambda *a, **k: pytest.fail("resolved"))
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    assert rt.main(["--target", "oras-go", "--version", "latest", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    (cell,) = plan["cells"].values()
    assert cell["exploratory"] and cell["image"] is None
    assert "resolved from https://proxy.golang.org at run time" in cell["would_run"][0]["note"]


def _fake_run_env(monkeypatch: pytest.MonkeyPatch, fake: FakeDocker, hit: bool = False) -> None:
    def probe(tag: str, tar_b64: str, sentinel_b64: str, image: str | None = None) -> dict:
        before = {"dev": "1", "ino": "9", "nlink": 1, "size": 30, "type": "reg"}
        return {
            "declined": {"message": "x"},
            "reference_before": before,
            "reference_after": before,
            "shared_identity": [],
        }

    monkeypatch.setattr(rog.ogh, "run_probe", probe)
    monkeypatch.setattr(prep.subprocess, "run", fake)
    monkeypatch.setattr(rt, "engine_provenance", lambda image: rt.Provenance(None, True, image))
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:" + SHA if ref in fake.images else None)
    monkeypatch.setattr(rog, "_verify_existing", lambda cell, image: None)  # tested on its own


def test_latest_run_is_exploratory_and_records_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeDocker(version="2.7.0", installed="2.7.0")
    image = "inodefence-oras-go-registry:2.7.0"
    _prepare(fake, "2.7.0", image)
    _fake_run_env(monkeypatch, fake)
    monkeypatch.setattr(prep, "resolve_latest", lambda *a, **k: "2.7.0")
    assert rt.main(["--target", "oras-go", "--version", "latest", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "TARGET-RUN RESOLVE oras-go latest -> 2.7.0" in out and EXPLORATORY_LABEL in out
    cell = tmp_path / "oras-go-2.7.0-exploratory"
    result = load_target_result(cell / "result.json")
    assert result.label == EXPLORATORY_LABEL
    p = result.preparation
    assert p is not None and p.method == "registry"
    assert (p.requested_spec, p.requested_version, p.installed_version) == (
        "latest",
        "2.7.0",
        "2.7.0",
    )
    assert p.resolved_at is not None and p.worker_sha256 == SHA
    assert p.producer_check and p.producer_check.startswith("frame worker extracted")
    assert (cell / "preparation" / "go.sum").read_text(encoding="utf-8") == fake.gosum
    assert (cell / "preparation" / "go.mod").read_text(encoding="utf-8") == fake.gomod


def test_describe_mismatch_gives_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker()
    image = f"{prep.REGISTRY_REPOSITORY}:{V}"
    _prepare(fake, V, image)
    fake.installed = "2.6.1"  # the image now reports something else
    _fake_run_env(monkeypatch, fake)
    assert rt.main(["--target", "oras-go", "--version", V, "--out", str(tmp_path)]) == 3
    assert not (tmp_path / f"oras-go-{V}-exploratory" / "result.json").exists()


def test_verified_result_has_no_preparation_and_keeps_the_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker()
    fake.images["inodefence-oras-go:2.6.2"] = {}
    _fake_run_env(monkeypatch, fake)
    assert rt.main(["--target", "oras-go", "--version", "2.6.2", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "oras-go-2.6.2" / "result.json").read_text(encoding="utf-8"))
    assert "preparation" not in data and data["label"] == LABEL
    assert not (tmp_path / "oras-go-2.6.2" / "preparation").exists()


def test_verified_and_exploratory_never_share_one_run(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stop:
        rt.main(
            [
                "--target",
                "oras-go",
                "--version",
                "2.6.2",
                "--version",
                "2.6.4",
                "--out",
                str(tmp_path),
            ]
        )
    assert stop.value.code == 3


def test_unregistered_without_auto_prepare_stops_with_the_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeDocker()
    _fake_run_env(monkeypatch, fake)
    assert rt.main(["--target", "oras-go", "--version", "2.6.4", "--out", str(tmp_path)]) == 3
    assert "AUTO_PREPARE=1" in capsys.readouterr().err
    assert fake.calls == []


# ---- a newer required Go: exact toolchain download, temporary Dockerfile copy only ----


def test_newer_go_downloads_exactly_that_toolchain_and_records_it() -> None:
    fake = FakeDocker(version="2.7.0", installed="2.7.0")
    fake.needs_go = "1.26.0"
    image = "inodefence-oras-go-registry:2.7.0-t"
    committed = prep.DOCKERFILE.read_text(encoding="utf-8")
    logs: list[str] = []
    prep.prepare("2.7.0", image, runner=fake, probe=_probe(), log=logs.append)
    assert image in fake.images
    assert [env.get("TC") for env in fake.envs] == [None, "go1.26.0"]
    assert any("toolchain go1.26.0 downloaded" in line and "내려받음" in line for line in logs)
    (dockerfile,) = fake.dockerfiles
    added = [line for line in dockerfile.splitlines() if line not in committed.splitlines()]
    assert added == [
        "ENV GOTOOLCHAIN=go1.26.0 GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org"
    ]
    assert prep.DOCKERFILE.read_text(encoding="utf-8") == committed
    labels = fake.images[image]
    assert labels[prep.LABEL_PREFIX + "toolchain_required"] == "go1.26.0"
    assert labels[prep.LABEL_PREFIX + "toolchain_used"] == "go1.26.0"
    assert labels[prep.LABEL_PREFIX + "base_image"] == prep.go_image()


def test_base_go_suffices_downloads_nothing_and_uses_the_committed_dockerfile() -> None:
    fake = FakeDocker()
    _prepare(fake)
    assert all("TC" not in env for env in fake.envs)
    assert fake.dockerfiles == [prep.DOCKERFILE.read_text(encoding="utf-8")]
    assert fake.images[IMAGE][prep.LABEL_PREFIX + "toolchain_required"] == "none"


@pytest.mark.parametrize(
    ("fail", "message"),
    [
        ("toolchain-download", "toolchain download failed"),
        ("toolchain-checksum", "checksum mismatch against sum.golang.org"),
    ],
)
def test_toolchain_failures_leave_no_image(fail: str, message: str) -> None:
    fake = FakeDocker(fail=fail, version="2.7.0", installed="2.7.0")
    fake.needs_go = "1.26.0"
    with pytest.raises(prep.RegistryPrepareError, match=message):
        _prepare(fake, "2.7.0", "inodefence-oras-go-registry:2.7.0-t")
    assert fake.images == {} and "build" not in [c[1] for c in fake.calls]


def test_worker_built_by_another_go_leaves_no_image() -> None:
    fake = FakeDocker(version="2.7.0", installed="2.7.0")
    fake.needs_go = "1.26.0"
    fake.built_go = "go1.25.14"
    with pytest.raises(
        prep.RegistryPrepareError, match="built with 'go1.25.14', expected go1.26.0"
    ):
        _prepare(fake, "2.7.0", "inodefence-oras-go-registry:2.7.0-t")
    assert fake.images == {}


@pytest.mark.parametrize("required", ["1.26", "1.26rc1", "1.26.0;id", "1.26.0.1"])
def test_non_exact_required_go_is_refused(required: str) -> None:
    gomod = f"module worker\n\ngo {required}\n".encode()
    with pytest.raises(prep.RegistryPrepareError, match="not an exact Go release"):
        prep.required_toolchain(gomod, "go1.25.14")


@pytest.mark.parametrize(
    ("directives", "expected"),
    [
        ("go 1.25.14\n", None),
        ("go 1.24.0\n", None),
        ("go 1.26.0\n", "go1.26.0"),
        ("go 1.25.0\ntoolchain go1.26.2\n", "go1.26.2"),
    ],
)
def test_required_toolchain(directives: str, expected: str | None) -> None:
    assert (
        prep.required_toolchain(f"module worker\n\n{directives}".encode(), "go1.25.14") == expected
    )


@pytest.mark.parametrize(
    "toolchain", ["auto", "local", "go1.26", "go1.26.0+auto", "go1.26.0\nRUN x"]
)
def test_dockerfile_copy_takes_only_an_exact_release(toolchain: str) -> None:
    with pytest.raises(prep.RegistryPrepareError, match="not an exact Go release"):
        prep.dockerfile_with_toolchain(toolchain)


def test_go_script_refuses_any_other_gotoolchain_value() -> None:
    assert 'GOTOOLCHAIN="${TC:-local}"' in prep._ENV_GUARD
    assert "go1.[0-9]*.[0-9]*)" in prep._ENV_GUARD and "auto" not in prep._ENV_GUARD


# ---- ensure_image: one call for the exploration driver ----


def test_ensure_image_resolves_prepares_and_returns_the_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def resolve_images(adapter, cells, *, auto_prepare):
        (cell,) = cells
        calls.append((cell.image_ref, cell.exploratory, auto_prepare))
        return {cell.image_ref: "sha256:" + SHA}, {}

    monkeypatch.setattr(prep, "resolve_latest", lambda *a, **k: "2.7.0")
    monkeypatch.setattr(rt, "resolve_images", resolve_images)
    got = rog.ensure_image("latest", image_tag_suffix="-t")
    assert got == rog.PreparedOrasGo(
        "latest", "2.7.0", "inodefence-oras-go-registry:2.7.0-t", "sha256:" + SHA, True
    )
    assert calls == [("inodefence-oras-go-registry:2.7.0-t", True, True)]
    verified = rog.ensure_image("2.6.1")
    assert verified.image_ref == "inodefence-oras-go:2.6.1" and not verified.exploratory


def test_ensure_image_raises_the_preparation_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve_images(adapter, cells, *, auto_prepare):
        return {}, {cells[0].image_ref: "preparing x failed (exit 1)"}

    monkeypatch.setattr(rt, "resolve_images", resolve_images)
    with pytest.raises(ValueError, match="preparing x failed"):
        rog.ensure_image("2.6.4")
    with pytest.raises(ValueError, match="dotted numeric"):
        rog.ensure_image("v2.6.4")


def test_selfdiscover_script_takes_a_prepared_image_without_building_it() -> None:
    script = (prep.REPO_ROOT / "scripts" / "local_oras_go_selfdiscover.sh").read_text(
        encoding="utf-8"
    )
    assert 'ORAS_GO_IMAGE="${EXPLORE_IMAGE:-inodefence-oras-go-selfdiscover:' in script
    # status lines name the prepared image, not the unused build role
    assert 'TARGET_DESC="image=$EXPLORE_IMAGE"' in script
    assert "role=$ORAS_GO_ROLE)" not in script
    done = subprocess.run(
        ["bash", str(prep.REPO_ROOT / "scripts" / "local_oras_go_selfdiscover.sh")],
        env={"EXPLORE_IMAGE": "x;rm -rf /", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2 and "plain image reference" in done.stderr


# ---- verify_existing: a present image is reused only if its worker is current ----


def _cell(version: str) -> Any:
    (cell,) = rog.ADAPTER.cells([version], [])
    return cell


def test_verified_image_needs_the_recipe_version_and_a_working_frame_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames: list[tuple[str, str]] = []

    def frame_check(runner, image, version):  # type: ignore[no-untyped-def]
        frames.append((image, version))
        return {"ok": True, "reason": "fine"}

    monkeypatch.setattr(prep, "frame_check", frame_check)
    monkeypatch.setattr(rog, "_recipe_verify", lambda cell, image: None)
    assert rog.ADAPTER.verify_existing is not None
    assert rog.ADAPTER.verify_existing(_cell("2.6.2"), "sha256:x") is None
    assert frames == [("inodefence-oras-go:2.6.2", "2.6.2")]

    monkeypatch.setattr(rog, "_recipe_verify", lambda cell, image: "reports v2.6.1")
    assert rog.ADAPTER.verify_existing(_cell("2.6.2"), "sha256:x") == "reports v2.6.1"
    assert len(frames) == 1  # a wrong version stops before the worker check


def test_proxy_image_skips_the_recipe_and_checks_the_frame_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rog, "_recipe_verify", lambda cell, image: pytest.fail("no recipe"))
    monkeypatch.setattr(
        prep, "frame_check", lambda runner, image, version: {"ok": True, "reason": "fine"}
    )
    assert rog.ADAPTER.verify_existing is not None
    assert rog.ADAPTER.verify_existing(_cell("2.7.0"), "sha256:x") is None


@pytest.mark.parametrize(
    ("check", "message"),
    [
        (
            lambda runner, image, version: {"ok": False, "reason": "unknown subcommand: frame"},
            "worker incompatible (frame) in inodefence-oras-go-registry:2.7.0: unknown "
            "subcommand: frame; rebuild it",
        ),
        (
            lambda runner, image, version: (_ for _ in ()).throw(
                prep.RegistryPrepareError("identify failed")
            ),
            "worker check failed in inodefence-oras-go-registry:2.7.0: identify failed; rebuild it",
        ),
    ],
)
def test_unusable_worker_refuses_reuse_with_a_reason(
    monkeypatch: pytest.MonkeyPatch, check: Any, message: str
) -> None:
    monkeypatch.setattr(prep, "frame_check", check)
    assert rog.ADAPTER.verify_existing is not None
    assert rog.ADAPTER.verify_existing(_cell("2.7.0"), "sha256:x") == message


def test_refused_reuse_gives_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeDocker()
    fake.images["inodefence-oras-go:2.6.2"] = {}
    _fake_run_env(monkeypatch, fake)
    monkeypatch.setattr(rog, "_verify_existing", lambda cell, image: "stale worker; rebuild it")
    assert rt.main(["--target", "oras-go", "--version", "2.6.2", "--out", str(tmp_path)]) == 3
    assert "refused: stale worker; rebuild it" in capsys.readouterr().err
    assert not list(tmp_path.rglob("result.json"))
