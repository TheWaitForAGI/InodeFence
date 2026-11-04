"""Oracle false-negative matrix: attack placement x extraction policy (audit Report 7 #5).

A false negative is a genuine boundary violation the generic C0/C1/C2 oracle MISSES.
This module estimates it with a controlled reference differential on Python stdlib
tarfile: each placement is extracted under ``fully_trusted`` (vulnerable) and ``data``
(the hardened PEP 706 filter, fixed) and judged by the production Observer + Oracle
through ``run_case`` -- the same construction as ``tests/test_python_tarfile_generality``.

Ground truth comes from the policy, not from the oracle: under ``fully_trusted`` the
placement genuinely reaches the sandbox sentinel or escapes ``extract/`` (ground-truth
POSITIVE), so the expected contract MUST fire; a miss is a false negative. Under ``data``
the placement is rejected (ground-truth NEGATIVE), so nothing should fire.

Only single-level ``..`` placements that land INSIDE the disposable sandbox temp dir are
executable in-process: they are created and removed there, never on the host. Absolute
targets, absolute names and multi-level escapes above the sandbox root would leave the
disposable sandbox, so they are NOT run here -- they are specified in ``RUNTIME_LANE_SPEC``
for the docker-isolated Runtime lane to run against real node-tar releases.

No oracle, mutator or feedback code references any placement; these are test INPUTS. The
sentinel target is read from ``SentinelSpec().name`` (the single source of truth), not a
hardcoded literal. Verdict rules are untouched (D038).

Run: PYTHONPATH=src python -m scripts.oracle_fn_matrix
"""

from __future__ import annotations

import json
import platform
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, ExecutionResult, ExecutionStatus
from inodefence.pipeline import run_case
from inodefence.runtime import SentinelSpec

Policy = Literal["fully_trusted", "data"]
Expected = tuple[bool, bool, bool]  # (C0, C1, C2) violated

# A fixture target, not oracle logic: the default sandbox sentinel's own name.
_SENTINEL = SentinelSpec().name


class PolicyExtractor:
    """Python stdlib tarfile under one extraction filter policy.

    ``fully_trusted`` applies no sanitation (affected); ``data`` applies the hardened
    PEP 706 filter (mitigated). Runs inside the BEFORE/AFTER window and writes nothing
    besides the extraction; archive rejection returns REJECTED rather than raising.
    """

    def __init__(self, policy: Policy) -> None:
        self.policy: Policy = policy

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        status, code, stderr = ExecutionStatus.SUCCESS, 0, ""
        try:
            with tarfile.open(archive_path, mode="r:") as archive:
                archive.errorlevel = 2
                archive.extractall(extraction_root, filter=self.policy)
        except tarfile.FilterError as error:
            status, code, stderr = ExecutionStatus.REJECTED, 2, f"{type(error).__name__}: {error}"
        except tarfile.TarError as error:
            status, code, stderr = ExecutionStatus.FAILED, 3, f"{type(error).__name__}: {error}"
        return ExecutionResult(
            f"python-tarfile-{self.policy.replace('_', '-')}",
            platform.python_version(),
            (),
            status,
            code,
            "",
            stderr[:200],
            0.0,
        )


@dataclass(frozen=True, slots=True)
class FnCase:
    """One placement whose ``fully_trusted`` extraction is a known boundary violation."""

    placement: str
    description: str
    case: ArchiveCase
    vulnerable_expected: Expected  # contracts that MUST fire under fully_trusted


EXECUTABLE_CASES: tuple[FnCase, ...] = (
    FnCase(
        "top-level-escape-c0",
        "regular '../escape.txt' creates a file at the sandbox root, outside extract/",
        ArchiveCase((ArchiveEntry("../escape.txt", EntryType.REGULAR, content=b"escape"),)),
        (True, False, False),
    ),
    FnCase(
        "top-level-hardlink-c1",
        f"hardlink 'alias' -> ../outside/{_SENTINEL} aliases the sentinel inode (C1 + C2)",
        ArchiveCase(
            (ArchiveEntry("alias", EntryType.HARDLINK, link_target=f"../outside/{_SENTINEL}"),)
        ),
        (False, True, True),
    ),
    FnCase(
        "top-level-symlink-write-c2",
        f"symlink 'link' -> ../outside/{_SENTINEL} then a regular write through it",
        ArchiveCase(
            (
                ArchiveEntry(
                    "link", EntryType.SYMLINK, link_target=f"../outside/{_SENTINEL}", mode=0o777
                ),
                ArchiveEntry("link", EntryType.REGULAR, content=b"through-symlink"),
            )
        ),
        (False, False, True),
    ),
    FnCase(
        "nested-symlink-write-c2",
        f"nested symlink 'deep/link' -> ../../outside/{_SENTINEL} then a regular write through it",
        ArchiveCase(
            (
                ArchiveEntry(
                    "deep/link",
                    EntryType.SYMLINK,
                    link_target=f"../../outside/{_SENTINEL}",
                    mode=0o777,
                ),
                ArchiveEntry("deep/link", EntryType.REGULAR, content=b"through-nested-symlink"),
            )
        ),
        (False, False, True),
    ),
    FnCase(
        "symlinked-dir-write-c2",
        f"symlink dir 'd' -> ../outside then regular 'd/{_SENTINEL}' writes via the dir symlink",
        ArchiveCase(
            (
                ArchiveEntry("d", EntryType.SYMLINK, link_target="../outside", mode=0o777),
                ArchiveEntry(f"d/{_SENTINEL}", EntryType.REGULAR, content=b"through-dir-symlink"),
            )
        ),
        (False, False, True),
    ),
)

# node-tar MVP vuln/fixed releases (D038). The Runtime lane confirms the exact set and
# runs each runtime-lane placement against each release pair inside docker isolation.
NODE_TAR_RELEASES: tuple[str, ...] = ("7.5.2", "7.5.3", "7.5.6", "7.5.7")

# Placements that must NOT run in-process (they leave the disposable sandbox). Data only;
# this module never executes them. The Runtime lane runs them under docker isolation.
RUNTIME_LANE_SPEC: tuple[dict[str, str], ...] = (
    {
        "placement": "absolute-symlink-target",
        "entry": "symlink 'link' -> /<abs sentinel path> then a regular write through it",
        "ground_truth": "positive (write reaches the sentinel via an absolute link)",
        "expected_contract": "C2 (and C1 if the write aliases the inode)",
        "reason": "absolute link target leaves the disposable sandbox; docker-only",
    },
    {
        "placement": "absolute-entry-name",
        "entry": "regular '/<abs>/escape' with an absolute member name",
        "ground_truth": "positive (write lands outside the extraction root)",
        "expected_contract": "C0",
        "reason": "an absolute member name would write to the host filesystem; docker-only",
    },
    {
        "placement": "multi-level-escape",
        "entry": "regular '../../escape' escaping two levels above extract/",
        "ground_truth": "positive (write lands above the sandbox temp root)",
        "expected_contract": "C0",
        "reason": "'../../' escapes above the disposable sandbox temp root; docker-only",
    },
)


def evaluate_executable(case: FnCase, policy: Policy) -> tuple[Expected, ExecutionStatus]:
    """Run one placement under one policy and return (observed verdicts, status)."""
    result = run_case(case.case, PolicyExtractor(policy))
    verdicts = tuple(verdict.violated for verdict in result.violations)
    assert len(verdicts) == 3
    return verdicts, result.execution.status  # type: ignore[return-value]


def main() -> int:
    """Run the executable subset under both policies; report any false negative."""
    false_negatives = 0
    print("# executable false-negative matrix (python-tarfile fully_trusted vs data)")
    for case in EXECUTABLE_CASES:
        vuln, vuln_status = evaluate_executable(case, "fully_trusted")
        fixed, fixed_status = evaluate_executable(case, "data")
        missed = vuln != case.vulnerable_expected
        leaked = fixed != (False, False, False)
        false_negatives += missed
        print(
            f"  {case.placement}: fully_trusted={vuln}({vuln_status.value}) "
            f"expected={case.vulnerable_expected} "
            f"{'FALSE-NEGATIVE' if missed else 'detected'} | "
            f"data={fixed}({fixed_status.value}) {'LEAK' if leaked else 'clean'}"
        )
    observed = len(EXECUTABLE_CASES)
    print(
        f"\nin-process false negatives: {false_negatives}/{observed} "
        f"(each placement is a ground-truth positive under fully_trusted)"
    )
    print("\n# runtime-lane spec (NOT executed here; docker-isolated node-tar)")
    print(
        json.dumps(
            {"node_tar_releases": NODE_TAR_RELEASES, "placements": RUNTIME_LANE_SPEC}, indent=2
        )
    )
    return 1 if false_negatives else 0


if __name__ == "__main__":
    raise SystemExit(main())
