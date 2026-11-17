"""oras-go's opt-in artifact layout (BACKLOG P-3): the same case, sent as generated and sent
with its entry names under ``d/``, compared.

What these tests are, and are not. The backend below is a **stand-in** for oras-go's geometry,
written from the worker's stated behaviour (``tools/oras-go/worker/main.go``): a member whose
name is not under ``d/`` is refused before anything is extracted, members unpack under
``<dest>/d``, and a hard-link target is resolved under ``<dest>/d`` (fixed releases) or against
the working directory, the sandbox root (the affected release). It is not oras-go. The tests pin
what OUR code does around that geometry -- which bytes are sent, what the unchanged observer and
oracle then judge, what is stored -- and the real extractor's behaviour is checked separately by a
demo run (``scripts/dev/product_e2e.py --target oras-go``).

No docker. The oracle, observer, generator and mutator are imported unchanged.
"""

from __future__ import annotations

import io
import json
import os
import tarfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from inodefence.builder import build_tar
from inodefence.effect_pipeline_oras_go import oras_go_wire_tar, run_oras_go_frame_case
from inodefence.execution.base import ContainerOutcome, ExecutionBackend
from inodefence.feedback.boundary_attempt_frame import FRAME_FORMAT
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, ExecutionStatus
from inodefence.model.filesystem import Region, path_region
from inodefence.tar_reader import read_builder_tar
from inodefence.targets.oras_go_effect import (
    ARTIFACT_DIR,
    ARTIFACT_LAYOUT,
    OrasGoFrameTarget,
    under_artifact_dir,
)

_IMAGE = "sha256:" + "a" * 64
_NEEDS_SANDBOX = pytest.mark.skipif(
    not Path("/var/lib/inodefence").is_dir(),
    reason="disposable sandbox requires the Linux runtime root (Dev Container)",
)

_REGULAR = ArchiveEntry("a.txt", EntryType.REGULAR, content=b"a")
#: A hard link whose target names the protected external file with no ``..`` (the controlled
#: shape ``verify`` uses for oras-go; not a fuzzer finding).
_EXTERNAL_HARDLINK = ArchiveCase(
    (ArchiveEntry("evil", EntryType.HARDLINK, link_target="outside/sentinel.txt"),)
)
_INTERNAL_HARDLINK = ArchiveCase(
    (_REGULAR, ArchiveEntry("b.txt", EntryType.HARDLINK, link_target="a.txt"))
)


class _OrasGoGeometry(ExecutionBackend):
    """Stand-in for the worker's ``frame`` command (see the module docstring)."""

    def __init__(self, *, affected: bool) -> None:
        self.affected = affected
        self.member_names: list[str] = []

    def validate_image(self, image_id: str) -> None:
        assert image_id == _IMAGE

    def policy(self, image_id):  # pragma: no cover - unused on the prepare path
        raise AssertionError("not used")

    def capture_isolation(self, image_id):  # pragma: no cover - unused on the prepare path
        raise AssertionError("not used")

    @contextmanager
    def prepare(self, request):
        command = request.command
        if "identify" in command:
            identity = json.dumps(
                {
                    "oras_go_version": "v2.6.1" if self.affected else "v2.6.2",
                    "go_version": "go1.25.14",
                    "worker_sha256": "b" * 64,
                }
            ).encode()

            class _Identity:
                def execute(self) -> ContainerOutcome:
                    return ContainerOutcome(0, identity, b"", 0.0, False)

            yield _Identity()
            return

        archive, dest = Path(command[2]), Path(command[3])
        backend = self

        class _Frame:
            def execute(self) -> ContainerOutcome:
                with tarfile.open(fileobj=io.BytesIO(archive.read_bytes())) as tar:
                    members = tar.getmembers()
                    backend.member_names = [member.name for member in members]
                    prefix = f"{ARTIFACT_DIR}/"
                    if any(not member.name.startswith(prefix) for member in members):
                        return ContainerOutcome(2, b"", b"member outside the artifact", 0.0, False)
                    artifact = dest / ARTIFACT_DIR
                    artifact.mkdir(parents=True, exist_ok=True)
                    for member in members:
                        path = dest / member.name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if member.isdir():
                            path.mkdir(exist_ok=True)
                        elif member.islnk():
                            base = dest.parent if backend.affected else artifact
                            try:
                                os.link(base / member.linkname, path)
                            except OSError:
                                return ContainerOutcome(2, b"", b"link refused", 0.0, False)
                        elif member.issym():
                            os.symlink(member.linkname, path)
                        else:
                            source = tar.extractfile(member)
                            path.write_bytes(source.read() if source else b"")
                frame = {
                    "format": FRAME_FORMAT,
                    "schema_version": 1,
                    "extractor": "stand-in",
                    "extraction_root_absolute": str(dest),
                    "attempts": [],
                }
                return ContainerOutcome(0, (json.dumps(frame) + "\n").encode(), b"", 0.0, False)

        yield _Frame()


def _run(case: ArchiveCase, *, affected: bool, layout: bool):
    backend = _OrasGoGeometry(affected=affected)
    target = OrasGoFrameTarget.bind(backend, _IMAGE)
    run = run_oras_go_frame_case(case, target, artifact_layout=layout)
    return run, backend


def _violated(run) -> tuple[bool, bool, bool]:
    c0, c1, c2 = run.base_result.violations
    return (c0.violated, c1.violated, c2.violated)


def _extracted(run) -> set[str]:
    before = {obj.path for obj in run.base_result.before.objects}
    return {obj.path for obj in run.base_result.after.objects} - before


# --- the mapping itself -----------------------------------------------------------------------


def test_only_relative_entry_names_move_under_the_artifact_dir() -> None:
    case = ArchiveCase(
        (
            ArchiveEntry("dir", EntryType.DIRECTORY, mode=0o755),
            ArchiveEntry("dir/a.txt", EntryType.REGULAR, content=b"x", mode=0o600),
            ArchiveEntry("dir/hard", EntryType.HARDLINK, link_target="dir/a.txt"),
            ArchiveEntry("dir/soft", EntryType.SYMLINK, link_target="../dir/a.txt"),
            ArchiveEntry("../up", EntryType.REGULAR, content=b"u"),
            ArchiveEntry("/abs", EntryType.REGULAR, content=b"z"),
        )
    )
    moved = under_artifact_dir(case)
    assert [entry.path for entry in moved.entries] == [
        "d/dir",
        "d/dir/a.txt",
        "d/dir/hard",
        "d/dir/soft",
        "d/../up",
        "/abs",  # an absolute name does not depend on where the archive unpacks
    ]
    # Types, order, contents, modes and BOTH kinds of link target are untouched.
    for before, after in zip(case.entries, moved.entries, strict=True):
        assert (after.entry_type, after.content, after.mode) == (
            before.entry_type,
            before.content,
            before.mode,
        )
        assert after.link_target == before.link_target


def test_default_wire_bytes_are_the_case_as_built() -> None:
    for case in (*minimal_seed_corpus(), _EXTERNAL_HARDLINK, ArchiveCase(())):
        assert oras_go_wire_tar(case) == build_tar(case)
        assert oras_go_wire_tar(case, artifact_layout=False) == build_tar(case)


def test_layout_changes_only_the_sent_bytes_not_the_case() -> None:
    case = _INTERNAL_HARDLINK
    case_id = case.case_id
    sent = oras_go_wire_tar(case, artifact_layout=True)
    assert sent == build_tar(under_artifact_dir(case)) != build_tar(case)
    assert case.case_id == case_id and [e.path for e in case.entries] == ["a.txt", "b.txt"]


def test_a_stored_input_is_replayed_without_a_second_prefix() -> None:
    # Replay reads the stored bytes back into a case and runs it with the layout off.
    stored = oras_go_wire_tar(_INTERNAL_HARDLINK, artifact_layout=True)
    replayed = read_builder_tar(stored)
    assert [entry.path for entry in replayed.entries] == ["d/a.txt", "d/b.txt"]
    assert oras_go_wire_tar(replayed) == stored  # same bytes run again, never ``d/d/``


def test_leaving_the_artifact_dir_by_name_stays_inside_the_judged_region() -> None:
    # The judged extraction region is still <dest> ("extract/"), not <dest>/d: one ``..`` from an
    # entry name lands in extract/, and it takes a second one to reach the sandbox root.
    assert path_region("extract/d/a.txt") is Region.EXTRACTION
    assert path_region("extract/up") is Region.EXTRACTION  # d/../up
    assert path_region("up") is Region.EXTERNAL  # d/../../up
    assert path_region("outside/sentinel.txt") is Region.EXTERNAL


# --- the same input, before and after ----------------------------------------------------------


@_NEEDS_SANDBOX
@pytest.mark.parametrize("affected", [True, False])
def test_seeds_are_refused_as_generated_and_extracted_under_the_artifact_dir(
    affected: bool,
) -> None:
    for seed in minimal_seed_corpus():
        as_generated, sent_plain = _run(seed, affected=affected, layout=False)
        assert as_generated.base_result.execution.status is ExecutionStatus.REJECTED
        assert not any(name.startswith("d/") for name in sent_plain.member_names)
        assert _extracted(as_generated) == set()
        assert _violated(as_generated) == (False, False, False)

    regular = minimal_seed_corpus()[0]
    moved, sent = _run(regular, affected=affected, layout=True)
    assert all(name.startswith("d/") for name in sent.member_names)
    assert moved.base_result.execution.status is ExecutionStatus.SUCCESS
    created = _extracted(moved)
    assert created and all(path.startswith("extract/d") for path in created)
    assert _violated(moved) == (False, False, False)
    assert moved.base_result.case == regular  # the recorded case is the logical one


@_NEEDS_SANDBOX
def test_recorded_archive_hash_is_of_the_bytes_that_ran() -> None:
    from hashlib import sha256

    case = minimal_seed_corpus()[0]
    plain, _ = _run(case, affected=False, layout=False)
    moved, _ = _run(case, affected=False, layout=True)
    assert plain.base_result.archive_sha256 == sha256(build_tar(case)).hexdigest()
    assert (
        moved.base_result.archive_sha256
        == sha256(oras_go_wire_tar(case, artifact_layout=True)).hexdigest()
    )


# --- a hard link to the external file: is the verdict the intended one? -------------------------


@_NEEDS_SANDBOX
def test_external_hardlink_as_generated_never_reaches_the_extractor() -> None:
    # Before: the name "evil" is outside d/, so even the affected geometry refuses it unextracted
    # and there is nothing for the oracle to judge.
    run, _ = _run(_EXTERNAL_HARDLINK, affected=True, layout=False)
    assert run.base_result.execution.status is ExecutionStatus.REJECTED
    assert _violated(run) == (False, False, False)


@_NEEDS_SANDBOX
def test_external_hardlink_under_the_artifact_dir_is_judged_on_the_affected_geometry() -> None:
    # After, affected geometry: the link target resolves against the sandbox root, the extracted
    # object shares the external file's inode, and the UNCHANGED oracle reports identity sharing
    # (C1) and the external file's link-count change (C2). No path or version is in that verdict.
    run, backend = _run(_EXTERNAL_HARDLINK, affected=True, layout=True)
    assert backend.member_names == ["d/evil"]
    assert run.base_result.execution.status is ExecutionStatus.SUCCESS
    assert _violated(run) == (False, True, True)
    assert "extract/d/evil" in _extracted(run)


@_NEEDS_SANDBOX
def test_external_hardlink_under_the_artifact_dir_is_refused_on_the_fixed_geometry() -> None:
    # After, fixed geometry: the same target resolves under <dest>/d, where no such file exists.
    run, _ = _run(_EXTERNAL_HARDLINK, affected=False, layout=True)
    assert run.base_result.execution.status is ExecutionStatus.REJECTED
    assert _violated(run) == (False, False, False)
    assert _extracted(run) <= {"extract/d"}


@_NEEDS_SANDBOX
def test_internal_hardlink_under_the_artifact_dir_is_not_a_violation() -> None:
    # A link between two members of the archive shares an inode INSIDE the extraction region.
    run, _ = _run(_INTERNAL_HARDLINK, affected=False, layout=True)
    assert run.base_result.execution.status is ExecutionStatus.SUCCESS
    assert {"extract/d/a.txt", "extract/d/b.txt"} <= _extracted(run)
    assert _violated(run) == (False, False, False)


# --- option plumbing -----------------------------------------------------------------------------


def test_option_is_forwarded_and_restricted_to_the_oras_go_campaign() -> None:
    import argparse

    from scripts import run_effect_demo as demo

    assert "oras_go_artifact_layout" in demo.DEMO_FORWARDED_ARGUMENTS

    def parse(*argv: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        demo.add_demo_arguments(parser)
        parser.add_argument("mode")
        args = parser.parse_args(list(argv))
        demo.check_demo_arguments(parser, args)
        return args

    on = parse("--oras-go-artifact-layout", ARTIFACT_LAYOUT, demo.ORAS_GO_CAMPAIGN_MODE)
    assert on.oras_go_artifact_layout == "artifact-dir"
    assert parse(demo.ORAS_GO_CAMPAIGN_MODE).oras_go_artifact_layout is None  # default: off
    with pytest.raises(SystemExit):
        parse("--oras-go-artifact-layout", ARTIFACT_LAYOUT, "effect-demo")
    with pytest.raises(SystemExit):
        parse("--oras-go-artifact-layout", "other", demo.ORAS_GO_CAMPAIGN_MODE)


def test_recording_producer_stores_the_bytes_that_ran() -> None:
    import base64

    from scripts.container_controller import oras_go_recording_producer

    class _Verdict:
        def __init__(self, cid: str, violated: bool) -> None:
            self.contract_id = type("C", (), {"value": cid})()
            self.violated = violated

    class _Hit:
        base_result = type(
            "B",
            (),
            {
                "execution": type("E", (), {"status": ExecutionStatus.SUCCESS})(),
                "violations": (_Verdict("C0", False), _Verdict("C1", True), _Verdict("C2", True)),
            },
        )()

    def stored(wire_tar) -> bytes:
        produce, _records, inputs = oras_go_recording_producer(lambda case: _Hit(), wire_tar)
        produce(_EXTERNAL_HARDLINK)
        return base64.b64decode(str(inputs[0]["tar_b64"]))

    assert stored(None) == build_tar(_EXTERNAL_HARDLINK)  # default: unchanged
    moved = stored(lambda case: oras_go_wire_tar(case, artifact_layout=True))
    assert moved == build_tar(under_artifact_dir(_EXTERNAL_HARDLINK))
