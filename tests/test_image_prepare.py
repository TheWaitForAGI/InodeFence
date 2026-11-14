"""Image preparation: generic helper + each target's recipe (no docker: a fake CLI plays it)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.decompress_image as dci
import scripts.image_prepare as ip
import scripts.node_tar_image as nti
import scripts.run_oras_go_target as rog
import scripts.run_python_tarfile_target as rpt

PREPARE = {
    "node-tar": nti.prepare,
    "python-tarfile": rpt.prepare_image,
    "oras-go": rog.prepare_image,
    "decompress": dci.prepare,
}


class ti:  # noqa: N801 - test-local facade over the four target modules
    UnsupportedVersionError = ip.UnsupportedVersionError
    ImagePrepareError = ip.ImagePrepareError

    @staticmethod
    def prepare(target: str, version: str, image_ref: str, runner: Any) -> ip.PreparedImage:
        return PREPARE[target](version, image_ref, runner)


class FakeDocker:
    """Minimal docker CLI: images by ref, build/pull that may fail, a version per image."""

    def __init__(self, images: dict[str, str] | None = None, *, reports: str = "", fail: str = ""):
        self.images = dict(images or {})  # ref -> what the offline version check prints
        self.reports = reports  # what a newly built/pulled image prints
        self.fail = fail  # "build" | "pull" | "check"
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "docker"
        args = cmd[1:]
        self.calls.append(args)
        verb = args[0]

        def done(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, code, out, err)

        if verb == "image":
            ref = args[-1]
            return done(0, f"sha256:{abs(hash(ref)):x}\n") if ref in self.images else done(1)
        if verb == "build":
            if self.fail == "build":
                return done(1, err="npm ERR! boom")
            self.images[args[args.index("-t") + 1]] = self.reports
            return done(0, "sha256:new\n")
        if verb == "pull":
            if self.fail == "pull":
                return done(1, err="manifest unknown")
            self.images[args[-1]] = self.reports
            return done()
        if verb == "tag":
            self.images[args[2]] = self.images[args[1]]
            return done()
        if verb == "run":
            assert args[1:4] == ["--rm", "--network", "none"]
            ref = next(a for a in args if a in self.images)
            if self.fail == "check":
                return done(1, err="exec failed")
            return done(0, self.images[ref] + "\n")
        raise AssertionError(args)

    def verbs(self) -> list[str]:
        return [c[0] for c in self.calls]


# ---- version validation and supported range (read from committed recipes) ----


@pytest.mark.parametrize(
    ("target", "version"),
    [
        ("node-tar", "7.5"),
        ("node-tar", "7.5.2; rm -rf /"),
        ("python-tarfile", "3.12"),
        ("oras-go", "v2.6.1"),
        ("decompress", "4.2.1"),
        ("decompress", "decompress@4.2.1 --build-arg X=1"),
    ],
)
def test_malformed_version_never_reaches_docker(target: str, version: str) -> None:
    docker = FakeDocker()
    with pytest.raises(ti.UnsupportedVersionError):
        ti.prepare(target, version, "inodefence-dev/x:1", docker)
    assert docker.calls == []


@pytest.mark.parametrize(
    ("target", "version", "reason"),
    [
        ("node-tar", "7.5.4", "no committed lock"),
        ("oras-go", "2.6.3", "buildable: 2.6.1, 2.6.2"),
        ("decompress", "decompress@11.1.4", "different packages"),
        ("decompress", "@xhmikosr/decompress@4.2.1", "not pinned"),
    ],
)
def test_unsupported_version_is_refused_with_reason(target: str, version: str, reason: str) -> None:
    docker = FakeDocker()
    with pytest.raises(ti.UnsupportedVersionError, match=reason):
        ti.prepare(target, version, "inodefence-dev/x:1", docker)
    assert docker.calls == []


def test_supported_recipes_come_from_committed_files() -> None:
    node = nti.recipe("7.4.4")
    assert node.build == (
        "-f",
        "tools/node-tar/effect/Dockerfile",
        "--build-arg",
        "TAR_VERSION=7.4.4",
    )
    assert rog.image_recipe("2.6.1").build[-1] == "ROLE=affected"  # type: ignore[index]
    assert rog.image_recipe("2.6.2").expected == "v2.6.2"
    fork = dci.recipe("@xhmikosr/decompress@11.1.4")
    assert fork.build[-1] == "ROLE=fixed"  # type: ignore[index]
    assert fork.expected == "@xhmikosr/decompress 11.1.4"
    assert dci.recipe("decompress@4.2.1").expected == "decompress 4.2.1"
    assert rpt.image_recipe("3.12.16").pull == "python:3.12.16-slim"


def test_node_tar_lock_must_pin_the_requested_version(tmp_path: Path) -> None:
    version_dir = tmp_path / "9.9.9"
    version_dir.mkdir(parents=True)
    (version_dir / "package.json").write_text(json.dumps({"dependencies": {"tar": "9.9.8"}}))
    (version_dir / "package-lock.json").write_text("{}")
    with pytest.raises(ti.UnsupportedVersionError, match="9.9.8"):
        nti.recipe("9.9.9", versions_dir=tmp_path)


# ---- reuse, prepare, verify ----


def test_existing_image_is_reused_without_build() -> None:
    docker = FakeDocker({"inodefence-oras-go:2.6.1": json.dumps({"oras_go_version": "v2.6.1"})})
    got = ti.prepare("oras-go", "2.6.1", "inodefence-oras-go:2.6.1", docker)
    assert got.prepared is False and got.observed == "v2.6.1"
    assert "build" not in docker.verbs() and "pull" not in docker.verbs()


def test_missing_image_is_built_then_verified() -> None:
    docker = FakeDocker(reports="7.4.4")
    got = ti.prepare("node-tar", "7.4.4", "inodefence-dev/node-tar-effect:7.4.4", docker)
    assert got.prepared is True and got.observed == "7.4.4"
    build = next(c for c in docker.calls if c[0] == "build")
    assert build[-3:] == ["-t", "inodefence-dev/node-tar-effect:7.4.4", "."]
    assert docker.verbs().index("build") < docker.verbs().index("run")


def test_version_mismatch_inside_image_is_an_error() -> None:
    docker = FakeDocker(reports="decompress 4.2.0")
    with pytest.raises(ti.ImagePrepareError, match="expected 'decompress 4.2.1'"):
        ti.prepare("decompress", "decompress@4.2.1", "inodefence-dev/decompress:4.2.1", docker)


def test_existing_image_with_wrong_contents_is_an_error_not_rebuilt() -> None:
    docker = FakeDocker({"inodefence-dev/node-tar-effect:7.5.2": "7.5.3"})
    with pytest.raises(ti.ImagePrepareError, match="contains '7.5.3'"):
        ti.prepare("node-tar", "7.5.2", "inodefence-dev/node-tar-effect:7.5.2", docker)
    assert "build" not in docker.verbs()


@pytest.mark.parametrize("step", ["build", "check"])
def test_build_or_check_failure_is_an_error(step: str) -> None:
    docker = FakeDocker(reports=json.dumps({"oras_go_version": "v2.6.2"}), fail=step)
    with pytest.raises(ti.ImagePrepareError, match="failed"):
        ti.prepare("oras-go", "2.6.2", "inodefence-dev/oras-go:2.6.2", docker)


def test_python_pull_only_when_official_tag_is_absent() -> None:
    absent = FakeDocker(reports="3.12.10")
    got = ti.prepare("python-tarfile", "3.12.10", "inodefence-dev/python:3.12.10-slim", absent)
    assert got.prepared is True
    assert ["pull", "-q", "python:3.12.10-slim"] in absent.calls
    assert ["tag", "python:3.12.10-slim", "inodefence-dev/python:3.12.10-slim"] in absent.calls

    present = FakeDocker({"python:3.12.16-slim": "3.12.16"})
    ti.prepare("python-tarfile", "3.12.16", "inodefence-dev/python:3.12.16-slim", present)
    assert "pull" not in present.verbs()  # a local official tag is never moved by a re-pull


def test_python_pull_failure_is_an_error() -> None:
    docker = FakeDocker(fail="pull")
    with pytest.raises(ti.ImagePrepareError, match="pull python:3.99.0-slim failed"):
        ti.prepare("python-tarfile", "3.99.0", "python:3.99.0-slim", docker)


def test_docker_unavailable_is_an_error() -> None:
    def missing(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker")

    with pytest.raises(ti.ImagePrepareError, match="FileNotFoundError"):
        ti.prepare("oras-go", "2.6.1", "inodefence-oras-go:2.6.1", missing)


def test_python_pull_is_only_the_official_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rpt.pti, "IMAGE", "evil.example/python:{runtime}-slim")
    docker = FakeDocker()
    with pytest.raises(ti.UnsupportedVersionError, match="not the official runtime tag"):
        ti.prepare("python-tarfile", "3.12.16", "inodefence-dev/python:3.12.16-slim", docker)
    assert docker.calls == []


def test_generic_helper_names_no_target() -> None:
    text = Path(ip.__file__).read_text(encoding="utf-8")
    for name in ("node-tar", "node_tar", "python-tarfile", "oras", "decompress", "tarfile"):
        assert name not in text
