"""Controlled oracle check (not node-tar): C0/C1/C2 verdicts for four TAR fixtures (P0-3).

The extractor here is trusted test code that follows TAR entries without boundary
checks, so the committed fixtures produce real persistent effects inside the
disposable sandbox. The real pipeline Observer and Oracle judge those effects.
Verdicts validate the Oracle only; they are not node-tar results or findings.

Run: PYTHONPATH=src python -m scripts.oracle_fixture_check
"""

import os
import tarfile
from dataclasses import dataclass
from pathlib import Path

from scripts.generate_tar_fixtures import FIXTURE_ROOT, baseline_case, oracle_case

from inodefence.model import (
    ArchiveCase,
    ExecutionResult,
    ExecutionStatus,
    IdentityEvidence,
    RunResult,
    StateChange,
)
from inodefence.pipeline import run_case

CONTROLLED_LABEL = "controlled oracle check (not node-tar)"
CONTROLLED_EXTRACTOR_ID = "controlled-unchecked-extractor"
CONTRACT_DESCRIPTIONS = (
    "C0: 해제 후 extract/ 밖 경로에 파일이 새로 생기거나, 사라지거나, "
    "다른 inode나 다른 종류로 바뀌면 위반이다(내용·권한만 바뀐 경우는 제외).",
    "C1: 해제가 끝난 시점에 extract/ 안의 객체가 보호 대상 sentinel과 같은 "
    "(st_dev, st_ino)를 가지면 위반이다(symlink는 자기 inode만 비교, 대상은 따라가지 않음).",
    "C2: 보호 대상 sentinel의 존재, 종류, inode, 내용 해시, 크기, mode, nlink, uid/gid, "
    "mtime/ctime 중 하나라도 바뀌면 위반이다(atime 제외).",
)
KNOWN_LIMITATIONS = (
    "C0는 snapshot에 흔적이 남지 않는 extract/ 밖 path 직접 사용은 잡지 못한다.",
    "C0는 archive/ 아래(HARNESS 영역)의 생성·삭제·교체도 위반으로 본다.",
    "실제 파일시스템에서 C1은 단독으로 나오지 않는다: sentinel hardlink는 "
    "sentinel nlink·ctime을 바꿔 C2도 함께 위반된다.",
)


class UncheckedControlledExtractor:
    """Follow entries literally, like an extractor without path or link checks.

    Every resolved write is asserted to stay inside the disposable sandbox, so the
    fixtures can reach outside/ there but never the host. Executes inside the
    BEFORE/AFTER window and writes nothing else.
    """

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        sandbox_root = Path(os.path.realpath(extraction_root.parent))

        def inside(path: Path) -> Path:
            resolved = Path(os.path.realpath(path))
            if not resolved.is_relative_to(sandbox_root):
                raise AssertionError(f"controlled extractor left the sandbox: {path}")
            return path

        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive.getmembers():
                destination = inside(extraction_root / member.name.rstrip("/"))
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    destination.write_bytes(stream.read())
                elif member.issym():
                    os.symlink(member.linkname, destination)
                elif member.islnk():
                    os.link(inside(extraction_root / member.linkname), destination)
                else:
                    raise AssertionError(f"unexpected controlled TAR member: {member.name}")
        return ExecutionResult(
            CONTROLLED_EXTRACTOR_ID, "1", (), ExecutionStatus.SUCCESS, 0, "", "", 0.0
        )


@dataclass(frozen=True, slots=True)
class OracleFixture:
    name: str
    fixture: Path
    case: ArchiveCase
    expected: tuple[bool, bool, bool]  # (C0, C1, C2) violated
    reason: str


ORACLE_FIXTURES = (
    OracleFixture(
        "normal",
        FIXTURE_ROOT / "hardlink" / "fixture.tar",
        baseline_case("hardlink"),
        (False, False, False),
        "a.txt와 b.txt가 inode를 공유하지만 둘 다 extract/ 안이라 sentinel과 무관하다.",
    ),
    OracleFixture(
        "c0",
        FIXTURE_ROOT / "oracle-c0" / "fixture.tar",
        oracle_case("oracle-c0"),
        (True, False, False),
        "regular ../escape.txt가 extract/ 밖(sandbox 루트)에 새 파일을 만든다.",
    ),
    OracleFixture(
        "c1",
        FIXTURE_ROOT / "oracle-c1" / "fixture.tar",
        oracle_case("oracle-c1"),
        (False, True, True),
        "hardlink alias -> ../outside/sentinel.txt: extract/alias가 sentinel inode를 공유하고 "
        "sentinel nlink·ctime도 바뀐다(C1 단독이 아니라 C1+C2).",
    ),
    OracleFixture(
        "c2",
        FIXTURE_ROOT / "oracle-c2" / "fixture.tar",
        oracle_case("oracle-c2"),
        (False, False, True),
        "symlink link -> ../outside/sentinel.txt 뒤 regular link 쓰기가 sentinel 내용을 바꾼다.",
    ),
)


def run_oracle_fixture(fixture: OracleFixture) -> RunResult:
    return run_case(fixture.case, UncheckedControlledExtractor())


def _evidence(item: StateChange | IdentityEvidence) -> str:
    if isinstance(item, IdentityEvidence):
        return f"{item.internal_path} == {item.sentinel_path} (dev:ino {item.st_dev}:{item.st_ino})"
    return f"{item.path}: {', '.join(field.value for field in item.fields)}"


def render_oracle_fixture(fixture: OracleFixture, result: RunResult) -> str:
    """One fixture's verdicts; every rendering starts with the controlled label."""
    lines = [
        f"[{CONTROLLED_LABEL}] extractor={result.execution.target_id} "
        "(TAR entry를 경계 검사 없이 따르는 통제 extractor)",
        f"fixture {fixture.name}: {fixture.fixture.relative_to(FIXTURE_ROOT.parents[2])}",
        f"  input: {fixture.reason}",
    ]
    for verdict, expected in zip(result.violations, fixture.expected, strict=True):
        state = "VIOLATED" if verdict.violated else "not violated"
        match = "expected" if verdict.violated == expected else "UNEXPECTED"
        lines.append(f"  {verdict.contract_id.value}: {state} ({match})")
        lines.extend(f"    evidence: {_evidence(item)}" for item in verdict.evidence)
    return "\n".join(lines) + "\n"


def render_contract_legend() -> str:
    lines = ["판정 기준 (현재 Oracle 코드 기준):"]
    lines.extend(f"  {text}" for text in CONTRACT_DESCRIPTIONS)
    lines.append("알려진 한계:")
    lines.extend(f"  - {text}" for text in KNOWN_LIMITATIONS)
    return "\n".join(lines) + "\n"


def main() -> int:
    print(render_contract_legend())
    unexpected = 0
    for fixture in ORACLE_FIXTURES:
        result = run_oracle_fixture(fixture)
        print(render_oracle_fixture(fixture, result))
        unexpected += tuple(v.violated for v in result.violations) != fixture.expected
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
